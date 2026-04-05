#!/usr/bin/env python3
"""
Search Harvest — 纯脚本素材收集，不依赖 LLM。

Reads daily_plan.json (produced by daily_plan.py) for topics and queries.
Falls back to cached directives in degraded mode if daily_plan.json is missing/stale.

Budget-aware: stops gracefully when --max-time is approaching.
Incremental: saves progress after each topic.

Usage:
  python3 scripts/search_harvest.py                       # normal (reads daily_plan.json)
  python3 scripts/search_harvest.py --max-time 240        # stop after 240s
  python3 scripts/search_harvest.py --topic <slug>        # only process one topic
  python3 scripts/search_harvest.py --dry-run             # search only, no crawl
  python3 scripts/search_harvest.py --stats               # show current stats
"""

import json
import sys
import os
import hashlib
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Tuple, Set

sys.path.insert(0, str(Path(__file__).parent))
from embed import EmbeddingService
from cache_manager import ArticleEmbedCache, ContextCache, DATA_DIR, SNIPPETS_DIR

# === Config ===
DAILY_PLAN_FILE = DATA_DIR / "daily_plan.json"
PLAN_FILE = DATA_DIR / "plan.json"
DIRECTIVES_FILE = DATA_DIR / "directives.json"
TOPIC_MATCHES_FILE = DATA_DIR / "topic_matches.json"
HARVEST_STATS_FILE = DATA_DIR / "harvest_stats.json"
SOURCE_CACHE_FILE = DATA_DIR / "source_cache.json"
PUSHED_TITLES_FILE = DATA_DIR / "pushed_titles.json"

from eir_config import load_config, get_api_url, get_api_key, load_settings as _load_settings

_settings = _load_settings()
_search_cfg = _settings.get("search", {})
SEARCH_GATEWAY = _search_cfg.get("search_gateway_url", "http://localhost:8899")
SEARCH_TIMEOUT = 10  # seconds per search query
MAX_SEARCH_RESULTS = 8  # per query
MAX_INDEX_PER_TOPIC = 8  # max URLs to index per topic (no crawl)
TOPIC_MATCH_THRESHOLD = 0.52
TOPIC_MATCH_TOP_N = 20

POOL_SUFFICIENT = {
    "high": 6,
    "medium": 4,
    "low": 3,
}
POOL_SATURATED = 10

# eir_config already imported above

# Eir API (only used in degraded mode)


# ============================================================
# Data loading helpers
# ============================================================

def load_api_key():
    # type: () -> str
    return get_api_key()


def fetch_directives():
    # type: () -> Dict
    """Fetch directives from Eir API and cache locally. (degraded mode only)"""
    api_key = load_api_key()
    req = urllib.request.Request(
        "%s/oc/curation" % (get_api_url() + "/api"),
        headers={"Authorization": "Bearer %s" % api_key}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    data["_fetched_at"] = datetime.utcnow().isoformat() + "Z"
    DIRECTIVES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIRECTIVES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return data


def fetch_used_urls():
    # type: () -> Set[str]
    """Fetch already-used source URLs from Eir API. (degraded mode only)"""
    api_key = load_api_key()
    req = urllib.request.Request(
        "%s/oc/sources" % (get_api_url() + "/api"),
        headers={"Authorization": "Bearer %s" % api_key}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            urls = json.loads(resp.read())
        if isinstance(urls, list):
            return set(urls)
        return set(urls.get("sources", urls.get("urls", [])))
    except Exception as e:
        print("  ⚠️ Failed to fetch used URLs: %s" % e, file=sys.stderr)
        return set()


def directives_to_topics(data):
    # type: (Dict) -> List[Dict]
    """Convert Eir API directives to topic list with queries. (degraded mode)"""
    topics = []
    for d in data.get("directives", []) + data.get("tracked", []):
        hints = d.get("search_hints", {})
        suggested = hints.get("suggested_queries", [])
        keywords = d.get("keywords", [])

        queries = []
        for q in suggested:
            engine = hints.get("engine", "general")
            lang = hints.get("lang", "en")
            if lang == "zh" or any(u'\u4e00' <= c <= u'\u9fff' for c in q):
                engine = "china"
            queries.append({
                "q": q,
                "engine": engine,
                "freshness": d.get("freshness", "7d")
            })

        if len(queries) < 2 and keywords:
            kw_sample = keywords[:4]
            q_text = " ".join(kw_sample)
            has_zh = any(u'\u4e00' <= c <= u'\u9fff' for c in q_text)
            queries.append({
                "q": q_text + " 2026" if has_zh else q_text + " 2026",
                "engine": "china" if has_zh else "general",
                "freshness": d.get("freshness", "7d")
            })

        topics.append({
            "slug": d["slug"],
            "topic": d.get("topic", d["slug"]),
            "description": d.get("description", ""),
            "keywords": keywords,
            "type": d.get("type", "explore"),
            "priority": d.get("priority", "medium"),
            "queries": queries,
            "avoid_terms": hints.get("avoid_terms", []),
            "source": "eir-directive",
            "needs_search": True,
            "needs_generate": True,
            "pool_size": 0,
            "good_snippet_count": 0,
        })

    return topics


def load_plan():
    # type: () -> Optional[Dict]
    """Load plan.json if exists and fresh (< 36h). Legacy support."""
    if not PLAN_FILE.exists():
        return None
    plan = json.loads(PLAN_FILE.read_text())
    created = plan.get("created_at", "")
    if created:
        try:
            age = datetime.utcnow() - datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
            if age > timedelta(hours=36):
                return None
        except Exception:
            pass
    return plan


def plan_to_topics(plan):
    # type: (Dict) -> List[Dict]
    return plan.get("topics", [])


# ============================================================
# Daily plan loading (new primary path)
# ============================================================

def load_daily_plan():
    # type: () -> Optional[Dict]
    """Load daily_plan.json if it exists and is from today."""
    if not DAILY_PLAN_FILE.exists():
        return None
    try:
        plan = json.loads(DAILY_PLAN_FILE.read_text())
    except Exception:
        return None
    plan_date = plan.get("date", "")
    today = date.today().isoformat()
    if plan_date != today:
        print("  ⚠️ daily_plan.json is from %s (today=%s), entering degraded mode" % (plan_date, today),
              file=sys.stderr)
        return None
    return plan


def save_daily_plan(plan):
    # type: (Dict) -> None
    DAILY_PLAN_FILE.write_text(json.dumps(plan, indent=2, ensure_ascii=False))


def sort_topics_by_priority(topics, completed_topics):
    # type: (List[Dict], List[str]) -> List[Dict]
    """Sort topics: needs_generate first, then by pool_size ascending, then by priority."""
    priority_order = {"high": 0, "medium": 1, "low": 2}

    def sort_key(t):
        # type: (Dict) -> tuple
        slug = t["slug"]
        if slug in completed_topics:
            return (3, 999, 999, 999)  # push completed to end
        # RSS-covered topics go to end (but before completed)
        rss_back = 1 if t.get("rss_covered", False) else 0
        needs_gen = 0 if t.get("needs_generate", True) else 1
        pool = t.get("pool_size", 0)
        pri = priority_order.get(t.get("priority", "medium"), 1)
        return (rss_back, needs_gen, pri, pool)

    return sorted(topics, key=sort_key)


# ============================================================
# Search & Crawl
# ============================================================

def search_gateway(query, engine="general", limit=MAX_SEARCH_RESULTS):
    # type: (str, str, int) -> List[Dict]
    """Search via Search Gateway (localhost:8899)."""
    params = urllib.parse.urlencode({
        "q": query,
        "category": engine,
        "limit": limit
    })
    url = "%s/search?%s" % (SEARCH_GATEWAY, params)
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        return [{"url": r["url"], "title": r.get("title", ""), "snippet": r.get("snippet", r.get("content", "")),
                 "published_date": r.get("publishedDate", "")}
                for r in results if r.get("url")]
    except Exception as e:
        print("  ⚠️ Search Gateway failed for '%s': %s" % (query, e), file=sys.stderr)
        return []


def save_snippet(url, data):
    # type: (str, Dict) -> Path
    """Save crawled content to snippets directory."""
    SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    path = SNIPPETS_DIR / ("%s.json" % url_hash)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


# ============================================================
# Stats & Matches
# ============================================================

def load_harvest_stats():
    # type: () -> Dict
    if HARVEST_STATS_FILE.exists():
        return json.loads(HARVEST_STATS_FILE.read_text())
    return {"by_topic": {}, "global": {}, "runs": []}


def save_harvest_stats(stats):
    # type: (Dict) -> None
    HARVEST_STATS_FILE.write_text(json.dumps(stats, indent=2, ensure_ascii=False))


def load_topic_matches():
    # type: () -> Dict
    if TOPIC_MATCHES_FILE.exists():
        return json.loads(TOPIC_MATCHES_FILE.read_text())
    return {}


def save_topic_matches(matches):
    # type: (Dict) -> None
    TOPIC_MATCHES_FILE.write_text(json.dumps(matches, indent=2, ensure_ascii=False))


def update_topic_matches(svc, cache, topics):
    # type: (EmbeddingService, ArticleEmbedCache, List[Dict]) -> Dict
    """Recalculate topic→article matches using cosine similarity."""
    if len(cache.embeddings) == 0:
        print("  No articles in cache, skipping topic matching")
        return {}

    matches = load_topic_matches()

    for topic in topics:
        slug = topic["slug"]
        # Use enriched embedding_text if available (includes description + keywords),
        # otherwise fall back to basic topic name + description.
        topic_text = topic.get("embedding_text", "").strip()
        if not topic_text:
            topic_text = "%s %s %s" % (
                topic.get("topic", ""),
                topic.get("description", ""),
                " ".join(topic.get("keywords", [])[:8])
            )
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
    return matches


# ============================================================
# Topic harvesting
# ============================================================

def harvest_topic(topic, svc, cache, used_urls, existing_matches, completed_queries,
                  dry_run=False):
    # type: (Dict, EmbeddingService, ArticleEmbedCache, set, Dict, set, bool) -> Dict
    """Search for a topic, index title+snippet (no full-text crawl). Crawl deferred to content_curator."""
    slug = topic["slug"]
    priority = topic.get("priority", "medium")
    stats = {
        "queries_run": 0,
        "search_results": 0,
        "new_articles": 0,
        "duplicates_l0": 0,
        "duplicates_l1": 0,
        "skipped_reason": None,
        "queries_completed": [],
    }

    if not topic.get("needs_search", True):
        stats["skipped_reason"] = "daily_plan says no search needed"
        print("  ⏭️  Skipped: daily plan says no search needed")
        return stats

    existing = existing_matches.get(slug, {})
    pool_size = len(existing.get("matches", []))
    sufficient = POOL_SUFFICIENT.get(priority, 4)

    if pool_size >= POOL_SATURATED:
        stats["skipped_reason"] = "saturated (%d >= %d)" % (pool_size, POOL_SATURATED)
        print("  ⏭️  Skipped: pool saturated (%d articles)" % pool_size)
        return stats

    if pool_size >= sufficient:
        stats["skipped_reason"] = "sufficient (%d >= %d for %s)" % (pool_size, sufficient, priority)
        print("  ⏭️  Skipped: pool sufficient (%d/%d for %s priority)" % (pool_size, sufficient, priority))
        return stats

    print("  📊 Pool: %d/%d" % (pool_size, sufficient))

    new_urls = []

    for qinfo in topic.get("queries", []):
        query = qinfo["q"]
        engine = qinfo.get("engine", "general")
        query_key = "%s|%s|%s" % (slug, engine, query)
        if query_key in completed_queries:
            print("  ⏭️  Query already done today: %s" % query[:50])
            continue

        stats["queries_run"] += 1
        print("  🔍 [%s] %s" % (engine, query))
        results = search_gateway(query, engine=engine)
        stats["search_results"] += len(results)
        stats["queries_completed"].append(query_key)

        # Track query yield for rotation
        query_new_count = 0

        for r in results:
            url = r["url"]
            if url in used_urls:
                stats["duplicates_l0"] += 1
                continue
            is_dup, _ = cache.check_duplicate(url)
            if is_dup:
                stats["duplicates_l0"] += 1
                continue
            if any(x in url.lower() for x in [".pdf", ".zip", ".mp4", "youtube.com/watch", "twitter.com", "x.com"]):
                continue

            # Freshness filter: skip results with known-stale publish dates
            pub_date = r.get("published_date", "")
            if pub_date:
                try:
                    from dateutil import parser as dateparser
                    pub_dt = dateparser.parse(pub_date)
                    if pub_dt:
                        age_days = (datetime.now(pub_dt.tzinfo or timezone.utc) - pub_dt).days
                        if age_days > 14:
                            continue  # Skip articles older than 14 days
                except Exception:
                    pass  # Can't parse date, let it through

            # Title/snippet quality filter: skip if too short or clearly garbage
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            if len(title) < 10 or (len(snippet) < 30 and not title):
                continue

            new_urls.append({"url": url, "title": title, "snippet": snippet,
                            "query": query, "published_date": pub_date})
            query_new_count += 1

        # Mark query yield for rotation decisions
        stats.setdefault("query_yields", {})[query_key] = query_new_count
        if query_new_count == 0:
            print("    ⚠️ Query yielded 0 new results")

    # Deduplicate URLs
    seen = set()  # type: Set[str]
    unique_urls = []
    for u in new_urls:
        if u["url"] not in seen:
            seen.add(u["url"])
            unique_urls.append(u)
    new_urls = unique_urls[:MAX_INDEX_PER_TOPIC]

    if dry_run:
        print("  [dry-run] Would index %d URLs" % len(new_urls))
        return stats

    # Embed title+snippet (no crawl) and add to cache
    # Pre-compute topic embedding for relevance check
    topic_text = topic.get("embedding_text", "").strip()
    if not topic_text:
        topic_text = "%s %s %s" % (topic.get("topic", ""), topic.get("description", ""),
                                    " ".join(topic.get("keywords", [])[:8]))
    topic_embedding = svc.embed_queries([topic_text])[0] if topic_text else None

    for item in new_urls:
        url = item["url"]
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        embed_text = "%s. %s" % (title, snippet)
        embedding = svc.embed_passages([embed_text])[0]

        is_dup, reason = cache.check_duplicate(url, embedding=embedding)
        if is_dup:
            stats["duplicates_l1"] += 1
            continue

        # Topic relevance check: skip if embedding doesn't match this topic
        if topic_embedding is not None:
            import numpy as np
            score = float(np.dot(embedding, topic_embedding) /
                         (np.linalg.norm(embedding) * np.linalg.norm(topic_embedding) + 1e-9))
            if score < TOPIC_MATCH_THRESHOLD - 0.05:  # slightly looser than strict matching
                stats.setdefault("filtered_irrelevant", 0)
                stats["filtered_irrelevant"] += 1
                continue

        cache.add_article(url, title, embedding, extra={
            "source_name": urllib.parse.urlparse(url).netloc,
            "source_rating": "B",
            "harvest_topic": slug,
        })

        # Save lightweight snippet (pending full-text crawl by content_curator)
        SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        snippet_path = SNIPPETS_DIR / ("%s.json" % url_hash)
        if not snippet_path.exists():
            snippet_data = {
                "url": url,
                "title": title,
                "snippet": snippet[:500],
                "content": "",
                "crawl_status": "pending",
                "source_name": urllib.parse.urlparse(url).netloc,
                "source_rating": "B",
                "lang": "en",
                "published": item.get("published_date", ""),
                "fetched_at": datetime.utcnow().isoformat() + "Z",
                "harvest_topic": slug,
                "search_query": item.get("query", ""),
            }
            snippet_path.write_text(json.dumps(snippet_data, indent=2, ensure_ascii=False))

        stats["new_articles"] += 1
        used_urls.add(url)
        print("    ✅ Indexed: %s" % title[:60])

    return stats


# ============================================================
# Main
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Search Harvest — material collection")
    parser.add_argument("--dry-run", action="store_true", help="Search only, no crawl")
    parser.add_argument("--stats", action="store_true", help="Show current stats")
    parser.add_argument("--topic", type=str, help="Only process this topic slug")
    parser.add_argument("--max-time", type=int, default=240, help="Max run time in seconds (default 240)")
    # Legacy flags (kept for backward compat)
    parser.add_argument("--skip-api", action="store_true", help="(deprecated, now default behavior)")
    args = parser.parse_args()

    if args.stats:
        stats = load_harvest_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return

    start_time = time.time()
    max_time = args.max_time
    print("🌾 Search Harvest starting at %sZ (max-time=%ds)" % (datetime.utcnow().isoformat(), max_time))

    # === Load embedding service and cache ===
    svc = EmbeddingService()
    cache = ArticleEmbedCache(svc)
    print("  Cache: %d articles, %d URL hashes" % (cache.stats()["total_articles"], cache.stats()["url_hashes"]))

    # === Load daily plan or fall back to degraded mode ===
    daily_plan = load_daily_plan()
    degraded = False

    if daily_plan:
        topics = daily_plan["topics"]
        used_urls = set(daily_plan.get("used_urls", []))
        completed_queries = set(daily_plan.get("completed_queries", []))
        completed_topics = set(daily_plan.get("completed_topics", []))
        print("  📋 Using daily_plan.json (%d topics, %d completed queries)" % (
            len(topics), len(completed_queries)))
    else:
        degraded = True
        print("  ⚠️ No valid daily_plan.json — running in DEGRADED mode")
        completed_queries = set()  # type: Set[str]
        completed_topics = set()  # type: Set[str]

        # Try plan.json, then cached directives, then API
        plan = load_plan()
        if plan:
            topics = plan_to_topics(plan)
            print("  Using plan.json (%d topics)" % len(topics))
        elif DIRECTIVES_FILE.exists():
            data = json.loads(DIRECTIVES_FILE.read_text())
            topics = directives_to_topics(data)
            print("  Using cached directives.json (%d topics)" % len(topics))
        else:
            print("  Fetching directives from Eir API (degraded)...")
            data = fetch_directives()
            topics = directives_to_topics(data)
            print("  Got %d topics from API" % len(topics))

        # Load used URLs
        used_urls = set()  # type: Set[str]
        if SOURCE_CACHE_FILE.exists():
            try:
                local = json.loads(SOURCE_CACHE_FILE.read_text())
                if isinstance(local, dict):
                    used_urls = set(local.keys())
            except Exception:
                pass
        print("  %d URLs from local cache" % len(used_urls))

    # Filter by --topic
    if args.topic:
        topics = [t for t in topics if t["slug"] == args.topic]
        if not topics:
            print("  ❌ Topic '%s' not found" % args.topic)
            return

    # Sort by priority
    topics = sort_topics_by_priority(topics, completed_topics)

    # === Load existing topic matches ===
    existing_matches = load_topic_matches()
    print("  Existing topic matches: %d topics" % len(existing_matches))

    # === Harvest loop ===
    all_stats = load_harvest_stats()
    run_stats = {
        "started_at": datetime.utcnow().isoformat() + "Z",
        "topics_processed": 0,
        "topics_skipped": 0,
        "total_new_articles": 0,
        "total_duplicates": 0,
        "budget_stopped": False,
        "degraded_mode": degraded,
    }

    for topic in topics:
        slug = topic["slug"]

        # Budget check (skip for first topic to always process at least one)
        elapsed = time.time() - start_time
        remaining = max_time - elapsed
        if remaining < 60 and run_stats["topics_processed"] > 0:
            print("\n⏰ Budget exhausted (%.0fs elapsed, %.0fs remaining < 60s). Stopping gracefully." % (
                elapsed, remaining))
            run_stats["budget_stopped"] = True
            break

        # Skip completed topics
        if slug in completed_topics:
            print("\n⏭️  Topic %s already completed today" % slug)
            run_stats["topics_skipped"] += 1
            continue

        print("\n📌 Topic: %s [%s]" % (topic.get("topic", slug), topic.get("priority", "?")))

        topic_stats = harvest_topic(
            topic, svc, cache, used_urls, existing_matches,
            completed_queries, dry_run=args.dry_run
        )

        if topic_stats.get("skipped_reason"):
            run_stats["topics_skipped"] += 1

        # Update per-topic stats
        existing_stat = all_stats.get("by_topic", {}).get(slug, {})
        total_searches = existing_stat.get("total_searches", 0) + topic_stats["queries_run"]
        total_results = existing_stat.get("total_results", 0) + topic_stats["search_results"]
        total_new = existing_stat.get("total_new_articles", 0) + topic_stats["new_articles"]
        total_dup = existing_stat.get("total_duplicates", 0) + topic_stats["duplicates_l0"] + topic_stats["duplicates_l1"]
        dedup_rate = total_dup / max(total_results, 1)

        pool_size = len(existing_matches.get(slug, {}).get("matches", []))
        all_stats.setdefault("by_topic", {})[slug] = {
            "total_searches": total_searches,
            "total_results": total_results,
            "total_new_articles": total_new,
            "total_duplicates": total_dup,
            "dedup_rate": round(dedup_rate, 3),
            "pool_size": pool_size,
            "last_harvest": datetime.utcnow().isoformat() + "Z",
            "last_new_count": topic_stats["new_articles"],
            "last_skipped": topic_stats.get("skipped_reason"),
            "last_filtered_irrelevant": topic_stats.get("filtered_irrelevant", 0),
            "query_yields": topic_stats.get("query_yields", {}),
        }

        run_stats["topics_processed"] += 1
        run_stats["total_new_articles"] += topic_stats["new_articles"]
        run_stats["total_duplicates"] += topic_stats["duplicates_l0"] + topic_stats["duplicates_l1"]

        print("  → new: %d, dup_l0: %d, dup_l1: %d" % (
            topic_stats["new_articles"], topic_stats["duplicates_l0"],
            topic_stats["duplicates_l1"]))

        # === Incremental save after each topic ===
        if not args.dry_run:
            cache.save()

            # Update daily_plan.json progress
            if daily_plan:
                for qk in topic_stats.get("queries_completed", []):
                    completed_queries.add(qk)
                if not topic_stats.get("skipped_reason"):
                    completed_topics.add(slug)
                daily_plan["completed_queries"] = sorted(completed_queries)
                daily_plan["completed_topics"] = sorted(completed_topics)
                save_daily_plan(daily_plan)

        save_harvest_stats(all_stats)

    # === Final topic matches update ===
    if not args.dry_run:
        cache.save()
        print("\n💾 Cache saved: %d articles" % cache.stats()["total_articles"])

    print("\n🔗 Updating topic matches...")
    matches = update_topic_matches(svc, cache, topics)
    for slug, m in matches.items():
        n = len(m.get("matches", []))
        print("  %s: %d matches (of %d candidates)" % (slug, n, m.get("total_candidates", 0)))

    # === Save final stats ===
    elapsed = time.time() - start_time
    run_stats["elapsed_seconds"] = round(elapsed, 1)
    run_stats["finished_at"] = datetime.utcnow().isoformat() + "Z"
    all_stats.setdefault("runs", []).append(run_stats)
    all_stats["runs"] = all_stats["runs"][-50:]
    all_stats["global"] = {
        "total_articles_in_pool": cache.stats()["total_articles"],
        "total_url_hashes": cache.stats()["url_hashes"],
        "last_harvest": run_stats["finished_at"],
    }
    save_harvest_stats(all_stats)

    print("\n✅ Harvest complete in %.0fs — %d new, %d duplicates, %d topics skipped%s" % (
        elapsed, run_stats["total_new_articles"], run_stats["total_duplicates"],
        run_stats.get("topics_skipped", 0),
        " [BUDGET STOPPED]" if run_stats.get("budget_stopped") else ""))


if __name__ == "__main__":
    main()
