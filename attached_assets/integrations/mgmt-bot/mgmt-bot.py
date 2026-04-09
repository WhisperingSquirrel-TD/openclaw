#!/usr/bin/env python3
"""
OpenClaw Management Bot — runs independently of the main gateway and LLM.

A separate Telegram bot that handles system management commands directly on
the Pi without touching the LLM. Works even when OpenAI is rate-limited or
the gateway is completely down.

COMMANDS
--------
  /status       — current provider, service state, Pi uptime
  /openai       — switch to OpenAI model and restart gateway
  /anthropic    — switch to Anthropic model and restart gateway
  /restart      — restart the L1 gateway service
  /pull         — git pull latest from GitHub (does NOT reinstall)
  /reboot       — reboot the Pi (refused if auto-start safety check fails)

SECURITY
--------
Only responds to the configured chat ID (MGMT_BOT_CHAT_ID).
All other messages are silently ignored.

REQUIRED ENV VARS (in ~/.openclaw/.env)
---------------------------------------
  MGMT_BOT_TOKEN          Telegram bot token for the management bot
                          (create a SECOND bot via BotFather — separate from the
                          main OpenClaw bot so the two don't conflict)
  MGMT_BOT_CHAT_ID        Your Telegram chat/user ID — only this ID is obeyed
  OPENCLAW_OPENAI_MODEL   Model ID to use for OpenAI, e.g. gpt-4o
  OPENCLAW_ANTHROPIC_MODEL Model ID to use for Anthropic, e.g. claude-3-5-sonnet-20241022

OPTIONAL ENV VARS
-----------------
  OPENCLAW_CONFIG_PATH    default: ~/.openclaw/openclaw.json
  OPENCLAW_GIT_DIR        default: ~/openclaw
  OPENCLAW_SERVICE_NAME   default: openclaw-gateway.service

SETUP
-----
1. Create a second Telegram bot via BotFather → copy the token
2. Add MGMT_BOT_TOKEN and MGMT_BOT_CHAT_ID to ~/.openclaw/.env
3. Add OPENCLAW_OPENAI_MODEL and OPENCLAW_ANTHROPIC_MODEL to ~/.openclaw/.env
4. Run the install script — it deploys this file and installs the systemd service
5. Verify: systemctl --user status openclaw-mgmt-bot.service

To find your chat ID: message @userinfobot on Telegram.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".openclaw"
OFFSET_FILE = STATE_DIR / "mgmt-bot-offset.json"

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_file = STATE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _cfg(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _require(key: str) -> str:
    val = _cfg(key)
    if not val:
        print(f"ERROR: {key} is not set in ~/.openclaw/.env", file=sys.stderr)
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# Telegram helpers (no library — just requests)
# ---------------------------------------------------------------------------

def _tg(token: str, method: str, **kwargs) -> dict:
    import urllib.request, urllib.parse
    url = TELEGRAM_API.format(token=token, method=method)
    data = json.dumps(kwargs).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"Telegram API error ({method}): {e}", file=sys.stderr)
        return {}


def send(token: str, chat_id: str, text: str) -> None:
    _tg(token, "sendMessage", chat_id=chat_id, text=text, parse_mode="Markdown")


def get_updates(token: str, offset: int) -> list:
    result = _tg(token, "getUpdates", offset=offset, timeout=30, allowed_updates=["message"])
    return result.get("result", [])


def load_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return json.loads(OFFSET_FILE.read_text()).get("offset", 0)
        except Exception:
            pass
    return 0


def save_offset(offset: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": offset}))


# ---------------------------------------------------------------------------
# openclaw.json editor
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    return Path(_cfg("OPENCLAW_CONFIG_PATH", str(STATE_DIR / "openclaw.json")))


def _read_config() -> dict:
    p = _config_path()
    if not p.exists():
        raise FileNotFoundError(f"openclaw.json not found at {p}")
    return json.loads(p.read_text())


def _write_config(data: dict) -> None:
    p = _config_path()
    # Remove immutable flag, write, restore
    subprocess.run(["sudo", "chattr", "-i", str(p)], capture_output=True)
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(p)
    finally:
        subprocess.run(["sudo", "chattr", "+i", str(p)], capture_output=True)


def _get_current_model(config: dict) -> str:
    """Navigate agents.defaults.model.primary (current schema)."""
    try:
        return config["agents"]["defaults"]["model"]["primary"]
    except (KeyError, TypeError):
        pass
    try:
        return config["agent"]["model"]
    except (KeyError, TypeError):
        pass
    return "unknown"


def _set_model(config: dict, model: str) -> dict:
    """Set model in the current schema location."""
    if "agents" in config and "defaults" in config.get("agents", {}):
        agents = config.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        model_block = defaults.setdefault("model", {})
        model_block["primary"] = model
    elif "agent" in config:
        config["agent"]["model"] = model
    else:
        # Best guess — write both
        config.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})["primary"] = model
    return config


# ---------------------------------------------------------------------------
# systemd helpers
# ---------------------------------------------------------------------------

def _service() -> str:
    return _cfg("OPENCLAW_SERVICE_NAME", "openclaw-gateway.service")


def _service_is_enabled() -> bool:
    r = subprocess.run(
        ["systemctl", "--user", "is-enabled", _service()],
        capture_output=True, text=True,
    )
    return r.stdout.strip() == "enabled"


def _linger_is_enabled() -> bool:
    user = os.environ.get("USER", "")
    r = subprocess.run(["loginctl", "show-user", user, "-p", "Linger"],
                       capture_output=True, text=True)
    return "Linger=yes" in r.stdout


def _service_status() -> str:
    r = subprocess.run(
        ["systemctl", "--user", "is-active", _service()],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def _restart_gateway() -> tuple[bool, str]:
    r = subprocess.run(
        ["systemctl", "--user", "restart", _service()],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        return True, "Gateway restarted successfully."
    return False, f"Restart failed:\n```{r.stderr.strip() or r.stdout.strip()}```"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_status(token: str, chat_id: str) -> None:
    try:
        config = _read_config()
        model = _get_current_model(config)
    except Exception as e:
        model = f"(error: {e})"

    svc_state = _service_status()
    enabled    = "✅ enabled" if _service_is_enabled() else "❌ NOT enabled"
    linger     = "✅ yes" if _linger_is_enabled() else "❌ NO (reboot unsafe)"

    uptime_r = subprocess.run(["uptime", "-p"], capture_output=True, text=True)
    uptime   = uptime_r.stdout.strip()

    msg = (
        f"*OpenClaw Status*\n\n"
        f"🤖 Model: `{model}`\n"
        f"⚙️ Gateway: `{svc_state}`\n"
        f"🔁 Auto-start: {enabled}\n"
        f"🔌 Linger: {linger}\n"
        f"⏱ Uptime: {uptime}"
    )
    send(token, chat_id, msg)


def cmd_switch(token: str, chat_id: str, provider: str) -> None:
    model_key = "OPENCLAW_OPENAI_MODEL" if provider == "openai" else "OPENCLAW_ANTHROPIC_MODEL"
    model = _cfg(model_key)
    if not model:
        send(token, chat_id,
             f"❌ `{model_key}` is not set in `~/.openclaw/.env`.\n"
             f"Add it and re-run the install script.")
        return
    try:
        config = _read_config()
        current = _get_current_model(config)
        if current == model:
            send(token, chat_id, f"ℹ️ Already using `{model}` — no change.")
            return
        config = _set_model(config, model)
        _write_config(config)
    except Exception as e:
        send(token, chat_id, f"❌ Failed to update config:\n```{e}```")
        return

    send(token, chat_id, f"✅ Model set to `{model}`\nRestarting gateway…")
    ok, msg = _restart_gateway()
    icon = "✅" if ok else "❌"
    send(token, chat_id, f"{icon} {msg}")


def cmd_restart(token: str, chat_id: str) -> None:
    send(token, chat_id, "🔄 Restarting L1 gateway…")
    ok, msg = _restart_gateway()
    icon = "✅" if ok else "❌"
    send(token, chat_id, f"{icon} {msg}")


def cmd_reboot(token: str, chat_id: str) -> None:
    issues = []
    if not _service_is_enabled():
        issues.append(f"• Gateway service (`{_service()}`) is NOT enabled — it won't restart after reboot")
        issues.append(f"  Fix: `systemctl --user enable {_service()}`")
    if not _linger_is_enabled():
        issues.append(f"• Linger is NOT enabled — user services won't start on boot")
        issues.append(f"  Fix: `sudo loginctl enable-linger {os.environ.get('USER', 'tomdean88')}`")

    if issues:
        send(token, chat_id,
             "❌ *Reboot refused — safety checks failed:*\n\n"
             + "\n".join(issues)
             + "\n\nFix these first, then try `/reboot` again.")
        return

    send(token, chat_id,
         "⚠️ *Rebooting Pi now.*\n"
         "Gateway will be back in ~60 seconds.\n"
         "This bot will also be back automatically.")
    time.sleep(2)
    subprocess.run(["sudo", "reboot"])


def cmd_pull(token: str, chat_id: str) -> None:
    git_dir = Path(_cfg("OPENCLAW_GIT_DIR", str(Path.home() / "openclaw")))
    if not git_dir.exists():
        send(token, chat_id, f"❌ Git directory not found: `{git_dir}`")
        return
    send(token, chat_id, f"⬇️ Pulling latest from GitHub (`{git_dir}`)…")
    r = subprocess.run(
        ["git", "-C", str(git_dir), "pull"],
        capture_output=True, text=True, timeout=60,
    )
    output = (r.stdout + r.stderr).strip()
    if r.returncode == 0:
        send(token, chat_id, f"✅ Pull complete:\n```{output}```\n\n"
             f"_Note: run the install script to deploy any updated files._")
    else:
        send(token, chat_id, f"❌ Pull failed:\n```{output}```")


def cmd_help(token: str, chat_id: str) -> None:
    send(token, chat_id,
         "*OpenClaw Management Bot*\n\n"
         "/status — current model, gateway state, reboot safety\n"
         "/openai — switch to OpenAI model + restart gateway\n"
         "/anthropic — switch to Anthropic model + restart gateway\n"
         "/restart — restart the L1 gateway\n"
         "/pull — git pull latest (deploy changes separately)\n"
         "/reboot — reboot Pi (refused if auto-start is not configured)\n"
         "/help — this message")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

COMMANDS = {
    "/status":    cmd_status,
    "/openai":    lambda t, c: cmd_switch(t, c, "openai"),
    "/anthropic": lambda t, c: cmd_switch(t, c, "anthropic"),
    "/restart":   cmd_restart,
    "/reboot":    cmd_reboot,
    "/pull":      cmd_pull,
    "/help":      cmd_help,
    "/start":     cmd_help,
}


def main() -> None:
    _load_dotenv()

    token      = _require("MGMT_BOT_TOKEN")
    allowed_id = _require("MGMT_BOT_CHAT_ID")

    print(f"[mgmt-bot] Starting. Listening for commands from chat_id={allowed_id}…")

    offset = load_offset()

    while True:
        try:
            updates = get_updates(token, offset)
        except Exception as e:
            print(f"[mgmt-bot] getUpdates error: {e}", file=sys.stderr)
            time.sleep(10)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            save_offset(offset)

            msg = update.get("message") or {}
            chat = msg.get("chat", {})
            chat_id = str(chat.get("id", ""))
            text = (msg.get("text") or "").strip()

            # Security: silently ignore anything not from the allowed chat
            if chat_id != allowed_id:
                continue

            # Extract command (strip bot username suffix e.g. /cmd@mybot)
            cmd = text.split()[0].split("@")[0].lower() if text else ""

            handler = COMMANDS.get(cmd)
            if handler:
                print(f"[mgmt-bot] Command: {cmd} from {chat_id}")
                try:
                    handler(token, chat_id)
                except Exception as e:
                    print(f"[mgmt-bot] Handler error ({cmd}): {e}", file=sys.stderr)
                    send(token, chat_id, f"❌ Error running `{cmd}`:\n```{e}```")

        time.sleep(1)


if __name__ == "__main__":
    main()
