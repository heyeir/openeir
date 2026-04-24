#!/usr/bin/env python3
"""
Phase 4: Generate content from tasks.

This is designed to be called by an OpenClaw agent (not standalone),
because content generation requires LLM. The script handles:
  1. Read task files
  2. Build generation prompts (agent calls LLM)
  3. Save generated content locally

API posting functionality moved to eir_post.py (Eir mode only).

Usage (by agent):
  The agent reads task files, generates content via LLM,
  then optionally calls eir_post functions for Eir mode.
"""

import json
from pathlib import Path

from .config import (
    GENERATED_DIR, TASKS_DIR,
    ensure_dirs,
)
from .workspace import SKILL_DIR

# Writer prompt paths
WRITER_PROMPT_PATH = SKILL_DIR / "references" / "writer-prompt-eir.md"
WRITER_PROMPT_STANDALONE_PATH = SKILL_DIR / "references" / "writer-prompt-standalone.md"


def load_writer_prompt():
    """Load writer prompt based on mode (eir or standalone)."""
    from .workspace import load_settings
    settings = load_settings()
    mode = settings.get("mode", "standalone")
    return _load_prompt_by_mode(mode)


def _load_prompt_by_mode(mode):
    """Load writer prompt file for the given mode."""
    if mode == "eir" and WRITER_PROMPT_PATH.exists():
        return WRITER_PROMPT_PATH.read_text()
    if WRITER_PROMPT_STANDALONE_PATH.exists():
        return WRITER_PROMPT_STANDALONE_PATH.read_text()
    if WRITER_PROMPT_PATH.exists():
        return WRITER_PROMPT_PATH.read_text()
    return "Generate structured content from the sources below."


def build_generation_prompt(task_data):
    """Build the LLM prompt for content generation from task data."""
    slug = task_data.get("topic_slug", "")
    angle = task_data.get("suggested_angle", "")
    reason = task_data.get("reason", "")
    source_text = task_data.get("source_text", "")
    reader_context = task_data.get("reader_context", "")
    
    # Load writer prompt: use mode marker from task (v2), fall back to embedded prompt (v1)
    writer_prompt_mode = task_data.get("writer_prompt_mode", "")
    if writer_prompt_mode:
        writer_prompt = _load_prompt_by_mode(writer_prompt_mode)
    else:
        writer_prompt = task_data.get("writer_prompt", "") or load_writer_prompt()

    prompt = """%s

---

## Task

Topic slug: %s
Angle: %s
Why: %s
Output language: zh
%s
Source material:
%s

Output ONLY the JSON. No other text or markdown fences.""" % (
        writer_prompt, slug, angle, reason, 
        "\nReader context:\n" + reader_context if reader_context else "",
        source_text)

    return prompt


def save_generated(content_data, suffix=""):
    """Save generated content to file."""
    ensure_dirs()
    slug = content_data.get("slug", "unknown")
    lang = content_data.get("lang", "zh")
    name = "%s_%s%s.json" % (slug, lang, suffix)
    path = GENERATED_DIR / name
    path.write_text(json.dumps(content_data, indent=2, ensure_ascii=False))
    return path


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
    "category": "%s"
  },
  "l1": {
    "title": "opinionated title, 8-15 EN words",
    "summary": "translated summary, 2-3 sentences",
    "key_quote": "translated key quote or empty string",
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
- dot.hook ≤8 words
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
        json.dumps(content_data.get("sources", []), ensure_ascii=False),
        content_data.get("contentGroup", ""),
    )
    return prompt


# === Functions for standalone generation ===

def get_tasks_for_generation():
    """Return task files ready for generation."""
    ensure_dirs()
    task_files = list(TASKS_DIR.glob("*.json"))
    task_files = [f for f in task_files if f.stem != "manifest"]
    
    tasks = []
    for task_file in task_files:
        try:
            task_data = json.loads(task_file.read_text())
            tasks.append({
                "file": task_file,
                "data": task_data,
                "prompt": build_generation_prompt(task_data),
            })
        except (json.JSONDecodeError, KeyError) as e:
            print(f"⚠️ Skipping invalid task file {task_file.name}: {e}")
    
    return tasks