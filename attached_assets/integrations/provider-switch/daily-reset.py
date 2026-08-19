#!/usr/bin/env python3
"""
Daily model reset — runs at 04:00 every day via cron.

Switches L1 to the balanced Codex harness model (openai-codex/gpt-5.6-terra)
at the start of each day so we begin on a current, cost-effective option.
The user can switch manually via /openai or /anthropic during the day.

Cron entry (added by install script):
  0 4 * * * /usr/bin/python3 ~/.openclaw/integrations/provider-switch/daily-reset.py

Restart strategy:
  systemctl --user restart — keeps the gateway owned and monitored by the
  confirmed openclaw-gateway.service user unit.
"""

import json
import os
import re
import shutil
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
CODEX_MODEL   = os.environ.get(
    "OPENCLAW_CODEX56_TERRA_MODEL", "openai-codex/gpt-5.6-terra"
)
LOG_MAX_LINES = 500

# Locate chattr — it lives in /sbin or /usr/sbin, which cron's PATH often omits.
_CHATTR = (shutil.which("chattr")
           or shutil.which("chattr", path="/sbin:/usr/sbin:/usr/bin:/bin")
           or "/sbin/chattr")


def log(msg: str) -> None:
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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


def _chattr(flag: str, path: Path) -> bool:
    """Run sudo chattr +i / -i, return True on success, log on failure."""
    r = subprocess.run(
        ["sudo", _CHATTR, flag, str(path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log(f"WARNING: sudo chattr {flag} failed (rc={r.returncode}): "
            f"{(r.stderr or r.stdout).strip()} — PATH used: {os.environ.get('PATH')}")
        return False
    return True


def _sanitize_model(model: str) -> str:
    """Strip shell export prefix/trailing punctuation — guards against old cmd_switch bug."""
    cleaned = re.sub(r'^export\s+\S+=', '', model).rstrip(".")
    if cleaned != model:
        log(f"Sanitized corrupted model value: {model!r} -> {cleaned!r}")
    return cleaned


def _set_model(config: dict, model: str) -> dict:
    model = _sanitize_model(model)
    try:
        config["agents"]["defaults"]["model"]["primary"] = model
    except (KeyError, TypeError):
        config.setdefault("agents", {}).setdefault("defaults", {}) \
              .setdefault("model", {})["primary"] = model
    return config


def _get_current_model(config: dict) -> str:
    try:
        raw = config["agents"]["defaults"]["model"]["primary"]
        return _sanitize_model(raw) if isinstance(raw, str) else ""
    except (KeyError, TypeError):
        return ""


def _restart_gateway() -> bool:
    """Restart the gateway through its systemd user service."""
    uid = os.getuid()
    env = dict(os.environ)
    env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    log(f"Restarting via systemctl --user restart {SERVICE_NAME}…")
    r = subprocess.run(
        ["systemctl", "--user", "restart", SERVICE_NAME],
        capture_output=True, text=True, env=env, timeout=30,
    )
    if r.returncode == 0:
        log("Gateway restarted successfully via systemctl --user")
        return True
    detail = (r.stderr or r.stdout).strip()
    log(f"ERROR: systemctl --user restart failed (rc={r.returncode}): {detail}")
    log("Config IS written to Terra — the gateway will use it after the next successful restart.")
    return False


def main() -> None:
    log(f"Daily reset starting — target model: {CODEX_MODEL}")
    log(f"chattr binary: {_CHATTR}")
    log(f"PATH: {os.environ.get('PATH', '(not set)')}")

    if not CONFIG_PATH.exists():
        log(f"ERROR: Config not found at {CONFIG_PATH}")
        sys.exit(1)

    unlocked = _chattr("-i", CONFIG_PATH)
    if not unlocked:
        log("WARNING: Could not remove immutable flag — will attempt write anyway")

    try:
        with CONFIG_PATH.open() as f:
            config = json.load(f)
    except Exception as e:
        log(f"ERROR: Could not read config: {e}")
        _chattr("+i", CONFIG_PATH)
        sys.exit(1)

    current = _get_current_model(config)
    if current == CODEX_MODEL:
        log(f"Config already shows {CODEX_MODEL} — skipping write, but restarting gateway anyway")
        log("(Gateway may be running a different model if a previous restart failed)")
        _chattr("+i", CONFIG_PATH)
        if not _restart_gateway():
            sys.exit(1)
        log("Daily reset complete")
        return

    config = _set_model(config, CODEX_MODEL)

    try:
        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=2)
        log(f"Config written: {current} → {CODEX_MODEL}")
    except Exception as e:
        log(f"ERROR: Could not write config: {e}")
        log("FLAG TO TOM: daily-reset.py could not update openclaw.json — "
            "likely still immutable (chattr -i failed). "
            "Check if 'sudo chattr' is allowed without password in cron.")
        _chattr("+i", CONFIG_PATH)
        sys.exit(1)

    _chattr("+i", CONFIG_PATH)

    if not _restart_gateway():
        sys.exit(1)

    log("Daily reset complete")


if __name__ == "__main__":
    main()
