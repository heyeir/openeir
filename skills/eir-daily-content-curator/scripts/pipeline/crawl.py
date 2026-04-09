#!/usr/bin/env python3
"""
Phase 3: Selective Crawl - only crawl URLs that are in candidates.json.

Reads candidates.json, crawls full text via Crawl4AI, saves to v9/snippets/.

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
    ensure_dirs, load_json,
)

CRAWL_TIMEOUT = 30
MIN_CONTENT_LEN = 500
MAX_CONTENT_LEN = 8000

# Date extraction patterns for article content
DATE_PATTERNS = [
    # ISO-like: 2026-04-08, 2026/04/08
    r'(20\d{2})[\-/](0[1-9]|1[0-2])[\-/](0[1-9]|[12]\d|3[01])',
    # English: April 8, 2026 / Apr 8, 2026 / 8 April 2026
    r'((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+20\d{2})',
    r'(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2})',
    # Chinese: 2026年4月8日
    r'(20\d{2}\u5e74\d{1,2}\u6708\d{1,2}\u65e5)',
    # Dot format: 2026.04.08
    r'(20\d{2})[.](0[1-9]|1[0-2])[.](0[1-9]|[12]\d|3[01])',
]

# Relative time patterns - "4h", "2 days ago", "3小时前", "1 hour ago"
RELATIVE_TIME_PATTERNS = [
    # English: 4h, 4 hours ago, 2 days ago, 30 minutes ago, 1 min ago, 3 hrs ago
    (r'(\d{1,3})\s*(?:h|hr|hrs|hour|hours)(?:\s+ago)?\b', 'hours'),
    (r'(\d{1,3})\s*(?:d|day|days)(?:\s+ago)?\b', 'days'),
    (r'(\d{1,3})\s*(?:m|min|mins|minute|minutes)(?:\s+ago)?\b', 'minutes'),
    # Chinese: 4小时前, 2天前, 30分钟前
    (r'(\d{1,3})\s*小时前', 'hours'),
    (r'(\d{1,3})\s*天前', 'days'),
    (r'(\d{1,3})\s*分钟前', 'minutes'),
    # "yesterday", "昨天"
    (r'\byesterday\b', 'yesterday'),
    (r'昨天', 'yesterday'),
]


def parse_relative_time(content):
    """Extract publish date from relative time expressions in article text.

    Only looks in the first 800 chars (byline area).
    Returns ISO 8601 string or None.
    """
    head = content[:800]
    now = datetime.now(timezone.utc)

    for pattern, unit in RELATIVE_TIME_PATTERNS:
        m = re.search(pattern, head, re.IGNORECASE)
        if m:
            if unit == 'yesterday':
                dt = now - timedelta(days=1)
                return dt.replace(hour=12, minute=0, second=0).isoformat()
            val = int(m.group(1))
            if val <= 0 or val > 365:
                continue
            if unit == 'hours' and val <= 72:
                return (now - timedelta(hours=val)).isoformat()
            elif unit == 'days' and val <= 30:
                return (now - timedelta(days=val)).isoformat()
            elif unit == 'minutes' and val <= 1440:
                return (now - timedelta(minutes=val)).isoformat()
    return None


# HTML head date patterns - structured data, meta tags, JS variables
HTML_DATE_KEYS = [
    r'datePublished',
    r'article:published_time',
    r'dateCreated',
    r'pageGenTime',
    r'publishDate',
    r'publish_date',
    r'og:updated_time',
    r'dateModified',
]


def fetch_html_head(url, max_bytes=15000):
    """Fetch raw HTML head (first N bytes) to extract structured date info."""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read(max_bytes).decode('utf-8', errors='replace')
    except Exception:
        return ""


def extract_date_from_html_head(html):
    """Extract publish date from raw HTML head - meta tags, JSON-LD, JS vars.

    Handles HTML entity encoding (e.g. MSN's &quot;pageGenTime&quot;:&quot;...&quot;).
    """
    if not html:
        return None

    # Unescape HTML entities first
    import html as html_mod
    decoded = html_mod.unescape(html)

    for key in HTML_DATE_KEYS:
        # JSON-LD / JS object: "datePublished":"2026-04-08T10:00:00Z"
        pattern = r'["\']%s["\']\s*[:=]\s*["\']([^"\']{10,30})["\']' % key
        m = re.search(pattern, decoded, re.IGNORECASE)
        if m:
            try:
                from dateutil import parser as dateparser
                dt = dateparser.parse(m.group(1))
                if dt and 2020 <= dt.year <= 2030:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat()
            except Exception:
                pass

        # Meta tag: <meta property="article:published_time" content="2026-04-08">
        meta_pattern = r'(?:property|name)\s*=\s*["\']%s["\'][^>]*content\s*=\s*["\']([^"\']{10,30})["\']' % key
        m = re.search(meta_pattern, decoded, re.IGNORECASE)
        if m:
            try:
                from dateutil import parser as dateparser
                dt = dateparser.parse(m.group(1))
                if dt and 2020 <= dt.year <= 2030:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat()
            except Exception:
                pass

    return None


def extract_publish_date(content, url="", html_head=""):
    """Extract the most likely publish date from article content, URL, or HTML head.

    Returns ISO 8601 string or None.
    Priority: 1) HTML head structured data, 2) URL path date, 3) article text.
    """
    # Priority 1: HTML head (most reliable - JSON-LD, meta tags, pageGenTime)
    if html_head:
        dt = extract_date_from_html_head(html_head)
        if dt:
            return dt

    candidates = []

    # Priority 2: URL path (e.g. /2026/04/08/ or /20260408/)
    url_match = re.search(r'/(20\d{2})[/-]?(0[1-9]|1[0-2])[/-]?(0[1-9]|[12]\d|3[01])', url)
    if url_match:
        try:
            dt = datetime(int(url_match.group(1)), int(url_match.group(2)), int(url_match.group(3)), tzinfo=timezone.utc)
            candidates.append(dt)
        except ValueError:
            pass

    # Priority 3: Relative time in byline ("4h", "2 days ago", "3小时前")
    rel = parse_relative_time(content)
    if rel:
        return rel  # relative time is very reliable when present

    # Priority 4: Absolute date in article text (first 1500 chars)
    head = content[:1500]
    for pattern in DATE_PATTERNS:
        for m in re.finditer(pattern, head):
            date_str = m.group(0)
            try:
                from dateutil import parser as dateparser
                dt = dateparser.parse(date_str)
                if dt and 2020 <= dt.year <= 2030:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    candidates.append(dt)
            except Exception:
                pass

    if not candidates:
        return None

    # Return the most recent date (most likely the publish date)
    candidates.sort(reverse=True)
    return candidates[0].isoformat()


def crawl_url(url):
    """Crawl a URL via Crawl4AI, return markdown content or None."""
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
            return None

        content = ""
        if isinstance(result, dict):
            md = result.get("markdown", result.get("extracted_content", result.get("text", "")))
            if isinstance(md, dict):
                content = md.get("raw_markdown", md.get("markdown_with_citations", ""))
            elif isinstance(md, str):
                content = md

        return content if content and len(content) >= 200 else None
    except Exception as e:
        print("    ⚠️ Crawl failed for %s: %s" % (url[:60], e))
        return None


def snippet_path_for_url(url):
    """Get snippet file path for a URL."""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    return SNIPPETS_DIR / ("%s.json" % url_hash)


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

    # Crawl
    success = 0
    failed = 0
    start = time.time()

    for item in urls_to_crawl:
        url = item["url"]
        path = item["path"]
        print("  🔗 [%s] %s" % (item["candidate_slug"], url[:70]))

        content = crawl_url(url)
        if content:
            # Clean markdown (basic: remove excessive whitespace)
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
                from markdown_cleaner import clean_markdown
                cleaned = clean_markdown(content)
            except ImportError:
                cleaned = content

            # Fetch HTML head for structured date extraction
            html_head = fetch_html_head(url)

            snippet_data = {
                "url": url,
                "content": cleaned[:MAX_CONTENT_LEN],
                "raw_length": len(content),
                "crawl_status": "ok",
                "crawled_at": datetime.now(timezone.utc).isoformat(),
            }
            # Extract publish date: HTML head > URL path > article text
            pub_date = extract_publish_date(cleaned, url, html_head)
            if pub_date:
                snippet_data["publishedDate"] = pub_date
                print("    📅 Extracted date: %s" % pub_date)
            path.write_text(json.dumps(snippet_data, indent=2, ensure_ascii=False))
            print("    ✅ %dc crawled" % len(cleaned))
            success += 1
        else:
            snippet_data = {
                "url": url,
                "content": "",
                "crawl_status": "failed",
                "crawled_at": datetime.now(timezone.utc).isoformat(),
            }
            path.write_text(json.dumps(snippet_data, indent=2, ensure_ascii=False))
            print("    ❌ Failed")
            failed += 1

        time.sleep(1)  # rate limit

    elapsed = time.time() - start
    print("\n✅ Crawl done in %.0fs - %d success, %d failed" % (elapsed, success, failed))

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

    # Save updated candidates
    candidates["crawled_at"] = datetime.now(timezone.utc).isoformat()
    CANDIDATES_FILE.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))
    print("  Updated candidates.json with crawl status")

    # === Freshness gate: enrich candidates with extracted dates ===
    print("\n📅 Freshness gate - checking source dates...")

    # Load directives for freshness config
    from .config import DIRECTIVES_FILE
    directives_data = load_json(DIRECTIVES_FILE, {})
    all_directives = directives_data.get("directives", []) + directives_data.get("tracked", [])
    directives_map = {d["slug"]: d for d in all_directives}

    # Also load search-result dates from topic_clusters
    clusters = load_json(V9_DIR / "topic_clusters.json", {})
    search_dates = {}  # url -> publishedDate from search results
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

        # Collect dates: search results + crawled snippets
        source_dates = {}  # url -> {date, source}
        for url in c.get("source_urls", []):
            # From news search results
            if url in search_dates:
                source_dates[url] = {"publishedDate": search_dates[url], "date_source": "search"}
            # From crawled snippet (extracted from content)
            path = snippet_path_for_url(url)
            if path.exists():
                snippet = load_json(path)
                pd = snippet.get("publishedDate")
                if pd and url not in source_dates:
                    source_dates[url] = {"publishedDate": pd, "date_source": "crawl_extract"}

        c["source_dates"] = source_dates

        # Check freshness: at least one source within window
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

    # Save final candidates with date info
    CANDIDATES_FILE.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))

    rejected = [c for c in candidate_list if not c.get("has_fresh_source")]
    if rejected:
        print("\n  ⚠️  %d candidates lack fresh sources and will be skipped in generation:" % len(rejected))
        for c in rejected:
            print("    - %s" % c.get("matched_topic_slug", "?"))


if __name__ == "__main__":
    main()
