#!/usr/bin/env python3
"""
Extract interests from OpenClaw conversation logs.
Updates ~/.openclaw/curator/config.json with discovered topics.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set
import re

# ─── Config ───────────────────────────────────────────────────────────────────

CONFIG_DIR = Path.home() / ".openclaw" / "curator"
CONFIG_FILE = CONFIG_DIR / "config.json"
OPENCLAW_DIR = Path.home() / ".openclaw"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def find_conversation_logs() -> List[Path]:
    """Find recent OpenClaw conversation/session logs."""
    logs = []
    
    # Check common log locations
    candidates = [
        OPENCLAW_DIR / "sessions",
        OPENCLAW_DIR / "logs",
        OPENCLAW_DIR / "conversations",
        OPENCLAW_DIR / "workspace" / ".sessions",
    ]
    
    cutoff = datetime.now() - timedelta(days=7)
    
    for candidate in candidates:
        if candidate.exists():
            for f in candidate.rglob("*.json"):
                try:
                    if f.stat().st_mtime > cutoff.timestamp():
                        logs.append(f)
                except:
                    pass
            for f in candidate.rglob("*.md"):
                try:
                    if f.stat().st_mtime > cutoff.timestamp():
                        logs.append(f)
                except:
                    pass
    
    return logs

def extract_user_messages(log_path: Path) -> List[str]:
    """Extract user messages from a log file."""
    messages = []
    content = log_path.read_text(errors="replace")
    
    if log_path.suffix == ".json":
        try:
            data = json.loads(content)
            # Handle various log formats
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("role") == "user":
                        messages.append(item.get("content", ""))
            elif isinstance(data, dict):
                for msg in data.get("messages", []):
                    if msg.get("role") == "user":
                        messages.append(msg.get("content", ""))
        except:
            pass
    else:
        # Markdown format - look for user messages
        # Common patterns: "User:", "Human:", "> "
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("User:") or line.startswith("Human:"):
                messages.append(line.split(":", 1)[-1].strip())
    
    return messages

def extract_topics_simple(messages: List[str]) -> Set[str]:
    """
    Simple topic extraction without LLM.
    Looks for repeated nouns, technical terms, etc.
    """
    topics = set()
    
    # Common tech/interest patterns
    patterns = [
        r'\b(AI|ML|LLM|GPT|Claude|Gemini)\b',
        r'\b(Python|JavaScript|TypeScript|Rust|Go|Java)\b',
        r'\b(React|Vue|Next\.?js|Node\.?js)\b',
        r'\b(Docker|Kubernetes|AWS|Azure|GCP)\b',
        r'\b(产品|设计|开发|架构|系统)\b',
        r'\b(机器学习|深度学习|人工智能|自然语言处理)\b',
        r'\b(startup|创业|融资|投资)\b',
    ]
    
    combined = " ".join(messages)
    
    for pattern in patterns:
        matches = re.findall(pattern, combined, re.IGNORECASE)
        topics.update(m.lower() if isinstance(m, str) else m[0].lower() for m in matches)
    
    # Normalize
    topic_map = {
        "ai": "AI",
        "ml": "Machine Learning",
        "llm": "LLM",
        "gpt": "AI",
        "claude": "AI",
        "gemini": "AI",
        "python": "Python",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "rust": "Rust",
        "react": "React",
        "next.js": "Next.js",
        "nextjs": "Next.js",
        "node.js": "Node.js",
        "nodejs": "Node.js",
        "docker": "DevOps",
        "kubernetes": "DevOps",
        "产品": "产品设计",
        "设计": "产品设计",
        "机器学习": "机器学习",
        "深度学习": "机器学习",
        "人工智能": "AI",
        "startup": "创业",
        "创业": "创业",
    }
    
    normalized = set()
    for t in topics:
        normalized.add(topic_map.get(t.lower(), t))
    
    return normalized

def detect_language(messages: List[str]) -> str:
    """Detect primary language from messages."""
    combined = " ".join(messages)
    # Simple heuristic: count Chinese characters
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', combined))
    total_chars = len(combined)
    
    if total_chars == 0:
        return "en"
    
    chinese_ratio = chinese_chars / total_chars
    return "zh" if chinese_ratio > 0.1 else "en"

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Scanning conversation logs...", file=sys.stderr)
    
    logs = find_conversation_logs()
    if not logs:
        print("No recent conversation logs found.", file=sys.stderr)
        print("Checked: ~/.openclaw/sessions, ~/.openclaw/logs, etc.", file=sys.stderr)
        return
    
    print(f"Found {len(logs)} log files", file=sys.stderr)
    
    all_messages = []
    for log in logs:
        messages = extract_user_messages(log)
        all_messages.extend(messages)
    
    if not all_messages:
        print("No user messages found in logs.", file=sys.stderr)
        return
    
    print(f"Extracted {len(all_messages)} user messages", file=sys.stderr)
    
    # Extract topics
    topics = extract_topics_simple(all_messages)
    language = detect_language(all_messages)
    
    if not topics:
        print("No topics detected. You may need to add interests manually.", file=sys.stderr)
        return
    
    print(f"Detected topics: {topics}", file=sys.stderr)
    print(f"Detected language: {language}", file=sys.stderr)
    
    # Update config
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text())
    else:
        config = {"interests": [], "language": "zh", "max_items": 5, "sources": []}
    
    # Merge interests (don't overwrite)
    existing = set(config.get("interests", []))
    merged = existing | topics
    config["interests"] = sorted(merged)
    config["language"] = language
    
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    
    print(f"\nUpdated {CONFIG_FILE}", file=sys.stderr)
    print(f"Interests: {config['interests']}", file=sys.stderr)

if __name__ == "__main__":
    main()
