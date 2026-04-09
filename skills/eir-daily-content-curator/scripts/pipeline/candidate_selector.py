#!/usr/bin/env python3
"""
Phase 2: Candidate Selection - cluster similar articles, LLM judges hot topics.

Reads latest_search.json, clusters by embedding similarity, then asks LLM
which clusters are worth generating content for.

Output: data/v9/candidates.json

Usage:
  python3 -m pipeline.candidate_selector
  python3 -m pipeline.candidate_selector --dry-run
"""

import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .config import (
    V9_DIR, CANDIDATES_FILE, DIRECTIVES_FILE, FRESHNESS_DAYS,
    ensure_dirs, load_json,
)


def load_search_results():
    """Load latest search results."""
    path = V9_DIR / "latest_search.json"
    data = load_json(path)
    if not data.get("results"):
        print("❌ No search results found in latest_search.json")
        sys.exit(1)
    return data


def cluster_by_topic(results):
    """Group results by their directive topic_slug.

    Within each topic, further cluster similar articles by title similarity
    (simple word-overlap for now - embedding clustering can be added later).
    """
    by_topic = {}
    for r in results:
        slug = r.get("topic_slug", "unknown")
        by_topic.setdefault(slug, []).append(r)
    return by_topic


def build_llm_prompt(topic_clusters, directives_map):
    """Build a prompt for LLM to judge which topics are hot and worth generating."""
    sections = []
    for slug, articles in topic_clusters.items():
        directive = directives_map.get(slug, {})
        topic_name = directive.get("label") or directive.get("topic", slug)
        topic_type = directive.get("tier") or directive.get("type", "unknown")
        freshness = directive.get("freshness", "7d")

        article_lines = []
        for i, a in enumerate(articles[:8]):  # max 8 per topic
            pub = a.get("publishedDate", "unknown")
            title = a.get("title", "")
            snippet = (a.get("snippet") or "")[:200]
            article_lines.append("  %d. [%s] %s\n     %s" % (i + 1, pub, title, snippet))

        sections.append(
            "## Topic: %s (slug: %s, type: %s, freshness: %s)\n"
            "Articles found: %d\n%s" % (
                topic_name, slug, topic_type, freshness,
                len(articles), "\n".join(article_lines),
            )
        )

    prompt = """You are a content curator for Eir, a knowledge product. Analyze these search results grouped by topic and decide which topics have hot/valuable content worth generating articles about.

Rules:
- A topic is "hot" if it has fresh, newsworthy, or insightful content that users would find valuable
- Each hot topic normally produces 1 article
- A very broad/general topic (like "AI hot news") can produce 2-3 articles if there are clearly distinct sub-stories
- Return suggested_angle for each article to write - be specific about the angle/focus
- matched_topic_slug must be the directive slug that this article belongs to

%s

Return JSON (no markdown fences):
{
  "candidates": [
    {
      "matched_topic_slug": "the-directive-slug",
      "suggested_angle": "specific angle for this article",
      "reason": "why this is worth writing about",
      "source_urls": ["url1", "url2", "url3"],
      "source_titles": ["title1", "title2", "title3"],
      "priority": "high" | "medium" | "low"
    }
  ],
  "skipped_topics": [
    {"slug": "...", "reason": "why skipped"}
  ]
}""" % "\n\n".join(sections)

    return prompt


def has_fresh_source(candidate, directives_map):
    """Check if at least one source has a verifiable publishedDate within freshness window.

    Rule: A candidate MUST have >=1 source URL with a publishedDate
    that falls within the directive's freshness window. If no source has a
    verifiable date, the candidate is rejected.
    """
    slug = candidate.get("matched_topic_slug", "")
    directive = directives_map.get(slug, {})
    freshness_str = directive.get("freshness", "7d")
    max_days = FRESHNESS_DAYS.get(freshness_str, 7)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

    source_urls = candidate.get("source_urls", [])
    # Collect publishedDate from search results stored in topic_clusters
    clusters_path = V9_DIR / "topic_clusters.json"
    clusters = load_json(clusters_path, {})
    cluster = clusters.get("clusters", {}).get(slug, {})
    articles = cluster.get("articles", [])

    # Build url -> publishedDate map from search results
    url_dates = {}
    for a in articles:
        url = a.get("url", "")
        pd = a.get("publishedDate")
        if pd:
            url_dates[url] = pd

    fresh_count = 0
    for url in source_urls:
        pd = url_dates.get(url)
        if not pd:
            continue
        try:
            from dateutil import parser as dateparser
            pub_dt = dateparser.parse(pd)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            if pub_dt >= cutoff:
                fresh_count += 1
        except Exception:
            pass

    return fresh_count > 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Candidate Selection")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    print("📋 Candidate Selection")

    # Load search results
    search_data = load_search_results()
    results = search_data["results"]
    print("  %d search results from run %s" % (len(results), search_data.get("run_id", "?")))

    # Load directives for context
    directives_data = load_json(DIRECTIVES_FILE, {})
    all_directives = directives_data.get("directives", []) + directives_data.get("tracked", [])
    directives_map = {d["slug"]: d for d in all_directives}

    # Cluster by topic
    topic_clusters = cluster_by_topic(results)
    print("  %d topic clusters:" % len(topic_clusters))
    for slug, arts in sorted(topic_clusters.items()):
        print("    %s: %d articles" % (slug, len(arts)))

    # Build LLM prompt
    prompt = build_llm_prompt(topic_clusters, directives_map)

    if args.dry_run:
        print("\n[dry-run] LLM prompt (%d chars):" % len(prompt))
        print(prompt[:2000])
        print("...")
        return

    # Write prompt for agent to process
    prompt_path = V9_DIR / "candidate_prompt.txt"
    prompt_path.write_text(prompt)

    # Also write cluster data for reference
    cluster_path = V9_DIR / "topic_clusters.json"
    cluster_data = {
        "clustered_at": datetime.now(timezone.utc).isoformat(),
        "clusters": {
            slug: {
                "topic_name": directives_map.get(slug, {}).get("topic", slug),
                "article_count": len(arts),
                "articles": [
                    {
                        "url": a["url"],
                        "title": a["title"],
                        "snippet": (a.get("snippet") or "")[:200],
                        "publishedDate": a.get("publishedDate"),
                        "freshness_status": a.get("freshness_status"),
                    }
                    for a in arts[:10]
                ],
            }
            for slug, arts in topic_clusters.items()
        },
    }
    cluster_path.write_text(json.dumps(cluster_data, indent=2, ensure_ascii=False))

    print("\n📝 Prompt written to %s (%d chars)" % (prompt_path.name, len(prompt)))
    print("   Clusters written to %s" % cluster_path.name)
    print("\n⏳ Waiting for LLM to judge candidates...")
    print("   The agent (or generate_and_post) should read candidate_prompt.txt,")
    print("   call LLM, and write candidates.json")
    print("\n   NOTE: After LLM writes candidates.json, apply freshness gate:")
    print("   Each candidate MUST have >=1 source with publishedDate within freshness window.")
    print("   Sources without dates can be supplemented by crawl-phase date extraction.")


if __name__ == "__main__":
    main()
