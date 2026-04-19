"""
Pipeline shared config — resolves workspace, API credentials, service URLs.
"""

import json
import os
import sys
from pathlib import Path

from .eir_config import (
    WORKSPACE, CONFIG_DIR, DATA_DIR, SKILL_DIR,
    load_config, get_api_url, get_api_key, load_settings,
)

# Pipeline data directories
V9_DIR = DATA_DIR / "v9"
RAW_RESULTS_DIR = V9_DIR / "raw_results"
CANDIDATES_FILE = V9_DIR / "candidates.json"
GENERATED_DIR = V9_DIR / "generated"
POSTED_DIR = V9_DIR / "posted"
SNIPPETS_DIR = V9_DIR / "snippets"
TASKS_DIR = V9_DIR / "tasks"

# Shared state files (cross-run)
DIRECTIVES_FILE = DATA_DIR / "directives.json"
PUSHED_TITLES_FILE = DATA_DIR / "pushed_titles.json"
USED_SOURCE_URLS_FILE = DATA_DIR / "used_source_urls.json"

# Service URLs
_settings = load_settings()
_search_cfg = _settings.get("search", {})
SEARXNG_URL = _search_cfg.get("searxng_url") or "http://localhost:8888"
CRAWL4AI_URL = _search_cfg.get("crawl4ai_url") or "http://localhost:11235"
SEARCH_GATEWAY_URL = _search_cfg.get("search_gateway_url") or "http://localhost:8899"

# Freshness mapping: directive string → days
FRESHNESS_DAYS = {
    "24h": 1, "1d": 1, "2d": 2, "3d": 3, "7d": 7, "14d": 14, "30d": 30,
}

# Map freshness strings to SearXNG time_range parameter
FRESHNESS_TO_TIME_RANGE = {
    "24h": "day",
    "1d": "day",
    "2d": "day",
    "3d": "week",
    "7d": "week",
    "14d": "month",
    "30d": "month",
}

# Search config
NEWS_MIN_RESULTS = 3  # if news returns fewer, supplement with general
MAX_RESULTS_PER_QUERY = 10


def ensure_dirs():
    """Create all pipeline data directories."""
    for d in [V9_DIR, RAW_RESULTS_DIR, GENERATED_DIR, POSTED_DIR, SNIPPETS_DIR, TASKS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# Source quality tiers for domain-based crawl prioritization
SOURCE_QUALITY = {
    # Tier 1: Reliable, rarely blocked
    "tier1": [
        "arstechnica.com", "theregister.com", "techcrunch.com", "wired.com",
        "theverge.com", "reuters.com", "apnews.com", "bbc.com",
        "phys.org", "news-medical.net", "nature.com", "science.org",
    ],
    # Tier 2: Usually OK
    "tier2": [
        "venturebeat.com", "zdnet.com", "thenextweb.com", "aol.com",
        "finance.yahoo.com", "businessinsider.com", "mashable.com",
        "securityweek.com", "ithome.com", "36kr.com",
    ],
    # Tier 3: Unreliable — high fail rate, paywalls, or aggregator link rot
    "tier3_unreliable": [
        "msn.com", "msn.cn", "forbes.com", "cnbc.com", "nytimes.com",
        "thehill.com", "politico.eu", "seekingalpha.com", "winbuzzer.com",
        "techrepublic.com", "beckershospitalreview.com",
    ],
}


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}
