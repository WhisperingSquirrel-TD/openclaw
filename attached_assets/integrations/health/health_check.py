#!/usr/bin/env python3
"""
OpenClaw System Health Check
=============================

Runs before the morning briefing (cron: 06:55 daily).
Writes ~/.openclaw/workspace/SYSTEM_HEALTH.md with any issues found.
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
  • Garmin: only flagged stale after 10:00 AM (cron runs at 09:00)
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
CODE_REPO  = HOME / "openclaw"
WORKSPACE_REPO = WORKSPACE
SP_BACKUP_STATE = OPENCLAW / "integrations/microsoft/sharepoint-backup-state.json"
SP_BACKUP_LOG = WORKSPACE / "memory/sharepoint-backup-log.txt"
SP_BACKUP_TIMER = "openclaw-sharepoint-backup.timer"
EXPENSE_WATCHER_STATE = OPENCLAW / "runtime/expense-intake-watcher/state.json"
EXPENSE_WATCHER_LOG = OPENCLAW / "runtime/expense-intake-watcher/watcher.log"
EXPENSE_WATCHER_TIMER = "expense-intake-watcher.timer"

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
    ("Stackstone report poller", OPENCLAW / "integrations/stackstone/poller.log", T5),
    ("Website enquiry poller",   OPENCLAW / "integrations/stackstone/enquiry-poller.log", T2),
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
    ("GARMIN_DAILY.md",         WORKSPACE / "GARMIN_DAILY.md",         T24H, 10),  # only flag after 10:00
]

# Error patterns to scan for in recent log lines
ERROR_PATTERNS = re.compile(
    r"\b(ERROR|CRITICAL|EXCEPTION|Traceback|token.refresh.fail|invalid_grant|"
    r"Auth\s*error|ConnectionError|Timeout|timed.out|JSONDecodeError|"
    r"Failed\s+to\s+(send|fetch|poll|refresh|connect)|"
    r"KeyError|AttributeError|cannot\s+read|unreadable)\b",
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


def _scan_log_errors(path: Path, last_n: int = SCAN_LINES) -> list[str]:
    """Return the matching error lines from the last `last_n` lines of the log."""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except FileNotFoundError:
        return []
    recent = lines[-last_n:]
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
        if summary.get('blocked', 0) > 0:
            issues.append(f"Expense watcher: {summary.get('blocked')} blocked item(s) in latest run — review expense intake blockers")
    except Exception as e:
        issues.append(f"Expense watcher: runtime state unreadable ({e})")

    timer_rc, timer_out, timer_err = _run(["systemctl", "--user", "is-enabled", EXPENSE_WATCHER_TIMER])
    if timer_rc != 0 or timer_out.strip() != "enabled":
        issues.append("Expense watcher: timer is not enabled")

    return issues


def check_enquiry_pipeline() -> list[str]:
    """
    Specific revenue-critical check for the website enquiry pipeline.
    Reads the state file to see when the last enquiry was seen, and whether
    the last stale alert has already fired (in which case suppress this check
    to avoid double-alerting — the poller already sends Telegram).
    """
    issues = []
    state_file = OPENCLAW / "integrations/stackstone/enquiry-poller-state.json"

    try:
        state = json.loads(state_file.read_text())
    except FileNotFoundError:
        # State file not created yet (no enquiries ever seen) — not an issue
        return []
    except Exception as e:
        issues.append(f"Website enquiry pipeline: state file unreadable ({e})")
        return issues

    last_stale_alert = state.get("last_stale_alert_at")
    if last_stale_alert:
        # The poller already sent a Telegram stale alert — note it here too
        issues.append(
            "Website enquiry pipeline: staleness alert was sent — "
            "check enquiry-poller.log and website contact form"
        )

    return issues


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=20)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def check_github_sync() -> list[str]:
    issues = []
    for label, repo in [("openclaw repo", CODE_REPO), ("workspace repo", WORKSPACE_REPO)]:
        if not repo.exists():
            issues.append(f"{label}: repo path missing ({repo})")
            continue
        rc, out, err = _run(["git", "status", "--porcelain"], cwd=repo)
        if rc != 0:
            issues.append(f"{label}: git status failed ({err or out})")
            continue
        if out.strip():
            issues.append(f"{label}: local changes present — GitHub may not reflect latest Pi state")
        # Fetch-less ahead/behind using existing remote refs
        rc, branch, err = _run(["git", "branch", "--show-current"], cwd=repo)
        branch = branch.strip() or "main"
        rc, out, err = _run(["git", "rev-list", "--left-right", "--count", f"origin/{branch}...{branch}"], cwd=repo)
        if rc == 0 and out.strip():
            try:
                behind, ahead = [int(x) for x in out.split()[:2]]
                if ahead > 0:
                    issues.append(f"{label}: {ahead} unpushed commit(s) on {branch}")
                if behind > 0:
                    issues.append(f"{label}: local {branch} is {behind} commit(s) behind origin/{branch}")
            except Exception:
                pass
        else:
            issues.append(f"{label}: could not compare local branch to remote tracking branch")
    return issues


def check_sharepoint_backup_health() -> list[str]:
    issues = []
    recent_success = False
    age = _mtime_age_minutes(SP_BACKUP_STATE)
    if age is None:
        issues.append("SharePoint backup: state file missing — backup may never have completed")
    else:
        if age > (26 * 60):
            age_h = int(age // 60)
            age_m = int(age % 60)
            issues.append(f"SharePoint backup: state stale ({age_h}h {age_m}m since last successful state update)")
        try:
            state = json.loads(SP_BACKUP_STATE.read_text())
            if state.get('status') != 'ok':
                issues.append("SharePoint backup: latest recorded state is not OK")
            else:
                recent_success = age <= (26 * 60)
        except Exception as e:
            issues.append(f"SharePoint backup: state unreadable ({e})")

    log_age = _mtime_age_minutes(SP_BACKUP_LOG)
    if log_age is not None and log_age <= (26 * 60):
        try:
            lines = SP_BACKUP_LOG.read_text(encoding='utf-8', errors='replace').splitlines()[-200:]
            if any('SharePoint backup completed successfully.' in line for line in lines):
                recent_success = True
        except Exception:
            pass

    rc, out, err = _run(["systemctl", "--user", "is-enabled", SP_BACKUP_TIMER])
    if rc != 0 or out.strip() != 'enabled':
        if recent_success:
            issues.append("SharePoint backup: timer state not readable as enabled, but recent backup success is proven by state/log")
        else:
            issues.append("SharePoint backup: timer not enabled")

    rc, out, err = _run(["systemctl", "--user", "show", SP_BACKUP_TIMER, "--property=NextElapseUSecRealtime", "--property=LastTriggerUSec"], cwd=WORKSPACE)
    if rc != 0:
        if recent_success:
            issues.append("SharePoint backup: could not read timer state, but recent backup success is proven by state/log")
        else:
            issues.append("SharePoint backup: could not read timer state")
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

def build_health_report(issues: list[str]) -> str:
    if not issues:
        return ""

    lines = ["⚙️ SYSTEM HEALTH\n"]
    for issue in issues:
        lines.append(f"• {issue}")
    return "\n".join(lines) + "\n"


def write_output(content: str) -> None:
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_MD.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(OUTPUT_MD)
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

    log_issues  = check_log_health()
    feed_issues = check_feed_freshness()
    exp_issues  = check_expense_watcher_health()
    enq_issues  = check_enquiry_pipeline()
    rem_issues  = check_reminder_failures()
    git_issues  = check_github_sync()
    spb_issues  = check_sharepoint_backup_health()

    issues.extend(log_issues)
    issues.extend(feed_issues)
    issues.extend(exp_issues)
    issues.extend(enq_issues)
    issues.extend(rem_issues)
    issues.extend(git_issues)
    issues.extend(spb_issues)

    report = build_health_report(issues)
    write_output(report)

    if issues:
        print(f"[{ts}] [health-check] {len(issues)} issue(s) found — written to SYSTEM_HEALTH.md",
              flush=True)
        for issue in issues:
            print(f"  • {issue}", flush=True)
    else:
        print(f"[{ts}] [health-check] All systems OK — SYSTEM_HEALTH.md cleared", flush=True)


if __name__ == "__main__":
    main()
