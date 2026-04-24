#!/usr/bin/env python3
"""
SharePoint CRM housekeeping sweep for OpenClaw.

Reads the local SharePoint cache, reviews each CRM entity (Account or Opportunity)
using the configured model via the Anthropic batch API (50% cost saving), and executes safe
normalisation changes via the existing sharepoint-queue.json write path.

Operating modes
───────────────
  Cron mode  (default)
    First run:  discover entities → submit Anthropic batch → save state
    Next run:   collect batch results → execute/propose → report to Telegram

  --sync flag
    Process all entities immediately using the synchronous Anthropic API.
    Useful for on-demand runs, /sp-housekeep Telegram command, and testing.

Arguments
─────────
  --mode  execute|dry-run     (default: execute)
  --scope all|accounts|opportunities|entity:<name>  (default: all)
  --sync                      Skip batch API, process immediately

Decision classes
────────────────
  safe        → auto-execute in execute mode; include in proposal in dry-run
  ambiguous   → never auto-write; always surfaced for Tom/L1 judgement
  blocked     → reported only; no write attempted

Scheduling
──────────
  Nightly cron at 02:00 (added by install script)
  On-demand via /sp-housekeep in mgmt-bot

Output
──────
  execute  → ~/.openclaw/workspace/HOUSEKEEPING_REPORT.md
  dry-run  → ~/.openclaw/workspace/HOUSEKEEPING_PROPOSAL.md
  Both     → Telegram notification on completion
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

STATE_DIR    = Path.home() / ".openclaw"
CACHE_DIR    = STATE_DIR / "workspace/sharepoint-cache"
MANIFEST     = CACHE_DIR / ".manifest.json"
QUEUE_FILE   = STATE_DIR / "sharepoint-queue.json"
RESULT_MD    = STATE_DIR / "workspace/SHAREPOINT_RESULT.md"
REPORT_MD    = STATE_DIR / "workspace/HOUSEKEEPING_REPORT.md"
PROPOSAL_MD  = STATE_DIR / "workspace/HOUSEKEEPING_PROPOSAL.md"
LOG_FILE     = STATE_DIR / "workspace/memory/sp-housekeeping-log.txt"
STATE_FILE   = STATE_DIR / "integrations/microsoft/sp-housekeeping-state.json"

ANTHROPIC_API_URL   = "https://api.anthropic.com/v1/messages"
ANTHROPIC_BATCH_URL = "https://api.anthropic.com/v1/messages/batches"
ANTHROPIC_MODEL     = "claude-haiku-4-5"

# SharePoint CRM root paths to search for entities
CRM_ACCOUNTS_PREFIX      = "Stackstone CRM/Accounts"
CRM_OPPORTUNITIES_PREFIX = "Stackstone CRM/Opportunities"

# Batch expiry — drop batches older than this (Anthropic expires after 24h)
BATCH_MAX_AGE_HOURS = 23

# Per-entity content limits sent to the model (keeps tokens reasonable)
CURRENT_MD_MAX_CHARS     = 4000
ARTIFACT_MAX_CHARS       = 2000
MAX_ARTIFACTS_IN_PROMPT  = 3

LOG_MAX_LINES = 500
LOG_TRIM_TO   = 400


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    line = f"[{ts()}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = LOG_FILE.read_text().splitlines(keepends=True)
        except FileNotFoundError:
            existing = []
        if len(existing) >= LOG_MAX_LINES:
            existing = existing[-LOG_TRIM_TO:]
        existing.append(line + "\n")
        tmp = LOG_FILE.with_suffix(".tmp")
        tmp.write_text("".join(existing))
        tmp.replace(LOG_FILE)
    except Exception:
        pass


def log_err(msg: str) -> None:
    log(f"ERROR: {msg}")


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_file = STATE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
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


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            data.setdefault("pending_batches", [])
            data.setdefault("last_run", None)
            return data
    except Exception as e:
        log(f"WARNING: Could not read state: {e} — starting fresh")
    return {"pending_batches": [], "last_run": None}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(STATE_FILE)
    except Exception as e:
        log_err(f"Could not save state: {e}")


# ---------------------------------------------------------------------------
# Entity discovery
# ---------------------------------------------------------------------------

def _parse_entity_key(sp_path: str) -> tuple[str, str] | None:
    """
    Given a SharePoint path, return (entity_type, entity_name) or None.

    /Stackstone CRM/Accounts/Harken Health/...    → ("account",      "Harken Health")
    /Stackstone CRM/Opportunities/Croyde Medical/... → ("opportunity", "Croyde Medical")
    """
    p = sp_path.lstrip("/")
    for prefix, etype in [
        (CRM_ACCOUNTS_PREFIX,      "account"),
        (CRM_OPPORTUNITIES_PREFIX, "opportunity"),
    ]:
        if p.startswith(prefix + "/"):
            remainder = p[len(prefix) + 1:]
            parts = remainder.split("/", 1)
            if parts[0]:
                return etype, parts[0]
    return None


def discover_entities(scope: str) -> list[dict]:
    """
    Read the SharePoint manifest and return a sorted list of entity dicts.

    Each dict: {"name": str, "type": "account"|"opportunity", "files": [path_str, ...]}

    Scope: all | accounts | opportunities | entity:<name>
    Priority order: accounts first, then opportunities (as per policy).
    """
    if not MANIFEST.exists():
        log("WARNING: Manifest not found — run /sp-sync first to populate the cache.")
        return []

    try:
        manifest = json.loads(MANIFEST.read_text())
    except Exception as e:
        log_err(f"Could not read manifest: {e}")
        return []

    entities: dict[tuple, list] = {}
    for sp_path in manifest:
        result = _parse_entity_key(sp_path)
        if result is None:
            continue
        etype, ename = result
        key = (etype, ename)
        entities.setdefault(key, [])
        # only include files that are actually cached/extracted (readable)
        entry = manifest[sp_path]
        if entry.get("cached") or entry.get("extracted"):
            entities[key].append(sp_path)

    # Apply scope filter
    scope_lower = scope.lower()
    filtered = []
    for (etype, ename), files in entities.items():
        if scope_lower == "all":
            filtered.append({"name": ename, "type": etype, "files": sorted(files)})
        elif scope_lower == "accounts" and etype == "account":
            filtered.append({"name": ename, "type": etype, "files": sorted(files)})
        elif scope_lower == "opportunities" and etype == "opportunity":
            filtered.append({"name": ename, "type": etype, "files": sorted(files)})
        elif scope_lower.startswith("entity:"):
            target = scope[7:].strip()
            if ename.lower() == target.lower():
                filtered.append({"name": ename, "type": etype, "files": sorted(files)})

    # Sort: accounts first, then opportunities, alphabetically within each group
    filtered.sort(key=lambda e: (0 if e["type"] == "account" else 1, e["name"].lower()))
    log(f"Discovered {len(filtered)} entities (scope: {scope})")
    return filtered


# ---------------------------------------------------------------------------
# Entity content reading
# ---------------------------------------------------------------------------

def _local_path_for(sp_path: str) -> Path:
    """Convert SharePoint path to local cache path."""
    clean = sp_path.lstrip("/")
    return CACHE_DIR / clean


def _read_entity_content(entity: dict) -> dict:
    """
    For one entity, read Current.md and up to MAX_ARTIFACTS_IN_PROMPT
    recent dated artifacts from the local cache.

    Returns: {
        "current_md": str | None,
        "current_md_path": str | None,
        "artifacts": [{"path": str, "content": str}, ...],
        "all_files": [str, ...],          # all SP paths for this entity
        "missing_current_md": bool,
    }
    """
    name = entity["name"]
    files = entity["files"]

    current_md_content = None
    current_md_path = None
    artifacts = []
    all_files = sorted(files)

    # Find Current.md
    for sp_path in files:
        filename = Path(sp_path).name
        if filename.lower() == f"{name.lower()} - current.md":
            local = _local_path_for(sp_path)
            if local.exists():
                raw = local.read_text(errors="replace")
                # Strip cache header line
                lines = raw.splitlines()
                if lines and lines[0].startswith("<!-- sharepoint-cache:"):
                    raw = "\n".join(lines[1:]).lstrip()
                current_md_content = raw[:CURRENT_MD_MAX_CHARS]
                current_md_path = sp_path
            break

    # Find dated artifacts (YYYY-MM-DD prefix), sort newest first
    dated = sorted(
        [f for f in files if Path(f).name[:10].replace("-", "").isdigit()
         and len(Path(f).name) > 10 and Path(f).name[10] == " "],
        reverse=True,
    )

    for sp_path in dated[:MAX_ARTIFACTS_IN_PROMPT]:
        local = _local_path_for(sp_path)
        extracted = Path(str(local) + ".extracted.md")
        read_from = extracted if extracted.exists() else local
        if read_from.exists():
            raw = read_from.read_text(errors="replace")
            lines = raw.splitlines()
            if lines and (lines[0].startswith("<!-- sharepoint-cache:") or
                          lines[0].startswith("<!-- sharepoint-binary-extract:")):
                raw = "\n".join(lines[1:]).lstrip()
            artifacts.append({
                "path": sp_path,
                "content": raw[:ARTIFACT_MAX_CHARS],
            })

    return {
        "current_md": current_md_content,
        "current_md_path": current_md_path,
        "artifacts": artifacts,
        "all_files": all_files,
        "missing_current_md": current_md_content is None,
    }


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

# The organisational rules live entirely in the skill file so L1 can update
# them without touching this code. Only the JSON output schema is defined here
# because that is a mechanical parsing contract, not a policy decision.
SKILL_FILE = STATE_DIR / "skills/crm-sharepoint/SKILL.md"

OUTPUT_CONTRACT = """
---

## Output contract for this run (follow exactly)

You must respond with **valid JSON only** — no prose, no markdown fences, nothing else.

IMPORTANT — SharePoint write model:
The underlying system supports create, update, append, and move.
There is NO delete capability — never attempt to delete files.

Action guide:
- "create"   — create a new file (provide "content")
- "update"   — overwrite an existing file (provide "content")
- "append"   — add content to an existing file (provide "content")
- "move"          — relocate or rename a file/folder (provide "path" = source, "destination" = target full path; NO content needed)
  - Use move to relocate loose/raw/source files into an Archive/ or Source/ subfolder
  - Use move to rename a file to its correct canonical name
  - Move is safe and reversible — prefer it over recreate when the source file simply needs relocating
- "delete_folder" — delete a folder (provide "path" = folder path; NO content or destination needed)
  - ONLY use after all files have been moved out — the system will REFUSE if the folder still has any contents
  - Safe to queue speculatively: if the folder is not yet empty the queue processor rejects it cleanly
  - Use this to remove leftover empty parent folders after moving their contents elsewhere
- "recreate" — create at canonical path when content also needs rewriting (provide "content" and "from_path")
  - The from_path file will NOT be deleted; it is surfaced as ambiguous for manual review

Output schema:
{
  "entity": "<name>",
  "type": "account|opportunity",
  "assessment": "<one sentence summary of current state>",
  "safe_changes": [
    {
      "action": "create|recreate|update|append|move|delete_folder",
      "path": "<full SP path — source for move, folder for delete_folder, destination for all others>",
      "destination": "<full SP destination path — required for move only>",
      "content": "<full file content — required for create/recreate/update/append; omit for move/delete_folder>",
      "from_path": "<original path — required for recreate only>",
      "reason": "<brief reason>"
    }
  ],
  "ambiguous": [
    {"file": "<path>", "reason": "<why judgement is needed>"}
  ],
  "blocked": [
    {"reason": "<why blocked>"}
  ],
  "current_md_status": "up_to_date|needs_update|missing"
}

If there is nothing to do, return empty arrays for safe_changes, ambiguous, blocked.
Only include safe_changes you are confident about. When in doubt, put in ambiguous.
"""

_MINIMAL_FALLBACK = """You are reviewing a SharePoint CRM entity as part of a structured housekeeping sweep.

WARNING: The crm-sharepoint skill file was not found at ~/.openclaw/skills/crm-sharepoint/SKILL.md.
Operating with minimal fallback rules only. Run /install to deploy the skill.

Core rules (minimal fallback):
- Folder per entity under /Accounts/ or /Opportunities/
- <Company> - Current.md is the retrieval anchor (latest truth)
- Dated files use YYYY-MM-DD - <Type> - <Description>.md format
- Never destructively reorganise — surface ambiguous items for judgement
- Never auto-write anything you are not certain about
"""


def _load_system_prompt() -> str:
    """
    Read the crm-sharepoint skill file and append the output contract.
    If the skill file is not found, use a minimal fallback with a clear warning.
    The skill file is the single source of truth for all organisational rules —
    update it and the next housekeeping run automatically picks up the changes.
    """
    if SKILL_FILE.exists():
        skill_content = SKILL_FILE.read_text()
        return skill_content + OUTPUT_CONTRACT
    else:
        log(
            f"WARNING: Skill file not found at {SKILL_FILE}. "
            "Run /install to deploy the crm-sharepoint skill. "
            "Using minimal fallback rules."
        )
        return _MINIMAL_FALLBACK + OUTPUT_CONTRACT


def _build_entity_prompt(entity: dict, content: dict) -> str:
    name = entity["name"]
    etype = entity["type"]
    entity_root = (
        f"/Stackstone CRM/Accounts/{name}"
        if etype == "account"
        else f"/Stackstone CRM/Opportunities/{name}"
    )

    parts = [
        f"Entity: {name}",
        f"Type: {etype}",
        f"Folder: {entity_root}",
        "",
        "## All files in this entity folder",
    ]
    for f in content["all_files"]:
        parts.append(f"  {f}")
    parts.append("")

    if content["current_md"]:
        parts += [
            "## Current.md (retrieval anchor — latest truth)",
            f"Path: {content['current_md_path']}",
            "",
            content["current_md"],
            "",
        ]
    else:
        parts += [
            "## Current.md",
            "MISSING — no Current.md file found for this entity.",
            "",
        ]

    if content["artifacts"]:
        parts.append("## Recent dated artifacts (newest first, truncated)")
        for art in content["artifacts"]:
            parts += [
                f"### {art['path']}",
                art["content"],
                "",
            ]
    else:
        parts.append("## Recent dated artifacts\nNone found in cache.")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Anthropic helpers
# ---------------------------------------------------------------------------

def _anthropic_headers() -> dict:
    return {
        "x-api-key":         os.environ.get("ANTHROPIC_API_KEY", ""),
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }


def _call_anthropic_sync(user_prompt: str) -> str:
    """Single synchronous Anthropic call. Used in --sync mode."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    body = json.dumps({
        "model":      ANTHROPIC_MODEL,
        "max_tokens": 2048,
        "system":     _load_system_prompt(),
        "messages":   [{"role": "user", "content": user_prompt}],
    }).encode()

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=body,
        headers=_anthropic_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]


def submit_anthropic_batch(requests: list[dict]) -> str | None:
    """
    Submit a list of {custom_id, prompt} dicts as one Anthropic batch.
    Returns batch_id on success, None on failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log_err("ANTHROPIC_API_KEY not set — cannot submit batch")
        return None

    system_prompt = _load_system_prompt()  # load once — same skill applies to all entities in this batch
    batch_requests = [
        {
            "custom_id": item["custom_id"],
            "params": {
                "model":      ANTHROPIC_MODEL,
                "max_tokens": 2048,
                "system":     system_prompt,
                "messages":   [{"role": "user", "content": item["prompt"]}],
            },
        }
        for item in requests
    ]

    body = json.dumps({"requests": batch_requests}).encode()
    req = urllib.request.Request(
        ANTHROPIC_BATCH_URL,
        data=body,
        headers=_anthropic_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        batch_id = data.get("id", "")
        log(f"  Batch submitted: {batch_id} ({len(batch_requests)} entities)")
        return batch_id
    except Exception as e:
        log_err(f"Batch submit failed: {e}")
        return None


def poll_anthropic_batch(batch_id: str) -> tuple[str, dict[str, str]]:
    """
    Check batch status. Returns (status, {custom_id: response_text}).
    status: "in_progress" | "ended"
    """
    req = urllib.request.Request(
        f"{ANTHROPIC_BATCH_URL}/{batch_id}",
        headers=_anthropic_headers(),
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        log_err(f"Batch poll failed for {batch_id}: {e}")
        return "in_progress", {}

    status = data.get("processing_status", "in_progress")
    counts = data.get("request_counts", {})
    log(f"  Batch {batch_id}: {status} — {counts}")

    if status != "ended":
        return "in_progress", {}

    # Collect results
    results: dict[str, str] = {}
    try:
        results_req = urllib.request.Request(
            f"{ANTHROPIC_BATCH_URL}/{batch_id}/results",
            headers=_anthropic_headers(),
            method="GET",
        )
        with urllib.request.urlopen(results_req, timeout=30) as resp:
            for line in resp.read().decode().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    cid = item.get("custom_id", "")
                    if item.get("result", {}).get("type") == "succeeded":
                        text = item["result"]["message"]["content"][0]["text"]
                        results[cid] = text
                    else:
                        results[cid] = '{"safe_changes":[],"ambiguous":[],"blocked":[{"reason":"batch_error"}],"current_md_status":"up_to_date","assessment":"Batch processing error"}'
                except Exception:
                    pass
    except Exception as e:
        log_err(f"Batch results fetch failed for {batch_id}: {e}")

    log(f"  Batch {batch_id} ended — {len(results)} result(s) retrieved")
    return "ended", results


# ---------------------------------------------------------------------------
# Decision parsing
# ---------------------------------------------------------------------------

def parse_decision(response_text: str, entity_name: str) -> dict:
    """Parse the model's JSON response into a decision dict."""
    try:
        raw = response_text.strip()
        # Strip any accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
        decision = json.loads(raw)
        decision.setdefault("safe_changes", [])
        decision.setdefault("ambiguous", [])
        decision.setdefault("blocked", [])
        decision.setdefault("current_md_status", "up_to_date")
        decision.setdefault("assessment", "")
        decision.setdefault("entity", entity_name)
        return decision
    except Exception as e:
        log_err(f"Could not parse decision for {entity_name}: {e} — raw: {response_text[:200]}")
        return {
            "entity": entity_name,
            "assessment": "Parse error",
            "safe_changes": [],
            "ambiguous": [],
            "blocked": [{"reason": f"Could not parse model response: {e}"}],
            "current_md_status": "up_to_date",
        }


# ---------------------------------------------------------------------------
# Queue execution
# ---------------------------------------------------------------------------

def _read_queue() -> list:
    try:
        if QUEUE_FILE.exists():
            return json.loads(QUEUE_FILE.read_text())
    except Exception:
        pass
    return []


def _write_queue(items: list) -> None:
    tmp = QUEUE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2))
    tmp.replace(QUEUE_FILE)


def execute_safe_changes(entity: dict, decision: dict) -> list[dict]:
    """
    Submit safe changes for one entity to sharepoint-queue.json.
    Returns list of submitted queue entries (for report tracking).
    """
    safe = decision.get("safe_changes", [])
    if not safe:
        return []

    submitted = []
    queue = _read_queue()
    run_ts = datetime.now(timezone.utc).isoformat()

    for change in safe:
        action = change.get("action", "").lower()
        path   = change.get("path", "")
        if not path:
            continue

        if action == "recreate":
            # SharePoint has no rename/delete. We create the new canonical file.
            # The original (from_path) is NOT touched — it is surfaced in ambiguous
            # so Tom/L1 can manually remove it when ready.
            from_path = change.get("from_path", "")
            content   = change.get("content", "")
            if not content:
                decision["ambiguous"].append({
                    "file": from_path or path,
                    "reason": "Recreate requested but no content provided — skipped",
                })
                continue
            if from_path:
                decision["ambiguous"].append({
                    "file": from_path,
                    "reason": f"Original file — new canonical version created at {path}. Safe to delete manually.",
                })
            entry_id = f"sp-hk-{entity['name'][:8].replace(' ', '')}-{len(queue)+1}-{int(time.time())}"
            entry = {
                "id":            entry_id,
                "operation":     "create",
                "path":          path,
                "content":       content,
                "requested_at":  run_ts,
                "_housekeeping": True,
                "_action":       "recreate",
                "_from_path":    from_path,
                "_reason":       change.get("reason", ""),
                "_verified":     False,
            }
            queue.append(entry)
            submitted.append(entry)

        elif action == "delete_folder":
            entry_id = f"sp-hk-{entity['name'][:8].replace(' ', '')}-{len(queue)+1}-{int(time.time())}"
            entry = {
                "id":            entry_id,
                "operation":     "delete_folder",
                "path":          path,
                "requested_at":  run_ts,
                "_housekeeping": True,
                "_reason":       change.get("reason", ""),
                "_verified":     False,
            }
            queue.append(entry)
            submitted.append(entry)

        elif action == "move":
            destination = change.get("destination", "").strip()
            if not destination:
                decision["ambiguous"].append({
                    "file": path,
                    "reason": "Move requested but no destination provided — skipped",
                })
                continue
            entry_id = f"sp-hk-{entity['name'][:8].replace(' ', '')}-{len(queue)+1}-{int(time.time())}"
            entry = {
                "id":            entry_id,
                "operation":     "move",
                "path":          path,
                "destination":   destination,
                "requested_at":  run_ts,
                "_housekeeping": True,
                "_reason":       change.get("reason", ""),
                "_verified":     False,
            }
            queue.append(entry)
            submitted.append(entry)

        elif action in ("create", "update", "append"):
            content = change.get("content", "")
            if not content:
                continue
            entry_id = f"sp-hk-{entity['name'][:8].replace(' ', '')}-{len(queue)+1}-{int(time.time())}"
            entry = {
                "id":            entry_id,
                "operation":     action,
                "path":          path,
                "content":       content,
                "requested_at":  run_ts,
                "_housekeeping": True,
                "_reason":       change.get("reason", ""),
                "_verified":     False,
            }
            queue.append(entry)
            submitted.append(entry)

    if submitted:
        _write_queue(queue)
        log(f"  Queued {len(submitted)} write(s)/move(s) for {entity['name']} "
            f"(pending verification — check SHAREPOINT_RESULT.md)")

    return submitted


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _write_report(results: list[dict], mode: str) -> Path:
    """Write HOUSEKEEPING_REPORT.md or HOUSEKEEPING_PROPOSAL.md."""
    out_path = PROPOSAL_MD if mode == "dry-run" else REPORT_MD
    run_ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    total_entities = len(results)
    total_safe     = sum(len(r.get("safe_changes", [])) for r in results)
    total_queued   = sum(len(r.get("queued", [])) for r in results)
    total_ambig    = sum(len(r.get("ambiguous", [])) for r in results)
    total_blocked  = sum(len(r.get("blocked", [])) for r in results)
    cm_updates     = sum(1 for r in results if r.get("current_md_status") == "needs_update")
    cm_missing     = sum(1 for r in results if r.get("current_md_status") == "missing")

    header = "HOUSEKEEPING PROPOSAL" if mode == "dry-run" else "HOUSEKEEPING REPORT"
    verify_note = (
        "\n> ⚠️ **Writes are queued, not yet verified.**  "
        "Check `SHAREPOINT_RESULT.md` to confirm each write completed successfully.  "
        "No entity is considered complete until its queued writes are verified.\n"
        if mode == "execute" else ""
    )
    lines = [
        f"# SharePoint {header}",
        f"_Run: {run_ts} — Mode: {mode}_",
        verify_note,
        "## Summary",
        f"| | |",
        f"|---|---|",
        f"| Entities reviewed | {total_entities} |",
        (f"| Safe changes proposed | {total_safe} |"
         if mode == "dry-run"
         else f"| Writes queued (pending verification) | {total_queued} |"),
        f"| Current.md needs update | {cm_updates} |",
        f"| Current.md missing | {cm_missing} |",
        f"| Needs Tom/L1 judgement | {total_ambig} |",
        f"| Blocked | {total_blocked} |",
        "",
    ]

    # Ambiguous items first (highest priority for review)
    ambig_results = [r for r in results if r.get("ambiguous")]
    if ambig_results:
        lines += ["---", "", "## Needs judgement"]
        for r in ambig_results:
            lines.append(f"\n### {r['entity']} ({r['type']})")
            for item in r["ambiguous"]:
                lines.append(f"- **{item.get('file', '?')}**")
                lines.append(f"  _{item.get('reason', '')}_")
        lines.append("")

    # Blocked items
    blocked_results = [r for r in results if r.get("blocked")]
    if blocked_results:
        lines += ["---", "", "## Blocked"]
        for r in blocked_results:
            lines.append(f"\n### {r['entity']} ({r['type']})")
            for item in r["blocked"]:
                lines.append(f"- {item.get('reason', '?')}")
        lines.append("")

    # Per-entity detail
    lines += ["---", "", "## Per-entity detail"]
    for r in results:
        status_icon = "✅" if not r.get("ambiguous") and not r.get("blocked") else (
            "⚠️" if r.get("ambiguous") else "❌"
        )
        lines.append(f"\n### {status_icon} {r['entity']} ({r['type']})")
        lines.append(f"_{r.get('assessment', '')}_")

        if mode == "dry-run" and r.get("safe_changes"):
            lines.append("\n**Proposed safe changes:**")
            for ch in r["safe_changes"]:
                lines.append(f"- `{ch.get('action', '?')}` {ch.get('path', '')} — {ch.get('reason', '')}")

        elif mode == "execute" and r.get("queued"):
            lines.append("\n**Writes queued (pending verification — check SHAREPOINT_RESULT.md):**")
            for q in r["queued"]:
                lines.append(f"- `{q.get('operation', '?')}` {q.get('path', '')} (id: `{q.get('id', '')}`)")

        if r.get("current_md_status") in ("needs_update", "missing"):
            lines.append(f"\n⚠️ Current.md: {r['current_md_status']}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    log(f"Report written: {out_path}")
    return out_path


def _send_telegram(summary: str) -> None:
    """Send a Telegram notification via the mgmt-bot token if available."""
    bot_token = os.environ.get("MGMT_BOT_TOKEN", "")
    chat_id   = os.environ.get("MGMT_BOT_CHAT_ID", "")
    if not bot_token or not chat_id:
        return
    try:
        body = json.dumps({
            "chat_id":    chat_id,
            "text":       summary,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        log(f"Telegram notify failed (non-fatal): {e}")


def _telegram_summary(results: list[dict], mode: str, scope: str) -> str:
    total    = len(results)
    queued   = sum(len(r.get("queued", [])) for r in results)
    proposed = sum(len(r.get("safe_changes", [])) for r in results)
    ambig    = sum(len(r.get("ambiguous", [])) for r in results)
    blocked  = sum(len(r.get("blocked", [])) for r in results)
    cm_issues = sum(1 for r in results
                    if r.get("current_md_status") in ("needs_update", "missing"))

    icon = "🧹"
    if mode == "dry-run":
        action_line = f"_{proposed} change(s) proposed_"
    else:
        action_line = f"_{queued} write(s) queued — pending verification (check SHAREPOINT\\_RESULT.md)_"

    lines = [
        f"{icon} *SharePoint Housekeeping {'Proposal' if mode == 'dry-run' else 'Queued'}*",
        f"Scope: `{scope}` · Mode: `{mode}`",
        "",
        f"• {total} entities reviewed",
        f"• {action_line}",
    ]
    if cm_issues:
        lines.append(f"• {cm_issues} Current.md issue(s)")
    if ambig:
        lines.append(f"• ⚠️ {ambig} item(s) need judgement")
    if blocked:
        lines.append(f"• ❌ {blocked} blocked write(s)")

    out_file = PROPOSAL_MD if mode == "dry-run" else REPORT_MD
    lines.append(f"\nFull report: `{out_file.name}`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pending batch collection
# ---------------------------------------------------------------------------

def process_pending_batches(state: dict, mode: str, scope: str) -> int:
    """
    Check all pending batches. Process any that have completed.
    Returns count of entities processed.
    """
    pending = state.get("pending_batches", [])
    if not pending:
        return 0

    now = datetime.now(timezone.utc)
    still_pending = []
    total_processed = 0

    for batch_entry in pending:
        batch_id      = batch_entry["batch_id"]
        submitted_at  = datetime.fromisoformat(batch_entry["submitted_at"])
        batch_mode    = batch_entry.get("mode", mode)
        batch_scope   = batch_entry.get("scope", scope)
        entity_map    = batch_entry.get("entity_map", {})  # custom_id → entity dict

        age_hours = (now - submitted_at).total_seconds() / 3600
        if age_hours > BATCH_MAX_AGE_HOURS:
            log(f"  Dropping expired batch {batch_id} ({age_hours:.1f}h old)")
            continue

        status, responses = poll_anthropic_batch(batch_id)
        if status != "ended":
            still_pending.append(batch_entry)
            continue

        # Process results
        log(f"  Collecting results from batch {batch_id} — {len(responses)} response(s)")
        results = []

        for custom_id, response_text in responses.items():
            entity = entity_map.get(custom_id)
            if not entity:
                continue

            decision = parse_decision(response_text, entity["name"])
            result = {
                "entity":            entity["name"],
                "type":              entity["type"],
                "assessment":        decision.get("assessment", ""),
                "safe_changes":      decision.get("safe_changes", []),
                "ambiguous":         decision.get("ambiguous", []),
                "blocked":           decision.get("blocked", []),
                "current_md_status": decision.get("current_md_status", "up_to_date"),
                "queued":            [],
            }

            if batch_mode == "execute":
                queued = execute_safe_changes(entity, decision)
                result["queued"] = queued
            # In dry-run, safe_changes are just recorded in the proposal

            results.append(result)
            total_processed += 1

        if results:
            _write_report(results, batch_mode)
            summary = _telegram_summary(results, batch_mode, batch_scope)
            _send_telegram(summary)
            log(f"  Processed {len(results)} entities from batch {batch_id}")

    state["pending_batches"] = still_pending
    return total_processed


# ---------------------------------------------------------------------------
# Synchronous processing (--sync mode)
# ---------------------------------------------------------------------------

def process_sync(entities: list[dict], mode: str) -> list[dict]:
    """Process entities immediately using the synchronous API."""
    results = []

    for entity in entities:
        log(f"  Processing {entity['name']} ({entity['type']}) …")
        content  = _read_entity_content(entity)
        prompt   = _build_entity_prompt(entity, content)

        try:
            response_text = _call_anthropic_sync(prompt)
        except Exception as e:
            log_err(f"Sync call failed for {entity['name']}: {e}")
            results.append({
                "entity":            entity["name"],
                "type":              entity["type"],
                "assessment":        "API error",
                "safe_changes":      [],
                "ambiguous":         [],
                "blocked":           [{"reason": str(e)}],
                "current_md_status": "up_to_date",
                "queued":            [],
            })
            continue

        decision = parse_decision(response_text, entity["name"])
        result = {
            "entity":            entity["name"],
            "type":              entity["type"],
            "assessment":        decision.get("assessment", ""),
            "safe_changes":      decision.get("safe_changes", []),
            "ambiguous":         decision.get("ambiguous", []),
            "blocked":           decision.get("blocked", []),
            "current_md_status": decision.get("current_md_status", "up_to_date"),
            "queued":            [],
        }

        if mode == "execute":
            queued = execute_safe_changes(entity, decision)
            result["queued"] = queued

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Degraded-state check
# ---------------------------------------------------------------------------

MANIFEST_MAX_AGE_HOURS = 36  # 1.5× nightly cron interval — buffer for slow/late sp-sync runs

_TOKEN_CANDIDATES = [
    STATE_DIR / "integrations/microsoft/token-assistant.json",
    STATE_DIR / "integrations/microsoft-l1/token.json",
    STATE_DIR / "integrations/microsoft-assistant/token.json",
]


def _resolve_token_file() -> Path | None:
    for candidate in _TOKEN_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


TOKEN_FILE: Path = _resolve_token_file() or _TOKEN_CANDIDATES[0]


def _check_degraded_state() -> list[str]:
    """
    Check for conditions that should block a sweep entirely.
    Returns a list of problem strings. Empty list = system looks healthy.

    Checks:
    1. Manifest exists and is recent
    2. Queue file is writable (write path open)
    3. Assistant token file exists (auth available)
    """
    problems = []

    # 1. Manifest freshness
    if not MANIFEST.exists():
        problems.append("SharePoint manifest missing — run /sp-sync first")
    else:
        try:
            manifest = json.loads(MANIFEST.read_text())
            synced_at = manifest.get("synced_at", "")
            if synced_at:
                synced_dt = datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - synced_dt).total_seconds() / 3600
                if age_hours > MANIFEST_MAX_AGE_HOURS:
                    problems.append(
                        f"SharePoint manifest is stale ({age_hours:.1f}h old, limit {MANIFEST_MAX_AGE_HOURS}h) "
                        f"— run /sp-sync to refresh"
                    )
        except Exception as e:
            problems.append(f"Could not read manifest timestamp: {e}")

    # 2. Queue file writability
    try:
        QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        test_path = QUEUE_FILE.parent / ".sp-hk-write-test"
        test_path.write_text("ok")
        test_path.unlink()
    except Exception as e:
        problems.append(f"Queue write path is not writable: {e}")

    # 3. Token file existence
    if not TOKEN_FILE.exists():
        candidates_str = ", ".join(str(c) for c in _TOKEN_CANDIDATES)
        problems.append(
            f"Assistant token file not found (checked: {candidates_str}) — run /ms-reauth"
        )

    return problems


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="SharePoint CRM housekeeping sweep",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--mode",  default="execute",
                   choices=["execute", "dry-run"],
                   help="execute: queue safe changes; dry-run: propose only (default: execute)")
    p.add_argument("--scope", default="all",
                   help="all | accounts | opportunities | entity:<name>  (default: all)")
    p.add_argument("--sync",  action="store_true",
                   help="Process immediately via sync API (no batch, instant results)")
    args = p.parse_args()

    _load_dotenv()
    log(f"SharePoint housekeeping starting — mode={args.mode} scope={args.scope} sync={args.sync}")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        msg = "ANTHROPIC_API_KEY not set in .env — cannot run housekeeping sweep"
        log_err(msg)
        _send_telegram(f"❌ *SharePoint Housekeeping blocked*\n{msg}")
        sys.exit(1)

    # ── Degraded-state check — bail entirely rather than partial noisy attempt ─
    problems = _check_degraded_state()
    if problems:
        problem_lines = "\n".join(f"• {p}" for p in problems)
        log_err(f"Housekeeping blocked — degraded state detected:\n{problem_lines}")
        _send_telegram(
            f"❌ *SharePoint Housekeeping blocked — degraded state*\n\n"
            f"{problem_lines}\n\n"
            f"_Resolve the above and retry._"
        )
        sys.exit(1)

    state = load_state()

    # ── Phase 1: Collect any completed batches ────────────────────────────────
    if not args.sync:
        processed = process_pending_batches(state, args.mode, args.scope)
        save_state(state)
        if processed > 0:
            log(f"Collected results for {processed} entities. Done.")
            return

    # ── Phase 2: Discover entities to process ────────────────────────────────
    entities = discover_entities(args.scope)
    if not entities:
        log("No entities found for the given scope — nothing to do.")
        return

    # ── Phase 3a: Sync mode — process immediately ─────────────────────────────
    if args.sync:
        log(f"Sync mode: processing {len(entities)} entities immediately")
        results = process_sync(entities, args.mode)
        _write_report(results, args.mode)
        summary = _telegram_summary(results, args.mode, args.scope)
        _send_telegram(summary)
        log(summary.replace("*", "").replace("_", ""))
        state["last_run"] = ts()
        save_state(state)
        return

    # ── Phase 3b: Batch mode — build and submit Anthropic batch ──────────────
    log(f"Batch mode: building prompts for {len(entities)} entities")
    batch_requests = []
    entity_map: dict[str, dict] = {}

    for entity in entities:
        custom_id = f"entity-{entity['name'].replace(' ', '_').replace('/', '_')}"
        content   = _read_entity_content(entity)
        prompt    = _build_entity_prompt(entity, content)
        batch_requests.append({"custom_id": custom_id, "prompt": prompt})
        entity_map[custom_id] = entity

    batch_id = submit_anthropic_batch(batch_requests)
    if not batch_id:
        log_err("Batch submission failed. Try --sync for immediate processing.")
        sys.exit(1)

    state["pending_batches"].append({
        "batch_id":     batch_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "mode":         args.mode,
        "scope":        args.scope,
        "entity_map":   entity_map,
    })
    state["last_run"] = ts()
    save_state(state)

    _send_telegram(
        f"🧹 *SharePoint Housekeeping batch submitted*\n"
        f"{len(batch_requests)} entities queued for review.\n"
        f"Results will be processed on the next cron run (~1–24h).\n"
        f"Use `/sp-housekeep --sync` for immediate results."
    )
    log(f"Batch {batch_id} submitted for {len(batch_requests)} entities. "
        f"Results collected on next cron run.")


if __name__ == "__main__":
    main()
