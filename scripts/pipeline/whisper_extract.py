#!/usr/bin/env python3
"""
Whisper Extract — Extract insights from conversations and generate shareable essays.

Analyzes OpenClaw conversations to find:
- Interesting opinions and perspectives
- Realizations and "aha moments"
- Recurring themes and patterns

Then generates polished mini-essays (Whispers) that can be shared via Eir.

Usage:
  python3 scripts/pipeline/whisper_extract.py              # extract from recent conversations
  python3 scripts/pipeline/whisper_extract.py --days 7     # last 7 days
  python3 scripts/pipeline/whisper_extract.py --post       # also post to Eir
  python3 scripts/pipeline/whisper_extract.py --dry-run    # preview without posting
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

WORKSPACE = Path(__file__).parent.parent.parent
CONFIG_DIR = WORKSPACE / "config"
DATA_DIR = WORKSPACE / "data"
WHISPERS_DIR = DATA_DIR / "whispers"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
EIR_CONFIG = CONFIG_DIR / "eir.json"

OPENCLAW_DIR = Path.home() / ".openclaw"
SESSIONS_DIR = OPENCLAW_DIR / "sessions"

sys.path.insert(0, str(Path(__file__).parent))
from eir_config import load_config as _load_eir_config, get_api_url, get_api_key


def load_settings() -> Dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {"mode": "standalone"}


def load_eir_api_key() -> Optional[str]:
    if EIR_CONFIG.exists():
        config = json.loads(EIR_CONFIG.read_text())
        return config.get("apiKey")
    return None


def get_recent_conversations(days: int = 3) -> List[Dict]:
    """Get recent conversations with substantial user messages."""
    conversations = []
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    if not SESSIONS_DIR.exists():
        return conversations
    
    for session_file in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(session_file.read_text())
            
            updated = data.get("updatedAt", data.get("createdAt", ""))
            if updated:
                try:
                    updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00")).replace(tzinfo=None)
                    if updated_dt < cutoff:
                        continue
                except Exception:
                    pass
            
            messages = data.get("messages", [])
            # Only include conversations with substantial user content
            user_messages = [m for m in messages if m.get("role") == "user" and len(m.get("content", "")) > 100]
            
            if user_messages:
                conversations.append({
                    "id": session_file.stem,
                    "messages": messages,
                    "user_messages": user_messages,
                    "updated": updated
                })
        except Exception as e:
            print(f"  ⚠️ Failed to read {session_file.name}: {e}")
    
    return conversations


def identify_whisper_candidates(conversations: List[Dict]) -> List[Dict]:
    """
    Identify conversation segments that could become Whispers.
    
    Looks for:
    - Strong opinions ("I think...", "In my view...")
    - Realizations ("I realized...", "It occurred to me...")
    - Questions that reveal thinking ("Why is it that...")
    - Conclusions after discussion
    """
    candidates = []
    
    opinion_patterns = [
        r"I think\b",
        r"I believe\b",
        r"In my (view|opinion)\b",
        r"我认为",
        r"我觉得",
        r"我的观点",
    ]
    
    realization_patterns = [
        r"I (just )?(realized|noticed)\b",
        r"It (occurred|dawned) on me\b",
        r"(Actually|Interestingly)\b",
        r"我(刚)?发现",
        r"原来",
        r"其实",
    ]
    
    for conv in conversations:
        for msg in conv.get("user_messages", []):
            content = msg.get("content", "")
            
            # Check for patterns
            has_opinion = any(re.search(p, content, re.IGNORECASE) for p in opinion_patterns)
            has_realization = any(re.search(p, content, re.IGNORECASE) for p in realization_patterns)
            
            # Minimum length for substantial thought
            if (has_opinion or has_realization) and len(content) > 150:
                candidates.append({
                    "conversation_id": conv["id"],
                    "content": content,
                    "type": "opinion" if has_opinion else "realization",
                    "updated": conv.get("updated")
                })
    
    return candidates


def generate_whisper_essay(candidate: Dict, context: List[Dict]) -> Optional[Dict]:
    """
    Generate a polished mini-essay from a conversation insight.
    
    This is a placeholder — in production, would use LLM to:
    1. Expand and polish the thought
    2. Add structure and flow
    3. Make it shareable without losing the personal voice
    """
    content = candidate.get("content", "")
    
    # Extract the core insight (simplified)
    # In production, this would use LLM
    lines = content.split("\n")
    hook = lines[0][:50] if lines else "A thought"
    
    # For now, just structure the raw content
    return {
        "dot": {
            "hook": hook
        },
        "l1": {
            "title": hook,
            "summary": content[:200] + "..." if len(content) > 200 else content,
            "insight": ""
        },
        "l2": {
            "content": content,
            "context": f"From a conversation on {candidate.get('updated', 'recently')}"
        },
        "conversationId": candidate.get("conversation_id"),
        "type": candidate.get("type", "thought"),
        "extractedAt": datetime.utcnow().isoformat() + "Z"
    }


def post_whispers_to_eir(whispers: List[Dict], api_key: str) -> Dict:
    """Post whispers to Eir API."""
    payload = json.dumps({"items": whispers}).encode()
    
    req = urllib.request.Request(
        f"{get_api_url()}/api/oc/whispers",
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
        return {"error": str(e), "body": body}
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Whisper Extract")
    parser.add_argument("--days", type=int, default=3, help="Days of history")
    parser.add_argument("--post", action="store_true", help="Post to Eir")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()
    
    settings = load_settings()
    mode = settings.get("mode", "standalone")
    
    if mode != "eir":
        print("❌ Whisper extraction requires Eir mode")
        print("   Run: /curate --mode eir")
        sys.exit(1)
    
    api_key = load_eir_api_key()
    if not api_key:
        print("❌ Eir API key not found")
        print("   Run: /curate --connect <code>")
        sys.exit(1)
    
    print(f"💭 Whisper Extract")
    
    # Get conversations
    print(f"  Loading conversations from last {args.days} days...")
    conversations = get_recent_conversations(days=args.days)
    print(f"  Found {len(conversations)} conversations")
    
    if not conversations:
        print("  No conversations to analyze")
        return
    
    # Find candidates
    candidates = identify_whisper_candidates(conversations)
    print(f"  Found {len(candidates)} potential whispers")
    
    if not candidates:
        print("  No whisper candidates found")
        return
    
    # Generate whispers
    whispers = []
    for c in candidates[:5]:  # Limit to 5 per run
        whisper = generate_whisper_essay(c, conversations)
        if whisper:
            whispers.append(whisper)
    
    print(f"  Generated {len(whispers)} whispers")
    
    # Save locally
    WHISPERS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    
    for i, w in enumerate(whispers):
        filename = f"{today}_{i:02d}.json"
        filepath = WHISPERS_DIR / filename
        filepath.write_text(json.dumps(w, indent=2, ensure_ascii=False))
        print(f"    📝 {filepath.name}: {w['dot']['hook'][:30]}...")
    
    # Post to Eir
    if args.post and not args.dry_run:
        print("\n  Posting to Eir...")
        result = post_whispers_to_eir(whispers, api_key)
        if result.get("ok"):
            print(f"  ✅ Posted {result.get('created', len(whispers))} whispers")
        else:
            print(f"  ❌ Post failed: {result}")
    elif args.dry_run:
        print("\n  [dry-run] Would post to Eir")
    
    print(f"\n✅ Done — {len(whispers)} whispers extracted")


if __name__ == "__main__":
    main()
