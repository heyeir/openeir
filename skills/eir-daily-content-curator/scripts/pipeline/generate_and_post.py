#!/usr/bin/env python3
"""
Phase 4+5: Generate content and POST to Eir Content API.

This is designed to be called by an OpenClaw agent (not standalone),
because content generation requires LLM. The script handles:
  1. Read candidates.json + crawled snippets
  2. Build generation prompts (agent calls LLM)
  3. POST to Eir Content API with topicSlug
  4. Translate + POST with same contentGroup ID

Usage (by agent):
  The agent reads candidates.json, generates content via LLM,
  then calls post_to_api() and translate_and_post() from this module.
"""

import hashlib
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import (
    CANDIDATES_FILE, SNIPPETS_DIR, GENERATED_DIR, POSTED_DIR,
    PUSHED_TITLES_FILE, V9_DIR,
    ensure_dirs, load_json, get_api_url, get_api_key,
)
from .eir_config import SKILL_DIR

TIMEOUT = 60
REQUEST_INTERVAL = 0.5

# Writer prompt is loaded from references/ at call time
WRITER_PROMPT_PATH = SKILL_DIR / "references" / "writer-prompt-eir.md"
TRANSLATE_PROMPT_PATH = SKILL_DIR / "references" / "writer-prompt-eir.md"  # same file, translate section below


def api_request(method, url, data=None, api_key=""):
    """Make API request with retry."""
    body = json.dumps(data, ensure_ascii=False).encode() if data else None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, method=method, data=body,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status, json.loads(resp.read())
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            try:
                return e.code, {"error": str(e)}
            except AttributeError:
                return 0, {"error": str(e)}
    return 0, {"error": "max retries"}


def _get_title_for_url(candidate, url):
    """Get title for a URL from candidate's source_titles (list or dict)."""
    titles = candidate.get("source_titles", [])
    urls = candidate.get("source_urls", [])
    if isinstance(titles, dict):
        return titles.get(url, "")
    if isinstance(titles, list) and isinstance(urls, list):
        try:
            idx = urls.index(url)
            return titles[idx] if idx < len(titles) else ""
        except ValueError:
            return ""
    return ""


def snippet_path_for_url(url):
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    return SNIPPETS_DIR / ("%s.json" % url_hash)


def load_candidate_sources(candidate):
    """Load crawled content for a candidate's source URLs."""
    sources = []
    for url in candidate.get("crawled_sources", candidate.get("source_urls", [])):
        path = snippet_path_for_url(url)
        if not path.exists():
            continue
        snippet = load_json(path)
        content = snippet.get("content", "")
        if len(content) < 500:
            continue
        sources.append({
            "url": url,
            "title": _get_title_for_url(candidate, url),
            "name": urlparse(url).netloc.replace("www.", ""),
            "content": content[:6000],
        })
    return sources


def _load_writer_prompt():
    """Load writer prompt from references/writer-prompt-eir.md."""
    if WRITER_PROMPT_PATH.exists():
        return WRITER_PROMPT_PATH.read_text()
    # Fallback: minimal inline prompt
    return "Generate a Chinese article for Eir. Output JSON only. See content-spec.md for format."


def build_generation_prompt(candidate, sources):
    """Build the LLM prompt for content generation."""
    slug = candidate["matched_topic_slug"]
    angle = candidate.get("suggested_angle", "")
    reason = candidate.get("reason", "")

    source_text = ""
    for i, s in enumerate(sources):
        source_text += "\n--- Source %d: %s (%s) ---\n%s\n" % (
            i + 1, s["title"], s["name"], s["content"][:4000])

    writer_prompt = _load_writer_prompt()

    prompt = """%s

---

## Task

Topic slug: %s
Angle: %s
Why: %s
Output language: zh

Source material:
%s

Output ONLY the JSON. No other text or markdown fences.""" % (
        writer_prompt, slug, angle, reason, source_text)

    return prompt


def post_to_api(content_data, api_key):
    """POST content to Eir Content API. Returns (content_id, contentGroup) or raises."""
    item = {
        "lang": content_data["lang"],
        "slug": content_data["slug"],
        "topicSlug": content_data.get("topicSlug", content_data["slug"]),
        "dot": content_data["dot"],
        "l1": content_data["l1"],
        "l2": content_data["l2"],
        "sources": content_data.get("sources", []),
    }
    if content_data.get("interests"):
        item["interests"] = content_data["interests"]
    if content_data.get("contentGroup"):
        item["contentGroup"] = content_data["contentGroup"]

    payload = {"items": [item]}

    time.sleep(REQUEST_INTERVAL)
    status, resp = api_request("POST", get_api_url() + "/api/oc/content", payload, api_key)

    if status not in (200, 201):
        raise RuntimeError("POST failed: %d %s" % (status, json.dumps(resp, ensure_ascii=False)[:300]))

    results = resp.get("results", [])
    if not results or results[0].get("status") != "accepted":
        reason = results[0].get("reason", "unknown") if results else "empty"
        raise RuntimeError("POST rejected: %s" % reason)

    content_id = results[0].get("id", "")
    content_group = results[0].get("contentGroup", "")
    return content_id, content_group


def build_translate_prompt(content_data):
    """Build prompt for translating zh content to en."""
    prompt = """Translate this Chinese content to English. Keep the same JSON structure.

Original content:
%s

Output JSON (no markdown fences):
{
  "lang": "en",
  "slug": "%s",
  "topicSlug": "%s",
  "contentGroup": "%s",
  "dot": {
    "hook": "≤8 English words, curiosity gap",
    "category": "%s",
    "color_hint": "%s"
  },
  "l1": {
    "title": "opinionated title, 8-15 EN words",
    "subtitle": "translated subtitle",
    "summary": "translated summary, 2-3 sentences",
    "key_quote": "translated key quote or empty string",
    "via": %s,
    "bullets": ["translated bullet 1", "bullet 2", "bullet 3"]
  },
  "l2": {
    "content": "translated body, 150-300 EN words, 2-4 paragraphs",
    "bullets": [translated fact bullets with confidence],
    "context": "translated context",
    "eir_take": "translated eir_take",
    "related_topics": ["related topic in English", "another", "third"]
  },
  "sources": %s
}

Rules:
- Natural English, not word-by-word translation
- dot.hook ≤ 8 words
- l2.bullets: keep {text, confidence} format, translate text
- l2.related_topics: translate to English topic phrases
- Keep sources unchanged
- contentGroup must be "%s" (same as Chinese version)""" % (
        json.dumps({
            "dot": content_data["dot"],
            "l1": content_data["l1"],
            "l2": content_data["l2"],
        }, ensure_ascii=False, indent=2),
        content_data["slug"],
        content_data.get("topicSlug", content_data["slug"]),
        content_data.get("contentGroup", ""),
        content_data["dot"].get("category", "focus"),
        content_data["dot"].get("color_hint", "blue"),
        json.dumps(content_data["l1"].get("via", []), ensure_ascii=False),
        json.dumps(content_data.get("sources", []), ensure_ascii=False),
        content_data.get("contentGroup", ""),
    )
    return prompt


def record_pushed(content_data, content_id, content_group):
    """Append to pushed_titles.json."""
    pushed = load_json(PUSHED_TITLES_FILE, [])
    if not isinstance(pushed, list):
        pushed = []
    pushed.append({
        "slug": content_data["slug"],
        "title": content_data.get("l1", {}).get("title", ""),
        "lang": content_data["lang"],
        "content_id": content_id,
        "content_group": content_group,
        "topic_slug": content_data.get("topicSlug", ""),
        "pushed_at": datetime.now(timezone.utc).isoformat(),
        "source_urls": [s.get("url", "") for s in content_data.get("sources", [])],
    })
    PUSHED_TITLES_FILE.write_text(json.dumps(pushed, ensure_ascii=False, indent=2))


def save_generated(content_data, suffix=""):
    """Save generated content to file."""
    slug = content_data.get("slug", "unknown")
    lang = content_data.get("lang", "zh")
    name = "%s_%s%s.json" % (slug, lang, suffix)
    path = GENERATED_DIR / name
    path.write_text(json.dumps(content_data, indent=2, ensure_ascii=False))
    return path


def save_posted(content_data, content_id, content_group):
    """Save posted content to posted dir."""
    slug = content_data.get("slug", "unknown")
    lang = content_data.get("lang", "zh")
    content_data["_posted"] = {
        "content_id": content_id,
        "content_group": content_group,
        "posted_at": datetime.now(timezone.utc).isoformat(),
    }
    name = "%s_%s.json" % (slug, lang)
    path = POSTED_DIR / name
    path.write_text(json.dumps(content_data, indent=2, ensure_ascii=False))
    return path


# === Functions for the agent to call ===

def get_candidates_for_generation():
    """Return candidates that have crawled content, ready for generation."""
    candidates = load_json(CANDIDATES_FILE, {})
    ready = []
    for c in candidates.get("candidates", []):
        if not c.get("has_content", False):
            continue
        sources = load_candidate_sources(c)
        if sources:
            ready.append({
                "candidate": c,
                "sources": sources,
                "prompt": build_generation_prompt(c, sources),
            })
    return ready


def get_translate_prompt(content_data):
    """Get translate prompt for a content item (after zh POST succeeds)."""
    return build_translate_prompt(content_data)
