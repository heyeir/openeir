#!/usr/bin/env python3
"""
Eir Picks Client — fetch public picks and post overlays.

Standalone script with zero external dependencies (stdlib only).
Requires: EIR_API_KEY env var or config/eir.json in skill directory.

Usage:
  python3 scripts/eir_picks.py fetch          # Fetch public picks → stdout JSON
  python3 scripts/eir_picks.py post FILE      # Post overlays from JSON file
  python3 scripts/eir_picks.py post -         # Post overlays from stdin
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = SKILL_DIR / "config" / "eir.json"
REQUEST_TIMEOUT = 30


def _load_config():
    """Load API credentials from env vars or config/eir.json."""
    api_url = os.environ.get("EIR_API_URL")
    api_key = os.environ.get("EIR_API_KEY")
    if api_url and api_key:
        return api_url.rstrip("/").removesuffix("/api"), api_key

    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text())
        url = cfg.get("apiUrl", "").rstrip("/")
        if url.endswith("/api"):
            url = url[:-4]
        key = cfg.get("apiKey", "")
        if url and key:
            return url, key

    print("Error: No API credentials. Set EIR_API_KEY + EIR_API_URL env vars,", file=sys.stderr)
    print("       or create config/eir.json with {\"apiUrl\": \"...\", \"apiKey\": \"...\"}", file=sys.stderr)
    sys.exit(1)


def fetch_picks():
    """Fetch public picks from /oc/curation. Returns dict with picks + context."""
    api_url, api_key = _load_config()
    req = urllib.request.Request(
        f"{api_url}/api/oc/curation",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read())

    return {
        "publicPicks": data.get("publicPicks", []),
        "recentEngagements": data.get("recentEngagements", []),
        "curationStats": data.get("curationStats", {}),
        "exclude": data.get("exclude", {}),
        "directives": [
            {"slug": d.get("slug"), "label": d.get("label"), "tier": d.get("tier")}
            for d in data.get("directives", [])
        ],
    }


def post_overlays(overlays):
    """POST overlays to /oc/picks. Returns API response dict."""
    if not overlays:
        return {"upserted": 0, "rejected": 0}

    api_url, api_key = _load_config()
    body = json.dumps({"picks": overlays}, ensure_ascii=False).encode()

    req = urllib.request.Request(
        f"{api_url}/api/oc/picks",
        method="POST",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:200]
        return {"error": str(e), "detail": body_text}


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "fetch":
        result = fetch_picks()
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        print()

    elif cmd == "post":
        src = sys.argv[2] if len(sys.argv) > 2 else "-"
        if src == "-":
            data = json.load(sys.stdin)
        else:
            data = json.loads(Path(src).read_text())
        overlays = data if isinstance(data, list) else data.get("picks", data.get("overlays", []))
        result = post_overlays(overlays)
        json.dump(result, sys.stdout, indent=2)
        print()

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
