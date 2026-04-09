#!/usr/bin/env python3
"""
Garmin Connect daily health data poller for OpenClaw.

Auth: uses garth's standard ~/.garth token store.
  - First run: prompts interactively for email/password, saves tokens to ~/.garth.
  - Subsequent runs: resumes silently from ~/.garth — no credentials needed.
  - GARMIN_EMAIL / GARMIN_PASSWORD env vars are used if present on first run,
    otherwise the script prompts interactively.

Fetches today's data:
  - Resting heart rate
  - HRV (last night, weekly average, status)
  - Sleep (duration, score, deep, REM, avg HR during sleep)
  - SpO2 (overnight average)
  - Average stress
  - Body battery (high and low)
  - Steps, calories, active minutes
  - Most recent activity

Writes two files:
  GARMIN_DAILY.md   — today's full snapshot, overwritten each run (never grows)
  GARMIN_ARCHIVE.md — rolling 28-day compact history, always in workspace.
                      L1 uses this proactively to spot trends and advise.

Scheduled at 09:00 daily (NOT 06:xx — CRM runs at 06:00; 07:xx also busy).

Dependencies:
  pip3 install --break-system-packages garminconnect garth
"""
import getpass
import os
import sys
import json
from datetime import datetime, date, timedelta, timezone
from pathlib import Path


def _load_dotenv() -> None:
    """Load ~/.openclaw/.env into os.environ so cron runs pick up credentials
    without needing a manual 'source' step first."""
    env_file = Path.home() / ".openclaw" / ".env"
    if not env_file.exists():
        return
    with env_file.open() as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

_load_dotenv()

OPENCLAW          = Path.home() / ".openclaw"
GARTH_HOME        = Path.home() / ".garth"          # garth standard token store
OUTPUT_MD         = OPENCLAW / "workspace/GARMIN_DAILY.md"
ARCHIVE_MD        = OPENCLAW / "workspace/GARMIN_ARCHIVE.md"
LOG_FILE          = OPENCLAW / "workspace/memory/poll-garmin-log.txt"

LOG_MAX_LINES     = 1000
LOG_TRIM_TO       = 800
ARCHIVE_RETAIN_DAYS = 28


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        existing = LOG_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    except FileNotFoundError:
        existing = []
    if len(existing) >= LOG_MAX_LINES:
        existing = existing[-LOG_TRIM_TO:]
    existing.append(line)
    tmp = LOG_FILE.with_suffix(".tmp")
    try:
        tmp.write_text("".join(existing), encoding="utf-8")
        tmp.replace(LOG_FILE)
    except Exception:
        tmp.unlink(missing_ok=True)
    print(line, end="", flush=True)


# ── Atomic write ──────────────────────────────────────────────────────────────

def write_atomic(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ── Value helpers ─────────────────────────────────────────────────────────────

def _safe(val, unit: str = "", fallback: str = "n/a") -> str:
    if val is None or val == -1:
        return fallback
    try:
        if isinstance(val, float) and val != val:  # NaN check
            return fallback
    except Exception:
        pass
    return f"{val}{unit}"


def _fmt_dur(seconds) -> str:
    if not seconds:
        return "n/a"
    try:
        s = int(seconds)
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}h {m}m" if h else f"{m}m"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_km(metres) -> str:
    if not metres:
        return "n/a"
    try:
        return f"{float(metres) / 1000:.2f} km"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_int(val) -> str:
    if val is None or val == -1:
        return "n/a"
    try:
        return f"{int(val):,}"
    except (TypeError, ValueError):
        return "n/a"


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_client():
    try:
        from garminconnect import Garmin
    except ImportError:
        log("ERROR: garminconnect not installed. Run: pip3 install --break-system-packages garminconnect garth")
        sys.exit(1)

    GARTH_HOME.mkdir(parents=True, exist_ok=True)

    # Attempt to resume a saved session — no credentials needed on repeat runs.
    client = Garmin()
    try:
        client.garth.load(str(GARTH_HOME))
        # Quick validation: call a lightweight endpoint to confirm tokens are live
        client.get_full_name()
        log(f"Garmin: resumed session from {GARTH_HOME}")
        return client
    except Exception:
        pass  # No tokens or expired — fall through to interactive login

    log("Garmin: no valid saved session — performing login")
    email    = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "").strip()

    interactive = sys.stdin.isatty()

    if not email:
        if interactive:
            email = input("Garmin email: ").strip()
        else:
            log("ERROR: GARMIN_EMAIL not set in ~/.openclaw/.env — cannot login non-interactively.")
            log("FLAG TO TOM: Add GARMIN_EMAIL=your@email.com to ~/.openclaw/.env then re-run /garmin.")
            sys.exit(1)
    if not password:
        if interactive:
            password = getpass.getpass("Garmin password: ")
        else:
            log("ERROR: GARMIN_PASSWORD not set in ~/.openclaw/.env — cannot login non-interactively.")
            log("FLAG TO TOM: Add GARMIN_PASSWORD=yourpassword to ~/.openclaw/.env then re-run /garmin.")
            sys.exit(1)

    client = Garmin(email, password)
    try:
        client.login()
    except Exception as e:
        err = str(e)
        if "429" in err or "Too Many Requests" in err:
            log("ERROR: Garmin rate-limited (429). Stop retrying and wait several hours.")
        elif "MFA" in err or "NEEDS_MFA" in err:
            if interactive:
                log("Garmin: MFA required")
                mfa = input("Enter Garmin MFA code: ").strip()
                client.login(mfa_code=mfa)
            else:
                log("ERROR: Garmin MFA required but running non-interactively — cannot prompt.")
                log("FLAG TO TOM: Run poll-garmin.py manually in a terminal to complete MFA, then the saved session will be used for future runs.")
                sys.exit(1)
        else:
            log(f"ERROR: Garmin login failed: {e}")
            raise
        if "429" in err:
            raise

    try:
        client.garth.dump(str(GARTH_HOME))
        log(f"Garmin: session tokens saved to {GARTH_HOME}")
    except Exception as dump_err:
        log(f"WARNING: Could not save tokens: {dump_err}")

    return client


# ── Data fetchers ─────────────────────────────────────────────────────────────

def _fetch(label: str, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        return result or {}
    except Exception as e:
        log(f"WARNING: {label} failed: {e}")
        return {}


def fetch_stats(client, today):
    return _fetch("get_stats", client.get_stats, today)

def fetch_hrv(client, today):
    return _fetch("get_hrv_data", client.get_hrv_data, today)

def fetch_sleep(client, today):
    return _fetch("get_sleep_data", client.get_sleep_data, today)

def fetch_spo2(client, today):
    return _fetch("get_spo2_data", client.get_spo2_data, today)

def fetch_respiration(client, today):
    return _fetch("get_respiration_data", client.get_respiration_data, today)

def fetch_body_battery(client, today):
    try:
        data = client.get_body_battery(today, today)
        return data
    except Exception as e:
        log(f"WARNING: get_body_battery failed: {e}")
        return None

def fetch_last_activity(client):
    try:
        acts = client.get_activities(0, 1)
        return acts[0] if acts else {}
    except Exception as e:
        log(f"WARNING: get_activities failed: {e}")
        return {}


# ── Body battery parsing ──────────────────────────────────────────────────────

def parse_body_battery(data):
    """Return (high, low) strings from the raw body battery list."""
    if not data:
        return "n/a", "n/a"
    values = []
    try:
        for entry in data:
            charged = None
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                charged = entry[1]
            elif isinstance(entry, dict):
                charged = (entry.get("charged") or entry.get("value")
                           or entry.get("bodyBatteryLevel"))
            if charged is not None:
                try:
                    values.append(int(charged))
                except (TypeError, ValueError):
                    pass
    except Exception as e:
        log(f"WARNING: body battery parse error: {e}")
    if not values:
        return "n/a", "n/a"
    return str(max(values)), str(min(values))


# ── Markdown builder ──────────────────────────────────────────────────────────

def build_markdown(stats: dict, hrv: dict, sleep: dict, spo2: dict,
                   body_battery_raw, activity: dict) -> str:
    now     = datetime.now()
    today   = date.today().strftime("%A, %d %B %Y")
    updated = now.strftime("%Y-%m-%d %H:%M")

    # ── Stats ──
    resting_hr    = _safe(stats.get("restingHeartRate"), " bpm")
    steps         = _fmt_int(stats.get("totalSteps"))
    calories      = _fmt_int(stats.get("totalKilocalories"))
    active_cals   = _fmt_int(stats.get("activeKilocalories"))
    avg_stress    = _safe(stats.get("averageStressLevel"))
    avg_stress    = f"{avg_stress}/100" if avg_stress != "n/a" else "n/a"
    intensity_mod = _fmt_int(stats.get("moderateIntensityMinutes"))
    intensity_vig = _fmt_int(stats.get("vigorousIntensityMinutes"))
    active_mins   = "n/a"
    try:
        m = int(stats.get("moderateIntensityMinutes") or 0)
        v = int(stats.get("vigorousIntensityMinutes") or 0)
        if m or v:
            active_mins = f"{m + v} min ({m} mod + {v} vig)"
    except (TypeError, ValueError):
        pass

    # ── HRV ──
    hrv_summary  = hrv.get("hrvSummary") or {}
    hrv_status   = _safe(hrv_summary.get("status"))
    hrv_last     = _safe(hrv_summary.get("lastNight"), " ms")
    hrv_weekly   = _safe(hrv_summary.get("weeklyAvg"), " ms")

    # ── Sleep ──
    sleep_dto    = sleep.get("dailySleepDTO") or {}
    scores       = sleep_dto.get("sleepScores") or {}
    overall      = scores.get("overall") or {}
    sleep_score  = _safe(overall.get("value"), "/100")
    sleep_secs   = (sleep_dto.get("sleepTimeSeconds")
                    or sleep_dto.get("sleepTimeTotalSeconds"))
    sleep_dur    = _fmt_dur(sleep_secs)
    deep_dur     = _fmt_dur(sleep_dto.get("deepSleepSeconds"))
    rem_dur      = _fmt_dur(sleep_dto.get("remSleepSeconds"))
    light_dur    = _fmt_dur(sleep_dto.get("lightSleepSeconds"))
    awake_dur    = _fmt_dur(sleep_dto.get("awakeSleepSeconds"))
    avg_sleep_hr = _safe(sleep_dto.get("averageSpO2Value"))  # sometimes stored here
    sleep_avg_hr = _safe(sleep_dto.get("averageSleepStress"))  # fallback label
    # Avg HR during sleep — may be under restingHeartRate or sleepHeartRate
    sleep_hr = _safe(sleep_dto.get("sleepHeartRate") or sleep_dto.get("avgSleepHeartRate"), " bpm")

    # ── SpO2 ──
    spo2_avg = "n/a"
    try:
        if isinstance(spo2, dict):
            spo2_avg = _safe(spo2.get("averageSpO2") or spo2.get("averageSpo2"), " %")
        elif isinstance(spo2, list) and spo2:
            vals = [e.get("value") or e.get("spo2") for e in spo2 if isinstance(e, dict)]
            vals = [v for v in vals if v is not None]
            if vals:
                spo2_avg = f"{sum(vals) / len(vals):.0f} %"
    except Exception:
        pass

    # ── Body battery ──
    bb_high, bb_low = parse_body_battery(body_battery_raw)

    # ── Activity ──
    act_name = (activity.get("activityName")
                or (activity.get("activityType") or {}).get("typeKey") or "n/a")
    act_dist = _fmt_km(activity.get("distance"))
    act_dur  = _fmt_dur(activity.get("duration"))
    act_hr   = _safe(activity.get("averageHR"), " bpm")
    act_date = (activity.get("startTimeLocal") or activity.get("startTimeGMT") or "")[:10] or "n/a"

    lines = [
        f"# Garmin Daily — {today}",
        f"_Last updated: {updated}_",
        "",
        "## Heart Rate",
        f"- **Resting HR**: {resting_hr}",
        f"- **Avg HR during sleep**: {sleep_hr}",
        "",
        "## HRV",
        f"- **Status**: {hrv_status}",
        f"- **Last night**: {hrv_last}",
        f"- **Weekly average**: {hrv_weekly}",
        "",
        "## Sleep",
        f"- **Duration**: {sleep_dur}",
        f"- **Score**: {sleep_score}",
        f"- **Deep**: {deep_dur}",
        f"- **REM**: {rem_dur}",
        f"- **Light**: {light_dur}",
        f"- **Awake**: {awake_dur}",
        "",
        "## Oxygen",
        f"- **SpO2 (overnight avg)**: {spo2_avg}",
        "",
        "## Stress & Energy",
        f"- **Average stress**: {avg_stress}",
        f"- **Body battery high**: {bb_high}",
        f"- **Body battery low**: {bb_low}",
        "",
        "## Activity",
        f"- **Steps**: {steps}",
        f"- **Calories (total)**: {calories} kcal",
        f"- **Calories (active)**: {active_cals} kcal",
        f"- **Active minutes**: {active_mins}",
        "",
        "## Most Recent Activity",
    ]

    if activity:
        lines += [
            f"- **Name**: {act_name}",
            f"- **Date**: {act_date}",
            f"- **Distance**: {act_dist}",
            f"- **Duration**: {act_dur}",
            f"- **Avg HR**: {act_hr}",
        ]
    else:
        lines.append("- No activity recorded")

    lines.append("")
    return "\n".join(lines)


# ── Rolling archive (28-day compact history) ──────────────────────────────────

def build_archive_entry(stats: dict, hrv: dict, sleep: dict, spo2: dict,
                        body_battery_raw, activity: dict) -> str:
    resting_hr  = _safe(stats.get("restingHeartRate"), " bpm")
    steps       = _fmt_int(stats.get("totalSteps"))
    avg_stress  = _safe(stats.get("averageStressLevel"), "/100")

    hrv_summary = hrv.get("hrvSummary") or {}
    hrv_val     = _safe(hrv_summary.get("lastNight"), " ms")
    hrv_status  = _safe(hrv_summary.get("status"))
    hrv_str     = f"{hrv_val} ({hrv_status})" if hrv_val != "n/a" else "n/a"

    sleep_dto   = sleep.get("dailySleepDTO") or {}
    scores      = sleep_dto.get("sleepScores") or {}
    overall     = scores.get("overall") or {}
    sleep_score = _safe(overall.get("value"), "/100")
    sleep_secs  = (sleep_dto.get("sleepTimeSeconds")
                   or sleep_dto.get("sleepTimeTotalSeconds"))
    sleep_dur   = _fmt_dur(sleep_secs)
    sleep_str   = f"{sleep_dur} ({sleep_score})" if sleep_dur != "n/a" else "n/a"

    bb_high, bb_low = parse_body_battery(body_battery_raw)
    bb_str = f"{bb_high}↑ {bb_low}↓" if bb_high != "n/a" else "n/a"

    act_name = (activity.get("activityName")
                or (activity.get("activityType") or {}).get("typeKey") or "")
    act_dist = _fmt_km(activity.get("distance"))
    act_str  = f"{act_name} {act_dist}".strip() if activity else "n/a"

    return (
        f"HR: {resting_hr} | HRV: {hrv_str} | Sleep: {sleep_str} | "
        f"Stress: {avg_stress} | BB: {bb_str} | Steps: {steps} | Activity: {act_str}"
    )


def update_archive(entry_line: str, today_str: str):
    import re
    cutoff = (date.today() - timedelta(days=ARCHIVE_RETAIN_DAYS)).strftime("%Y-%m-%d")

    try:
        raw = ARCHIVE_MD.read_text(encoding="utf-8") if ARCHIVE_MD.exists() else ""
    except Exception as e:
        log(f"WARNING: Could not read archive: {e} — starting fresh")
        raw = ""

    date_pattern = re.compile(r"^## (\d{4}-\d{2}-\d{2})$", re.MULTILINE)
    matches = list(date_pattern.finditer(raw))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        sec_date = m.group(1)
        start    = m.end()
        end      = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections[sec_date] = raw[start:end].strip()

    sections[today_str] = entry_line
    sections = {d: v for d, v in sections.items() if d >= cutoff}

    updated = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Garmin Archive — Rolling 28 Days",
        f"_Last updated: {updated}_",
        "",
        "_One entry per day. HR = resting heart rate. BB = body battery high↑/low↓. "
        "Sleep shown as duration (score/100)._",
        "",
    ]
    for d in sorted(sections.keys(), reverse=True):
        lines.append(f"## {d}")
        lines.append(sections[d])
        lines.append("")

    try:
        write_atomic(ARCHIVE_MD, "\n".join(lines))
        log(f"Archive updated: {len(sections)} entries → {ARCHIVE_MD}")
    except Exception as e:
        log(f"WARNING: Could not write archive: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

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

    log(f"Fetching data for {today}")
    stats    = fetch_stats(client, today)
    hrv      = fetch_hrv(client, today)
    sleep    = fetch_sleep(client, today)
    spo2     = fetch_spo2(client, today)
    body_bat = fetch_body_battery(client, today)
    activity = fetch_last_activity(client)

    md = build_markdown(stats, hrv, sleep, spo2, body_bat, activity)

    try:
        write_atomic(OUTPUT_MD, md)
        log(f"Written: {OUTPUT_MD}")
    except Exception as e:
        log(f"ERROR: Failed to write {OUTPUT_MD}: {e}")
        log("FLAG TO TOM: poll-garmin.py could not write GARMIN_DAILY.md.")
        sys.exit(1)

    try:
        archive_entry = build_archive_entry(stats, hrv, sleep, spo2, body_bat, activity)
        update_archive(archive_entry, today)
    except Exception as e:
        log(f"WARNING: Archive update failed: {e} — daily file is unaffected")

    log("Garmin poller complete")


if __name__ == "__main__":
    main()
