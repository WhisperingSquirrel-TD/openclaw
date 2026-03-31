#!/usr/bin/env python3
"""
Garmin Connect daily health data poller for OpenClaw.

Fetches today's data from Garmin Connect:
  - Resting heart rate
  - HRV status and last-night value
  - Sleep score and duration
  - Average stress level
  - Body battery (peak of the day)
  - Step count
  - Most recent activity (name, distance, duration, avg HR)

Writes two files:
  GARMIN_DAILY.md   — today's full snapshot, overwritten each run (never grows)
  GARMIN_ARCHIVE.md — rolling 28-day history, one compact entry per day,
                      auto-trimmed on each run. Always in workspace so L1
                      can spot trends and advise on health patterns.

Caches session tokens to avoid MFA on every run.

Scheduled at 09:00 daily (NOT 06:xx — the CRM runs at 06:00, and 07:00 is
also busy with another job).

FIRST-RUN SETUP (run once interactively to cache tokens):
  export GARMIN_EMAIL=you@example.com
  export GARMIN_PASSWORD=yourpassword
  python3 ~/.openclaw/integrations/garmin/poll-garmin.py

  If Garmin requires MFA, you will be prompted once. After that,
  tokens are cached and subsequent unattended runs need no interaction.

Dependencies:
  pip3 install garminconnect
"""
import os
import sys
import json
from datetime import datetime, date, timedelta
from pathlib import Path

STATE_DIR          = Path.home() / ".openclaw"
TOKEN_STORE        = STATE_DIR / "integrations/garmin/tokens"
OUTPUT_MD          = STATE_DIR / "workspace/GARMIN_DAILY.md"
ARCHIVE_MD         = STATE_DIR / "workspace/GARMIN_ARCHIVE.md"
LOG_FILE           = STATE_DIR / "workspace/memory/poll-garmin-log.txt"

LOG_MAX_LINES      = 1000
LOG_TRIM_TO        = 800
ARCHIVE_RETAIN_DAYS = 28     # rolling window — entries older than this are dropped


# ── Logging (same rotation pattern as poll.py) ──────────────────────────────

def log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        existing = LOG_FILE.read_text().splitlines(keepends=True)
    except FileNotFoundError:
        existing = []
    if len(existing) >= LOG_MAX_LINES:
        existing = existing[-LOG_TRIM_TO:]
    existing.append(line)
    tmp = LOG_FILE.with_suffix(".tmp")
    try:
        tmp.write_text("".join(existing))
        tmp.replace(LOG_FILE)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
    print(line, end="")


# ── Atomic file write (same pattern as poll.py) ──────────────────────────────

def write_atomic(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


# ── Safe value helpers ───────────────────────────────────────────────────────

def _safe(val, unit: str = "", fallback: str = "N/A") -> str:
    if val is None or val == -1:
        return fallback
    return f"{val}{unit}"


def _fmt_duration_seconds(seconds) -> str:
    if not seconds:
        return "N/A"
    try:
        s = int(seconds)
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}h {m}m" if h else f"{m}m"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_distance_m(metres) -> str:
    if not metres:
        return "N/A"
    try:
        km = float(metres) / 1000
        return f"{km:.2f} km"
    except (TypeError, ValueError):
        return "N/A"


# ── Garmin data fetching ─────────────────────────────────────────────────────

def get_client():
    try:
        import garminconnect
    except ImportError:
        log("ERROR: garminconnect not installed. Run: pip3 install garminconnect")
        sys.exit(1)

    email    = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "").strip()

    if not email or not password:
        log("ERROR: GARMIN_EMAIL and GARMIN_PASSWORD must be set in environment.")
        log("  Add them to ~/.openclaw/.env and source it before running.")
        sys.exit(1)

    client = garminconnect.Garmin(email, password)

    TOKEN_STORE.mkdir(parents=True, exist_ok=True)
    token_store_str = str(TOKEN_STORE)

    try:
        client.login(token_store_str)
        log("Garmin: loaded cached session tokens")
    except FileNotFoundError:
        log("Garmin: no cached tokens — performing full login (MFA prompt may appear)")
        _mfa_login(client, token_store_str)
    except Exception as e:
        err = str(e).lower()
        if "auth" in err or "login" in err or "401" in err or "403" in err:
            log(f"Garmin: cached token invalid ({e}) — re-authenticating")
            _mfa_login(client, token_store_str)
        else:
            raise

    return client


def _mfa_login(client, token_store_str: str):
    """Full login with optional MFA. Saves tokens on success."""
    try:
        client.login()
    except Exception as e:
        err_str = str(e)
        if "MFA" in err_str or "NEEDS_MFA" in err_str or "auth" in err_str.lower():
            log("Garmin: MFA required — prompting for one-time code")
            mfa = input("Enter Garmin MFA code: ").strip()
            client.garth.resume(token_store_str)
            client.login(mfa_code=mfa)
        else:
            raise

    try:
        client.garth.dump(token_store_str)
        log(f"Garmin: session tokens saved to {token_store_str}")
    except Exception as dump_err:
        log(f"WARNING: Could not save Garmin tokens — next run will re-authenticate: {dump_err}")


def fetch_stats(client, today: str) -> dict:
    try:
        return client.get_stats(today) or {}
    except Exception as e:
        log(f"WARNING: get_stats failed: {e}")
        return {}


def fetch_hrv(client, today: str) -> dict:
    try:
        data = client.get_hrv_data(today)
        return data or {}
    except Exception as e:
        log(f"WARNING: get_hrv_data failed: {e}")
        return {}


def fetch_sleep(client, today: str) -> dict:
    try:
        data = client.get_sleep_data(today)
        return data or {}
    except Exception as e:
        log(f"WARNING: get_sleep_data failed: {e}")
        return {}


def fetch_body_battery(client, today: str):
    try:
        data = client.get_body_battery(today, today)
        return data
    except Exception as e:
        log(f"WARNING: get_body_battery failed: {e}")
        return None


def fetch_last_activity(client) -> dict:
    try:
        activities = client.get_activities(0, 1)
        if activities:
            return activities[0]
    except Exception as e:
        log(f"WARNING: get_activities failed: {e}")
    return {}


# ── Parse body battery readings ──────────────────────────────────────────────

def parse_body_battery_peak(data) -> str:
    """
    garminconnect returns body battery as a list of readings.
    Each entry is typically [timestamp_ms, charged_value, active_value]
    or a dict with 'charged'/'active' keys. Extract the peak charged value.
    """
    if not data:
        return "N/A"
    try:
        peak = None
        for entry in data:
            charged = None
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                charged = entry[1]
            elif isinstance(entry, dict):
                charged = entry.get("charged") or entry.get("value") or entry.get("bodyBatteryLevel")
            if charged is not None:
                try:
                    v = int(charged)
                    if peak is None or v > peak:
                        peak = v
                except (TypeError, ValueError):
                    pass
        return f"{peak}" if peak is not None else "N/A"
    except Exception as e:
        log(f"WARNING: body battery parse failed: {e}")
        return "N/A"


# ── Build markdown output ────────────────────────────────────────────────────

def build_markdown(stats: dict, hrv: dict, sleep: dict, body_battery_raw,
                   activity: dict) -> str:
    now      = datetime.now()
    today    = date.today().strftime("%A, %d %B %Y")
    updated  = now.strftime("%Y-%m-%d %H:%M")

    # Stats
    resting_hr = _safe(stats.get("restingHeartRate"), " bpm")
    steps      = _safe(stats.get("totalSteps"))
    if steps != "N/A":
        try:
            steps = f"{int(steps):,}"
        except (ValueError, TypeError):
            pass
    avg_stress = _safe(stats.get("averageStressLevel"))
    if avg_stress != "N/A":
        avg_stress = f"{avg_stress}/100"

    # HRV
    hrv_summary = hrv.get("hrvSummary") or {}
    hrv_status  = _safe(hrv_summary.get("status"))
    hrv_value   = _safe(hrv_summary.get("lastNight"), " ms")

    # Sleep
    sleep_dto   = sleep.get("dailySleepDTO") or {}
    scores      = sleep_dto.get("sleepScores") or {}
    overall     = scores.get("overall") or {}
    sleep_score = _safe(overall.get("value"), "/100")
    sleep_secs  = sleep_dto.get("sleepTimeSeconds") or sleep_dto.get("sleepTimeTotalSeconds")
    sleep_dur   = _fmt_duration_seconds(sleep_secs)

    # Body battery
    bb_peak = parse_body_battery_peak(body_battery_raw)

    # Activity
    act_name     = activity.get("activityName") or activity.get("activityType", {}).get("typeKey") or "N/A"
    act_distance = _fmt_distance_m(activity.get("distance"))
    act_duration = _fmt_duration_seconds(activity.get("duration"))
    act_hr       = _safe(activity.get("averageHR"), " bpm")
    act_date_raw = activity.get("startTimeLocal") or activity.get("startTimeGMT") or ""
    act_date     = act_date_raw[:10] if act_date_raw else "N/A"

    lines = [
        f"# Garmin Daily — {today}",
        f"_Last updated: {updated}_",
        "",
        "## Heart Rate",
        f"- **Resting HR**: {resting_hr}",
        "",
        "## HRV",
        f"- **Status**: {hrv_status}",
        f"- **Last night**: {hrv_value}",
        "",
        "## Sleep",
        f"- **Score**: {sleep_score}",
        f"- **Duration**: {sleep_dur}",
        "",
        "## Stress & Energy",
        f"- **Average stress**: {avg_stress}",
        f"- **Body battery peak**: {bb_peak}",
        "",
        "## Activity",
        f"- **Steps**: {steps}",
        "",
        "## Most Recent Activity",
    ]

    if activity:
        lines += [
            f"- **Name**: {act_name}",
            f"- **Date**: {act_date}",
            f"- **Distance**: {act_distance}",
            f"- **Duration**: {act_duration}",
            f"- **Avg HR**: {act_hr}",
        ]
    else:
        lines.append("- No activity recorded")

    lines.append("")
    return "\n".join(lines)


# ── Rolling archive (28-day compact history) ─────────────────────────────────

def build_archive_entry(stats: dict, hrv: dict, sleep: dict, body_battery_raw,
                        activity: dict) -> str:
    """One compact line per day — enough for L1 to spot trends."""
    resting_hr  = _safe(stats.get("restingHeartRate"), " bpm")
    steps       = stats.get("totalSteps")
    steps_fmt   = f"{int(steps):,}" if steps else "N/A"
    avg_stress  = _safe(stats.get("averageStressLevel"), "/100")

    hrv_summary = hrv.get("hrvSummary") or {}
    hrv_val     = _safe(hrv_summary.get("lastNight"), " ms")
    hrv_status  = _safe(hrv_summary.get("status"))
    hrv_str     = f"{hrv_val} ({hrv_status})" if hrv_val != "N/A" else "N/A"

    sleep_dto   = sleep.get("dailySleepDTO") or {}
    scores      = sleep_dto.get("sleepScores") or {}
    overall     = scores.get("overall") or {}
    sleep_score = _safe(overall.get("value"), "/100")
    sleep_secs  = sleep_dto.get("sleepTimeSeconds") or sleep_dto.get("sleepTimeTotalSeconds")
    sleep_dur   = _fmt_duration_seconds(sleep_secs)
    sleep_str   = f"{sleep_dur} ({sleep_score})" if sleep_dur != "N/A" else "N/A"

    bb          = parse_body_battery_peak(body_battery_raw)

    act_name    = activity.get("activityName") or "N/A"
    act_dist    = _fmt_distance_m(activity.get("distance"))
    act_str     = f"{act_name} {act_dist}".strip() if activity else "N/A"

    return (
        f"HR: {resting_hr} | HRV: {hrv_str} | Sleep: {sleep_str} | "
        f"Stress: {avg_stress} | BB: {bb} | Steps: {steps_fmt} | Activity: {act_str}"
    )


def update_archive(entry_line: str, today: str):
    """
    Upsert today's entry into GARMIN_ARCHIVE.md and trim to ARCHIVE_RETAIN_DAYS.
    Sections are delimited by '## YYYY-MM-DD' headings — one per day.
    """
    import re
    cutoff = (date.today() - timedelta(days=ARCHIVE_RETAIN_DAYS)).strftime("%Y-%m-%d")

    # Load existing archive or start fresh
    try:
        raw = ARCHIVE_MD.read_text(encoding="utf-8") if ARCHIVE_MD.exists() else ""
    except Exception as e:
        log(f"WARNING: Could not read archive: {e} — starting fresh")
        raw = ""

    # Split into sections: each starts with '## YYYY-MM-DD'
    date_pattern = re.compile(r"^## (\d{4}-\d{2}-\d{2})$", re.MULTILINE)
    matches = list(date_pattern.finditer(raw))

    sections: dict[str, str] = {}  # date_str → body lines (excluding the heading)
    for i, m in enumerate(matches):
        sec_date = m.group(1)
        start    = m.end()
        end      = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections[sec_date] = raw[start:end].strip()

    # Upsert today
    sections[today] = entry_line

    # Trim to retain window (drop anything older than cutoff)
    sections = {d: v for d, v in sections.items() if d >= cutoff}

    # Rebuild — newest first
    updated  = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines    = [
        "# Garmin Archive — Rolling 28 Days",
        f"_Last updated: {updated}_",
        "",
        "_One entry per day. HR = resting heart rate. BB = body battery peak. "
        "Sleep shown as duration (score/100)._",
        "",
    ]
    for d in sorted(sections.keys(), reverse=True):
        lines.append(f"## {d}")
        lines.append(sections[d])
        lines.append("")

    try:
        write_atomic(ARCHIVE_MD, "\n".join(lines))
        log(f"Archive updated: {len(sections)} entries (rolling {ARCHIVE_RETAIN_DAYS} days) → {ARCHIVE_MD}")
    except Exception as e:
        log(f"WARNING: Could not write archive: {e}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    log("Garmin poller starting")

    today = date.today().strftime("%Y-%m-%d")

    try:
        client = get_client()
    except SystemExit:
        raise
    except Exception as e:
        log(f"ERROR: Garmin login failed: {e}")
        log("FLAG TO TOM: poll-garmin.py could not authenticate with Garmin Connect.")
        sys.exit(1)

    log(f"Fetching Garmin data for {today}")

    stats       = fetch_stats(client, today)
    hrv         = fetch_hrv(client, today)
    sleep       = fetch_sleep(client, today)
    body_bat    = fetch_body_battery(client, today)
    activity    = fetch_last_activity(client)

    md = build_markdown(stats, hrv, sleep, body_bat, activity)

    try:
        write_atomic(OUTPUT_MD, md)
        log(f"Written: {OUTPUT_MD}")
    except Exception as e:
        log(f"ERROR: Failed to write {OUTPUT_MD}: {e}")
        log("FLAG TO TOM: poll-garmin.py could not write GARMIN_DAILY.md.")
        sys.exit(1)

    # Update rolling 28-day archive (non-fatal — daily file is the priority)
    try:
        archive_entry = build_archive_entry(stats, hrv, sleep, body_bat, activity)
        update_archive(archive_entry, today)
    except Exception as e:
        log(f"WARNING: Archive update failed: {e} — daily file is unaffected")

    log("Garmin poller complete")


if __name__ == "__main__":
    main()
