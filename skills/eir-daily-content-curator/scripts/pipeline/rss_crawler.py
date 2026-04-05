#!/usr/bin/env python3
"""
RSS Feed Crawler — fetches RSS feeds, embeds title+summary, stores in cache.
Does NOT crawl full article text. Full-text crawl is deferred to content_curator.py
which selectively crawls only articles matching user topics.

Usage:
  python3 rss_crawler.py                    # Index all feeds
  python3 rss_crawler.py --tier S           # Only S-tier feeds
  python3 rss_crawler.py --dry-run          # Parse feeds but don't embed
  python3 rss_crawler.py --stats            # Show feed stats
  python3 rss_crawler.py --max-time 180     # Time budget in seconds
"""

import json
import sys
import re
import hashlib
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from embed import EmbeddingService
from cache_manager import ArticleEmbedCache, SNIPPETS_DIR, DATA_DIR
from eir_config import SKILL_DIR, CONFIG_DIR

# Sources: check workspace config first, then skill default
SOURCES_FILE = CONFIG_DIR / "sources.json"
SKILL_SOURCES_FILE = SKILL_DIR / "config" / "sources.json"
MAX_ITEMS_PER_FEED = 10

TIER_INTERVAL_HOURS = {"S": 4, "A": 8, "B": 24}
FEED_STATE_FILE = DATA_DIR / "feed_state.json"


def load_sources():
    for path in [SOURCES_FILE, SKILL_SOURCES_FILE]:
        if path.exists():
            try:
                return json.loads(path.read_text()).get("rss", [])
            except (json.JSONDecodeError, KeyError):
                continue
    return []
    return json.loads(SOURCES_FILE.read_text()).get("rss", [])


def load_feed_state():
    if FEED_STATE_FILE.exists():
        return json.loads(FEED_STATE_FILE.read_text())
    return {}


def save_feed_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FEED_STATE_FILE.write_text(json.dumps(state, indent=2))


def should_crawl_feed(feed, state):
    tier = feed.get("rating", "B")
    interval = TIER_INTERVAL_HOURS.get(tier, 24)
    last_crawl = state.get(feed["url"], {}).get("last_crawl")
    if not last_crawl:
        return True
    try:
        last_dt = datetime.fromisoformat(last_crawl.replace("Z", "+00:00")).replace(tzinfo=None)
        return datetime.utcnow() - last_dt >= timedelta(hours=interval)
    except Exception:
        return True


def fetch_rss(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Eir-Curator/1.0"})
        data = urllib.request.urlopen(req, timeout=15).read()
        root = ET.fromstring(data)
    except Exception as e:
        print(f"  ⚠️  Feed error: {e}")
        return []

    items = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for item in root.findall(".//item")[:MAX_ITEMS_PER_FEED]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title and link:
            desc = re.sub(r"<[^>]+>", " ", desc)
            desc = re.sub(r"\s+", " ", desc).strip()[:500]
            items.append({"title": title, "url": link, "summary": desc, "published": pub})

    for entry in root.findall(".//atom:entry", ns)[:MAX_ITEMS_PER_FEED]:
        title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
        link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        summary = (entry.findtext("atom:summary", namespaces=ns) or entry.findtext("atom:content", namespaces=ns) or "").strip()
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = re.sub(r"\s+", " ", summary).strip()[:500]
        pub = (entry.findtext("atom:updated", namespaces=ns) or entry.findtext("atom:published", namespaces=ns) or "").strip()
        if title and link:
            items.append({"title": title, "url": link, "summary": summary, "published": pub})

    return items


def _load_topic_embeddings(svc):
    """Pre-compute topic embeddings for pre-filter. Returns (embeddings, threshold) or (None, 0)."""
    try:
        from search_harvest import load_daily_plan, DIRECTIVES_FILE, directives_to_topics
        from search_harvest import TOPIC_MATCH_THRESHOLD

        daily_plan = load_daily_plan()
        if daily_plan:
            topics = daily_plan.get("topics", [])
        elif DIRECTIVES_FILE.exists():
            data = json.loads(DIRECTIVES_FILE.read_text())
            topics = directives_to_topics(data)
        else:
            return None, 0

        # Only match tracked + focus (same as _update_topic_matches)
        RSS_MATCH_TYPES = {"track", "tracked", "focus"}
        topics = [t for t in topics if t.get("type", "") in RSS_MATCH_TYPES]
        if not topics:
            return None, 0

        topic_texts = []
        for t in topics:
            txt = t.get("embedding_text", "").strip()
            if not txt:
                txt = f"{t.get('topic', '')} {t.get('description', '')} {' '.join(t.get('keywords', [])[:8])}"
            topic_texts.append(txt)

        topic_embs = svc.embed_queries(topic_texts)
        # Use a looser threshold for pre-filter (catch more, let dispatcher decide)
        prefilter_threshold = max(TOPIC_MATCH_THRESHOLD - 0.08, 0.35)
        return topic_embs, prefilter_threshold
    except Exception as e:
        print(f"⚠️ Topic pre-filter init failed: {e}", file=sys.stderr)
        return None, 0


def _passes_prefilter(emb, topic_embs, threshold, svc):
    """Check if article embedding matches any topic above threshold."""
    if topic_embs is None:
        return True  # No pre-filter available, pass everything
    import numpy as np
    for t_emb in topic_embs:
        score = float(np.dot(emb, t_emb) / (np.linalg.norm(emb) * np.linalg.norm(t_emb) + 1e-9))
        if score >= threshold:
            return True
    return False


def run_crawl(tier_filter=None, dry_run=False, max_time=0):
    """Fetch RSS feeds, embed title+summary only. No full-text crawl."""
    crawl_start = time.time()
    sources = load_sources()
    if not sources:
        print("No sources found.")
        return

    state = load_feed_state()
    svc = EmbeddingService()
    cache = ArticleEmbedCache(svc)

    # Pre-compute topic embeddings for relevance filtering
    topic_embs, prefilter_threshold = _load_topic_embeddings(svc)
    if topic_embs is not None:
        print(f"🎯 Pre-filter active: {len(topic_embs)} topics, threshold={prefilter_threshold:.2f}")
    else:
        print("⚠️ Pre-filter unavailable, storing all articles")

    total_new = 0
    total_dup = 0
    total_filtered = 0

    for feed in sources:
        tier = feed.get("rating", "B")
        name = feed.get("name", "?")

        if tier_filter and tier != tier_filter:
            continue
        if max_time > 0 and (time.time() - crawl_start) > max_time - 20:
            print(f"⏰ Time budget reached")
            break
        if not should_crawl_feed(feed, state):
            continue

        print(f"\n📡 {name} (tier {tier})")
        items = fetch_rss(feed["url"])
        print(f"  Fetched {len(items)} items")
        prev_filtered = total_filtered

        if dry_run:
            for it in items[:3]:
                print(f"    - {it['title'][:70]}")
            state.setdefault(feed["url"], {})["last_crawl"] = datetime.utcnow().isoformat() + "Z"
            continue

        new_count = 0
        for it in items:
            is_dup, _ = cache.check_duplicate(it["url"])
            if is_dup:
                total_dup += 1
                continue

            # Embed title + RSS summary (no crawl)
            embed_text = f"{it['title']}. {it.get('summary', '')}"
            emb = svc.embed_passages([embed_text])[0]

            is_dup, reason = cache.check_duplicate(it["url"], emb)
            if is_dup:
                total_dup += 1
                continue

            # Pre-filter: skip articles that don't match any topic
            if not _passes_prefilter(emb, topic_embs, prefilter_threshold, svc):
                total_filtered += 1
                continue

            cache.add_article(it["url"], it["title"], emb, extra={
                "source_name": name,
                "source_rating": tier,
                "published": it.get("published", ""),
                "summary": it.get("summary", "")[:300],
            })

            # Save lightweight snippet (pending full-text crawl by content_curator)
            SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
            url_hash = hashlib.md5(it["url"].encode()).hexdigest()[:12]
            snippet_path = SNIPPETS_DIR / f"{url_hash}.json"
            if not snippet_path.exists():
                snippet = {
                    "url": it["url"],
                    "title": it["title"],
                    "snippet": it.get("summary", "")[:500],
                    "content": "",
                    "crawl_status": "pending",
                    "source_name": name,
                    "source_rating": tier,
                    "lang": feed.get("lang", "en"),
                    "published": it.get("published", ""),
                    "fetched_at": datetime.utcnow().isoformat() + "Z",
                }
                snippet_path.write_text(json.dumps(snippet, indent=2, ensure_ascii=False))

            new_count += 1
            total_new += 1

        print(f"  New: {new_count}, Dup: {len(items) - new_count - (total_filtered - prev_filtered)}, Filtered: {total_filtered - prev_filtered}")
        state[feed["url"]] = {
            "last_crawl": datetime.utcnow().isoformat() + "Z",
            "last_items": len(items),
            "last_new": new_count,
            "dup_rate": round((len(items) - new_count) / max(len(items), 1), 2),
        }
        cache.save()
        save_feed_state(state)

    # Update topic matches
    _update_topic_matches(svc, cache)

    elapsed = time.time() - crawl_start
    print(f"\n✅ RSS done in {elapsed:.0f}s — {total_new} new, {total_dup} dup, "
          f"{total_filtered} filtered (irrelevant), "
          f"cache: {cache.stats()['total_articles']} articles")


def _update_topic_matches(svc, cache):
    """Recalculate topic matches using enriched embedding_text."""
    try:
        from search_harvest import load_topic_matches, save_topic_matches
        from search_harvest import TOPIC_MATCH_THRESHOLD, TOPIC_MATCH_TOP_N
        from search_harvest import DIRECTIVES_FILE, load_daily_plan

        daily_plan = load_daily_plan()
        if daily_plan:
            topics = daily_plan.get("topics", [])
        elif DIRECTIVES_FILE.exists():
            from search_harvest import directives_to_topics
            data = json.loads(DIRECTIVES_FILE.read_text())
            topics = directives_to_topics(data)
        else:
            topics = []

        # RSS only matches broad tier-1/2 topics (tracked + focus).
        # Niche topics (explore, seed) rely on targeted search results.
        RSS_MATCH_TYPES = {"track", "tracked", "focus"}
        topics = [t for t in topics if t.get("type", "") in RSS_MATCH_TYPES]

        if not topics or len(cache.embeddings) == 0:
            return

        matches = load_topic_matches()
        for topic in topics:
            slug = topic["slug"]
            topic_text = topic.get("embedding_text", "").strip()
            if not topic_text:
                topic_text = f"{topic.get('topic', '')} {topic.get('description', '')} {' '.join(topic.get('keywords', [])[:8])}"
            topic_emb = svc.embed_queries([topic_text])[0]
            scores = svc.cosine_batch(topic_emb, cache.embeddings)
            article_list = cache.meta.get("articles", [])
            scored = []
            for i, score in enumerate(scores):
                if score >= TOPIC_MATCH_THRESHOLD and i < len(article_list):
                    art = article_list[i]
                    scored.append({
                        "article_idx": i,
                        "url": art["url"],
                        "title": art.get("title", ""),
                        "score": round(float(score), 4),
                        "source_name": art.get("source_name", ""),
                        "added_at": art.get("added_at", ""),
                    })
            scored.sort(key=lambda x: x["score"], reverse=True)
            matches[slug] = {
                "topic": topic.get("topic", slug),
                "type": topic.get("type", ""),
                "priority": topic.get("priority", ""),
                "matches": scored[:TOPIC_MATCH_TOP_N],
                "total_candidates": len(scored),
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
        save_topic_matches(matches)
        print(f"Topic matches updated: {len(matches)} topics")
    except Exception as e:
        print(f"⚠️ Topic match update skipped: {e}", file=sys.stderr)


def show_stats():
    state = load_feed_state()
    sources = load_sources()
    print("=== Feed Stats ===\n")
    for feed in sources:
        s = state.get(feed["url"], {})
        name = feed.get("name", "?")
        tier = feed.get("rating", "?")
        due = should_crawl_feed(feed, state)
        marker = "🔴 DUE" if due else "✅"
        print(f"  {marker} {name:20s} tier={tier} | last={s.get('last_crawl', 'never')[:19]} "
              f"items={s.get('last_items', '?')} new={s.get('last_new', '?')}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--stats" in args:
        show_stats()
    else:
        tier = args[args.index("--tier") + 1] if "--tier" in args else None
        dry_run = "--dry-run" in args
        mt = int(args[args.index("--max-time") + 1]) if "--max-time" in args else 0
        run_crawl(tier_filter=tier, dry_run=dry_run, max_time=mt)
