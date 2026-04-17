#!/usr/bin/env python3
"""
Garmin Connect cookie-based health data poller for OpenClaw.

Bypasses garth/OAuth entirely — uses browser session cookies to call
Garmin Connect's internal API directly. No rate-limit risk from auth flows.

Setup (one-time):
  python3 poll-garmin-cookie.py --setup

  Follow the prompts to paste cookie values from your browser.
  Cookies are saved to ~/.openclaw/integrations/garmin/garmin-cookies.json.

When cookies expire (usually 7-14 days):
  1. Log into connect.garmin.com in your browser
  2. Run: python3 poll-garmin-cookie.py --setup
  3. Paste fresh cookies

Normal run (cron-safe, no interaction needed):
  python3 poll-garmin-cookie.py

Outputs:
  GARMIN_DAILY.md   — today's full snapshot (overwritten each run)
  GARMIN_ARCHIVE.md — rolling 28-day compact history
"""
import os
import sys
import json
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    import urllib.request as urllib_request
    import urllib.error as urllib_error
except ImportError:
    pass

OPENCLAW       = Path.home() / ".openclaw"
GARMIN_DIR     = OPENCLAW / "integrations" / "garmin"
COOKIE_FILE    = GARMIN_DIR / "garmin-cookies.json"
OUTPUT_MD      = OPENCLAW / "workspace" / "GARMIN_DAILY.md"
ARCHIVE_MD     = OPENCLAW / "workspace" / "GARMIN_ARCHIVE.md"
LOG_FILE       = OPENCLAW / "workspace" / "memory" / "poll-garmin-log.txt"

LOG_MAX_LINES     = 1000
LOG_TRIM_TO       = 800
ARCHIVE_RETAIN_DAYS = 28

BASE_URL = "https://connect.garmin.com"


# ── Logging ────────────────────────────────────────────────────────────────────

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


# ── Atomic write ───────────────────────────────────────────────────────────────

def write_atomic(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ── Cookie management ──────────────────────────────────────────────────────────

def load_cookies() -> dict:
    if not COOKIE_FILE.exists():
        log("ERROR: Cookie file not found. Run: python3 poll-garmin-cookie.py --setup")
        log("FLAG TO TOM: Garmin cookie file missing — run setup on the Pi.")
        sys.exit(1)
    try:
        data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        if not data.get("SESSIONID"):
            log("ERROR: Cookie file is missing SESSIONID. Run --setup again.")
            sys.exit(1)
        return data
    except Exception as e:
        log(f"ERROR: Could not read cookie file: {e}")
        sys.exit(1)


def cookies_to_header(cookies: dict) -> str:
    parts = []
    for key, val in cookies.items():
        if val and key not in ("_saved_at", "_note"):
            parts.append(f"{key}={val}")
    return "; ".join(parts)


def setup_cookies():
    print("\n=== Garmin Cookie Setup ===")
    print("1. Open connect.garmin.com in your browser and log in")
    print("2. Press F12 → Application tab → Cookies → https://connect.garmin.com")
    print("3. Paste the values below (press Enter to skip optional ones)\n")

    cookies = {}

    sessionid = input("SESSIONID (required): ").strip()
    if not sessionid:
        print("ERROR: SESSIONID is required.")
        sys.exit(1)
    cookies["SESSIONID"] = sessionid

    session = input("session (optional but recommended): ").strip()
    if session:
        cookies["session"] = session

    cflb = input("_cflb (optional): ").strip()
    if cflb:
        cookies["_cflb"] = cflb

    jwt = input("JWT_WEB (optional): ").strip()
    if jwt:
        cookies["JWT_WEB"] = jwt

    cookies["_saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    cookies["_note"] = "Created by poll-garmin-cookie.py --setup"

    GARMIN_DIR.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    print(f"\nCookies saved to {COOKIE_FILE}")
    print("Running a quick test fetch...")

    try:
        display_name = get_display_name(cookies)
        print(f"SUCCESS — logged in as: {display_name}")
        log(f"Cookie setup complete. Display name: {display_name}")
    except Exception as e:
        print(f"WARNING: Test fetch failed ({e}) — cookies may be incomplete or expired.")
        log(f"WARNING: Cookie setup test failed: {e}")


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _get(path: str, cookies: dict, params: dict = None) -> dict:
    url = BASE_URL + path
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"

    req = urllib_request.Request(url)
    req.add_header("Cookie", cookies_to_header(cookies))
    req.add_header("NK", "NT")
    req.add_header("X-app-ver", "4.61.2.0")
    req.add_header("Accept", "application/json, text/javascript, */*; q=0.01")
    req.add_header("User-Agent",
        "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    req.add_header("Referer", "https://connect.garmin.com/modern/")
    req.add_header("X-Requested-With", "XMLHttpRequest")

    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            if not body.strip():
                return {}
            return json.loads(body)
    except urllib_error.HTTPError as e:
        code = e.code
        if code == 401:
            raise RuntimeError("COOKIES_EXPIRED")
        if code == 429:
            raise RuntimeError("RATE_LIMITED")
        raise RuntimeError(f"HTTP {code}: {e.reason}")
    except Exception as e:
        raise RuntimeError(str(e))


def _safe_get(label: str, path: str, cookies: dict, params: dict = None):
    try:
        return _get(path, cookies, params)
    except RuntimeError as e:
        err = str(e)
        if "COOKIES_EXPIRED" in err:
            log(f"ERROR: Garmin cookies have expired. Run --setup on the Pi to refresh them.")
            log("FLAG TO TOM: Garmin cookies expired — log into connect.garmin.com and run --setup.")
            sys.exit(1)
        if "RATE_LIMITED" in err:
            log("ERROR: Garmin rate-limited (429). Wait and try again later.")
            sys.exit(1)
        log(f"WARNING: {label} failed: {err}")
        return {}
    except Exception as e:
        log(f"WARNING: {label} failed: {e}")
        return {}


# ── Garth-mode auth + HTTP (uses GARMIN_EMAIL / GARMIN_PASSWORD from .env) ──────
#
# When credentials are present the poller authenticates via the garminconnect
# library (which wraps garth OAuth2).  Garth stores tokens in ~/.garth/ and
# refreshes them automatically, so re-auth only happens once every few weeks —
# completely avoiding the "cookie expired every 7 days" problem.
#
# Garth's `connectapi()` hits https://connectapi.garmin.com{path}, so the
# paths are the same as the cookie paths but WITHOUT the /modern/proxy/ prefix.

def _garth_mfa_prompt():
    """MFA callback for garth — only works from an interactive terminal."""
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Garmin MFA required but running as a service (no TTY). "
            "Run setup manually: python3 ~/.openclaw/integrations/garmin/poll-garmin-cookie.py --setup-garth"
        )
    return input("Garmin MFA code: ").strip()


def _garth_auth(interactive: bool = False):
    """
    Authenticate with Garmin using GARMIN_EMAIL + GARMIN_PASSWORD from .env.
    Returns a garminconnect.Garmin instance with an active session.
    Tokens are cached in ~/.garth/ and auto-refreshed by garth on future runs.
    Raises RuntimeError with a clear message on any failure.

    interactive=True: called from --setup-garth (terminal, MFA prompt OK)
    interactive=False: called from cron/service (MFA will raise, not hang)
    """
    try:
        from garminconnect import Garmin
    except ImportError:
        raise RuntimeError(
            "garminconnect not installed. Run: "
            "pip3 install --break-system-packages garminconnect"
        )

    email    = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError("GARMIN_EMAIL or GARMIN_PASSWORD missing from ~/.openclaw/.env")

    garth_token_dir = Path.home() / ".garth"
    garth_token_dir.mkdir(parents=True, exist_ok=True)

    mfa_cb = _garth_mfa_prompt if interactive else None
    try:
        api = Garmin(email=email, password=password, is_cn=False, prompt_mfa=mfa_cb)
    except TypeError:
        # Older garminconnect without prompt_mfa param
        api = Garmin(email, password)

    # Try token cache first (avoids triggering auth endpoints on every run)
    token_file = garth_token_dir / "oauth2_token.json"
    if token_file.exists() or (garth_token_dir / "token.json").exists():
        try:
            api.login(tokenstore=str(garth_token_dir))
            log(f"Garth: resumed session from cached tokens in {garth_token_dir}")
            return api
        except Exception as e:
            log(f"Garth: cached tokens invalid ({e}) — attempting fresh login")

    # No valid cached tokens — need a fresh login
    if not interactive and not sys.stdin.isatty():
        raise RuntimeError(
            "Garth tokens missing or expired and running as a service (no TTY). "
            "Run first-time setup: python3 ~/.openclaw/integrations/garmin/poll-garmin-cookie.py --setup-garth"
        )

    log("Garth: logging in with email/password...")
    try:
        api.login()
        try:
            api.garth.dump(str(garth_token_dir))
        except AttributeError:
            pass  # older garminconnect versions may not have dump()
        log(f"Garth: login successful — tokens cached in {garth_token_dir}")
    except Exception as e:
        raise RuntimeError(f"Garth login failed: {e}")

    return api


def setup_garth():
    """
    Interactive first-time Garmin auth via garth/credentials.
    Handles MFA prompt. Run once from a terminal; subsequent runs use cached tokens.
    """
    _load_dotenv()
    print("\n=== Garmin Garth Setup ===")
    print("Authenticating with GARMIN_EMAIL + GARMIN_PASSWORD from ~/.openclaw/.env")
    print("If MFA is enabled you will be prompted for a code.\n")

    try:
        api = _garth_auth(interactive=True)
        dn = _garth_display_name(api)
        print(f"\nSUCCESS — logged in as: {dn}")
        print(f"Tokens cached in: {Path.home() / '.garth'}/")
        print("The daily cron at 09:00 will now use these tokens automatically.")
        log(f"Garth setup complete. Display name: {dn}")
    except Exception as e:
        print(f"\nERROR: {e}")
        print("Check GARMIN_EMAIL and GARMIN_PASSWORD in ~/.openclaw/.env")
        sys.exit(1)


def _garth_get(api, path: str, params: dict = None) -> dict:
    """Make an authenticated GET to connectapi.garmin.com via garth."""
    try:
        kwargs = {"params": params} if params else {}
        result = api.garth.connectapi(path, **kwargs)
        return result if result else {}
    except Exception as e:
        err = str(e)
        if "401" in err or "Unauthorized" in err.lower():
            raise RuntimeError("COOKIES_EXPIRED")
        if "429" in err:
            raise RuntimeError("RATE_LIMITED")
        raise RuntimeError(err)


def _garth_safe_get(api, label: str, path: str, params: dict = None):
    try:
        return _garth_get(api, path, params)
    except RuntimeError as e:
        err = str(e)
        if "COOKIES_EXPIRED" in err:
            log(f"ERROR: Garth 401 on {label} — tokens may be revoked.")
            log(f"  Delete ~/.garth/ and re-run to force a fresh login.")
            sys.exit(1)
        if "RATE_LIMITED" in err:
            log(f"ERROR: Garmin rate-limited (429) on {label}. Wait and retry.")
            sys.exit(1)
        log(f"WARNING: {label} failed (garth): {err}")
        return {}
    except Exception as e:
        log(f"WARNING: {label} failed (garth): {e}")
        return {}


def _garth_display_name(api) -> str:
    """
    Get displayName via garth.
    Resolution order: env var override → garth.username → userprofile API.
    """
    override = os.environ.get("GARMIN_DISPLAY_NAME", "").strip()
    if override:
        log(f"Using GARMIN_DISPLAY_NAME override: {override}")
        return override

    # garth exposes the username after login
    try:
        dn = api.garth.username
        if dn:
            log(f"Garth: display name from garth.username = '{dn}'")
            return dn
    except Exception:
        pass

    # Fall back to the userprofile API (same endpoint, no /modern/proxy/ prefix)
    try:
        data = _garth_get(api, "/userprofile-service/userprofile/settings")
        dn = (
            (data.get("userData") or {}).get("displayName")
            or data.get("displayName")
            or data.get("userName")
        )
        if dn:
            log(f"Garth: display name from userprofile API = '{dn}'")
            return dn
    except Exception as e:
        log(f"WARNING: garth userprofile API failed: {e}")

    raise RuntimeError(
        "Could not resolve Garmin displayName in garth mode. "
        "Set GARMIN_DISPLAY_NAME=YourUsername in ~/.openclaw/.env"
    )


def _fetch_all_garth(api, today: str):
    """
    Run all data fetches using garth (connectapi paths — no /modern/proxy/ prefix).
    Returns the same tuple as the cookie-based fetch calls in main():
        (stats_raw, wellness_raw, hr_raw, hrv_raw, sleep_raw, spo2_raw, body_bat, activity)
    """
    display_name = _garth_display_name(api)
    log(f"Garth: fetching data for {today} (user={display_name})")

    stats_raw = _garth_safe_get(api, "stats",
        f"/userstats-service/statistics/daily/{display_name}",
        {"fromDate": today, "untilDate": today, "metricId": "60,61,51,71,2,56,57"})

    wellness_raw = _garth_safe_get(api, "wellness",
        f"/wellness-service/wellness/dailySummaryChart/{display_name}",
        {"date": today})

    hr_raw = _garth_safe_get(api, "resting_hr",
        f"/wellness-service/wellness/dailyHeartRate/{display_name}",
        {"date": today})

    hrv_raw = _garth_safe_get(api, "hrv",
        f"/hrv-service/hrv/{today}")

    sleep_raw = _garth_safe_get(api, "sleep",
        f"/wellness-service/wellness/dailySleepData/{display_name}",
        {"date": today, "nonSleepBufferMinutes": "60"})

    spo2_raw = _garth_safe_get(api, "spo2",
        f"/wellness-service/wellness/dailySpo2/{display_name}",
        {"calendarDate": today})

    bb_raw = _garth_safe_get(api, "body_battery",
        "/wellness-service/wellness/bodyBattery/reports/daily",
        {"startDate": today, "endDate": today})
    if isinstance(bb_raw, list):
        body_bat = bb_raw
    elif isinstance(bb_raw, dict):
        body_bat = bb_raw.get("bodyBatteryFeedbackList") or bb_raw.get("bodyBatteryList") or []
    else:
        body_bat = []

    act_raw = _garth_safe_get(api, "activities",
        "/activitylist-service/activities/search/activities",
        {"limit": "1", "start": "0"})
    activity = act_raw[0] if isinstance(act_raw, list) and act_raw else {}

    return stats_raw, wellness_raw, hr_raw, hrv_raw, sleep_raw, spo2_raw, body_bat, activity


# ── Data fetchers ──────────────────────────────────────────────────────────────

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


def get_display_name(cookies: dict) -> str:
    """
    Resolve the Garmin displayName needed for per-user API calls.

    Resolution order:
    1. GARMIN_DISPLAY_NAME env var (fastest, manual override — set in ~/.openclaw/.env)
    2. /modern/proxy/userprofile-service/userprofile/settings  (primary API)
    3. /modern/proxy/userprofile-service/socialProfile/        (alternative endpoint)
    4. /proxy/userprofile-service/userprofile/settings         (no /modern prefix fallback)

    If all fail: raises RuntimeError with a clear flag message.

    To set a manual override (avoids the API call entirely):
        echo 'GARMIN_DISPLAY_NAME=YourGarminUsername' >> ~/.openclaw/.env
    Find your username: log into connect.garmin.com, look at the profile URL.
    """
    # 1. Manual env var override — most reliable, skips the API call entirely
    override = os.environ.get("GARMIN_DISPLAY_NAME", "").strip()
    if override:
        log(f"Using GARMIN_DISPLAY_NAME override: {override}")
        return override

    endpoints = [
        "/modern/proxy/userprofile-service/userprofile/settings",
        "/modern/proxy/userprofile-service/socialProfile/",
        "/proxy/userprofile-service/userprofile/settings",
    ]

    last_error = ""
    for ep in endpoints:
        try:
            data = _get(ep, cookies)
            name = (
                (data.get("userData") or {}).get("displayName")
                or data.get("displayName")
                or data.get("userName")
                or data.get("screenName")
                or (data.get("userProfile") or {}).get("displayName")
            )
            if name:
                log(f"Resolved displayName='{name}' via {ep}")
                return name
            log(f"WARNING: {ep} returned data but no displayName field — trying next endpoint")
        except RuntimeError as e:
            err = str(e)
            last_error = err
            if "COOKIES_EXPIRED" in err or "RATE_LIMITED" in err:
                raise  # propagate immediately — no point trying other endpoints
            log(f"WARNING: {ep} failed ({err}) — trying next endpoint")
        except Exception as e:
            last_error = str(e)
            log(f"WARNING: {ep} failed ({e}) — trying next endpoint")

    raise RuntimeError(
        f"Could not resolve Garmin displayName from any endpoint. "
        f"Last error: {last_error}. "
        f"To fix: set GARMIN_DISPLAY_NAME=YourUsername in ~/.openclaw/.env "
        f"(find your username in the connect.garmin.com profile URL)"
    )


def fetch_stats(cookies: dict, display_name: str, today: str) -> dict:
    return _safe_get("stats",
        f"/modern/proxy/userstats-service/statistics/daily/{display_name}",
        cookies,
        {"fromDate": today, "untilDate": today, "metricId": "60,61,51,71,2,56,57"})


def fetch_wellness(cookies: dict, display_name: str, today: str) -> dict:
    return _safe_get("wellness",
        f"/modern/proxy/wellness-service/wellness/dailySummaryChart/{display_name}",
        cookies,
        {"date": today})


def fetch_hrv(cookies: dict, today: str) -> dict:
    return _safe_get("hrv",
        f"/modern/proxy/hrv-service/hrv/{today}",
        cookies)


def fetch_sleep(cookies: dict, display_name: str, today: str) -> dict:
    return _safe_get("sleep",
        f"/modern/proxy/wellness-service/wellness/dailySleepData/{display_name}",
        cookies,
        {"date": today, "nonSleepBufferMinutes": "60"})


def fetch_spo2(cookies: dict, display_name: str, today: str) -> dict:
    return _safe_get("spo2",
        f"/modern/proxy/wellness-service/wellness/dailySpo2/{display_name}",
        cookies,
        {"calendarDate": today})


def fetch_body_battery(cookies: dict, today: str):
    data = _safe_get("body_battery",
        "/modern/proxy/wellness-service/wellness/bodyBattery/reports/daily",
        cookies,
        {"startDate": today, "endDate": today})
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("bodyBatteryFeedbackList") or data.get("bodyBatteryList") or []
    return []


def fetch_last_activity(cookies: dict) -> dict:
    data = _safe_get("activities",
        "/modern/proxy/activitylist-service/activities/search/activities",
        cookies,
        {"limit": "1", "start": "0"})
    if isinstance(data, list) and data:
        return data[0]
    return {}


def fetch_resting_hr(cookies: dict, display_name: str, today: str) -> dict:
    return _safe_get("resting_hr",
        f"/modern/proxy/wellness-service/wellness/dailyHeartRate/{display_name}",
        cookies,
        {"date": today})


# ── Value helpers ──────────────────────────────────────────────────────────────

def _safe(val, unit: str = "", fallback: str = "n/a") -> str:
    if val is None or val == -1:
        return fallback
    try:
        if isinstance(val, float) and val != val:
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


# ── Stat extraction helpers ────────────────────────────────────────────────────

def extract_stats(stats_raw: dict, wellness_raw, hr_raw: dict) -> dict:
    """
    The userstats endpoint returns a list of metric objects. Flatten them
    into a simple key→value dict for the rest of the script.
    Fallback to wellness chart data where userstats is empty.
    """
    out = {}

    # userstats returns {"allMetrics": {"metricsMap": {"WELLNESS_TOTAL_STEPS": [...], ...}}}
    metrics_map = {}
    if isinstance(stats_raw, dict):
        metrics_map = (stats_raw.get("allMetrics", {}) or {}).get("metricsMap", {}) or {}

    def _metric(key):
        entries = metrics_map.get(key, [])
        if isinstance(entries, list) and entries:
            return entries[0].get("value")
        return None

    out["totalSteps"]               = _metric("WELLNESS_TOTAL_STEPS")
    out["totalKilocalories"]        = _metric("WELLNESS_TOTAL_CALORIES")
    out["activeKilocalories"]       = _metric("WELLNESS_ACTIVE_CALORIES")
    out["moderateIntensityMinutes"] = _metric("WELLNESS_MODERATE_INTENSITY_MINUTES")
    out["vigorousIntensityMinutes"] = _metric("WELLNESS_VIGOROUS_INTENSITY_MINUTES")
    out["averageStressLevel"]       = _metric("WELLNESS_AVERAGE_STRESS")
    out["restingHeartRate"]         = _metric("WELLNESS_RESTING_HEART_RATE")

    # Fallback resting HR from dailyHeartRate endpoint
    if out["restingHeartRate"] is None and isinstance(hr_raw, dict):
        out["restingHeartRate"] = hr_raw.get("restingHeartRate")

    # Fallback steps/calories from wellness chart if userstats empty
    if out["totalSteps"] is None and isinstance(wellness_raw, list) and wellness_raw:
        total_steps = sum(
            (e.get("steps") or 0) for e in wellness_raw if isinstance(e, dict)
        )
        if total_steps:
            out["totalSteps"] = total_steps

    return out


def extract_hrv(hrv_raw: dict) -> dict:
    if not hrv_raw:
        return {}
    summary = hrv_raw.get("hrvSummary") or hrv_raw
    return {
        "status":    summary.get("status") or summary.get("weeklyAvgStr"),
        "lastNight": summary.get("lastNight") or summary.get("lastNightAvg"),
        "weeklyAvg": summary.get("weeklyAvg") or summary.get("weekly5DayAvg"),
    }


def extract_sleep(sleep_raw: dict) -> dict:
    if not sleep_raw:
        return {}
    dto = sleep_raw.get("dailySleepDTO") or sleep_raw
    scores = dto.get("sleepScores") or {}
    overall = scores.get("overall") or {}
    return {
        "score":       overall.get("value"),
        "sleepSecs":   dto.get("sleepTimeSeconds") or dto.get("sleepTimeTotalSeconds"),
        "deepSecs":    dto.get("deepSleepSeconds"),
        "remSecs":     dto.get("remSleepSeconds"),
        "lightSecs":   dto.get("lightSleepSeconds"),
        "awakeSecs":   dto.get("awakeSleepSeconds"),
        "sleepHR":     dto.get("sleepHeartRate") or dto.get("avgSleepHeartRate"),
    }


def extract_spo2(spo2_raw) -> str:
    if not spo2_raw:
        return "n/a"
    if isinstance(spo2_raw, dict):
        val = spo2_raw.get("averageSpO2") or spo2_raw.get("averageSpo2")
        if val:
            return f"{val} %"
    if isinstance(spo2_raw, list) and spo2_raw:
        vals = [e.get("value") or e.get("spo2") for e in spo2_raw if isinstance(e, dict)]
        vals = [v for v in vals if v is not None]
        if vals:
            return f"{sum(vals) / len(vals):.0f} %"
    return "n/a"


def parse_body_battery(data) -> tuple:
    if not data:
        return "n/a", "n/a"
    values = []
    try:
        for entry in data:
            charged = None
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                charged = entry[1]
            elif isinstance(entry, dict):
                charged = (entry.get("charged")
                           or entry.get("value")
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


# ── Markdown builder ───────────────────────────────────────────────────────────

def build_markdown(stats: dict, hrv: dict, sleep: dict,
                   spo2_str: str, body_battery_raw, activity: dict) -> str:
    now   = datetime.now()
    today = date.today().strftime("%A, %d %B %Y")
    updated = now.strftime("%Y-%m-%d %H:%M")

    resting_hr  = _safe(stats.get("restingHeartRate"), " bpm")
    steps       = _fmt_int(stats.get("totalSteps"))
    calories    = _fmt_int(stats.get("totalKilocalories"))
    active_cals = _fmt_int(stats.get("activeKilocalories"))
    avg_stress  = _safe(stats.get("averageStressLevel"))
    avg_stress  = f"{avg_stress}/100" if avg_stress != "n/a" else "n/a"
    active_mins = "n/a"
    try:
        m = int(stats.get("moderateIntensityMinutes") or 0)
        v = int(stats.get("vigorousIntensityMinutes") or 0)
        if m or v:
            active_mins = f"{m + v} min ({m} mod + {v} vig)"
    except (TypeError, ValueError):
        pass

    hrv_status = _safe(hrv.get("status"))
    hrv_last   = _safe(hrv.get("lastNight"), " ms")
    hrv_weekly = _safe(hrv.get("weeklyAvg"), " ms")

    sleep_score = _safe(sleep.get("score"), "/100")
    sleep_dur   = _fmt_dur(sleep.get("sleepSecs"))
    deep_dur    = _fmt_dur(sleep.get("deepSecs"))
    rem_dur     = _fmt_dur(sleep.get("remSecs"))
    light_dur   = _fmt_dur(sleep.get("lightSecs"))
    awake_dur   = _fmt_dur(sleep.get("awakeSecs"))
    sleep_hr    = _safe(sleep.get("sleepHR"), " bpm")

    bb_high, bb_low = parse_body_battery(body_battery_raw)

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
        f"- **SpO2 (overnight avg)**: {spo2_str}",
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


# ── Rolling archive ────────────────────────────────────────────────────────────

def build_archive_entry(stats: dict, hrv: dict, sleep: dict,
                        spo2_str: str, body_battery_raw, activity: dict) -> str:
    resting_hr = _safe(stats.get("restingHeartRate"), " bpm")
    steps      = _fmt_int(stats.get("totalSteps"))
    avg_stress = _safe(stats.get("averageStressLevel"), "/100")

    hrv_val    = _safe(hrv.get("lastNight"), " ms")
    hrv_status = _safe(hrv.get("status"))
    hrv_str    = f"{hrv_val} ({hrv_status})" if hrv_val != "n/a" else "n/a"

    sleep_score = _safe(sleep.get("score"), "/100")
    sleep_dur   = _fmt_dur(sleep.get("sleepSecs"))
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


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true",
                        help="Interactive cookie setup — paste SESSIONID from browser devtools")
    parser.add_argument("--setup-garth", action="store_true",
                        help="First-time garth/credential auth (handles MFA interactively). "
                             "Run once from a terminal — tokens are cached for future cron runs.")
    args = parser.parse_args()

    if args.setup:
        setup_cookies()
        return

    if args.setup_garth:
        setup_garth()
        return

    _load_dotenv()  # loads GARMIN_EMAIL, GARMIN_PASSWORD, GARMIN_DISPLAY_NAME, etc.
    log("Garmin poller starting")
    today = date.today().strftime("%Y-%m-%d")

    # ── Auth strategy: credentials (garth) preferred, cookies as fallback ────────
    garth_api = None
    use_garth = False

    garmin_email    = os.environ.get("GARMIN_EMAIL", "").strip()
    garmin_password = os.environ.get("GARMIN_PASSWORD", "").strip()

    if garmin_email and garmin_password:
        try:
            garth_api = _garth_auth(interactive=False)
            use_garth = True
            log("Auth: using garth (email/password from .env) — self-healing, no manual cookie setup needed")
        except RuntimeError as e:
            log(f"WARNING: Garth auth failed ({e})")
            if "setup-garth" in str(e) or "no TTY" in str(e) or "MFA" in str(e):
                log("FLAG TO TOM: Run the one-time Garmin garth setup from a terminal:")
                log("  python3 ~/.openclaw/integrations/garmin/poll-garmin-cookie.py --setup-garth")
                log("  This handles MFA if needed and caches tokens for all future cron runs.")
                sys.exit(1)
            log("Falling back to cookie mode...")

    if not use_garth:
        log("Auth: using cookie mode (GARMIN_EMAIL/GARMIN_PASSWORD not in .env or garth auth failed)")
        cookies = load_cookies()
        try:
            display_name = get_display_name(cookies)
            log(f"Garmin: cookie session active — display name: {display_name}")
        except RuntimeError as e:
            err = str(e)
            if "COOKIES_EXPIRED" in err:
                log("ERROR: Garmin cookies have expired.")
                log("FLAG TO TOM: Add GARMIN_EMAIL + GARMIN_PASSWORD to ~/.openclaw/.env for self-healing auth,")
                log("  OR log into connect.garmin.com and run: python3 ~/.openclaw/integrations/garmin/poll-garmin-cookie.py --setup")
                sys.exit(1)
            log(f"ERROR: Could not verify Garmin session: {err}")
            log("FLAG TO TOM: Garmin session check failed. Add GARMIN_EMAIL + GARMIN_PASSWORD to .env, or run --setup.")
            sys.exit(1)

    # ── Fetch all data ────────────────────────────────────────────────────────────
    if use_garth:
        (stats_raw, wellness_raw, hr_raw,
         hrv_raw, sleep_raw, spo2_raw,
         body_bat, activity) = _fetch_all_garth(garth_api, today)
    else:
        log(f"Fetching data for {today}")
        stats_raw    = fetch_stats(cookies, display_name, today)
        wellness_raw = fetch_wellness(cookies, display_name, today)
        hr_raw       = fetch_resting_hr(cookies, display_name, today)
        hrv_raw      = fetch_hrv(cookies, today)
        sleep_raw    = fetch_sleep(cookies, display_name, today)
        spo2_raw     = fetch_spo2(cookies, display_name, today)
        body_bat     = fetch_body_battery(cookies, today)
        activity     = fetch_last_activity(cookies)

    stats = extract_stats(stats_raw, wellness_raw, hr_raw)
    hrv   = extract_hrv(hrv_raw)
    sleep = extract_sleep(sleep_raw)
    spo2  = extract_spo2(spo2_raw)

    md = build_markdown(stats, hrv, sleep, spo2, body_bat, activity)

    try:
        write_atomic(OUTPUT_MD, md)
        log(f"Written: {OUTPUT_MD}")
    except Exception as e:
        log(f"ERROR: Failed to write {OUTPUT_MD}: {e}")
        log("FLAG TO TOM: poll-garmin-cookie.py could not write GARMIN_DAILY.md.")
        sys.exit(1)

    try:
        archive_entry = build_archive_entry(stats, hrv, sleep, spo2, body_bat, activity)
        update_archive(archive_entry, today)
    except Exception as e:
        log(f"WARNING: Archive update failed: {e} — daily file is unaffected")

    log("Garmin cookie-poller complete")


if __name__ == "__main__":
    main()
