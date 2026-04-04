#!/usr/bin/env python3
"""
Post Content — reads generated content JSON files and POSTs to Eir API.

API: each language version is a separate item with top-level l1/l2.
ID format: {8-char contentGroup}_{lang} (e.g. a3k9m2x7_en).

API flow:
  1. POST /api/oc/content {items: [{lang, dot, l1, l2, sources, ...}]}
  2. For bilingual: POST both lang versions in the same request

Usage:
  python3 scripts/pipeline/post_content.py                     # post all pending
  python3 scripts/pipeline/post_content.py --file data/generated/ai-agents.json
  python3 scripts/pipeline/post_content.py --dry-run
"""

import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from eir_config import WORKSPACE, DATA_DIR, load_config as _load_eir_config, get_api_url, get_api_key

DATA = DATA_DIR
GENERATED_DIR = DATA / "generated"
POSTED_DIR = DATA / "posted"
BACKUP_DIR = DATA / "backup"
PUSHED_TITLES_FILE = DATA / "pushed_titles.json"
TRANSLATE_TASKS_DIR = DATA / "translate_tasks"

# Rate limiting
REQUEST_INTERVAL = 0.5  # seconds between requests
MAX_RETRIES = 3
TIMEOUT = 60  # seconds


def load_config():
    config = _load_eir_config()
    if not config.get("apiKey"):
        print("❌ Config not found. Set EIR_API_KEY env var or create config/eir.json", file=sys.stderr)
        print("   Run `node scripts/connect.mjs <PAIRING_CODE>` first.", file=sys.stderr)
        sys.exit(1)
    return config


def api_request(method, url, data=None, api_key="", retries=MAX_RETRIES):
    """Make API request with retry logic."""
    body = json.dumps(data, ensure_ascii=False).encode() if data else None
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, method=method, data=body,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                }
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode()[:500]
            except Exception:
                pass
            
            # Rate limit: wait and retry
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 60))
                print("    ⏳ Rate limited, waiting %ds..." % retry_after, file=sys.stderr)
                time.sleep(retry_after)
                continue
            
            return e.code, {"error": str(e), "body": body_text}
        except Exception as e:
            if attempt < retries - 1:
                print("    ⚠️ Request failed, retrying... (%s)" % e, file=sys.stderr)
                time.sleep(2 ** attempt)
                continue
            return 0, {"error": str(e)}
    
    return 0, {"error": "max retries exceeded"}


def backup_file(path):
    """Backup file before modification."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / ("%s_%s.json" % (Path(path).stem, ts))
    shutil.copy2(path, backup_path)
    return backup_path


def repair_json(text):
    """Repair JSON with unescaped quotes inside string values."""
    result = []
    i = 0
    in_string = False
    while i < len(text):
        c = text[i]
        if not in_string:
            if c == '"':
                in_string = True
            result.append(c)
        else:
            if c == '\\':
                result.append(c)
                if i + 1 < len(text):
                    i += 1
                    result.append(text[i])
            elif c == '"':
                rest = text[i+1:].lstrip()
                if rest and rest[0] in (',', '}', ']', ':'):
                    in_string = False
                    result.append(c)
                elif rest and rest[0] == '"':
                    in_string = False
                    result.append(c)
                else:
                    result.append('\\"')
            elif c == '\n':
                result.append('\\n')
            else:
                result.append(c)
        i += 1
    return ''.join(result)


def load_generated(path):
    """Load a generated JSON file, repairing if needed."""
    raw = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print("    ⚠️ Malformed JSON, backing up and attempting repair...", file=sys.stderr)
        backup_file(path)
        repaired = repair_json(raw)
        data = json.loads(repaired)  # will raise if still broken
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("    ✅ JSON repaired", file=sys.stderr)
        return data


def validate_content(content):
    """Validate content structure before posting."""
    errors = []
    
    # Required fields
    if not content.get("lang"):
        errors.append("missing 'lang'")
    if not content.get("slug"):
        errors.append("missing 'slug'")
    if not content.get("l1", {}).get("title"):
        errors.append("missing 'l1.title'")
    if not content.get("dot", {}).get("hook"):
        errors.append("missing 'dot.hook'")
    
    # Source URL validation
    for i, src in enumerate(content.get("sources", [])):
        url = src.get("url", "")
        if not url:
            errors.append("sources[%d] missing url" % i)
        elif not url.startswith(("http://", "https://")):
            errors.append("sources[%d] invalid url scheme" % i)
        # Block internal IPs
        elif any(ip in url for ip in ["://10.", "://192.168.", "://127.", "://localhost"]):
            errors.append("sources[%d] internal URL not allowed" % i)
    
    return errors


def post_content(generated_file, api_key, dry_run=False, dedup=None, bilingual=False):
    """Post a single content file to the API."""
    content = load_generated(generated_file)
    slug = content.get("slug", "unknown")
    lang = content.get("lang", content.get("output_lang", "zh"))
    
    # Normalize: ensure 'lang' field exists
    content["lang"] = lang
    
    title = content.get("l1", {}).get("title", slug)
    
    # Validate
    errors = validate_content(content)
    if errors:
        return {"slug": slug, "status": "error", "reason": "validation: " + "; ".join(errors)}
    
    # Semantic dedup check
    if dedup:
        is_dup, match, score = dedup.check(title)
        if is_dup:
            reason = "dedup: %.3f similar to '%s'" % (score, match.get("title", "?")[:40])
            print("  ⏭️  %s — %s" % (slug, reason))
            return {"slug": slug, "title": title, "status": "skipped", "reason": reason}
    
    if dry_run:
        print("  [dry-run] Would POST: %s (%s) — %s" % (slug, lang, title))
        return {"slug": slug, "title": title, "lang": lang, "status": "dry-run"}
    
    # Enrich sources with publish_time from snippet data
    sources = content.get("sources", [])
    snippets_dir = DATA / "snippets"
    for src in sources:
        url = src.get("url", "")
        # Normalize field name: publishTime → publish_time
        if "publishTime" in src and "publish_time" not in src:
            src["publish_time"] = src.pop("publishTime")
        if url and "publish_time" not in src:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            snippet_path = snippets_dir / ("%s.json" % url_hash)
            if snippet_path.exists():
                try:
                    sd = json.loads(snippet_path.read_text())
                    pub = sd.get("published", "")
                    if pub:
                        src["publish_time"] = pub
                except Exception:
                    pass
    
    # Build API payload: top-level l1/l2 per lang
    item = {
        "lang": lang,
        "dot": content.get("dot", {}),
        "slug": content.get("slug", slug),
        "topicSlug": content.get("topic_slug", content.get("topicSlug", slug)),
        "l1": content.get("l1", {}),
        "l2": content.get("l2", {}),
        "sources": sources,
    }
    # Include optional fields
    if content.get("content_url_slug"):
        item["content_url_slug"] = content["content_url_slug"]
    if content.get("topics"):
        item["topics"] = content["topics"]
    
    payload = {"items": [item]}
    
    # POST to API
    time.sleep(REQUEST_INTERVAL)
    status, resp = api_request("POST", get_api_url() + "/api/oc/content", payload, api_key)
    
    if status not in (200, 201):
        return {"slug": slug, "title": title, "lang": lang, "status": "error",
                "reason": "POST failed: %d %s" % (status, resp)}
    
    # Response: {accepted: N, rejected: N, results: [{status, id, contentGroup, ...}]}
    results = resp.get("results", [])
    if not results or results[0].get("status") != "accepted":
        reason = results[0].get("reason", resp.get("error", "unknown")) if results else "empty results"
        return {"slug": slug, "title": title, "lang": lang, "status": "error",
                "reason": "POST rejected: %s" % reason}
    
    content_id = results[0].get("id", "") if results else resp.get("id", "")
    content_group = results[0].get("contentGroup", "") if results else ""
    print("    POST %s (%s) ok → %s (group: %s)" % (slug, lang, content_id, content_group))
    
    # Move to posted dir
    POSTED_DIR.mkdir(parents=True, exist_ok=True)
    posted_path = POSTED_DIR / Path(generated_file).name
    os.rename(generated_file, posted_path)
    
    # Update pushed_titles
    pushed = []
    if PUSHED_TITLES_FILE.exists():
        try:
            pushed = json.loads(PUSHED_TITLES_FILE.read_text())
        except Exception:
            pushed = []
    
    pushed.append({
        "slug": slug,
        "title": title,
        "lang": lang,
        "content_id": content_id,
        "pushed_at": datetime.now(timezone.utc).isoformat(),
        "source_urls": [s.get("url", "") for s in sources if s.get("url")],
    })
    PUSHED_TITLES_FILE.write_text(json.dumps(pushed, ensure_ascii=False, indent=2))
    
    # Record in semantic dedup index
    if dedup:
        dedup.record(title, slug=slug, content_id=content_id, lang=lang,
                     source_urls=[s.get("url", "") for s in sources if s.get("url")])
    
    # Queue translation task if bilingual
    if bilingual:
        target_lang = "en" if lang == "zh" else "zh"
        queue_translation(content_id, lang, target_lang, content)
    
    return {"slug": slug, "title": title, "lang": lang, "content_id": content_id, "status": "ok"}


def queue_translation(content_id, source_lang, target_lang, content):
    """Queue a translation task for later processing."""
    TRANSLATE_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    
    task = {
        "source_content_id": content_id,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "slug": content.get("slug"),
        "l1": content.get("l1"),
        "l2": content.get("l2"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    task_path = TRANSLATE_TASKS_DIR / ("%s_%s.json" % (content.get("slug", "unknown"), target_lang))
    task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))
    print("    📝 Translation task queued: %s → %s" % (source_lang, target_lang))


def main():
    parser = argparse.ArgumentParser(description="Post generated content to Eir API")
    parser.add_argument("--file", help="Post a single file")
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--bilingual", action="store_true", help="Queue translation tasks")
    args = parser.parse_args()
    
    config = load_config()
    api_key = config.get("apiKey")
    if not api_key:
        print("❌ apiKey not found in config", file=sys.stderr)
        sys.exit(1)
    
    # Check user bilingual setting (can be overridden by --bilingual flag)
    bilingual = args.bilingual or config.get("bilingual", False)
    
    # Initialize semantic dedup
    dedup = None
    try:
        from title_dedup import TitleDedup
        dedup = TitleDedup()
        print("  Title dedup loaded (%d titles, threshold=%.2f)" % (len(dedup._meta), dedup.threshold))
    except Exception as e:
        print("  ⚠️ Title dedup unavailable: %s" % e, file=sys.stderr)
    
    if args.file:
        files = [args.file]
    else:
        files = sorted(glob.glob(str(GENERATED_DIR / "*.json")))
    
    if not files:
        print("No generated files to post.")
        return
    
    print("Posting %d content file(s)..." % len(files))
    results = []
    for f in files:
        slug = Path(f).stem
        print("  → %s" % slug)
        result = post_content(f, api_key, dry_run=args.dry_run, dedup=dedup, bilingual=bilingual)
        results.append(result)
        status_msg = result.get("reason", result.get("content_id", ""))
        print("    %s: %s" % (result["status"], status_msg))
    
    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    skip = sum(1 for r in results if r["status"] == "skipped")
    
    print("\n✅ %d posted, ⏭️ %d skipped, ❌ %d failed" % (ok, skip, err))
    
    if results:
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
