#!/usr/bin/env python3
"""
Content Curator — merges RSS + search candidates, decides which topics are hot today,
and selectively crawls full text only for top-matched articles.

Runs AFTER rss_crawler + search_harvest have indexed title+snippet embeddings.
Runs BEFORE generate_dispatcher picks topics for content generation.

Flow:
  1. Load topic_matches (from RSS + search embedding matches)
  2. For each topic, rank candidates by score + freshness
  3. Decide which topics have enough signal to generate content today
  4. Crawl full text only for top candidates of selected topics
  5. Update snippet files with full content
  6. Output curation_result.json for dispatcher

Usage:
  python3 content_curator.py                      # normal run
  python3 content_curator.py --max-time 300       # time budget
  python3 content_curator.py --dry-run            # show plan without crawling
  python3 content_curator.py --topic <slug>       # curate one topic only
"""

import json
import sys
import hashlib
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from embed import EmbeddingService
from cache_manager import ArticleEmbedCache, SNIPPETS_DIR, DATA_DIR

DAILY_PLAN_FILE = DATA_DIR / "daily_plan.json"
TOPIC_MATCHES_FILE = DATA_DIR / "topic_matches.json"
PUSHED_TITLES_FILE = DATA_DIR / "pushed_titles.json"
CURATION_RESULT_FILE = DATA_DIR / "curation_result.json"

CRAWL4AI_URL = "http://localhost:11235"
CRAWL_TIMEOUT = 25
MAX_SNIPPET_CHARS = 3000

# How many articles to crawl per topic (only top-ranked)
MAX_CRAWL_PER_TOPIC = 5
# Minimum match score to consider an article relevant
MIN_MATCH_SCORE = 0.52
# Minimum number of matched candidates for a topic to be "hot"
MIN_CANDIDATES_FOR_HOT = 2
# Minimum snippet length to count as "has full text"
MIN_FULL_TEXT_LEN = 500


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def crawl_url(url):
    """Crawl a single URL via Crawl4AI. Returns content string or None."""
    try:
        payload = json.dumps({"urls": [url], "priority": 5, "word_count_threshold": 100}).encode()
        req = urllib.request.Request(
            f"{CRAWL4AI_URL}/crawl",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=CRAWL_TIMEOUT + 10) as resp:
            data = json.loads(resp.read())

        if isinstance(data, dict):
            result = data.get("results", data.get("result", data))
            if isinstance(result, list) and result:
                result = result[0]
        elif isinstance(data, list) and data:
            result = data[0]
        else:
            return None

        content = ""
        if isinstance(result, dict):
            md = result.get("markdown", result.get("extracted_content", result.get("text", "")))
            if isinstance(md, dict):
                content = md.get("raw_markdown", md.get("markdown_with_citations", ""))
            elif isinstance(md, list):
                content = "\n".join(str(c) for c in md)
            elif isinstance(md, str):
                content = md

        if not content or len(content) < 100:
            return None
        return content[:MAX_SNIPPET_CHARS]
    except Exception as e:
        print(f"    ⚠️ Crawl failed: {e}")
        return None


def load_snippet(url):
    """Load snippet file for a URL if it exists."""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    path = SNIPPETS_DIR / f"{url_hash}.json"
    if path.exists():
        try:
            return json.loads(path.read_text()), path
        except Exception:
            pass
    return None, path


def save_snippet(path, data):
    """Save snippet data to file."""
    SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get_used_source_urls(pushed_titles):
    """Collect all source URLs from previously pushed content."""
    used = set()
    for p in pushed_titles:
        for u in p.get("source_urls", []):
            used.add(u)
    return used


def score_candidate(match, now):
    """Score a candidate article: combines embedding score + freshness."""
    embed_score = match.get("score", 0)

    # Freshness bonus: articles added recently score higher
    added = match.get("added_at", "")
    freshness_bonus = 0
    if added:
        try:
            added_dt = datetime.fromisoformat(added.replace("Z", "+00:00"))
            hours_ago = (now - added_dt).total_seconds() / 3600.0
            # 0-6h: +0.05, 6-24h: +0.03, 24-72h: +0.01, >72h: 0
            if hours_ago <= 6:
                freshness_bonus = 0.05
            elif hours_ago <= 24:
                freshness_bonus = 0.03
            elif hours_ago <= 72:
                freshness_bonus = 0.01
        except Exception:
            pass

    return embed_score + freshness_bonus


def curate_topics(daily_plan, topic_matches, pushed_titles, used_source_urls):
    """Analyze all topics and decide which are hot today.

    Returns list of curated topics, each with ranked candidates to crawl.
    """
    now = datetime.now(timezone.utc)
    topics = daily_plan.get("topics", [])
    curated = []

    for topic in topics:
        slug = topic["slug"]
        tm = topic_matches.get(slug, {})
        matches = tm.get("matches", [])

        if not matches:
            continue

        # Filter out used source URLs
        available = [m for m in matches if m.get("url") not in used_source_urls]

        if len(available) < MIN_CANDIDATES_FOR_HOT:
            print(f"  ⏭️  {slug}: only {len(available)} available candidates (need {MIN_CANDIDATES_FOR_HOT})")
            continue

        # Score and rank
        scored = []
        for m in available:
            s = score_candidate(m, now)
            scored.append({**m, "combined_score": round(s, 4)})
        scored.sort(key=lambda x: x["combined_score"], reverse=True)

        # Check if we already have full text for top candidates
        has_full_text = 0
        needs_crawl = []
        for m in scored[:MAX_CRAWL_PER_TOPIC]:
            snippet_data, snippet_path = load_snippet(m["url"])
            if snippet_data:
                content = snippet_data.get("content") or snippet_data.get("markdown") or snippet_data.get("snippet") or ""
                if len(content) >= MIN_FULL_TEXT_LEN:
                    has_full_text += 1
                    continue
            needs_crawl.append({"match": m, "snippet_path": snippet_path})

        curated.append({
            "slug": slug,
            "topic_name": topic.get("topic", slug),
            "type": topic.get("type", ""),
            "priority": topic.get("priority", "medium"),
            "total_candidates": len(available),
            "top_score": scored[0]["combined_score"] if scored else 0,
            "has_full_text": has_full_text,
            "needs_crawl": needs_crawl,
            "top_candidates": scored[:MAX_CRAWL_PER_TOPIC],
        })

    # Sort: priority first, then by top_score
    priority_order = {"high": 0, "medium": 1, "low": 2}
    curated.sort(key=lambda x: (priority_order.get(x["priority"], 2), -x["top_score"]))

    return curated


def crawl_for_topics(curated_topics, dry_run=False, max_time=0):
    """Selectively crawl full text for top candidates of curated topics."""
    start = time.time()
    total_crawled = 0
    total_failed = 0
    total_skipped = 0

    for ct in curated_topics:
        slug = ct["slug"]
        needs = ct["needs_crawl"]

        if not needs:
            print(f"  ✅ {slug}: {ct['has_full_text']} articles already have full text")
            total_skipped += len(ct["top_candidates"]) - ct["has_full_text"]
            continue

        print(f"\n  📥 {slug}: crawling {len(needs)} articles (have {ct['has_full_text']} full text)")

        for item in needs:
            if max_time > 0 and (time.time() - start) > max_time - 30:
                print(f"  ⏰ Time budget reached")
                return total_crawled, total_failed

            match = item["match"]
            url = match["url"]
            snippet_path = item["snippet_path"]

            if dry_run:
                print(f"    [dry-run] Would crawl: {match.get('title', url)[:60]}")
                continue

            print(f"    🔗 {match.get('title', '')[:60]}...")
            content = crawl_url(url)

            if not content:
                total_failed += 1
                # Update snippet status
                snippet_data, _ = load_snippet(url)
                if snippet_data:
                    snippet_data["crawl_status"] = "failed"
                    save_snippet(snippet_path, snippet_data)
                continue

            total_crawled += 1

            # Update snippet with full content
            snippet_data, _ = load_snippet(url)
            if not snippet_data:
                snippet_data = {
                    "url": url,
                    "title": match.get("title", ""),
                    "source_name": match.get("source_name", ""),
                    "lang": "en",
                    "fetched_at": datetime.utcnow().isoformat() + "Z",
                }

            snippet_data["content"] = content
            snippet_data["crawl_status"] = "done"
            snippet_data["crawled_at"] = datetime.utcnow().isoformat() + "Z"
            save_snippet(snippet_path, snippet_data)
            print(f"    ✅ {len(content)}c crawled")

    return total_crawled, total_failed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Content Curator — selective full-text crawl")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-time", type=int, default=300)
    parser.add_argument("--topic", type=str, help="Curate one topic only")
    args = parser.parse_args()

    start = time.time()
    print(f"📋 Content Curator starting (max-time={args.max_time}s)")

    # Load data
    daily_plan = load_json(DAILY_PLAN_FILE, {})
    topic_matches = load_json(TOPIC_MATCHES_FILE, {})
    pushed_titles = load_json(PUSHED_TITLES_FILE, [])

    if not daily_plan.get("topics"):
        print("ERROR: No topics in daily_plan.json")
        sys.exit(1)

    used_source_urls = get_used_source_urls(pushed_titles)
    # Also load API-side used URLs
    used_urls_file = DATA_DIR / "used_source_urls.json"
    if used_urls_file.exists():
        try:
            api_urls = json.loads(used_urls_file.read_text())
            if isinstance(api_urls, list):
                used_source_urls.update(api_urls)
        except Exception:
            pass

    print(f"  {len(daily_plan['topics'])} topics, {len(topic_matches)} matched, "
          f"{len(used_source_urls)} used URLs excluded")

    # Curate
    curated = curate_topics(daily_plan, topic_matches, pushed_titles, used_source_urls)

    if args.topic:
        curated = [c for c in curated if c["slug"] == args.topic]

    print(f"\n🔥 {len(curated)} topics have candidates:")
    for ct in curated:
        crawl_count = len(ct["needs_crawl"])
        print(f"  {ct['slug']:35s} candidates={ct['total_candidates']:2d}  "
              f"full_text={ct['has_full_text']}  need_crawl={crawl_count}  "
              f"top_score={ct['top_score']:.3f}")

    # Crawl
    total_crawled, total_failed = crawl_for_topics(
        curated, dry_run=args.dry_run, max_time=args.max_time
    )

    elapsed = time.time() - start

    # Save curation result for dispatcher
    result = {
        "curated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "total_crawled": total_crawled,
        "total_failed": total_failed,
        "topics": [
            {
                "slug": ct["slug"],
                "topic_name": ct["topic_name"],
                "type": ct["type"],
                "priority": ct["priority"],
                "total_candidates": ct["total_candidates"],
                "has_full_text": ct["has_full_text"] + sum(
                    1 for n in ct["needs_crawl"]
                    if load_snippet(n["match"]["url"])[0]
                    and len((load_snippet(n["match"]["url"])[0].get("content") or "")) >= MIN_FULL_TEXT_LEN
                ),
                "top_score": ct["top_score"],
            }
            for ct in curated
        ],
    }

    if not args.dry_run:
        CURATION_RESULT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"\n✅ Curation done in {elapsed:.0f}s — {total_crawled} crawled, {total_failed} failed")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
