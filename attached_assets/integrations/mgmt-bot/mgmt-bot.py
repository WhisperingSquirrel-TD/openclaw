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
  /codex        — switch to OpenAI Codex OAuth model and restart gateway
  /restart      — restart the L1 gateway service
  /pull         — git pull latest from GitHub (does NOT reinstall)
  /reboot       — reboot the Pi (refused if auto-start safety check fails)
  /health       — run system health check now and show output
  /logs         — show recent errors across all poller logs
  /garmin       — manually trigger the Garmin poller
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
  OPENCLAW_OPENAI_MODEL     Model ID for OpenAI API, e.g. openai/gpt-4o
  OPENCLAW_ANTHROPIC_MODEL  Model ID for Anthropic API, e.g. anthropic/claude-sonnet-4-5
  OPENCLAW_CODEX_MODEL      Model ID for OpenAI Codex OAuth, e.g. openai-codex/gpt-4o
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
     OPENCLAW_OPENAI_MODEL=openai/gpt-4o
     OPENCLAW_ANTHROPIC_MODEL=anthropic/claude-sonnet-4-5
     OPENCLAW_CODEX_MODEL=openai-codex/gpt-4o
4. Run the install script — deploys this file and installs the systemd service
5. Verify: systemctl --user status openclaw-mgmt-bot.service
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse
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
    result = _tg(
        token, "getUpdates",
        offset=offset, timeout=30,
        allowed_updates=["message"],
    )
    return result.get("result", [])


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

    send(token, chat_id,
         f"*OpenClaw Status*\n\n"
         f"🤖 Model: `{model}`\n"
         f"⚙️ Gateway: `{svc_state}`\n"
         f"🔁 Auto-start: {enabled}\n"
         f"🔌 Linger: {linger}\n"
         f"🧠 Soul: {soul_src}\n"
         f"⏱ Uptime: {uptime}")


def cmd_switch(token: str, chat_id: str, provider: str) -> None:
    model_key = {
        "openai":     "OPENCLAW_OPENAI_MODEL",
        "anthropic":  "OPENCLAW_ANTHROPIC_MODEL",
        "codex":      "OPENCLAW_CODEX_MODEL",
    }.get(provider, "OPENCLAW_OPENAI_MODEL")
    model     = _cfg(model_key)
    if not model:
        send(token, chat_id,
             f"❌ `{model_key}` is not set in `~/.openclaw/.env`.\n"
             f"Add it and re-run the install script.")
        return
    # Validate the required API key is present in .env before switching.
    # Codex uses OAuth (no key needed); openai/anthropic need their keys.
    api_key_var = {
        "openai":    "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "codex":     None,
    }.get(provider)
    if api_key_var:
        if not _cfg(api_key_var):
            send(token, chat_id,
                 f"❌ `{api_key_var}` is not set in `~/.openclaw/.env`.\n"
                 f"Add it before switching to `{provider}`.")
            return

    # Ensure the model has a provider prefix — the gateway requires it and
    # will incorrectly prepend "anthropic/" to any bare model ID.
    # If the .env value already contains "/" (e.g. openai-codex/gpt-4o),
    # use it verbatim. Only add the correct gateway prefix for bare names.
    gateway_prefix = {
        "openai":    "openai",
        "anthropic": "anthropic",
        "codex":     "openai-codex",
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
    The install script now auto-sources ~/.openclaw/.env so no
    manual source step is needed."""
    git_dir     = Path(_cfg("OPENCLAW_GIT_DIR", str(Path.home() / "openclaw")))
    install_sh  = Path.home() / "install-forked-openclaw.sh"

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

    send(token, chat_id, f"✅ Pull complete:\n```{pull_out}```\n\n🔧 Running install script… _(this takes ~5 min on Pi — you'll get the result when it's done)_")
    try:
        install = subprocess.run(
            ["bash", str(install_sh)],
            capture_output=True, text=True, timeout=900,
        )
    except subprocess.TimeoutExpired:
        send(token, chat_id,
             "⏱ Install script timed out after 15 minutes.\n\n"
             "The script may still be running in the background on the Pi.\n"
             "Check status with: `journalctl --user -u openclaw-gateway.service -n 30`\n"
             "or run the install manually: `bash ~/install-forked-openclaw.sh`")
        return
    except Exception as e:
        send(token, chat_id, f"❌ Install failed unexpectedly:\n```{e}```")
        return

    output = (install.stdout + install.stderr).strip()
    # Show last 40 lines — install output can be long
    lines  = output.splitlines()
    tail   = "\n".join(lines[-40:])
    prefix = f"_(showing last 40 of {len(lines)} lines)_\n\n" if len(lines) > 40 else ""

    if install.returncode == 0:
        send(token, chat_id, f"✅ Install complete:\n\n{prefix}```{tail}```")
    else:
        send(token, chat_id, f"⚠️ Install finished with errors:\n\n{prefix}```{tail}```")


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
        STATE_DIR / "integrations/stackstone/poller.log",
        STATE_DIR / "integrations/stackstone/enquiry-poller.log",
        STATE_DIR / "integrations/health/health-check.log",
        STATE_DIR / "integrations/mgmt-bot/mgmt-bot.log",
        STATE_DIR / "workspace/memory/poll-garmin-log.txt",
        STATE_DIR / "workspace/memory/poll-calendar-log.txt",
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
    script = Path(_cfg("OPENCLAW_GARMIN_SCRIPT",
                        str(STATE_DIR / "integrations/garmin/poll-garmin.py")))
    if not script.exists():
        send(token, chat_id, f"❌ Garmin script not found: `{script}`")
        return
    send(token, chat_id, "🏃 Triggering Garmin poller (this may take 30–60 seconds)…")
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
         "/codex — switch to OpenAI Codex OAuth + restart gateway\n\n"
         "*Services*\n"
         "/restart — restart the L1 gateway\n"
         "/garmin — manually trigger the Garmin poller\n"
         "/pull — git pull latest from GitHub\n"
         "/install — git pull + run install script (sources .env automatically)\n"
         "/reboot — reboot Pi (refused if not safe)\n\n"
         "*Identity*\n"
         "/soul — upload new SOUL.md (send as a .md file)\n\n"
         "/help — this message\n"
         "/cancel — cancel a pending operation")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

COMMANDS = {
    "/status":    cmd_status,
    "/openai":    lambda t, c: cmd_switch(t, c, "openai"),
    "/anthropic": lambda t, c: cmd_switch(t, c, "anthropic"),
    "/codex":     lambda t, c: cmd_switch(t, c, "codex"),
    "/restart":   cmd_restart,
    "/reboot":    cmd_reboot,
    "/pull":      cmd_pull,
    "/install":   cmd_install,
    "/health":    cmd_health,
    "/logs":      cmd_logs,
    "/garmin":    cmd_garmin,
    "/disk":      cmd_disk,
    "/soul":      cmd_soul_start,
    "/cancel":    cmd_cancel,
    "/help":      cmd_help,
    "/start":     cmd_help,
}


def main() -> None:
    _load_dotenv()

    token      = _require("MGMT_BOT_TOKEN")
    allowed_id = _require("MGMT_BOT_CHAT_ID")

    print(f"[mgmt-bot] Starting. Listening on chat_id={allowed_id}…")

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
