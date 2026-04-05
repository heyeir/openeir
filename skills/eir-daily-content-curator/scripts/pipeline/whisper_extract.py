#!/usr/bin/env python3
"""
Whisper Extract — Incremental extraction of insights from conversations.

Analyzes Eir conversations to find "Whisper moments" — genuine intellectual
collisions worth preserving. Generates polished mini-essays (Whispers).

Usage:
  python3 scripts/pipeline/whisper_extract.py              # incremental extract
  python3 scripts/pipeline/whisper_extract.py --since 2026-04-01T00:00:00Z
  python3 scripts/pipeline/whisper_extract.py --dry-run    # preview only
  python3 scripts/pipeline/whisper_extract.py --max 3      # max whispers per run
"""

# NOTE: This script provides API helpers for fetching/posting whispers.
# The actual LLM analysis is done by the OpenClaw agent using the prompt
# in references/whisper-api.md.

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Import Eir config (handles API URL and key)
sys.path.insert(0, str(Path(__file__).parent))
from eir_config import get_api_url, get_api_key

# === Constants ===
MIN_CONVERSATION_MESSAGES = 5
MAX_WHISPERS_PER_RUN = 5
WHISPER_CANDIDATE_LIMIT = 10


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_conversations(since: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Fetch conversations with whisper candidate flag from Eir API."""
    api_url = get_api_url()
    api_key = get_api_key()
    
    params = {"whisper_candidates": "true", "limit": limit}
    if since:
        params["since"] = since
    
    query = urllib.parse.urlencode(params)
    
    req = urllib.request.Request(
        f"{api_url}/api/oc/conversations?{query}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("conversations", [])
    except Exception as e:
        print(f"  ❌ Failed to fetch conversations: {e}")
        return []


def fetch_conversation_detail(conv_id: str) -> Optional[Dict]:
    """Fetch full conversation with messages."""
    api_url = get_api_url()
    api_key = get_api_key()
    
    req = urllib.request.Request(
        f"{api_url}/api/oc/conversations/{conv_id}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("conversation")
    except Exception as e:
        print(f"    ⚠️ Failed to fetch conversation {conv_id}: {e}")
        return None


def format_conversation(conv: Dict) -> str:
    """Format conversation for LLM analysis."""
    messages = conv.get("messages", [])
    lines = []
    for msg in messages:
        role = "User" if msg.get("role") == "user" else "Eir"
        content = msg.get("content", "")
        if len(content) > 2000:
            content = content[:2000] + "... [truncated]"
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def analyze_conversation(conv: Dict) -> Optional[Dict]:
    """Analyze if conversation is a Whisper moment."""
    conv_text = format_conversation(conv)
    
    prompt = f'''You are Eir's Whisper analyzer. Review this conversation.

A Whisper moment requires AT LEAST 2 of:
- Beyond surface-level (>5 exchanges)
- Genuine disagreement or perspective shift
- Unresolved question emerges
- Non-obvious insight expressed
- Fundamental/philosophical topic

If NO: return {{"whisper": false, "reason": "brief"}}

If YES: return {{
  "whisper": true,
  "analysis": {{
    "why_worthy": "...",
    "core_tension": "X vs Y",
    "key_insight": "...",
    "unresolved": "...",
    "eir_role": "challenger|extender|mirror|catalyst",
    "thinking_path": ["node1", "node2", "node3"]
  }}
}}

Conversation:
{conv_text}'''
    
    sys.exit("Error: whisper_extract.py must be run through an OpenClaw agent. The agent provides LLM analysis.")


def generate_whisper(conv: Dict, analysis: Dict) -> Optional[Dict]:
    """Generate full Whisper from conversation and analysis.
    
    NOTE: Must be run through an OpenClaw agent which provides LLM analysis.
    The prompt templates above are reference only — the agent calls the LLM directly.
    """
    sys.exit("Error: whisper_extract.py must be run through an OpenClaw agent. The agent provides LLM analysis.")


def post_whisper(whisper: Dict) -> Dict:
    """Post a single whisper to Eir API."""
    api_url = get_api_url()
    api_key = get_api_key()
    
    payload = json.dumps(whisper).encode()
    
    req = urllib.request.Request(
        f"{api_url}/api/oc/whispers",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        return {"error": f"{e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Whisper Extract")
    parser.add_argument("--since", type=str, help="ISO 8601 timestamp (e.g., 2026-04-01T00:00:00Z)")
    parser.add_argument("--max", type=int, default=MAX_WHISPERS_PER_RUN, help="Max whispers")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()
    
    # Verify API connectivity
    try:
        get_api_key()
    except RuntimeError as e:
        print(f"❌ Eir API not configured: {e}")
        print("   Run: /curate --connect <code>")
        sys.exit(1)
    
    print(f"💭 Whisper Extract")
    
    # Fetch conversations with whisper candidate flag
    print(f"  Fetching whisper candidate conversations...")
    conversations = fetch_conversations(since=args.since, limit=WHISPER_CANDIDATE_LIMIT)
    print(f"  Found {len(conversations)} candidates")
    
    if not conversations:
        print("  No whisper candidates found")
        return
    
    # Process each candidate
    whispers_created = 0
    for conv_summary in conversations[:args.max]:
        conv_id = conv_summary.get("id")
        print(f"\n  Processing: {conv_id}")
        
        # Fetch full conversation with messages
        conv = fetch_conversation_detail(conv_id)
        if not conv:
            continue
        
        if len(conv.get("messages", [])) < MIN_CONVERSATION_MESSAGES:
            print(f"    ⏭️ Skipped: too few messages")
            continue
        
        # Analyze for whisper worthiness
        print(f"    Analyzing...")
        analysis = analyze_conversation(conv)
        if not analysis:
            print(f"    ⏭️ Not a whisper moment")
            continue
        
        print(f"    ✓ Candidate: {analysis.get('core_tension', '...')[:40]}...")
        
        # Generate whisper
        print(f"    Generating...")
        whisper = generate_whisper(conv, analysis)
        if not whisper:
            print(f"    ❌ Generation failed")
            continue
        
        print(f"    ✓ {whisper['dot']['hook'][:30]}...")
        
        if args.dry_run:
            print(f"    [dry-run] Would post to Eir")
            whispers_created += 1
            continue
        
        # Post to Eir
        result = post_whisper(whisper)
        if result.get("ok"):
            print(f"    ✅ Created: {result.get('id', 'unknown')}")
            whispers_created += 1
        else:
            print(f"    ❌ Post failed: {result.get('error', 'Unknown error')}")
    
    print(f"\n✅ Done — {whispers_created} Whispers {'would be ' if args.dry_run else ''}created")


if __name__ == "__main__":
    main()
