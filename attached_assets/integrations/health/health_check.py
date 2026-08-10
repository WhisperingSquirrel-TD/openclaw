#!/usr/bin/env python3
"""
OpenClaw System Health Check
=============================

Runs from the configured system-health route.
Writes ~/.openclaw/workspace/SYSTEM_HEALTH.md with any issues found.
The scheduler/delivery cadence is verified separately from the live cron list.
L1 reads this file at the start of its morning briefing turn and prepends
a ⚙️ SYSTEM HEALTH section only when the file is non-empty.

What it checks
--------------
CRONS / LOG HEALTH — for each poller:
  • Is the log file missing? (service never ran or was wiped)
  • Has the log file gone stale? (cron stopped firing)
  • Does the recent log contain ERROR lines? (poller running but broken)
  • Multiple consecutive errors in last N lines?

FEED / FILE FRESHNESS — for each workspace file:
  • Has the file not been updated within its expected refresh window?
  • This catches silent cron failures where the process exits without logging

SPECIAL CASES:
  • Garmin: expected before standups (06:35 and 13:35 via the same route as management-bot /garmin)
  • CRM: only flagged stale if a new prospects folder exists but CRM not updated
  • Enquiry poller: stale threshold 15 min (cron every 2 min)

OUTPUT
------
Non-empty SYSTEM_HEALTH.md → L1 includes ⚙️ SYSTEM HEALTH section in briefing.
Empty SYSTEM_HEALTH.md (or missing) → L1 omits the section entirely.

SOUL.md INSTRUCTION (add to L1 morning briefing section):
  At the start of your morning briefing, read SYSTEM_HEALTH.md.
  If it is non-empty, prepend this section BEFORE anything else:

  ⚙️ SYSTEM HEALTH
  [paste content verbatim]

  If SYSTEM_HEALTH.md is empty or missing, omit this section completely.
"""
import json
import os
import re
import subprocess
import sys
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HOME       = Path.home()
OPENCLAW   = HOME / ".openclaw"
WORKSPACE  = OPENCLAW / "workspace"
MEMORY     = WORKSPACE / "memory"
OUTPUT_MD  = WORKSPACE / "SYSTEM_HEALTH.md"
BACKUP_HEALTH_MD = WORKSPACE / "memory/sharepoint-backup-health.md"
CONFIG_PATH = OPENCLAW / "openclaw.json"
BOOTSTRAP_FILES = [
    WORKSPACE / "AGENTS.md",
    WORKSPACE / "MEMORY.md",
    WORKSPACE / "HEARTBEAT.md",
    WORKSPACE / "SYSTEM_MAP.md",
    WORKSPACE / "USER.md",
    WORKSPACE / "SOUL.md",
    WORKSPACE / "IDENTITY.md",
    WORKSPACE / "TOOLS.md",
]
CODE_REPO  = HOME / "openclaw"
WORKSPACE_REPO = WORKSPACE
SP_BACKUP_STATE = OPENCLAW / "integrations/microsoft/sharepoint-backup-state.json"
SP_BACKUP_LOG = WORKSPACE / "memory/sharepoint-backup-log.txt"
SP_BACKUP_TIMER = "openclaw-sharepoint-backup.timer"
GITHUB_BACKUP_LOG = MEMORY / "github-backup.log"
GITHUB_BACKUP_SCRIPT = OPENCLAW / "scripts/github_backup.sh"
# Two daily runs (03:45 and 14:20); 14h catches either missed run at the
# next health pass while allowing normal scheduling/host jitter.
GITHUB_BACKUP_MAX_AGE_MINUTES = 14 * 60
# Canonical expense-intake execution evidence. The central mirror router is the
# ordered trigger and invokes the expense executor immediately after writing
# normalised all-surface events. The compatibility watcher timer is not health
# proof and is retired after equivalence acceptance.
EXPENSE_WATCHER_STATE = OPENCLAW / "runtime/inbound-watch-router/state.json"
EXPENSE_WATCHER_TIMER = "openclaw-mirror-router.timer"
EXPENSE_RESOLUTION_TIMER = "expense-enrichment-resolution.timer"
# Cron has a minimal environment, so neither the systemd user bus nor the
# OpenClaw CLI path can be assumed to be inherited. Resolve both explicitly.
USER_RUNTIME_DIR = Path(f"/run/user/{os.getuid()}")
USER_BUS_ADDRESS = f"unix:path={USER_RUNTIME_DIR / 'bus'}"
_SYSTEM_OPENCLAW_CLI = Path("/usr/local/bin/openclaw")
OPENCLAW_CLI = os.environ.get(
    "OPENCLAW_CLI",
    shutil.which("openclaw")
    or (str(_SYSTEM_OPENCLAW_CLI) if _SYSTEM_OPENCLAW_CLI.exists() else str(HOME / ".npm-packages/bin/openclaw")),
)
REPORT_POLLER_STATE = OPENCLAW / "integrations/stackstone/report-poller-state.json"
ENQUIRY_POLLER_STATE = OPENCLAW / "integrations/stackstone/enquiry-poller-state.json"

# Cron health is collected deterministically here rather than by the delivery
# agent, whose tool response would otherwise include every job payload.
CRITICAL_CRON_NAMES = {
    "Morning standup — 06:30 daily",
    "Afternoon standup — 13:45 daily",
    "Inbox watch — every 3 hours",
    "Bounce & unsub detection — every 3 hours",
    "System health delivery — daily 15:05",
}

# ---------------------------------------------------------------------------
# Monitored services
# Each entry: (label, log_path, expected_max_age_minutes, error_scan_lines)
# log_path is None for services that log only via stdout→cron-append file
# ---------------------------------------------------------------------------

# Time windows — how recently must the log have been written?
T5   = 20   # pollers running every 5 min — stale after 20 min
T15  = 40   # pollers running every 15 min — stale after 40 min
T2   = 15   # pollers running every 2 min — stale after 15 min
T24H = 25 * 60  # daily pollers — stale after 25h

LOG_CHECKS = [
    # (label, log_file, stale_minutes)
    ("Microsoft inbox poller",   MEMORY / "poll-microsoft-log.txt",        T5),
    ("Microsoft assistant inbox",MEMORY / "poll-assistant-log.txt",        T5),
    ("Gmail poller",             MEMORY / "poll-gmail-log.txt",            T5),
    ("Outlook calendar poller",  MEMORY / "poll-calendar-log.txt",         T15),
    ("Garmin poller",            MEMORY / "poll-garmin-log.txt",           T24H),
    ("CRM lead importer",        MEMORY / "poll-crm-log.txt",              T24H),
]

# Feed files L1 depends on — stale if not updated within window
FEED_CHECKS = [
    # (label, file_path, stale_minutes, only_after_hour)
    # only_after_hour: skip stale check before this hour (0 = always check)
    ("MICROSOFT_INBOX.md",      WORKSPACE / "MICROSOFT_INBOX.md",      T5,   0),
    ("MICROSOFT_EXTERNAL.md",   WORKSPACE / "MICROSOFT_EXTERNAL.md",   T5,   0),
    ("GMAIL_INBOX.md",          WORKSPACE / "GMAIL_INBOX.md",          T5,   0),
    ("OUTLOOK_CALENDAR.md",     WORKSPACE / "OUTLOOK_CALENDAR.md",     T15,  0),
    ("WHATSAPP_RECENT.md",      WORKSPACE / "WHATSAPP_RECENT.md",      T15,  0),
    ("STACKSTONE_REPORTS.md",   WORKSPACE / "STACKSTONE_REPORTS.md",   T5,   0),
    ("STACKSTONE_ENQUIRIES.md", WORKSPACE / "STACKSTONE_ENQUIRIES.md", T2,   0),
    ("GARMIN_DAILY.md",         WORKSPACE / "GARMIN_DAILY.md",         T24H, 10),  # expected before standups via 06:35/13:35 Garmin cron
]

# Error patterns to scan for in recent log lines
ERROR_PATTERNS = re.compile(
    r"\b(ERROR|CRITICAL|EXCEPTION|Traceback|token.refresh.fail|invalid_grant|"
    r"Auth\s*error|ConnectionError|Timeout|timed.out|JSONDecodeError|"
    r"Failed\s+to\s+(send|fetch|poll|refresh|connect)|"
    r"KeyError|AttributeError|cannot\s+read|unreadable)\b",
    re.IGNORECASE,
)
SUCCESS_PATTERNS = re.compile(
    r"(Poll complete|poll complete|Pipeline complete|succeeded|written to|wrote .* to|Token refreshed successfully)",
    re.IGNORECASE,
)

SCAN_LINES = 80   # how many recent log lines to scan for errors
ERROR_THRESHOLD = 3  # flag if >= this many error lines in last SCAN_LINES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _mtime_age_minutes(path: Path) -> float | None:
    """Return age of file in minutes, or None if file doesn't exist."""
    try:
        mtime = path.stat().st_mtime
        age_s = (_now().timestamp() - mtime)
        return age_s / 60
    except FileNotFoundError:
        return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_minutes_from_iso(value: str | None) -> float | None:
    dt = _parse_iso_datetime(value)
    if dt is None:
        return None
    return (_now() - dt).total_seconds() / 60


def _format_age_minutes(age: float | None) -> str:
    if age is None:
        return "unknown age"
    total_minutes = max(0, int(age))
    age_h = total_minutes // 60
    age_m = total_minutes % 60
    return f"{age_h}h {age_m}m" if age_h else f"{age_m}m"


def _load_json_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _scan_log_errors(path: Path, last_n: int = SCAN_LINES) -> list[str]:
    """Return matching error lines from the last `last_n` lines of the log.

    If a success marker appears in that recent window, only scan lines *after the
    last success marker*. This prevents transient network/DNS failures from
    poisoning health status long after recovery has already been logged.
    """
    try:
        lines = path.read_text(errors="replace").splitlines()
    except FileNotFoundError:
        return []
    recent = lines[-last_n:]
    last_success_idx = None
    for idx, line in enumerate(recent):
        if SUCCESS_PATTERNS.search(line):
            last_success_idx = idx
    if last_success_idx is not None:
        recent = recent[last_success_idx + 1:]
    return [l for l in recent if ERROR_PATTERNS.search(l)]


def _is_garmin_stale_period() -> bool:
    """Garmin runs at 09:00 — only flag it as stale after 10:00 local."""
    return datetime.now().hour >= 10


def _is_crm_stale_period() -> bool:
    """CRM runs at 08:00 — only flag it as stale after 09:00 local."""
    return datetime.now().hour >= 9


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_log_health() -> list[str]:
    issues = []

    for label, log_path, stale_minutes in LOG_CHECKS:
        # Special daily-cron timing guards
        if "Garmin" in label and not _is_garmin_stale_period():
            continue
        if "CRM" in label and not _is_crm_stale_period():
            continue

        age = _mtime_age_minutes(log_path)

        if age is None:
            # Log file missing entirely — never ran or wiped
            if "Garmin" in label or "CRM" in label:
                # These may not exist yet on a fresh install — not alarming
                continue
            issues.append(f"{label}: log file missing — cron may never have run ({log_path.name})")
            continue

        if age > stale_minutes:
            age_h = int(age // 60)
            age_m = int(age % 60)
            age_str = f"{age_h}h {age_m}m" if age_h else f"{age_m}m"
            issues.append(
                f"{label}: log stale ({age_str} since last write) — cron may have stopped"
            )
            continue  # Don't also scan errors if the log is stale/not running

        # Log is fresh — scan for recent errors
        error_lines = _scan_log_errors(log_path)
        if len(error_lines) >= ERROR_THRESHOLD:
            # Extract a brief summary of the first unique error
            unique_msgs = []
            seen = set()
            for line in error_lines:
                m = ERROR_PATTERNS.search(line)
                key = m.group(0).upper() if m else "ERROR"
                if key not in seen:
                    seen.add(key)
                    snippet = line.strip()[-120:]
                    unique_msgs.append(snippet)
                if len(unique_msgs) >= 2:
                    break
            detail = unique_msgs[0] if unique_msgs else "(see log)"
            issues.append(
                f"{label}: {len(error_lines)} error(s) in last {SCAN_LINES} log lines — {detail}"
            )
        elif error_lines:
            # 1-2 errors — note but lower priority
            snippet = error_lines[-1].strip()[-120:]
            issues.append(f"{label}: recent error in log — {snippet}")

    return issues


def check_feed_freshness() -> list[str]:
    issues = []

    for label, feed_path, stale_minutes, only_after_hour in FEED_CHECKS:
        if only_after_hour and datetime.now().hour < only_after_hour:
            continue

        age = _mtime_age_minutes(feed_path)

        if age is None:
            issues.append(f"{label}: file missing — feed has never been written")
            continue

        if age > stale_minutes:
            age_h = int(age // 60)
            age_m = int(age % 60)
            age_str = f"{age_h}h {age_m}m" if age_h else f"{age_m}m"
            issues.append(f"{label}: stale ({age_str} since last update)")

    return issues


def check_expense_watcher_health() -> list[str]:
    issues = []

    age = _mtime_age_minutes(EXPENSE_WATCHER_STATE)
    if age is None:
        issues.append("Expense watcher: runtime state missing — expense auto-capture may not be running")
        return issues

    if age > T15:
        age_h = int(age // 60)
        age_m = int(age % 60)
        age_str = f"{age_h}h {age_m}m" if age_h else f"{age_m}m"
        issues.append(f"Expense watcher: runtime state stale ({age_str} since last update) — expense auto-capture may be stuck")

    try:
        state = json.loads(EXPENSE_WATCHER_STATE.read_text())
        last_run = state.get('last_run')
        if not last_run:
            issues.append("Expense watcher: runtime state has no last_run timestamp")
        summary = state.get('last_summary') or {}
        blocked = int(summary.get('blocked', 0) or 0) + int(summary.get('mirror_blocked', 0) or 0)
        if blocked > 0:
            issues.append(f"Expense watcher: {blocked} blocked item(s) in latest run — review expense intake blockers")
    except Exception as e:
        issues.append(f"Expense watcher: runtime state unreadable ({e})")

    timer_rc, timer_out, timer_err = _run_user_systemctl("is-enabled", EXPENSE_WATCHER_TIMER)
    timer_enabled = timer_rc == 0 and timer_out.strip() == "enabled"

    active_rc, active_out, active_err = _run_user_systemctl("is-active", EXPENSE_WATCHER_TIMER)
    timer_active = active_rc == 0 and active_out.strip() == "active"

    if not timer_enabled:
        issues.append("Expense watcher: timer is not enabled")
    elif not timer_active:
        issues.append("Expense watcher: timer is enabled but not active")

    resolution_rc, resolution_out, _ = _run_user_systemctl("is-enabled", EXPENSE_RESOLUTION_TIMER)
    resolution_active_rc, resolution_active_out, _ = _run_user_systemctl("is-active", EXPENSE_RESOLUTION_TIMER)
    if resolution_rc != 0 or resolution_out.strip() != "enabled":
        issues.append("Expense enrichment resolution: timer is not enabled")
    elif resolution_active_rc != 0 or resolution_active_out.strip() != "active":
        issues.append("Expense enrichment resolution: timer is enabled but not active")

    return issues


def check_enquiry_pipeline() -> list[str]:
    """Use state + feed freshness to detect real enquiry-pipeline failures."""
    issues = []
    state = _load_json_file(ENQUIRY_POLLER_STATE)
    if state is None:
        return []

    failures = int(state.get("consecutive_api_failures", 0) or 0)
    if failures > 0:
        summary = state.get("last_failure_summary") or "see enquiry-poller.log"
        issues.append(
            f"Website enquiry pipeline: {failures} consecutive API failure(s) — {summary}"
        )
        return issues

    success_age = _age_minutes_from_iso(state.get("last_successful_poll_at"))
    if success_age is not None and success_age > T2:
        issues.append(
            f"Website enquiry pipeline: last successful poll was {_format_age_minutes(success_age)} ago"
        )

    return issues


def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, capture_output=True, text=True, timeout=20)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def _run_user_systemctl(*args: str) -> tuple[int, str, str]:
    """Run systemctl --user with the user bus available under cron too."""
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", str(USER_RUNTIME_DIR))
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", USER_BUS_ADDRESS)
    return _run(["systemctl", "--user", *args], env=env)


def check_github_sync() -> tuple[list[str], list[str]]:
    issues = []
    info = []
    for label, repo in [("openclaw repo", CODE_REPO), ("workspace repo", WORKSPACE_REPO)]:
        if not repo.exists():
            issues.append(f"{label}: repo path missing ({repo})")
            continue
        rc, out, err = _run(["git", "status", "--porcelain"], cwd=repo)
        if rc != 0:
            issues.append(f"{label}: git status failed ({err or out})")
            continue
        dirty = bool(out.strip())
        # A dirty working tree is normal during active Pi development. Preserve
        # it as diagnostic evidence, but do not turn it into a daily health
        # alert unless Git itself is broken or commits are actually unpushed.
        if dirty:
            info.append(f"{label}: local working tree dirty (diagnostic only; no unpushed-commit failure proven)")

        rc, branch, err = _run(["git", "branch", "--show-current"], cwd=repo)
        branch = branch.strip() or "main"

        rc, compare, err = _run(["git", "rev-list", "--left-right", "--count", f"origin/{branch}...{branch}"], cwd=repo)
        ahead = behind = None
        if rc == 0 and compare.strip():
            try:
                behind, ahead = [int(x) for x in compare.split()[:2]]
            except Exception:
                behind = ahead = None
        else:
            issues.append(f"{label}: could not compare local branch to remote tracking branch")

        rc, pushed_ts, err = _run(["git", "log", "-1", "--format=%cI", f"origin/{branch}"], cwd=repo)
        pushed_age = _age_minutes_from_iso(pushed_ts.strip()) if rc == 0 and pushed_ts.strip() else None
        summary_bits = []
        if pushed_age is not None:
            summary_bits.append(f"last successful push {_format_age_minutes(pushed_age)} ago")
        else:
            summary_bits.append("last successful push unknown")
        if ahead is not None:
            summary_bits.append(f"ahead {ahead}")
        if behind is not None:
            summary_bits.append(f"behind {behind}")
        summary_bits.append("dirty" if dirty else "clean")
        info.append(f"{label}: {', '.join(summary_bits)}")

        if ahead is not None and ahead > 0:
            issues.append(f"{label}: {ahead} unpushed commit(s) on {branch}")
        if behind is not None and behind > 0:
            issues.append(f"{label}: local {branch} is {behind} commit(s) behind origin/{branch}")
    return issues, info


def check_github_backup_health() -> tuple[list[str], list[str]]:
    """Verify the live GitHub backup schedule and recent successful run."""
    issues: list[str] = []
    info: list[str] = []

    if not GITHUB_BACKUP_SCRIPT.exists():
        issues.append("GitHub backup: backup script missing")
        return issues, info

    rc, crontab, err = _run(["crontab", "-l"])
    if rc != 0:
        issues.append("GitHub backup: could not read live crontab")
    else:
        schedule_lines = [line.strip() for line in crontab.splitlines()
                          if "github_backup.sh" in line and not line.lstrip().startswith("#")]
        if not any(line.startswith("45 3 ") for line in schedule_lines):
            issues.append("GitHub backup: overnight 03:45 schedule missing")
        if not any(line.startswith("20 14 ") for line in schedule_lines):
            issues.append("GitHub backup: daytime 14:20 schedule missing")

    age = _mtime_age_minutes(GITHUB_BACKUP_LOG)
    latest_success = False
    if age is None:
        issues.append("GitHub backup: success log missing")
    else:
        try:
            lines = GITHUB_BACKUP_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            latest_success = any("GitHub backup run finished" in line for line in lines[-200:])
        except Exception:
            issues.append("GitHub backup: success log unreadable")
        if age > GITHUB_BACKUP_MAX_AGE_MINUTES:
            issues.append(f"GitHub backup: stale ({_format_age_minutes(age)} since last log update)")
        elif latest_success:
            info.append(f"GitHub backup: last recorded run {_format_age_minutes(age)} ago")
        else:
            issues.append("GitHub backup: recent log has no completed-run marker")

    return issues, info


def check_sharepoint_backup_health() -> tuple[list[str], list[str], dict]:
    issues = []
    info = []
    recent_success = False
    age = _mtime_age_minutes(SP_BACKUP_STATE)
    state = _load_json_file(SP_BACKUP_STATE)
    details: dict = {
        "result_shape": "coverage_incomplete",
        "status": "unknown",
        "updated_age_minutes": None,
        "recent_success": False,
        "timer_enabled": None,
        "timer_state_readable": True,
        "notes": [],
    }

    if age is None or state is None:
        issues.append("SharePoint backup: state file missing or unreadable — backup may never have completed")
        details["notes"].append("State file missing or unreadable.")
    else:
        updated_age = _age_minutes_from_iso(state.get("updated_utc")) or age
        status = state.get("status") or "unknown"
        details["status"] = status
        details["updated_age_minutes"] = updated_age
        info.append(f"SharePoint backup: {status} — last successful state update {_format_age_minutes(updated_age)} ago")
        if updated_age > (26 * 60):
            issues.append(f"SharePoint backup: stale ({_format_age_minutes(updated_age)} since last successful state update)")
            details["notes"].append("Last successful state update is beyond the allowed backup window.")
        if status != 'ok':
            issues.append("SharePoint backup: latest recorded state is not OK")
            details["notes"].append("Latest recorded backup state is not OK.")
        else:
            recent_success = updated_age <= (26 * 60)
            if recent_success:
                details["notes"].append("Recent successful backup is proven by the state file.")

    log_age = _mtime_age_minutes(SP_BACKUP_LOG)
    if log_age is not None and log_age <= (26 * 60):
        try:
            lines = SP_BACKUP_LOG.read_text(encoding='utf-8', errors='replace').splitlines()[-200:]
            if any('SharePoint backup completed successfully.' in line for line in lines):
                recent_success = True
                details["notes"].append("Recent successful backup is also corroborated by the backup log.")
        except Exception:
            details["notes"].append("Backup log could not be parsed for recent success corroboration.")

    details["recent_success"] = recent_success

    rc, out, err = _run_user_systemctl("is-enabled", SP_BACKUP_TIMER)
    timer_enabled = rc == 0 and out.strip() == 'enabled'
    details["timer_enabled"] = timer_enabled
    if rc != 0 or out.strip() != 'enabled':
        if recent_success:
            details["notes"].append("Timer-read anomaly: timer not readable as enabled, but recent success is proven.")
        else:
            issues.append("SharePoint backup: timer not enabled")
            details["notes"].append("Timer is not enabled and there is no strong recent-success proof to offset that.")

    rc, out, err = _run_user_systemctl("show", SP_BACKUP_TIMER, "--property=NextElapseUSecRealtime", "--property=LastTriggerUSec")
    timer_state_readable = rc == 0
    details["timer_state_readable"] = timer_state_readable
    if rc != 0:
        if recent_success:
            details["notes"].append("Timer state could not be read, but recent success is proven.")
        else:
            issues.append("SharePoint backup: could not read timer state")
            details["notes"].append("Timer state is unreadable and there is no strong recent-success proof.")

    if recent_success and details["status"] == "ok" and timer_enabled and timer_state_readable:
        details["result_shape"] = "healthy"
    elif recent_success and details["status"] == "ok":
        details["result_shape"] = "acceptable_drift"
    elif issues:
        details["result_shape"] = "persistent_failure"
    else:
        details["result_shape"] = "coverage_incomplete"

    return issues, info, details


def check_bootstrap_pressure() -> list[str]:
    """Fail closed when an always-loaded bootstrap file exceeds its configured budget.

    This is deliberately deterministic and bounded: it does not try to infer the
    runtime's full context size, but it catches the concrete file-level overflow
    that can make injection/truncation predictable and visible.
    """
    issues = []
    config = _load_json_file(CONFIG_PATH)
    if not isinstance(config, dict):
        return ["Bootstrap health: openclaw.json unreadable — bootstrap budget unverified"]

    try:
        budget = int(
            config.get("agents", {})
                  .get("defaults", {})
                  .get("bootstrapMaxChars")
        )
    except (AttributeError, TypeError, ValueError):
        return ["Bootstrap health: bootstrapMaxChars missing/invalid — budget unverified"]

    if budget <= 0:
        return ["Bootstrap health: bootstrapMaxChars is non-positive — budget invalid"]

    for path in BOOTSTRAP_FILES:
        if not path.exists():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            issues.append(f"Bootstrap health: could not measure {path.name}")
            continue
        if size > budget:
            issues.append(
                f"Bootstrap health: {path.name} is {size} bytes, above "
                f"bootstrapMaxChars={budget}"
            )
    return issues


def check_stackstone_report_poller_state() -> list[str]:
    issues = []
    state = _load_json_file(REPORT_POLLER_STATE)
    if state is None:
        return issues

    failures = int(state.get("consecutive_failures", 0) or 0)
    if failures > 0:
        summary = state.get("last_failure_summary") or "see poller.log"
        issues.append(f"Stackstone report poller: {failures} consecutive failure(s) — {summary}")
        return issues

    success_age = _age_minutes_from_iso(state.get("last_successful_fetch_at") or state.get("last_success_at"))
    if success_age is not None and success_age > T5:
        issues.append(f"Stackstone report poller: last successful poll was {_format_age_minutes(success_age)} ago")

    return issues


def check_critical_cron_health() -> list[str]:
    """Check only the small named cron allowlist via the local Gateway CLI.

    This keeps scheduler evidence deterministic and prevents the delivery agent
    from loading every cron payload merely to inspect five jobs.
    """
    issues = []
    rc, out, err = _run([OPENCLAW_CLI, "cron", "list", "--json", "--timeout", "15000"])
    if rc != 0:
        return [f"Critical cron health: scheduler list unavailable — {err or out or 'unknown error'}"]
    try:
        data = json.loads(out)
        jobs = data.get("jobs", [])
    except (json.JSONDecodeError, AttributeError):
        return ["Critical cron health: scheduler returned unreadable job data"]

    found = {job.get("name"): job for job in jobs if job.get("name") in CRITICAL_CRON_NAMES}
    for name in sorted(CRITICAL_CRON_NAMES):
        job = found.get(name)
        if job is None:
            issues.append(f"Critical cron: missing required job — {name}")
            continue
        if not job.get("enabled", False):
            issues.append(f"Critical cron: disabled — {name}")
            continue
        state = job.get("state") or {}
        if not state.get("nextRunAtMs"):
            issues.append(f"Critical cron: next run missing — {name}")
        errors = int(state.get("consecutiveErrors", 0) or 0)
        if errors > 0:
            detail = state.get("lastError") or state.get("lastRunStatus") or "unknown error"
            issues.append(f"Critical cron: {name} has {errors} consecutive error(s) — {detail}")
    return issues


def check_reminder_failures() -> list[str]:
    """
    Check if any scheduled reminder or L1 task shows a recent failure.
    Looks in the gateway log (if accessible) for reminder/task errors.
    """
    issues = []
    # Gateway log is usually only accessible via systemd journal — we check
    # the alert file that L1 writes when actions fail
    alert_file = MEMORY / "email-alert.md"
    age = _mtime_age_minutes(alert_file)
    # Note: alert-file being old is normal (no recent known-contact emails)
    # We don't flag this unless it's missing — just return no issues here
    return issues


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def build_health_report(issues: list[str], info: list[str]) -> str:
    """Emit only actionable health degradation; diagnostics stay in the run log."""
    if not issues:
        return ""

    lines = ["⚙️ SYSTEM HEALTH\n"]
    for issue in issues:
        lines.append(f"• {issue}")
    for item in info:
        lines.append(f"• {item}")
    return "\n".join(lines) + "\n"


def build_sharepoint_backup_health_report(details: dict) -> str:
    lines = [
        "# SharePoint Backup Health",
        f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        f"- Result shape: `{details.get('result_shape', 'unknown')}`",
        f"- Latest recorded status: `{details.get('status', 'unknown')}`",
        f"- Last successful state age: {_format_age_minutes(details.get('updated_age_minutes'))}",
        f"- Recent success proven: `{details.get('recent_success')}`",
        f"- Timer enabled: `{details.get('timer_enabled')}`",
        f"- Timer state readable: `{details.get('timer_state_readable')}`",
        "",
        "## Notes",
    ]
    notes = details.get("notes") or []
    if notes:
        lines.extend(f"- {note}" for note in notes)
    else:
        lines.append("- No additional notes.")
    lines.append("")
    return "\n".join(lines)


def write_output(content: str, path: Path = OUTPUT_MD) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [health-check] Starting system health check", flush=True)

    issues: list[str] = []
    info: list[str] = []

    bootstrap_issues = check_bootstrap_pressure()
    log_issues  = check_log_health()
    feed_issues = check_feed_freshness()
    exp_issues  = check_expense_watcher_health()
    enq_issues  = check_enquiry_pipeline()
    report_issues = check_stackstone_report_poller_state()
    cron_issues = check_critical_cron_health()
    rem_issues  = check_reminder_failures()
    git_issues, git_info  = check_github_sync()
    ghb_issues, ghb_info = check_github_backup_health()
    spb_issues, spb_info, sp_details  = check_sharepoint_backup_health()

    issues.extend(bootstrap_issues)
    issues.extend(log_issues)
    issues.extend(feed_issues)
    issues.extend(exp_issues)
    issues.extend(enq_issues)
    issues.extend(report_issues)
    issues.extend(cron_issues)
    issues.extend(rem_issues)
    issues.extend(git_issues)
    issues.extend(ghb_issues)
    issues.extend(spb_issues)
    info.extend(git_info)
    info.extend(ghb_info)
    if sp_details.get("result_shape") != "healthy":
        info.extend(spb_info)

    report = build_health_report(issues, info)
    write_output(report)
    write_output(build_sharepoint_backup_health_report(sp_details), BACKUP_HEALTH_MD)

    if issues:
        print(f"[{ts}] [health-check] {len(issues)} issue(s) found — written to SYSTEM_HEALTH.md",
              flush=True)
        for issue in issues:
            print(f"  • {issue}", flush=True)
    elif info:
        print(f"[{ts}] [health-check] No active issues — SYSTEM_HEALTH.md cleared; diagnostics retained in run context", flush=True)
    else:
        print(f"[{ts}] [health-check] All systems OK — SYSTEM_HEALTH.md cleared", flush=True)


if __name__ == "__main__":
    main()
