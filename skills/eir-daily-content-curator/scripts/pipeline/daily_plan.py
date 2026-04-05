#!/usr/bin/env python3
"""
Daily Planning — fetch directives from Eir API, analyze local state, produce daily_plan.json.

Run once per day (e.g. 4am via cron). All other scripts read daily_plan.json instead of calling API.

Usage:
  python3 scripts/daily_plan.py              # normal run
  python3 scripts/daily_plan.py --dry-run    # print plan without writing
"""

import json
import sys
import os
import time
import urllib.request
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Set, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from cache_manager import DATA_DIR, SNIPPETS_DIR

# === Config ===
DAILY_PLAN_FILE = DATA_DIR / "daily_plan.json"
DIRECTIVES_FILE = DATA_DIR / "directives.json"
TOPIC_MATCHES_FILE = DATA_DIR / "topic_matches.json"
HARVEST_STATS_FILE = DATA_DIR / "harvest_stats.json"
PUSHED_TITLES_FILE = DATA_DIR / "pushed_titles.json"
SOURCE_CACHE_FILE = DATA_DIR / "source_cache.json"

FEED_STATE_FILE = DATA_DIR / "feed_state.json"
TOPIC_ENRICHMENTS_FILE = DATA_DIR / "topic_enrichments.json"

from eir_config import load_config, get_api_url, get_api_key

# Pool thresholds (same as search_harvest.py)
POOL_SUFFICIENT = {"high": 6, "medium": 4, "low": 3}
POOL_SATURATED = 10


def load_api_key():
    # type: () -> str
    return get_api_key()


def fetch_directives():
    # type: () -> Dict
    """Fetch directives from Eir API and cache locally."""
    api_key = load_api_key()
    req = urllib.request.Request(
        "%s/oc/content" % (get_api_url() + "/api"),
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
    """Fetch already-used source URLs from Eir API."""
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


def load_pushed_titles():
    # type: () -> List[Dict]
    if PUSHED_TITLES_FILE.exists():
        data = json.loads(PUSHED_TITLES_FILE.read_text())
        if isinstance(data, list):
            return data
        return []
    return []


def load_topic_matches():
    # type: () -> Dict
    if TOPIC_MATCHES_FILE.exists():
        return json.loads(TOPIC_MATCHES_FILE.read_text())
    return {}


def load_harvest_stats():
    # type: () -> Dict
    if HARVEST_STATS_FILE.exists():
        return json.loads(HARVEST_STATS_FILE.read_text())
    return {}


def count_snippets_by_topic(topic_matches=None):
    # type: (Optional[Dict]) -> Dict[str, int]
    """Count good snippets (>=500c) per topic using topic_matches URL mapping.

    Falls back to harvest_topic tag if topic_matches is not provided.
    """
    counts = {}  # type: Dict[str, int]
    if not SNIPPETS_DIR.exists():
        return counts

    # Build url -> content_len index from snippet files
    if topic_matches:
        url_lens = {}  # type: Dict[str, int]
        for f in SNIPPETS_DIR.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                url = d.get("url", "")
                content = d.get("content") or d.get("snippet") or ""
                if url:
                    url_lens[url] = len(content)
            except Exception:
                pass

        # Count good snippets per topic via topic_matches
        for slug, info in topic_matches.items():
            good = 0
            for m in info.get("matches", []):
                url = m.get("url", "")
                if url_lens.get(url, 0) >= 500:
                    good += 1
            counts[slug] = good
        return counts

    # Fallback: count by harvest_topic tag
    for f in SNIPPETS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            topic = d.get("harvest_topic", "")
            if topic:
                counts[topic] = counts.get(topic, 0) + 1
        except Exception:
            pass
    return counts


def load_topic_enrichments():
    # type: () -> Dict
    if TOPIC_ENRICHMENTS_FILE.exists():
        try:
            return json.loads(TOPIC_ENRICHMENTS_FILE.read_text())
        except Exception:
            pass
    return {}


def directives_to_queries(d, enrichment=None):
    # type: (Dict, Optional[Dict]) -> List[Dict]
    """Convert a single directive to query list, using enrichment if available."""
    hints = d.get("search_hints") or {}
    suggested = hints.get("suggested_queries") or []
    keywords = d.get("keywords") or []
    topic_name = d.get("topic") or d.get("name") or ""
    description = d.get("description") or ""

    # Merge enriched queries if API has none
    if not suggested and enrichment:
        suggested = enrichment.get("search_queries", [])
    # Merge enriched keywords if API has none
    if not keywords and enrichment:
        keywords = enrichment.get("keywords_enriched", [])

    queries = []
    for q in suggested:
        engine = hints.get("engine", "general")
        lang = hints.get("lang", "en")
        if lang == "zh" or any(u'\u4e00' <= c <= u'\u9fff' for c in q):
            engine = "china"
        queries.append({
            "q": q,
            "engine": engine,
            "freshness": d.get("freshness", "7d"),
        })

    if len(queries) < 2 and keywords:
        kw_sample = keywords[:4]
        q_text = " ".join(kw_sample)
        has_zh = any(u'\u4e00' <= c <= u'\u9fff' for c in q_text)
        queries.append({
            "q": q_text + " 2026",
            "engine": "china" if has_zh else "general",
            "freshness": d.get("freshness", "7d"),
        })

    # Ensure every topic gets at least 2 queries by generating from name/description
    if len(queries) < 2 and topic_name:
        has_zh = any(u'\u4e00' <= c <= u'\u9fff' for c in topic_name)
        engine = "china" if has_zh else "general"
        # Query 1: topic name + recent
        queries.append({
            "q": f"{topic_name} latest research 2026" if not has_zh else f"{topic_name} 最新进展 2026",
            "engine": engine,
            "freshness": "7d",
        })
        # Query 2: topic name + description keywords
        if description and len(queries) < 3:
            desc_words = description.split()[:6]
            desc_query = " ".join(desc_words)
            queries.append({
                "q": desc_query,
                "engine": engine,
                "freshness": "7d",
            })

    return queries


def check_rss_coverage(topics, today_str):
    # type: (List[Dict], str) -> Dict[str, bool]
    """Check which topics already have sufficient fresh RSS articles from today."""
    topic_matches = load_topic_matches()
    feed_state = {}  # type: Dict
    if FEED_STATE_FILE.exists():
        try:
            feed_state = json.loads(FEED_STATE_FILE.read_text())
        except Exception:
            pass

    # Check if any RSS crawl happened today
    rss_ran_today = False
    for url, info in feed_state.items():
        lc = info.get("last_crawl", "")
        if lc.startswith(today_str):
            rss_ran_today = True
            break

    if not rss_ran_today:
        return {}

    coverage = {}  # type: Dict[str, bool]
    for topic in topics:
        slug = topic["slug"]
        matches_info = topic_matches.get(slug, {})
        matches = matches_info.get("matches", [])
        # Count matches added today (from RSS — check added_at starts with today)
        fresh_count = 0
        for m in matches:
            added = m.get("added_at", "")
            if added.startswith(today_str):
                fresh_count += 1
        pool_size = len(matches)
        # RSS covered if >=2 fresh articles today AND pool is not tiny
        if fresh_count >= 2 and pool_size >= 3:
            coverage[slug] = True
    return coverage


def build_plan(data, used_urls, today_str):
    # type: (Dict, Set[str], str) -> Dict
    """Build the daily plan from directives + local state + topic enrichments."""
    topic_matches = load_topic_matches()
    snippet_counts = count_snippets_by_topic(topic_matches)
    pushed = load_pushed_titles()
    enrichments = load_topic_enrichments()
    rss_coverage = check_rss_coverage([], today_str)  # will be updated below

    # Which slugs have content pushed today?
    pushed_today = set()  # type: Set[str]
    for item in pushed:
        pushed_at = item.get("pushed_at", "")
        if pushed_at.startswith(today_str):
            pushed_today.add(item.get("slug", ""))

    topics = []
    all_directives = data.get("directives", []) + data.get("tracked", [])

    for d in all_directives:
        slug = d["slug"]
        priority = d.get("priority", "medium")
        dtype = d.get("type", "explore")
        enrichment = enrichments.get(slug, {})

        # Pool analysis
        matches_info = topic_matches.get(slug, {})
        pool_size = len(matches_info.get("matches", []))
        good_snippet_count = snippet_counts.get(slug, 0)
        sufficient = POOL_SUFFICIENT.get(priority, 4)

        # Determine needs
        needs_search = pool_size < POOL_SATURATED and pool_size < sufficient

        # Check RSS coverage — if RSS already provided enough fresh articles, skip search
        rss_covered = False
        # Re-check per topic: count today's matches
        matches_list = matches_info.get("matches", [])
        fresh_from_rss = sum(1 for m in matches_list if m.get("added_at", "").startswith(today_str))
        if fresh_from_rss >= 2 and pool_size >= 3:
            rss_covered = True
            needs_search = False

        needs_generate = slug not in pushed_today

        queries = directives_to_queries(d, enrichment=enrichment)

        # Merge enriched description/keywords if API directive is sparse
        description = d.get("description") or ""
        keywords = d.get("keywords") or []
        embedding_text = ""
        if enrichment:
            if not description:
                description = enrichment.get("description_enriched", "")
            if not keywords:
                keywords = enrichment.get("keywords_enriched", [])
            embedding_text = enrichment.get("embedding_text", "")

        topics.append({
            "slug": slug,
            "topic": d.get("topic", slug),
            "description": description,
            "keywords": keywords,
            "embedding_text": embedding_text,
            "type": dtype,
            "priority": priority,
            "queries": queries,
            "avoid_terms": (d.get("search_hints") or {}).get("avoid_terms", []),
            "needs_search": needs_search,
            "needs_generate": needs_generate,
            "rss_covered": rss_covered,
            "pool_size": pool_size,
            "good_snippet_count": good_snippet_count,
        })

    # Detect if all strong-interest topics are saturated (pushed recently + no new material)
    # If so, flag that explore topics should be sourced from unmatched snippets
    from datetime import timedelta
    cooldown_cutoff = (datetime.utcnow() - timedelta(hours=20)).isoformat() + "Z"
    recently_pushed_slugs = set()
    for item in pushed:
        if item.get("pushed_at", "") >= cooldown_cutoff:
            recently_pushed_slugs.add(item.get("slug", ""))

    strong_topics = [t for t in topics if t["priority"] in ("high", "medium")]
    saturated_count = 0
    for t in strong_topics:
        slug = t["slug"]
        in_cooldown = slug in recently_pushed_slugs
        # Check if new snippets exist since last push
        last_push = ""
        for item in pushed:
            if item.get("slug") == slug:
                pa = item.get("pushed_at", "")
                if pa > last_push:
                    last_push = pa
        matches_list = topic_matches.get(slug, {}).get("matches", [])
        has_fresh = any(m.get("added_at", "") > last_push for m in matches_list) if last_push else False
        if in_cooldown or (last_push and not has_fresh):
            saturated_count += 1

    needs_explore = saturated_count >= len(strong_topics) * 0.7 if strong_topics else False

    # Find unmatched snippets for explore candidates
    explore_snippets = []  # type: List[Dict]
    if needs_explore:
        matched_urls = set()  # type: Set[str]
        for slug_key, info in topic_matches.items():
            for m in info.get("matches", []):
                matched_urls.add(m.get("url", ""))
        for f in sorted(SNIPPETS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                d = json.loads(f.read_text())
                url = d.get("url", "")
                content = d.get("content", "") or d.get("snippet", "")
                if url and url not in matched_urls and url not in used_urls and len(content) >= 500:
                    explore_snippets.append({
                        "url": url,
                        "title": d.get("title", "")[:100],
                        "source_name": d.get("source_name", ""),
                        "content_preview": content[:300],
                        "content_len": len(content),
                    })
                    if len(explore_snippets) >= 20:
                        break
            except Exception:
                pass

    plan = {
        "date": today_str,
        "directives_fetched_at": data.get("_fetched_at", datetime.utcnow().isoformat() + "Z"),
        "topics": topics,
        "used_urls": sorted(used_urls),
        "completed_queries": [],
        "completed_topics": [],
        "needs_explore": needs_explore,
        "explore_snippets": explore_snippets,
    }
    return plan


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Daily Plan — produce daily_plan.json")
    parser.add_argument("--dry-run", action="store_true", help="Print plan, don't write")
    args = parser.parse_args()

    today_str = date.today().isoformat()
    print("📋 Daily Plan for %s" % today_str)

    # Phase 1: RSS crawl
    print("\n📡 Phase 1: RSS crawl...")
    try:
        from rss_crawler import run_crawl
        run_crawl(max_time=180)
        print("  ✅ RSS crawl complete")
    except Exception as e:
        print("  ⚠️ RSS crawl failed: %s" % e, file=sys.stderr)

    # Phase 2: Fetch directives from API
    print("\n📋 Phase 2: Building daily plan...")
    print("  Fetching directives from Eir API...")
    try:
        data = fetch_directives()
        n_dirs = len(data.get("directives", [])) + len(data.get("tracked", []))
        print("  ✅ Got %d directives" % n_dirs)
    except Exception as e:
        print("  ❌ API fetch failed: %s" % e, file=sys.stderr)
        if DIRECTIVES_FILE.exists():
            data = json.loads(DIRECTIVES_FILE.read_text())
            print("  ⚠️ Using cached directives.json")
        else:
            print("  ❌ No cached directives either, aborting", file=sys.stderr)
            sys.exit(1)

    # Fetch used URLs — only URLs that were actually *published* to Eir.
    # source_cache is "crawled URLs" (for search dedup), NOT "published URLs".
    # Mixing them blocks the dispatcher from selecting any topics.
    print("  Fetching used URLs...")
    used_urls = fetch_used_urls()  # from API: already-published source URLs
    # Also include locally-pushed source URLs (in case API hasn't synced yet)
    pushed = load_pushed_titles()
    for p in pushed:
        for u in p.get("source_urls", []):
            used_urls.add(u)
    print("  %d published source URLs" % len(used_urls))

    # Build plan
    plan = build_plan(data, used_urls, today_str)

    # Summary
    needs_search = sum(1 for t in plan["topics"] if t["needs_search"])
    needs_gen = sum(1 for t in plan["topics"] if t["needs_generate"])
    rss_cov = sum(1 for t in plan["topics"] if t.get("rss_covered"))
    print("  Topics: %d total, %d need search, %d need generation, %d RSS-covered" % (
        len(plan["topics"]), needs_search, needs_gen, rss_cov))
    for t in plan["topics"]:
        flag_s = "🔍" if t["needs_search"] else "  "
        flag_g = "✍️" if t["needs_generate"] else "  "
        flag_r = "📡" if t.get("rss_covered") else "  "
        print("    %s %s %s %s [%s] pool=%d snippets=%d queries=%d" % (
            flag_s, flag_g, flag_r, t["slug"], t["priority"],
            t["pool_size"], t["good_snippet_count"], len(t["queries"])))

    if plan.get("needs_explore"):
        print("  🔭 Strong topics saturated — %d explore snippets available" % len(plan.get("explore_snippets", [])))
    else:
        print("  📌 Strong topics have fresh material — no explore needed")

    if args.dry_run:
        print("\n[dry-run] Would write to %s" % DAILY_PLAN_FILE)
        return

    # Write
    DAILY_PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    DAILY_PLAN_FILE.write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    print("\n✅ Written to %s" % DAILY_PLAN_FILE)


if __name__ == "__main__":
    main()
