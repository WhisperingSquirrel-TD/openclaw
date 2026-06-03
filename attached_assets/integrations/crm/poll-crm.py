#!/usr/bin/env python3
"""
poll-crm.py — Stackstone CRM lead importer (no LLM, no timeout risk)

Replaces the agentTurn cron that used to call the crm-update skill.
Pure Python — CSV parsing + markdown table append. Runs in under 2 seconds.

What it does:
  1. Finds the newest YYYYMMDD folder in ~/prospects/ not yet imported
  2. Reads the prospects_YYYYMMDD.csv inside it
  3. Extracts existing domains from crm.md (to prevent duplicates)
  4. Appends new Leads table rows for any unseen domain/email combos
  5. Updates the state file and "Last updated" line in crm.md

What it does NOT do:
  - Bounce/unsubscribe detection (still handled by L1 during inbox reads)
  - Campaign management (still handled by L1 on request)
  - Reply detection (still handled by L1 during inbox reads)

Scheduled at 08:00 daily (NOT 06:xx — CRM prospector runs at 06:00;
NOT 07:xx — another job runs there).

Files:
  ~/prospects/YYYYMMDD/prospects_YYYYMMDD.csv   — source CSVs
  ~/.openclaw/workspace/stackstone/crm.md        — CRM (Leads table appended)
  ~/.openclaw/workspace/memory/crm-import-state.json  — tracks last imported folder
  ~/.openclaw/workspace/memory/poll-crm-log.txt  — rotating log
"""

import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

OPENCLAW      = Path.home() / ".openclaw"
PROSPECTS_DIR = Path.home() / "prospects"
CRM_MD        = OPENCLAW / "workspace/stackstone/crm.md"
STATE_FILE    = OPENCLAW / "workspace/memory/crm-import-state.json"
LOG_FILE      = OPENCLAW / "workspace/memory/poll-crm-log.txt"

LOG_MAX_LINES = 500
LOG_TRIM_TO   = 400

# CSV column names as written by the prospector (case-insensitive match below)
COL_COMPANY = ["company", "company name", "company_name"]
COL_DOMAIN  = ["domain"]
COL_ICP     = ["icp", "icp score", "icp_score"]
COL_LOC     = ["location", "loc"]
COL_CONTACT = ["contact", "contact name", "contact_name", "name"]
COL_TITLE   = ["title", "job title", "job_title"]
COL_EMAIL   = ["email", "email address", "email_address"]


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        _rotate_log()
    except Exception:
        pass


def _rotate_log():
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) > LOG_MAX_LINES:
            LOG_FILE.write_text("\n".join(lines[-LOG_TRIM_TO:]) + "\n", encoding="utf-8")
    except Exception:
        pass


# ── Atomic write ──────────────────────────────────────────────────────────────

def write_atomic(path: Path, content: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


# ── State file ────────────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"WARNING: Could not read state file: {e} — starting fresh")
    return {"last_imported_folder": None, "last_imported_at": None}


def save_state(folder: str):
    state = {
        "last_imported_folder": folder,
        "last_imported_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_atomic(STATE_FILE, json.dumps(state, indent=2))


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _find_col(header_row: list[str], candidates: list[str]) -> int | None:
    """Case-insensitive column index lookup."""
    lower = [h.lower().strip() for h in header_row]
    for candidate in candidates:
        if candidate in lower:
            return lower.index(candidate)
    return None


def parse_csv(csv_path: Path) -> list[dict]:
    """Parse a prospects CSV. Returns list of normalised row dicts."""
    rows = []
    try:
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                log(f"WARNING: Empty CSV {csv_path}")
                return rows

            ci = {
                "company": _find_col(headers, COL_COMPANY),
                "domain":  _find_col(headers, COL_DOMAIN),
                "icp":     _find_col(headers, COL_ICP),
                "loc":     _find_col(headers, COL_LOC),
                "contact": _find_col(headers, COL_CONTACT),
                "title":   _find_col(headers, COL_TITLE),
                "email":   _find_col(headers, COL_EMAIL),
            }

            missing = [k for k, v in ci.items() if v is None and k in ("company", "domain", "email")]
            if missing:
                log(f"WARNING: CSV {csv_path.name} missing required columns: {missing} — skipping")
                return rows

            for raw in reader:
                def _get(key):
                    idx = ci.get(key)
                    return raw[idx].strip() if idx is not None and idx < len(raw) else ""

                rows.append({
                    "company": _get("company"),
                    "domain":  _get("domain").lower(),
                    "icp":     _get("icp") or "—",
                    "loc":     _get("loc") or "—",
                    "contact": _get("contact") or "—",
                    "title":   _get("title") or "—",
                    "email":   _get("email").lower(),
                })
    except Exception as e:
        log(f"ERROR: Could not parse CSV {csv_path}: {e}")
    return rows


# ── CRM.md helpers ────────────────────────────────────────────────────────────

def load_crm() -> str:
    try:
        if CRM_MD.exists():
            return CRM_MD.read_text(encoding="utf-8")
    except Exception as e:
        log(f"ERROR: Cannot read crm.md: {e}")
        sys.exit(1)
    return ""


def extract_existing_emails(crm_text: str) -> set[str]:
    """Pull every email address already in the Leads table."""
    emails = set()
    in_leads = False
    for line in crm_text.splitlines():
        if re.match(r"^##\s+Leads", line):
            in_leads = True
            continue
        if in_leads and re.match(r"^##\s+", line):
            break
        if in_leads and line.startswith("|"):
            # Find anything that looks like an email address in the row
            found = re.findall(r"[\w.+\-]+@[\w.\-]+\.\w+", line)
            emails.update(e.lower() for e in found)
    return emails


def build_lead_row(r: dict) -> str:
    """Format one Leads table row. Pipes in cell values are replaced with commas."""
    def _cell(v):
        return str(v).replace("|", ",").strip() or "—"

    return (
        f"| {_cell(r['company'])} | {_cell(r['domain'])} | {_cell(r['icp'])} "
        f"| {_cell(r['loc'])} | {_cell(r['contact'])} | {_cell(r['title'])} "
        f"| {_cell(r['email'])} | — | New | | | |"
    )


def append_leads(crm_text: str, new_rows: list[str]) -> str:
    """
    Insert new_rows after the last data row of the Leads table.
    The Leads table ends at the last `|`-prefixed line before the next `##` heading
    or end of file.
    """
    lines = crm_text.splitlines()
    in_leads     = False
    last_row_idx = None

    for i, line in enumerate(lines):
        if re.match(r"^##\s+Leads", line):
            in_leads = True
            continue
        if in_leads and re.match(r"^##\s+", line):
            break
        if in_leads and line.startswith("|"):
            last_row_idx = i

    if last_row_idx is None:
        log("WARNING: Could not find Leads table in crm.md — appending at end of file")
        return crm_text + "\n" + "\n".join(new_rows) + "\n"

    lines[last_row_idx + 1:last_row_idx + 1] = new_rows
    return "\n".join(lines) + "\n"


def update_last_updated(crm_text: str) -> str:
    """Refresh the 'Last updated' line near the top."""
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    return re.sub(
        r"\*Last updated:.*?\*",
        f"*Last updated: {ts} | Managed by L1 (poll-crm.py)*",
        crm_text,
        count=1,
    )


# ── Prospect folder discovery ─────────────────────────────────────────────────

def find_new_folders(last_imported: str | None) -> list[str]:
    """
    Return all YYYYMMDD folders in ~/prospects/ that are newer than last_imported,
    sorted oldest-first so we import in chronological order.
    """
    if not PROSPECTS_DIR.exists():
        log(f"WARNING: {PROSPECTS_DIR} does not exist — nothing to import")
        return []

    folders = sorted(
        d.name for d in PROSPECTS_DIR.iterdir()
        if d.is_dir() and re.match(r"^\d{8}$", d.name)
    )

    if last_imported:
        folders = [f for f in folders if f > last_imported]

    return folders


def find_csv_in_folder(folder: Path) -> Path | None:
    """Find the prospects CSV inside a dated folder."""
    candidates = sorted(folder.glob("prospects_*.csv")) + sorted(folder.glob("*.csv"))
    return candidates[0] if candidates else None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("CRM import poller starting")

    state         = load_state()
    last_imported = state.get("last_imported_folder")
    log(f"Last imported folder: {last_imported or 'none'}")

    crm_text = load_crm()

    new_folders = find_new_folders(last_imported)
    if not new_folders:
        crm_text = update_last_updated(crm_text)
        write_atomic(CRM_MD, crm_text)
        log("No new prospect folders to import — refreshed crm.md timestamp only")
        return

    log(f"New folders to process: {new_folders}")
    existing_emails = extract_existing_emails(crm_text)
    log(f"crm.md: {len(existing_emails)} existing emails loaded")

    total_added = 0

    for folder_name in new_folders:
        folder  = PROSPECTS_DIR / folder_name
        csv_path = find_csv_in_folder(folder)

        if not csv_path:
            log(f"WARNING: No CSV found in {folder} — skipping")
            save_state(folder_name)
            continue

        log(f"Processing {csv_path.name} ({folder_name})")
        prospects = parse_csv(csv_path)
        log(f"  {len(prospects)} rows in CSV")

        new_rows = []
        for r in prospects:
            if not r["email"] or r["email"] == "—":
                continue
            if r["email"] in existing_emails:
                continue
            new_rows.append(build_lead_row(r))
            existing_emails.add(r["email"])

        if new_rows:
            crm_text = append_leads(crm_text, new_rows)
            log(f"  +{len(new_rows)} new leads added")
            total_added += len(new_rows)
        else:
            log(f"  All {len(prospects)} rows already in CRM — nothing to add")

        save_state(folder_name)
        log(f"  State updated → {folder_name}")

    crm_text = update_last_updated(crm_text)
    write_atomic(CRM_MD, crm_text)
    if total_added > 0:
        log(f"crm.md written — {total_added} new leads total")
    else:
        log("crm.md written — timestamp refreshed; no new leads across all folders")

    log("CRM import poller complete")


if __name__ == "__main__":
    main()
