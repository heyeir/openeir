#!/usr/bin/env python3
"""
Public Picks + Engagement integration for the content pipeline.

Data plumbing only — the LLM agent does all analysis and generation.

Responsibilities:
1. Fetch curation data (publicPicks + engagements) — cached from eir_sync
2. POST pick overlays to /oc/picks
3. Save/load daily engagement insights (written by agent)
4. Provide context data for candidate selection (dedup against pool content)

Usage:
  # In pipeline agent context:
  from pipeline.picks_overlay import (
      get_cached_curation,
      post_overlays,
      save_engagement_insight,
      load_recent_insights,
      save_overlay_result,
      get_overlay_stats,
  )
"""

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .config import DATA_DIR, DIRECTIVES_FILE, ensure_dirs
from .workspace import get_api_url, get_api_key

ENGAGEMENT_DIR = DATA_DIR / "engagement"
PICKS_CACHE_FILE = DATA_DIR / "picks_cache.json"
PICKS_OVERLAY_FILE = DATA_DIR / "picks_overlay_result.json"
REQUEST_INTERVAL = 0.5


def get_cached_curation():
    """Load cached curation data (written by eir_sync.fetch_directives).
    Returns dict with publicPicks, recentEngagements, engagementRate, curationStats."""
    if DIRECTIVES_FILE.exists():
        try:
            data = json.loads(DIRECTIVES_FILE.read_text(encoding="utf-8"))
            return {
                "publicPicks": data.get("publicPicks", []),
                "recentEngagements": data.get("recentEngagements", []),
                "engagementRate": data.get("engagementRate"),
                "curationStats": data.get("curationStats", {}),
                "exclude": data.get("exclude", {}),
            }
        except Exception:
            pass
    return {"publicPicks": [], "recentEngagements": [], "engagementRate": None}


def get_public_picks_context():
    """Return a compact string summarizing existing public picks for candidate selection dedup.
    The agent injects this into its candidate selection context."""
    curation = get_cached_curation()
    picks = curation.get("publicPicks", [])
    if not picks:
        return ""
    lines = ["## Existing Public Pool Content (do NOT duplicate these topics/events)"]
    for p in picks:
        title = p.get("title", "")
        bullets = p.get("bullets", [])
        bullet_str = "; ".join(b[:60] if isinstance(b, str) else b.get("text", "")[:60] for b in bullets[:3])
        lines.append(f"- {title}")
        if bullet_str:
            lines.append(f"  Key facts: {bullet_str}")
    return "\n".join(lines)


def get_engagement_context():
    """Return a compact string summarizing recent engagement for the agent."""
    curation = get_cached_curation()
    engs = curation.get("recentEngagements", [])
    if not engs:
        return ""

    lines = ["## Recent User Engagement (past 24h)"]
    deep = []
    skimmed = []
    for e in engs:
        signals = e.get("signals", [])
        title = e.get("title", "")[:60]
        topics = e.get("topicSlugs", [])
        has_deep = any(s in signals for s in ["article_click", "detail_bottom", "like", "bookmark", "share"])
        if has_deep:
            signal_str = ", ".join(s for s in signals if s != "impression")
            deep.append(f"- {title} [{signal_str}] topics={topics}")
        else:
            skimmed.append(title)

    if deep:
        lines.append("### Deep engagement (clicked/read/liked/bookmarked/shared):")
        lines.extend(deep)
    if skimmed:
        lines.append(f"### Impression only ({len(skimmed)} items skimmed, not engaged):")
        for t in skimmed[:5]:
            lines.append(f"- {t}")
        if len(skimmed) > 5:
            lines.append(f"  ... and {len(skimmed) - 5} more")

    return "\n".join(lines)


def post_overlays(overlays):
    """POST overlays to /oc/picks. Returns API response."""
    if not overlays:
        print("  No overlays to POST")
        return {"upserted": 0, "rejected": 0}

    api_key = get_api_key()
    url = "%s/api/oc/picks" % get_api_url()
    payload = {"picks": overlays}
    body = json.dumps(payload, ensure_ascii=False).encode()

    time.sleep(REQUEST_INTERVAL)
    req = urllib.request.Request(
        url, method="POST", data=body,
        headers={
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        print("✅ POST overlays: %d upserted, %d rejected" % (
            result.get("upserted", 0), result.get("rejected", 0)))
        return result
    except Exception as e:
        body_text = ""
        if hasattr(e, "read"):
            body_text = e.read().decode("utf-8", errors="replace")
        print("❌ POST overlays failed: %s %s" % (e, body_text[:200]), file=sys.stderr)
        return {"error": str(e)}


def save_engagement_insight(insight):
    """Save daily engagement insight (generated by LLM agent).

    Args:
        insight: dict with keys like:
            - date: "2026-05-15"
            - deep_interests: ["ai-coding", "ai-agents"] — topics user deeply engaged
            - skimmed_topics: ["cybersecurity"] — topics user only glanced at
            - known_content: ["Cline SDK开源", "SAP Agent化"] — content user already knows
            - interest_shifts: "用户对 ai-coding 的兴趣明显增强..." — LLM analysis
            - recommendations: "增加 AI agent 架构类内容..." — LLM suggestion
    """
    ensure_dirs()
    ENGAGEMENT_DIR.mkdir(parents=True, exist_ok=True)

    date = insight.get("date", datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d"))
    path = ENGAGEMENT_DIR / f"{date}.json"
    insight["saved_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(insight, indent=2, ensure_ascii=False), encoding="utf-8")
    print("💡 Saved engagement insight for %s" % date)
    return path


def load_recent_insights(days=7):
    """Load engagement insights from the past N days.
    Returns list of insight dicts, newest first."""
    ENGAGEMENT_DIR.mkdir(parents=True, exist_ok=True)
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz).date()
    insights = []

    for i in range(days):
        date = today - timedelta(days=i)
        path = ENGAGEMENT_DIR / f"{date.isoformat()}.json"
        if path.exists():
            try:
                insights.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass

    return insights


def get_recent_insights_context(days=3):
    """Return compact string of recent engagement insights for pipeline context."""
    insights = load_recent_insights(days=days)
    if not insights:
        return ""

    lines = ["## Recent Engagement Insights"]
    for ins in insights:
        date = ins.get("date", "unknown")
        lines.append(f"\n### {date}")
        if ins.get("deep_interests"):
            lines.append(f"  Deep interests: {', '.join(ins['deep_interests'])}")
        if ins.get("known_content"):
            known = ins["known_content"]
            lines.append(f"  Already knows: {', '.join(known[:5])}")
        if ins.get("interest_shifts"):
            lines.append(f"  Shifts: {ins['interest_shifts']}")

    return "\n".join(lines)


def save_overlay_result(overlays, picks_count):
    """Save overlay results to local file for brief reporting."""
    ensure_dirs()
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_picks": picks_count,
        "recommended": sum(1 for o in overlays if o.get("recommend")),
        "not_recommended": sum(1 for o in overlays if not o.get("recommend")),
        "overlays": overlays,
    }
    PICKS_OVERLAY_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def get_overlay_stats():
    """Load overlay stats for daily brief reporting."""
    if PICKS_OVERLAY_FILE.exists():
        try:
            return json.loads(PICKS_OVERLAY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None
