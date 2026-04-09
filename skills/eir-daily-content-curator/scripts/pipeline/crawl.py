#!/usr/bin/env python3
"""
Phase 3: Selective Crawl — only crawl URLs that are in candidates.json.

Reads candidates.json, crawls full text via Crawl4AI (with web_fetch fallback),
extracts publish dates, saves to snippets/.

Usage:
  python3 -m pipeline.crawl
  python3 -m pipeline.crawl --dry-run
"""

import hashlib
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .config import (
    CANDIDATES_FILE, SNIPPETS_DIR, CRAWL4AI_URL, V9_DIR, FRESHNESS_DAYS,
    DIRECTIVES_FILE,
    ensure_dirs, load_json,
)
from .date_extractor import extract_publish_date

CRAWL_TIMEOUT = 30
MIN_CONTENT_LEN = 500
MAX_CONTENT_LEN = 8000

# ─── Crawling ────────────────────────────────────────────────────────────────


def crawl_url(url):
    """Crawl a URL via Crawl4AI, return (markdown, raw_html) or (None, None).

    raw_html is the first ~20KB of the page, used for date extraction.
    """
    try:
        payload = json.dumps({
            "urls": [url],
            "word_count_threshold": 100,
            "excluded_tags": ["nav", "footer", "header", "aside"],
            "bypass_cache": True,
        }).encode()
        req = urllib.request.Request(
            "%s/crawl" % CRAWL4AI_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=CRAWL_TIMEOUT + 10) as resp:
            data = json.loads(resp.read())

        # Parse response (Crawl4AI has varying response formats)
        if isinstance(data, dict):
            result = data.get("results", data.get("result", data))
            if isinstance(result, list) and result:
                result = result[0]
        elif isinstance(data, list) and data:
            result = data[0]
        else:
            return None, None

        content = ""
        raw_html = ""
        if isinstance(result, dict):
            # Extract markdown
            md = result.get("markdown", result.get("extracted_content", result.get("text", "")))
            if isinstance(md, dict):
                content = md.get("raw_markdown", md.get("markdown_with_citations", ""))
            elif isinstance(md, str):
                content = md
            # Extract raw HTML if available (for date extraction)
            raw_html = result.get("html", result.get("raw_html", ""))
            if isinstance(raw_html, str):
                raw_html = raw_html[:20000]  # limit for date extraction
            else:
                raw_html = ""

        if content and len(content) >= 200:
            return content, raw_html
        return None, raw_html
    except Exception as e:
        print("    ⚠️ Crawl4AI failed: %s" % e)
        return None, None


def web_fetch_fallback(url):
    """Fallback: fetch page via direct HTTP request, return (text, html_head).

    Uses a simple urllib request with browser-like headers.
    Returns stripped text (not markdown) and raw HTML head for date extraction.
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read(200000).decode("utf-8", errors="replace")

        html_head = raw[:20000]

        # Basic HTML to text: strip tags, collapse whitespace
        text = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) >= 300:
            return text[:MAX_CONTENT_LEN], html_head
        return None, html_head
    except Exception as e:
        print("    ⚠️ web_fetch fallback failed: %s" % e)
        return None, None


def fetch_html_head_only(url):
    """Fetch just the HTML head (first 20KB) for date extraction.

    Lightweight — only used when we already have markdown content but no date.
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read(20000).decode("utf-8", errors="replace")
    except Exception:
        return ""


# ─── Snippet storage ─────────────────────────────────────────────────────────


def snippet_path_for_url(url):
    """Get snippet file path for a URL."""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    return SNIPPETS_DIR / ("%s.json" % url_hash)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Selective Crawl")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    print("📥 Selective Crawl")

    candidates = load_json(CANDIDATES_FILE, {})
    candidate_list = candidates.get("candidates", [])
    if not candidate_list:
        print("  ❌ No candidates in candidates.json")
        sys.exit(1)

    # Collect all URLs to crawl
    urls_to_crawl = []
    for c in candidate_list:
        for url in c.get("source_urls", []):
            path = snippet_path_for_url(url)
            if path.exists():
                existing = load_json(path)
                content = existing.get("content", "")
                if len(content) >= MIN_CONTENT_LEN:
                    continue  # already have good content
            urls_to_crawl.append({
                "url": url,
                "candidate_slug": c.get("matched_topic_slug", "?"),
                "path": path,
            })

    print("  %d candidates, %d URLs to crawl" % (len(candidate_list), len(urls_to_crawl)))

    if args.dry_run:
        for item in urls_to_crawl:
            print("  [dry-run] Would crawl: %s" % item["url"][:80])
        return

    # Crawl each URL
    success = 0
    failed = 0
    start = time.time()

    for item in urls_to_crawl:
        url = item["url"]
        path = item["path"]
        print("  🔗 [%s] %s" % (item["candidate_slug"], url[:70]))

        # Try Crawl4AI
        content, raw_html = crawl_url(url)
        crawl_method = "crawl4ai"

        if not content:
            # web_fetch only for date extraction, not content fallback
            print("    ↩️ Crawl4AI failed, fetching HTML head for date only...")
            raw_html = fetch_html_head_only(url) or ""
            crawl_method = None  # no content obtained

        if content:
            snippet_data = {
                "url": url,
                "content": content[:MAX_CONTENT_LEN],
                "raw_length": len(content),
                "crawl_status": "ok",
                "crawl_method": crawl_method,
                "crawled_at": datetime.now(timezone.utc).isoformat(),
            }

            # Extract publish date using multi-strategy extractor
            # Priority: raw HTML (structured data) > URL path > article text
            html_for_date = raw_html or ""
            if not html_for_date:
                # If Crawl4AI didn't return raw HTML, try fetching head separately
                html_for_date = fetch_html_head_only(url)

            pub_date = extract_publish_date(html_for_date, url) if html_for_date else None
            if not pub_date:
                # Fallback: extract from article text (less reliable)
                pub_date = extract_publish_date(content[:3000], url)

            if pub_date:
                snippet_data["publishedDate"] = pub_date
                print("    📅 Date: %s" % pub_date)

            path.write_text(json.dumps(snippet_data, indent=2, ensure_ascii=False))
            print("    ✅ %dc via %s" % (len(content), crawl_method))
            success += 1
        else:
            snippet_data = {
                "url": url,
                "content": "",
                "crawl_status": "failed",
                "crawled_at": datetime.now(timezone.utc).isoformat(),
            }
            # Still try to extract date from HTML head
            if raw_html:
                pub_date = extract_publish_date(raw_html, url)
                if pub_date:
                    snippet_data["publishedDate"] = pub_date
                    print("    📅 Date (from HTML head): %s" % pub_date)
            path.write_text(json.dumps(snippet_data, indent=2, ensure_ascii=False))
            print("    ❌ No content (date-only save)")
            failed += 1

        time.sleep(1)  # rate limit

    elapsed = time.time() - start
    print("\n✅ Crawl done in %.0fs — %d success, %d failed" % (elapsed, success, failed))

    # Update candidates with crawl status
    for c in candidate_list:
        crawled_sources = []
        for url in c.get("source_urls", []):
            path = snippet_path_for_url(url)
            if path.exists():
                snippet = load_json(path)
                if snippet.get("crawl_status") == "ok" and len(snippet.get("content", "")) >= MIN_CONTENT_LEN:
                    crawled_sources.append(url)
        c["crawled_sources"] = crawled_sources
        c["has_content"] = len(crawled_sources) > 0

    candidates["crawled_at"] = datetime.now(timezone.utc).isoformat()
    CANDIDATES_FILE.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))
    print("  Updated candidates.json with crawl status")

    # === Freshness gate ===
    print("\n📅 Freshness gate — checking source dates...")

    directives_data = load_json(DIRECTIVES_FILE, {})
    all_directives = directives_data.get("directives", []) + directives_data.get("tracked", [])
    directives_map = {d["slug"]: d for d in all_directives}

    # Search-result dates from topic_clusters
    clusters = load_json(V9_DIR / "topic_clusters.json", {})
    search_dates = {}
    for slug, cluster in clusters.get("clusters", {}).items():
        for a in cluster.get("articles", []):
            if a.get("publishedDate"):
                search_dates[a["url"]] = a["publishedDate"]

    for c in candidate_list:
        slug = c.get("matched_topic_slug", "")
        directive = directives_map.get(slug, {})
        freshness_str = directive.get("freshness", "7d")
        max_days = FRESHNESS_DAYS.get(freshness_str, 7)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

        source_dates = {}
        for url in c.get("source_urls", []):
            # From search results
            if url in search_dates:
                source_dates[url] = {"publishedDate": search_dates[url], "date_source": "search"}
            # From crawled snippet
            path = snippet_path_for_url(url)
            if path.exists():
                snippet = load_json(path)
                pd = snippet.get("publishedDate")
                if pd and url not in source_dates:
                    source_dates[url] = {"publishedDate": pd, "date_source": "crawl_extract"}

        c["source_dates"] = source_dates

        has_fresh = False
        for url, info in source_dates.items():
            try:
                from dateutil import parser as dateparser
                pub_dt = dateparser.parse(info["publishedDate"])
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt >= cutoff:
                    has_fresh = True
                    break
            except Exception:
                pass

        c["has_fresh_source"] = has_fresh
        dated_count = len(source_dates)
        total_sources = len(c.get("source_urls", []))
        status = "✅" if has_fresh else "❌"
        print("  %s %s: %d/%d sources dated, fresh=%s (window=%dd)" % (
            status, slug, dated_count, total_sources, has_fresh, max_days))

    CANDIDATES_FILE.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))

    rejected = [c for c in candidate_list if not c.get("has_fresh_source")]
    if rejected:
        print("\n  ⚠️  %d candidates lack fresh sources and will be skipped in generation:" % len(rejected))
        for c in rejected:
            print("    - %s" % c.get("matched_topic_slug", "?"))


if __name__ == "__main__":
    main()
