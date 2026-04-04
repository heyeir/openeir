#!/usr/bin/env python3
"""
Eir Daily Content Curator — Interactive Setup Wizard

Guides new users through initial configuration.
Run this after installing the skill to set up your workspace.

Usage:
  python3 scripts/setup.py              # Interactive setup
  python3 scripts/setup.py --check      # Verify current setup
  python3 scripts/setup.py --mode=eir   # Auto-select mode
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple, Literal

# === Paths ===
# Skill root is where this script lives
SKILL_DIR = Path(__file__).resolve().parent.parent

# Default workspace is under user's OpenClaw directory
DEFAULT_WORKSPACE = Path.home() / ".openclaw" / "skills" / "eir"

# === Mode Descriptions ===
MODE_DESCRIPTIONS = {
    "standalone": """
Standalone Mode — Simple RSS curation
• Reads RSS feeds based on your interests
• Delivers content directly via OpenClaw
• Optional: web search with Tavily/Brave APIs
• No Eir account needed
""",
    "eir": """
Eir Mode — Full AI-powered curation (requires heyeir.com account)
• Personalized content based on your interest profile
• Multi-source synthesis and deep-dive analysis
• Automatic interest learning from conversations
• Beautiful reading experience in Eir app
• Requires: Eir account + API connection
"""
}


def print_step(n: int, title: str):
    print(f"\n{'='*60}")
    print(f"Step {n}: {title}")
    print('='*60)


def input_default(prompt: str, default: str) -> str:
    response = input(f"{prompt} [{default}]: ").strip()
    return response if response else default


def input_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    response = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not response:
        return default
    return response in ('y', 'yes', 'true', '1')


def input_choice(prompt: str, choices: list, default: int = 0) -> int:
    """Ask user to select from numbered choices."""
    print()
    for i, choice in enumerate(choices, 1):
        marker = " (default)" if i - 1 == default else ""
        print(f"  {i}. {choice}{marker}")
    while True:
        response = input(f"\n{prompt} [{default + 1}]: ").strip()
        if not response:
            return default
        try:
            idx = int(response) - 1
            if 0 <= idx < len(choices):
                return idx
        except ValueError:
            pass
        print("  Please enter a valid number.")


def detect_eir_connection(workspace: Path) -> Optional[Dict]:
    """Check if Eir is already connected in this workspace."""
    eir_config = workspace / "config" / "eir.json"
    if eir_config.exists():
        try:
            return json.loads(eir_config.read_text())
        except:
            pass
    return None


def setup_workspace() -> Path:
    """Determine and create workspace directory."""
    print_step(1, "Workspace Setup")
    
    print(f"Skill location: {SKILL_DIR}")
    print(f"\nWhere should your Eir workspace be?")
    print(f"  (This is where config, data, and caches will be stored)")
    
    # Default to ~/.openclaw/skills/eir
    workspace = DEFAULT_WORKSPACE
    response = input(f"\nWorkspace path [{workspace}]: ").strip()
    if response:
        workspace = Path(response).expanduser()
    
    # Create directories
    config_dir = workspace / "config"
    data_dir = workspace / "data"
    
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n✓ Workspace: {workspace}")
    print(f"✓ Config: {config_dir}")
    print(f"✓ Data: {data_dir}")
    
    return workspace


def choose_mode(workspace: Path, auto_mode: Optional[str] = None) -> Literal["standalone", "eir"]:
    """Ask user to choose mode, or auto-detect."""
    print_step(2, "Choose Mode")
    
    # Check if already connected
    existing = detect_eir_connection(workspace)
    if existing:
        print(f"✓ Found existing Eir connection:")
        print(f"  User ID: {existing.get('userId', '?')}")
        print(f"  Connected: {existing.get('connectedAt', '?')[:10]}")
        if input_yes_no("Use Eir mode?", default=True):
            return "eir"
    
    if auto_mode:
        return auto_mode
    
    # Show mode descriptions
    print("\n" + MODE_DESCRIPTIONS["standalone"])
    print(MODE_DESCRIPTIONS["eir"])
    
    modes = ["standalone", "eir"]
    choice = input_choice("Select mode", modes, default=0)
    return modes[choice]


def setup_standalone(workspace: Path) -> Dict:
    """Configure standalone mode."""
    print_step(3, "Standalone Configuration")
    
    print("\nStandalone mode uses local RSS feeds + optional web search.")
    print("No Eir account or API keys needed.\n")
    
    settings = {
        "mode": "standalone",
        "max_items_per_day": 5,
        "local_storage": str(workspace / "data"),
        "rss_sources": str(workspace / "config" / "sources.json"),
        "cron": {
            "schedule": "0 8 * * *",
            "timezone": "UTC"
        },
        "search": {
            "providers": [],
            "tavily_api_key": None,
            "brave_api_key": None
        }
    }
    
    # Language
    lang = input_default("Content language (zh/en)", "zh")
    settings["language"] = lang
    
    # Timezone
    try:
        import tzlocal
        local_tz = str(tzlocal.get_localzone())
    except:
        local_tz = "UTC"
    tz = input_default("Timezone", local_tz)
    settings["cron"]["timezone"] = tz
    
    # Max items
    max_items = input_default("Max items per day", "5")
    settings["max_items_per_day"] = int(max_items)
    
    # Optional search
    if input_yes_no("\nEnable web search? (requires Tavily or Brave API key)", default=False):
        print("\nGet API key from:")
        print("  Tavily: https://tavily.com (recommended)")
        print("  Brave: https://brave.com/search/api/")
        
        provider = input_default("Provider (tavily/brave)", "tavily")
        api_key = input("API key: ").strip()
        
        settings["search"]["providers"] = [provider]
        settings["search"][f"{provider}_api_key"] = api_key
    
    return settings


def setup_eir(workspace: Path) -> Dict:
    """Configure Eir mode."""
    print_step(3, "Eir Configuration")
    
    print("\nEir mode connects to heyeir.com for personalized curation.")
    print("You need an Eir account and a pairing code.\n")
    
    settings = {
        "mode": "eir",
        "max_items_per_day": 10,
        "local_storage": str(workspace / "data"),
        "rss_sources": str(workspace / "config" / "sources.json"),
        "cron": {
            "schedule": "0 8 * * *",
            "timezone": "UTC"
        },
        "search": {
            "providers": ["searxng"],
            "searxng_url": "http://localhost:8888",
            "crawl4ai_url": "http://localhost:11235",
            "search_gateway_url": "http://localhost:8899"
        },
        "eir": {
            "api_key": None,
            "bilingual": False,
            "sync_interests": True,
            "post_content": True,
            "extract_whispers": True
        }
    }
    
    # Check existing connection
    existing = detect_eir_connection(workspace)
    if not existing:
        print("⚠ Not connected to Eir yet.")
        print("\nTo connect:")
        print("  1. Open Eir app → Settings → Connect OpenClaw")
        print("  2. Get a pairing code")
        print("  3. Run: node scripts/connect.mjs <CODE>")
        
        if input_yes_no("\nDo you have a pairing code now?", default=False):
            code = input("Enter pairing code: ").strip()
            if code:
                # Run connect.mjs
                env = os.environ.copy()
                env["EIR_API_URL"] = "https://api.heyeir.com"
                try:
                    result = subprocess.run(
                        ["node", str(SKILL_DIR / "scripts" / "connect.mjs"), code],
                        capture_output=True,
                        text=True,
                        env=env,
                        cwd=str(workspace)
                    )
                    if result.returncode == 0:
                        print("✓ Connected to Eir")
                        existing = detect_eir_connection(workspace)
                    else:
                        print(f"✗ Connection failed: {result.stderr}")
                except FileNotFoundError:
                    print("✗ Node.js not found. Please install Node.js.")
        else:
            print("\nYou can connect later by running:")
            print(f"  cd {workspace}")
            print(f"  node {SKILL_DIR}/scripts/connect.mjs <CODE>")
    
    if existing:
        settings["eir"]["api_key"] = existing.get("apiKey")
    
    # Language preferences
    print("\n--- Content Preferences ---")
    
    lang = input_default("Primary content language (zh/en)", "zh")
    settings["eir"]["primary_language"] = lang
    
    bilingual = input_yes_no("Generate bilingual content (zh+en)?", default=False)
    settings["eir"]["bilingual"] = bilingual
    
    # Timezone
    try:
        import tzlocal
        local_tz = str(tzlocal.get_localzone())
    except:
        local_tz = "UTC"
    tz = input_default("Timezone", local_tz)
    settings["cron"]["timezone"] = tz
    
    # Infrastructure check
    print("\n--- Infrastructure Check ---")
    print("Eir mode works best with local search infrastructure:")
    print("  • SearXNG (localhost:8888) — meta-search")
    print("  • Crawl4AI (localhost:11235) — article extraction")
    print("  • Search Gateway (localhost:8899) — search routing")
    
    if not input_yes_no("\nHave you set up these services?", default=False):
        print("\nSee: references/infrastructure-setup.md")
        print("Or run with default settings (will use fallback APIs)")
    
    return settings


def save_settings(workspace: Path, settings: Dict):
    """Save settings to workspace."""
    settings_file = workspace / "config" / "settings.json"
    try:
        settings_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
        print(f"\n✓ Saved settings to {settings_file}")
    except Exception as e:
        print(f"\n✗ Failed to save settings: {e}")
        raise


def create_sources_json(workspace: Path):
    """Copy default sources.json if not exists."""
    sources_file = workspace / "config" / "sources.json"
    if not sources_file.exists():
        # Copy from skill
        skill_sources = SKILL_DIR / "config" / "sources.json"
        if skill_sources.exists():
            import shutil
            shutil.copy(skill_sources, sources_file)
            print(f"✓ Copied default RSS sources to {sources_file}")


def print_summary(workspace: Path, mode: str, settings: Dict):
    """Print setup summary and next steps."""
    print_step(4, "Setup Complete")
    
    print(f"\nWorkspace: {workspace}")
    print(f"Mode: {mode}")
    
    if mode == "standalone":
        print(f"\nNext steps:")
        print(f"  1. Test: python3 {SKILL_DIR}/scripts/standalone/curate.py")
        print(f"  2. Add cron: openclaw cron add --name 'daily-curate' --cron '0 8 * * *' ...")
    else:
        print(f"\nNext steps:")
        if not settings["eir"].get("api_key"):
            print(f"  1. Connect Eir: node {SKILL_DIR}/scripts/connect.mjs <CODE>")
        print(f"  2. Test: python3 {SKILL_DIR}/scripts/pipeline/daily_plan.py")
        print(f"  3. See SKILL.md for full pipeline cron setup")
    
    print(f"\nConfig files:")
    print(f"  Settings: {workspace}/config/settings.json")
    print(f"  Sources:  {workspace}/config/sources.json")
    if mode == "eir":
        print(f"  Eir:      {workspace}/config/eir.json")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Eir Content Curator Setup")
    parser.add_argument("--check", action="store_true", help="Verify current setup")
    parser.add_argument("--mode", choices=["standalone", "eir"], help="Auto-select mode")
    args = parser.parse_args()
    
    print("="*60)
    print("Eir Daily Content Curator — Setup")
    print("="*60)
    
    if args.check:
        # Just verify
        ws = DEFAULT_WORKSPACE
        print(f"\nWorkspace: {ws}")
        print(f"Exists: {ws.exists()}")
        if (ws / "config" / "settings.json").exists():
            s = json.loads((ws / "config" / "settings.json").read_text())
            print(f"Mode: {s.get('mode', '?')}")
        return
    
    # Step 1: Workspace
    workspace = setup_workspace()
    
    # Step 2: Choose mode
    mode = choose_mode(workspace, auto_mode=args.mode)
    
    # Step 3: Configure based on mode
    if mode == "standalone":
        settings = setup_standalone(workspace)
    else:
        settings = setup_eir(workspace)
    
    # Step 4: Save
    save_settings(workspace, settings)
    create_sources_json(workspace)
    
    # Summary
    print_summary(workspace, mode, settings)


if __name__ == "__main__":
    main()
