#!/usr/bin/env python3
"""
Eir Daily Content Curator — Interactive Setup Wizard

Guides new users through initial configuration:
1. Detects or creates config directory
2. Checks Eir connection status
3. Guides through pairing (if needed)
4. Configures mode (standalone vs eir)
5. Sets user preferences (language, timezone, bilingual)
6. Verifies infrastructure services
7. Creates default cron schedule

Usage:
  python3 scripts/setup.py              # Interactive setup
  python3 scripts/setup.py --check      # Just verify current setup
  python3 scripts/setup.py --auto       # Non-interactive, use defaults
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

# === Paths ===
WORKSPACE = Path(__file__).resolve().parent.parent
CONFIG_DIR = WORKSPACE / "config"
DATA_DIR = WORKSPACE / "data"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
EIR_CONFIG_FILE = CONFIG_DIR / "eir.json"
SOURCES_FILE = CONFIG_DIR / "sources.json"

# === Defaults ===
DEFAULT_SETTINGS = {
    "mode": "standalone",
    "max_items_per_day": 10,
    "local_storage": "data/",
    "api_url": None,
    "search": {
        "providers": ["searxng"],
        "searxng_url": "http://localhost:8888",
        "crawl4ai_url": "http://localhost:11235",
        "search_gateway_url": "http://localhost:8899"
    },
    "rss_sources": "config/sources.json",
    "cron": {
        "schedule": "0 8 * * *",
        "timezone": "UTC"
    },
    "eir": {
        "api_key": None,
        "bilingual": False,
        "sync_interests": True,
        "post_content": True,
        "extract_whispers": True
    }
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


def check_service(url: str, timeout: int = 5) -> Tuple[bool, str]:
    """Check if a service is running."""
    import urllib.request
    try:
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except Exception as e:
        return False, str(e)


def detect_eir_connection() -> Optional[Dict]:
    """Check if Eir is already connected."""
    if EIR_CONFIG_FILE.exists():
        try:
            return json.loads(EIR_CONFIG_FILE.read_text())
        except:
            pass
    return None


def check_infrastructure() -> Dict[str, Tuple[bool, str]]:
    """Check all infrastructure services."""
    services = {
        "SearXNG (search)": "http://localhost:8888",
        "Crawl4AI (crawl)": "http://localhost:11235/health",
        "Search Gateway": "http://localhost:8899/search?q=test&limit=1"
    }
    results = {}
    for name, url in services.items():
        ok, msg = check_service(url)
        results[name] = (ok, msg)
    return results


def setup_config_directory():
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✓ Config directory: {CONFIG_DIR}")
    print(f"✓ Data directory: {DATA_DIR}")


def setup_eir_connection(auto: bool = False) -> bool:
    """Guide user through Eir connection."""
    existing = detect_eir_connection()
    if existing:
        print(f"✓ Already connected to Eir")
        print(f"  User ID: {existing.get('userId', '?')}")
        print(f"  Connected at: {existing.get('connectedAt', '?')}")
        return True
    
    if auto:
        print("⚠ Not connected to Eir (skipping in --auto mode)")
        return False
    
    print("\nTo connect to Eir (heyeir.com), you need a pairing code.")
    print("Get one from: Eir App → Settings → Connect OpenClaw")
    
    if not input_yes_no("Do you have a pairing code?", default=False):
        print("\nYou can connect later by running:")
        print("  node scripts/connect.mjs <PAIRING_CODE>")
        return False
    
    code = input("Enter pairing code: ").strip()
    if not code:
        print("⚠ No code provided, skipping connection")
        return False
    
    # Run connect.mjs
    api_url = os.environ.get("EIR_API_URL", "https://api.heyeir.com")
    env = os.environ.copy()
    env["EIR_API_URL"] = api_url
    
    try:
        result = subprocess.run(
            ["node", str(WORKSPACE / "scripts" / "connect.mjs"), code],
            capture_output=True,
            text=True,
            env=env
        )
        if result.returncode == 0:
            print("✓ Successfully connected to Eir")
            return True
        else:
            print(f"✗ Connection failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print("✗ Node.js not found. Please install Node.js or connect manually:")
        print(f"  EIR_API_URL={api_url} node scripts/connect.mjs {code}")
        return False


def setup_settings(auto: bool = False) -> Dict:
    """Create or update settings.json."""
    settings = DEFAULT_SETTINGS.copy()
    
    if SETTINGS_FILE.exists():
        try:
            existing = json.loads(SETTINGS_FILE.read_text())
            settings.update(existing)
            print(f"✓ Loaded existing settings from {SETTINGS_FILE}")
        except:
            print(f"⚠ Could not parse existing settings, using defaults")
    
    # Auto-detect mode based on Eir connection
    eir_connected = detect_eir_connection() is not None
    if eir_connected and settings.get("mode") == "standalone":
        print(f"\n⚠ Detected Eir connection but mode is 'standalone'")
        if auto or input_yes_no("Switch to 'eir' mode?", default=True):
            settings["mode"] = "eir"
            print("✓ Switched to 'eir' mode")
    
    if not auto:
        print("\n--- Content Preferences ---")
        
        # Language
        current_lang = settings.get("eir", {}).get("primary_language", "zh")
        lang = input_default("Primary content language (zh/en)", current_lang)
        if "eir" not in settings:
            settings["eir"] = {}
        settings["eir"]["primary_language"] = lang
        
        # Bilingual
        current_bilingual = settings.get("eir", {}).get("bilingual", False)
        bilingual = input_yes_no("Generate bilingual content (zh+en)?", current_bilingual)
        settings["eir"]["bilingual"] = bilingual
        
        # Timezone
        import tzlocal
        local_tz = tzlocal.get_localzone().key if hasattr(tzlocal.get_localzone(), 'key') else str(tzlocal.get_localzone())
        tz = input_default("Timezone", settings.get("cron", {}).get("timezone", local_tz))
        settings["cron"]["timezone"] = tz
        
        # Schedule
        current_schedule = settings.get("cron", {}).get("schedule", "0 8 * * *")
        print(f"\nCron schedule format: minute hour day month weekday")
        print(f"Example: '0 8 * * *' = 8:00 AM daily")
        schedule = input_default("Content delivery schedule", current_schedule)
        settings["cron"]["schedule"] = schedule
    
    # Write settings
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
    print(f"✓ Saved settings to {SETTINGS_FILE}")
    return settings


def setup_infrastructure_guide(auto: bool = False):
    """Check and report infrastructure status."""
    print_step(4, "Infrastructure Check")
    print("Checking local services...")
    
    results = check_infrastructure()
    all_ok = True
    for name, (ok, msg) in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {name}: {msg if not ok else 'OK'}")
        if not ok:
            all_ok = False
    
    if not all_ok:
        print("\n⚠ Some services are not running. For full pipeline:")
        print("  1. SearXNG: docker run -p 8888:8080 searxng/searxng")
        print("  2. Crawl4AI: docker run -p 11235:11235 unclecode/crawl4ai")
        print("  3. Search Gateway: See references/infrastructure-setup.md")
        
        if not auto:
            if input_yes_no("Continue anyway? (pipeline will use fallback APIs)", default=True):
                print("✓ Continuing with fallback mode")
            else:
                print("Setup paused. Start services and re-run setup.py")
                sys.exit(0)
    else:
        print("✓ All infrastructure services are running")
    
    return results


def setup_cron_jobs(settings: Dict, auto: bool = False):
    """Set up cron jobs for the pipeline."""
    print_step(5, "Cron Schedule")
    
    mode = settings.get("mode", "standalone")
    tz = settings.get("cron", {}).get("timezone", "UTC")
    
    if mode == "eir":
        print("Eir mode detected. Recommended cron jobs:")
        print("  1. daily-plan: 0 4 * * * (generate daily content plan)")
        print("  2. rss-crawler: 0 5,11,17,23 * * * (fetch RSS 4x/day)")
        print("  3. search-harvest: 0 6,9,12,15,18,21 * * * (search 6x/day)")
        print("  4. generate-post: 0 7,15,21 * * * (generate & post content)")
        
        if not auto and input_yes_no("Add these cron jobs?", default=True):
            # This would call openclaw cron add commands
            print("✓ Cron jobs would be added here (requires openclaw CLI)")
            print("  Run: openclaw cron add --name 'eir-daily-plan' --cron '0 4 * * *' ...")
        else:
            print("⚠ Skipped cron setup. Add manually later with 'openclaw cron add'")
    else:
        print("Standalone mode. Recommended cron:")
        print("  daily-curate: 0 8 * * * (once daily)")
        
        if not auto and input_yes_no("Add cron job?", default=False):
            print("✓ Would add: openclaw cron add --name 'daily-curate' --cron '0 8 * * *' ...")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Eir Content Curator Setup")
    parser.add_argument("--check", action="store_true", help="Just verify setup")
    parser.add_argument("--auto", action="store_true", help="Non-interactive mode")
    args = parser.parse_args()
    
    print("="*60)
    print("Eir Daily Content Curator — Setup Wizard")
    print("="*60)
    
    if args.check:
        print("\n--- Configuration Check ---")
        setup_config_directory()
        eir = detect_eir_connection()
        print(f"Eir connection: {'✓ Yes' if eir else '✗ No'}")
        if eir:
            print(f"  User ID: {eir.get('userId')}")
        check_infrastructure()
        sys.exit(0)
    
    # Step 1: Config directory
    print_step(1, "Configuration Directory")
    setup_config_directory()
    
    # Step 2: Eir connection
    print_step(2, "Eir Connection")
    setup_eir_connection(auto=args.auto)
    
    # Step 3: Settings
    print_step(3, "Content Preferences")
    settings = setup_settings(auto=args.auto)
    
    # Step 4: Infrastructure
    setup_infrastructure_guide(auto=args.auto)
    
    # Step 5: Cron
    if not args.auto:
        setup_cron_jobs(settings, auto=args.auto)
    
    print("\n" + "="*60)
    print("Setup complete!")
    print("="*60)
    print(f"\nNext steps:")
    print(f"  1. Review config: cat {SETTINGS_FILE}")
    print(f"  2. Test run: python3 scripts/standalone/curate.py")
    if settings.get("mode") == "eir":
        print(f"  3. Run pipeline: python3 scripts/pipeline/daily_plan.py")
    print(f"\nFor help: See SKILL.md and references/infrastructure-setup.md")


if __name__ == "__main__":
    main()