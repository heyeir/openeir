"""
Shared Eir configuration loader and workspace resolver.

Workspace resolution (first match wins):
1. EIR_WORKSPACE env var
2. settings.json in skill's config/ dir → reads workspace_dir from it
3. Skill root directory (fallback for development)

Config resolution for Eir API credentials:
1. Environment variables (EIR_API_URL, EIR_API_KEY)
2. EIR_CONFIG env var pointing to a JSON file
3. <workspace>/config/eir.json
4. <skill_root>/config/eir.json
"""

import json
import os
from pathlib import Path

# Skill root: scripts/pipeline/eir_config.py → 3 levels up
SKILL_DIR = Path(__file__).resolve().parent.parent.parent


def resolve_workspace() -> Path:
    """Resolve the Eir workspace directory.

    The workspace holds config/, data/, and all runtime state.
    Resolution order:
      1. EIR_WORKSPACE env var (absolute path)
      2. workspace_dir field in <skill_root>/config/settings.json
      3. Skill root directory (development fallback)
    """
    # 1. Env var — highest priority
    env_ws = os.environ.get("EIR_WORKSPACE")
    if env_ws:
        return Path(env_ws).expanduser()

    # 2. Read from skill's settings.json
    settings_file = SKILL_DIR / "config" / "settings.json"
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text())
            ws = settings.get("workspace_dir")
            if ws:
                return Path(ws).expanduser()
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. Fallback: skill root (for development / pre-setup)
    return SKILL_DIR


# Module-level convenience — importable by all pipeline scripts
WORKSPACE = resolve_workspace()
CONFIG_DIR = WORKSPACE / "config"
DATA_DIR = WORKSPACE / "data"


def load_settings() -> dict:
    """Load settings.json from the resolved workspace."""
    settings_file = CONFIG_DIR / "settings.json"
    if settings_file.exists():
        try:
            return json.loads(settings_file.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def load_config() -> dict:
    """Load Eir API config from env vars or config file."""
    api_url = os.environ.get("EIR_API_URL")
    api_key = os.environ.get("EIR_API_KEY")
    if api_url and api_key:
        return {"apiUrl": api_url, "apiKey": api_key}

    # Fallback: config file
    for path in [
        Path(os.environ.get("EIR_CONFIG", "/dev/null")),
        CONFIG_DIR / "eir.json",
        SKILL_DIR / "config" / "eir.json",
    ]:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, KeyError):
                continue

    return {}


def get_api_url() -> str:
    config = load_config()
    return config.get("apiUrl", "").rstrip("/")


def get_api_key() -> str:
    config = load_config()
    key = config.get("apiKey")
    if not key:
        raise RuntimeError(
            "No API key found. Set EIR_API_KEY env var or create config/eir.json"
        )
    return key
