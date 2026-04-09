#!/usr/bin/env python3
"""
Daily model reset — runs at 04:00 every day via cron.

Switches L1 to the Codex OAuth model (openai-codex/gpt-5.4) at the
start of each day so we always begin on the most cost-effective option.
The user can switch manually via /openai or /anthropic during the day.

Cron entry (added by install script):
  0 4 * * * /usr/bin/python3 ~/.openclaw/integrations/provider-switch/daily-reset.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _load_dotenv() -> None:
    env_file = Path.home() / ".openclaw" / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()

CONFIG_PATH   = Path(os.environ.get("OPENCLAW_CONFIG_PATH",
                     str(Path.home() / ".openclaw" / "openclaw.json")))
LOG_FILE      = Path.home() / ".openclaw" / "workspace" / "memory" / "daily-reset.log"
SERVICE_NAME  = os.environ.get("OPENCLAW_SERVICE_NAME", "openclaw-gateway.service")
CODEX_MODEL   = os.environ.get("OPENCLAW_CODEX_MODEL", "openai-codex/gpt-5.4")
LOG_MAX_LINES = 500


def log(msg: str) -> None:
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
        lines = LOG_FILE.read_text().splitlines()
        if len(lines) > LOG_MAX_LINES:
            LOG_FILE.write_text("\n".join(lines[-LOG_MAX_LINES:]) + "\n")
    except Exception:
        pass


def _set_model(config: dict, model: str) -> dict:
    try:
        config["agents"]["defaults"]["model"]["primary"] = model
    except (KeyError, TypeError):
        config.setdefault("agents", {}).setdefault("defaults", {}) \
              .setdefault("model", {})["primary"] = model
    return config


def _get_current_model(config: dict) -> str:
    try:
        return config["agents"]["defaults"]["model"]["primary"]
    except (KeyError, TypeError):
        return ""


def main() -> None:
    log(f"Daily reset starting — target model: {CODEX_MODEL}")

    if not CONFIG_PATH.exists():
        log(f"ERROR: Config not found at {CONFIG_PATH}")
        sys.exit(1)

    subprocess.run(["sudo", "chattr", "-i", str(CONFIG_PATH)],
                   capture_output=True)

    try:
        with CONFIG_PATH.open() as f:
            config = json.load(f)
    except Exception as e:
        log(f"ERROR: Could not read config: {e}")
        subprocess.run(["sudo", "chattr", "+i", str(CONFIG_PATH)],
                       capture_output=True)
        sys.exit(1)

    current = _get_current_model(config)
    if current == CODEX_MODEL:
        log(f"Already on {CODEX_MODEL} — no change needed")
        subprocess.run(["sudo", "chattr", "+i", str(CONFIG_PATH)],
                       capture_output=True)
        return

    config = _set_model(config, CODEX_MODEL)

    try:
        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        log(f"ERROR: Could not write config: {e}")
        subprocess.run(["sudo", "chattr", "+i", str(CONFIG_PATH)],
                       capture_output=True)
        sys.exit(1)

    subprocess.run(["sudo", "chattr", "+i", str(CONFIG_PATH)],
                   capture_output=True)

    log(f"Model switched: {current} -> {CODEX_MODEL}")

    result = subprocess.run(
        ["systemctl", "--user", "restart", SERVICE_NAME],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        log("Gateway restarted successfully")
    else:
        log(f"WARNING: Gateway restart failed: {result.stderr.strip()}")

    log("Daily reset complete")


if __name__ == "__main__":
    main()
