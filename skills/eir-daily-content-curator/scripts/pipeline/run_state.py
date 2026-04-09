"""
Pipeline run state manager — enables resume from last checkpoint.

State file: data/v9/run_state.json
Each run has a unique run_id (date-based, one per calendar day).
Steps: search → candidates → crawl → generate → post → brief
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import V9_DIR, USED_SOURCE_URLS_FILE, PUSHED_TITLES_FILE, load_json

STATE_FILE = V9_DIR / "run_state.json"

STEPS = ["search", "candidates", "crawl", "generate", "brief"]


def _today_run_id():
    """Run ID = calendar date in local-ish form (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
    If today's run exists and is not complete, resume it.
    If today's run is complete or no run exists, create new.
    """
    state = load_state()
    today = _today_run_id()

    if state.get("run_id") == today and state.get("status") != "complete":
        # Resume
        return state, True

    # New run
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
    save_state(state)


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
    """Get ALL used source URLs: from state + pushed_titles + used_source_urls.json.
    This is the single source of truth for URL dedup.
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

    # 3. From current run state
    state = load_state()
    for u in state.get("posted_source_urls", []):
        urls.add(u)

    return urls


def persist_used_urls(urls):
    """Write used URLs to persistent file (called after successful run)."""
    existing = load_json(USED_SOURCE_URLS_FILE, [])
    if not isinstance(existing, list):
        existing = []
    all_urls = list(set(existing) | set(urls))
    USED_SOURCE_URLS_FILE.write_text(json.dumps(all_urls, indent=2))


def get_posted_topic_slugs():
    """Get topic slugs already posted today (for content-level dedup)."""
    state = load_state()
    today = _today_run_id()
    if state.get("run_id") != today:
        return set()
    return {p["topic"] for p in state.get("posted_ids", []) if p.get("topic")}
