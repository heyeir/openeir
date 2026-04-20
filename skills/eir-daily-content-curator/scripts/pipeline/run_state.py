"""
Pipeline run state manager — enables resume from last checkpoint.

State file: data/v9/run_state.json
One run at a time. Run continues until complete, then new run can start.
Steps: search → candidates → crawl → generate → brief
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import V9_DIR, USED_SOURCE_URLS_FILE, PUSHED_TITLES_FILE, load_json

STATE_FILE = V9_DIR / "run_state.json"

STEPS = ["search", "candidates", "crawl", "generate"]

# Bloom filter for URL dedup (memory-efficient for large URL sets)
_BLOOM_SIZE = 100000  # 100K bits ≈ 12.5KB, enough for thousands of URLs
_BLOOM_HASHES = 5


class URLBloomFilter:
    """Simple bloom filter for URL dedup with O(1) lookup."""
    
    def __init__(self, size=_BLOOM_SIZE, hashes=_BLOOM_HASHES):
        self.size = size
        self.hashes = hashes
        self.bits = [False] * size
        self.count = 0

    def _hashes_for(self, url):
        import hashlib
        h = hashlib.md5(url.encode()).hexdigest()
        # MD5 gives 32 hex chars, use chunks of 6 chars for 5 hashes
        for i in range(self.hashes):
            start = (i * 6) % 30
            yield int(h[start:start+6], 16) % self.size

    def add(self, url):
        """Add URL to filter."""
        for i in self._hashes_for(url):
            self.bits[i] = True
        self.count += 1

    def might_contain(self, url):
        """Check if URL might be in filter (may have false positives)."""
        return all(self.bits[i] for i in self._hashes_for(url))

    def to_dict(self):
        return {"size": self.size, "bits": "".join("1" if b else "0" for b in self.bits), "count": self.count}

    @classmethod
    def from_dict(cls, d):
        bf = cls(d.get("size", _BLOOM_SIZE))
        bits_str = d.get("bits", "")
        bf.bits = [c == "1" for c in bits_str] if bits_str else [False] * bf.size
        bf.count = d.get("count", 0)
        return bf


# Global bloom filter (loaded once)
_url_bloom = None


def _get_bloom_filter():
    """Get or create the global URL bloom filter."""
    global _url_bloom
    if _url_bloom is not None:
        return _url_bloom
    
    # Try loading from file
    bloom_file = V9_DIR / "url_bloom.json"
    if bloom_file.exists():
        try:
            d = load_json(bloom_file, {})
            _url_bloom = URLBloomFilter.from_dict(d)
            return _url_bloom
        except Exception:
            pass
    
    # Create new and populate from existing URLs
    _url_bloom = URLBloomFilter()
    urls = get_all_used_urls()
    for u in urls:
        _url_bloom.add(u)
    return _url_bloom


def _save_bloom_filter():
    """Persist bloom filter to file."""
    global _url_bloom
    if _url_bloom is None:
        return
    bloom_file = V9_DIR / "url_bloom.json"
    bloom_file.write_text(json.dumps(_url_bloom.to_dict()))


def load_state():
    """Load current run state."""
    return load_json(STATE_FILE, {})


def save_state(state):
    """Persist run state."""
    V9_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def get_or_create_run():
    """Get today's run or create a new one.
    Returns (state, is_resume).
    Logic:
    - If today's run exists and is not complete → resume
    - Otherwise → start new run for today
    Managed by calendar day so each day gets one fresh pipeline cycle.
    """
    state = load_state()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Resume if today's run exists and is not complete
    if state.get("run_id") == today and state.get("status") not in ("complete", ""):
        return state, True

    # New run for today
    state = {
        "run_id": today,
        "status": "started",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "steps": {},
        "posted_ids": [],
        "posted_source_urls": [],
        "errors": [],
        "log": [],
    }
    save_state(state)
    return state, False


def mark_step(state, step, status, details=None):
    """Mark a step as done/error with optional details."""
    state["steps"][step] = {
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if details:
        state["steps"][step].update(details)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # If error, mark run as error and notify
    if status == "error":
        state["status"] = "error"
        state["error_at"] = datetime.now(timezone.utc).isoformat()
        error_msg = details.get("error", "Unknown error") if details else "Unknown error"
        state.setdefault("errors", []).append({
            "step": step,
            "error": error_msg,
            "at": datetime.now(timezone.utc).isoformat(),
        })
    
    save_state(state)
    
    # Notify on error (called by agent, not here directly)
    if status == "error":
        return error_msg
    return None


def is_step_done(state, step):
    """Check if a step completed successfully."""
    return state.get("steps", {}).get(step, {}).get("status") == "done"


def mark_complete(state):
    """Mark the entire run as complete."""
    state["status"] = "complete"
    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


def log_entry(state, msg):
    """Append a log entry."""
    state.setdefault("log", []).append({
        "t": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "msg": msg,
    })
    save_state(state)


def record_posted_url(state, url):
    """Record a source URL as posted (for dedup)."""
    state.setdefault("posted_source_urls", [])
    if url not in state["posted_source_urls"]:
        state["posted_source_urls"].append(url)
    # Also add to bloom filter
    bf = _get_bloom_filter()
    bf.add(url)
    _save_bloom_filter()
    save_state(state)


def record_posted_id(state, content_id, content_group, slug, topic_slug):
    """Record a posted content item."""
    state.setdefault("posted_ids", [])
    state["posted_ids"].append({
        "id": content_id,
        "group": content_group,
        "slug": slug,
        "topic": topic_slug,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    save_state(state)


def get_all_used_urls():
    """Get ALL used source URLs: from used_source_urls.json + pushed_titles.
    This is the source of truth for populating bloom filter.
    """
    urls = set()

    # 1. From used_source_urls.json (cross-run persistent)
    used = load_json(USED_SOURCE_URLS_FILE, [])
    if isinstance(used, list):
        urls.update(used)

    # 2. From pushed_titles.json
    pushed = load_json(PUSHED_TITLES_FILE, [])
    if isinstance(pushed, list):
        for p in pushed:
            for u in p.get("source_urls", []):
                urls.add(u)

    return urls


def url_is_used(url):
    """Fast bloom filter check if URL is likely already used."""
    bf = _get_bloom_filter()
    return bf.might_contain(url)


def persist_used_urls(urls):
    """Write used URLs to persistent file (called after successful run)."""
    existing = load_json(USED_SOURCE_URLS_FILE, [])
    if not isinstance(existing, list):
        existing = []
    all_urls = list(set(existing) | set(urls))
    USED_SOURCE_URLS_FILE.write_text(json.dumps(all_urls, indent=2))
    
    # Also update bloom filter
    bf = _get_bloom_filter()
    for u in urls:
        bf.add(u)
    _save_bloom_filter()


def get_posted_topic_slugs():
    """Get topic slugs already posted (today + historical from pushed_titles).
    This enables cross-day topic dedup to avoid repeating the same topic."""
    topics = set()
    
    # 1. Today's run_state
    state = load_state()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.get("run_id") == today:
        for p in state.get("posted_ids", []):
            if p.get("topic"):
                topics.add(p["topic"])
    
    # 2. Historical from pushed_titles.json
    pushed = load_json(PUSHED_TITLES_FILE, [])
    if isinstance(pushed, list):
        for p in pushed:
            ts = p.get("topic_slug")
            if ts and ts != "":
                topics.add(ts)
    
    return topics


def get_recent_posted_events(days=3):
    """Return list of {slug, title, topic} for posts in the last `days` days.
    Used for event-level semantic dedup."""
    import glob
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events = []
    
    state = load_state()
    for p in state.get("posted_ids", []):
        at_str = p.get("at", "")
        if not at_str:
            continue
        try:
            at = datetime.fromisoformat(at_str)
            if at < cutoff:
                continue
        except (ValueError, TypeError):
            continue
        events.append({
            "slug": p.get("slug", ""),
            "topic": p.get("topic", ""),
            "title": "",  # run_state doesn't have title, will enrich below
        })
    
    # Enrich with titles from posted/ and generated/ directories
    posted_dir = V9_DIR / "posted"
    generated_dir = V9_DIR / "generated"
    for ev in events:
        slug = ev["slug"]
        for d in [posted_dir, generated_dir]:
            path = d / ("%s_zh.json" % slug)
            if path.exists():
                try:
                    data = load_json(path, {})
                    ev["title"] = data.get("l1", {}).get("title", "")
                    break
                except Exception:
                    pass
    
    return events


def get_posted_content_slugs():
    """Get content slugs already posted (all-time from pushed_titles).
    Dedup by content_slug (not topic_slug) — same topic with different
    angle/event is allowed; only identical content is blocked."""
    slugs = set()
    
    # 1. Today's run_state
    state = load_state()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.get("run_id") == today:
        for p in state.get("posted_ids", []):
            if p.get("slug"):
                slugs.add(p["slug"])
    
    # 2. Historical from pushed_titles.json
    pushed = load_json(PUSHED_TITLES_FILE, [])
    if isinstance(pushed, list):
        for p in pushed:
            s = p.get("slug")
            if s and s != "":
                slugs.add(s)
    
    return slugs


def get_error_for_notification():
    """Get error info for user notification (if run is in error state)."""
    state = load_state()
    if state.get("status") != "error":
        return None
    errors = state.get("errors", [])
    if not errors:
        return {"step": "unknown", "error": "Unknown error"}
    last = errors[-1]
    return {
        "run_id": state.get("run_id"),
        "step": last.get("step"),
        "error": last.get("error"),
        "at": last.get("at"),
    }