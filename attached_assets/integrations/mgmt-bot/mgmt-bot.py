#!/usr/bin/env python3
"""
OpenClaw Management Bot — runs independently of the main gateway and LLM.

A separate Telegram bot that handles system management commands directly on
the Pi without touching the LLM. Works even when OpenAI is rate-limited or
the gateway is completely down.

COMMANDS
--------
  /status       — current provider, service state, Pi uptime
  /codex54full  — switch to Codex Web 5.4 full (default) and restart gateway
  /codex55full  — switch to Codex Web 5.5 full and restart gateway
  /codex53mini  — switch to Codex Web 5.3 mini and restart gateway
  /codex54mini  — switch to Codex Web 5.4 mini and restart gateway
  /sonnet45     — switch to Anthropic Sonnet 4.5 and restart gateway
  /sonnet46     — switch to Anthropic Sonnet 4.6 and restart gateway
  /opus46       — switch to Anthropic Opus 4.6 and restart gateway
  /gpt5mini     — switch to OpenAI GPT-5 mini and restart gateway
  /gpt54        — switch to OpenAI GPT-5.4 and restart gateway
  /qwen30b      — switch to Local Qwen3 Coder 30b 131k (Mac Mini) and restart gateway
  /restart      — restart the L1 gateway service
  /pull         — git pull latest from GitHub (does NOT reinstall)
  /reboot       — reboot the Pi (refused if auto-start safety check fails)
  /health       — run system health check now and show output
  /logs         — show recent errors across all poller logs
  /garmin       — manually trigger the Garmin poller
  /garmin-setup — one-time Garmin login (caches self-renewing token)
  /garmin-status— show Garmin token validity/age
  /yt-add       — add a YouTube channel to the transcript poller
  /yt-list      — list configured YouTube channels
  /yt-run       — trigger the YouTube channel poller now
  /ai-briefing  — run the AI briefing pipeline now or show current briefing status
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
  All model IDs below are OPTIONAL — each command has a built-in default and
  works out of the box. Set a var only to override the exact model ID string.
  OPENCLAW_CODEX_MODEL        override /codex54full, default openai-codex/gpt-5.4
  OPENCLAW_CODEX55_MODEL      override /codex55full, default openai-codex/gpt-5.5
  OPENCLAW_CODEX_MINI_MODEL   override /codex53mini, default openai-codex/gpt-5.3-codex-spark
  OPENCLAW_CODEX_MINI54_MODEL override /codex54mini, default openai-codex/gpt-5.4-mini
  OPENCLAW_ANTHROPIC_MODEL    override /sonnet45,    default anthropic/claude-sonnet-4-5
  OPENCLAW_SONNET_MODEL       override /sonnet46,    default anthropic/claude-sonnet-4-6
  OPENCLAW_OPUS_MODEL         override /opus46,      default anthropic/claude-opus-4-6
  OPENCLAW_OPENAI_MODEL       override /gpt5mini,    default openai/gpt-5-mini
  OPENCLAW_GPT54_MODEL        override /gpt54,       default openai/gpt-5.4
  OPENCLAW_LOCAL_QWEN30B_MODEL override /qwen30b,    default custom-mac-ollama/qwen3-coder-131k
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
     OPENCLAW_OPENAI_MODEL=openai/gpt-5-mini
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
# Written while a Codex re-auth is waiting for the user to sign in. If the bot
# is restarted mid-wait (e.g. by an install), the waiting thread dies silently;
# main() checks this marker on startup and tells the owner what happened.
CODEX_REAUTH_MARKER = STATE_DIR / "integrations/mgmt-bot/codex-reauth-in-progress"

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

def _audit(msg: str) -> None:
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    print(f"[mgmt-bot] {ts} {msg}", file=sys.stderr, flush=True)


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
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except Exception:
                _audit(f"Telegram API invalid JSON ({method}): {body[:500]}")
                return {"ok": False, "description": "invalid JSON response"}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        _audit(f"Telegram API HTTP error ({method}): {e}; body={body[:1000]}")
        try:
            return json.loads(body) if body else {"ok": False, "description": str(e)}
        except Exception:
            return {"ok": False, "description": f"{e}; {body[:300]}"}
    except Exception as e:
        _audit(f"Telegram API error ({method}): {e}")
        return {"ok": False, "description": str(e)}


def send(token: str, chat_id: str, text: str) -> bool:
    # Plain text first: management replies are operational, so reliability beats Markdown styling.
    _audit(f"sendMessage attempt chat_id={chat_id} chars={len(text)}")
    resp = _tg(token, "sendMessage", chat_id=chat_id, text=text)
    if resp.get("ok"):
        _audit("sendMessage ok")
        return True
    _audit(f"sendMessage failed: {resp.get('description', resp)}")
    return False


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
            if not result.get("ok"):
                # HTTP 200 but Telegram reported an API-level failure
                # (e.g. invalid token). Treat as a failure so backoff engages
                # instead of silently spinning.
                raise RuntimeError(
                    f"Telegram API not ok: {result.get('description', result)}"
                )
            get_updates._fail_count = 0
            return result.get("result", [])
    except Exception as e:
        # Sustained network/DNS failures (Errno -3 name resolution, Errno 101
        # unreachable, connection reset) would otherwise make this loop spin
        # ~once/second, flooding the log and hammering a network that's already
        # struggling. Back off exponentially (capped at 60s) and only log the
        # first failure and every 10th thereafter so the log stays readable.
        get_updates._fail_count = getattr(get_updates, "_fail_count", 0) + 1
        fails = get_updates._fail_count
        backoff = min(60, 2 ** min(fails, 6))
        if fails == 1 or fails % 10 == 0:
            print(
                f"[mgmt-bot] getUpdates error (x{fails}): {e}; backing off {backoff}s",
                file=sys.stderr,
            )
        time.sleep(backoff)
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


def _service_state_details(service: str) -> dict:
    r = subprocess.run(
        [
            "systemctl", "--user", "show", service,
            "--property=ActiveState,SubState,Result,ExecMainPID,LoadState,UnitFileState",
        ],
        capture_output=True, text=True, timeout=10,
    )
    props: dict[str, str] = {}
    for line in (r.stdout or "").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        props[k.strip()] = v.strip()
    return {
        "active": props.get("ActiveState") or "unknown",
        "sub": props.get("SubState") or "unknown",
        "result": props.get("Result") or "unknown",
        "pid": props.get("ExecMainPID") or "0",
        "load": props.get("LoadState") or "unknown",
        "unit_file": props.get("UnitFileState") or "unknown",
    }


def _restart_gateway() -> tuple[bool, str]:
    svc = _service()
    _audit(f"restart requested service={svc}")
    try:
        before = _service_state_details(svc)
        before_pid = (before.get("pid") or "0").strip()
        r = subprocess.run(
            ["systemctl", "--user", "restart", "--no-block", svc],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as e:
        _audit(f"restart launch exception service={svc}: {e}")
        return False, f"Restart launch failed: {e}"
    if r.returncode != 0:
        detail = (r.stderr.strip() or r.stdout.strip() or f"exit {r.returncode}")
        _audit(f"restart launch failed service={svc}: {detail}")
        return False, f"Restart failed: {detail}"

    deadline = time.time() + 90
    saw_transition = False
    last = before
    while time.time() < deadline:
        try:
            last = _service_state_details(svc)
        except Exception as e:
            _audit(f"restart poll exception service={svc}: {e}")
            time.sleep(2)
            continue

        active = last["active"]
        sub = last["sub"]
        result = last["result"]
        pid = (last["pid"] or "0").strip()
        pid_changed = pid not in {"", "0"} and pid != before_pid

        if active in {"activating", "deactivating", "reloading"}:
            saw_transition = True
            time.sleep(2)
            continue

        if active == "failed":
            _audit(f"restart failed service={svc} active={active} sub={sub} result={result}")
            return False, f"Restart failed: service entered failed/{sub} (result: {result})."

        if active == "inactive":
            if saw_transition:
                time.sleep(2)
                continue
            time.sleep(2)
            continue

        if active == "active":
            if saw_transition or pid_changed:
                _audit(
                    f"restart complete service={svc} active={active} sub={sub} pid={pid} "
                    f"result={result} before_pid={before_pid} pid_changed={pid_changed} "
                    f"saw_transition={saw_transition}"
                )
                if pid_changed:
                    return True, f"Gateway restarted successfully (active/{sub}, pid changed to {pid})."
                return True, f"Gateway restarted successfully (active/{sub})."
            time.sleep(2)
            continue

        time.sleep(2)

    summary = (
        f"active={last['active']}, sub={last['sub']}, result={last['result']}, "
        f"pid={last['pid']}, before_pid={before_pid}, saw_transition={saw_transition}"
    )
    _audit(f"restart timed out service={svc} {summary}")
    return False, f"Restart requested but service did not become healthy within 90s ({summary})."


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


# Model registry — every mgmt-bot model command maps to one entry here.
#   env_var        : ~/.openclaw/.env override for the exact model ID string
#                    (lets you correct a model name without editing this file)
#   default_model  : used when env_var is not set — works out of the box
#   api_key_var    : API key that MUST exist in .env before switching
#                    (None = OAuth / gateway-managed auth, no key needed)
#   gateway_prefix : provider prefix added to a bare model ID
#   label          : human-friendly name shown in Telegram replies
MODEL_REGISTRY = {
    # --- Codex Web (OAuth, no API key). gpt-5.4 is the daily-reset default. ---
    "codex54full": ("OPENCLAW_CODEX_MODEL",        "openai-codex/gpt-5.4",         None,            "openai-codex", "Codex 5.4 (full)"),
    "codex55full": ("OPENCLAW_CODEX55_MODEL",      "openai-codex/gpt-5.5",         None,            "openai-codex", "Codex 5.5 (full)"),
    "codex53mini": ("OPENCLAW_CODEX_MINI_MODEL",   "openai-codex/gpt-5.3-codex-spark", None,        "openai-codex", "Codex 5.3 Spark (Pro)"),
    "codex54mini": ("OPENCLAW_CODEX_MINI54_MODEL", "openai-codex/gpt-5.4-mini",    None,            "openai-codex", "Codex 5.4 mini"),
    # --- Anthropic API (auth handled internally by the gateway) ---
    "sonnet45":    ("OPENCLAW_ANTHROPIC_MODEL",    "anthropic/claude-sonnet-4-5",  None,            "anthropic",    "Anthropic Sonnet 4.5"),
    "sonnet46":    ("OPENCLAW_SONNET_MODEL",       "anthropic/claude-sonnet-4-6",  None,            "anthropic",    "Anthropic Sonnet 4.6"),
    "opus46":      ("OPENCLAW_OPUS_MODEL",         "anthropic/claude-opus-4-6",    None,            "anthropic",    "Anthropic Opus 4.6"),
    # --- OpenAI API (needs OPENAI_API_KEY) ---
    "gpt5mini":    ("OPENCLAW_OPENAI_MODEL",       "openai/gpt-5-mini",            "OPENAI_API_KEY", "openai",      "OpenAI GPT-5 mini"),
    "gpt54":       ("OPENCLAW_GPT54_MODEL",        "openai/gpt-5.4",               "OPENAI_API_KEY", "openai",      "OpenAI GPT-5.4"),
    # --- Local LLMs on the LAN (Mac Mini, OpenAI-compatible custom provider, no API key) ---
    # Model string is "<endpoint-id>/<model-id>" and must match the custom provider
    # already configured in openclaw.json. Override the exact string via .env if it drifts.
    # Registry keys are lowercase (incoming commands are lower-cased before dispatch).
    "qwen30b":     ("OPENCLAW_LOCAL_QWEN30B_MODEL", "custom-mac-ollama/qwen3-coder-131k",  None, "custom-mac-ollama", "Local Qwen3 Coder 30b 131k (Mac Mini)"),
}


def cmd_switch(token: str, chat_id: str, provider: str) -> None:
    spec = MODEL_REGISTRY.get(provider)
    if spec is None:
        send(token, chat_id, f"❌ Unknown model route `{provider}`.")
        return
    env_var, default_model, api_key_var, gateway_prefix, label = spec

    # .env override wins over the built-in default; defaults work out of the box.
    model = _cfg(env_var) or default_model
    if not model:
        send(token, chat_id,
             f"❌ `{env_var}` is not set in `~/.openclaw/.env`.\n"
             f"Add it and re-run the install script.")
        return

    # Validate the required API key is present in .env before switching.
    # Codex uses OAuth and Anthropic auth is gateway-managed (no key needed).
    if api_key_var and not _cfg(api_key_var):
        send(token, chat_id,
             f"❌ `{api_key_var}` is not set in `~/.openclaw/.env`.\n"
             f"Add it before switching to {label}.")
        return

    # Ensure the model has a provider prefix — the gateway requires it and
    # will incorrectly prepend "anthropic/" to any bare model ID.
    # If the value already contains "/" (e.g. openai-codex/gpt-5.4), use it
    # verbatim. Only add the correct gateway prefix for bare names.
    if "/" not in model:
        model = f"{gateway_prefix}/{model}"

    # Sanitize — strip any accidental shell-export prefix and trailing punctuation
    # e.g. "export openclaw_codex_mini_model=openai-codex/gpt-5.3-codex." → correct value
    import re as _re
    model = _re.sub(r'^export\s+\S+=', '', model).rstrip(".")

    try:
        config  = _read_config()
        provider_id = model.split("/", 1)[0] if "/" in model else gateway_prefix
        if provider_id.startswith("custom-") and provider_id not in config.get("models", {}).get("providers", {}):
            send(token, chat_id,
                 f"❌ Provider {provider_id} is not configured in openclaw.json yet.\n"
                 f"Run the protected config patch first, then retry {model}.")
            return
        current = _get_current_model(config)
        _audit(f"cmd_switch provider={provider} label={label} current={current} requested={model}")
        if current == model:
            send(token, chat_id, f"ℹ️ Already using {model} ({label}) — no change.")
            return
        config = _set_model(config, model)
        _write_config(config)
        after = _get_current_model(_read_config())
        _audit(f"cmd_switch config_written provider={provider} after={after}")
    except Exception as e:
        _audit(f"cmd_switch failed provider={provider}: {e}")
        send(token, chat_id, f"❌ Failed to update config: {e}")
        return

    send(token, chat_id, f"✅ Model set to {model} ({label})\nRestarting gateway…")
    ok, msg = _restart_gateway()
    try:
        proof_model = _get_current_model(_read_config())
    except Exception as e:
        proof_model = f"unreadable: {e}"
    svc_state = _service_status()
    _audit(f"cmd_switch complete provider={provider} ok={ok} model={proof_model} gateway={svc_state} msg={msg}")
    send(token, chat_id, f"{'✅' if ok else '❌'} {msg}\nModel now: {proof_model}\nGateway: {svc_state}")


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

    # Local edits to tracked files make `git pull` refuse to merge. GitHub is
    # authoritative for this repo, so auto-stash them (recoverable via
    # `git stash pop` on the Pi) instead of failing the pull.
    stash_note = ""
    try:
        st = subprocess.run(
            ["git", "-C", str(git_dir), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=60,
        )
        if st.stdout.strip():
            label = "mgmt-bot auto-stash before /pull " + time.strftime("%Y-%m-%d %H:%M:%S")
            sr = subprocess.run(
                ["git", "-C", str(git_dir), "stash", "push", "-m", label],
                capture_output=True, text=True, timeout=120,
            )
            if sr.returncode != 0:
                s_out = (sr.stdout + sr.stderr).strip()[-1500:]
                send(token, chat_id,
                     f"❌ Local changes found on the Pi but auto-stash failed — pull aborted.\n\n```{s_out}```")
                return
            stash_note = (f"⚠️ Local changes to tracked files were auto-stashed before pulling "
                          f"as “{label}” (recover with `git stash list` / `git stash pop`).\n")
    except Exception as e:
        send(token, chat_id, f"❌ Pre-pull check failed: `{e}`")
        return

    r = subprocess.run(
        ["git", "-C", str(git_dir), "pull", "--ff-only"],
        capture_output=True, text=True, timeout=120,
    )
    output = (r.stdout + r.stderr).strip()[-1500:]
    if r.returncode == 0:
        send(token, chat_id,
             f"✅ Pull complete:\n{stash_note}```{output}```\n\n"
             f"_Send /install to deploy the updated files._")
    else:
        send(token, chat_id, f"❌ Pull failed:\n{stash_note}```{output}```")


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

    send(token, chat_id,
         "🔧 Starting install in background…\n"
         "_(it will pull latest from GitHub first, then run the install script; "
         "you should get a Telegram message when it finishes, even after I restart)_")

    # Write a self-contained Python wrapper that:
    #   1. runs the install script via subprocess (capturing output)
    #   2. sends the result back to Telegram via urllib (no curl escaping issues)
    # Launched with start_new_session=True so it becomes its own session leader
    # and is NOT killed when systemd stops/restarts the mgmt-bot service.
    # Snapshot the vault passphrase NOW (from mgmt-bot's already-loaded env)
    # so the wrapper can inject it explicitly — avoids any interactive prompt.
    _vault_pass = _cfg("OPENCLAW_VAULT_PASSPHRASE", "")

    wrapper_path = Path("/tmp/openclaw-install-wrapper.py")
    wrapper_log_path = str(STATE_DIR / "integrations/mgmt-bot/install-wrapper.log")
    wrapper_launch_log_path = str(STATE_DIR / "integrations/mgmt-bot/install-wrapper-launch.log")
    wrapper_path.write_text(
        "#!/usr/bin/env python3\n"
        "import subprocess, urllib.request, urllib.error, json, sys, time, os\n"
        f"TOKEN   = {token!r}\n"
        f"CHAT_ID = {chat_id!r}\n"
        f"INSTALL = {str(install_sh)!r}\n"
        f"GIT_DIR = {str(git_dir)!r}\n"
        f"VAULT_PASS = {_vault_pass!r}\n"
        "\n"
        f"LOG = {wrapper_log_path!r}\n"
        "def log(line):\n"
        "    try:\n"
        "        with open(LOG, 'a') as f:\n"
        "            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + str(line) + '\\n')\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "# Hardcoded last-resort Telegram Bot API IPs (used only if DoH yields none).\n"
        "TG_IP_FALLBACK = ['149.154.167.220', '149.154.166.110']\n"
        "\n"
        "def _doh_resolve(host):\n"
        "    # Resolve via DNS-over-HTTPS at a LITERAL IP so it works even when the\n"
        "    # Pi's only resolver (Tailscale MagicDNS) is starved during install.\n"
        "    # Both endpoints' TLS certs carry their IP as a SAN, so cert checks pass.\n"
        "    import ssl\n"
        "    ips = []\n"
        "    for endpoint, path in (('1.1.1.1', '/dns-query'), ('8.8.8.8', '/resolve')):\n"
        "        try:\n"
        "            u = f'https://{endpoint}{path}?name={host}&type=A'\n"
        "            req = urllib.request.Request(u, headers={'accept': 'application/dns-json'})\n"
        "            ctx = ssl.create_default_context()\n"
        "            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:\n"
        "                data = json.loads(r.read().decode())\n"
        "            for ans in data.get('Answer', []):\n"
        "                if ans.get('type') == 1:\n"
        "                    ips.append(ans['data'])\n"
        "            if ips:\n"
        "                log(f'doh resolved {host} via {endpoint}: {ips}')\n"
        "                return ips\n"
        "        except Exception as e:\n"
        "            log(f'doh resolve via {endpoint} failed: {e}')\n"
        "    return ips\n"
        "\n"
        "def _send_by_ip(ip, payload, host='api.telegram.org'):\n"
        "    # POST to Telegram by IP with SNI=host so it bypasses system DNS but\n"
        "    # still validates the cert against api.telegram.org.\n"
        "    import ssl, socket\n"
        "    ctx = ssl.create_default_context()\n"
        "    raw = socket.create_connection((ip, 443), timeout=15)\n"
        "    try:\n"
        "        sock = ctx.wrap_socket(raw, server_hostname=host)\n"
        "        head = (f'POST /bot{TOKEN}/sendMessage HTTP/1.1\\r\\n'\n"
        "                f'Host: {host}\\r\\n'\n"
        "                'Content-Type: application/json\\r\\n'\n"
        "                f'Content-Length: {len(payload)}\\r\\n'\n"
        "                'Connection: close\\r\\n\\r\\n').encode()\n"
        "        sock.sendall(head + payload)\n"
        "        resp = b''\n"
        "        while True:\n"
        "            chunk = sock.recv(4096)\n"
        "            if not chunk:\n"
        "                break\n"
        "            resp += chunk\n"
        "        sock.close()\n"
        "        return resp.split(b'\\r\\n', 1)[0].decode('latin1', 'replace')\n"
        "    finally:\n"
        "        try:\n"
        "            raw.close()\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
        "def _send_dns_resilient(payload, mode):\n"
        "    # DoH-resolved IPs first, then the hardcoded fallback list.\n"
        "    ips = _doh_resolve('api.telegram.org') or []\n"
        "    for ip in ips + TG_IP_FALLBACK:\n"
        "        try:\n"
        "            status = _send_by_ip(ip, payload)\n"
        "            log(f'dns-resilient send via {ip} ({mode}): {status}')\n"
        "            if ' 200 ' in status:\n"
        "                return 'ok'\n"
        "            if ' 400 ' in status:\n"
        "                return 'bad400'\n"
        "        except Exception as e:\n"
        "            log(f'dns-resilient send via {ip} failed: {e}')\n"
        "    return 'fail'\n"
        "\n"
        "def tg(text):\n"
        "    # Retry hard. The install pegs the Pi CPU and the gateway restart\n"
        "    # can briefly starve tailscaled/MagicDNS, so api.telegram.org may\n"
        "    # fail to resolve via the SYSTEM resolver right when this fires.\n"
        "    # So: try the normal path, and on any network/DNS error fall back to\n"
        "    # a DNS-over-HTTPS resolve + send-by-IP that needs NO working system\n"
        "    # resolver. Keep trying for ~3 min so the completion message lands.\n"
        "    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'\n"
        "    md    = json.dumps({'chat_id': CHAT_ID, 'text': text,\n"
        "                        'parse_mode': 'Markdown'}).encode()\n"
        "    plain = json.dumps({'chat_id': CHAT_ID, 'text': text}).encode()\n"
        "    payload, mode = md, 'markdown'\n"
        "    last = ''\n"
        "    # Wall-clock cap so worst-case retries (DoH + multiple by-IP sends, each\n"
        "    # able to time out) can't run for tens of minutes when the box is offline.\n"
        "    deadline = time.time() + 300\n"
        "    for attempt in range(1, 19):\n"
        "        if time.time() > deadline:\n"
        "            log('tg send deadline (5 min) reached; stopping retries')\n"
        "            break\n"
        "        try:\n"
        "            req = urllib.request.Request(\n"
        "                url, data=payload,\n"
        "                headers={'Content-Type': 'application/json'})\n"
        "            urllib.request.urlopen(req, timeout=15)\n"
        "            log(f'tg send OK on attempt {attempt} ({mode})')\n"
        "            return True\n"
        "        except urllib.error.HTTPError as e:\n"
        "            try:\n"
        "                body = e.read().decode('utf-8', 'replace')[:200]\n"
        "            except Exception:\n"
        "                body = ''\n"
        "            last = f'HTTP {e.code} {body}'.strip()\n"
        "            log(f'tg send attempt {attempt} failed: {last}')\n"
        "            # A 400 means Telegram rejected the content (usually bad\n"
        "            # Markdown). Retrying the same payload never works, so drop\n"
        "            # to plain text once and retry immediately.\n"
        "            if e.code == 400 and mode == 'markdown':\n"
        "                payload, mode = plain, 'plain'\n"
        "                log('falling back to plain text')\n"
        "                continue\n"
        "            time.sleep(10)\n"
        "        except Exception as e:\n"
        "            last = str(e)\n"
        "            log(f'tg send attempt {attempt} failed (normal path): {last}')\n"
        "            # System DNS is likely down (MagicDNS starved). Try the\n"
        "            # DNS-resilient path before sleeping for the next attempt.\n"
        "            r = _send_dns_resilient(payload, mode)\n"
        "            if r == 'ok':\n"
        "                log(f'tg send OK on attempt {attempt} (dns-resilient {mode})')\n"
        "                return True\n"
        "            if r == 'bad400' and mode == 'markdown':\n"
        "                payload, mode = plain, 'plain'\n"
        "                log('falling back to plain text (dns-resilient)')\n"
        "                continue\n"
        "            time.sleep(10)\n"
        "    log(f'tg send GAVE UP after retries: {last}')\n"
        "    return False\n"
        "\n"
        "def _crash_hook(exc_type, exc, tb):\n"
        "    # Any uncaught exception (e.g. a subprocess TimeoutExpired) previously\n"
        "    # killed the wrapper SILENTLY — the owner never got a completion message.\n"
        "    # Log the full traceback and send a crash report instead.\n"
        "    import traceback\n"
        "    log('wrapper CRASHED: ' + ''.join(traceback.format_exception(exc_type, exc, tb)))\n"
        "    try:\n"
        "        tg('❌ Install wrapper crashed before completion: ' + str(exc)[:400]\n"
        "           + '\\n\\nCheck ~/.openclaw/integrations/mgmt-bot/install-wrapper.log on the Pi, '\n"
        "           + 'then verify the gateway with /status.')\n"
        "    except Exception:\n"
        "        pass\n"
        "sys.excepthook = _crash_hook\n"
        "\n"
        "HOME = os.path.expanduser('~')\n"
        "\n"
        "# Build a clean env for the install: inherit current env and\n"
        "# force OPENCLAW_VAULT_PASSPHRASE so nothing can prompt for it.\n"
        "install_env = os.environ.copy()\n"
        "if VAULT_PASS:\n"
        "    install_env['OPENCLAW_VAULT_PASSPHRASE'] = VAULT_PASS\n"
        "# Mark as non-interactive so the install script skips any TTY-gated prompts.\n"
        "install_env['OPENCLAW_NONINTERACTIVE'] = '1'\n"
        "\n"
        "log('wrapper started; pulling latest before install')\n"
        "# Local edits to tracked files make `git pull` refuse to merge. GitHub is\n"
        "# authoritative for this repo, so auto-stash them (recoverable via\n"
        "# `git stash pop` on the Pi) instead of aborting the whole install.\n"
        "stash_note = ''\n"
        "st = subprocess.run(['git', '-C', GIT_DIR, 'status', '--porcelain', '--untracked-files=no'],\n"
        "                    capture_output=True, text=True, timeout=60)\n"
        "if st.stdout.strip():\n"
        "    label = 'mgmt-bot auto-stash before /install ' + time.strftime('%Y-%m-%d %H:%M:%S')\n"
        "    sr = subprocess.run(['git', '-C', GIT_DIR, 'stash', 'push', '-m', label],\n"
        "                        capture_output=True, text=True, timeout=120)\n"
        "    if sr.returncode != 0:\n"
        "        s_out = (sr.stdout + sr.stderr).strip()\n"
        "        log('git stash failed before install')\n"
        "        tg('❌ Local changes found on the Pi but auto-stash failed — install aborted.\\n\\n```'\n"
        "           + (s_out or 'no output')[-3000:] + '```')\n"
        "        raise SystemExit(1)\n"
        "    stash_note = ('⚠️ Local changes to tracked files on the Pi were auto-stashed before pulling '\n"
        "                  'as \u201c' + label + '\u201d (recover with `git stash list` / `git stash pop`).\\n')\n"
        "    log('auto-stashed local changes: ' + label)\n"
        "pull = subprocess.run(['git', '-C', GIT_DIR, 'pull', '--ff-only'],\n"
        "                      capture_output=True, text=True, timeout=300)\n"
        "pull_out = (pull.stdout + pull.stderr).strip()\n"
        "if pull.returncode != 0:\n"
        "    msg = ('❌ Pull failed — install aborted.\\n' + stash_note + '\\n```'\n"
        "           + (pull_out or 'no output')[-3000:] + '```')\n"
        "    log('git pull failed before install')\n"
        "    tg(msg)\n"
        "    raise SystemExit(1)\n"
        "\n"
        "log('git pull complete; running install script')\n"
        "\n"
        "def svc_active(name):\n"
        "    r = subprocess.run(['systemctl', '--user', 'is-active', name],\n"
        "                       capture_output=True, text=True)\n"
        "    return r.stdout.strip() == 'active'\n"
        "\n"
        "def gateway_up():\n"
        "    \"\"\"Prefer systemd restart (same path as /restart + model switch, so the\n"
        "    unit reports is-active=active); fall back to l1-start.sh only if it fails.\"\"\"\n"
        "    r = subprocess.run(['systemctl', '--user', 'restart', 'openclaw-gateway.service'],\n"
        "                       capture_output=True, timeout=30)\n"
        "    if r.returncode == 0:\n"
        "        return True\n"
        "    l1_start = os.path.join(HOME, 'l1-start.sh')\n"
        "    if os.path.exists(l1_start):\n"
        "        r = subprocess.run(['bash', l1_start],\n"
        "                           capture_output=True, text=True, timeout=30,\n"
        "                           stdin=subprocess.DEVNULL, env=install_env)\n"
        "        return r.returncode == 0\n"
        "    return False\n"
        "\n"
        "def wait_active(name, timeout):\n"
        "    # Poll until the unit reports active, up to `timeout` seconds. The box\n"
        "    # can take several minutes to settle after an install, so a fixed short\n"
        "    # sleep would wrongly report 'inconclusive' even though it does come up.\n"
        "    end = time.time() + timeout\n"
        "    while time.time() < end:\n"
        "        if svc_active(name):\n"
        "            return True\n"
        "        time.sleep(5)\n"
        "    return svc_active(name)\n"
        "\n"
        "# Run the install script with stdin=DEVNULL so it cannot block on any prompt.\n"
        "# 60-min cap: a full gateway rebuild (pnpm install + tsdown build) on the Pi\n"
        "# can far exceed the old 15-min cap, and the resulting TimeoutExpired used to\n"
        "# kill the wrapper silently — no completion message ever arrived.\n"
        "try:\n"
        "    res = subprocess.run(['bash', INSTALL],\n"
        "                         capture_output=True, text=True, timeout=3600,\n"
        "                         stdin=subprocess.DEVNULL, env=install_env)\n"
        "except subprocess.TimeoutExpired as e:\n"
        "    log('install script timed out after 60 min')\n"
        "    try:\n"
        "        gateway_up()\n"
        "    except Exception:\n"
        "        pass\n"
        "    out = e.stdout or ''\n"
        "    if isinstance(out, bytes):\n"
        "        out = out.decode('utf-8', 'replace')\n"
        "    tail = '\\n'.join(out.strip().splitlines()[-15:])\n"
        "    tg('⚠️ Install was still running after 60 minutes and was stopped.\\n'\n"
        "       'The gateway was restarted as a safety net — verify with /status.\\n\\n'\n"
        "       '```' + tail[-1500:] + '```')\n"
        "    raise SystemExit(1)\n"
        "output = (res.stdout + res.stderr).strip()\n"
        "lines  = output.splitlines()\n"
        "tail   = '\\n'.join(lines[-40:])\n"
        "prefix = f'_(showing last 40 of {len(lines)} lines)_\\n\\n' if len(lines) > 40 else ''\n"
        "\n"
        "# Safety net: ensure the gateway comes back up regardless of install outcome.\n"
        "# gateway_up() prefers systemctl --user restart (systemd-managed, reports\n"
        "# is-active=active) and falls back to l1-start.sh only if that fails.\n"
        "# The box can take several minutes to settle after an install, so poll\n"
        "# patiently before deciding the status tag rather than after a fixed 8s.\n"
        "gw = 'openclaw-gateway.service'\n"
        "if not wait_active(gw, 120):\n"
        "    gateway_up()\n"
        "    wait_active(gw, 60)\n"
        "\n"
        "gw_ok  = svc_active(gw)\n"
        "gw_tag = '✅ Gateway: running' if gw_ok else '⚠️ Gateway check inconclusive — verify with /status'\n"
        "\n"
        "if res.returncode == 0:\n"
        "    head = f'✅ Install complete.\\n{gw_tag}\\n{stash_note}\\n'\n"
        "else:\n"
        "    head = f'⚠️ Install finished with errors (rc={res.returncode}).\\n{gw_tag}\\n{stash_note}\\n'\n"
        "# Telegram returns HTTP 400 for any message over 4096 chars. That's a\n"
        "# hard length limit, not a Markdown problem, so the plain-text fallback\n"
        "# can't rescue it — we MUST trim the embedded log tail so the whole\n"
        "# message fits, or the completion message never arrives.\n"
        "msg = head + prefix + '```' + tail + '```'\n"
        "if len(msg) > 3900:\n"
        "    keep = 3900 - len(head) - len(prefix) - 40\n"
        "    if keep < 0:\n"
        "        keep = 0\n"
        "    tail = tail[-keep:]\n"
        "    msg = head + prefix + '```\\n…(truncated — full output in the install log on the Pi)\\n' + tail + '```'\n"
        "log(f'tg sending completion message ({len(msg)} chars)')\n"
        "tg(msg)\n"
    )
    wrapper_path.chmod(0o700)

    # Escape the mgmt-bot systemd cgroup so systemd doesn't kill the wrapper
    # when it restarts this service during the install. systemd-run --user
    # puts the wrapper in its own transient unit with its own cgroup.
    # Falls back to start_new_session if systemd-run is unavailable.
    # Capture the launcher's own output so a systemd-run failure (e.g. missing
    # XDG_RUNTIME_DIR/D-Bus) is visible in a durable log instead of vanishing.
    Path(wrapper_log_path).parent.mkdir(parents=True, exist_ok=True)
    _audit(f"cmd_install wrapper_logs wrapper={wrapper_log_path} launch={wrapper_launch_log_path}")
    _launch_log = open(wrapper_launch_log_path, "ab")
    _sdr = shutil.which("systemd-run")
    if _sdr:
        subprocess.Popen(
            [_sdr, "--user", "--no-block",
             sys.executable, str(wrapper_path)],
            stdin=subprocess.DEVNULL,
            stdout=_launch_log,
            stderr=_launch_log,
        )
    else:
        subprocess.Popen(
            [sys.executable, str(wrapper_path)],
            stdin=subprocess.DEVNULL,
            stdout=_launch_log,
            stderr=_launch_log,
            start_new_session=True,
        )
    # Child has inherited (dup'd) the fd; the parent copy is no longer needed.
    _launch_log.close()


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
        STATE_DIR / "integrations/ai-briefing/pipeline.log",
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


def _garmin_script() -> "Path":
    override = _cfg("OPENCLAW_GARMIN_SCRIPT", "")
    if override:
        return Path(override)
    return STATE_DIR / "integrations/garmin/poll-garmin.py"


def _run_garmin(token: str, chat_id: str, args: list, intro: str, timeout: int = 120) -> None:
    script = _garmin_script()
    if not script.exists():
        send(token, chat_id, "❌ Garmin poller not found at "
                             f"`{script}` — run the install script first.")
        return
    send(token, chat_id, intro)
    try:
        r = subprocess.run(
            ["python3", str(script), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        send(token, chat_id, "❌ Garmin command timed out.")
        return
    output = (r.stdout + r.stderr).strip()
    tail   = "\n".join(output.splitlines()[-15:]) if output else "(no output)"
    icon   = "✅" if r.returncode == 0 else "❌"
    send(token, chat_id, f"{icon} Result:\n```{tail}```")


def cmd_garmin(token: str, chat_id: str) -> None:
    _run_garmin(token, chat_id, [],
                "🏃 Triggering Garmin poller — may take 30–60 seconds…")


def cmd_garmin_setup(token: str, chat_id: str) -> None:
    # One-time auth from GARMIN_EMAIL/GARMIN_PASSWORD in .env. No MFA on this
    # account, so this completes non-interactively.
    _run_garmin(token, chat_id, ["--setup"],
                "🔐 Authenticating with Garmin (one-time) — caches a self-renewing token…")


def cmd_garmin_status(token: str, chat_id: str) -> None:
    _run_garmin(token, chat_id, ["--status"],
                "🔎 Checking Garmin token status…", timeout=60)


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


def _yt_strip_tracking(url: str) -> str:
    """Remove YouTube share tracking params (?si=, &si=) from a URL."""
    import urllib.parse as _urlparse
    try:
        parsed = _urlparse.urlparse(url)
        qs = _urlparse.parse_qs(parsed.query, keep_blank_values=True)
        # Remove tracking-only params that don't affect channel resolution
        for param in ("si", "feature", "pp", "igsh"):
            qs.pop(param, None)
        clean_query = _urlparse.urlencode({k: v[0] for k, v in qs.items()})
        return _urlparse.urlunparse(parsed._replace(query=clean_query))
    except Exception:
        return url


def _yt_extract_handle(url: str) -> str:
    """Return the @handle (without @) from a YouTube channel URL, or ''."""
    import re as _re
    m = _re.search(r'youtube\.com/@([\w.-]+)', url)
    return m.group(1) if m else ""


def _yt_resolve_channel_id(handle_or_url: str) -> str:
    """
    Attempt to resolve a YouTube @handle or channel URL to a UC... channel ID.
    Fetches the channel page and extracts the channelId from page metadata.
    Returns '' on failure.
    """
    import re as _re
    import urllib.request as _req

    # Build URL to fetch
    handle = _yt_extract_handle(handle_or_url)
    if handle:
        fetch_url = f"https://www.youtube.com/@{handle}"
    elif handle_or_url.startswith("http"):
        fetch_url = handle_or_url.split("?")[0]  # strip query string for page fetch
    else:
        return ""

    try:
        request = _req.Request(
            fetch_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with _req.urlopen(request, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[mgmt-bot] _yt_resolve_channel_id fetch failed: {e}", file=sys.stderr)
        return ""

    # Look for channelId in the page (YouTube embeds it in page metadata/JS)
    patterns = [
        r'"channelId"\s*:\s*"(UC[\w-]{22})"',
        r'"externalChannelId"\s*:\s*"(UC[\w-]{22})"',
        r'channel_id=UC([\w-]{22})',
        r'"key"\s*:\s*"channelId"\s*,\s*"value"\s*:\s*"(UC[\w-]{22})"',
    ]
    for pat in patterns:
        m = _re.search(pat, html)
        if m:
            cid = m.group(1)
            # Normalise — some patterns already include UC prefix
            if not cid.startswith("UC"):
                cid = "UC" + cid
            return cid
    return ""


def cmd_yt_add(token: str, chat_id: str, args: str) -> None:
    """
    Usage: /yt-add <channel_url_or_id> [label]
    Examples:
      /yt-add https://www.youtube.com/@mkbhd MKBHD
      /yt-add UCBcRF18a7Qf58cCRy5xuWwQ "OpenClaw Dev Channel"
      /yt-add https://www.youtube.com/@lex_fridman
    """
    import re as _re

    parts = args.strip().split(None, 1)
    if not parts:
        send(token, chat_id,
             "Usage: `/yt-add <channel_url_or_id> [label]`\n\n"
             "Examples:\n"
             "`/yt-add https://www.youtube.com/@mkbhd MKBHD`\n"
             "`/yt-add UCBcRF18a7Qf58cCRy5xuWwQ`")
        return

    raw_input = parts[0].strip()
    label = parts[1].strip().strip('"').strip("'") if len(parts) > 1 else ""

    # Strip YouTube share tracking params (?si=...) — these change every time
    # you copy a link so they break duplicate detection and add noise
    url_or_id = _yt_strip_tracking(raw_input)

    # Bare UC... channel ID — store directly
    if _re.match(r'^UC[\w-]{22}$', url_or_id):
        resolved_id = url_or_id
        display = url_or_id
    else:
        # @handle or full URL — resolve to a channel ID so the RSS feed works
        # reliably. YouTube deprecated the ?user= RSS endpoint for new channels.
        send(token, chat_id, "🔍 Resolving channel ID from URL — just a moment…")
        resolved_id = _yt_resolve_channel_id(url_or_id)
        display = url_or_id

    if resolved_id:
        entry: dict = {"channel_id": resolved_id}
        # Keep the clean URL as a human-readable reference
        if not _re.match(r'^UC[\w-]{22}$', url_or_id):
            entry["channel_url"] = url_or_id
    else:
        # Could not resolve — store as URL and the poller will do best-effort
        send(token, chat_id,
             "⚠️ Could not auto-resolve channel ID from that URL.\n"
             "The channel will be added but may not poll correctly.\n"
             "For best results: open the channel in YouTube → About page → share icon → copy channel ID.")
        entry = {"channel_url": url_or_id}

    if label:
        entry["label"] = label
    entry["active"] = True

    channels = _yt_load_channels()

    # Duplicate check — compare by channel_id if we have one, else by URL
    for existing in channels:
        if resolved_id and existing.get("channel_id") == resolved_id:
            send(token, chat_id,
                 f"⚠️ That channel is already in the list "
                 f"(ID: `{resolved_id}`, label: {existing.get('label', 'unlabelled')}).")
            return
        if not resolved_id and existing.get("channel_url") == url_or_id:
            send(token, chat_id, f"⚠️ Channel `{url_or_id}` is already in the list.")
            return

    channels.append(entry)
    _yt_save_channels(channels)

    label_str = f" ({label})" if label else ""
    id_str = f"\nChannel ID: `{resolved_id}`" if resolved_id else ""
    send(token, chat_id,
         f"✅ YouTube channel added{label_str}:\n`{display}`{id_str}\n\n"
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
    send(token, chat_id,
         "▶️ Running YouTube channel poller (sync mode — summaries generated immediately)…")
    # --sync: process videos synchronously so Telegram notifications arrive
    # within this run rather than waiting for the next cron batch cycle.
    r = subprocess.run(
        ["python3", str(poller), "--sync"],
        capture_output=True, text=True, timeout=300,
    )
    output = (r.stdout + r.stderr).strip()
    tail = "\n".join(output.splitlines()[-20:]) if output else "(no output)"
    if r.returncode == 0:
        send(token, chat_id, f"✅ YouTube poller complete:\n```{tail}```")
    else:
        send(token, chat_id, f"❌ YouTube poller failed:\n```{tail}```")


def cmd_ai_briefing(token: str, chat_id: str, arg: str = "") -> None:
    """
    /ai-briefing          — show current briefing status (state.json)
    /ai-briefing run      — run the full pipeline now (collect → rank → synthesize)
    /ai-briefing status   — same as bare /ai-briefing
    /ai-briefing read     — show first 3000 chars of AI_BRIEFING_CURRENT.md
    """
    run_script  = STATE_DIR / "integrations" / "ai-briefing" / "run.py"
    current_md  = STATE_DIR / "ai-briefing" / "AI_BRIEFING_CURRENT.md"
    state_file  = STATE_DIR / "ai-briefing" / "state.json"

    cmd = (arg.strip().lower() or "status")

    if cmd == "run":
        if not run_script.exists():
            send(token, chat_id, "❌ AI briefing pipeline not found — run `/install` first.")
            return
        send(token, chat_id,
             "📰 Running AI briefing pipeline (collect → rank → synthesize)…\n"
             "_This takes 2–5 minutes. You'll get a message when done._")
        r = subprocess.run(
            ["python3", str(run_script)],
            capture_output=True, text=True, timeout=600,
        )
        output = (r.stdout + r.stderr).strip()
        tail = "\n".join(output.splitlines()[-20:]) if output else "(no output)"
        if r.returncode == 0:
            send(token, chat_id, f"✅ AI briefing pipeline complete:\n```{tail}```")
        else:
            send(token, chat_id, f"⚠️ AI briefing pipeline finished with issues (rc={r.returncode}):\n```{tail}```")
        return

    if cmd == "read":
        if not current_md.exists():
            send(token, chat_id,
                 "📭 No briefing yet.\nSend `/ai-briefing run` to generate one.")
            return
        content = current_md.read_text(encoding="utf-8")
        preview = content[:3000] + ("…\n_(truncated — full file in AI\\_BRIEFING\\_CURRENT.md)_" if len(content) > 3000 else "")
        send(token, chat_id, preview)
        return

    # Default: status
    lines = ["📰 *AI Briefing Status*\n"]

    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            pipeline_status = state.get("pipeline_status", "unknown")
            last_run  = state.get("pipeline_end", state.get("last_successful_run", "never"))[:19]
            last_date = state.get("last_briefing_date", "none")
            error     = state.get("pipeline_error", "")

            icon = {"success": "✅", "running": "🔄", "failed": "❌", "partial_failure": "⚠️"}.get(pipeline_status, "❓")
            lines.append(f"{icon} Pipeline: `{pipeline_status}`")
            lines.append(f"🕐 Last run: {last_run}")
            lines.append(f"📅 Last briefing: {last_date}")
            if error:
                lines.append(f"⚠️ Error: {error}")

            collect = state.get("collect", {})
            rank    = state.get("rank", {})
            synth   = state.get("synthesize", {})
            if collect:
                lines.append(f"\n*Collect:* {collect.get('items_new', 0)} new items, "
                              f"{collect.get('sources_ok', 0)} sources OK, "
                              f"{collect.get('sources_failed', 0)} failed")
            if rank:
                lines.append(f"*Rank:* {rank.get('items_shortlisted', 0)} shortlisted"
                              f"{' (quiet week)' if rank.get('quiet_week') else ''}")
            if synth:
                lines.append(f"*Synthesize:* {synth.get('items_included', 0)} included"
                              f"{', fallback used' if synth.get('fallback_used') else ''}")
        except Exception as e:
            lines.append(f"⚠️ Could not read state: {e}")
    else:
        lines.append("No state file — pipeline has not run yet.")

    if current_md.exists():
        size = current_md.stat().st_size
        lines.append(f"\n📄 `AI_BRIEFING_CURRENT.md` exists ({size} bytes)")
        lines.append("Send `/ai-briefing read` to preview it")
    else:
        lines.append("\n📭 No current briefing file")

    lines.append("\nSend `/ai-briefing run` to run the pipeline now")
    send(token, chat_id, "\n".join(lines))


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


def cmd_qwen_status(token: str, chat_id: str) -> None:
    """Check the Mac mini Ollama/Qwen route without changing the main gateway model."""
    base = _cfg("LOCAL_QWEN_BASE_URL", "http://192.168.86.46:11434").rstrip("/")
    wanted = _cfg("LOCAL_QWEN_MODEL", "qwen3-coder-131k")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=10) as resp:
            data = json.loads(resp.read())
        models = [m.get("name", "") for m in data.get("models", [])]
        model_bases = [m.split(":", 1)[0] for m in models]
        present = wanted in models or wanted in model_bases
        preview = "\n".join(f"• `{m}`" for m in models[:12]) or "(none returned)"
        send(token, chat_id,
             f"{'✅' if present else '⚠️'} *Local Qwen route*\n\n"
             f"Endpoint: `{base}`\n"
             f"Target: `{wanted}` {'present' if present else 'NOT FOUND'}\n\n"
             f"*Models:*\n{preview}")
    except Exception as e:
        send(token, chat_id, f"❌ Local Qwen route unavailable at `{base}`:\n```{e}```")


def cmd_qwen_test(token: str, chat_id: str) -> None:
    """Run the bounded task-worker self-test against Mac mini Qwen."""
    script = STATE_DIR / "workspace" / "projects" / "workspace-control-panel" / "scripts" / "local-qwen-task-worker.py"
    if not script.exists():
        send(token, chat_id, f"❌ Local Qwen worker script not found: `{script}`")
        return
    send(token, chat_id, "🧪 Running local Qwen task-worker self-test…")
    try:
        r = subprocess.run(["python3", str(script), "--self-test"], capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        send(token, chat_id, "⏱ Local Qwen self-test timed out after 240s.")
        return
    out = (r.stdout + r.stderr).strip()
    tail = out[-2500:] if out else "(no output)"
    icon = "✅" if r.returncode == 0 else "❌"
    send(token, chat_id, f"{icon} *Local Qwen self-test*\n\n```{tail}```")


def _run_wcp_script(script_name: str) -> str:
    project_dir = Path.home() / ".openclaw" / "workspace" / "projects" / "workspace-control-panel"
    script_path = project_dir / "scripts" / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"WCP helper script not found: {script_path}")
    if not os.access(script_path, os.X_OK):
        raise PermissionError(f"WCP helper script is not executable: {script_path}")
    proc = subprocess.run([str(script_path)], cwd=project_dir, capture_output=True, text=True, timeout=120)
    combined = "\n".join(part.strip() for part in [proc.stdout, proc.stderr] if part and part.strip()).strip()
    if proc.returncode != 0:
        raise RuntimeError(combined or f"Script failed with exit code {proc.returncode}")
    return combined or "Done."


def cmd_wcp_up(token: str, chat_id: str) -> None:
    send(token, chat_id, "🚀 Restarting WCP gateway and creating a fresh quick tunnel…")
    out = _run_wcp_script("start-gateway-and-tunnel.sh")
    send(token, chat_id, f"✅ *WCP up*\n\n```{out}```")


def cmd_wcp_url(token: str, chat_id: str) -> None:
    out = _run_wcp_script("print-tunnel-url.sh")
    send(token, chat_id, f"🔗 *Current WCP tunnel URL*\n\n`{out}`")


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


def _find_codex_bin() -> str | None:
    candidates = [
        shutil.which("codex"),
        str(Path.home() / ".npm-packages/bin/codex"),
        str(Path.home() / ".local/share/pnpm/codex"),
        str(Path.home() / ".npm-global/bin/codex"),
        str(Path.home() / ".local/bin/codex"),
        "/usr/local/bin/codex",
        "/usr/bin/codex",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists() and os.access(candidate, os.X_OK):
            return candidate
    return None


def cmd_codex_reauth(token: str, chat_id: str) -> None:
    """Re-authenticate OpenAI Codex via device code flow, phone-first and remote-safe."""
    import threading

    codex_bin = _find_codex_bin()
    if not codex_bin:
        send(token, chat_id, "❌ `codex` CLI not found on the Pi in PATH or standard install locations.")
        return

    helper = STATE_DIR / "workspace" / "skills" / "codex-reauth" / "reauth-copy-tokens.py"
    if not helper.exists():
        send(token, chat_id, f"❌ Codex token-copy helper not found at `{helper}`")
        return

    send(token, chat_id,
         "🔐 *OpenAI Codex re-auth*\n\n"
         "Starting device auth on the Pi… I’ll send you the URL and one-time code next.\n"
         "_You can complete this from your phone, remotely — no home network needed._")

    def _run_impl() -> None:
        import re as _re

        try:
            env = os.environ.copy()
            env["PATH"] = ":".join(filter(None, [
                env.get("PATH", ""),
                str(Path.home() / ".npm-packages/bin"),
                str(Path.home() / ".local/share/pnpm"),
                str(Path.home() / ".npm-global/bin"),
                str(Path.home() / ".local/bin"),
                "/usr/local/bin",
            ]))
            proc = subprocess.Popen(
                [codex_bin, "login", "--device-auth"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except Exception as e:
            send(token, chat_id, f"❌ Could not start Codex device auth: `{e}`")
            return

        url = None
        code = None
        lines = []

        if proc.stdout is None:
            send(token, chat_id, "❌ Codex device auth started without readable output.")
            return

        for raw in proc.stdout:
            line = raw.rstrip("\n")
            lines.append(line)
            clean = _re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
            if not url:
                m = _re.search(r'https://\S+', clean)
                if m:
                    url = m.group(0)
            if not code:
                m = _re.fullmatch(r'([A-Z0-9]{4,}-[A-Z0-9-]{4,})', clean)
                if m:
                    code = m.group(1)
            if url and code:
                send(token, chat_id,
                     f"🔐 *OpenAI Codex re-auth*\n\n"
                     f"1. Open this URL on your phone:\n{url}\n\n"
                     f"2. Enter this one-time code:\n`{code}`\n\n"
                     "_This works remotely — you do not need to be on the same network as the Pi._\n\n"
                     "I’ll keep waiting here and will message you when the auth is complete.")
                break

        if not (url and code):
            try:
                proc.kill()
            except Exception:
                pass
            tail = "\n".join(lines[-20:])
            send(token, chat_id,
                 f"❌ Could not parse Codex device-auth URL/code from CLI output.\n\n```{tail}```")
            return

        # Wait (bounded) for the user to finish sign-in — the codex CLI exits
        # once auth completes. The old unbounded stdout.read() could block this
        # thread FOREVER if the CLI hung, with no message ever sent.
        try:
            remaining = proc.communicate(timeout=1200)[0] or ""
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            send(token, chat_id,
                 "⌛ Codex device auth was not completed within 20 minutes, so I stopped waiting.\n"
                 "Run /codex_reauth again when you're ready to sign in.")
            return
        if remaining:
            lines.extend(remaining.splitlines())

        rc = proc.returncode
        if rc != 0:
            tail = "\n".join(lines[-30:])
            send(token, chat_id,
                 f"❌ Codex device auth did not complete successfully (exit {rc}).\n\n```{tail}```")
            return

        # Step 1: copy tokens into OpenClaw.
        try:
            copy = subprocess.run(
                ["python3", str(helper)],
                capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            send(token, chat_id,
                 "⚠️ Codex sign-in completed, but the *token copy* step timed out (2 min).\n"
                 "Run the re-auth again; if this repeats, check CPU load on the Pi.")
            return
        except Exception as e:
            send(token, chat_id, f"⚠️ Codex sign-in completed, but token copy failed: `{e}`")
            return
        if copy.returncode != 0:
            tail = (copy.stdout + copy.stderr).strip()[-1500:]
            send(token, chat_id,
                 f"⚠️ Sign-in succeeded but token copy failed.\n\n```{tail}```")
            return

        # Step 2: restart the gateway. A cold gateway start on the Pi routinely
        # exceeds 30s (boot embed pegs the CPU), so allow up to 3 minutes.
        try:
            restart = subprocess.run(
                ["systemctl", "--user", "restart", "openclaw-gateway.service"],
                capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            send(token, chat_id,
                 "⚠️ Sign-in and token copy succeeded, but the *gateway restart* is taking "
                 "longer than 3 minutes. Auth itself is almost certainly fine — give the Pi "
                 "a few minutes, then check /status or message the assistant.")
            return
        except Exception as e:
            send(token, chat_id, f"⚠️ Tokens copied, but gateway restart failed: `{e}`")
            return
        if restart.returncode != 0:
            tail = (restart.stdout + restart.stderr).strip()[-1500:]
            send(token, chat_id,
                 f"⚠️ Tokens copied, but gateway restart failed.\n\n```{tail}```")
            return

        # Step 3: verify. Right after a restart the Pi CPU is often pegged and the
        # Node CLI cold start alone can blow a short timeout even though auth is
        # fine — so retry a few times with generous limits before worrying anyone.
        verify_out = ""
        verify_note = "no output"
        for attempt in range(3):
            if attempt:
                time.sleep(20)
            try:
                verify = subprocess.run(
                    "openclaw config auth-status 2>&1 | grep -A 5 'openai-codex'",
                    shell=True, capture_output=True, text=True, timeout=120,
                )
            except subprocess.TimeoutExpired:
                verify_note = "auth-status timed out (2 min)"
                continue
            except Exception as e:
                verify_note = f"auth-status failed: {e}"
                continue
            verify_out = (verify.stdout + verify.stderr).strip()
            if verify_out and "Failed to refresh OAuth token" not in verify_out:
                break

        if not verify_out or "Failed to refresh OAuth token" in verify_out:
            tail = verify_out[-1500:] if verify_out else f"({verify_note})"
            send(token, chat_id,
                 "⚠️ Codex sign-in, token copy and gateway restart all *succeeded*, but I "
                 "could not positively verify auth afterwards.\n"
                 "It has most likely still worked — test by messaging the assistant, or run "
                 "`openclaw config auth-status` on the Pi.\n\n"
                 f"```{tail}```")
            return

        send(token, chat_id,
             f"✅ *OpenAI Codex re-auth complete*\n\n"
             f"Tokens copied into OpenClaw, gateway restarted, and auth verification passed.\n\n```{verify_out[-1200:]}```")

    def _run() -> None:
        # Crash guard + interruption marker: any uncaught exception previously
        # killed this thread SILENTLY, and a bot restart mid-wait lost the flow
        # with no trace. The marker lets main() report an interrupted re-auth
        # on the next startup.
        try:
            CODEX_REAUTH_MARKER.parent.mkdir(parents=True, exist_ok=True)
            CODEX_REAUTH_MARKER.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
        try:
            _run_impl()
        except Exception as e:
            print(f"[mgmt-bot] codex reauth error: {e}", file=sys.stderr)
            try:
                send(token, chat_id,
                     f"❌ Codex re-auth failed unexpectedly: `{e}`\n"
                     "Run /codex_reauth to try again.")
            except Exception:
                pass
        finally:
            try:
                CODEX_REAUTH_MARKER.unlink(missing_ok=True)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()


def cmd_ms_reauth(token: str, chat_id: str, account: str = "assistant") -> None:
    """
    Re-authenticate a Microsoft account via device code flow.
    Requests ALL scopes in one go so this never needs repeating:
      Mail.Send  Mail.Read  Files.ReadWrite  Sites.ReadWrite.All
      Calendars.ReadWrite  Tasks.ReadWrite  User.Read  offline_access

    account = "assistant"  → assistant@stackstoneconsulting.co.uk (SharePoint + email)
    account = "microsoft"  → tom@ personal account (email + calendar)
    """
    import threading

    FULL_SCOPES = (
        "Mail.Send Mail.Read Files.ReadWrite Sites.ReadWrite.All "
        "Calendars.ReadWrite Tasks.ReadWrite User.Read offline_access"
    )

    if account == "assistant":
        candidates = [
            STATE_DIR / "integrations/microsoft/token-assistant.json",
            STATE_DIR / "integrations/microsoft-l1/token.json",
        ]
        acct_label = "assistant@stackstoneconsulting.co.uk"
    else:
        candidates = [
            STATE_DIR / "integrations/microsoft/token-microsoft.json",
            STATE_DIR / "integrations/microsoft/token.json",
        ]
        acct_label = "tom@ personal"

    token_file = next((c for c in candidates if c.exists()), None)
    if not token_file:
        send(token, chat_id,
             f"❌ No token file found for `{account}` account.\n"
             f"Tried:\n" + "\n".join(f"  `{c}`" for c in candidates))
        return

    try:
        raw = json.loads(token_file.read_text())
    except Exception as e:
        send(token, chat_id, f"❌ Could not read token file: {e}")
        return

    # Normalise MSAL format if needed
    if "RefreshToken" in raw and "AccessToken" in raw:
        at_list  = list(raw.get("AccessToken",  {}).values())
        app_list = list(raw.get("AppMetadata",  {}).values())
        at  = at_list[0]  if at_list  else {}
        app = app_list[0] if app_list else {}
        raw = {
            "client_id": at.get("client_id") or app.get("client_id", ""),
            "tenant_id": at.get("realm", "common"),
            "refresh_token": "",
        }

    client_id = raw.get("client_id", "")
    tenant    = raw.get("tenant_id", "common")
    if not client_id:
        send(token, chat_id, "❌ `client_id` missing from token file — cannot reauth.")
        return

    # Step 1: get device code (fast — one API call)
    try:
        import urllib.request as _req2
        import urllib.parse as _urlparse
        body = _urlparse.urlencode({"client_id": client_id, "scope": FULL_SCOPES}).encode()
        req  = _req2.Request(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with _req2.urlopen(req, timeout=15) as resp:
            flow = json.loads(resp.read())
    except Exception as e:
        send(token, chat_id, f"❌ Device code request failed: {e}")
        return

    # Step 2: send code to Telegram immediately
    send(token, chat_id,
         f"🔐 *Microsoft re-auth — {acct_label}*\n\n"
         f"{flow.get('message', '(no message)')}\n\n"
         f"_Scopes: email · SharePoint · calendar · tasks_\n"
         f"_Waiting up to 15 min — I'll message you when it's done._")

    # Step 3: poll for completion in a background thread
    def _poll() -> None:
        import time as _time, urllib.request as _req3, urllib.parse as _up
        interval    = flow.get("interval", 5)
        device_code = flow["device_code"]
        deadline    = _time.time() + flow.get("expires_in", 900)

        while _time.time() < deadline:
            _time.sleep(interval)
            try:
                body2 = _up.urlencode({
                    "client_id":   client_id,
                    "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                }).encode()
                req2 = _req3.Request(
                    f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                    data=body2,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with _req3.urlopen(req2, timeout=15) as r:
                    data = json.loads(r.read())
            except Exception:
                continue

            if "access_token" in data:
                try:
                    current = json.loads(token_file.read_text())
                    if "RefreshToken" not in current:
                        current["access_token"]  = data["access_token"]
                        current["refresh_token"] = data.get(
                            "refresh_token", current.get("refresh_token", ""))
                        tmp = token_file.with_suffix(".tmp")
                        tmp.write_text(json.dumps(current, indent=2))
                        tmp.replace(token_file)
                    send(token, chat_id,
                         f"✅ *Microsoft re-auth complete* — {acct_label}\n\n"
                         f"All scopes granted: email · SharePoint · calendar · tasks\n"
                         f"This account won't need re-auth again unless access is revoked.")
                except Exception as e:
                    send(token, chat_id,
                         f"⚠️ Sign-in succeeded but token write failed: {e}\n"
                         f"Run manually: `python3 sharepoint.py reauth --account {account}`")
                return

            err = data.get("error", "")
            if err in ("authorization_pending", "slow_down"):
                if err == "slow_down":
                    interval += 5
                continue
            send(token, chat_id,
                 f"❌ Microsoft re-auth failed:\n`{data.get('error_description', err)}`")
            return

        send(token, chat_id,
             "⏱ Re-auth timed out — the code expired before sign-in completed.\n"
             "Try `/ms-reauth` again.")

    threading.Thread(target=_poll, daemon=True).start()


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


def cmd_sp_housekeep(token: str, chat_id: str, args_str: str = "") -> None:
    """
    Trigger the SharePoint CRM housekeeping sweep.

    Usage:
      /sp-housekeep                     — full execute sweep, sync mode
      /sp-housekeep dry-run             — propose changes only, no writes
      /sp-housekeep accounts            — execute, accounts only
      /sp-housekeep opportunities       — execute, opportunities only
      /sp-housekeep entity:Harken Health — execute, one entity only
      /sp-housekeep dry-run entity:Croyde Medical — dry-run, one entity
    """
    hk_script = STATE_DIR / "integrations/microsoft/sharepoint_housekeeping.py"
    if not hk_script.exists():
        send(token, chat_id,
             f"❌ Housekeeping script not found at `{hk_script}`.\n"
             f"Run `/install` to deploy it.")
        return

    # Parse optional args from message
    # Normalise for flag detection
    args_lower = args_str.lower() if args_str else ""
    mode  = "dry-run" if "dry-run" in args_lower or "dry_run" in args_lower else "execute"
    scope = "all"

    # entity:<name> can contain spaces — must be parsed from the original string
    # Match "entity:" and consume everything after it, stopping at known flags
    import re as _re
    entity_match = _re.search(
        r'(?i)entity:\s*(.+?)(?:\s+(?:dry-run|dry_run|accounts|opportunities)\b|$)',
        args_str.strip(),
    )
    if entity_match:
        scope = "entity:" + entity_match.group(1).strip()
    elif "accounts" in args_lower:
        scope = "accounts"
    elif "opportunities" in args_lower:
        scope = "opportunities"

    action_label = "Proposing changes (dry-run)" if mode == "dry-run" else "Running housekeeping sweep"
    send(token, chat_id,
         f"🧹 *SharePoint Housekeeping*\n"
         f"Mode: `{mode}` · Scope: `{scope}`\n\n"
         f"_{action_label} — using --sync for immediate results…_")

    cmd = ["python3", str(hk_script),
           "--mode",  mode,
           "--scope", scope,
           "--sync"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        send(token, chat_id, "⏱ Housekeeping timed out after 10 minutes.")
        return
    except Exception as e:
        send(token, chat_id, f"❌ Housekeeping failed unexpectedly:\n```{e}```")
        return

    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-20:])
        send(token, chat_id,
             f"❌ *Housekeeping failed* (exit {result.returncode}):\n```{tail}```")
        return

    # Read the output report/proposal file for a compact summary
    report_file = (STATE_DIR / "workspace" / "HOUSEKEEPING_PROPOSAL.md"
                   if mode == "dry-run"
                   else STATE_DIR / "workspace" / "HOUSEKEEPING_REPORT.md")
    try:
        report_lines = report_file.read_text().splitlines()
        # Send summary section (first ~25 lines = header + summary table)
        summary_block = "\n".join(report_lines[:25])
        send(token, chat_id,
             f"✅ *SharePoint Housekeeping {'Proposal' if mode == 'dry-run' else 'Complete'}*\n\n"
             f"```\n{summary_block}\n```\n\n"
             f"Full report: `{report_file.name}`")
    except Exception:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-15:])
        send(token, chat_id, f"✅ Housekeeping complete.\n```{tail}```")


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
         "*Provider (model switch)*\n"
         "/codex54full — Codex 5.4 full [default] + restart\n"
         "/codex55full — Codex 5.5 full + restart\n"
         "/codex53mini — Codex 5.3 mini + restart\n"
         "/codex54mini — Codex 5.4 mini + restart\n"
         "/sonnet45 — Anthropic Sonnet 4.5 + restart\n"
         "/sonnet46 — Anthropic Sonnet 4.6 + restart\n"
         "/opus46 — Anthropic Opus 4.6 + restart\n"
         "/gpt5mini — OpenAI GPT-5 mini + restart\n"
         "/gpt54 — OpenAI GPT-5.4 + restart\n"
         "/qwen30b — Local Qwen3 Coder 30b 131k (Mac Mini) + restart\n"
         "/qwen-status — check Mac mini Ollama/Qwen route\n"
         "/qwen-test — run bounded task-worker self-test\n"
         "/codex_reauth — start remote phone-first Codex OAuth re-auth\n\n"
         "*Services*\n"
         "/restart — restart the L1 gateway\n"
         "/garmin — manually trigger the Garmin poller\n"
         "/garmin-setup — one-time Garmin login (caches self-renewing token)\n"
         "/garmin-status — show Garmin token validity/age\n"
         "/yt-add <url> [label] — add a YouTube channel to the transcript poller\n"
         "/yt-list — list configured YouTube channels\n"
         "/yt-run — trigger the YouTube channel poller now\n"
         "/ai-briefing — show briefing status, or: run | read\n"
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
         "/sp-sync — force immediate SharePoint content mirror refresh\n"
         "/sp-housekeep — CRM housekeeping sweep (entity-by-entity normalisation)\n"
         "  Options: dry-run · accounts · opportunities · entity:<name>\n"
         "  Example: /sp-housekeep dry-run entity:Harken Health\n\n"
         "*Microsoft Auth*\n"
         "/ms-reauth — re-authenticate assistant@ account (email + SharePoint + calendar + tasks)\n"
         "/ms-reauth-personal — re-authenticate tom@ personal account (email + calendar)\n"
         "_One reauth covers everything — no future reauth needed unless access is revoked._\n\n"
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
    ("wcp_up",    "Restart WCP gateway + create quick tunnel"),
    ("wcp_url",   "Show current WCP quick tunnel URL"),
    # Control
    ("restart",   "Restart the L1 gateway service"),
    ("pull",      "Git pull latest from GitHub"),
    ("install",   "Git pull + run install script"),
    ("reboot",    "Reboot the Pi (refused if not safe)"),
    # Model switching
    ("codex54full", "Switch to Codex Web 5.4 full (default)"),
    ("codex55full", "Switch to Codex Web 5.5 full"),
    ("codex53mini", "Switch to Codex Web 5.3 mini"),
    ("codex54mini", "Switch to Codex Web 5.4 mini"),
    ("sonnet45",    "Switch to Anthropic Sonnet 4.5"),
    ("sonnet46",    "Switch to Anthropic Sonnet 4.6"),
    ("opus46",      "Switch to Anthropic Opus 4.6"),
    ("gpt5mini",    "Switch to OpenAI GPT-5 mini"),
    ("gpt54",       "Switch to OpenAI GPT-5.4"),
    ("qwen30b",     "Switch to Local Qwen3 Coder 30b 131k (Mac Mini)"),
    ("qwen_status", "Check Mac mini Ollama/Qwen route"),
    ("qwen_test",   "Run local Qwen task-worker self-test"),
    ("codex_reauth", "Start remote phone-first Codex OAuth re-auth"),
    # Integrations
    ("garmin",       "Manually trigger the Garmin poller"),
    ("garmin_setup", "One-time Garmin login (caches self-renewing token)"),
    ("garmin_status", "Show Garmin token validity/age"),
    ("yt_add",       "Add a YouTube channel — /yt-add <url> [label]"),
    ("yt_list",      "List configured YouTube channels"),
    ("yt_run",       "Trigger the YouTube channel poller now"),
    ("ai_briefing",  "AI briefing: status | run | read"),
    ("sp_sync",        "Force SharePoint content mirror refresh"),
    ("sp_housekeep",   "CRM housekeeping sweep — dry-run|accounts|entity:<name>"),
    ("ms_reauth",          "Re-auth assistant@ (email+SP+cal+tasks, one-time)"),
    ("ms_reauth_personal", "Re-auth tom@ personal (email+calendar, one-time)"),
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
    "/codex54full":  lambda t, c: cmd_switch(t, c, "codex54full"),
    "/codex55full":  lambda t, c: cmd_switch(t, c, "codex55full"),
    "/codex53mini":  lambda t, c: cmd_switch(t, c, "codex53mini"),
    "/codex54mini":  lambda t, c: cmd_switch(t, c, "codex54mini"),
    "/sonnet45":     lambda t, c: cmd_switch(t, c, "sonnet45"),
    "/sonnet46":     lambda t, c: cmd_switch(t, c, "sonnet46"),
    "/opus46":       lambda t, c: cmd_switch(t, c, "opus46"),
    "/gpt5mini":     lambda t, c: cmd_switch(t, c, "gpt5mini"),
    "/gpt54":        lambda t, c: cmd_switch(t, c, "gpt54"),
    "/qwen30b":      lambda t, c: cmd_switch(t, c, "qwen30b"),
    "/qwen-status":  cmd_qwen_status,
    "/qwen_status":  cmd_qwen_status,
    "/qwen-test":    cmd_qwen_test,
    "/qwen_test":    cmd_qwen_test,
    "/codex-reauth": cmd_codex_reauth,
    "/codex_reauth": cmd_codex_reauth,
    "/restart":    cmd_restart,
    "/reboot":     cmd_reboot,
    "/pull":       cmd_pull,
    "/install":    cmd_install,
    "/health":     cmd_health,
    "/logs":       cmd_logs,
    "/garmin":     cmd_garmin,
    "/garmin-setup":  cmd_garmin_setup,
    "/garmin_setup":  cmd_garmin_setup,
    "/garmin-status": cmd_garmin_status,
    "/garmin_status": cmd_garmin_status,
    "/yt-list":    cmd_yt_list,
    "/yt_list":    cmd_yt_list,
    "/yt-run":          cmd_yt_run,
    "/yt_run":          cmd_yt_run,
    "/ai-briefing":     lambda t, c: cmd_ai_briefing(t, c, ""),
    "/ai_briefing":     lambda t, c: cmd_ai_briefing(t, c, ""),
    "/disk":            cmd_disk,
    "/wcp-up":          cmd_wcp_up,
    "/wcp_up":          cmd_wcp_up,
    "/wcp-url":         cmd_wcp_url,
    "/wcp_url":         cmd_wcp_url,
    "/soul":       cmd_soul_start,
    "/sp-sync":    cmd_sp_sync,
    "/sp_sync":    cmd_sp_sync,
    "/ms-reauth":          lambda t, c: cmd_ms_reauth(t, c, "assistant"),
    "/ms_reauth":          lambda t, c: cmd_ms_reauth(t, c, "assistant"),
    "/ms-reauth-personal": lambda t, c: cmd_ms_reauth(t, c, "microsoft"),
    "/ms_reauth_personal": lambda t, c: cmd_ms_reauth(t, c, "microsoft"),
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

    # If a Codex re-auth was still waiting for sign-in when this bot was
    # restarted (e.g. at the end of an install), its waiting thread died
    # silently — tell the owner instead of leaving them hanging.
    try:
        if CODEX_REAUTH_MARKER.exists():
            started = CODEX_REAUTH_MARKER.read_text().strip()
            CODEX_REAUTH_MARKER.unlink()
            send(token, allowed_id,
                 "⚠️ I was restarted while a Codex re-auth (started "
                 f"{started or 'earlier'}) was still waiting for sign-in, so that "
                 "attempt was interrupted and its result was lost.\n"
                 "If you already completed the sign-in on your phone it may still "
                 "have worked — but the safest move is to simply run /codex_reauth "
                 "again and complete it once more.")
    except Exception as e:
        print(f"[mgmt-bot] reauth marker check error: {e}", file=sys.stderr)

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

            if cmd in ("/sp-housekeep", "/sp_housekeep"):
                print(f"[mgmt-bot] Command: {cmd} {arg!r} from {chat_id}")
                try:
                    cmd_sp_housekeep(token, chat_id, arg)
                except Exception as e:
                    print(f"[mgmt-bot] Handler error ({cmd}): {e}", file=sys.stderr)
                    send(token, chat_id, f"❌ Error running `{cmd}`:\n```{e}```")
                continue

            if cmd in ("/ai-briefing", "/ai_briefing"):
                print(f"[mgmt-bot] Command: {cmd} {arg!r} from {chat_id}")
                try:
                    cmd_ai_briefing(token, chat_id, arg)
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
