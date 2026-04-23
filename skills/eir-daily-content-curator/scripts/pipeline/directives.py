#!/usr/bin/env python3
"""
Pure local directive/interests loading for standalone mode.
Extracted from search.py to separate network-free operations.
"""

import json
from pathlib import Path

from .config import CONFIG_DIR, DIRECTIVES_FILE, load_json


def load_local_interests():
    """Load interests from local config/interests.json (standalone mode).
    Converts to directive format for pipeline compatibility."""
    interests_file = CONFIG_DIR / "interests.json"
    if not interests_file.exists():
        return None
    try:
        data = json.loads(interests_file.read_text())
        topics = data.get("topics", [])
        if not topics:
            return None
        directives = []
        for t in topics:
            directives.append({
                "slug": t.get("label", "").lower().replace(" ", "-"),
                "label": t.get("label", ""),
                "topic": t.get("label", ""),
                "description": ", ".join(t.get("keywords", [])),
                "keywords": t.get("keywords", []),
                "freshness": t.get("freshness", "7d"),
                "tier": "focus",
                "searchHints": t.get("search_hints", []),
            })
        return {"directives": directives, "tracked": []}
    except Exception:
        return None


def load_directives():
    """Load directives - local resolution only.

    Resolution order:
      1. Cached directives.json (from previous fetch)
      2. Local interests.json (standalone mode)
    """
    if DIRECTIVES_FILE.exists():
        print("  Using cached directives.json")
        return load_json(DIRECTIVES_FILE)

    # Fallback: local interests (standalone mode)
    local = load_local_interests()
    if local:
        n = len(local.get("directives", []))
        print("  ✅ Loaded %d topics from local interests.json" % n)
        return local

    raise RuntimeError("No directives available. Create config/interests.json or run pipeline.eir_sync fetch")