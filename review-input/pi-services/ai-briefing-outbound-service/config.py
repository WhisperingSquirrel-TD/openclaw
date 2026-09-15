from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config.example.json"
OPENCLAW_ENV_PATH = Path.home() / ".openclaw" / ".env"


def _read_env_value_from_file(key_name: str) -> str:
    if not OPENCLAW_ENV_PATH.exists():
        return ""
    for raw in OPENCLAW_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, val = line.partition("=")
        if key.strip() != key_name:
            continue
        return val.strip().strip('"').strip("'")
    return ""


@dataclass
class Config:
    database_path: str
    template_path: str
    briefing_api_base_url: str
    briefing_api_key_env: str
    briefing_poll_interval_seconds: int
    briefing_timeout_seconds: int
    briefing_queue_concurrency: int
    default_crm_import_limit: int
    send_account: str
    send_from_name: str

    @property
    def api_key(self) -> str:
        key = os.environ.get(self.briefing_api_key_env, "").strip()
        if not key:
            key = _read_env_value_from_file(self.briefing_api_key_env)
        if not key:
            raise RuntimeError(
                f"Missing API key env var: {self.briefing_api_key_env}. "
                f"Set it before calling the website briefing API."
            )
        return key


def _load_openclaw_env() -> None:
    if not OPENCLAW_ENV_PATH.exists():
        return
    for raw in OPENCLAW_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ[key] = val


def load_config(path: Path | None = None) -> Config:
    _load_openclaw_env()
    config_path = path or (DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return Config(**raw)
