#!/usr/bin/env python3
"""
Stackstone Website Enquiry Poller — OpenClaw Integration
=========================================================

WHAT THIS DOES
--------------
Polls the Stackstone website integration API for new contact-form / website
enquiry submissions and fires an immediate Telegram alert to Tom for each one.

This is revenue-critical alerting. Enquiries are NOT the same as report views
or networking-report emails — they are direct inbound leads and must surface
immediately.

SOURCE OF WEBSITE ENQUIRIES
----------------------------
Contact form submissions on stackstoneconsulting.co.uk are stored in the
website's database and exposed via the integration API:

  GET  STACKSTONE_BASE_URL/api/integration/enquiries
       → Returns a JSON list of unalerted enquiries. Each record contains:
         id, name, company, email, phone (optional), role (optional),
         message, createdAt

  PATCH STACKSTONE_BASE_URL/api/integration/enquiries/:id/alerted
       → Marks an enquiry as alerted so it won't be re-delivered.

Both endpoints are authenticated with the same INTEGRATION_API_KEY used by
the networking-report poller.

HOW THE ALERT WORKS
-------------------
For each new (unalerted) enquiry:
  1. Send a Telegram message to Tom with:
       🔔 NEW WEBSITE ENQUIRY [REVENUE CRITICAL]
       Name, Company, Role/Title, Email, Phone, Message summary
  2. PATCH the enquiry as alerted so it won't fire again.
  3. Write to the state log for audit trail.

FAILURE / STALENESS BEHAVIOUR
------------------------------
- If the API call fails (network error, 5xx, auth error):
    → Telegram alert sent immediately, no retry storm (next cron run = 2 min)
- If the API returns 404:
    → Logged as "endpoint not deployed yet", no Telegram alert (expected during dev)
- Staleness check:
    → If the API has returned zero enquiries for more than STALE_HOURS (default 24h)
      AND the last known enquiry was received more than STALE_HOURS ago, a
      Telegram health warning is sent once per STALE_INTERVAL_HOURS (6h) to flag
      that the enquiry pipeline may be broken (form not sending, API down, etc.)
    → Staleness check uses a separate state file to track last-seen times.

CRON
----
Runs every 2 minutes (installed by install-forked-openclaw.sh):
  */2 * * * * python3 ~/.openclaw/integrations/stackstone/enquiry_poller.py >> \
                       ~/.openclaw/integrations/stackstone/enquiry-poller.log 2>&1

REQUIRED ENV VARS (loaded from ~/.openclaw/.env)
-------------------------------------------------
  INTEGRATION_API_KEY    — shared secret for the Stackstone integration API
  STACKSTONE_BASE_URL    — e.g. https://stackstoneconsulting.co.uk
  TELEGRAM_BOT_TOKEN     — Telegram bot token (or read from openclaw.json)
  TELEGRAM_CHAT_ID       — Tom's Telegram chat ID (or read from openclaw.json)

TO TEST MANUALLY
----------------
  python3 ~/.openclaw/integrations/stackstone/enquiry_poller.py

To inject a test enquiry, POST to:
  curl -X POST STACKSTONE_BASE_URL/api/integration/enquiries/test \
       -H "Authorization: Bearer INTEGRATION_API_KEY"
(Endpoint must be implemented on the website side for test mode.)

Or: temporarily insert a row directly into the website DB and verify the
Telegram alert fires within 2 minutes.
"""
import fcntl
import json
import os
import re
import sys
import requests
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

STATE_DIR     = Path.home() / ".openclaw"
LOCK_FILE     = Path("/tmp/openclaw-stackstone-enquiry-poller.lock")
STATE_FILE    = STATE_DIR / "integrations/stackstone/enquiry-poller-state.json"
ENQUIRIES_MD  = STATE_DIR / "workspace/STACKSTONE_ENQUIRIES.md"
LOG_PREFIX    = "[stackstone-enquiry-poller]"

STALE_HOURS            = 24   # alert if no enquiries seen in this many hours
STALE_INTERVAL_HOURS   = 6    # only re-alert staleness every this many hours
ENQUIRIES_RETAIN_DAYS  = 90   # rolling window kept in workspace file


# ---------------------------------------------------------------------------
# Load .env early — cron has a minimal shell environment
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] {LOG_PREFIX} {msg}", flush=True)


def log_err(msg: str) -> None:
    print(f"[{ts()}] {LOG_PREFIX} ERROR: {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Lock — prevents overlapping cron runs
# ---------------------------------------------------------------------------

def acquire_lock() -> object:
    fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except OSError:
        print(f"{LOG_PREFIX} Another instance already running. Exiting.", file=sys.stderr)
        sys.exit(0)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _read_openclaw_config() -> dict:
    config_path = STATE_DIR / "openclaw.json"
    try:
        return json.loads(config_path.read_text())
    except Exception:
        return {}


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def get_telegram_credentials() -> tuple[str, str]:
    bot_token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id   = get_env("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        return bot_token, chat_id

    config = _read_openclaw_config()
    tg = config.get("channels", {}).get("telegram", {})

    if not bot_token:
        bot_token = tg.get("botToken", "")
        if not bot_token:
            for acc in tg.get("accounts", {}).values():
                if isinstance(acc, dict) and acc.get("botToken"):
                    bot_token = acc["botToken"]
                    break

    if not chat_id:
        allow_from = tg.get("allowFrom", [])
        if allow_from:
            chat_id = str(allow_from[0])

    return bot_token, chat_id


def get_api_key() -> str:
    key = get_env("INTEGRATION_API_KEY")
    if not key:
        raise RuntimeError("INTEGRATION_API_KEY not set. Add it to ~/.openclaw/.env")
    return key


def get_base_url() -> str:
    return get_env("STACKSTONE_BASE_URL", "https://stackstoneconsulting.co.uk").rstrip("/")


# ---------------------------------------------------------------------------
# State file — tracks last-alerted enquiry and staleness
# ---------------------------------------------------------------------------

def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception as e:
        log(f"WARNING: Could not read state file: {e} — starting fresh")
    return {
        "alerted_ids":           [],
        "last_enquiry_seen_at":  None,
        "last_stale_alert_at":   None,
        "total_alerted":         0,
    }


def save_state(state: dict) -> None:
    _write_atomic(STATE_FILE, state)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _send_telegram(msg: str) -> None:
    bot_token, chat_id = get_telegram_credentials()
    if not bot_token or not chat_id:
        log("WARNING: Telegram credentials not configured — skipping notification")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": msg},
            timeout=10,
        )
        if not resp.ok:
            log_err(f"Telegram sendMessage failed: {resp.status_code} {resp.text}")
    except Exception as e:
        log_err(f"Telegram notify failed: {e}")


def alert_new_enquiry(enquiry: dict) -> None:
    name    = (enquiry.get("name")    or "").strip() or "Unknown"
    company = (enquiry.get("company") or "").strip() or "—"
    role    = (enquiry.get("role")    or enquiry.get("title") or "").strip() or "—"
    email   = (enquiry.get("email")   or "").strip() or "—"
    phone   = (enquiry.get("phone")   or "").strip() or "—"
    message = (enquiry.get("message") or "").strip()
    source  = (enquiry.get("source")  or "website contact form").strip()

    # Trim message for the alert — enough to act on without blowing up the message
    msg_preview = (message[:400] + "…") if len(message) > 400 else message
    if not msg_preview:
        msg_preview = "(no message text)"

    created = enquiry.get("createdAt") or enquiry.get("created_at") or ""
    created_fmt = created[:16].replace("T", " ") if created else "unknown"

    text = (
        "🔔 NEW WEBSITE ENQUIRY — REVENUE CRITICAL\n"
        f"Source: {source}\n"
        f"Received: {created_fmt}\n\n"
        f"Name:    {name}\n"
        f"Company: {company}\n"
        f"Role:    {role}\n"
        f"Email:   {email}\n"
        f"Phone:   {phone}\n\n"
        f"Message:\n{msg_preview}"
    )
    _send_telegram(text)
    log(f"ALERTED: {name} ({company}) <{email}>")


def alert_api_failure(error: str) -> None:
    _send_telegram(
        "⚠️ WEBSITE ENQUIRY PIPELINE FAILURE\n\n"
        "The enquiry poller could not reach the Stackstone integration API.\n"
        f"Error: {error}\n\n"
        "Check: INTEGRATION_API_KEY, STACKSTONE_BASE_URL, website status."
    )


def alert_stale_feed() -> None:
    _send_telegram(
        "⚠️ WEBSITE ENQUIRY FEED MAY BE BROKEN\n\n"
        f"No new enquiries have been seen in the last {STALE_HOURS} hours.\n\n"
        "Possible causes:\n"
        "• Contact form not sending to the database\n"
        "• Integration API endpoint down\n"
        "• INTEGRATION_API_KEY expired or rotated\n\n"
        "Action: Test the contact form manually or check the website logs."
    )


# ---------------------------------------------------------------------------
# Stackstone integration API
# ---------------------------------------------------------------------------

def fetch_enquiries() -> list[dict] | None:
    """
    Returns list of enquiry dicts, or None if the call failed (caller handles alerting).
    Returns [] if the endpoint returns 404 (not yet deployed — expected during dev).
    """
    base    = get_base_url()
    api_key = get_api_key()
    try:
        resp = requests.get(
            f"{base}/api/integration/enquiries",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
    except Exception as e:
        log_err(f"Network error fetching enquiries: {e}")
        return None

    if resp.status_code == 404:
        log("GET /api/integration/enquiries → 404: endpoint not yet deployed. Skipping.")
        return []

    if not resp.ok:
        log_err(f"API error: {resp.status_code} {resp.text[:200]}")
        return None

    try:
        data = resp.json()
    except Exception as e:
        log_err(f"JSON parse error: {e} — raw: {resp.text[:200]}")
        return None

    return data if isinstance(data, list) else data.get("enquiries", [])


def mark_alerted(enquiry_id: str) -> bool:
    """
    Mark one enquiry as alerted on the website. Returns True on success.
    Raises on failure so the caller skips adding it to alerted_ids (safe retry next poll).
    """
    base    = get_base_url()
    api_key = get_api_key()
    try:
        resp = requests.patch(
            f"{base}/api/integration/enquiries/{enquiry_id}/alerted",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except Exception as e:
        log_err(f"Network error marking enquiry {enquiry_id} as alerted: {e}")
        return False

    if resp.status_code == 404:
        log(f"PATCH /enquiries/{enquiry_id}/alerted → 404 (endpoint not deployed). Skipping mark.")
        return True  # Don't re-alert — we did send the Telegram message

    if not resp.ok:
        log_err(f"PATCH /enquiries/{enquiry_id}/alerted failed: {resp.status_code} {resp.text[:200]}")
        return False

    return True


# ---------------------------------------------------------------------------
# Staleness check
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def check_staleness(state: dict) -> bool:
    """
    Returns True if a staleness alert was sent this call.
    Fires only once per STALE_INTERVAL_HOURS.
    """
    last_seen_str       = state.get("last_enquiry_seen_at")
    last_stale_alert_str = state.get("last_stale_alert_at")

    if last_seen_str is None:
        # No enquiry ever seen — don't alert (system may be newly installed)
        return False

    last_seen        = _parse_iso(last_seen_str)
    last_stale_alert = _parse_iso(last_stale_alert_str)
    now              = _now_utc()

    if last_seen and (now - last_seen) < timedelta(hours=STALE_HOURS):
        return False  # Recent enough — no stale alert

    # Feed is stale. Only alert if we haven't alerted in the last STALE_INTERVAL_HOURS.
    if last_stale_alert and (now - last_stale_alert) < timedelta(hours=STALE_INTERVAL_HOURS):
        log(f"Feed stale but staleness alert sent within last {STALE_INTERVAL_HOURS}h — suppressing duplicate")
        return False

    log(f"Staleness threshold exceeded ({STALE_HOURS}h since last enquiry) — sending alert")
    alert_stale_feed()
    state["last_stale_alert_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return True


# ---------------------------------------------------------------------------
# Workspace file — rolling log for L1 to read
# ---------------------------------------------------------------------------

def update_enquiries_log(enquiry: dict) -> None:
    """Append enquiry to STACKSTONE_ENQUIRIES.md, prune entries older than
    ENQUIRIES_RETAIN_DAYS. L1 reads this file to answer questions about leads."""
    name    = (enquiry.get("name")    or "").strip() or "Unknown"
    company = (enquiry.get("company") or "").strip() or "—"
    role    = (enquiry.get("role")    or enquiry.get("title") or "").strip() or "—"
    email   = (enquiry.get("email")   or "").strip() or "—"
    phone   = (enquiry.get("phone")   or "").strip() or "—"
    message = (enquiry.get("message") or "").strip()
    source  = (enquiry.get("source")  or "website contact form").strip()
    msg_preview = (message[:300] + "…") if len(message) > 300 else message

    created = enquiry.get("createdAt") or enquiry.get("created_at") or ""
    received_fmt = created[:16].replace("T", " ") if created else datetime.now().strftime("%Y-%m-%d %H:%M")
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")

    new_entry = (
        f"## {now_str} — {name} ({company})\n"
        f"- **Received**: {received_fmt}\n"
        f"- **Source**: {source}\n"
        f"- **Role**: {role}\n"
        f"- **Email**: {email}\n"
        f"- **Phone**: {phone}\n"
        f"- **Message**: {msg_preview}\n"
    )

    cutoff = (date.today() - timedelta(days=ENQUIRIES_RETAIN_DAYS)).strftime("%Y-%m-%d")

    try:
        raw = ENQUIRIES_MD.read_text(encoding="utf-8") if ENQUIRIES_MD.exists() else ""
    except Exception:
        raw = ""

    body_lines = [l for l in raw.splitlines()
                  if not l.startswith("# Stackstone Enquiries") and not l.startswith("_Last updated")]

    pruned: list[str] = []
    skip = False
    for line in body_lines:
        m = re.match(r"^## (\d{4}-\d{2}-\d{2})", line)
        if m:
            skip = m.group(1) < cutoff
        if not skip:
            pruned.append(line)

    body    = "\n".join(pruned).strip()
    updated = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = (
        f"# Stackstone Enquiries — Inbound Leads Log\n"
        f"_Last updated: {updated} | Retains {ENQUIRIES_RETAIN_DAYS} days_\n\n"
        f"{new_entry}\n"
        f"{body}\n"
    )

    try:
        ENQUIRIES_MD.parent.mkdir(parents=True, exist_ok=True)
        tmp = ENQUIRIES_MD.with_suffix(".tmp")
        tmp.write_text(content.strip() + "\n", encoding="utf-8")
        tmp.replace(ENQUIRIES_MD)
        log(f"Workspace log updated: {ENQUIRIES_MD}")
    except Exception as e:
        log(f"WARNING: Could not write {ENQUIRIES_MD}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    acquire_lock()

    log("Poll starting")

    try:
        api_key = get_api_key()  # Validate early
    except RuntimeError as e:
        log_err(str(e))
        sys.exit(1)

    state = load_state()

    # Cap alerted_ids list to avoid unbounded growth (keep last 2000)
    if len(state.get("alerted_ids", [])) > 2000:
        state["alerted_ids"] = state["alerted_ids"][-2000:]

    alerted_ids = set(str(i) for i in state.get("alerted_ids", []))

    enquiries = fetch_enquiries()

    if enquiries is None:
        # API call failed — alert and exit
        alert_api_failure("Could not reach /api/integration/enquiries (see poller log for detail)")
        save_state(state)
        return

    log(f"API returned {len(enquiries)} enquiry record(s)")

    new_count = 0

    for enquiry in enquiries:
        eid = str(enquiry.get("id") or enquiry.get("uuid") or "")
        if not eid:
            log(f"WARNING: Enquiry record has no id/uuid — skipping: {str(enquiry)[:120]}")
            continue

        if eid in alerted_ids:
            continue  # Already alerted

        log(f"New enquiry: id={eid} name={enquiry.get('name','?')} email={enquiry.get('email','?')}")

        # Fire the Telegram alert first
        alert_new_enquiry(enquiry)

        # Write to workspace file so L1 can answer questions about leads
        update_enquiries_log(enquiry)

        # Mark alerted on the website (best-effort)
        mark_ok = mark_alerted(eid)

        if mark_ok:
            alerted_ids.add(eid)
            state["alerted_ids"] = list(alerted_ids)
            new_count += 1

        # Update last-seen timestamp to now
        received = enquiry.get("createdAt") or enquiry.get("created_at") or ""
        if received:
            state["last_enquiry_seen_at"] = received if "T" in received else received.replace(" ", "T") + "Z"
        else:
            state["last_enquiry_seen_at"] = _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")

        state["total_alerted"] = state.get("total_alerted", 0) + 1
        save_state(state)

    if new_count == 0:
        log("No new enquiries.")

    # Run staleness check regardless
    check_staleness(state)
    save_state(state)

    log(f"Poll complete — new alerts sent: {new_count}")


if __name__ == "__main__":
    main()
