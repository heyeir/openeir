#!/usr/bin/env python3
"""
Post Translation — reads translated content and PATCHes to Eir API as locale.

Reads from data/translated/*.json (output by translation subagent)
and calls PATCH /api/oc/content/:id/locale/:lang to add the translation.

Usage:
  python3 scripts/pipeline/post_translation.py
  python3 scripts/pipeline/post_translation.py --file data/translated/ai-agents_en.json
  python3 scripts/pipeline/post_translation.py --dry-run
"""

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from eir_config import DATA_DIR, load_config as _load_eir_config, get_api_url, get_api_key

DATA = DATA_DIR
TRANSLATED_DIR = DATA / "translated"
POSTED_DIR = DATA / "posted_translations"

REQUEST_INTERVAL = 0.5
TIMEOUT = 60


def load_config():
    config = _load_eir_config()
    if not config.get("apiKey"):
        print("❌ Config not found. Set EIR_API_KEY env var or create config/eir.json", file=sys.stderr)
        sys.exit(1)
    return config


def api_request(method, url, data=None, api_key=""):
    import urllib.request
    body = json.dumps(data, ensure_ascii=False).encode() if data else None
    req = urllib.request.Request(
        url, method=method, data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.request.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode()[:500]
        except Exception:
            pass
        return e.code, {"error": str(e), "body": body_text}
    except Exception as e:
        return 0, {"error": str(e)}


def post_translation(translated_file, api_key, dry_run=False):
    """Post a translated content file to the API."""
    content = json.loads(Path(translated_file).read_text(encoding="utf-8"))
    
    source_content_id = content.get("source_content_id", content.get("translation_of"))
    lang = content.get("lang", content.get("target_lang"))
    slug = content.get("slug", "unknown")
    title = content.get("l1", {}).get("title", slug)
    
    if not source_content_id:
        return {"slug": slug, "status": "error", "reason": "missing source_content_id"}
    if not lang:
        return {"slug": slug, "status": "error", "reason": "missing lang"}
    if not content.get("l1", {}).get("title"):
        return {"slug": slug, "status": "error", "reason": "missing l1.title"}
    
    if dry_run:
        print("  [dry-run] Would POST translation: %s (%s) → %s" % (slug, lang, source_content_id))
        return {"slug": slug, "lang": lang, "status": "dry-run"}
    
    # Build payload
    payload = {
        "lang": lang,
        "dot": content.get("dot", {}),
        "l1": content.get("l1", {}),
        "l2": content.get("l2", {}),
    }
    
    # PATCH /content/:id/locale/:lang (not POST .../translation which is 404)
    time.sleep(REQUEST_INTERVAL)
    url = "%s/content/%s/locale/%s" % (get_api_url() + "/api/oc", source_content_id, lang)
    status, resp = api_request("PATCH", url, payload, api_key)
    
    if status not in (200, 201):
        return {"slug": slug, "lang": lang, "status": "error",
                "reason": "POST failed: %d %s" % (status, resp)}
    
    new_content_id = resp.get("id", "")
    print("    PATCH locale %s (%s) ok" % (slug, lang))
    
    # Move to posted dir
    POSTED_DIR.mkdir(parents=True, exist_ok=True)
    posted_path = POSTED_DIR / Path(translated_file).name
    os.rename(translated_file, posted_path)
    
    return {
        "slug": slug,
        "title": title,
        "lang": lang,
        "content_id": new_content_id,
        "source_content_id": source_content_id,
        "status": "ok"
    }


def main():
    parser = argparse.ArgumentParser(description="Post translated content to Eir API")
    parser.add_argument("--file", help="Post a single file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    config = load_config()
    api_key = config.get("apiKey")
    if not api_key:
        print("❌ apiKey not found in config", file=sys.stderr)
        sys.exit(1)
    
    if args.file:
        files = [args.file]
    else:
        files = sorted(glob.glob(str(TRANSLATED_DIR / "*.json")))
    
    if not files:
        print("No translated files to post.")
        return
    
    print("Posting %d translation(s)..." % len(files))
    results = []
    for f in files:
        slug = Path(f).stem
        print("  → %s" % slug)
        result = post_translation(f, api_key, dry_run=args.dry_run)
        results.append(result)
        print("    %s: %s" % (result["status"], result.get("reason", result.get("content_id", ""))))
    
    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    print("\n✅ %d posted, ❌ %d failed" % (ok, err))


if __name__ == "__main__":
    main()
