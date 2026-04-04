#!/usr/bin/env python3
"""
Backfill Snippets — crawls full article content for snippets with crawl_status=pending
or missing/thin content. Designed to run after rss_crawler when Crawl4AI is available.

Usage:
  python3 scripts/backfill_snippets.py                  # backfill all pending
  python3 scripts/backfill_snippets.py --max 30         # limit items
  python3 scripts/backfill_snippets.py --topic-only     # only topic-matched articles
  python3 scripts/backfill_snippets.py --max-time 120   # time budget in seconds
"""

import argparse
import json
import os
import hashlib
import time
import glob
import requests

CRAWL4AI_URL = "http://localhost:11235"
SNIPPETS_DIR = "data/snippets"
TOPIC_MATCHES = "data/topic_matches.json"
TIMEOUT = 30
MIN_CONTENT_LEN = 500


def crawl_url(url):
    try:
        resp = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            json={
                "urls": [url],
                "word_count_threshold": 100,
                "excluded_tags": ["nav", "footer", "header", "aside"],
                "bypass_cache": True,
            },
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if isinstance(data, dict):
            result = data.get("result") or data.get("results")
            if isinstance(result, list):
                result = result[0] if result else data
            elif result is None:
                result = data
        elif isinstance(data, list):
            result = data[0] if data else {}
        else:
            result = {}

        content = (result.get("markdown") or result.get("extracted_content")
                   or result.get("content") or result.get("text") or "")
        if isinstance(content, dict):
            content = content.get("raw_markdown") or content.get("markdown") or str(content)
        title = result.get("title") or result.get("metadata", {}).get("title", "")
        return {"content": content, "title": title}
    except Exception as e:
        return None


def needs_backfill(snippet_data):
    """Check if a snippet needs its content backfilled."""
    # Explicit pending status
    if snippet_data.get("crawl_status") == "pending":
        return True
    # Missing or thin content
    content = snippet_data.get("markdown", "") or snippet_data.get("content", "")
    return len(content) < MIN_CONTENT_LEN


def get_topic_urls():
    """Get all URLs referenced by topic matches."""
    urls = set()
    try:
        tm = json.load(open(TOPIC_MATCHES))
        for tdata in tm.values():
            for m in tdata.get("matches", []):
                url = m.get("url", "")
                if url:
                    urls.add(url)
    except Exception:
        pass
    return urls


def main():
    parser = argparse.ArgumentParser(description="Backfill snippet content")
    parser.add_argument("--max", type=int, default=50, help="Max items to crawl")
    parser.add_argument("--max-time", type=int, default=0, help="Time budget in seconds (0=unlimited)")
    parser.add_argument("--topic-only", action="store_true", help="Only backfill topic-matched articles")
    args = parser.parse_args()

    # Check Crawl4AI health
    try:
        r = requests.get(f"{CRAWL4AI_URL}/health", timeout=5)
        if r.status_code != 200:
            print("❌ Crawl4AI not healthy")
            return
    except Exception:
        print("❌ Crawl4AI not reachable")
        return

    topic_urls = get_topic_urls() if args.topic_only else None

    # Scan snippets for pending items
    todo = []
    for f in glob.glob(f"{SNIPPETS_DIR}/*.json"):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        url = d.get("url", "")
        if not url:
            continue
        if topic_urls is not None and url not in topic_urls:
            continue
        if needs_backfill(d):
            todo.append({"path": f, "url": url, "title": d.get("title", "?")[:60], "data": d})

    # Prioritize topic-matched articles
    topic_urls_all = get_topic_urls()
    todo.sort(key=lambda x: (0 if x["url"] in topic_urls_all else 1, x["path"]))
    todo = todo[:args.max]

    print(f"🔄 Backfill: {len(todo)} snippets need crawling")
    start = time.time()
    success = 0
    fail = 0

    for i, item in enumerate(todo):
        if args.max_time > 0 and time.time() - start > args.max_time - 10:
            print(f"⏰ Time budget reached, stopping ({i} processed)")
            break

        result = crawl_url(item["url"])
        if result and len(result.get("content", "")) >= 200:
            # Update snippet
            d = item["data"]
            d["markdown"] = result["content"]
            d["content"] = result["content"][:8000]
            if result.get("title"):
                d["title"] = result["title"]
            d["crawl_status"] = "ok"
            d["crawled_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with open(item["path"], "w") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            success += 1
        else:
            fail += 1
        time.sleep(1)

    print(f"✅ Backfill done: {success} crawled, {fail} failed ({time.time()-start:.0f}s)")


if __name__ == "__main__":
    main()
