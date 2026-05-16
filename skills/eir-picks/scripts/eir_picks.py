#!/usr/bin/env python3
"""
Eir Picks Client — connect, fetch public picks, and post overlays.

Standalone script, stdlib only, no external dependencies.

Usage:
  python3 scripts/eir_picks.py connect CODE   # Exchange pairing code for API key
  python3 scripts/eir_picks.py fetch           # Fetch public picks → stdout JSON
  python3 scripts/eir_picks.py post FILE       # Post overlays from JSON file
  python3 scripts/eir_picks.py post -          # Post overlays from stdin
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = SKILL_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "eir.json"
API_BASE = "https://api.heyeir.com"
REQUEST_TIMEOUT = 30


def _load_config():
    """Load API credentials from env vars or config/eir.json."""
    api_url = os.environ.get("EIR_API_URL")
    api_key = os.environ.get("EIR_API_KEY")
    if api_url and api_key:
        url = api_url.rstrip("/")
        return url.removesuffix("/api"), api_key

    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text())
        url = cfg.get("apiUrl", "").rstrip("/")
        if url.endswith("/api"):
            url = url[:-4]
        key = cfg.get("apiKey", "")
        if url and key:
            return url, key

    print("Error: Not connected. Run: python3 scripts/eir_picks.py connect YOUR_CODE", file=sys.stderr)
    sys.exit(1)


def connect(code):
    """Exchange pairing code for API key. Saves to config/eir.json."""
    body = json.dumps({"code": code}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/oc/connect",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        print(f"Connection failed ({e.code}): {detail}", file=sys.stderr)
        sys.exit(1)

    api_key = result.get("apiKey")
    if not api_key:
        print(f"Unexpected response: {result}", file=sys.stderr)
        sys.exit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {"apiUrl": API_BASE, "apiKey": api_key}
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    print(f"✅ Connected successfully. Config saved to {CONFIG_FILE.relative_to(SKILL_DIR)}")


def fetch_picks():
    """Fetch public picks from /oc/curation. Returns dict with picks + context."""
    api_url, api_key = _load_config()
    req = urllib.request.Request(
        f"{api_url}/api/oc/curation",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        print(f"Fetch failed ({e.code}): {detail}", file=sys.stderr)
        sys.exit(1)

    return {
        "publicPicks": data.get("publicPicks", []),
        "recentEngagements": data.get("recentEngagements", []),
        "curationStats": data.get("curationStats", {}),
        "directives": [
            {"slug": d.get("slug"), "label": d.get("label"), "tier": d.get("tier")}
            for d in data.get("directives", [])
        ],
    }


def post_overlays(overlays):
    """POST overlays to /oc/picks. Returns API response dict."""
    if not overlays:
        print("Nothing to post.")
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
        detail = e.read().decode("utf-8", errors="replace")[:200]
        return {"error": str(e), "detail": detail}


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "connect":
        if len(sys.argv) < 3:
            print("Usage: python3 scripts/eir_picks.py connect YOUR_PAIRING_CODE", file=sys.stderr)
            sys.exit(1)
        connect(sys.argv[2])

    elif cmd == "fetch":
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
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    main()
