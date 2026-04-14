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
    DIRECTIVES_FILE, DATA_DIR,
    ensure_dirs, load_json,
)
from .date_extractor import extract_publish_date

CRAWL_TIMEOUT = 30          # HTTP client timeout (seconds)
PAGE_TIMEOUT_MS = 20000     # Crawl4AI Playwright navigation timeout (ms)
MIN_CONTENT_LEN = 500
MAX_CONTENT_LEN = 8000

DOMAIN_STATS_FILE = DATA_DIR / "domain_stats.json"

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
            "page_timeout": PAGE_TIMEOUT_MS,
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

        # Remove page template elements (same tags Crawl4AI excludes)
        for tag in ["nav", "header", "footer", "aside", "menu"]:
            text = re.sub(r"<%s[^>]*>.*?</%s>" % (tag, tag), "", raw,
                          flags=re.DOTALL | re.IGNORECASE)
            raw = text  # chain removals

        # Remove script and style
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)

        # Strip remaining HTML tags and collapse whitespace
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


# ─── Content quality ─────────────────────────────────────────────────────────

# Boilerplate phrases that indicate nav/template content rather than article body
_BOILERPLATE_PHRASES = [
    "privacy policy", "terms of use", "cookie settings", "sign up",
    "newsletter", "about us", "contact us", "all rights reserved",
    "submit press release", "press release", "advertisement",
    "subscribe", "log in", "sign in", "follow us",
]


def content_quality_score(text):
    """Return a quality score 0-100. Low score = likely boilerplate.

    Checks:
    - Ratio of boilerplate phrases to total length
    - Average sentence length (very short = nav links)
    - Presence of article-like structure (paragraphs)
    """
    if not text or len(text) < 200:
        return 0

    text_lower = text.lower()
    total_len = len(text_lower)

    # Boilerplate phrase density
    bp_count = sum(1 for phrase in _BOILERPLATE_PHRASES if phrase in text_lower)
    bp_penalty = min(bp_count * 8, 40)  # max 40 points penalty

    # Check first 500 chars — if mostly short fragments, likely nav
    first_chunk = text[:500]
    words = first_chunk.split()
    if len(words) < 20:
        return max(0, 30 - bp_penalty)

    # Avg word count per "sentence" (split by . or newline)
    sentences = [s.strip() for s in re.split(r'[.\n]', text[:2000]) if len(s.strip()) > 10]
    if not sentences:
        return max(0, 30 - bp_penalty)

    avg_sentence_words = sum(len(s.split()) for s in sentences) / len(sentences)
    # Article sentences typically 8-30 words; nav fragments < 5
    if avg_sentence_words < 4:
        return max(0, 25 - bp_penalty)

    score = 70
    if avg_sentence_words >= 8:
        score += 15
    if len(sentences) >= 5:
        score += 15
    score -= bp_penalty

    return max(0, min(100, score))



def snippet_path_for_url(url):
    """Get snippet file path for a URL."""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    return SNIPPETS_DIR / ("%s.json" % url_hash)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    import argparse
    from urllib.parse import urlparse
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

    # Load domain stats
    domain_stats = load_json(DOMAIN_STATS_FILE, {})

    def get_domain(url):
        return urlparse(url).netloc.replace("www.", "")

    def domain_rate(domain):
        d = domain_stats.get(domain, {})
        total = d.get("ok", 0) + d.get("fail", 0)
        if total == 0:
            return 0.5
        return d["ok"] / total

    def update_domain(domain, ok):
        d = domain_stats.setdefault(domain, {"ok": 0, "fail": 0})
        d["ok" if ok else "fail"] += 1

    # Collect URLs per candidate, sorted by domain success rate
    candidate_urls = []
    for c in candidate_list:
        urls = []
        for url in c.get("source_urls", []):
            path = snippet_path_for_url(url)
            if path.exists():
                existing = load_json(path)
                if len(existing.get("content", "")) >= MIN_CONTENT_LEN:
                    continue
            urls.append(url)
        urls.sort(key=lambda u: -domain_rate(get_domain(u)))
        slug = c.get("content_slug", c.get("matched_topic_slug", "?"))
        candidate_urls.append({"slug": slug, "urls": urls})

    total_urls = sum(len(cu["urls"]) for cu in candidate_urls)
    print("  %d candidates, %d URLs to crawl" % (len(candidate_list), total_urls))

    if args.dry_run:
        for cu in candidate_urls:
            print("  [%s] %d URLs" % (cu["slug"], len(cu["urls"])))
            for u in cu["urls"]:
                d = get_domain(u)
                print("    %.0f%% %s — %s" % (domain_rate(d) * 100, d, u[:60]))
        return

    # Crawl each candidate's URLs
    success = 0
    failed = 0
    start = time.time()
    MIN_GOOD_SOURCES = 1

    for cu in candidate_urls:
        slug = cu["slug"]
        good_count = 0

        for url in cu["urls"]:
            domain = get_domain(url)
            rate = domain_rate(domain)
            path = snippet_path_for_url(url)

            # Skip low-rate domains if we already have enough good sources
            if good_count >= MIN_GOOD_SOURCES and rate < 0.3:
                print("  ⏭️  [%s] skip %s (rate %.0f%%, have %d sources)" % (
                    slug, domain, rate * 100, good_count))
                continue

            print("  🔗 [%s] %s" % (slug, url[:70]))

            # Try Crawl4AI
            content, raw_html = crawl_url(url)
            crawl_method = "crawl4ai"

            # Quality check on Crawl4AI result
            if content:
                q_score = content_quality_score(content)
                if q_score < 40:
                    print("    ⚠️ Crawl4AI quality low (%d/100), trying web_fetch..." % q_score)
                    content = None
                else:
                    print("    📊 Quality: %d/100" % q_score)

            if not content:
                if crawl_method == "crawl4ai":
                    print("    ↩️ Crawl4AI failed, trying web_fetch fallback...")
                wf_content, wf_html = web_fetch_fallback(url)
                if wf_content:
                    wf_score = content_quality_score(wf_content)
                    print("    📊 web_fetch quality: %d/100" % wf_score)
                    if wf_score >= 40:
                        content = wf_content
                        raw_html = wf_html or raw_html
                        crawl_method = "web_fetch"
                    else:
                        print("    ⚠️ web_fetch also low quality")
                        if not raw_html:
                            raw_html = wf_html or ""
                if not content:
                    if not raw_html:
                        raw_html = fetch_html_head_only(url) or ""
                    crawl_method = None

            if content:
                q_score = content_quality_score(content)
                snippet_data = {
                    "url": url,
                    "content": content[:MAX_CONTENT_LEN],
                    "raw_length": len(content),
                    "crawl_status": "ok",
                    "crawl_method": crawl_method,
                    "quality_score": q_score,
                    "crawled_at": datetime.now(timezone.utc).isoformat(),
                }
                html_for_date = raw_html or ""
                if not html_for_date:
                    html_for_date = fetch_html_head_only(url)
                pub_date = extract_publish_date(html_for_date, url) if html_for_date else None
                if not pub_date:
                    pub_date = extract_publish_date(content[:3000], url)
                if pub_date:
                    snippet_data["publishedDate"] = pub_date
                    print("    📅 Date: %s" % pub_date)
                path.write_text(json.dumps(snippet_data, indent=2, ensure_ascii=False))
                print("    ✅ %dc via %s" % (len(content), crawl_method))
                success += 1
                good_count += 1
                update_domain(domain, True)
            else:
                snippet_data = {
                    "url": url,
                    "content": "",
                    "crawl_status": "failed",
                    "crawled_at": datetime.now(timezone.utc).isoformat(),
                }
                if raw_html:
                    pub_date = extract_publish_date(raw_html, url)
                    if pub_date:
                        snippet_data["publishedDate"] = pub_date
                        print("    📅 Date (from HTML head): %s" % pub_date)
                path.write_text(json.dumps(snippet_data, indent=2, ensure_ascii=False))
                print("    ❌ No content (date-only save)")
                failed += 1
                update_domain(domain, False)

            time.sleep(1)

    elapsed = time.time() - start
    print("\n✅ Crawl done in %.0fs — %d success, %d failed" % (elapsed, success, failed))

    # Save domain stats
    DOMAIN_STATS_FILE.write_text(json.dumps(domain_stats, indent=2, ensure_ascii=False))
    print("  Domain stats saved (%d domains)" % len(domain_stats))

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

    # Search-result dates from topic files
    topics_dir = V9_DIR / "topics"
    search_dates = {}
    if topics_dir.exists():
        for tf in topics_dir.glob("*.json"):
            if tf.name == "index.json":
                continue
            topic_data = load_json(tf, {})
            for a in topic_data.get("articles", []):
                if a.get("publishedDate"):
                    search_dates[a["url"]] = a["publishedDate"]
    # Also check legacy topic_clusters.json
    clusters = load_json(V9_DIR / "topic_clusters.json", {})
    for slug, cluster in clusters.get("clusters", {}).items():
        for a in cluster.get("articles", []):
            if a.get("publishedDate") and a["url"] not in search_dates:
                search_dates[a["url"]] = a["publishedDate"]

    for c in candidate_list:
        slug = c.get("matched_topic_slug", "")
        directive = directives_map.get(slug, {})
        freshness_str = directive.get("freshness", "7d")
        max_days = FRESHNESS_DAYS.get(freshness_str, 7)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

        source_dates = {}
        for url in c.get("source_urls", []):
            if url in search_dates:
                source_dates[url] = {"publishedDate": search_dates[url], "date_source": "search"}
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
        print("\n  ⚠️  %d candidates lack fresh sources:" % len(rejected))
        for c in rejected:
            print("    - %s" % c.get("matched_topic_slug", "?"))


if __name__ == "__main__":
    main()
