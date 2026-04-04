#!/usr/bin/env python3
"""
Deliver — Save content locally and send notifications.

Reads generated content files and:
1. Saves to local workspace/eir/ directory
2. Sends notification via user's default channel

In Eir mode, also runs post_content.py to push to Eir API.

Usage:
  python3 scripts/pipeline/deliver.py                  # deliver all pending
  python3 scripts/pipeline/deliver.py --file data/generated/ai-agents.json
  python3 scripts/pipeline/deliver.py --dry-run
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent.parent
DATA_DIR = WORKSPACE / "data"
GENERATED_DIR = DATA_DIR / "generated"
DELIVERED_DIR = DATA_DIR / "delivered"
CONFIG_DIR = WORKSPACE / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

# OpenClaw workspace
OPENCLAW_WORKSPACE = Path.home() / ".openclaw" / "workspace"


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {"mode": "standalone", "local_storage": "workspace/eir/"}


def get_local_storage_path(settings: dict) -> Path:
    """Get the local storage path, creating if needed."""
    storage = settings.get("local_storage", "workspace/eir/")
    
    # If it starts with "workspace/", use OpenClaw workspace
    if storage.startswith("workspace/"):
        path = OPENCLAW_WORKSPACE / storage.replace("workspace/", "")
    else:
        path = Path(storage)
    
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_message_standalone(content: dict) -> str:
    """Format content for standalone mode message."""
    title = content.get("title", "Untitled")
    summary = content.get("summary", "")
    source = content.get("source", {})
    source_name = source.get("name", "Unknown")
    source_url = source.get("url", "")
    published = source.get("published", "")
    
    # Format time
    time_str = ""
    if published:
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            diff = now - dt
            if diff.days > 0:
                time_str = f"{diff.days}d ago"
            elif diff.seconds >= 3600:
                time_str = f"{diff.seconds // 3600}h ago"
            else:
                time_str = f"{diff.seconds // 60}m ago"
        except Exception:
            time_str = ""
    
    via = f"via {source_name}"
    if time_str:
        via += f" · {time_str}"
    
    msg = f"📰 {title}\n\n{summary}\n\n{via}"
    if source_url:
        msg += f"\n🔗 {source_url}"
    
    return msg


def format_message_eir(content: dict) -> str:
    """Format content for Eir mode message."""
    dot = content.get("dot", {})
    l1 = content.get("l1", {})
    l2 = content.get("l2", {})
    sources = content.get("sources", [])
    
    hook = dot.get("hook", "")
    title = l1.get("title", "Untitled")
    summary = l1.get("summary", "")
    bullets = l1.get("bullets", [])
    via = l1.get("via", [])
    eir_take = l2.get("eir_take", "")
    
    msg = f"✨ {hook}\n\n**{title}**\n\n{summary}"
    
    if bullets:
        msg += "\n\n"
        for b in bullets[:3]:
            msg += f"• {b}\n"
    
    if eir_take:
        msg += f"\n💡 *Eir's Take*: {eir_take}"
    
    if via:
        msg += f"\n\nvia {', '.join(via[:2])}"
    
    if sources:
        msg += f"\n🔗 {sources[0].get('url', '')}"
    
    return msg


def send_notification(message: str, dry_run: bool = False) -> bool:
    """
    Send notification via OpenClaw message tool.
    
    Uses the default channel configured in OpenClaw.
    """
    if dry_run:
        print(f"  [dry-run] Would send:\n{message[:200]}...")
        return True
    
    try:
        # Use openclaw CLI to send message
        # This will use the user's default channel
        result = subprocess.run(
            ["openclaw", "message", "--send", message],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True
        else:
            print(f"  ⚠️ Message send failed: {result.stderr}")
            return False
    except FileNotFoundError:
        # openclaw CLI not available, try direct message
        print("  ⚠️ OpenClaw CLI not found, skipping notification")
        return False
    except Exception as e:
        print(f"  ⚠️ Notification failed: {e}")
        return False


def deliver_content(file_path: str, settings: dict, dry_run: bool = False) -> dict:
    """Deliver a single content file."""
    mode = settings.get("mode", "standalone")
    storage_path = get_local_storage_path(settings)
    
    # Load content
    content = json.loads(Path(file_path).read_text())
    slug = content.get("slug", Path(file_path).stem)
    
    result = {
        "slug": slug,
        "status": "ok",
        "local_path": None,
        "notified": False
    }
    
    # Save locally
    today = datetime.now().strftime("%Y-%m-%d")
    local_dir = storage_path / today
    local_dir.mkdir(parents=True, exist_ok=True)
    local_file = local_dir / f"{slug}.json"
    
    if not dry_run:
        shutil.copy(file_path, local_file)
        result["local_path"] = str(local_file)
        print(f"    📁 Saved to {local_file}")
    else:
        result["local_path"] = f"[dry-run] {local_file}"
    
    # Format and send notification
    if mode == "standalone":
        message = format_message_standalone(content)
    else:
        message = format_message_eir(content)
    
    result["notified"] = send_notification(message, dry_run=dry_run)
    
    # Move to delivered
    if not dry_run:
        DELIVERED_DIR.mkdir(parents=True, exist_ok=True)
        delivered_path = DELIVERED_DIR / Path(file_path).name
        os.rename(file_path, delivered_path)
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Deliver content locally + notify")
    parser.add_argument("--file", help="Deliver a single file")
    parser.add_argument("--dry-run", action="store_true", help="Preview without delivering")
    args = parser.parse_args()
    
    settings = load_settings()
    mode = settings.get("mode", "standalone")
    
    print(f"📤 Deliver ({mode} mode)")
    
    # Get files to deliver
    if args.file:
        files = [args.file]
    else:
        files = sorted(glob.glob(str(GENERATED_DIR / "*.json")))
    
    if not files:
        print("  No content to deliver")
        return
    
    print(f"  Delivering {len(files)} item(s)...")
    
    results = []
    for f in files:
        slug = Path(f).stem
        print(f"  → {slug}")
        result = deliver_content(f, settings, dry_run=args.dry_run)
        results.append(result)
    
    # In Eir mode, also run post_content.py
    if mode == "eir" and not args.dry_run:
        print("\n  Running Eir post_content...")
        try:
            subprocess.run(
                ["python3", str(WORKSPACE / "scripts" / "pipeline" / "post_content.py")],
                cwd=WORKSPACE,
                check=True
            )
        except Exception as e:
            print(f"  ⚠️ post_content failed: {e}")
    
    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    notified = sum(1 for r in results if r.get("notified"))
    print(f"\n✅ {ok} delivered, {notified} notified")


if __name__ == "__main__":
    main()
