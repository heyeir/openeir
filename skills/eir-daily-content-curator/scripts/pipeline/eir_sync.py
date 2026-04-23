#!/usr/bin/env python3
"""
Eir API read operations - fetch directives and report misses.
Only used when Eir mode is enabled.

Usage:
  python3 -m pipeline.eir_sync fetch     # Fetch directives from API
  python3 -m pipeline.eir_sync miss      # Report missed topic slugs
"""

import json
import sys
import urllib.request
from datetime import datetime, timezone

from .config import DIRECTIVES_FILE, load_json
from .workspace import get_api_url, get_api_key


def _fetch_interests_as_directives():
    """Fallback: build directives from /oc/interests when /oc/curation is unavailable.
    Assigns default tier/freshness based on heat score."""
    api_key = get_api_key()
    req = urllib.request.Request(
        "%s/api/oc/interests" % get_api_url(),
        headers={"Authorization": "Bearer %s" % api_key},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = json.loads(resp.read())
    interests = raw.get("interests", raw) if isinstance(raw, dict) else raw

    # Sort by heat desc, take top N (avoid too many searches)
    interests = [i for i in interests if isinstance(i, dict) and i.get("status") == "active"]
    interests.sort(key=lambda i: i.get("heat", 0), reverse=True)
    top = interests[:40]  # reasonable daily search budget

    directives = []
    tracked = []
    for idx, i in enumerate(top):
        heat = i.get("heat", 0)
        # Assign tier based on heat
        if heat >= 80:
            tier = "tracked"
        elif heat >= 30:
            tier = "focus"
        else:
            tier = "explore"
        # Default freshness by tier
        freshness_map = {"tracked": "3d", "focus": "7d", "explore": "7d"}
        label = i.get("label", "")
        if isinstance(label, list):
            label = label[0] if label else i.get("slug", "")
        d = {
            "slug": i.get("slug", ""),
            "label": label,
            "tier": tier,
            "freshness": freshness_map.get(tier, "7d"),
            "searchHints": [],  # no hints available from interests API
        }
        if tier == "tracked":
            tracked.append(d)
        else:
            directives.append(d)

    data = {
        "directives": directives + tracked,
        "tracked": [],
        "_source": "interests_fallback",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    DIRECTIVES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIRECTIVES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    n = len(directives) + len(tracked)
    print("⚠️  /oc/curation unavailable — built %d directives from /oc/interests (fallback)" % n)
    return data


def fetch_directives():
    """Fetch fresh directives from Eir API.
    Falls back to building directives from /oc/interests if /oc/curation fails."""
    api_key = get_api_key()
    # Try /oc/curation first
    try:
        req = urllib.request.Request(
            "%s/api/oc/curation" % get_api_url(),
            headers={"Authorization": "Bearer %s" % api_key},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        data["_fetched_at"] = datetime.now(timezone.utc).isoformat()
        DIRECTIVES_FILE.parent.mkdir(parents=True, exist_ok=True)
        DIRECTIVES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        n = len(data.get("directives", [])) + len(data.get("tracked", []))
        print("✅ Fetched %d directives from API" % n)
        return data
    except Exception as e:
        print("⚠️  /oc/curation failed (%s), trying interests fallback..." % e, file=sys.stderr)

    # Fallback: build from interests
    try:
        return _fetch_interests_as_directives()
    except Exception as e2:
        print("❌ Both /oc/curation and /oc/interests failed: %s" % e2, file=sys.stderr)
        raise


def report_misses(misses):
    """Report missed topic slugs to POST /oc/curation/miss.
    
    Args:
        misses: list of {slug, reason} dicts, or list of slug strings (legacy)
    """
    if not misses:
        return
    # Normalize to [{slug, reason}]
    normalized = []
    for m in misses:
        if isinstance(m, str):
            normalized.append({"slug": m, "reason": "no usable content"})
        else:
            normalized.append({"slug": m.get("slug", ""), "reason": m.get("reason", "no usable content")})
    normalized = [m for m in normalized if m["slug"]]
    if not normalized:
        return
    try:
        api_url = get_api_url()
        api_key = get_api_key()
        payload = json.dumps({
            "slugs": [m["slug"] for m in normalized],
            "details": normalized,
        }).encode()
        req = urllib.request.Request(
            "%s/api/oc/curation/miss" % api_url,
            data=payload,
            headers={
                "Authorization": "Bearer %s" % api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        slugs_str = ", ".join(m["slug"] for m in normalized)
        print("📡 Reported %d missed topics: %s" % (len(normalized), slugs_str))
    except Exception as e:
        print("⚠️ Failed to report misses: %s" % e)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Eir sync operations")
    parser.add_argument("action", choices=["fetch", "miss"], help="Action to perform")
    parser.add_argument("--slugs", nargs="+", help="Topic slugs for miss reporting")
    parser.add_argument("--reason", default="manual", help="Reason for miss")
    args = parser.parse_args()

    if args.action == "fetch":
        fetch_directives()
    elif args.action == "miss":
        if not args.slugs:
            print("Error: --slugs required for miss action", file=sys.stderr)
            sys.exit(1)
        misses = [{"slug": slug, "reason": args.reason} for slug in args.slugs]
        report_misses(misses)


if __name__ == "__main__":
    main()