#!/usr/bin/env python3
"""
Phase 2.5: Resolve Sources — fill source_urls in candidates.json from topic files.

After the agent writes candidates.json with source_refs (article indices),
this script resolves them to actual URLs from the topic files.

If source_urls already exist and are valid, they are preserved.
If source_refs are provided, they are resolved to URLs.
If neither exists, ALL articles from the matched topic are used as sources.

Usage:
  python3 -m pipeline.resolve_sources
"""

import json
import sys
from pathlib import Path

from .config import CANDIDATES_FILE, V9_DIR, load_json, ensure_dirs


TOPICS_DIR = V9_DIR / "topics"


def resolve():
    """Resolve source_refs to source_urls in candidates.json."""
    ensure_dirs()

    if not CANDIDATES_FILE.exists():
        print("❌ No candidates.json found")
        sys.exit(1)

    data = load_json(CANDIDATES_FILE)
    candidates = data.get("candidates", [])
    if not candidates:
        print("❌ No candidates in candidates.json")
        sys.exit(1)

    print("🔗 Resolve Sources")
    resolved_count = 0

    for c in candidates:
        topic_slug = c.get("matched_topic_slug", "")
        content_slug = c.get("content_slug", "?")

        # Skip if source_urls already populated with real URLs
        existing_urls = c.get("source_urls", [])
        if existing_urls and all(u.startswith("http") for u in existing_urls):
            print("  ✓ %s: %d source_urls already set" % (content_slug, len(existing_urls)))
            continue

        # Load topic file
        topic_path = TOPICS_DIR / ("%s.json" % topic_slug)
        if not topic_path.exists():
            print("  ⚠️ %s: topic file not found (%s)" % (content_slug, topic_slug))
            continue

        topic_data = load_json(topic_path)
        articles = topic_data.get("articles", [])
        if not articles:
            print("  ⚠️ %s: no articles in topic file" % content_slug)
            continue

        # Resolve source_refs (1-based indices) if provided
        source_refs = c.get("source_refs", [])
        if source_refs:
            urls = []
            titles = {}
            for idx in source_refs:
                # Support both 0-based and 1-based (treat as 1-based if max > len)
                i = idx - 1 if idx >= 1 else idx
                if 0 <= i < len(articles):
                    a = articles[i]
                    urls.append(a["url"])
                    titles[a["url"]] = a.get("title", "")
            c["source_urls"] = urls
            c["source_titles"] = titles
            print("  ✅ %s: resolved %d source_refs → %d URLs" % (
                content_slug, len(source_refs), len(urls)))
        else:
            # No source_refs: use all articles from topic (up to 5, prefer those with dates)
            dated = [a for a in articles if a.get("publishedDate")]
            undated = [a for a in articles if not a.get("publishedDate")]
            selected = (dated + undated)[:5]

            urls = [a["url"] for a in selected]
            titles = {a["url"]: a.get("title", "") for a in selected}
            c["source_urls"] = urls
            c["source_titles"] = titles
            print("  ✅ %s: auto-filled %d URLs from topic '%s'" % (
                content_slug, len(urls), topic_slug))

        resolved_count += 1

    # Write back
    CANDIDATES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print("\n🔗 Resolved sources for %d/%d candidates" % (resolved_count, len(candidates)))


def main():
    resolve()


if __name__ == "__main__":
    main()
