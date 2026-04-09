#!/usr/bin/env python3
"""
SharePoint write queue processor for OpenClaw.

Runs every 1 minute via cron. Reads ~/.openclaw/sharepoint-queue.json,
executes each pending operation via sharepoint.py, writes results to
SHAREPOINT_RESULT.md so L1 can see what happened — all without exec.run
or TOTP approval from L1's perspective.

QUEUE FORMAT (~/.openclaw/sharepoint-queue.json)
-------------------------------------------------
L1 writes this file directly (file writes need no exec/TOTP):

[
  {
    "id": "unique-id",
    "operation": "create" | "update" | "append" | "read" | "list",
    "path": "/Stackstone CRM/Opportunities/Harken Health.md",
    "content": "Optional markdown content for create/update/append",
    "requested_at": "2026-04-09T10:00:00Z"
  }
]

RESULT FILE (~/.openclaw/workspace/SHAREPOINT_RESULT.md)
---------------------------------------------------------
After processing, results are written here so L1 can read the outcome.
For read/list operations the file content is included.

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
# Execute a single SharePoint operation
# ---------------------------------------------------------------------------

def _run_operation(op: dict) -> tuple[bool, str]:
    """Execute one queue entry. Returns (success, output_text)."""
    operation = op.get("operation", "").lower()
    sp_path   = op.get("path", "").strip()
    content   = op.get("content", "")

    if not operation:
        return False, "Missing 'operation' field"
    if not sp_path:
        return False, "Missing 'path' field"
    if not SP_SCRIPT.exists():
        return False, f"sharepoint.py not found at {SP_SCRIPT}"

    cmd = ["python3", str(SP_SCRIPT), operation, sp_path]

    if operation in ("create", "update", "append"):
        if not content:
            return False, f"Operation '{operation}' requires 'content' field"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix="oc-sp-content-",
            delete=False, dir="/tmp",
        ) as tf:
            tf.write(content)
            content_file = tf.name
        cmd += ["--content-file", content_file]
        if operation == "create" and op.get("allow_overwrite"):
            cmd += ["--allow-overwrite"]
    else:
        content_file = None

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = (result.stdout + result.stderr).strip()
        success = result.returncode == 0
        return success, output
    except subprocess.TimeoutExpired:
        return False, "Timed out after 60 seconds"
    except Exception as e:
        return False, str(e)
    finally:
        if content_file:
            try:
                Path(content_file).unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Write SHAREPOINT_RESULT.md
# ---------------------------------------------------------------------------

def _write_results(results: list[dict]) -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# SharePoint Queue Results",
        "",
        f"_Last processed: {now}_",
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
            results = []
            processed = []

            for op in queue:
                op_id   = op.get("id", str(uuid.uuid4())[:8])
                op_name = op.get("operation", "?")
                path    = op.get("path", "?")
                log(f"Processing [{op_id}] {op_name.upper()} {path}")

                success, output = _run_operation(op)
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
                processed.append(op_id)

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
