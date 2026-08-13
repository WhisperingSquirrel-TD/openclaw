#!/usr/bin/env python3
"""
SharePoint write queue processor for OpenClaw.

Runs every 1 minute via cron. Reads ~/.openclaw/sharepoint-queue.json,
executes each pending operation via sharepoint.py, writes results to
SHAREPOINT_RESULT.md so L1 can see what happened — all without exec.run
or TOTP approval from L1's perspective.

ALL QUEUE OPERATIONS ARE EXEC-FREE FROM L1'S SIDE.
L1 queues work by writing JSON to sharepoint-queue.json (a plain file
write). The cron-based processor picks it up independently. No exec.run,
no TOTP gate — this applies equally to create/update/append, move, and
delete_folder.

READS ARE NOT HANDLED HERE.
Files are read from the local content mirror at:
  ~/.openclaw/workspace/sharepoint-cache/<SP-path>
The sharepoint_cache_poller.py keeps that mirror fresh (every 15 min).
The AI reads from local files directly — no queue entry needed.

QUEUE FORMAT (~/.openclaw/sharepoint-queue.json)
-------------------------------------------------
L1 writes queue entries directly as file writes (no exec/TOTP needed):

[
  {
    "id": "unique-id",
    "operation": "create" | "update" | "append",
    "path": "/Stackstone CRM/Opportunities/Harken Health.md",
    "content": "Markdown content to write",
    "requested_at": "2026-04-09T10:00:00Z"
  },
  {
    "id": "unique-id",
    "operation": "move",
    "path": "/Stackstone CRM/Andy Barrett - SJP/raw-transcript.docx",
    "destination": "/Stackstone CRM/Andy Barrett - SJP/Archive/raw-transcript.docx",
    "requested_at": "2026-04-09T10:00:00Z"
  }
]

RESULT FILE (~/.openclaw/workspace/SHAREPOINT_RESULT.md)
---------------------------------------------------------
After processing, write results are recorded here so L1 can confirm
that its writes succeeded or see error details.

CRON SCHEDULE: every 1 minute (installed by install-forked-openclaw.sh)
"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR   = Path.home() / ".openclaw"
WORKSPACE   = STATE_DIR / "workspace"
QUEUE_FILE  = STATE_DIR / "sharepoint-queue.json"
RESULT_MD   = WORKSPACE / "SHAREPOINT_RESULT.md"
LOCK_FILE   = STATE_DIR / "integrations/microsoft/sp-queue.lock"
LOG_FILE    = STATE_DIR / "integrations/microsoft/sp-queue-processor.log"
SP_SCRIPT   = STATE_DIR / "integrations/microsoft-l1/sharepoint.py"
LOG_MAX     = 500

WRITE_OPERATIONS         = {"create", "update", "append"}
MOVE_OPERATIONS          = {"move"}           # relocate/rename, no delete permission
FOLDER_DELETE_OPERATIONS = {"delete_folder"}  # empty folders only — files never deleted
READ_OPERATIONS          = {"read_binary"}    # on-demand binary extraction

# OpenClaw skill assets are governed separately by the versioned skill-library
# publisher. The generic SharePoint queue must never create, update, move or
# delete them, even if an upstream worker is compromised or misconfigured.
PROTECTED_ROOTS = frozenset({"skills"})


def _queue_path_allowed(path: str) -> tuple[bool, str]:
    clean = str(path or "").strip().lstrip("/")
    if not clean:
        return False, "Missing path"
    parts = Path(clean).parts
    if not parts or ".." in parts:
        return False, "Unsafe SharePoint path"
    if parts[0].lower() in PROTECTED_ROOTS:
        return False, "Protected SharePoint root 'skills' is managed only by the versioned skill publisher"
    return True, ""

# Binary extractor — same directory as this script
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
try:
    from sharepoint_binary_extractor import extract_text as _extract_binary_text  # type: ignore
except ImportError:
    _extract_binary_text = None  # type: ignore


# ---------------------------------------------------------------------------
# Env / .env loader
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

_load_dotenv()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with LOG_FILE.open("a") as fh:
            fh.write(line)
        _trim_log()
    except OSError:
        pass
    print(line, end="")


def _trim_log() -> None:
    try:
        lines = LOG_FILE.read_text().splitlines()
        if len(lines) > LOG_MAX:
            LOG_FILE.write_text("\n".join(lines[-LOG_MAX:]) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Lock (prevent concurrent runs)
# ---------------------------------------------------------------------------

class _Lock:
    def __enter__(self):
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        if LOCK_FILE.exists():
            age = datetime.now().timestamp() - LOCK_FILE.stat().st_mtime
            if age < 120:
                raise RuntimeError(f"Lock held ({age:.0f}s old) — another run in progress")
            LOCK_FILE.unlink(missing_ok=True)
        LOCK_FILE.write_text(str(os.getpid()))
        return self

    def __exit__(self, *_):
        LOCK_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Queue read / write
# ---------------------------------------------------------------------------

def _read_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    try:
        raw = QUEUE_FILE.read_text().strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except (json.JSONDecodeError, OSError) as e:
        log(f"WARN: Could not read queue file: {e}")
    return []


def _write_queue(items: list[dict]) -> None:
    tmp = QUEUE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(items, indent=2))
        tmp.replace(QUEUE_FILE)
    except OSError as e:
        log(f"ERROR: Could not write queue: {e}")
        tmp.unlink(missing_ok=True)


def _clear_queue() -> None:
    QUEUE_FILE.write_text("[]")


# ---------------------------------------------------------------------------
# Token refresh + binary fetch (mirrors sharepoint_cache_poller.py)
# ---------------------------------------------------------------------------

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _get_sp_access_token() -> tuple[str, str, str]:
    """Return (access_token, site_id, drive_id) for binary reads."""
    import requests as _req

    candidates = [
        STATE_DIR / "integrations/microsoft/token-assistant.json",
        STATE_DIR / "integrations/microsoft-l1/token.json",
        STATE_DIR / "integrations/microsoft/token-assistant.json",
    ]
    token_file = next((c for c in candidates if c.exists()), None)
    if not token_file:
        raise RuntimeError(
            "No assistant@ token found. Run:\n"
            "  python3 ~/.openclaw/integrations/microsoft-l1/sharepoint.py reauth"
        )

    raw  = token_file.read_text()
    data = json.loads(raw)
    if "RefreshToken" in data and "AccessToken" in data:
        at_list  = list(data.get("AccessToken",  {}).values())
        rt_list  = list(data.get("RefreshToken", {}).values())
        app_list = list(data.get("AppMetadata",  {}).values())
        at  = at_list[0]  if at_list  else {}
        rt  = rt_list[0]
        app = app_list[0] if app_list else {}
        data = {
            "client_id":     at.get("client_id") or app.get("client_id", ""),
            "client_secret": "",
            "tenant_id":     at.get("realm", "common"),
            "refresh_token": rt["secret"],
            "access_token":  at.get("secret", ""),
        }

    tenant = data.get("tenant_id", "common")
    resp = _req.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id":     data["client_id"],
            "refresh_token": data["refresh_token"],
            "grant_type":    "refresh_token",
            "scope":         "Files.ReadWrite Sites.ReadWrite.All offline_access",
        },
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text[:300]}")

    new_tok = resp.json()
    access_token = new_tok["access_token"]

    host       = os.environ.get("SHAREPOINT_HOST",       "seerepeat.sharepoint.com").strip()
    site_path  = os.environ.get("SHAREPOINT_SITE_PATH",  "/sites/StackstoneConsulting").strip()
    drive_name = os.environ.get("SHAREPOINT_DRIVE_NAME", "Documents").strip()

    hdrs = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    site_resp = _req.get(f"{GRAPH_BASE}/sites/{host}:{site_path}", headers=hdrs, timeout=15)
    if not site_resp.ok:
        raise RuntimeError(f"Site lookup failed ({site_resp.status_code})")
    site_id = site_resp.json()["id"]

    drives_resp = _req.get(f"{GRAPH_BASE}/sites/{site_id}/drives", headers=hdrs, timeout=15)
    drives = drives_resp.json().get("value", [])
    drive_id = next(
        (d["id"] for d in drives if d.get("name", "").lower() == drive_name.lower()),
        drives[0]["id"] if drives else None,
    )
    if not drive_id:
        raise RuntimeError("No drives found on SharePoint site")

    return access_token, site_id, drive_id


def _fetch_binary_bytes(access_token: str, site_id: str, drive_id: str, sp_path: str) -> bytes:
    import requests as _req
    clean = sp_path.strip("/")
    url   = f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{clean}:/content"
    resp  = _req.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
        allow_redirects=True,
    )
    if not resp.ok:
        raise RuntimeError(f"Binary fetch failed ({resp.status_code}): {resp.text[:200]}")
    return resp.content


# ---------------------------------------------------------------------------
# Execute a single read_binary operation
# ---------------------------------------------------------------------------

CACHE_DIR = STATE_DIR / "workspace" / "sharepoint-cache"
WORKSPACE = STATE_DIR / "workspace"


def _run_read_binary_operation(op: dict) -> tuple[bool, str]:
    """Download and extract a binary SharePoint file into the local cache."""
    sp_path = op.get("path", "").strip()
    if not sp_path:
        return False, "Missing 'path' field"

    if _extract_binary_text is None:
        return False, (
            "sharepoint_binary_extractor is not installed. "
            "Run: pip3 install --break-system-packages python-docx pdfminer.six python-pptx extract-msg"
        )

    filename      = Path(sp_path).name
    rel_path      = sp_path.strip("/")
    extracted_rel = rel_path + ".extracted.md"
    local_path    = CACHE_DIR / extracted_rel
    image_dir     = local_path.parent / (Path(filename).stem + ".images")

    try:
        access_token, site_id, drive_id = _get_sp_access_token()
        raw_bytes = _fetch_binary_bytes(access_token, site_id, drive_id, sp_path)
    except Exception as e:
        return False, f"Download failed: {e}"

    extracted_text = _extract_binary_text(filename, raw_bytes, image_dir=image_dir)

    now    = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = f"<!-- sharepoint-binary-extract: {sp_path} | synced: {now} -->\n\n"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(header + extracted_text, encoding="utf-8")

    return True, (
        f"Extracted to: sharepoint-cache/{extracted_rel}\n"
        f"Read it with: cat ~/.openclaw/workspace/sharepoint-cache/{extracted_rel}"
    )


# ---------------------------------------------------------------------------
# Execute a single SharePoint delete_folder operation
# ---------------------------------------------------------------------------

def _run_delete_folder_operation(op: dict) -> tuple[bool, str]:
    """Execute one delete_folder queue entry. Returns (success, output_text).

    sharepoint.py enforces the empty-folder safety check server-side — if the
    folder has any contents the Graph call is refused before any DELETE is sent.
    """
    sp_path = op.get("path", "").strip()

    if not sp_path:
        return False, "Missing 'path' field"
    if not SP_SCRIPT.exists():
        return False, f"sharepoint.py not found at {SP_SCRIPT}"

    cmd = ["python3", str(SP_SCRIPT), "delete_folder", sp_path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output  = (result.stdout + result.stderr).strip()
        success = result.returncode == 0
        return success, output
    except subprocess.TimeoutExpired:
        return False, "Timed out after 30 seconds"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Execute a single SharePoint move operation
# ---------------------------------------------------------------------------

def _run_move_operation(op: dict) -> tuple[bool, str]:
    """Execute one move queue entry. Returns (success, output_text)."""
    sp_path     = op.get("path", "").strip()
    destination = op.get("destination", "").strip()

    if not sp_path:
        return False, "Missing 'path' field"
    if not destination:
        return False, "Missing 'destination' field for move operation"
    if not SP_SCRIPT.exists():
        return False, f"sharepoint.py not found at {SP_SCRIPT}"

    cmd = ["python3", str(SP_SCRIPT), "move", sp_path, "--destination", destination]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output  = (result.stdout + result.stderr).strip()
        success = result.returncode == 0
        return success, output
    except subprocess.TimeoutExpired:
        return False, "Timed out after 60 seconds"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Execute a single SharePoint write operation
# ---------------------------------------------------------------------------

def _run_write_operation(op: dict) -> tuple[bool, str]:
    """Execute one write queue entry. Returns (success, output_text)."""
    operation = op.get("operation", "").lower()
    sp_path   = op.get("path", "").strip()
    content   = op.get("content", "")

    if operation not in WRITE_OPERATIONS:
        return False, (
            f"Operation '{operation}' is not a write operation. "
            f"Reads are handled via the local SharePoint cache — "
            f"read ~/.openclaw/workspace/sharepoint-cache/<path> directly."
        )
    if not sp_path:
        return False, "Missing 'path' field"
    if not SP_SCRIPT.exists():
        return False, f"sharepoint.py not found at {SP_SCRIPT}"
    if not content:
        return False, f"Operation '{operation}' requires 'content' field"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="oc-sp-content-",
        delete=False, dir="/tmp",
    ) as tf:
        tf.write(content)
        content_file = tf.name

    cmd = ["python3", str(SP_SCRIPT), operation, sp_path, "--content-file", content_file]
    if operation == "create" and op.get("allow_overwrite"):
        cmd += ["--allow-overwrite"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output  = (result.stdout + result.stderr).strip()
        success = result.returncode == 0
        return success, output
    except subprocess.TimeoutExpired:
        return False, "Timed out after 60 seconds"
    except Exception as e:
        return False, str(e)
    finally:
        try:
            Path(content_file).unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Write SHAREPOINT_RESULT.md (write results only)
# ---------------------------------------------------------------------------

def _write_results(results: list[dict]) -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# SharePoint Write Results",
        "",
        f"_Last processed: {now}_",
        "",
        "> This file shows write and move operation results (create/update/append/move).",
        "> To read SharePoint files, use the local cache:",
        "> `~/.openclaw/workspace/sharepoint-cache/<SP-path>`",
        "",
    ]

    for r in results:
        op      = r.get("operation", "?")
        path    = r.get("path", "?")
        ok      = r.get("success", False)
        output  = r.get("output", "")
        icon    = "✅" if ok else "❌"
        ts      = r.get("requested_at", "")[:19].replace("T", " ")

        lines += [
            f"## {icon} `{op.upper()}` — `{path}`",
            f"_Requested: {ts}_",
            "",
        ]
        if output:
            lines += [
                "```",
                output[:2000],
                "```",
                "",
            ]

    lines.append("_Results written by sharepoint_queue_processor.py_")
    RESULT_MD.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    queue = _read_queue()
    if not queue:
        return

    log(f"Queue processor starting — {len(queue)} item(s) to process")

    try:
        with _Lock():
            results   = []
            rejected  = []

            for op in queue:
                op_id      = op.get("id", str(uuid.uuid4())[:8])
                op_name    = op.get("operation", "?")
                path       = op.get("path", "?")
                log(f"Processing [{op_id}] {op_name.upper()} {path}")

                op_lower = op_name.lower()
                allowed, rejection = _queue_path_allowed(path)
                if op_lower == "move":
                    dest_allowed, dest_rejection = _queue_path_allowed(op.get("destination", ""))
                    if not dest_allowed:
                        allowed, rejection = False, f"Unsafe move destination: {dest_rejection}"
                if not allowed:
                    log(f"  REJECTED: {rejection}")
                    rejected.append(op_id)
                    results.append({
                        "id": op_id, "operation": op_name, "path": path,
                        "success": False, "output": rejection,
                        "requested_at": op.get("requested_at", ""),
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    continue

                if op_lower in READ_OPERATIONS:
                    success, output = _run_read_binary_operation(op)
                elif op_lower in WRITE_OPERATIONS:
                    success, output = _run_write_operation(op)
                elif op_lower in MOVE_OPERATIONS:
                    success, output = _run_move_operation(op)
                elif op_lower in FOLDER_DELETE_OPERATIONS:
                    success, output = _run_delete_folder_operation(op)
                else:
                    msg = (
                        f"Unknown operation '{op_name}'. "
                        f"Write operations: {', '.join(sorted(WRITE_OPERATIONS))}. "
                        f"Move operations: {', '.join(sorted(MOVE_OPERATIONS))}. "
                        f"Folder delete: {', '.join(sorted(FOLDER_DELETE_OPERATIONS))}. "
                        f"Read operations: {', '.join(sorted(READ_OPERATIONS))}. "
                        f"For plain text files, read directly from "
                        f"~/.openclaw/workspace/sharepoint-cache/<path>."
                    )
                    log(f"  REJECTED: {msg}")
                    rejected.append(op_id)
                    results.append({
                        "id": op_id, "operation": op_name, "path": path,
                        "success": False, "output": msg,
                        "requested_at": op.get("requested_at", ""),
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    continue

                status = "OK" if success else "FAILED"
                log(f"  → {status}: {output[:120]}")

                results.append({
                    "id":           op_id,
                    "operation":    op_name,
                    "path":         path,
                    "success":      success,
                    "output":       output,
                    "requested_at": op.get("requested_at", ""),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                })

            _clear_queue()
            _write_results(results)
            ok_count   = sum(1 for r in results if r["success"])
            fail_count = len(results) - ok_count
            log(f"Done — {ok_count} succeeded, {fail_count} failed. Results in SHAREPOINT_RESULT.md")

    except RuntimeError as e:
        log(f"Skipped: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
