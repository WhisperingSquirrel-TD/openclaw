#!/usr/bin/env python3
"""
Stackstone Networking Report — Email Delivery Poller
=====================================================

Polls the Stackstone website's integration API for unsent networking reports
and sends each one as a branded HTML email via Microsoft Graph.

Pattern: pull from website (same as email pollers) — no HTTP endpoint on the Pi,
no Cloudflare tunnel, no subdomain needed.

Cron (installed by install-forked-openclaw.sh):
  */5 * * * * python3 ~/.openclaw/integrations/stackstone/report_poller.py >> ~/.openclaw/integrations/stackstone/poller.log 2>&1

Required env vars (already in the Pi environment):
  INTEGRATION_API_KEY    — shared secret for the Stackstone integration API
  STACKSTONE_BASE_URL    — e.g. https://stackstoneconsulting.co.uk

Optional env vars (if not set, reads from ~/.openclaw/openclaw.json):
  TELEGRAM_BOT_TOKEN     — Telegram bot token for notifications
  TELEGRAM_CHAT_ID       — Tom's Telegram chat ID for notifications
  SENDER_EMAIL           — From address (default: tom@stackstoneconsulting.co.uk)
  SENDER_NAME            — Display name (default: Tom Dean)
"""
import fcntl
import json
import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

STATE_DIR  = Path.home() / ".openclaw"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
LOCK_FILE  = Path("/tmp/openclaw-stackstone-report-poller.lock")
LOG_PREFIX = "[stackstone-report-poller]"


# ── Logging ───────────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] {LOG_PREFIX} {msg}", flush=True)


def log_err(msg: str) -> None:
    print(f"[{ts()}] {LOG_PREFIX} ERROR: {msg}", file=sys.stderr, flush=True)


# ── Lock — prevents overlapping cron runs ─────────────────────────────────────

def acquire_lock() -> object:
    fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except OSError:
        print(f"{LOG_PREFIX} Another instance is already running. Exiting.", file=sys.stderr)
        sys.exit(0)


# ── Config helpers ────────────────────────────────────────────────────────────

def _read_openclaw_config() -> dict:
    config_path = STATE_DIR / "openclaw.json"
    try:
        return json.loads(config_path.read_text())
    except Exception:
        return {}


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def get_telegram_credentials() -> tuple[str, str]:
    """Return (bot_token, chat_id). Reads env vars first, falls back to openclaw.json."""
    bot_token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id   = get_env("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        return bot_token, chat_id

    config = _read_openclaw_config()
    tg = config.get("channels", {}).get("telegram", {})

    if not bot_token:
        bot_token = tg.get("botToken", "")
        if not bot_token:
            accounts = tg.get("accounts", {})
            for acc in accounts.values():
                if isinstance(acc, dict) and acc.get("botToken"):
                    bot_token = acc["botToken"]
                    break

    if not chat_id:
        allow_from = tg.get("allowFrom", [])
        if allow_from:
            chat_id = str(allow_from[0])

    return bot_token, chat_id


def get_sender() -> tuple[str, str]:
    email = get_env("SENDER_EMAIL", "tom@stackstoneconsulting.co.uk")
    name  = get_env("SENDER_NAME",  "Tom Dean")
    return email, name


# ── Telegram notification ─────────────────────────────────────────────────────

def notify(msg: str) -> None:
    bot_token, chat_id = get_telegram_credentials()
    if not bot_token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": f"[Stackstone] {msg}"},
            timeout=10,
        )
    except Exception as e:
        log_err(f"Telegram notify failed: {e}")


# ── MS Graph token handling (copied from send.py) ─────────────────────────────

def _write_token_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _load_json_resilient(path: Path) -> dict:
    raw = path.read_text()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_err:
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(raw.strip())
            if isinstance(data, dict):
                log(f"WARNING: Token file corrupted — auto-recovered.")
                _write_token_atomic(path, data)
                return data
        except json.JSONDecodeError:
            pass
        raise ValueError(
            f"Token file unreadable: {path}\nError: {first_err}"
        ) from first_err


def _find_token_file() -> Path:
    candidates = [
        STATE_DIR / "integrations/microsoft/token-microsoft.json",
        STATE_DIR / "integrations/microsoft/token.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"No MS token file found. Tried: {[str(c) for c in candidates]}"
    )


def _load_token() -> tuple[dict, Path]:
    token_file = _find_token_file()
    data = _load_json_resilient(token_file)
    if "RefreshToken" in data and "AccessToken" in data:
        at_list  = list(data.get("AccessToken",  {}).values())
        rt_list  = list(data.get("RefreshToken", {}).values())
        app_list = list(data.get("AppMetadata",  {}).values())
        at  = at_list[0]  if at_list  else {}
        rt  = rt_list[0]
        app = app_list[0] if app_list else {}
        simple = {
            "client_id":     at.get("client_id") or app.get("client_id", ""),
            "client_secret": "",
            "tenant_id":     at.get("realm", "common"),
            "refresh_token": rt["secret"],
            "access_token":  at.get("secret", ""),
        }
        _write_token_atomic(token_file, simple)
        return simple, token_file
    return data, token_file


def _refresh_access_token(token_data: dict, token_file: Path) -> str:
    tenant = token_data.get("tenant_id", "common")
    post_data: dict = {
        "client_id":     token_data["client_id"],
        "refresh_token": token_data["refresh_token"],
        "grant_type":    "refresh_token",
        "scope":         "Mail.Send offline_access",
    }
    secret = token_data.get("client_secret", "")
    if secret:
        post_data["client_secret"] = secret

    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data=post_data,
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"Token refresh failed: {resp.status_code} {resp.text}")

    new_data = resp.json()
    token_data["access_token"]  = new_data["access_token"]
    token_data["refresh_token"] = new_data.get("refresh_token", token_data["refresh_token"])
    _write_token_atomic(token_file, token_data)
    return token_data["access_token"]


def get_access_token() -> str:
    token_data, token_file = _load_token()
    return _refresh_access_token(token_data, token_file)


# ── Email HTML template (matches send-report-server.js exactly) ───────────────

def build_email_html(first_name: str, company_name: str, report_url: str,
                     sender_email: str, sender_name: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your AI Opportunity Report</title>
<style>
  body{{margin:0;padding:0;background:#F0EEE9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}}
  .wrap{{max-width:580px;margin:32px auto;background:#fff;border-radius:8px;overflow:hidden}}
  .top{{background:#2C2C2E;padding:24px 32px 0}}
  .logo-row{{display:flex;align-items:center;gap:10px;margin-bottom:20px}}
  .logo-name{{color:#fff;font-size:17px;font-weight:700;letter-spacing:-0.3px}}
  .rule{{height:3px;background:#D4A017}}
  .hero{{background:#48484A;padding:24px 32px}}
  .hero h1{{color:#fff;font-size:20px;font-weight:700;margin:0 0 8px}}
  .hero p{{color:rgba(255,255,255,0.6);font-size:14px;margin:0;line-height:1.6}}
  .body{{padding:32px}}
  .body p{{font-size:15px;color:#3C3C3E;line-height:1.7;margin:0 0 16px}}
  .cta-wrap{{margin:24px 0 0}}
  .cta-btn{{display:inline-block;background:#D4A017;color:#2C2C2E;text-decoration:none;padding:14px 28px;border-radius:6px;font-size:15px;font-weight:700}}
  .note{{font-size:12px;color:#AEAEB2;margin-top:16px !important}}
  .footer{{background:#F0EEE9;padding:20px 32px;border-top:1px solid #E0DDD6}}
  .footer p{{font-size:12px;color:#8E8E93;margin:0 0 3px;line-height:1.5}}
  .footer a{{color:#8E8E93}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="logo-row">
      <svg width="26" height="26" viewBox="0 0 36 36" fill="none">
        <rect x="10" y="24" width="16" height="5" rx="2" fill="#D4A017"/>
        <rect x="7" y="18" width="22" height="5" rx="2" fill="#787878"/>
        <rect x="12" y="12" width="12" height="5" rx="2" fill="#A0A0A0"/>
        <rect x="15" y="6" width="6" height="5" rx="2" fill="#C0C0C0"/>
      </svg>
      <span class="logo-name">Stackstone Consulting</span>
    </div>
  </div>
  <div class="rule"></div>
  <div class="hero">
    <h1>Hi {first_name},</h1>
    <p>Great to meet you. Your bespoke AI opportunity report for {company_name} is ready.</p>
  </div>
  <div class="body">
    <p>I've put together a report based on research into {company_name} — covering where AI can make the biggest practical difference for a business in your position, with realistic timelines and no fluff.</p>
    <p>It includes your sector context, a primary opportunity specific to you, three quick wins you could act on in the next 90 days, and honest caveats about what to watch out for.</p>
    <div class="cta-wrap">
      <a href="{report_url}" class="cta-btn">View your report</a>
    </div>
    <p class="note">The report also has a PDF download button if you'd like to save or share it internally. The link doesn't expire.</p>
  </div>
  <div class="footer">
    <p><strong>{sender_name}</strong> — Founder, Stackstone Consulting</p>
    <p><a href="mailto:{sender_email}">{sender_email}</a> &nbsp;|&nbsp; <a href="https://stackstoneconsulting.co.uk">stackstoneconsulting.co.uk</a></p>
    <p>Abingdon, Oxfordshire</p>
  </div>
</div>
</body>
</html>"""


# ── Graph email send ──────────────────────────────────────────────────────────

def send_report_email(access_token: str, report: dict) -> None:
    """Send the branded report email for a single report record."""
    to_email    = report["to"]["email"]
    to_name     = report["to"]["name"]
    first_name  = report["firstName"]
    company     = report["companyName"]
    report_url  = report["reportUrl"]

    sender_email, sender_name = get_sender()
    html_body = build_email_html(first_name, company, report_url, sender_email, sender_name)

    message = {
        "subject": f"Your AI Opportunity Report \u2014 {company}",
        "body": {"contentType": "HTML", "content": html_body},
        "toRecipients": [{"emailAddress": {"address": to_email, "name": to_name}}],
        "replyTo": [{"emailAddress": {"address": sender_email, "name": sender_name}}],
    }

    resp = requests.post(
        f"{GRAPH_BASE}/me/sendMail",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        },
        json={"message": message, "saveToSentItems": True},
        timeout=20,
    )
    if resp.status_code not in (200, 202, 204):
        raise RuntimeError(f"Graph sendMail {resp.status_code}: {resp.text}")


# ── Stackstone integration API ────────────────────────────────────────────────

def get_base_url() -> str:
    url = get_env("STACKSTONE_BASE_URL", "https://stackstoneconsulting.co.uk")
    return url.rstrip("/")


def get_api_key() -> str:
    key = get_env("INTEGRATION_API_KEY")
    if not key:
        raise RuntimeError(
            "INTEGRATION_API_KEY not set. Add it to your Pi environment."
        )
    return key


def fetch_unsent_reports() -> list[dict]:
    base    = get_base_url()
    api_key = get_api_key()
    resp = requests.get(
        f"{base}/api/integration/reports",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    if resp.status_code == 404:
        log("Integration API not yet deployed — nothing to do.")
        return []
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("reports", [])


def mark_report_sent(uuid: str) -> None:
    base    = get_base_url()
    api_key = get_api_key()
    resp = requests.patch(
        f"{base}/api/integration/reports/{uuid}/sent",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10,
    )
    if not resp.ok:
        log_err(f"Failed to mark {uuid} as sent: {resp.status_code} {resp.text}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    lock_fh = acquire_lock()

    log("Poll starting")

    try:
        reports = fetch_unsent_reports()
    except Exception as e:
        log_err(f"Failed to fetch reports: {e}")
        return

    if not reports:
        log("No unsent reports.")
        return

    log(f"Found {len(reports)} unsent report(s). Refreshing Graph token...")

    try:
        access_token = get_access_token()
    except Exception as e:
        log_err(f"Token error: {e}")
        notify(f"FAILED to get MS Graph token for report delivery: {e}")
        return

    sent = 0
    failed = 0

    for report in reports:
        uuid        = report.get("uuid") or report.get("id", "unknown")
        first_name  = report.get("firstName", "")
        to_name     = report.get("to", {}).get("name", "")
        company     = report.get("companyName", "")
        report_url  = report.get("reportUrl", "")

        try:
            send_report_email(access_token, report)
            mark_report_sent(uuid)
            log(f"Sent: {to_name} ({company}) — {uuid}")
            notify(f"Report sent to {to_name} ({company}) \u2014 {report_url}")
            sent += 1
        except Exception as e:
            log_err(f"Failed to send report {uuid} to {to_name}: {e}")
            notify(f"FAILED to send report to {to_name} ({company}): {e}")
            failed += 1
            time.sleep(2)

    log(f"Poll complete \u2014 sent: {sent}, failed: {failed}")


if __name__ == "__main__":
    main()
