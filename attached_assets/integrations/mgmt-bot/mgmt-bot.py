#!/usr/bin/env python3
"""
OpenClaw Management Bot — runs independently of the main gateway and LLM.

A separate Telegram bot that handles system management commands directly on
the Pi without touching the LLM. Works even when OpenAI is rate-limited or
the gateway is completely down.

COMMANDS
--------
  /status       — current provider, service state, Pi uptime
  /openai       — switch to OpenAI API model and restart gateway
  /anthropic    — switch to Anthropic API model and restart gateway
  /codex        — switch to OpenAI Codex gpt-5.4 (full) and restart gateway
  /codexmini    — switch to OpenAI Codex gpt-5.4-mini (cheaper/faster) and restart gateway
  /restart      — restart the L1 gateway service
  /pull         — git pull latest from GitHub (does NOT reinstall)
  /reboot       — reboot the Pi (refused if auto-start safety check fails)
  /health       — run system health check now and show output
  /logs         — show recent errors across all poller logs
  /garmin       — manually trigger the Garmin poller
  /yt-add       — add a YouTube channel to the transcript poller
  /yt-list      — list configured YouTube channels
  /yt-run       — trigger the YouTube channel poller now
  /disk         — disk space on the Pi
  /soul         — upload a new SOUL.md as a .docx file, re-encrypts and restarts

SECURITY
--------
Only responds to the configured chat ID (MGMT_BOT_CHAT_ID).
All other messages are silently ignored.

REQUIRED ENV VARS (in ~/.openclaw/.env)
---------------------------------------
  MGMT_BOT_TOKEN            Telegram bot token for the management bot
                            (create a SECOND bot via BotFather — separate from the
                            main OpenClaw bot so the two don't conflict)
  MGMT_BOT_CHAT_ID          Your Telegram chat/user ID — only this ID is obeyed
  OPENCLAW_OPENAI_MODEL     Model ID for OpenAI API, e.g. openai/gpt-5-mini-2025-08-07
  OPENCLAW_ANTHROPIC_MODEL  Model ID for Anthropic API, e.g. anthropic/claude-sonnet-4-5
  OPENCLAW_CODEX_MODEL      Model ID for /codex command, e.g. openai-codex/gpt-5.4
  OPENCLAW_CODEX_MINI_MODEL Model ID for /codexmini command, e.g. openai-codex/gpt-5.4-mini
  OPENCLAW_VAULT_PASSPHRASE Passphrase used to encrypt SOUL.md (already in .env)

OPTIONAL ENV VARS
-----------------
  OPENCLAW_CONFIG_PATH    default: ~/.openclaw/openclaw.json
  OPENCLAW_GIT_DIR        default: ~/openclaw
  OPENCLAW_SERVICE_NAME   default: openclaw-gateway.service
  OPENCLAW_HEALTH_SCRIPT  default: ~/.openclaw/integrations/health/health_check.py
  OPENCLAW_GARMIN_SCRIPT  default: ~/.openclaw/integrations/garmin/poll-garmin.py
  OPENCLAW_VAULT_DIR      default: ~/.openclaw/vault

SOUL UPDATE FLOW
----------------
1. Send /soul to the management bot
2. Bot prompts: "Send your new SOUL.md as a .docx file"
3. Upload the .docx file in Telegram
4. Bot downloads it, converts via LibreOffice, encrypts with existing vault
   passphrase, backs up the old SOUL.md.enc, writes the new one, restarts gateway
5. Bot confirms with a preview of the first few lines

SETUP
-----
1. Create a second Telegram bot via BotFather → copy the token
2. Message @userinfobot on Telegram → copy your numeric chat ID
3. Add to ~/.openclaw/.env:
     MGMT_BOT_TOKEN=<token>
     MGMT_BOT_CHAT_ID=<your_numeric_id>
     OPENCLAW_OPENAI_MODEL=openai/gpt-5-mini-2025-08-07
     OPENCLAW_ANTHROPIC_MODEL=anthropic/claude-sonnet-4-5
     OPENCLAW_CODEX_MODEL=openai-codex/gpt-5.4
4. Run the install script — deploys this file and installs the systemd service
5. Verify: systemctl --user status openclaw-mgmt-bot.service
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_DIR   = Path.home() / ".openclaw"
OFFSET_FILE = STATE_DIR / "mgmt-bot-offset.json"
SOUL_PENDING_FLAG = Path("/tmp/oc-mgmt-soul-pending")

TELEGRAM_API    = "https://api.telegram.org/bot{token}/{method}"
TELEGRAM_FILE   = "https://api.telegram.org/file/bot{token}/{file_path}"

# Soul vault constants — must match soul-vault.ts exactly
_ALGORITHM        = "aes-256-gcm"
_KEY_LENGTH       = 32
_IV_LENGTH        = 12
_SALT_LENGTH      = 16
_TAG_LENGTH       = 16
_PBKDF2_ITERATIONS = 100_000


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
        if line.startswith("export "):
            line = line[7:]
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# ---------------------------------------------------------------------------
# Config helpers
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
# Telegram helpers (no external library — stdlib only)
# ---------------------------------------------------------------------------

def _tg(token: str, method: str, **kwargs) -> dict:
    url  = TELEGRAM_API.format(token=token, method=method)
    data = json.dumps(kwargs).encode()
    req  = urllib.request.Request(
        url, data=data,
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
    """Long-poll Telegram for new messages.

    The Telegram timeout=30 is the server-side wait (seconds).
    The socket timeout must be larger — give 10 s of headroom.
    """
    url  = TELEGRAM_API.format(token=token, method="getUpdates")
    data = json.dumps({
        "offset": offset,
        "timeout": 30,
        "allowed_updates": ["message"],
    }).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
            return result.get("result", [])
    except Exception as e:
        print(f"[mgmt-bot] getUpdates error: {e}", file=sys.stderr)
        return []


def get_file(token: str, file_id: str) -> str | None:
    """Return the file_path for a Telegram file_id."""
    r = _tg(token, "getFile", file_id=file_id)
    return r.get("result", {}).get("file_path")


def download_file(token: str, file_path: str, dest: Path) -> None:
    url = TELEGRAM_FILE.format(token=token, file_path=file_path)
    with urllib.request.urlopen(url, timeout=60) as resp:
        dest.write_bytes(resp.read())


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
    explicit = _cfg("OPENCLAW_CONFIG_PATH")
    if explicit:
        return Path(explicit)
    state_dir = Path(_cfg("OPENCLAW_STATE_DIR", str(STATE_DIR)))
    return state_dir / "openclaw.json"


def _read_config() -> dict:
    p = _config_path()
    if not p.exists():
        raise FileNotFoundError(f"openclaw.json not found at {p}")
    return json.loads(p.read_text())


def _write_config(data: dict) -> None:
    p = _config_path()
    subprocess.run(["sudo", "chattr", "-i", str(p)], capture_output=True)
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(p)
    finally:
        subprocess.run(["sudo", "chattr", "+i", str(p)], capture_output=True)


def _get_current_model(config: dict) -> str:
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
    if "agents" in config and "defaults" in config.get("agents", {}):
        config.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})["primary"] = model
    elif "agent" in config:
        config["agent"]["model"] = model
    else:
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
    r = subprocess.run(
        ["loginctl", "show-user", user, "-p", "Linger"],
        capture_output=True, text=True,
    )
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
# Soul vault encryption (mirrors soul-vault.ts exactly)
# ---------------------------------------------------------------------------

def _encrypt_soul(plaintext: str, passphrase: str) -> bytes:
    """
    AES-256-GCM + PBKDF2-HMAC-SHA512.
    Output layout: salt(16) | iv(12) | tag(16) | ciphertext
    Must match soul-vault.ts encryptContent() byte-for-byte.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    salt = os.urandom(_SALT_LENGTH)
    iv   = os.urandom(_IV_LENGTH)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA512(),
        length=_KEY_LENGTH,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    key = kdf.derive(passphrase.encode("utf-8"))

    aesgcm = AESGCM(key)
    ct_and_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)

    # cryptography library appends tag at end; Node.js puts it before ciphertext
    ciphertext = ct_and_tag[:-_TAG_LENGTH]
    tag        = ct_and_tag[-_TAG_LENGTH:]

    return salt + iv + tag + ciphertext


def _vault_dir() -> Path:
    """
    Mirror soul-vault.ts resolveVaultDir() exactly:
      resolveStateDir() → OPENCLAW_STATE_DIR ?? ~/.openclaw
      resolveVaultDir() → {stateDir}/vault

    OPENCLAW_VAULT_DIR can override the full path if needed, but
    under normal circumstances OPENCLAW_STATE_DIR is the only var
    the gateway respects, so we follow the same logic.
    """
    # Explicit override wins
    override = _cfg("OPENCLAW_VAULT_DIR")
    if override:
        return Path(override)
    # Otherwise: match the gateway — OPENCLAW_STATE_DIR ?? ~/.openclaw, then /vault
    state_dir = Path(_cfg("OPENCLAW_STATE_DIR", str(STATE_DIR)))
    return state_dir / "vault"


def _convert_docx_to_text(docx_path: Path) -> str:
    """Convert a .docx to plaintext using LibreOffice headless."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = subprocess.run(
            [
                "libreoffice", "--headless",
                "--convert-to", "txt:Text",
                "--outdir", tmp_dir,
                str(docx_path),
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice conversion failed: {result.stderr.strip() or result.stdout.strip()}"
            )
        txt_path = Path(tmp_dir) / docx_path.with_suffix(".txt").name
        if not txt_path.exists():
            raise RuntimeError("LibreOffice ran but produced no output file.")
        return txt_path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _daily_reset_status() -> str:
    """Return a one-line summary of the last daily reset run."""
    log_path = STATE_DIR / "workspace" / "memory" / "daily-reset.log"
    if not log_path.exists():
        return "⚠️ never run (no log found)"
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
        # Find the last "complete" or "ERROR" line to summarise what happened
        summary = ""
        last_ts  = ""
        for line in reversed(lines):
            if not last_ts and line.startswith("["):
                last_ts = line[1:20]  # timestamp portion
            if any(k in line.lower() for k in ("complete", "error", "switched", "no change", "skipping write", "restarting gateway")):
                summary = line.split("] ", 1)[-1] if "] " in line else line
                break
        if not last_ts:
            return "⚠️ log exists but unreadable"
        return f"{last_ts} — {summary}" if summary else f"last ran {last_ts}"
    except Exception as e:
        return f"⚠️ could not read log: {e}"


def cmd_status(token: str, chat_id: str) -> None:
    try:
        config  = _read_config()
        model   = _get_current_model(config)
    except Exception as e:
        model = f"(error: {e})"

    svc_state = _service_status()
    enabled   = "✅ enabled" if _service_is_enabled() else "❌ NOT enabled"
    linger    = "✅ yes" if _linger_is_enabled() else "❌ NO (reboot unsafe)"
    uptime    = subprocess.run(["uptime", "-p"], capture_output=True, text=True).stdout.strip()

    vault_enc = (_vault_dir() / "SOUL.md.enc").exists()
    soul_src  = "🔐 encrypted vault" if vault_enc else "📄 plaintext SOUL.md"

    reset_info = _daily_reset_status()

    send(token, chat_id,
         f"*OpenClaw Status*\n\n"
         f"🤖 Model: `{model}`\n"
         f"⚙️ Gateway: `{svc_state}`\n"
         f"🔁 Auto-start: {enabled}\n"
         f"🔌 Linger: {linger}\n"
         f"🧠 Soul: {soul_src}\n"
         f"⏱ Uptime: {uptime}\n"
         f"🔄 Daily reset: {reset_info}")


def cmd_switch(token: str, chat_id: str, provider: str) -> None:
    model_key = {
        "openai":     "OPENCLAW_OPENAI_MODEL",
        "anthropic":  "OPENCLAW_ANTHROPIC_MODEL",
        "codex":      "OPENCLAW_CODEX_MODEL",
        "codexmini":  "OPENCLAW_CODEX_MINI_MODEL",
    }.get(provider, "OPENCLAW_OPENAI_MODEL")

    # Default values if env var not explicitly set
    model_defaults = {
        "codexmini": "openai-codex/gpt-5.4-mini",
        "codex":     "openai-codex/gpt-5.4",
    }
    model = _cfg(model_key) or model_defaults.get(provider, "")
    if not model:
        send(token, chat_id,
             f"❌ `{model_key}` is not set in `~/.openclaw/.env`.\n"
             f"Add it and re-run the install script.")
        return
    # Validate the required API key is present in .env before switching.
    # Codex uses OAuth (no key needed); openai/anthropic need their keys.
    api_key_var = {
        "openai":    "OPENAI_API_KEY",
        "anthropic": None,  # gateway handles Anthropic auth internally
        "codex":     None,  # uses OAuth
        "codexmini": None,  # uses OAuth
    }.get(provider)
    if api_key_var:
        if not _cfg(api_key_var):
            send(token, chat_id,
                 f"❌ `{api_key_var}` is not set in `~/.openclaw/.env`.\n"
                 f"Add it before switching to `{provider}`.")
            return

    # Ensure the model has a provider prefix — the gateway requires it and
    # will incorrectly prepend "anthropic/" to any bare model ID.
    # If the .env value already contains "/" (e.g. openai-codex/gpt-5.4),
    # use it verbatim. Only add the correct gateway prefix for bare names.
    gateway_prefix = {
        "openai":    "openai",
        "anthropic": "anthropic",
        "codex":     "openai-codex",
        "codexmini": "openai-codex",
    }.get(provider, provider)
    if "/" not in model:
        model = f"{gateway_prefix}/{model}"
    try:
        config  = _read_config()
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
    send(token, chat_id, f"{'✅' if ok else '❌'} {msg}")


def cmd_restart(token: str, chat_id: str) -> None:
    send(token, chat_id, "🔄 Restarting L1 gateway…")
    ok, msg = _restart_gateway()
    send(token, chat_id, f"{'✅' if ok else '❌'} {msg}")


def cmd_reboot(token: str, chat_id: str) -> None:
    issues = []
    if not _service_is_enabled():
        issues.append(f"• Gateway (`{_service()}`) is NOT enabled")
        issues.append(f"  Fix: `systemctl --user enable {_service()}`")
    if not _linger_is_enabled():
        issues.append("• Linger is NOT enabled — user services won't start on boot")
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
         "This management bot will also restart automatically.")
    time.sleep(2)
    subprocess.run(["sudo", "reboot"])


def cmd_pull(token: str, chat_id: str) -> None:
    git_dir = Path(_cfg("OPENCLAW_GIT_DIR", str(Path.home() / "openclaw")))
    if not git_dir.exists():
        send(token, chat_id, f"❌ Git directory not found: `{git_dir}`")
        return
    send(token, chat_id, "⬇️ Pulling latest from GitHub…")
    r = subprocess.run(
        ["git", "-C", str(git_dir), "pull"],
        capture_output=True, text=True, timeout=60,
    )
    output = (r.stdout + r.stderr).strip()
    if r.returncode == 0:
        send(token, chat_id,
             f"✅ Pull complete:\n```{output}```\n\n"
             f"_Send /install to deploy the updated files._")
    else:
        send(token, chat_id, f"❌ Pull failed:\n```{output}```")


def cmd_install(token: str, chat_id: str) -> None:
    """Pull latest from GitHub then run the install script.

    The install script restarts this bot via systemd, which kills the current
    process before any result can be sent.  Fix: run everything in a fully
    detached child (new session, stdin/out/err closed) so it survives the
    systemd restart.  The wrapper reports back to Telegram via curl once done.
    """
    git_dir    = Path(_cfg("OPENCLAW_GIT_DIR", str(Path.home() / "openclaw")))
    install_sh = Path.home() / "install-forked-openclaw.sh"

    if not git_dir.exists():
        send(token, chat_id, f"❌ Git directory not found: `{git_dir}`")
        return
    if not install_sh.exists():
        send(token, chat_id, f"❌ Install script not found: `{install_sh}`")
        return

    send(token, chat_id, "⬇️ Pulling latest from GitHub…")
    pull = subprocess.run(
        ["git", "-C", str(git_dir), "pull"],
        capture_output=True, text=True, timeout=60,
    )
    pull_out = (pull.stdout + pull.stderr).strip()
    if pull.returncode != 0:
        send(token, chat_id, f"❌ Pull failed — install aborted:\n```{pull_out}```")
        return

    send(token, chat_id,
         f"✅ Pull complete:\n```{pull_out}```\n\n"
         f"🔧 Running install script in background…\n"
         f"_(this takes ~5 min — you will get a Telegram message when it finishes, "
         f"even after I restart)_")

    # Write a self-contained Python wrapper that:
    #   1. runs the install script via subprocess (capturing output)
    #   2. sends the result back to Telegram via urllib (no curl escaping issues)
    # Launched with start_new_session=True so it becomes its own session leader
    # and is NOT killed when systemd stops/restarts the mgmt-bot service.
    wrapper_path = Path("/tmp/openclaw-install-wrapper.py")
    wrapper_path.write_text(
        "#!/usr/bin/env python3\n"
        "import subprocess, urllib.request, json, sys, time\n"
        f"TOKEN   = {token!r}\n"
        f"CHAT_ID = {chat_id!r}\n"
        f"INSTALL = {str(install_sh)!r}\n"
        "\n"
        "def tg(text):\n"
        "    try:\n"
        "        data = json.dumps({'chat_id': CHAT_ID, 'text': text,\n"
        "                           'parse_mode': 'Markdown'}).encode()\n"
        "        req  = urllib.request.Request(\n"
        "            f'https://api.telegram.org/bot{TOKEN}/sendMessage',\n"
        "            data=data, headers={'Content-Type': 'application/json'})\n"
        "        urllib.request.urlopen(req, timeout=15)\n"
        "    except Exception as e:\n"
        "        print(f'tg send failed: {e}', file=sys.stderr)\n"
        "\n"
        "import os, shutil as _shutil\n"
        "HOME = os.path.expanduser('~')\n"
        "\n"
        "def svc_active(name):\n"
        "    r = subprocess.run(['systemctl', '--user', 'is-active', name],\n"
        "                       capture_output=True, text=True)\n"
        "    return r.stdout.strip() == 'active'\n"
        "\n"
        "def gateway_up():\n"
        "    \"\"\"Try l1-start.sh first (Pi-native), then systemctl --user start.\"\"\"\n"
        "    l1_start = os.path.join(HOME, 'l1-start.sh')\n"
        "    if os.path.exists(l1_start):\n"
        "        r = subprocess.run(['bash', l1_start], capture_output=True, text=True, timeout=30)\n"
        "        if r.returncode == 0:\n"
        "            return True\n"
        "    # Fallback: systemctl --user start\n"
        "    subprocess.run(['systemctl', '--user', 'start', 'openclaw-gateway.service'],\n"
        "                   capture_output=True, timeout=30)\n"
        "    return False\n"
        "\n"
        "# Run the install script\n"
        "res = subprocess.run(['bash', INSTALL],\n"
        "                     capture_output=True, text=True, timeout=900)\n"
        "output = (res.stdout + res.stderr).strip()\n"
        "lines  = output.splitlines()\n"
        "tail   = '\\n'.join(lines[-40:])\n"
        "prefix = f'_(showing last 40 of {len(lines)} lines)_\\n\\n' if len(lines) > 40 else ''\n"
        "\n"
        "# Safety net: ensure the gateway comes back up regardless of install outcome.\n"
        "# Use l1-start.sh (Pi-native) — systemctl --user may not work in this context.\n"
        "time.sleep(8)\n"
        "gw = 'openclaw-gateway.service'\n"
        "if not svc_active(gw):\n"
        "    gateway_up()\n"
        "    time.sleep(8)\n"
        "\n"
        "gw_ok  = svc_active(gw)\n"
        "gw_tag = '✅ Gateway: running' if gw_ok else '⚠️ Gateway check inconclusive — verify with /status'\n"
        "\n"
        "if res.returncode == 0:\n"
        "    msg = f'✅ Install complete.\\n{gw_tag}\\n\\n{prefix}```{tail}```'\n"
        "else:\n"
        "    msg = f'⚠️ Install finished with errors (rc={res.returncode}).\\n{gw_tag}\\n\\n{prefix}```{tail}```'\n"
        "tg(msg)\n"
    )
    wrapper_path.chmod(0o700)

    # Escape the mgmt-bot systemd cgroup so systemd doesn't kill the wrapper
    # when it restarts this service during the install. systemd-run --user
    # puts the wrapper in its own transient unit with its own cgroup.
    # Falls back to start_new_session if systemd-run is unavailable.
    _sdr = shutil.which("systemd-run")
    if _sdr:
        subprocess.Popen(
            [_sdr, "--user", "--no-block",
             sys.executable, str(wrapper_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.Popen(
            [sys.executable, str(wrapper_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def cmd_health(token: str, chat_id: str) -> None:
    script = Path(_cfg("OPENCLAW_HEALTH_SCRIPT",
                        str(STATE_DIR / "integrations/health/health_check.py")))
    if not script.exists():
        send(token, chat_id, f"❌ Health script not found: `{script}`")
        return
    send(token, chat_id, "🔍 Running system health check…")
    r = subprocess.run(
        ["python3", str(script)],
        capture_output=True, text=True, timeout=60,
    )
    health_file = STATE_DIR / "workspace/SYSTEM_HEALTH.md"
    if health_file.exists() and health_file.stat().st_size > 0:
        content = health_file.read_text().strip()
        preview = content[:3000] + ("…" if len(content) > 3000 else "")
        send(token, chat_id, f"⚠️ *Issues found:*\n\n```{preview}```")
    else:
        send(token, chat_id, "✅ All systems healthy — SYSTEM_HEALTH.md is empty.")


def cmd_logs(token: str, chat_id: str) -> None:
    log_paths = [
        STATE_DIR / "gateway.log",
        STATE_DIR / "integrations/stackstone/poller.log",
        STATE_DIR / "integrations/stackstone/enquiry-poller.log",
        STATE_DIR / "integrations/health/health-check.log",
        STATE_DIR / "integrations/mgmt-bot/mgmt-bot.log",
        STATE_DIR / "workspace/memory/poll-garmin-log.txt",
        STATE_DIR / "workspace/memory/poll-calendar-log.txt",
        STATE_DIR / "workspace/memory/poll-calendar-google-log.txt",
        STATE_DIR / "workspace/memory/poll-crm-log.txt",
        STATE_DIR / "workspace/memory/poll-gmail-log.txt",
    ]
    errors = []
    for log in log_paths:
        if not log.exists():
            continue
        try:
            lines = log.read_text().splitlines()
            for line in lines[-200:]:
                if "ERROR" in line or "error" in line.lower() and "level" not in line.lower():
                    errors.append(f"`{log.name}`: {line.strip()}")
        except Exception:
            pass

    if not errors:
        send(token, chat_id, "✅ No errors found in recent poller logs.")
        return

    # Cap output to fit in Telegram message
    output = "\n".join(errors[-20:])
    if len(errors) > 20:
        output = f"_(showing last 20 of {len(errors)} errors)_\n\n" + output
    send(token, chat_id, f"⚠️ *Recent errors:*\n\n{output}")


def cmd_garmin(token: str, chat_id: str) -> None:
    cookie_script = STATE_DIR / "integrations/garmin/poll-garmin-cookie.py"
    legacy_script  = STATE_DIR / "integrations/garmin/poll-garmin.py"
    override = _cfg("OPENCLAW_GARMIN_SCRIPT", "")
    if override:
        script = Path(override)
    elif cookie_script.exists():
        script = cookie_script
    elif legacy_script.exists():
        script = legacy_script
    else:
        send(token, chat_id, "❌ Garmin script not found (neither cookie nor legacy poller present)")
        return
    send(token, chat_id, f"🏃 Triggering Garmin poller (`{script.name}`) — may take 30–60 seconds…")
    r = subprocess.run(
        ["python3", str(script)],
        capture_output=True, text=True, timeout=120,
    )
    output = (r.stdout + r.stderr).strip()
    tail   = "\n".join(output.splitlines()[-15:]) if output else "(no output)"
    if r.returncode == 0:
        send(token, chat_id, f"✅ Garmin poller complete:\n```{tail}```")
    else:
        send(token, chat_id, f"❌ Garmin poller failed:\n```{tail}```")


def _yt_channels_path() -> "Path":
    return STATE_DIR / "integrations" / "youtube" / "channels.json"


def _yt_load_channels() -> list:
    p = _yt_channels_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text())
        return [c for c in raw if "_comment" not in c and "_fields" not in c]
    except Exception:
        return []


def _yt_save_channels(channels: list) -> None:
    p = _yt_channels_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(channels, indent=2))
    tmp.replace(p)


def cmd_yt_add(token: str, chat_id: str, args: str) -> None:
    """
    Usage: /yt-add <channel_url_or_id> [label]
    Examples:
      /yt-add https://www.youtube.com/@mkbhd MKBHD
      /yt-add UCBcRF18a7Qf58cCRy5xuWwQ "OpenClaw Dev Channel"
      /yt-add https://www.youtube.com/@lex_fridman
    """
    parts = args.strip().split(None, 1)
    if not parts:
        send(token, chat_id,
             "Usage: `/yt-add <channel_url_or_id> [label]`\n\n"
             "Examples:\n"
             "`/yt-add https://www.youtube.com/@mkbhd MKBHD`\n"
             "`/yt-add UCBcRF18a7Qf58cCRy5xuWwQ`")
        return

    url_or_id = parts[0].strip()
    label = parts[1].strip().strip('"').strip("'") if len(parts) > 1 else ""

    # Detect whether it's a bare channel ID (UC...) or a URL
    import re as _re
    is_channel_id = bool(_re.match(r'^UC[\w-]{22}$', url_or_id))

    if is_channel_id:
        entry: dict = {"channel_id": url_or_id}
    else:
        entry = {"channel_url": url_or_id}

    if label:
        entry["label"] = label
    entry["active"] = True

    channels = _yt_load_channels()

    # Check for duplicates
    for existing in channels:
        if existing.get("channel_id") == entry.get("channel_id") and entry.get("channel_id"):
            send(token, chat_id, f"⚠️ Channel `{url_or_id}` is already in the list.")
            return
        if existing.get("channel_url") == entry.get("channel_url") and entry.get("channel_url"):
            send(token, chat_id, f"⚠️ Channel `{url_or_id}` is already in the list.")
            return

    channels.append(entry)
    _yt_save_channels(channels)

    label_str = f" ({label})" if label else ""
    send(token, chat_id,
         f"✅ YouTube channel added{label_str}:\n`{url_or_id}`\n\n"
         f"It will be polled within the next 30 minutes.")


def cmd_yt_list(token: str, chat_id: str) -> None:
    channels = _yt_load_channels()
    if not channels:
        send(token, chat_id,
             "No channels configured yet.\n\n"
             "Add one with: `/yt-add <url_or_id> [label]`")
        return
    lines = [f"*YouTube channels ({len(channels)}):*\n"]
    for i, ch in enumerate(channels, 1):
        ident = ch.get("channel_id") or ch.get("channel_url", "?")
        label = ch.get("label", "")
        active = "✅" if ch.get("active", True) else "⏸"
        lines.append(f"{active} {i}. {label or ident}\n   `{ident}`")
    send(token, chat_id, "\n".join(lines))


def cmd_yt_run(token: str, chat_id: str) -> None:
    poller = STATE_DIR / "integrations" / "youtube" / "channel_poller.py"
    if not poller.exists():
        send(token, chat_id, "❌ YouTube channel poller not found — run `/install` first.")
        return
    send(token, chat_id, "▶️ Running YouTube channel poller — may take a minute…")
    r = subprocess.run(
        ["python3", str(poller)],
        capture_output=True, text=True, timeout=180,
    )
    output = (r.stdout + r.stderr).strip()
    tail = "\n".join(output.splitlines()[-20:]) if output else "(no output)"
    if r.returncode == 0:
        send(token, chat_id, f"✅ YouTube poller complete:\n```{tail}```")
    else:
        send(token, chat_id, f"❌ YouTube poller failed:\n```{tail}```")


def cmd_disk(token: str, chat_id: str) -> None:
    r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    if len(lines) >= 2:
        header, data = lines[0], lines[1]
        parts = data.split()
        used, avail, pct = parts[2], parts[3], parts[4]
        warn = "⚠️" if int(pct.rstrip("%")) >= 80 else "✅"
        send(token, chat_id,
             f"{warn} *Disk (/)* \n\n"
             f"Used: `{used}`  Available: `{avail}`  ({pct} full)\n\n"
             f"```{header}\n{data}```")
    else:
        send(token, chat_id, f"```{r.stdout.strip()}```")


def cmd_soul_start(token: str, chat_id: str) -> None:
    """Step 1 of 2: prompt the user to send their SOUL.md file."""
    passphrase = _cfg("OPENCLAW_VAULT_PASSPHRASE")
    if not passphrase:
        send(token, chat_id,
             "❌ `OPENCLAW_VAULT_PASSPHRASE` is not set in `~/.openclaw/.env`.\n"
             "Cannot encrypt a new SOUL without it.")
        return
    SOUL_PENDING_FLAG.write_text("waiting")
    send(token, chat_id,
         "🧠 *Soul update ready.*\n\n"
         "Send your `SOUL.md` file now.\n\n"
         "I will:\n"
         "1. Read the markdown content directly\n"
         "2. Back up the current `SOUL.md.enc`\n"
         "3. Re-encrypt with the existing vault passphrase\n"
         "4. Restart the gateway\n\n"
         "_Send /cancel to abort._")


def cmd_soul_process(token: str, chat_id: str, document: dict) -> None:
    """Step 2 of 2: receive SOUL.md, encrypt, install."""
    SOUL_PENDING_FLAG.unlink(missing_ok=True)

    file_name = document.get("file_name", "")
    if not file_name.lower().endswith(".md"):
        send(token, chat_id,
             f"❌ Expected a `.md` file, got `{file_name}`.\n"
             "Send `/soul` again and upload your `SOUL.md`.")
        return

    passphrase = _cfg("OPENCLAW_VAULT_PASSPHRASE")
    if not passphrase:
        send(token, chat_id, "❌ `OPENCLAW_VAULT_PASSPHRASE` not set — cannot encrypt.")
        return

    token_val = _require("MGMT_BOT_TOKEN")
    send(token, chat_id, "⬇️ Downloading SOUL.md…")

    try:
        file_path_tg = get_file(token_val, document["file_id"])
        if not file_path_tg:
            raise RuntimeError("Could not get file path from Telegram.")

        with tempfile.TemporaryDirectory() as tmp_dir:
            md_path = Path(tmp_dir) / file_name
            download_file(token_val, file_path_tg, md_path)
            plaintext = md_path.read_text(encoding="utf-8")

    except RuntimeError as e:
        send(token, chat_id, f"❌ Download failed:\n```{e}```")
        return
    except Exception as e:
        send(token, chat_id, f"❌ Unexpected error:\n```{e}```")
        return

    if not plaintext.strip():
        send(token, chat_id, "❌ File is empty — no changes made.")
        return

    send(token, chat_id, "🔐 Encrypting new SOUL…")
    try:
        encrypted = _encrypt_soul(plaintext, passphrase)
    except ImportError:
        send(token, chat_id,
             "❌ `cryptography` Python package not installed.\n"
             "Run: `pip3 install --break-system-packages cryptography`")
        return
    except Exception as e:
        send(token, chat_id, f"❌ Encryption failed:\n```{e}```")
        return

    vault = _vault_dir()
    vault.mkdir(parents=True, exist_ok=True)
    enc_path = vault / "SOUL.md.enc"
    bak_path = vault / "SOUL.md.enc.bak"

    try:
        if enc_path.exists():
            enc_path.rename(bak_path)
            send(token, chat_id, f"📦 Old SOUL backed up to `SOUL.md.enc.bak`")
        enc_path.write_bytes(encrypted)
    except Exception as e:
        send(token, chat_id, f"❌ Failed to write vault file:\n```{e}```")
        return

    send(token, chat_id, "🔄 Restarting gateway to load new SOUL…")
    ok, msg = _restart_gateway()

    preview_lines = plaintext.strip().splitlines()[:5]
    preview       = "\n".join(preview_lines)

    send(token, chat_id,
         f"{'✅' if ok else '⚠️'} *Soul update complete.*\n\n"
         f"```{preview}…```\n\n"
         f"_{len(plaintext):,} characters encrypted and installed._\n"
         f"{'✅ Gateway restarted.' if ok else f'⚠️ {msg}'}")


def _collect_route_urls(project_dir: Path, base_url: str) -> str:
    """Scan a Next.js project and return a formatted list of all testable URLs."""
    base = base_url.rstrip("/")
    routes: list[tuple[str, str]] = []  # (label, path)

    # Detect Next.js app router (app/) or pages router (pages/)
    app_dir   = project_dir / "app"
    pages_dir = project_dir / "pages"

    def _label(path: str) -> str:
        low = path.lower()
        if "/api/" in low or low.startswith("api/"):
            return "🔌 API"
        if "admin" in low:
            return "🔐 Admin"
        if path in ("/", ""):
            return "🏠 Home"
        return "📄 Page"

    seen: set[str] = set()

    def _add(path: str) -> None:
        if path not in seen:
            seen.add(path)
            routes.append((_label(path), path))

    if app_dir.exists():
        for item in sorted(app_dir.rglob("page.tsx")) + sorted(app_dir.rglob("page.ts")) + \
                    sorted(app_dir.rglob("page.jsx")) + sorted(app_dir.rglob("page.js")):
            rel = item.parent.relative_to(app_dir)
            path = "/" + str(rel).replace("\\", "/") if str(rel) != "." else "/"
            # Skip dynamic catch-all segments for cleanliness
            if "[[" in path:
                continue
            # Turn [slug] into :slug for display
            display = re.sub(r'\[([^\]]+)\]', r':\1', path)
            _add(display)
        for item in sorted(app_dir.rglob("route.tsx")) + sorted(app_dir.rglob("route.ts")) + \
                    sorted(app_dir.rglob("route.js")):
            rel = item.parent.relative_to(app_dir)
            path = "/api/" + str(rel).replace("\\", "/") if "api" not in str(rel) else \
                   "/" + str(rel).replace("\\", "/")
            display = re.sub(r'\[([^\]]+)\]', r':\1', path)
            _add(display)

    elif pages_dir.exists():
        for item in sorted(pages_dir.rglob("*.tsx")) + sorted(pages_dir.rglob("*.ts")) + \
                    sorted(pages_dir.rglob("*.jsx")) + sorted(pages_dir.rglob("*.js")):
            rel = str(item.relative_to(pages_dir).with_suffix("")).replace("\\", "/")
            if rel.startswith("_") or rel.startswith("api/_"):
                continue
            path = "/" if rel in ("index", "Index") else "/" + rel
            display = re.sub(r'\[([^\]]+)\]', r':\1', path)
            _add(display)

    # Fallback: at least show the root
    if not routes:
        _add("/")

    lines = []
    for label, path in routes:
        lines.append(f"{label} `{base}{path}`")

    return "\n".join(lines)


def _load_vercel_creds() -> tuple[str, str]:
    """Return (vercel_token, vercel_scope) from ~/.openclaw/.env."""
    env_file = STATE_DIR / ".env"
    token, scope = "", ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("VERCEL_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"')
            if line.startswith("VERCEL_SCOPE="):
                scope = line.split("=", 1)[1].strip().strip('"')
    return token, scope


def _dev_env() -> dict:
    """Return an env dict that adds npm/node global bin dirs to PATH.

    The mgmt-bot runs as a systemd service with a minimal PATH, so tools
    installed globally via npm (like vercel) are invisible without this.
    We extend PATH with all common npm global bin locations so every
    dev subprocess can find node tools regardless of how they were installed.
    """
    env  = os.environ.copy()
    home = str(Path.home())
    extra = [
        f"{home}/.npm-global/bin",     # npm prefix = ~/.npm-global
        f"{home}/.local/bin",           # pip / manual installs
        f"{home}/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    existing = env.get("PATH", "")
    env["PATH"] = ":".join(extra) + (":" + existing if existing else "")
    return env


def _find_vercel() -> list[str]:
    """Return the command list to invoke the Vercel CLI.

    Checks PATH (via shutil.which using the extended dev env), then falls
    back to npx so we never hard-code a specific install location.
    """
    import shutil
    dev_path = _dev_env().get("PATH", "")
    vercel   = shutil.which("vercel", path=dev_path)
    if vercel:
        return [vercel]
    # Fall back to npx — it resolves global packages even off PATH
    npx = shutil.which("npx", path=dev_path) or "npx"
    return [npx, "--yes", "vercel"]


def _preview_state_path(project_dir: Path) -> Path:
    return project_dir / ".preview-state.json"


def _load_preview_state(project_dir: Path) -> dict:
    p = _preview_state_path(project_dir)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def _save_preview_state(project_dir: Path, project: str, new_url: str) -> str | None:
    """Persist the new canonical preview URL; return the old URL if one existed."""
    state    = _load_preview_state(project_dir)
    old_url  = state.get("current_url")
    now      = __import__("datetime").datetime.utcnow().isoformat()
    new_state: dict = {
        "project":    project,
        "current_url": new_url,
        "created_at": now,
    }
    if old_url and old_url != new_url:
        new_state["superseded_url"] = old_url
        new_state["superseded_at"]  = now
    _preview_state_path(project_dir).write_text(json.dumps(new_state, indent=2))
    return old_url if old_url != new_url else None


def _delete_vercel_preview(old_url: str, vercel_token: str, vercel_scope: str,
                            env: dict) -> bool:
    """Remove a stale Vercel preview deployment. Returns True on success."""
    vercel_bin = _find_vercel()
    cmd = vercel_bin + ["remove", old_url, "--yes", "--token", vercel_token, "--safe"]
    if vercel_scope:
        cmd += ["--scope", vercel_scope]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    if r.returncode != 0 and "You cannot set your Personal Account" in (r.stdout + r.stderr):
        cmd2 = [c for c in cmd if c != vercel_scope and c != "--scope"]
        r = subprocess.run(cmd2, capture_output=True, text=True, timeout=60, env=env)
    return r.returncode == 0


def _run_dev_pipeline(token: str, chat_id: str, project_dir: Path, project: str) -> None:
    """Core pipeline: npm install → npm run build → vercel preview.

    Tracks one canonical preview URL per project in .preview-state.json.
    When a new preview is created the previous one is deleted from Vercel
    so only the current preview is ever live.
    """
    vercel_token, vercel_scope = _load_vercel_creds()
    if not vercel_token:
        send(token, chat_id, "❌ `VERCEL_TOKEN` not set in `~/.openclaw/.env`")
        return

    env = _dev_env()

    send(token, chat_id, f"📦 Running `npm install` in `{project}`…")
    install = subprocess.run(
        ["npm", "install"],
        cwd=str(project_dir),
        capture_output=True, text=True, timeout=300,
        env=env,
    )
    if install.returncode != 0:
        tail = (install.stdout + install.stderr).strip()[-1500:]
        send(token, chat_id, f"❌ `npm install` failed:\n```{tail}```")
        return

    send(token, chat_id, "✅ `npm install` done. Running `npm run build`…")
    build = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(project_dir),
        capture_output=True, text=True, timeout=300,
        env=env,
    )
    if build.returncode != 0:
        tail = (build.stdout + build.stderr).strip()[-1500:]
        send(token, chat_id, f"❌ `npm run build` failed:\n```{tail}```")
        return

    vercel_bin = _find_vercel()
    send(token, chat_id, f"✅ Build passed. Deploying Vercel preview…")

    def _run_vercel(with_scope: bool) -> subprocess.CompletedProcess:
        cmd = vercel_bin + ["--token", vercel_token, "--yes"]
        if with_scope and vercel_scope:
            cmd += ["--scope", vercel_scope]
        return subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=300,
            env=env,
        )

    vercel = _run_vercel(with_scope=True)
    vercel_out = (vercel.stdout + vercel.stderr).strip()

    # Vercel CLI rejects --scope for personal accounts; retry without it
    if "You cannot set your Personal Account as the scope" in vercel_out:
        vercel = _run_vercel(with_scope=False)
        vercel_out = (vercel.stdout + vercel.stderr).strip()

    urls = re.findall(r'https://[^\s]+\.vercel\.app', vercel_out)
    preview_url = urls[-1] if urls else None

    if preview_url:
        # Track canonical preview — delete the previous one if it exists
        old_url = _save_preview_state(project_dir, project, preview_url)
        cleanup_note = ""
        if old_url:
            deleted = _delete_vercel_preview(old_url, vercel_token, vercel_scope, env)
            if deleted:
                cleanup_note = f"\n_Previous preview deleted: `{old_url}`_"
            else:
                cleanup_note = f"\n_⚠️ Could not delete previous preview — remove manually: `{old_url}`_"

        url_lines = _collect_route_urls(project_dir, preview_url)
        send(token, chat_id,
             f"🚀 *Preview ready — {project}*\n\n"
             f"{url_lines}"
             f"{cleanup_note}\n\n"
             f"Review it, then reply:\n"
             f"• `deploy {project}` — go live\n"
             f"• `reject {project}` — discard")
    else:
        tail = vercel_out[-1500:]
        send(token, chat_id,
             f"⚠️ Vercel ran but no preview URL found.\n\n```{tail}```\n\n"
             f"Check https://vercel.com/dashboard manually.")


def cmd_dev_run(token: str, chat_id: str, project: str) -> None:
    """Manual: npm install + build + vercel preview for a workspace project."""
    if not project:
        send(token, chat_id,
             "❌ Usage: `/dev-run <project-name>`\n"
             "Example: `/dev-run george-dean-portfolio`")
        return
    project_dir = STATE_DIR / "workspace" / "projects" / project
    if not project_dir.exists():
        send(token, chat_id,
             f"❌ Project not found: `{project_dir}`")
        return
    _run_dev_pipeline(token, chat_id, project_dir, project)


def cmd_dev_test(token: str, chat_id: str, project: str) -> None:
    """Run lint + typecheck + build for a workspace project."""
    if not project:
        send(token, chat_id,
             "❌ Usage: `/dev-test <project-name>`\n"
             "Example: `/dev-test george-dean-portfolio`")
        return

    projects_dir = STATE_DIR / "workspace" / "projects"
    project_dir  = projects_dir / project

    if not project_dir.exists():
        send(token, chat_id,
             f"❌ Project not found: `{project_dir}`\n"
             f"Check the name and try again.")
        return

    send(token, chat_id, f"🧪 Testing `{project}`…\n\n📦 Running `npm install` first…")
    env = _dev_env()
    install = subprocess.run(
        ["npm", "install"],
        cwd=str(project_dir),
        capture_output=True, text=True, timeout=300,
        env=env,
    )
    if install.returncode != 0:
        tail = (install.stdout + install.stderr).strip()[-1000:]
        send(token, chat_id, f"❌ `npm install` failed:\n```{tail}```")
        return

    results = []
    pkg = (project_dir / "package.json").read_text() if (project_dir / "package.json").exists() else ""

    steps = [
        ("lint",       "npm run lint"),
        ("typecheck",  "npm run typecheck"),
        ("build",      "npm run build"),
        ("test",       "npm test"),
    ]

    failed = False
    for key, cmd_str in steps:
        if f'"scripts"' in pkg and f'"{key}"' not in pkg:
            results.append(f"⏭ `{cmd_str}` — skipped (not in package.json)")
            continue
        r = subprocess.run(
            cmd_str.split(),
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=180,
            env=env,
        )
        if r.returncode == 0:
            results.append(f"✅ `{cmd_str}` — passed")
        else:
            tail = (r.stdout + r.stderr).strip()[-800:]
            results.append(f"❌ `{cmd_str}` — FAILED\n```{tail}```")
            failed = True
            break

    summary = "\n".join(results)
    icon = "❌" if failed else "✅"
    send(token, chat_id,
         f"{icon} *Test results — {project}*\n\n{summary}\n\n"
         + ("Fix the errors above and run `/dev-test` again." if failed
            else f"All checks passed. Run `/dev-run {project}` to generate a preview."))


def cmd_sp_sync(token: str, chat_id: str) -> None:
    """Force an immediate SharePoint content mirror sync."""
    poller = STATE_DIR / "integrations/microsoft/sharepoint_cache_poller.py"
    if not poller.exists():
        send(token, chat_id,
             f"❌ SharePoint cache poller not found at `{poller}`.\n"
             f"Run `/install` to deploy it.")
        return

    send(token, chat_id, "🔄 Syncing SharePoint content mirror… _(this may take 1–2 minutes)_")
    sync_started_at = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            ["python3", str(poller)],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        send(token, chat_id, "⏱ SharePoint sync timed out after 5 minutes.")
        return
    except Exception as e:
        send(token, chat_id, f"❌ Sync failed unexpectedly:\n```{e}```")
        return

    output = (result.stdout + result.stderr).strip()

    # Treat non-zero exit as a hard failure — never read stale manifest
    if result.returncode != 0:
        tail = "\n".join(output.splitlines()[-20:])
        send(token, chat_id,
             f"❌ *SharePoint sync failed* (exit {result.returncode}):\n```{tail}```")
        return

    # Poller succeeded — read manifest to confirm it was written this run
    manifest_path = STATE_DIR / "workspace" / "sharepoint-cache" / ".manifest.json"
    try:
        manifest   = json.loads(manifest_path.read_text())
        synced_at  = manifest.get("synced_at", "")

        # Verify manifest was written during this sync run by comparing its
        # synced_at timestamp against the moment the bot invoked the poller.
        # This avoids false stale warnings from arbitrary time windows and is
        # accurate regardless of how long a large-library sync takes.
        if synced_at:
            try:
                manifest_dt = datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
                # Allow up to 10s clock skew between Pi and UTC time source
                cmd_started = sync_started_at if sync_started_at.tzinfo else sync_started_at.replace(tzinfo=timezone.utc)
                if manifest_dt < cmd_started - timedelta(seconds=10):
                    raise ValueError(
                        f"Manifest timestamp {synced_at} predates this sync run "
                        f"(started {sync_started_at.strftime('%H:%M:%S')} UTC)"
                    )
            except (ValueError, TypeError) as age_err:
                tail = "\n".join(output.splitlines()[-10:])
                send(token, chat_id,
                     f"⚠️ *SharePoint sync ran but manifest looks stale*:\n"
                     f"_{age_err}_\n\n```{tail}```")
                return

        files_cached  = manifest.get("files_cached",  0)
        files_fresh   = manifest.get("files_fresh",   files_cached)
        files_stale   = manifest.get("files_stale",   0)
        files_skipped = manifest.get("files_skipped", 0)
        orphans       = len(manifest.get("orphans_deleted", []))
        synced_label  = synced_at[:16].replace("T", " ")

        cache_dir = STATE_DIR / "workspace" / "sharepoint-cache"
        total_kb  = sum(
            f.stat().st_size for f in cache_dir.rglob("*")
            if f.is_file() and not f.name.startswith(".")
        ) // 1024

        stale_line  = f"\n⏳ Stale (kept from previous run): {files_stale}" if files_stale else ""
        orphan_line = f"\n🗑 Orphans/ineligible deleted: {orphans}" if orphans else ""

        skipped_lines = []
        for rel_path, meta in manifest.get("skipped", {}).items():
            reason   = meta.get("reason_detail", meta.get("reason", "?"))
            size     = meta.get("size", 0)
            size_str = f"{size // 1024:,} KB" if size else "empty"
            skipped_lines.append(f"  • `{rel_path}` ({size_str}) — {reason}")

        skipped_summary = ""
        if skipped_lines:
            skipped_summary = "\n\n*Skipped:*\n" + "\n".join(skipped_lines[:10])
            if len(skipped_lines) > 10:
                skipped_summary += f"\n  … and {len(skipped_lines) - 10} more (see SHAREPOINT_INDEX.md)"

        send(token, chat_id,
             f"✅ *SharePoint sync complete* — {synced_label}\n\n"
             f"📄 Files in cache: {files_cached} ({files_fresh} fresh"
             f"{f', {files_stale} stale' if files_stale else ''})\n"
             f"⚠️ Files skipped: {files_skipped}\n"
             f"💾 Total cache: {total_kb:,} KB"
             f"{orphan_line}"
             f"{stale_line}"
             f"{skipped_summary}")

    except Exception as e:
        tail = "\n".join(output.splitlines()[-10:])
        send(token, chat_id,
             f"⚠️ *SharePoint sync ran but manifest could not be parsed*:\n"
             f"_{e}_\n\n```{tail}```")


def cmd_cancel(token: str, chat_id: str) -> None:
    SOUL_PENDING_FLAG.unlink(missing_ok=True)
    send(token, chat_id, "↩️ Cancelled.")


def cmd_help(token: str, chat_id: str) -> None:
    send(token, chat_id,
         "*OpenClaw Management Bot*\n\n"
         "*System*\n"
         "/status — model, gateway state, uptime, reboot safety\n"
         "/health — run system health check now\n"
         "/logs — recent errors across all poller logs\n"
         "/disk — disk space on the Pi\n\n"
         "*Provider*\n"
         "/anthropic — switch to Anthropic API + restart gateway\n"
         "/openai — switch to OpenAI API + restart gateway\n"
         "/codex — switch to OpenAI Codex gpt-5.4 (full) + restart gateway\n"
         "/codexmini — switch to OpenAI Codex gpt-5.4-mini (cheaper/faster) + restart\n\n"
         "*Services*\n"
         "/restart — restart the L1 gateway\n"
         "/garmin — manually trigger the Garmin poller\n"
         "/yt-add <url> [label] — add a YouTube channel to the transcript poller\n"
         "/yt-list — list configured YouTube channels\n"
         "/yt-run — trigger the YouTube channel poller now\n"
         "/pull — git pull latest from GitHub\n"
         "/install — git pull + run install script (sources .env automatically)\n"
         "/reboot — reboot Pi (refused if not safe)\n\n"
         "*Dev Workflow*\n"
         "/dev-run <project> — npm install + build + Vercel preview URL\n"
         "/dev-test <project> — npm install + lint + typecheck + build\n"
         "/dev-queue — show queued commands waiting from L1\n"
         "/dev-pause — stop auto-executing L1 dev commands (review mode)\n"
         "/dev-resume — resume auto-executing L1 dev commands\n\n"
         "_L1 queues git/npm work via .dev-cmd.json — mgmt-bot executes it._\n"
         "_Supported ops: git\\_clone · git\\_pull · git\\_branch · git\\_commit\\_push_\n"
         "_git\\_merge\\_main · git\\_delete\\_branch · npm\\_install · npm\\_upgrade · npm\\_run_\n\n"
         "*SharePoint*\n"
         "/sp-sync — force immediate SharePoint content mirror refresh\n\n"
         "*Identity*\n"
         "/soul — upload new SOUL.md (send as a .md file)\n\n"
         "/help — this message\n"
         "/cancel — cancel a pending operation")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

# Telegram menu commands registered via setMyCommands.
# Telegram only allows a-z, 0-9, and underscore in registered command names,
# so commands with dashes (dev-run, dev-test, sp-sync) are registered with
# underscores here. Both forms are accepted by the handler (see COMMANDS below).
MENU_COMMANDS = [
    # System
    ("status",    "Current provider, service state, Pi uptime"),
    ("health",    "Run system health check now"),
    ("logs",      "Show recent errors across all poller logs"),
    ("disk",      "Disk space on the Pi"),
    # Control
    ("restart",   "Restart the L1 gateway service"),
    ("pull",      "Git pull latest from GitHub"),
    ("install",   "Git pull + run install script"),
    ("reboot",    "Reboot the Pi (refused if not safe)"),
    # Model switching
    ("openai",    "Switch to OpenAI API model"),
    ("anthropic", "Switch to Anthropic API model"),
    ("codex",     "Switch to OpenAI Codex gpt-5.4 (full)"),
    ("codexmini", "Switch to OpenAI Codex gpt-5.4-mini (cheaper/faster)"),
    # Integrations
    ("garmin",    "Manually trigger the Garmin poller"),
    ("yt_add",    "Add a YouTube channel — /yt-add <url> [label]"),
    ("yt_list",   "List configured YouTube channels"),
    ("yt_run",    "Trigger the YouTube channel poller now"),
    ("sp_sync",   "Force SharePoint content mirror refresh"),
    # Dev workflow
    ("dev_run",    "Build + Vercel preview — specify project name"),
    ("dev_test",   "Lint + typecheck + build — specify project name"),
    ("dev_queue",  "Show pending dev commands from L1"),
    ("dev_pause",  "Pause L1 dev command auto-execution"),
    ("dev_resume", "Resume L1 dev command auto-execution"),
    # Identity / misc
    ("soul",      "Upload a new SOUL.md (.md file)"),
    ("cancel",    "Cancel a pending operation"),
    ("help",      "Show all commands"),
]


def _register_commands(token: str) -> None:
    """Register the command menu with Telegram so / shows a pickable list."""
    payload = json.dumps({
        "commands": [
            {"command": cmd, "description": desc}
            for cmd, desc in MENU_COMMANDS
        ]
    }).encode()

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/setMyCommands",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print(f"[mgmt-bot] Command menu registered ({len(MENU_COMMANDS)} commands)")
            else:
                print(f"[mgmt-bot] setMyCommands warning: {result}", file=sys.stderr)
    except Exception as e:
        print(f"[mgmt-bot] setMyCommands failed (non-fatal): {e}", file=sys.stderr)



# ---------------------------------------------------------------------------
# Dev-command queue — L1 writes .dev-cmd.json; mgmt-bot executes it
# ---------------------------------------------------------------------------
#
# Supported operations (whitelist — nothing else is executed):
#
#   git_clone        Clone a GitHub repo into workspace/projects/<project>
#                    args: {url: "https://github.com/owner/repo.git", branch?: "main"}
#
#   git_pull         git pull in the project directory
#                    args: {}
#
#   git_branch       Create and checkout a new branch
#                    args: {branch: "patch/short-slug"}
#
#   git_commit_push  git add -A, commit, push to current (or named) branch
#                    args: {message: "feat: ...", branch?: "main"}
#
#   git_merge_main   Merge a feature branch into main and push
#                    args: {branch: "patch/short-slug"}
#
#   git_delete_branch  Delete branch locally and on remote
#                    args: {branch: "patch/short-slug"}
#
#   npm_install      npm install (from existing package.json)
#                    args: {}
#
#   npm_upgrade      Install / upgrade a specific package
#                    args: {package: "next@latest"}
#                    Package arg must match: <name>@<version> — no shell chars
#
#   npm_run          Run a named npm script (build/lint/typecheck/test only)
#                    args: {script: "build"}
#
# Pause control:
#   Create  ~/.openclaw/workspace/.dev-cmd-paused  →  queue pauses
#   Delete  ~/.openclaw/workspace/.dev-cmd-paused  →  queue resumes
#
# File format — L1 writes to ~/.openclaw/workspace/projects/<project>/.dev-cmd.json:
#   {
#     "project":      "george-dean-portfolio",
#     "operation":    "npm_upgrade",
#     "args":         {"package": "next@latest"},
#     "message":      "Human-readable description shown in Telegram",
#     "triggered_at": "2026-04-13T10:00:00"
#   }
# ---------------------------------------------------------------------------

DEV_CMD_PAUSE_FLAG = STATE_DIR / "workspace" / ".dev-cmd-paused"

# Only these npm scripts may be run via npm_run
_NPM_SCRIPT_ALLOWLIST = {"build", "lint", "typecheck", "test", "type-check"}

# GitHub clone URLs must start with this prefix
_GITHUB_URL_PREFIX = "https://github.com/"

_NPM_PACKAGE_RE = re.compile(r'^[\w@][\w@./-]*$')


def _dev_cmd_paused() -> bool:
    return DEV_CMD_PAUSE_FLAG.exists()


def _validate_project_path(project_dir: Path) -> bool:
    """Ensure the project directory is inside workspace/projects/ — no path traversal."""
    projects_root = STATE_DIR / "workspace" / "projects"
    try:
        project_dir.resolve().relative_to(projects_root.resolve())
        return True
    except ValueError:
        return False


def _execute_dev_cmd(token: str, chat_id: str, cmd_file: Path) -> None:
    """Parse a .dev-cmd.json file, validate, execute the whitelisted operation."""
    try:
        data = json.loads(cmd_file.read_text())
    except Exception as e:
        send(token, chat_id, f"⚠️ Dev-cmd parse error in `{cmd_file}`: {e}")
        cmd_file.unlink(missing_ok=True)
        return

    project   = data.get("project", cmd_file.parent.name)
    operation = data.get("operation", "").strip()
    args      = data.get("args", {}) if isinstance(data.get("args"), dict) else {}
    message   = data.get("message", "")

    project_dir = STATE_DIR / "workspace" / "projects" / project
    cmd_file.unlink(missing_ok=True)   # consume immediately

    send(token, chat_id,
         f"🔧 *Dev-cmd — {project}*\n"
         f"`{operation}`"
         + (f"\n_{message}_" if message else ""))

    env = _dev_env()

    def run(cmd: list, cwd: Path | None = None, timeout: int = 120) -> tuple[int, str]:
        r = subprocess.run(cmd, cwd=str(cwd or project_dir),
                           capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout + r.stderr).strip()

    def ok(detail: str = "") -> None:
        send(token, chat_id, f"✅ `{operation}` done" + (f"\n```{detail[-800:]}```" if detail else ""))

    def fail(reason: str) -> None:
        send(token, chat_id, f"❌ `{operation}` failed\n```{reason[-1200:]}```")

    # ── Validate project path ────────────────────────────────────────────────
    if not _validate_project_path(project_dir):
        fail(f"Invalid project path: {project_dir}")
        return

    # ── Operations ───────────────────────────────────────────────────────────

    if operation == "git_clone":
        url    = args.get("url", "")
        branch = args.get("branch", "main")
        if not url.startswith(_GITHUB_URL_PREFIX):
            fail(f"git_clone: url must start with {_GITHUB_URL_PREFIX}")
            return
        token_val = os.environ.get("GITHUB_TOKEN", "")
        if token_val:
            auth_url = url.replace("https://", f"https://{token_val}@")
        else:
            auth_url = url
        projects_root = STATE_DIR / "workspace" / "projects"
        projects_root.mkdir(parents=True, exist_ok=True)
        rc, out = run(["git", "clone", "--branch", branch, auth_url, str(project_dir)],
                      cwd=projects_root, timeout=120)
        if rc == 0:
            ok(out)
        else:
            fail(out)

    elif operation == "git_pull":
        if not project_dir.exists():
            fail(f"Project dir not found: {project_dir}")
            return
        rc, out = run(["git", "pull"])
        if rc == 0:
            ok(out)
        else:
            fail(out)

    elif operation == "git_branch":
        branch = args.get("branch", "").strip()
        if not branch or "/" not in branch:
            fail("git_branch: branch must be in format patch/slug or feature/slug")
            return
        rc, out = run(["git", "checkout", "-b", branch])
        if rc == 0:
            ok(out)
        else:
            fail(out)

    elif operation == "git_commit_push":
        msg    = args.get("message", "chore: update").strip()
        branch = args.get("branch", "")
        rc, out = run(["git", "add", "-A"])
        if rc != 0:
            fail(out); return
        rc, out = run(["git", "commit", "-m", msg])
        if rc != 0 and "nothing to commit" not in out:
            fail(out); return
        push_args = ["git", "push", "-u", "origin"]
        if branch:
            push_args.append(branch)
        else:
            push_args.append("HEAD")

        # Inject token into remote URL for authenticated push, restore after
        token_val = os.environ.get("GITHUB_TOKEN", "")
        def _set_auth_url() -> str:
            """Set token-embedded remote URL; returns original URL."""
            orig = subprocess.run(["git", "remote", "get-url", "origin"],
                                  cwd=str(project_dir), capture_output=True, text=True).stdout.strip()
            if token_val and "github.com" in orig and f"{token_val}@" not in orig:
                subprocess.run(["git", "remote", "set-url", "origin",
                                orig.replace("https://", f"https://{token_val}@")],
                               cwd=str(project_dir), capture_output=True)
            return orig

        def _restore_url(orig: str) -> None:
            if token_val:
                clean = subprocess.run(["git", "remote", "get-url", "origin"],
                                       cwd=str(project_dir), capture_output=True,
                                       text=True).stdout.strip().replace(f"{token_val}@", "")
                subprocess.run(["git", "remote", "set-url", "origin", clean],
                               cwd=str(project_dir), capture_output=True)

        orig_url = _set_auth_url()
        rc, out  = run(push_args)

        # Auto-recover: if remote is ahead, pull --rebase then retry once
        if rc != 0 and ("fetch first" in out or "rejected" in out):
            send(token, chat_id,
                 f"⚠️ Push rejected (remote ahead) — running `git pull --rebase` then retrying…")
            pr_rc, pr_out = run(["git", "pull", "--rebase"], timeout=60)
            if pr_rc != 0:
                _restore_url(orig_url)
                fail(f"pull --rebase failed — resolve conflicts manually:\n{pr_out}"); return
            rc, out = run(push_args)

        _restore_url(orig_url)
        if rc == 0:
            ok(out)
        else:
            fail(out)

    elif operation == "git_merge_main":
        branch = args.get("branch", "").strip()
        if not branch:
            fail("git_merge_main: branch arg required"); return
        rc, out = run(["git", "checkout", "main"])
        if rc != 0:
            fail(out); return
        # Pull latest main before merging to avoid push rejection
        rc, out = run(["git", "pull", "--rebase"], timeout=60)
        if rc != 0:
            fail(f"git pull --rebase on main failed:\n{out}"); return
        rc, out = run(["git", "merge", branch, "--no-ff",
                       "-m", f"Merge {branch} into main (approved via Telegram)"])
        if rc != 0:
            fail(out); return
        rc, out = run(["git", "push", "origin", "main"])
        if rc == 0:
            ok(out)
        else:
            fail(out)

    elif operation == "git_delete_branch":
        branch = args.get("branch", "").strip()
        if not branch:
            fail("git_delete_branch: branch arg required"); return
        run(["git", "checkout", "main"])
        run(["git", "branch", "-D", branch])
        rc, out = run(["git", "push", "origin", "--delete", branch])
        ok(f"Branch {branch} deleted" + (f"\n{out}" if out else ""))

    elif operation == "npm_install":
        rc, out = run(["npm", "install"], timeout=300)
        if rc == 0:
            ok(out[-600:] if out else "")
        else:
            fail(out)

    elif operation == "npm_upgrade":
        package = args.get("package", "").strip()
        if not package or not _NPM_PACKAGE_RE.match(package):
            fail(f"npm_upgrade: invalid package name '{package}' — must match name@version")
            return
        rc, out = run(["npm", "install", package], timeout=300)
        if rc == 0:
            ok(out[-600:] if out else "")
        else:
            fail(out)

    elif operation == "npm_run":
        script = args.get("script", "").strip()
        if script not in _NPM_SCRIPT_ALLOWLIST:
            fail(f"npm_run: '{script}' not in allowed scripts {sorted(_NPM_SCRIPT_ALLOWLIST)}")
            return
        rc, out = run(["npm", "run", script], timeout=300)
        if rc == 0:
            ok(out[-800:] if out else "")
        else:
            fail(out)

    else:
        send(token, chat_id,
             f"⛔ Dev-cmd `{operation}` is not a recognised operation.\n"
             f"Allowed: git_clone, git_pull, git_branch, git_commit_push, "
             f"git_merge_main, git_delete_branch, npm_install, npm_upgrade, npm_run")


def _check_dev_cmds(token: str, chat_id: str) -> None:
    """Process any .dev-cmd.json files written by L1 in project directories."""
    if _dev_cmd_paused():
        return
    projects_dir = STATE_DIR / "workspace" / "projects"
    if not projects_dir.exists():
        return
    for cmd_file in sorted(projects_dir.glob("*/.dev-cmd.json")):
        try:
            _execute_dev_cmd(token, chat_id, cmd_file)
        except Exception as e:
            print(f"[mgmt-bot] Dev-cmd error ({cmd_file}): {e}", file=sys.stderr)
            send(token, chat_id, f"⚠️ Dev-cmd crashed on `{cmd_file.parent.name}`: {e}")
            cmd_file.unlink(missing_ok=True)


def cmd_dev_pause(token: str, chat_id: str) -> None:
    DEV_CMD_PAUSE_FLAG.parent.mkdir(parents=True, exist_ok=True)
    DEV_CMD_PAUSE_FLAG.touch()
    send(token, chat_id,
         "⏸ Dev-command queue *paused*.\n"
         "L1 can still write requests but they won't run until you send `/dev_resume`.")


def cmd_dev_resume(token: str, chat_id: str) -> None:
    DEV_CMD_PAUSE_FLAG.unlink(missing_ok=True)
    send(token, chat_id, "▶️ Dev-command queue *resumed*. Processing any pending commands now…")
    _check_dev_cmds(token, chat_id)


def cmd_dev_queue(token: str, chat_id: str) -> None:
    """Show all pending .dev-cmd.json files and the current pause state."""
    projects_dir = STATE_DIR / "workspace" / "projects"
    pending = sorted(projects_dir.glob("*/.dev-cmd.json")) if projects_dir.exists() else []
    paused  = _dev_cmd_paused()
    status  = "⏸ *Paused*" if paused else "▶️ *Running*"

    if not pending:
        send(token, chat_id, f"{status} — no pending dev commands.")
        return

    lines = [f"{status} — {len(pending)} pending command(s):\n"]
    for f in pending:
        try:
            d = json.loads(f.read_text())
            lines.append(f"• `{d.get('project','?')}` → `{d.get('operation','?')}` — {d.get('message','')}")
        except Exception:
            lines.append(f"• `{f}` (unreadable)")
    send(token, chat_id, "\n".join(lines))


def _check_dev_triggers(token: str, chat_id: str) -> None:
    """Auto-run the dev pipeline for any project that has a .pending-dev-run trigger file."""
    projects_dir = STATE_DIR / "workspace" / "projects"
    if not projects_dir.exists():
        return
    for trigger in sorted(projects_dir.glob("*/.pending-dev-run")):
        project     = trigger.parent.name
        project_dir = trigger.parent
        try:
            meta = json.loads(trigger.read_text()) if trigger.stat().st_size > 0 else {}
        except Exception:
            meta = {}
        change = meta.get("change", "")
        trigger.unlink(missing_ok=True)
        print(f"[mgmt-bot] Auto-trigger: {project} ({change})")
        header = f"🤖 *Auto-build triggered — {project}*"
        if change:
            header += f"\n_{change}_"
        send(token, chat_id, header)
        _run_dev_pipeline(token, chat_id, project_dir, project)


COMMANDS = {
    "/status":     cmd_status,
    "/openai":     lambda t, c: cmd_switch(t, c, "openai"),
    "/anthropic":  lambda t, c: cmd_switch(t, c, "anthropic"),
    "/codex":      lambda t, c: cmd_switch(t, c, "codex"),
    "/codexmini":  lambda t, c: cmd_switch(t, c, "codexmini"),
    "/restart":    cmd_restart,
    "/reboot":     cmd_reboot,
    "/pull":       cmd_pull,
    "/install":    cmd_install,
    "/health":     cmd_health,
    "/logs":       cmd_logs,
    "/garmin":     cmd_garmin,
    "/yt-list":    cmd_yt_list,
    "/yt_list":    cmd_yt_list,
    "/yt-run":     cmd_yt_run,
    "/yt_run":     cmd_yt_run,
    "/disk":       cmd_disk,
    "/soul":       cmd_soul_start,
    "/sp-sync":    cmd_sp_sync,
    "/sp_sync":    cmd_sp_sync,
    "/dev-run":    cmd_dev_run,
    "/dev_run":    cmd_dev_run,
    "/dev-test":   cmd_dev_test,
    "/dev_test":   cmd_dev_test,
    "/dev-pause":  cmd_dev_pause,
    "/dev_pause":  cmd_dev_pause,
    "/dev-resume": cmd_dev_resume,
    "/dev_resume": cmd_dev_resume,
    "/dev-queue":  cmd_dev_queue,
    "/dev_queue":  cmd_dev_queue,
    "/cancel":     cmd_cancel,
    "/help":       cmd_help,
    "/start":      cmd_help,
}


def main() -> None:
    _load_dotenv()

    token      = _require("MGMT_BOT_TOKEN")
    allowed_id = _require("MGMT_BOT_CHAT_ID")

    print(f"[mgmt-bot] Starting. Listening on chat_id={allowed_id}…")
    _register_commands(token)

    offset            = load_offset()
    last_trigger_check = 0.0

    while True:
        # Poll for AI-written trigger files every 30 s
        now = time.time()
        if now - last_trigger_check >= 30:
            try:
                _check_dev_triggers(token, allowed_id)
            except Exception as e:
                print(f"[mgmt-bot] Trigger check error: {e}", file=sys.stderr)
            try:
                _check_dev_cmds(token, allowed_id)
            except Exception as e:
                print(f"[mgmt-bot] Dev-cmd check error: {e}", file=sys.stderr)
            last_trigger_check = now

        # get_updates already handles its own exceptions and returns []
        updates = get_updates(token, offset)

        for update in updates:
            offset = update["update_id"] + 1
            save_offset(offset)

            msg     = update.get("message") or {}
            chat    = msg.get("chat", {})
            chat_id = str(chat.get("id", ""))
            text    = (msg.get("text") or "").strip()

            # Security: silently ignore anything not from the allowed chat
            if chat_id != allowed_id:
                continue

            # Handle document upload (soul update flow)
            document = msg.get("document")
            if document and SOUL_PENDING_FLAG.exists():
                print(f"[mgmt-bot] Document received for soul update: {document.get('file_name')}")
                try:
                    cmd_soul_process(token, chat_id, document)
                except Exception as e:
                    print(f"[mgmt-bot] Soul process error: {e}", file=sys.stderr)
                    send(token, chat_id, f"❌ Soul update error:\n```{e}```")
                continue

            if document and not SOUL_PENDING_FLAG.exists():
                send(token, chat_id,
                     "📎 File received, but I wasn't expecting one.\n"
                     "Send `/soul` first, then upload your `.docx`.")
                continue

            # Extract command and optional argument
            parts = text.split(maxsplit=1) if text else []
            cmd   = parts[0].split("@")[0].lower() if parts else ""
            arg   = parts[1].strip() if len(parts) > 1 else ""

            # Commands that take an argument (accept both dash and underscore forms)
            if cmd in ("/yt-add", "/yt_add"):
                print(f"[mgmt-bot] Command: {cmd} {arg!r} from {chat_id}")
                try:
                    cmd_yt_add(token, chat_id, arg)
                except Exception as e:
                    print(f"[mgmt-bot] Handler error ({cmd}): {e}", file=sys.stderr)
                    send(token, chat_id, f"❌ Error running `{cmd}`:\n```{e}```")
                continue

            if cmd in ("/dev-run", "/dev_run", "/dev-test", "/dev_test"):
                print(f"[mgmt-bot] Command: {cmd} {arg!r} from {chat_id}")
                try:
                    if cmd in ("/dev-run", "/dev_run"):
                        cmd_dev_run(token, chat_id, arg)
                    else:
                        cmd_dev_test(token, chat_id, arg)
                except Exception as e:
                    print(f"[mgmt-bot] Handler error ({cmd}): {e}", file=sys.stderr)
                    send(token, chat_id, f"❌ Error running `{cmd}`:\n```{e}```")
                continue

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
