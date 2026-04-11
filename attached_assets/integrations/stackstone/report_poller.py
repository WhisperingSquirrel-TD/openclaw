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
from datetime import datetime, timedelta, date
from pathlib import Path

STATE_DIR    = Path.home() / ".openclaw"
WORKSPACE_MD = STATE_DIR / "workspace/STACKSTONE_REPORTS.md"
GRAPH_BASE   = "https://graph.microsoft.com/v1.0"
LOCK_FILE    = Path("/tmp/openclaw-stackstone-report-poller.lock")
LOG_PREFIX   = "[stackstone-report-poller]"
REPORTS_RETAIN_DAYS = 90


# ── Load .env early — cron runs with a minimal shell environment ──────────────
# Reads ~/.openclaw/.env (key=value format, # comments, no shell expansion).
# Only sets vars that aren't already in the environment so explicit exports win.

def _load_dotenv() -> None:
    env_file = STATE_DIR / ".env"
    if not env_file.exists():
        return
    try:
        for raw_line in env_file.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass

_load_dotenv()


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


# ── Email HTML template ───────────────────────────────────────────────────────
# Personal text-style email — matches Tom's cold outreach style.
# No images, no background colours, no button boxes. Just text, amber links,
# and horizontal rules. Renders identically everywhere and degrades to plain text.

def build_email_html(first_name: str, company_name: str, report_url: str,
                     sender_email: str, sender_name: str) -> str:
    # Minimal personal-feel HTML — matches the style of Tom's cold outreach emails.
    # No images, no background colours, no button boxes. Just text, links, and rules.
    # Renders consistently in Gmail, Outlook, Apple Mail and dark mode because
    # there is nothing to fail — it degrades gracefully to plain text.
    F = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<title>Your AI Opportunity Report</title>
</head>
<body style="margin:0;padding:0;background-color:#ffffff;{F}-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td align="center" style="padding:32px 20px;">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;width:100%;">

        <!-- Headline -->
        <tr>
          <td style="padding-bottom:6px;">
            <p style="margin:0;{F}font-size:26px;font-weight:700;line-height:1.2;color:#1C1C1E;">Your AI opportunity report</p>
            <p style="margin:6px 0 0 0;{F}font-size:18px;font-weight:600;line-height:1.3;color:#D4A017;">for {company_name}.</p>
          </td>
        </tr>

        <!-- Rule -->
        <tr>
          <td style="padding:20px 0 20px 0;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td style="height:1px;background-color:#E0DDD6;font-size:0;line-height:0;">&nbsp;</td></tr>
            </table>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td>
            <p style="margin:0 0 16px 0;{F}font-size:15px;line-height:1.75;color:#1C1C1E;">Hi {first_name},</p>
            <p style="margin:0 0 16px 0;{F}font-size:15px;line-height:1.75;color:#1C1C1E;">Great to meet you. I've put together a personalised AI opportunity report based on our conversation — specific to where {company_name} is right now.</p>
            <p style="margin:0 0 16px 0;{F}font-size:15px;line-height:1.75;color:#1C1C1E;">It covers where AI can make the biggest practical difference for a business in your position. No jargon, no vendor pitches &mdash; just realistic opportunities with honest context on what to watch out for.</p>
            <p style="margin:0 0 16px 0;{F}font-size:15px;line-height:1.75;color:#1C1C1E;">Inside: your sector context, a primary opportunity specific to you, three things you could act on in the next 90 days, and honest things to consider so you go in with eyes open.</p>
          </td>
        </tr>

        <!-- CTA link -->
        <tr>
          <td style="padding:8px 0 24px 0;">
            <p style="margin:0;{F}font-size:15px;line-height:1.75;color:#1C1C1E;">
              <a href="{report_url}" target="_blank" style="color:#D4A017;font-weight:700;text-decoration:underline;">Read your report &rarr;</a>
            </p>
            <p style="margin:8px 0 0 0;{F}font-size:13px;line-height:1.6;color:#8E8E93;">There's a PDF download button on the page if you'd like to save or share it. The link doesn't expire.</p>
          </td>
        </tr>

        <!-- Rule -->
        <tr>
          <td style="padding:4px 0 20px 0;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td style="height:1px;background-color:#E0DDD6;font-size:0;line-height:0;">&nbsp;</td></tr>
            </table>
          </td>
        </tr>

        <!-- Signature -->
        <tr>
          <td>
            <p style="margin:0 0 2px 0;{F}font-size:14px;font-weight:700;color:#1C1C1E;">{sender_name}</p>
            <p style="margin:0 0 2px 0;{F}font-size:13px;color:#6C6C70;">Founder, Stackstone Consulting</p>
            <p style="margin:0 0 2px 0;{F}font-size:13px;">
              <a href="https://stackstoneconsulting.co.uk" style="color:#D4A017;text-decoration:none;">stackstoneconsulting.co.uk</a>
            </p>
            <p style="margin:0 0 2px 0;{F}font-size:13px;">
              <a href="mailto:{sender_email}" style="color:#6C6C70;text-decoration:none;">{sender_email}</a>
            </p>
            <p style="margin:0;{F}font-size:13px;color:#6C6C70;">Abingdon, Oxfordshire</p>
          </td>
        </tr>

        <!-- Unsubscribe note -->
        <tr>
          <td style="padding-top:28px;">
            <p style="margin:0;{F}font-size:11px;color:#AEAEB2;font-style:italic;">If you'd rather not hear from us, just reply &ldquo;unsubscribe&rdquo;.</p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>

</body>
</html>"""


# ── Graph email send ──────────────────────────────────────────────────────────

def send_report_email(access_token: str, report: dict) -> None:
    """Send the branded report email for a single report record."""
    to_email    = (report.get("to") or {}).get("email") or ""
    to_name     = (report.get("to") or {}).get("name") or ""
    if not to_email:
        raise ValueError("Report has no recipient email address — skipping")
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
    """Mark a report as email-sent on the website. Raises on failure so the
    caller can treat an un-acknowledged send as a failure and retry next poll."""
    base    = get_base_url()
    api_key = get_api_key()
    resp = requests.patch(
        f"{base}/api/integration/reports/{uuid}/sent",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10,
    )
    if not resp.ok:
        raise RuntimeError(
            f"PATCH /api/integration/reports/{uuid}/sent failed: "
            f"{resp.status_code} {resp.text}"
        )


# ── Workspace file — rolling log for L1 to read ───────────────────────────────

def update_reports_log(report: dict, status: str = "sent") -> None:
    """Append a report entry to STACKSTONE_REPORTS.md and prune entries older
    than REPORTS_RETAIN_DAYS so the file never grows unbounded."""
    import re

    first_name  = report.get("firstName", "")
    to_info     = report.get("to") or {}
    to_name     = to_info.get("name", "").strip() or first_name
    to_email    = to_info.get("email", "").strip()
    company     = report.get("companyName", "").strip()
    report_url  = report.get("reportUrl", "").strip()
    uuid        = report.get("uuid") or report.get("id", "unknown")
    now_str     = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_str   = date.today().strftime("%Y-%m-%d")

    new_entry = (
        f"## {now_str} — {to_name} ({company})\n"
        f"- **Status**: {status}\n"
        f"- **Email**: {to_email}\n"
        f"- **Report**: {report_url}\n"
        f"- **ID**: {uuid}\n"
    )

    cutoff = (date.today() - timedelta(days=REPORTS_RETAIN_DAYS)).strftime("%Y-%m-%d")

    try:
        raw = WORKSPACE_MD.read_text(encoding="utf-8") if WORKSPACE_MD.exists() else ""
    except Exception:
        raw = ""

    # Strip old header lines so we can rebuild them
    body_lines = [l for l in raw.splitlines() if not l.startswith("# Stackstone Reports") and not l.startswith("_Last updated")]

    # Prune entries older than cutoff by date in the heading
    pruned: list[str] = []
    skip = False
    for line in body_lines:
        m = re.match(r"^## (\d{4}-\d{2}-\d{2})", line)
        if m:
            skip = m.group(1) < cutoff
        if not skip:
            pruned.append(line)

    body = "\n".join(pruned).strip()
    updated = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = (
        f"# Stackstone Reports — Sent Log\n"
        f"_Last updated: {updated} | Retains {REPORTS_RETAIN_DAYS} days_\n\n"
        f"{new_entry}\n"
        f"{body}\n"
    )

    try:
        WORKSPACE_MD.parent.mkdir(parents=True, exist_ok=True)
        tmp = WORKSPACE_MD.with_suffix(".tmp")
        tmp.write_text(content.strip() + "\n", encoding="utf-8")
        tmp.replace(WORKSPACE_MD)
        log(f"Workspace log updated: {WORKSPACE_MD}")
    except Exception as e:
        log(f"WARNING: Could not write {WORKSPACE_MD}: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    lock_fh = acquire_lock()

    log("Poll starting")

    try:
        reports = fetch_unsent_reports()
    except Exception as e:
        log_err(f"Failed to fetch reports: {e}")
        notify(f"FAILED to poll integration API for unsent reports: {e}")
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
            update_reports_log(report, status="sent")
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
