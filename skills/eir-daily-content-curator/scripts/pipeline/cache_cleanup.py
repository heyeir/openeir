#!/usr/bin/env python3
"""
Cache Cleanup — Remove dead content from embed cache, snippets, and topic matches.

Dead content = articles that don't match any user topic and will never be used.

Usage:
  python3 scripts/cache_cleanup.py --stats      # Show waste stats only
  python3 scripts/cache_cleanup.py --dry-run    # Show what would be cleaned
  python3 scripts/cache_cleanup.py              # Actually clean
"""

import argparse
import glob
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
DATA = WORKSPACE / "data"
EMBED_META = DATA / "embed_meta.json"
EMBED_CACHE = DATA / "embed_cache.npz"
SNIPPETS_DIR = DATA / "snippets"
TOPIC_MATCHES = DATA / "topic_matches.json"
PUSHED_TITLES = DATA / "pushed_titles.json"
SOURCE_CACHE = DATA / "source_cache.json"

# TTL settings
TTL_UNMATCHED_HOURS = 48    # Unmatched articles: 2 days (give topic_matches time to update)
TTL_MATCHED_DAYS = 7        # Matched but unused articles: 7 days
TTL_PUSHED_DAYS = 30        # Published source URLs: keep 30 days for dedup


def load_json(path, default=None):
    if path.exists():
        return json.loads(path.read_text())
    return default or {}


def compute_stats():
    """Compute cache health stats."""
    meta = load_json(EMBED_META, {"articles": []})
    articles = meta.get("articles", [])
    tm = load_json(TOPIC_MATCHES)
    pt = load_json(PUSHED_TITLES)

    now = datetime.now(timezone.utc)

    # Matched URLs
    matched_urls = set()
    for slug, tdata in tm.items():
        for m in tdata.get("matches", []):
            matched_urls.add(m.get("url", ""))

    # Pushed URLs
    pushed_urls = set()
    entries = pt.values() if isinstance(pt, dict) else pt
    for e in entries:
        for u in e.get("source_urls", []):
            pushed_urls.add(u)

    # Categorize articles
    stats = {
        "total": len(articles),
        "matched": 0,
        "pushed": 0,
        "unmatched_fresh": 0,
        "unmatched_stale": 0,
        "by_source": {},
    }

    removable_indices = []
    removable_urls = set()

    for i, a in enumerate(articles):
        url = a.get("url", "")
        src = a.get("source_name", "?")
        added = a.get("added_at", "")

        if src not in stats["by_source"]:
            stats["by_source"][src] = {"total": 0, "matched": 0, "removable": 0}
        stats["by_source"][src]["total"] += 1

        if url in pushed_urls:
            stats["pushed"] += 1
            continue

        if url in matched_urls:
            stats["matched"] += 1
            stats["by_source"][src]["matched"] += 1
            continue

        # Unmatched — check age
        if added:
            try:
                dt = datetime.fromisoformat(added.replace("Z", "+00:00"))
                age_hours = (now - dt).total_seconds() / 3600
                if age_hours > TTL_UNMATCHED_HOURS:
                    stats["unmatched_stale"] += 1
                    removable_indices.append(i)
                    removable_urls.add(url)
                    stats["by_source"][src]["removable"] += 1
                else:
                    stats["unmatched_fresh"] += 1
            except:
                stats["unmatched_stale"] += 1
                removable_indices.append(i)
                removable_urls.add(url)
                stats["by_source"][src]["removable"] += 1
        else:
            stats["unmatched_stale"] += 1
            removable_indices.append(i)
            removable_urls.add(url)
            stats["by_source"][src]["removable"] += 1

    # Orphan snippets
    article_urls = set(a.get("url", "") for a in articles)
    snippet_files = glob.glob(str(SNIPPETS_DIR / "*.json"))
    orphan_snippets = []
    unmatched_snippets = []

    for f in snippet_files:
        try:
            s = json.loads(Path(f).read_text())
            url = s.get("url", "")
            if url and url not in article_urls:
                orphan_snippets.append(f)
            elif url in removable_urls:
                unmatched_snippets.append(f)
        except:
            orphan_snippets.append(f)

    stats["orphan_snippets"] = len(orphan_snippets)
    stats["unmatched_snippets"] = len(unmatched_snippets)
    stats["removable_articles"] = len(removable_indices)
    stats["removable_snippet_files"] = orphan_snippets + unmatched_snippets
    stats["removable_indices"] = removable_indices
    stats["removable_urls"] = removable_urls

    return stats


def print_stats(stats):
    """Print cache health report."""
    total = stats["total"]
    print(f"📊 CACHE HEALTH")
    print(f"  Total articles: {total}")
    print(f"  Published (keep): {stats['pushed']}")
    print(f"  Matched to topic (keep): {stats['matched']}")
    print(f"  Unmatched fresh <{TTL_UNMATCHED_HOURS}h (keep): {stats['unmatched_fresh']}")
    print(f"  Unmatched stale >{TTL_UNMATCHED_HOURS}h (removable): {stats['unmatched_stale']}")
    print(f"  Orphan snippets: {stats['orphan_snippets']}")
    print(f"  Unmatched snippets: {stats['unmatched_snippets']}")

    kept = stats["pushed"] + stats["matched"] + stats["unmatched_fresh"]
    print(f"\n  After cleanup: {kept} articles (was {total})")
    print(f"  Removable: {stats['removable_articles']} articles + {len(stats['removable_snippet_files'])} snippets")

    # Top waste sources
    by_src = sorted(stats["by_source"].items(), key=lambda x: -x[1]["removable"])
    print(f"\n🗑️ Top waste sources:")
    for src, s in by_src[:10]:
        if s["removable"] > 0:
            print(f"  {src:25s} {s['removable']:3d}/{s['total']:3d} removable")


def run_cleanup(dry_run=False):
    """Remove dead content."""
    stats = compute_stats()
    print_stats(stats)

    if stats["removable_articles"] == 0 and len(stats["removable_snippet_files"]) == 0:
        print("\n✅ Cache is clean, nothing to do.")
        return

    if dry_run:
        print(f"\n🔍 DRY RUN — would remove {stats['removable_articles']} articles + {len(stats['removable_snippet_files'])} snippets")
        return

    print(f"\n🧹 Cleaning...")

    # 1. Remove articles from embed_meta + embed_cache
    import numpy as np
    meta = load_json(EMBED_META, {"articles": []})
    articles = meta.get("articles", [])

    remove_set = set(stats["removable_indices"])
    keep_indices = [i for i in range(len(articles)) if i not in remove_set]

    # Filter articles
    new_articles = [articles[i] for i in keep_indices]

    # Filter embeddings
    if EMBED_CACHE.exists():
        data = np.load(EMBED_CACHE)
        embs = data["embeddings"]
        if len(embs) == len(articles):
            new_embs = embs[keep_indices]
            np.savez_compressed(EMBED_CACHE, embeddings=new_embs)
            print(f"  Embeddings: {len(embs)} → {len(new_embs)}")
        else:
            print(f"  ⚠️ Embedding count mismatch ({len(embs)} vs {len(articles)}), skipping npz cleanup")

    meta["articles"] = new_articles
    EMBED_META.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"  Articles: {len(articles)} → {len(new_articles)}")

    # 2. Remove snippets
    removed_snippets = 0
    for f in stats["removable_snippet_files"]:
        try:
            os.remove(f)
            removed_snippets += 1
        except:
            pass
    print(f"  Snippets removed: {removed_snippets}")

    # 3. Clean source_cache (remove URLs of deleted articles)
    if SOURCE_CACHE.exists():
        sc = load_json(SOURCE_CACHE)
        kept_urls = set(a.get("url", "") for a in new_articles)
        if isinstance(sc, dict):
            new_sc = {url: v for url, v in sc.items() if url in kept_urls or url in stats.get("pushed_urls", set())}
            SOURCE_CACHE.write_text(json.dumps(new_sc, ensure_ascii=False))
            print(f"  Source cache: {len(sc)} → {len(new_sc)}")

    # 4. Clean topic_matches (remove entries pointing to deleted articles)
    tm = load_json(TOPIC_MATCHES)
    removed_matches = 0
    kept_urls = set(a.get("url", "") for a in new_articles)
    for slug in tm:
        old_matches = tm[slug].get("matches", [])
        new_matches = [m for m in old_matches if m.get("url", "") in kept_urls]
        removed_matches += len(old_matches) - len(new_matches)
        tm[slug]["matches"] = new_matches
    TOPIC_MATCHES.write_text(json.dumps(tm, indent=2, ensure_ascii=False))
    print(f"  Topic match entries pruned: {removed_matches}")

    print(f"\n✅ Cleanup done. Cache: {len(new_articles)} articles")


def main():
    parser = argparse.ArgumentParser(description="Cache Cleanup")
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be cleaned")
    args = parser.parse_args()

    if args.stats:
        stats = compute_stats()
        print_stats(stats)
    else:
        run_cleanup(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
