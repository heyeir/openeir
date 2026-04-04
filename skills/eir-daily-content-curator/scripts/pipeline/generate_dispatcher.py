#!/usr/bin/env python3
"""
Generate Dispatcher — selects topics, prepares context, writes task files.
Subagents write content to local files. A separate step (post_content.py) handles API posting.

Usage:
  python3 scripts/generate_dispatcher.py              # normal run
  python3 scripts/generate_dispatcher.py --dry-run    # show what would be generated
  python3 scripts/generate_dispatcher.py --max-topics 3  # limit topics (default 3)
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# scripts/pipeline/generate_dispatcher.py → go 3 levels up to skill root
WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(WORKSPACE, "data")
TASKS_DIR = os.path.join(DATA, "generate_tasks")
GENERATED_DIR = os.path.join(DATA, "generated")
MANIFEST_PATH = os.path.join(DATA, "generate_manifest.json")

MIN_SNIPPET_LEN = 500
MAX_SNIPPETS_PER_TOPIC = 3
# Cooldown: skip slug if pushed within the last N hours
SLUG_COOLDOWN_HOURS = 36
# Consecutive push penalty: how many recent days to check
RECENT_DAYS_PENALTY = 3


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def load_snippets_index():
    """Build url -> snippet data mapping from all snippet files."""
    index = {}
    for sf in glob.glob(os.path.join(DATA, "snippets", "*.json")):
        s = load_json(sf)
        if not s:
            continue
        url = s.get("url", "")
        if url:
            content = s.get("markdown") or s.get("content") or s.get("snippet") or ""
            index[url] = {
                "url": url,
                "title": s.get("title", ""),
                "source_name": s.get("source_name", ""),
                "content": content,
                "content_len": len(content),
                "lang": s.get("lang", "en"),
                "published": s.get("published", ""),
            }
    return index


def get_cooled_slugs(pushed_titles):
    """Return set of slugs pushed within the cooldown window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=SLUG_COOLDOWN_HOURS)
    cutoff_str = cutoff.isoformat()
    slugs = set()
    for p in pushed_titles:
        pushed_at = p.get("pushed_at", "")
        if pushed_at >= cutoff_str:
            slugs.add(p.get("slug", ""))
    return slugs


def count_recent_pushes(pushed_titles, days=RECENT_DAYS_PENALTY):
    """Count pushes per slug in the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.isoformat()
    counts = {}
    for p in pushed_titles:
        pushed_at = p.get("pushed_at", "")
        if pushed_at >= cutoff_str:
            slug = p.get("slug", "")
            counts[slug] = counts.get(slug, 0) + 1
    return counts


def get_last_pushed_at(pushed_titles, slug):
    """Return the most recent pushed_at ISO string for a slug, or ''."""
    latest = ""
    for p in pushed_titles:
        if p.get("slug") == slug:
            pa = p.get("pushed_at", "")
            if pa > latest:
                latest = pa
    return latest


def select_topics(plan, cooled_slugs, topic_matches, snippets_index, max_topics,
                  pushed_titles=None, used_source_urls=None):
    """Select topics eligible for generation.

    Scoring combines:
    - freshness: recent matches score higher
    - relevance: higher embedding scores preferred
    - diversity: penalize slugs pushed recently to avoid repetition
    - general topics (type=focus with broad coverage) can get multiple slots
    """
    candidates = []
    pushed_titles = pushed_titles or []
    used_source_urls = used_source_urls or set()
    recent_push_counts = count_recent_pushes(pushed_titles)

    for topic in plan.get("topics", []):
        slug = topic.get("slug", "")

        # Skip if within cooldown window
        if slug in cooled_slugs:
            continue

        # Get matches for this topic
        tm = topic_matches.get(slug, {})
        matches = tm.get("matches", [])

        # Find good snippets (≥500 chars) from matches, excluding used source URLs
        good_snippets = []
        for m in matches:
            url = m.get("url", "")
            if url in used_source_urls:
                continue
            si = snippets_index.get(url)
            if si and si["content_len"] >= MIN_SNIPPET_LEN:
                good_snippets.append({
                    "url": url,
                    "title": si["title"] or m.get("title", ""),
                    "source_name": si["source_name"] or m.get("source_name", ""),
                    "score": m.get("score", 0),
                    "content": si["content"],
                    "lang": si["lang"],
                    "published": si.get("published", ""),
                    "added_at": m.get("added_at", ""),
                })

        if not good_snippets:
            continue

        # Check freshness: if pushed before, prefer new material.
        last_push = get_last_pushed_at(pushed_titles, slug)
        if last_push:
            fresh_snippets = [s for s in good_snippets if s.get("added_at", "") > last_push]
            if fresh_snippets:
                fresh_urls = {s["url"] for s in fresh_snippets}
                good_snippets = fresh_snippets + [s for s in good_snippets if s["url"] not in fresh_urls]
            else:
                used_urls = set()
                for p in pushed_titles:
                    if p.get("slug") == slug and p.get("source_urls"):
                        used_urls.update(p["source_urls"])
                unused_snippets = [s for s in good_snippets if s["url"] not in used_urls]
                if len(unused_snippets) >= 2:
                    good_snippets = unused_snippets
                elif len(good_snippets) >= 6:
                    pass  # enough variety
                else:
                    continue  # truly exhausted

        # Sort snippets by score desc
        good_snippets.sort(key=lambda x: x["score"], reverse=True)

        # === Composite scoring ===
        priority_order = {"high": 0, "medium": 1, "low": 2}
        pri_score = priority_order.get(topic.get("priority", "low"), 2)

        # Freshness score: average recency of top-3 snippets (hours since added)
        now = datetime.now(timezone.utc)
        freshness_scores = []
        for s in good_snippets[:3]:
            added = s.get("added_at", "")
            if added:
                try:
                    added_dt = datetime.fromisoformat(added.replace("Z", "+00:00"))
                    hours_ago = (now - added_dt).total_seconds() / 3600.0
                    # Fresher = lower score (better). Cap at 168h (1 week)
                    freshness_scores.append(min(hours_ago, 168))
                except Exception:
                    freshness_scores.append(168)
            else:
                freshness_scores.append(168)
        avg_freshness = sum(freshness_scores) / max(len(freshness_scores), 1)

        # Relevance score: average embedding score of top-3
        avg_relevance = sum(s["score"] for s in good_snippets[:3]) / min(len(good_snippets), 3)

        # Consecutive push penalty: each push in recent N days adds penalty
        push_penalty = recent_push_counts.get(slug, 0)  # 0, 1, 2, 3...

        # Composite sort key:
        # 1. needs_generate (0 = yes, 1 = no)
        # 2. push_penalty (lower = less recently pushed = better)
        # 3. priority (0 = high)
        # 4. freshness (lower = more recent = better)
        # 5. negative relevance (higher relevance = better, so negate)
        sort_key = (
            0 if topic.get("needs_generate") else 1,
            push_penalty,
            pri_score,
            avg_freshness,
            -avg_relevance,
        )

        candidates.append({
            "topic": topic,
            "good_snippets": good_snippets[:MAX_SNIPPETS_PER_TOPIC],
            "sort_key": sort_key,
            "_debug": {
                "push_penalty": push_penalty,
                "avg_freshness_h": round(avg_freshness, 1),
                "avg_relevance": round(avg_relevance, 4),
                "snippet_count": len(good_snippets),
            },
        })

    candidates.sort(key=lambda x: x["sort_key"])

    # === Diversity enforcement ===
    # If top-N candidates are all tracked topics, swap one for a different type
    selected = candidates[:max_topics]
    if len(selected) >= 2 and len(candidates) > max_topics:
        selected_types = [c["topic"].get("type", "") for c in selected]
        if all(t in ("track", "attention") for t in selected_types):
            # Find first non-track candidate not already selected
            selected_slugs = {c["topic"]["slug"] for c in selected}
            for c in candidates[max_topics:]:
                if c["topic"].get("type", "") not in ("track", "attention"):
                    if c["topic"]["slug"] not in selected_slugs:
                        # Replace the last (weakest) selected with this diverse one
                        selected[-1] = c
                        break

    return selected


def write_task_file(candidate, dry_run=False):
    """Write a task file containing only source articles and writing rules.
    No API instructions — subagent only produces content JSON."""
    topic = candidate["topic"]
    slug = topic["slug"]
    snippets = candidate["good_snippets"]

    # Determine dot.category from topic type
    type_map = {"focus": "focus", "attention": "attention", "seed": "seed",
                "track": "attention", "explore": "seed"}
    dot_category = type_map.get(topic.get("type", "focus"), "focus")

    # Determine color_hint from keywords/description heuristic
    desc_lower = ((topic.get("description") or "") + " " + " ".join(
        topic.get("keywords") or [] if isinstance(topic.get("keywords"), list)
        else [topic["keywords"]] if isinstance(topic.get("keywords"), str)
        else []
    )).lower()
    if any(w in desc_lower for w in ["health", "medical", "aging", "elderly", "care", "养老", "健康"]):
        color_hint = "cyan"
    elif any(w in desc_lower for w in ["design", "ux", "ui", "体验"]):
        color_hint = "amber"
    elif any(w in desc_lower for w in ["business", "market", "revenue", "automotive", "汽车"]):
        color_hint = "gold"
    else:
        color_hint = "blue"

    task = {
        "slug": slug,
        "topic_name": topic.get("topic", slug),
        "topic_type": topic.get("type", "focus"),
        "description": topic.get("description", ""),
        "dot_category": dot_category,
        "color_hint": color_hint,
        "output_lang": "zh",
        "source_articles": [
            {
                "url": s["url"],
                "title": s["title"],
                "source_name": s["source_name"],
                "lang": s["lang"],
                "published": s.get("published", ""),
                "content": s["content"][:8000],
            }
            for s in snippets
        ],
        "output_path": "data/generated/%s.json" % slug,
    }

    path = os.path.join(TASKS_DIR, slug + ".json")
    if not dry_run:
        os.makedirs(TASKS_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)

    return path


def main():
    parser = argparse.ArgumentParser(description="Generate Dispatcher")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    parser.add_argument("--max-topics", type=int, default=3, help="Max topics to generate")
    args = parser.parse_args()

    # Load data
    plan = load_json(os.path.join(DATA, "daily_plan.json"), {})
    pushed = load_json(os.path.join(DATA, "pushed_titles.json"), [])
    topic_matches = load_json(os.path.join(DATA, "topic_matches.json"), {})

    # Load used source URLs (from API-side dedup)
    used_source_urls_list = load_json(os.path.join(DATA, "used_source_urls.json"), [])
    used_source_urls = set(used_source_urls_list) if isinstance(used_source_urls_list, list) else set()
    # Also add from pushed_titles
    for p in pushed:
        for u in p.get("source_urls", []):
            used_source_urls.add(u)
    print("  %d used source URLs excluded" % len(used_source_urls), file=sys.stderr)

    if not plan.get("topics"):
        print("ERROR: No topics in daily_plan.json", file=sys.stderr)
        sys.exit(1)

    # Build snippet index
    print("Loading snippets...", file=sys.stderr)
    snippets_index = load_snippets_index()
    print("  %d snippets indexed" % len(snippets_index), file=sys.stderr)

    # Filter
    cooled_slugs = get_cooled_slugs(pushed)
    print("  %d slugs in cooldown" % len(cooled_slugs), file=sys.stderr)

    # Select from focus topics
    selected = select_topics(plan, cooled_slugs, topic_matches, snippets_index, args.max_topics,
                             pushed_titles=pushed, used_source_urls=used_source_urls)
    print("  %d topics selected for generation" % len(selected), file=sys.stderr)
    for c in selected:
        debug = c.get("_debug", {})
        print("    → %s [push_penalty=%d, freshness=%.0fh, relevance=%.3f, snippets=%d]" % (
            c["topic"]["slug"], debug.get("push_penalty", 0),
            debug.get("avg_freshness_h", 0), debug.get("avg_relevance", 0),
            debug.get("snippet_count", 0)), file=sys.stderr)

    # If quota not filled, try explore topics from unmatched snippets
    remaining_slots = args.max_topics - len(selected)
    if remaining_slots > 0 and plan.get("needs_explore") and plan.get("explore_snippets"):
        explore_snippets = plan["explore_snippets"]
        print("  🔭 %d explore snippets available, filling %d slots" % (
            len(explore_snippets), remaining_slots), file=sys.stderr)

        # Group explore snippets into ad-hoc topics (by source similarity)
        # Each explore candidate = 1-3 snippets from the same cluster
        explore_used = 0
        for es in explore_snippets:
            if explore_used >= remaining_slots:
                break
            url = es.get("url", "")
            si = snippets_index.get(url)
            if not si or si["content_len"] < MIN_SNIPPET_LEN:
                continue

            # Check cooldown on pseudo-slug
            explore_slug = "explore-" + url.split("/")[-1][:30].replace(".", "-").lower()
            if explore_slug in cooled_slugs:
                continue

            selected.append({
                "topic": {
                    "slug": explore_slug,
                    "topic": es.get("title", "Explore")[:60],
                    "description": "Auto-discovered content outside tracked interests",
                    "type": "explore",
                    "priority": "low",
                },
                "good_snippets": [{
                    "url": url,
                    "title": si["title"] or es.get("title", ""),
                    "source_name": si["source_name"],
                    "score": es.get("best_score", 0),
                    "content": si["content"],
                    "lang": si["lang"],
                    "added_at": es.get("added_at", ""),
                }],
                "sort_key": (2, 2, 1),  # lowest priority
            })
            explore_used += 1

        print("  %d explore topics added" % explore_used, file=sys.stderr)

    if not selected:
        print("No topics eligible for generation.", file=sys.stderr)
        manifest = {"tasks": [], "generated_at": datetime.now(timezone.utc).isoformat()}
        if not args.dry_run:
            os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
            with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Ensure generated dir exists
    if not args.dry_run:
        os.makedirs(GENERATED_DIR, exist_ok=True)

    # Write task files
    tasks = []
    for candidate in selected:
        topic = candidate["topic"]
        slug = topic["slug"]
        path = write_task_file(candidate, dry_run=args.dry_run)
        rel_path = os.path.relpath(path, WORKSPACE)

        snippet_titles = [s["title"][:40] for s in candidate["good_snippets"]]
        tasks.append({
            "slug": slug,
            "task_file": rel_path,
            "output_file": "data/generated/%s.json" % slug,
            "topic_name": topic.get("topic", slug),
            "type": topic.get("type", "focus"),
            "priority": topic.get("priority", "medium"),
            "snippet_count": len(candidate["good_snippets"]),
            "top_sources": snippet_titles,
        })

        action = "WOULD CREATE" if args.dry_run else "CREATED"
        print("  %s: %s (%d snippets)" % (action, rel_path, len(candidate["good_snippets"])),
              file=sys.stderr)

    # Write manifest
    manifest = {
        "tasks": tasks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not args.dry_run:
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
