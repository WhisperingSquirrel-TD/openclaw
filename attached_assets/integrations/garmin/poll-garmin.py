#!/usr/bin/env python3
"""
Garmin Connect health-data poller for OpenClaw.

Uses the maintained `garminconnect` library (Garmin's current DI OAuth flow).
You authenticate ONCE; the library caches a self-renewing refresh token, so
scheduled runs never log in again — they only resume from the cached token and
auto-refresh.  This is what fixes the old 429 spiral: the previous garth-based
auth was blocked by Garmin and every cron run re-attempted a login, which made
the per-account rate-limit ban worse.

Auth model
----------
  • One-time setup (run once, from anywhere):
        python3 poll-garmin.py --setup
    Reads GARMIN_EMAIL + GARMIN_PASSWORD from ~/.openclaw/.env, logs in
    (prompting for an MFA code only if your account has MFA enabled), and
    saves tokens to ~/.garminconnect/.

  • Scheduled / cron run (no interaction, no credential login ever):
        python3 poll-garmin.py
    Resumes from the cached token and auto-refreshes.  If the token is missing
    or rejected it FLAGS TOM to re-run setup instead of attempting a login.

  • Token status (never logs in):
        python3 poll-garmin.py --status

  • Backfill history into the archive:
        python3 poll-garmin.py --backfill 30

Golden rule (enforced below): never call a credential login from the scheduled
path.  A 429 anywhere writes a cooldown stamp that suppresses all login
attempts for COOLDOWN_HOURS.

Outputs:
  GARMIN_DAILY.md   — today's full snapshot (overwritten each run)
  GARMIN_ARCHIVE.md — rolling 28-day compact history for trend analysis
"""
import os
import sys
import json
import time
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path

OPENCLAW    = Path.home() / ".openclaw"
GARMIN_DIR  = OPENCLAW / "integrations" / "garmin"
# garminconnect caches its token(s) here (current versions: garmin_tokens.json;
# older versions: oauth1_token.json + oauth2_token.json).
TOKENSTORE  = Path(os.environ.get("GARMINTOKENS", str(Path.home() / ".garminconnect")))
OUTPUT_MD   = OPENCLAW / "workspace" / "GARMIN_DAILY.md"
ARCHIVE_MD  = OPENCLAW / "workspace" / "GARMIN_ARCHIVE.md"
LOG_FILE    = OPENCLAW / "workspace" / "memory" / "poll-garmin-log.txt"
BACKOFF_FILE = GARMIN_DIR / ".garmin_429_backoff"

LOG_MAX_LINES       = 1000
LOG_TRIM_TO         = 800
ARCHIVE_RETAIN_DAYS = 28
COOLDOWN_HOURS      = 24      # after a 429, suppress all login attempts this long
LOG_TO_STDOUT       = False   # keep Garmin chatter out of aggregated runtime logs


# ── Logging ─────────────────────────────────────────────────────────────────────

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
    if LOG_TO_STDOUT:
        print(line, end="", flush=True)


def say(msg: str):
    """Print to stdout (for interactive --setup/--status and mgmt-bot tails) and log."""
    print(msg, flush=True)
    log(msg)


# ── Atomic write ────────────────────────────────────────────────────────────────

def write_atomic(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ── .env loader ───────────────────────────────────────────────────────────────--

def _load_dotenv() -> None:
    env_file = OPENCLAW / ".env"
    if not env_file.exists():
        return
    try:
        for raw in env_file.read_text(encoding="utf-8").splitlines():
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
    except Exception:
        pass


# ── Formatting helpers ───────────────────────────────────────────────────────---

def _safe(val, suffix: str = "") -> str:
    if val is None or val == "" or val == -1:
        return "n/a"
    return f"{val}{suffix}"


def _fmt_int(val) -> str:
    try:
        return f"{int(val):,}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_dur(seconds) -> str:
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return "n/a"
    if s <= 0:
        return "n/a"
    h, m = divmod(s // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _fmt_km(meters) -> str:
    try:
        km = float(meters) / 1000.0
    except (TypeError, ValueError):
        return "n/a"
    if km <= 0:
        return "n/a"
    return f"{km:.2f} km"


def _deep_find(obj, key: str):
    """Recursively search a nested dict/list for the first value under `key`."""
    if isinstance(obj, dict):
        if key in obj and obj[key] not in (None, "", -1):
            return obj[key]
        for v in obj.values():
            found = _deep_find(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _deep_find(v, key)
            if found is not None:
                return found
    return None


# ── 429 cooldown guard ───────────────────────────────────────────────────────---

def _in_cooldown() -> int:
    """Return remaining cooldown minutes if a recent 429 stamp exists, else 0."""
    if not BACKOFF_FILE.exists():
        return 0
    try:
        age = time.time() - BACKOFF_FILE.stat().st_mtime
    except OSError:
        return 0
    remaining = COOLDOWN_HOURS * 3600 - age
    return int(remaining / 60) if remaining > 0 else 0


def _mark_429():
    try:
        GARMIN_DIR.mkdir(parents=True, exist_ok=True)
        BACKOFF_FILE.touch()
    except OSError:
        pass


def _clear_cooldown():
    BACKOFF_FILE.unlink(missing_ok=True)


# ── Authentication ───────────────────────────────────────────────────────────---

def _import_garmin():
    try:
        from garminconnect import (
            Garmin,
            GarminConnectAuthenticationError,
            GarminConnectTooManyRequestsError,
        )
        return Garmin, GarminConnectAuthenticationError, GarminConnectTooManyRequestsError
    except ImportError:
        raise RuntimeError(
            "garminconnect not installed. Run: "
            "pip3 install --break-system-packages --upgrade garminconnect"
        )


# Token filenames differ across garminconnect/garth versions: the current
# garminconnect bundles a garth fork that writes a SINGLE consolidated
# `garmin_tokens.json`, while older versions wrote `oauth1_token.json`
# (+ `oauth2_token.json`). Detection must accept any known layout.
TOKEN_FILENAMES = ("garmin_tokens.json", "oauth1_token.json")


def _token_file():
    """Return the cached token file (whichever layout exists), or None."""
    for name in TOKEN_FILENAMES:
        p = TOKENSTORE / name
        if p.exists():
            return p
    return None


def _tokens_present() -> bool:
    return _token_file() is not None


def _persist_tokens(client) -> None:
    """Write the in-memory OAuth tokens to TOKENSTORE after a credential login.

    The garth client that actually holds the tokens is an internal attribute of
    the Garmin object whose name changed across garminconnect versions
    (`.garth` in older releases, `.client` in current ones). Try each known
    handle and stop as soon as the token file lands on disk.
    """
    TOKENSTORE.mkdir(parents=True, exist_ok=True)
    last_err = None
    for attr in ("garth", "client"):
        garth_client = getattr(client, attr, None)
        dump = getattr(garth_client, "dump", None) if garth_client is not None else None
        if callable(dump):
            try:
                dump(str(TOKENSTORE))
                if _tokens_present():
                    return
            except Exception as e:
                last_err = e
    if last_err is not None:
        log(f"WARNING: token dump attempts failed: {last_err}")


def _mfa_prompt() -> str:
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Garmin MFA required but no terminal is attached. "
            "Run setup from a terminal: python3 poll-garmin.py --setup"
        )
    return input("Garmin MFA code: ").strip()


def resume_client():
    """
    Resume a session from cached tokens WITHOUT any credential login.
    Constructed with no email/password, so it can never fall through to an SSO
    login (and therefore can never trigger a 429 ban) — it either loads valid
    tokens / silently refreshes, or raises.
    """
    Garmin, AuthErr, TooMany = _import_garmin()
    if not _tokens_present():
        raise RuntimeError("NO_TOKENS")
    client = Garmin()
    try:
        client.login(str(TOKENSTORE))
    except TooMany as e:
        _mark_429()
        raise RuntimeError(f"RATE_LIMITED: {e}")
    except AuthErr as e:
        raise RuntimeError(f"TOKENS_REJECTED: {e}")
    except Exception as e:
        # Connection/transport errors etc. — surface as a controlled failure so
        # get_client_for_run()/cmd_status() never crash with a raw traceback.
        raise RuntimeError(f"RESUME_FAILED: {e}")
    return client


def login_and_save(interactive: bool):
    """
    One-time credential login (setup). Reads GARMIN_EMAIL/GARMIN_PASSWORD from
    the environment, logs in (MFA prompt only if the account requires it), and
    persists tokens to TOKENSTORE.
    """
    Garmin, AuthErr, TooMany = _import_garmin()
    email    = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError("GARMIN_EMAIL or GARMIN_PASSWORD missing from ~/.openclaw/.env")

    TOKENSTORE.mkdir(parents=True, exist_ok=True)
    mfa_cb = _mfa_prompt if interactive else None
    client = Garmin(email=email, password=password, is_cn=False, prompt_mfa=mfa_cb)
    # Force a FRESH credential login. We deliberately do NOT pass TOKENSTORE to
    # login() here: on first-time setup the token dir is empty, and some
    # garminconnect/garth versions try to LOAD oauth1_token.json before falling
    # back to credentials — raising
    #   [Errno 2] No such file or directory: '~/.garminconnect/oauth1_token.json'
    # We also temporarily clear GARMINTOKENS so login() can't pick up a path and
    # attempt the same doomed load.
    _saved_tokenenv = os.environ.pop("GARMINTOKENS", None)
    try:
        client.login()
    except TooMany as e:
        _mark_429()
        raise RuntimeError(
            f"Garmin SSO rate-limited (429): {e}. The ban is per-account and "
            f"lasts 24-72h — do NOT retry. Wait, then run --setup once."
        )
    except AuthErr as e:
        raise RuntimeError(f"Login failed (check credentials / MFA): {e}")
    finally:
        if _saved_tokenenv is not None:
            os.environ["GARMINTOKENS"] = _saved_tokenenv
    # Persist tokens so scheduled runs can resume from them (version-robust dump),
    # then verify the file actually landed — otherwise we'd report success while
    # leaving nothing for cron to resume, forcing repeated logins (429 risk).
    _persist_tokens(client)
    if not _tokens_present():
        raise RuntimeError(
            f"Login succeeded but no token file was written to {TOKENSTORE}. "
            f"Upgrade the library and retry once: "
            f"pip3 install --break-system-packages --upgrade garminconnect"
        )
    _clear_cooldown()
    try:
        os.chmod(TOKENSTORE, 0o700)
        for f in TOKENSTORE.glob("*"):
            os.chmod(f, 0o600)
    except OSError:
        pass
    return client


def get_client_for_run():
    """
    Auth path for scheduled/backfill runs. NEVER performs a credential login.
    Exits cleanly with a clear flag if setup is needed.
    """
    mins = _in_cooldown()
    if mins:
        log(f"Garmin: in 429 cooldown for {mins}m more — skipping run to avoid worsening the ban.")
        sys.exit(0)

    if not _tokens_present():
        log("ERROR: No cached Garmin tokens.")
        log("FLAG TO TOM: run one-time setup → python3 ~/.openclaw/integrations/garmin/poll-garmin.py --setup")
        sys.exit(1)

    try:
        client = resume_client()
        log("Garmin: resumed session from cached tokens (auto-refresh).")
        return client
    except RuntimeError as e:
        err = str(e)
        if "RATE_LIMITED" in err:
            log(f"ERROR: Garmin rate-limited (429) on resume — cooldown set. {err}")
            sys.exit(1)
        log(f"ERROR: Cached Garmin tokens rejected/invalid ({err}).")
        log("FLAG TO TOM: re-run setup → python3 ~/.openclaw/integrations/garmin/poll-garmin.py --setup")
        sys.exit(1)


# ── Safe API call wrapper ──────────────────────────────────────────────────────-

def _call(client, label: str, method_name: str, *args):
    """Call a garminconnect method by name, swallowing per-metric errors."""
    _, _, TooMany = _import_garmin()
    fn = getattr(client, method_name, None)
    if fn is None:
        log(f"WARNING: {label}: method {method_name}() not in this garminconnect version")
        return None
    try:
        return fn(*args)
    except TooMany as e:
        _mark_429()
        log(f"ERROR: Garmin rate-limited (429) on {label} — cooldown set. {e}")
        sys.exit(1)
    except Exception as e:
        log(f"WARNING: {label} failed: {e}")
        return None


# ── Data fetch ──────────────────────────────────────────────────────────────────

def fetch_all(client, day: str) -> dict:
    log(f"Garmin: fetching data for {day}")
    data = {
        "stats":      _call(client, "stats",      "get_stats",              day) or {},
        "hr":         _call(client, "heart_rate",  "get_heart_rates",       day) or {},
        "hrv":        _call(client, "hrv",         "get_hrv_data",          day) or {},
        "sleep":      _call(client, "sleep",       "get_sleep_data",        day) or {},
        "spo2":       _call(client, "spo2",        "get_spo2_data",         day) or {},
        "stress":     _call(client, "stress",      "get_stress_data",       day) or {},
        "readiness":  _call(client, "readiness",   "get_training_readiness", day) or {},
        "body_bat":   _call(client, "body_battery", "get_body_battery",     day, day) or [],
        "max_metrics": _call(client, "max_metrics", "get_max_metrics",      day) or {},
    }
    acts = _call(client, "activities", "get_activities", 0, 5)
    data["activities"] = acts if isinstance(acts, list) else (acts or [])

    # Post-workout recovery HR lives in activity details — fetch for the latest one.
    data["recovery_hr"] = None
    if data["activities"]:
        latest = data["activities"][0]
        rhr = _deep_find(latest, "recoveryHeartRate")
        if rhr is None:
            act_id = latest.get("activityId")
            if act_id is not None:
                details = _call(client, "activity_details", "get_activity", act_id)
                rhr = _deep_find(details or {}, "recoveryHeartRate")
        data["recovery_hr"] = rhr
    return data


# ── Extraction ───────────────────────────────────────────────────────────────---

def extract(day: str, data: dict) -> dict:
    stats     = data.get("stats") or {}
    hr        = data.get("hr") or {}
    hrv       = data.get("hrv") or {}
    sleep_raw = data.get("sleep") or {}
    spo2      = data.get("spo2") or {}
    stress    = data.get("stress") or {}
    readiness = data.get("readiness") or {}
    body_bat  = data.get("body_bat") or []
    maxm      = data.get("max_metrics") or {}
    acts      = data.get("activities") or []

    if isinstance(readiness, list):
        readiness = readiness[0] if readiness else {}

    out = {}
    out["resting_hr"] = (stats.get("restingHeartRate")
                         or hr.get("restingHeartRate"))

    # HRV
    hrv_summary = hrv.get("hrvSummary") if isinstance(hrv, dict) else {}
    hrv_summary = hrv_summary or {}
    out["hrv_last"]   = hrv_summary.get("lastNightAvg")
    out["hrv_status"] = hrv_summary.get("status")
    out["hrv_weekly"] = hrv_summary.get("weeklyAvg")

    # Training readiness (recovery readiness)
    out["readiness_score"]    = readiness.get("score")
    out["readiness_level"]    = readiness.get("level")
    out["readiness_feedback"] = (readiness.get("feedbackShort")
                                 or readiness.get("feedbackLong"))

    # Sleep
    sdto = (sleep_raw.get("dailySleepDTO") if isinstance(sleep_raw, dict) else {}) or {}
    out["sleep_secs"]  = sdto.get("sleepTimeSeconds")
    out["deep_secs"]   = sdto.get("deepSleepSeconds")
    out["rem_secs"]    = sdto.get("remSleepSeconds")
    out["light_secs"]  = sdto.get("lightSleepSeconds")
    out["awake_secs"]  = sdto.get("awakeSleepSeconds")
    scores = sdto.get("sleepScores") or {}
    out["sleep_score"] = (scores.get("overall") or {}).get("value") if isinstance(scores, dict) else None
    out["sleep_hr"]    = sleep_raw.get("restingHeartRate") if isinstance(sleep_raw, dict) else None

    # SpO2
    out["spo2_avg"] = spo2.get("averageSpO2") if isinstance(spo2, dict) else None
    out["spo2_low"] = spo2.get("lowestSpO2") if isinstance(spo2, dict) else None

    # Stress (prefer dedicated endpoint, fall back to stats)
    avg_stress = stress.get("avgStressLevel") if isinstance(stress, dict) else None
    max_stress = stress.get("maxStressLevel") if isinstance(stress, dict) else None
    if avg_stress in (None, -1):
        avg_stress = stats.get("averageStressLevel")
    if max_stress in (None, -1):
        max_stress = stats.get("maxStressLevel")
    out["avg_stress"] = avg_stress
    out["max_stress"] = max_stress

    # Body Battery (peak/low)
    out["bb_high"], out["bb_low"] = _parse_body_battery(body_bat, stats)

    # VO2 max
    gen = maxm.get("generic") if isinstance(maxm, dict) else None
    if isinstance(maxm, list) and maxm:
        gen = (maxm[0] or {}).get("generic")
    out["vo2max"] = (gen or {}).get("vo2MaxPreciseValue") or (gen or {}).get("vo2MaxValue") if gen else None

    # Steps / calories / intensity minutes
    out["steps"]       = stats.get("totalSteps")
    out["calories"]    = stats.get("totalKilocalories")
    out["active_cals"] = stats.get("activeKilocalories")
    try:
        mod = int(stats.get("moderateIntensityMinutes") or 0)
        vig = int(stats.get("vigorousIntensityMinutes") or 0)
        out["intensity_min"] = (mod, vig) if (mod or vig) else None
    except (TypeError, ValueError):
        out["intensity_min"] = None

    # Recent activity + recovery HR
    out["recovery_hr"] = data.get("recovery_hr")
    if acts:
        a = acts[0]
        out["act_name"] = (a.get("activityName")
                           or (a.get("activityType") or {}).get("typeKey") or "n/a")
        out["act_date"] = (a.get("startTimeLocal") or a.get("startTimeGMT") or "")[:10] or "n/a"
        out["act_dist"] = a.get("distance")
        out["act_dur"]  = a.get("duration")
        out["act_avg_hr"] = a.get("averageHR")
        out["act_max_hr"] = a.get("maxHR")
    else:
        out["act_name"] = None
    return out


def _parse_body_battery(body_bat, stats) -> tuple:
    high = low = None
    if isinstance(stats, dict):
        high = stats.get("bodyBatteryHighestValue")
        low  = stats.get("bodyBatteryLowestValue")
    if (high is None or low is None) and isinstance(body_bat, list):
        levels = []
        for day_entry in body_bat:
            arr = (day_entry or {}).get("bodyBatteryValuesArray") or []
            for point in arr:
                # point shapes: [ts, level] or [ts, status, level]
                if isinstance(point, list) and point:
                    val = point[-1]
                    if isinstance(val, (int, float)):
                        levels.append(val)
        if levels:
            high = max(levels) if high is None else high
            low  = min(levels) if low is None else low
    return high, low


# ── Markdown builders ────────────────────────────────────────────────────────---

def build_markdown(day: str, x: dict) -> str:
    updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    if x.get("intensity_min"):
        mod, vig = x["intensity_min"]
        active_mins = f"{mod + vig} min ({mod} mod + {vig} vig)"
    else:
        active_mins = "n/a"

    lines = [
        f"# Garmin Daily — {day}",
        f"_Last updated: {updated}_",
        "",
        "## Recovery & Readiness",
        f"- **Training readiness**: {_safe(x.get('readiness_score'), '/100')}"
        + (f" ({x['readiness_level']})" if x.get("readiness_level") else ""),
        f"- **Readiness note**: {_safe(x.get('readiness_feedback'))}",
        f"- **HRV status**: {_safe(x.get('hrv_status'))}",
        f"- **HRV last night**: {_safe(x.get('hrv_last'), ' ms')}",
        f"- **HRV weekly avg**: {_safe(x.get('hrv_weekly'), ' ms')}",
        f"- **Body Battery high**: {_safe(x.get('bb_high'))}",
        f"- **Body Battery low**: {_safe(x.get('bb_low'))}",
        "",
        "## Heart Rate",
        f"- **Resting HR**: {_safe(x.get('resting_hr'), ' bpm')}",
        f"- **Avg HR during sleep**: {_safe(x.get('sleep_hr'), ' bpm')}",
        f"- **Post-workout recovery HR**: {_safe(x.get('recovery_hr'), ' bpm')}",
        "",
        "## Sleep",
        f"- **Duration**: {_fmt_dur(x.get('sleep_secs'))}",
        f"- **Score**: {_safe(x.get('sleep_score'), '/100')}",
        f"- **Deep**: {_fmt_dur(x.get('deep_secs'))}",
        f"- **REM**: {_fmt_dur(x.get('rem_secs'))}",
        f"- **Light**: {_fmt_dur(x.get('light_secs'))}",
        f"- **Awake**: {_fmt_dur(x.get('awake_secs'))}",
        "",
        "## Oxygen & Stress",
        f"- **SpO2 (overnight avg)**: {_safe(x.get('spo2_avg'), '%')}",
        f"- **SpO2 (lowest)**: {_safe(x.get('spo2_low'), '%')}",
        f"- **Average stress**: {_safe(x.get('avg_stress'), '/100')}",
        f"- **Peak stress**: {_safe(x.get('max_stress'), '/100')}",
        "",
        "## Fitness & Activity",
        f"- **VO2 max**: {_safe(x.get('vo2max'))}",
        f"- **Steps**: {_fmt_int(x.get('steps'))}",
        f"- **Calories (total)**: {_safe(x.get('calories'), ' kcal')}",
        f"- **Calories (active)**: {_safe(x.get('active_cals'), ' kcal')}",
        f"- **Active minutes**: {active_mins}",
        "",
        "## Most Recent Activity",
    ]
    if x.get("act_name"):
        lines += [
            f"- **Name**: {x.get('act_name')}",
            f"- **Date**: {x.get('act_date')}",
            f"- **Distance**: {_fmt_km(x.get('act_dist'))}",
            f"- **Duration**: {_fmt_dur(x.get('act_dur'))}",
            f"- **Avg HR**: {_safe(x.get('act_avg_hr'), ' bpm')}",
            f"- **Max HR**: {_safe(x.get('act_max_hr'), ' bpm')}",
            f"- **Recovery HR**: {_safe(x.get('recovery_hr'), ' bpm')}",
        ]
    else:
        lines.append("- No activity recorded")
    lines.append("")
    return "\n".join(lines)


def build_archive_entry(x: dict) -> str:
    rhr   = _safe(x.get("resting_hr"), " bpm")
    ready = _safe(x.get("readiness_score"), "/100")
    hrv_v = _safe(x.get("hrv_last"), " ms")
    hrv_s = x.get("hrv_status")
    hrv   = f"{hrv_v} ({hrv_s})" if hrv_v != "n/a" and hrv_s else hrv_v
    sleep = _fmt_dur(x.get("sleep_secs"))
    sc    = x.get("sleep_score")
    sleep_str = f"{sleep} ({sc}/100)" if sleep != "n/a" and sc else sleep
    stress = _safe(x.get("avg_stress"), "/100")
    bb_h, bb_l = x.get("bb_high"), x.get("bb_low")
    bb = f"{bb_h}↑ {bb_l}↓" if bb_h is not None else "n/a"
    steps = _fmt_int(x.get("steps"))
    act = x.get("act_name") or ""
    act_str = f"{act} {_fmt_km(x.get('act_dist'))}".strip() if act else "n/a"
    return (
        f"Readiness: {ready} | HR: {rhr} | HRV: {hrv} | Sleep: {sleep_str} | "
        f"Stress: {stress} | BB: {bb} | Steps: {steps} | Activity: {act_str}"
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
    sections: dict = {}
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


# ── Backfill ────────────────────────────────────────────────────────────────────

def run_backfill(client, days: int):
    import re
    log(f"Backfill: starting — requesting {days} days of history")
    raw = ARCHIVE_MD.read_text(encoding="utf-8") if ARCHIVE_MD.exists() else ""
    date_pattern = re.compile(r"^## (\d{4}-\d{2}-\d{2})$", re.MULTILINE)
    matches = list(date_pattern.finditer(raw))
    sections: dict = {}
    for i, m in enumerate(matches):
        sec_date = m.group(1)
        start    = m.end()
        end      = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections[sec_date] = raw[start:end].strip()

    today = date.today()
    fetched = skipped = failed = 0
    for offset in range(1, days + 1):
        target = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        if target in sections and sections[target].count(": n/a") < 5 \
           and "n/a |" not in sections[target]:
            skipped += 1
            continue
        try:
            data  = fetch_all(client, target)
            x     = extract(target, data)
            sections[target] = build_archive_entry(x)
            fetched += 1
            log(f"Backfill: {target} — OK")
        except SystemExit:
            raise
        except Exception as e:
            log(f"Backfill: {target} — FAILED: {e}")
            failed += 1
        time.sleep(1)  # gentle pacing

    updated = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Garmin Archive — Rolling History",
        f"_Last updated: {updated} (backfill — {fetched} new days)_",
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
        log(f"Backfill complete: {fetched} fetched, {skipped} skipped, {failed} failed")
    except Exception as e:
        log(f"ERROR: Could not write archive after backfill: {e}")


# ── Setup / status commands ──────────────────────────────────────────────────---

def cmd_setup():
    _load_dotenv()
    say("=== Garmin Setup (one-time) ===")
    say("Authenticating with GARMIN_EMAIL + GARMIN_PASSWORD from ~/.openclaw/.env")
    interactive = sys.stdin.isatty()
    if interactive:
        say("If your account has MFA enabled you will be prompted for a code.")
    try:
        client = login_and_save(interactive=interactive)
        name = client.get_full_name()
        say(f"SUCCESS — logged in as: {name}")
        say(f"Tokens cached in: {TOKENSTORE}/")
        say("The daily cron at 09:00 will now resume from these tokens automatically.")
    except RuntimeError as e:
        say(f"ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        say(f"ERROR: setup failed: {e}")
        sys.exit(1)


def cmd_status():
    _load_dotenv()
    mins = _in_cooldown()
    if mins:
        say(f"429 cooldown active: {mins} minutes remaining (logins suppressed).")
        say("Skipping token probe during cooldown to avoid contacting Garmin.")
        return
    if not _tokens_present():
        say("No cached tokens — run setup: python3 poll-garmin.py --setup")
        sys.exit(1)
    try:
        tf = _token_file()
        if tf is not None:
            age_s = time.time() - tf.stat().st_mtime
            say(f"Token age: {int(age_s / 86400)} days ({tf.name}; auto-refreshes).")
    except OSError:
        pass
    try:
        client = resume_client()
        name = client.get_full_name()
        say(f"OK — tokens valid. Logged in as: {name}")
    except RuntimeError as e:
        if "RATE_LIMITED" in str(e):
            say(f"Garmin rate-limited (429): {e}")
        else:
            say(f"Tokens invalid/rejected ({e}) — re-run setup: python3 poll-garmin.py --setup")
        sys.exit(1)


# ── Debug dump ────────────────────────────────────────────────────────────────--

def _debug_dump(day: str, data: dict, x: dict):
    """Print the raw shape of every endpoint + the extracted values.

    Distinguishes the three reasons a field shows 'n/a':
      • endpoint ERRORED   → value is None/{}/[] AND a 'WARNING: <label> failed'
                             line appears above in this output/log;
      • data genuinely absent → endpoint returned {} or a dict missing the key
                             (e.g. watch not worn overnight, or device lacks the
                             feature) with NO warning;
      • key drift          → endpoint returned a populated dict but under keys the
                             extractor doesn't read (top-level keys shown below).
    """
    import json as _json
    say(f"=== GARMIN RAW ENDPOINT DUMP (debug) — day={day} ===")
    for key in ("stats", "hr", "hrv", "sleep", "spo2", "stress",
                "readiness", "body_bat", "max_metrics", "activities"):
        val = data.get(key)
        if isinstance(val, dict):
            say(f"[{key}] dict, top-level keys: {sorted(val.keys())}")
        elif isinstance(val, list):
            first = val[0] if val else None
            fk = sorted(first.keys()) if isinstance(first, dict) else type(first).__name__
            say(f"[{key}] list len={len(val)}, first item keys/type: {fk}")
        else:
            say(f"[{key}] {type(val).__name__}: {val!r}")
        try:
            say(f"    json[:1000]: {_json.dumps(val, default=str)[:1000]}")
        except Exception as e:
            say(f"    (json dump failed: {e})")
    say("--- EXTRACTED VALUES (None/'n/a' = missing) ---")
    for k in sorted(x.keys()):
        say(f"    {k} = {x[k]!r}")
    say("=== END DUMP ===")


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Garmin Connect poller (garminconnect library)")
    parser.add_argument("--setup", action="store_true",
                        help="One-time credential login; caches tokens. MFA prompt if needed.")
    parser.add_argument("--status", action="store_true",
                        help="Report token validity/age. Never logs in.")
    parser.add_argument("--backfill", type=int, metavar="DAYS", nargs="?", const=30,
                        help="Fetch historical data into GARMIN_ARCHIVE.md (default 30 days).")
    parser.add_argument("--debug", action="store_true",
                        help="Dump raw endpoint responses + extracted values to diagnose "
                             "missing fields, then write files as usual.")
    args = parser.parse_args()

    if args.setup:
        cmd_setup()
        return
    if args.status:
        cmd_status()
        return

    _load_dotenv()
    log("Garmin poller starting")
    today = date.today().strftime("%Y-%m-%d")

    client = get_client_for_run()

    if args.backfill:
        run_backfill(client, args.backfill)
        return

    data = fetch_all(client, today)
    x    = extract(today, data)

    if args.debug:
        _debug_dump(today, data, x)

    md = build_markdown(today, x)
    try:
        write_atomic(OUTPUT_MD, md)
        log(f"Written: {OUTPUT_MD}")
    except Exception as e:
        log(f"ERROR: Failed to write {OUTPUT_MD}: {e}")
        log("FLAG TO TOM: poll-garmin.py could not write GARMIN_DAILY.md.")
        sys.exit(1)

    try:
        update_archive(build_archive_entry(x), today)
    except Exception as e:
        log(f"WARNING: Archive update failed: {e} — daily file is unaffected")

    say("Garmin poller complete")


if __name__ == "__main__":
    main()
