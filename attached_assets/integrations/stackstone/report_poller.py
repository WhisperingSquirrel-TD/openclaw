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
# Cross-client safe: fully inline styles, table layout, VML button for Outlook.
# No <style> blocks — Gmail strips them. No SVG — most clients don't render it.

def build_email_html(first_name: str, company_name: str, report_url: str,
                     sender_email: str, sender_name: str) -> str:
    # All styles are inline — Gmail strips <style> blocks entirely.
    # Layout uses tables throughout — no divs, no flexbox, no CSS classes.
    # CTA button uses the bulletproof VML pattern so Outlook renders it correctly.
    return f"""<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="x-apple-disable-message-reformatting">
<title>Your AI Opportunity Report</title>
<!--[if mso]>
<noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript>
<![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#F0EEE9;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">

<!-- Outer wrapper -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F0EEE9;">
  <tr>
    <td align="center" style="padding:32px 16px;">

      <!-- Card -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:580px;background-color:#ffffff;border-radius:8px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">

        <!-- Header: charcoal background with logo -->
        <tr>
          <td style="background-color:#2C2C2E;padding:24px 32px 22px 32px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <!-- Bar chart icon: 4 coloured rectangles side by side -->
                <td style="padding-right:10px;vertical-align:middle;">
                  <table role="presentation" cellpadding="0" cellspacing="1" border="0" style="display:inline-table;">
                    <tr>
                      <td style="width:5px;height:10px;background-color:#C0C0C0;vertical-align:bottom;"></td>
                      <td style="width:5px;height:14px;background-color:#A0A0A0;vertical-align:bottom;"></td>
                      <td style="width:5px;height:18px;background-color:#787878;vertical-align:bottom;"></td>
                      <td style="width:5px;height:22px;background-color:#D4A017;vertical-align:bottom;"></td>
                    </tr>
                  </table>
                </td>
                <td style="vertical-align:middle;">
                  <span style="color:#ffffff;font-size:17px;font-weight:700;letter-spacing:-0.3px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">Stackstone Consulting</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Amber rule -->
        <tr>
          <td style="height:3px;background-color:#D4A017;font-size:0;line-height:0;">&nbsp;</td>
        </tr>

        <!-- Hero: dark slate with greeting -->
        <tr>
          <td style="background-color:#48484A;padding:28px 32px 24px 32px;">
            <p style="margin:0 0 10px 0;color:#ffffff;font-size:22px;font-weight:700;line-height:1.2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">Hi {first_name},</p>
            <p style="margin:0;color:rgba(255,255,255,0.65);font-size:14px;line-height:1.65;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">Great to meet you. I've put together a personalised AI opportunity report for you — specific to {company_name} and where you are right now.</p>
          </td>
        </tr>

        <!-- Body copy -->
        <tr>
          <td style="background-color:#ffffff;padding:32px 32px 8px 32px;">
            <p style="margin:0 0 18px 0;color:#3C3C3E;font-size:15px;line-height:1.7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">It covers where AI can make the biggest practical difference for a business in your position, with realistic timelines and no fluff.</p>
            <p style="margin:0 0 28px 0;color:#3C3C3E;font-size:15px;line-height:1.7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">Inside: your sector context, a primary opportunity specific to you, three quick wins you could act on in the next 90 days, and honest things to consider so you go in with eyes open.</p>

            <!-- Bulletproof CTA button -->
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:28px;">
              <tr>
                <td style="border-radius:6px;background-color:#D4A017;" align="center">
                  <!--[if mso]>
                  <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word"
                    href="{report_url}"
                    style="height:48px;v-text-anchor:middle;width:200px;"
                    arcsize="10%" stroke="f" fillcolor="#D4A017">
                    <w:anchorlock/>
                    <center style="color:#2C2C2E;font-family:sans-serif;font-size:15px;font-weight:700;">View your report</center>
                  </v:roundrect>
                  <![endif]-->
                  <!--[if !mso]><!-->
                  <a href="{report_url}" target="_blank"
                     style="display:inline-block;background-color:#D4A017;color:#2C2C2E;text-decoration:none;padding:14px 32px;border-radius:6px;font-size:15px;font-weight:700;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;mso-hide:all;">View your report</a>
                  <!--<![endif]-->
                </td>
              </tr>
            </table>

            <p style="margin:0 0 32px 0;color:#AEAEB2;font-size:12px;line-height:1.6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">The report also has a PDF download button if you'd like to save or share it internally. The link doesn't expire.</p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background-color:#F0EEE9;padding:20px 32px 24px 32px;border-top:1px solid #E0DDD6;">
            <p style="margin:0 0 4px 0;color:#6C6C70;font-size:13px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;"><strong style="color:#48484A;">{sender_name}</strong> &mdash; Founder, Stackstone Consulting</p>
            <p style="margin:0 0 4px 0;font-size:12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
              <a href="mailto:{sender_email}" style="color:#6C6C70;text-decoration:none;">{sender_email}</a>
              <span style="color:#AEAEB2;">&nbsp;&nbsp;|&nbsp;&nbsp;</span>
              <a href="https://stackstoneconsulting.co.uk" style="color:#6C6C70;text-decoration:none;">stackstoneconsulting.co.uk</a>
            </p>
            <p style="margin:0;color:#AEAEB2;font-size:12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">Abingdon, Oxfordshire</p>
          </td>
        </tr>

      </table>
      <!-- /Card -->

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
