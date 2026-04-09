#!/usr/bin/env python3
"""
Phase 1: Search - news-first, general-fallback.

For each directive topic:
  1. Search SearXNG news category → filter by publishedDate within freshness
  2. If news < 3 results, supplement with general category
  3. URL dedup, used-source exclusion
  4. Output: data/v9/raw_results/{run_id}.json

Usage:
  python3 -m pipeline.search                    # normal run
  python3 -m pipeline.search --topic ai-health  # single topic
  python3 -m pipeline.search --dry-run
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .config import (
    SEARXNG_URL, DIRECTIVES_FILE, PUSHED_TITLES_FILE, USED_SOURCE_URLS_FILE,
    RAW_RESULTS_DIR, V9_DIR, FRESHNESS_DAYS, NEWS_MIN_RESULTS, MAX_RESULTS_PER_QUERY,
    ensure_dirs, load_json, get_api_url, get_api_key,
)


def fetch_directives_from_api():
    """Fetch fresh directives from Eir API."""
    api_key = get_api_key()
    req = urllib.request.Request(
        "%s/api/oc/curation" % get_api_url(),
        headers={"Authorization": "Bearer %s" % api_key},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    data["_fetched_at"] = datetime.now(timezone.utc).isoformat()
    DIRECTIVES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIRECTIVES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return data


def load_directives():
    """Load directives - fetch from API, fallback to cache."""
    try:
        data = fetch_directives_from_api()
        n = len(data.get("directives", [])) + len(data.get("tracked", []))
        print("  ✅ Fetched %d directives from API" % n)
        return data
    except Exception as e:
        print("  ⚠️ API fetch failed: %s" % e, file=sys.stderr)
        if DIRECTIVES_FILE.exists():
            print("  Using cached directives.json")
            return load_json(DIRECTIVES_FILE)
        raise


def load_used_urls():
    """Load already-published source URLs."""
    urls = set()
    # From API cache
    used = load_json(USED_SOURCE_URLS_FILE, [])
    if isinstance(used, list):
        urls.update(used)
    # From pushed_titles
    pushed = load_json(PUSHED_TITLES_FILE, [])
    for p in pushed:
        for u in p.get("source_urls", []):
            urls.add(u)
    return urls


def _detect_query_language(query):
    """Detect if query is primarily Chinese or English."""
    cjk_count = sum(1 for c in query if '\u4e00' <= c <= '\u9fff')
    return "zh" if cjk_count > len(query) * 0.2 else "en"


def searxng_search(query, category="news", limit=MAX_RESULTS_PER_QUERY):
    """Search SearXNG and return results list."""
    lang = _detect_query_language(query)
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "categories": category,
        "language": lang,
        "pageno": 1,
    })
    url = "%s/search?%s" % (SEARXNG_URL, params)
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])[:limit]
        return [
            {
                "url": r["url"],
                "title": r.get("title", ""),
                "snippet": r.get("content", ""),
                "publishedDate": r.get("publishedDate"),
                "engines": r.get("engines", []),
                "score": r.get("score", 0),
                "category": category,
            }
            for r in results if r.get("url")
        ]
    except Exception as e:
        print("    ⚠️ SearXNG %s search failed: %s" % (category, e), file=sys.stderr)
        return []


def filter_by_freshness(results, freshness_str):
    """Filter results by publishedDate within freshness window."""
    max_days = FRESHNESS_DAYS.get(freshness_str, 7)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    filtered = []
    for r in results:
        pub = r.get("publishedDate")
        if not pub:
            # No date - mark as unknown, keep but deprioritize
            r["freshness_status"] = "unknown"
            filtered.append(r)
            continue
        try:
            from dateutil import parser as dateparser
            pub_dt = dateparser.parse(pub)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            if pub_dt >= cutoff:
                r["freshness_status"] = "fresh"
                filtered.append(r)
            else:
                r["freshness_status"] = "stale"
                # Drop stale results
        except Exception:
            r["freshness_status"] = "unknown"
            filtered.append(r)
    return filtered


def build_queries(directive):
    """Build search queries from a directive."""
    queries = []
    # API returns searchHints as string[] (camelCase)
    hints = directive.get("searchHints") or directive.get("search_hints") or []
    if isinstance(hints, dict):
        suggested = hints.get("suggested_queries") or []
    else:
        suggested = hints  # already a list of query strings
    topic_name = directive.get("label") or directive.get("topic") or directive.get("slug") or ""
    description = directive.get("description") or ""
    keywords = directive.get("keywords") or []
    freshness = directive.get("freshness", "7d")

    # Use suggested queries from API
    for q in suggested:
        queries.append({"q": q, "freshness": freshness})

    # Generate from topic name if insufficient
    if len(queries) < 2 and topic_name:
        has_zh = any('\u4e00' <= c <= '\u9fff' for c in topic_name)
        if has_zh:
            queries.append({"q": "%s 最新" % topic_name, "freshness": freshness})
        else:
            queries.append({"q": "%s latest news" % topic_name, "freshness": freshness})

    # Generate from description keywords
    if len(queries) < 2 and description:
        desc_words = description.split()[:8]
        queries.append({"q": " ".join(desc_words), "freshness": freshness})

    # Generate from keywords
    if len(queries) < 2 and keywords:
        kw = keywords[:4] if isinstance(keywords, list) else []
        if kw:
            queries.append({"q": " ".join(kw), "freshness": freshness})

    return queries


# --- Layered search (2-pass) for broad "news" topics ---

ENTITY_KEYWORDS = [
    "Anthropic", "OpenAI", "Google", "Meta", "Microsoft", "Apple", "Nvidia",
    "Amazon", "Huawei", "ByteDance", "Baidu", "Alibaba", "Tencent", "Zhipu",
    "Mistral", "Cohere", "xAI", "DeepSeek", "Perplexity",
    "Claude", "GPT", "Gemini", "Llama", "Codex", "Copilot", "Cursor",
    "Sora", "Muse", "Grok", "Kimi", "Qwen",
]


def _is_broad_news_topic(directive):
    """Detect if a directive is a broad news-aggregation topic that benefits
    from 2-pass layered search. Heuristic: tier=focus AND freshness <= 1d."""
    tier = directive.get("tier", "")
    freshness = directive.get("freshness", "7d")
    return tier == "focus" and freshness in ("1d", "3d")


def _extract_entities(results):
    """Extract company/product entity names from search result titles."""
    entity_counts = {}
    for r in results:
        title = r.get("title", "")
        for ent in ENTITY_KEYWORDS:
            if ent.lower() in title.lower():
                entity_counts[ent] = entity_counts.get(ent, 0) + 1
    # Return entities sorted by count (most mentioned first)
    return sorted(entity_counts.keys(), key=lambda e: -entity_counts[e])


def _get_user_interest_keywords(all_directives):
    """Derive user interest keywords from directive slugs and labels."""
    interest_kw = set()
    interest_map = {
        "ai-agent": ["agent", "agentic"],
        "ai-companion": ["companion", "emotional AI"],
        "content-creation": ["content", "creator"],
        "design": ["design", "UX"],
        "product": ["product", "feature"],
    }
    for d in all_directives:
        slug = d.get("slug", "")
        for prefix, kws in interest_map.items():
            if prefix in slug:
                interest_kw.update(kws)
    # Always include these core interests
    interest_kw.update(["agent", "product", "launch"])
    return list(interest_kw)


def _build_pass2_queries(entities, interest_keywords, freshness):
    """Generate targeted Pass 2 queries: entity × interest keyword."""
    queries = []
    seen = set()
    for ent in entities[:6]:  # top 6 entities
        # Basic entity news query
        q = "%s AI news" % ent
        if q not in seen:
            queries.append({"q": q, "freshness": freshness})
            seen.add(q)
        # Entity + interest keywords (pick top 2 interests)
        for kw in interest_keywords[:2]:
            q2 = "%s %s" % (ent, kw)
            if q2 not in seen:
                queries.append({"q": q2, "freshness": freshness})
                seen.add(q2)
    return queries


def search_topic_layered(directive, used_urls, all_directives):
    """2-pass layered search for broad news topics.
    Pass 1: Broad discovery query → detect entities (companies/products)
    Pass 2: Entity × user-interests targeted queries
    """
    slug = directive["slug"]
    topic_name = directive.get("label") or directive.get("topic", slug)
    freshness = directive.get("freshness", "7d")

    all_results = []
    seen_urls = set()

    def _add(results, query):
        added = 0
        for r in results:
            if r["url"] not in seen_urls and r["url"] not in used_urls:
                r["topic_slug"] = slug
                r["topic_name"] = topic_name
                r["search_query"] = query
                all_results.append(r)
                seen_urls.add(r["url"])
                added += 1
        return added

    # --- Pass 1: Broad discovery ---
    print("    🔎 [Pass 1] Broad discovery")
    broad_queries = [
        "AI industry news today",
        "AI行业新闻 今日",
    ]
    # Also include original searchHints for coverage
    original_queries = build_queries(directive)
    for qinfo in original_queries:
        if qinfo["q"] not in broad_queries:
            broad_queries.append(qinfo["q"])

    pass1_raw = []  # unfiltered for entity extraction
    pass1_results = []  # filtered for adding
    for q in broad_queries:
        print("    🔍 [P1 news] %s" % q[:60])
        results = searxng_search(q, category="news")
        pass1_raw.extend(results)  # keep raw for entity detection
        results = filter_by_freshness(results, freshness)
        for r in results:
            pass1_results.append(r)
        _add(results, q)
        time.sleep(0.5)

    # Extract entities from UNFILTERED Pass 1 (better entity detection)
    entities = _extract_entities(pass1_raw)
    print("    📡 Detected entities: %s" % ", ".join(entities[:8]))

    # --- Pass 2: Entity × interest targeted search ---
    interest_kw = _get_user_interest_keywords(all_directives)
    pass2_queries = _build_pass2_queries(entities, interest_kw, freshness)
    if pass2_queries:
        print("    🔎 [Pass 2] %d targeted queries (entities × interests)" % len(pass2_queries))
        for qinfo in pass2_queries:
            q = qinfo["q"]
            print("    🔍 [P2 news] %s" % q[:60])
            results = searxng_search(q, category="news")
            results = filter_by_freshness(results, freshness)
            n = _add(results, q)
            if n > 0:
                print("      +%d new" % n)
            time.sleep(0.4)

    # General fallback if still low
    fresh = [r for r in all_results if r.get("freshness_status") == "fresh"]
    if len(fresh) < NEWS_MIN_RESULTS:
        print("    📎 Still low (%d), trying general..." % len(fresh))
        for q in broad_queries[:2]:
            print("    🔍 [general] %s" % q[:60])
            results = searxng_search(q, category="general")
            results = filter_by_freshness(results, freshness)
            _add(results, q)
            time.sleep(0.5)

    # Post-filter
    all_results = _post_filter(all_results)
    print("    ✅ %s: %d results (layered 2-pass)" % (slug, len(all_results)))
    return all_results


def _post_filter(results):
    """Common post-processing: skip junk URLs, short titles, sort."""
    skip_patterns = [".pdf", ".zip", ".mp4", "youtube.com/watch", "twitter.com/", "x.com/"]
    results = [r for r in results if not any(p in r["url"].lower() for p in skip_patterns)]
    results = [r for r in results if len(r.get("title", "")) >= 10]

    def sort_key(r):
        fresh = 0 if r.get("freshness_status") == "fresh" else 1
        return (fresh, -r.get("score", 0))
    results.sort(key=sort_key)
    return results


def search_topic(directive, used_urls):
    """Search for a single topic: news first, general fallback."""
    slug = directive["slug"]
    topic_name = directive.get("label") or directive.get("topic", slug)
    freshness = directive.get("freshness", "7d")
    queries = build_queries(directive)

    if not queries:
        print("  ⏭️  %s: no queries" % slug)
        return []

    all_results = []
    seen_urls = set()

    # Step 1: News search (all queries)
    news_results = []
    for qinfo in queries:
        q = qinfo["q"]
        print("    🔍 [news] %s" % q[:60])
        results = searxng_search(q, category="news")
        results = filter_by_freshness(results, freshness)
        for r in results:
            if r["url"] not in seen_urls and r["url"] not in used_urls:
                r["topic_slug"] = slug
                r["topic_name"] = topic_name
                r["search_query"] = q
                news_results.append(r)
                seen_urls.add(r["url"])
        time.sleep(0.5)  # rate limit

    # Only keep fresh results from news
    fresh_news = [r for r in news_results if r.get("freshness_status") == "fresh"]
    print("    📰 News: %d results (%d fresh)" % (len(news_results), len(fresh_news)))
    all_results.extend(fresh_news)

    # Step 2: General fallback if news < threshold
    if len(fresh_news) < NEWS_MIN_RESULTS:
        print("    📎 News insufficient (%d < %d), trying general..." % (len(fresh_news), NEWS_MIN_RESULTS))
        for qinfo in queries[:2]:  # limit general queries
            q = qinfo["q"]
            print("    🔍 [general] %s" % q[:60])
            results = searxng_search(q, category="general")
            results = filter_by_freshness(results, freshness)
            for r in results:
                if r["url"] not in seen_urls and r["url"] not in used_urls:
                    r["topic_slug"] = slug
                    r["topic_name"] = topic_name
                    r["search_query"] = q
                    all_results.append(r)
                    seen_urls.add(r["url"])
            time.sleep(0.5)

    # Post-filter
    all_results = _post_filter(all_results)
    print("    ✅ %s: %d results after filtering" % (slug, len(all_results)))
    return all_results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Search")
    parser.add_argument("--topic", type=str, help="Only search this topic slug")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    start = time.time()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    print("🔍 Search starting (run=%s)" % run_id)

    # Load directives
    data = load_directives()
    all_directives = data.get("directives", []) + data.get("tracked", [])
    print("  %d directives loaded" % len(all_directives))

    # Filter by topic if specified
    if args.topic:
        all_directives = [d for d in all_directives if d["slug"] == args.topic]
        if not all_directives:
            print("  ❌ Topic '%s' not found" % args.topic)
            sys.exit(1)

    # Load used URLs
    used_urls = load_used_urls()
    print("  %d used source URLs excluded" % len(used_urls))

    # Search each topic
    all_results = []
    for directive in all_directives:
        slug = directive["slug"]
        print("\n📌 %s [%s, freshness=%s]" % (
            directive.get("label") or directive.get("topic", slug),
            directive.get("tier") or directive.get("type", "?"),
            directive.get("freshness", "7d"),
        ))

        if args.dry_run:
            queries = build_queries(directive)
            for q in queries:
                print("    [dry-run] Would search: %s" % q["q"][:60])
            continue

        if _is_broad_news_topic(directive):
            results = search_topic_layered(directive, used_urls, all_directives)
        else:
            results = search_topic(directive, used_urls)
        all_results.extend(results)

    if args.dry_run:
        print("\n[dry-run] Done.")
        return

    # Save raw results
    output = {
        "run_id": run_id,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "topic_count": len(all_directives),
        "total_results": len(all_results),
        "results": all_results,
    }
    output_path = RAW_RESULTS_DIR / ("%s.json" % run_id)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    # Also write latest symlink
    latest_path = V9_DIR / "latest_search.json"
    latest_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    elapsed = time.time() - start
    print("\n✅ Search done in %.0fs - %d results saved to %s" % (
        elapsed, len(all_results), output_path.name))

    # Summary by topic
    by_topic = {}
    for r in all_results:
        s = r.get("topic_slug", "?")
        by_topic[s] = by_topic.get(s, 0) + 1
    for s, n in sorted(by_topic.items()):
        print("  %s: %d results" % (s, n))


if __name__ == "__main__":
    main()
