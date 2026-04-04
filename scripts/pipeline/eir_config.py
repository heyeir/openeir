"""
Shared Eir configuration loader.

Config resolution order:
1. Environment variables (EIR_API_URL, EIR_API_KEY)
2. Custom config file (EIR_CONFIG env var)
3. config/eir.json (relative to skill root)
4. ~/.openclaw/skills/eir/config.json (legacy fallback)
"""

import json
import os
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent  # skill root
DATA_DIR = WORKSPACE / "data"


def load_config():
    """Load Eir config from env vars or config file."""
    api_url = os.environ.get("EIR_API_URL")
    api_key = os.environ.get("EIR_API_KEY")
    if api_url and api_key:
        return {"apiUrl": api_url, "apiKey": api_key}

    # Fallback: config file
    for path in [
        Path(os.environ.get("EIR_CONFIG", "")),
        WORKSPACE / "config" / "eir.json",
        Path.home() / ".openclaw" / "skills" / "eir" / "config.json",
    ]:
        if path.exists():
            return json.loads(path.read_text())

    return {}


def get_api_url():
    config = load_config()
    return config.get("apiUrl", "").rstrip("/")


def get_api_key():
    config = load_config()
    key = config.get("apiKey")
    if not key:
        raise RuntimeError(
            "No API key found. Set EIR_API_KEY env var or create config/eir.json"
        )
    return key
