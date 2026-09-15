#!/usr/bin/env python3
"""
SharePoint write queue processor for OpenClaw.

Runs every 1 minute via cron. Reads ~/.openclaw/sharepoint-queue.json,
executes each pending operation via sharepoint.py, writes results to
SHAREPOINT_RESULT.md so L1 can see what happened — all without exec.run
or TOTP approval from L1's perspective.

ALL QUEUE OPERATIONS ARE EXEC-FREE FROM L1'S SIDE.
L1 submits complete operation objects through ``enqueue_operation``.  That
producer owns the queue lock and atomic publication; agents must never edit
sharepoint-queue.json directly.  The cron-based processor picks entries up
independently. No exec.run or TOTP gate is required for bounded operations.

READS ARE NOT HANDLED HERE.
Files are read from the local content mirror at:
  ~/.openclaw/workspace/sharepoint-cache/<SP-path>
The sharepoint_cache_poller.py keeps that mirror fresh (every 15 min).
The AI reads from local files directly — no queue entry needed.

PRODUCER PAYLOAD FORMAT
-------------------------------------------------
L1 passes each complete object to ``enqueue_operation`` (no exec/TOTP needed):

[
  {
    "id": "unique-id",
    "operation": "create" | "update" | "append" | "update_workbook",
    "path": "/Stackstone CRM/Opportunities/Harken Health.md",
    "content": "Markdown content to write",
    "base_etag": "\"{current-version}\"",  # required for authoritative ledgers
    "expected_source_sha256": "<sha256 of content read before update>",
    "content_sha256": "<sha256 of the exact queued replacement content>",
    "requested_at": "2026-04-09T10:00:00Z"
  },
  {
    "id": "unique-workbook-id",
    "operation": "update_workbook",
    "path": "/Finance/Finance ledger.xlsx",
    "content_base64": "<base64 of exact XLSX bytes>",
    "content_sha256": "<sha256 of those exact bytes>",
    "base_etag": "\"{current-version}\"",
    "expected_source_sha256": "<sha256 of exact XLSX bytes read before update>",
    "semantic_sha256": "<sha256 of workbook cells/tables>",
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
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR   = Path.home() / ".openclaw"
WORKSPACE   = STATE_DIR / "workspace"
QUEUE_FILE  = STATE_DIR / "sharepoint-queue.json"
RESULT_MD   = WORKSPACE / "SHAREPOINT_RESULT.md"
RESULT_JSON = STATE_DIR / "sharepoint-queue-results.json"
LOCK_FILE   = STATE_DIR / "integrations/microsoft/sp-queue.lock"
LOG_FILE    = STATE_DIR / "integrations/microsoft/sp-queue-processor.log"
SP_SCRIPT   = STATE_DIR / "integrations/microsoft-l1/sharepoint.py"
LOG_MAX     = 500

WRITE_OPERATIONS         = {"create", "update", "append", "update_workbook"}
SKILL_RELEASE_OPERATIONS = {"publish_skill"}  # audited in-place canonical skill publisher
MOVE_OPERATIONS          = {"move"}           # relocate/rename, no delete permission
FOLDER_DELETE_OPERATIONS = {"delete_folder"}  # empty folders only — files never deleted
READ_OPERATIONS          = {"read_binary"}    # on-demand binary extraction
BINARY_UPLOAD_OPERATIONS = {"upload_binary"}  # receipt originals, MIME preserved
AUTHORITATIVE_UPDATE_PATHS = frozenset({
    "expenses/expense ledger.md",
    "finance/finance ledger.md",
})

# OpenClaw skill assets are governed separately by the versioned skill-library
# publisher. The generic SharePoint queue must never create, update, move or
# delete them, even if an upstream worker is compromised or misconfigured.
PROTECTED_ROOTS = frozenset({"skills"})
SKILL_PUBLISHER = WORKSPACE / "scripts/publish_skill_release_to_sharepoint.py"
SKILL_ID_ALLOWLIST = frozenset({"workspace-skills", "openclaw-skills"})
_QUEUE_MUTEX = threading.Lock()


def _queue_path_allowed(path: str) -> tuple[bool, str]:
    clean = str(path or "").strip().lstrip("/")
    if not clean:
        return False, "Missing path"
    parts = Path(clean).parts
    if not parts or ".." in parts:
        return False, "Unsafe SharePoint path"
    if parts[0].lower() in PROTECTED_ROOTS:
        return False, "Protected SharePoint root 'skills' is managed only by the guarded publish_skill operation"
    return True, ""


def _is_authoritative_update_path(path: str) -> bool:
    return str(path or "").strip().strip("/").casefold() in AUTHORITATIVE_UPDATE_PATHS


def _workbook_semantic_field(op: dict) -> str:
    """Read the shared schema name plus the finance agent's legacy alias."""
    value = op.get("semantic_sha256")
    if value in (None, ""):
        value = op.get("semantic_workbook_sha256")
    return str(value or "").strip()


def _validate_update_protocol(op: dict) -> tuple[bool, str]:
    """Validate the queue-side optimistic concurrency contract."""
    operation = str(op.get("operation", "")).lower()
    if operation == "create" and _is_authoritative_update_path(op.get("path", "")):
        return False, (
            "Generic create is refused for authoritative ledger paths; "
            "use the seer-finance gated bootstrap mechanism"
        )
    if operation in {"create", "upload", "upload_binary"} and _is_canonical_workbook_path(
        op.get("path", "")
    ):
        return False, (
            "Generic create/upload is refused for canonical workbook paths; "
            "use the update_workbook operation"
        )
    if operation in {"update", "append"} and _is_canonical_workbook_path(
        op.get("path", "")
    ):
        return False, (
            "Generic update/append is refused for canonical workbook paths; "
            "use the update_workbook operation"
        )
    if operation == "update_workbook":
        if not _is_canonical_workbook_path(op.get("path", "")):
            return False, (
                "update_workbook is restricted to the canonical Expense and "
                "Finance workbook paths"
            )
        missing = [
            field
            for field in (
                "content_base64",
                "content_sha256",
                "base_etag",
                "expected_source_sha256",
            )
            if not str(op.get(field, "")).strip()
        ]
        if not _workbook_semantic_field(op):
            missing.append("semantic_sha256")
        if missing:
            return False, (
                "Canonical workbook update requires "
                + ", ".join(repr(field) for field in missing)
                + "; re-read the workbook and retry from its current version"
            )
        for field in (
            "content_sha256",
            "expected_source_sha256",
        ):
            if not _is_sha256(op.get(field)):
                return False, f"{field} must be a SHA-256 hex digest"
        if not _is_sha256(_workbook_semantic_field(op)):
            return False, "semantic_sha256 must be a SHA-256 hex digest"
        return True, ""
    if operation not in {"update", "append"}:
        return True, ""
    if _is_authoritative_update_path(op.get("path", "")):
        missing = []
        if not str(op.get("base_etag", "")).strip():
            missing.append("'base_etag'")
        if not str(op.get("expected_source_sha256", "")).strip():
            missing.append("'expected_source_sha256'")
        if missing:
            return False, (
                "Authoritative ledger update/append requires "
                + " and ".join(missing)
                + "; re-read the ledger and retry from its current version"
            )
    expected_hash = str(op.get("expected_source_sha256", "")).strip().lower()
    if expected_hash and (
        len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash)
    ):
        return False, "expected_source_sha256 must be a SHA-256 hex digest"
    return True, ""


def _conflict_proof(output: str) -> dict | None:
    """Classify stale-base conflicts as terminal rebase-required failures."""
    text = str(output or "")
    lowered = text.casefold()
    # A malformed queue entry is terminal, but it is not evidence that the
    # remote document changed; callers should fix the request rather than
    # treating a missing protocol field as a rebase receipt.
    if "requires" in lowered and (
        "base_etag" in lowered or "expected_source_sha256" in lowered
    ):
        return None
    proof: dict | None = None
    if "source hash conflict" in lowered or "source_hash" in lowered:
        proof = {"kind": "source_hash_mismatch"}
    elif "base etag" in lowered or "base_etag" in lowered:
        proof = {"kind": "base_etag_mismatch"}
    elif re.search(r"(?<!\d)412(?!\d)", lowered):
        proof = {"kind": "remote_precondition_failed", "status": 412}
    elif re.search(r"(?<!\d)409(?!\d)", lowered):
        proof = {"kind": "remote_conflict", "status": 409}
    if proof is not None:
        # Keep the bounded CLI detail as machine-readable evidence without
        # requiring consumers to parse human log text.
        proof["message"] = text[:2000]
    return proof

# Binary extractor — same directory as this script
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
try:
    from sharepoint_binary_extractor import extract_text as _extract_binary_text  # type: ignore
except ImportError:
    _extract_binary_text = None  # type: ignore
from sharepoint_workbook import (  # type: ignore
    is_canonical_workbook_path as _is_canonical_workbook_path,
    is_sha256 as _is_sha256,
    semantic_sha256 as _workbook_semantic_sha256,
)


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
    def __init__(self, blocking: bool = False):
        self.blocking = blocking
        self._fd = None

    def __enter__(self):
        # The lock file is deliberately independent of TOTP/exec.  flock
        # closes the check-then-create race in the old sentinel-only lock,
        # while the process mutex also serialises threads in one interpreter.
        acquired = _QUEUE_MUTEX.acquire(blocking=self.blocking)
        if not acquired:
            raise RuntimeError("another queue operation is in progress")
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            import fcntl
            self._fd = LOCK_FILE.open("a+")
            flags = fcntl.LOCK_EX
            if not self.blocking:
                flags |= fcntl.LOCK_NB
            try:
                fcntl.flock(self._fd.fileno(), flags)
            except BlockingIOError:
                self._fd.close()
                self._fd = None
                raise RuntimeError("another queue operation is in progress")
            self._fd.seek(0)
            self._fd.truncate()
            self._fd.write(str(os.getpid()))
            self._fd.flush()
        except Exception:
            _QUEUE_MUTEX.release()
            raise
        return self

    def __exit__(self, *_):
        try:
            if self._fd is not None:
                import fcntl
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
                self._fd.close()
        finally:
            self._fd = None
            _QUEUE_MUTEX.release()


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


def enqueue_operation(operation: dict) -> bool:
    """Atomically append one queue operation without dropping producers.

    Queue writers normally have no TOTP/exec requirement.  This helper is the
    safe read/modify/write path for producers that run in the same process (or
    cooperate through the queue lock); existing IDs are idempotent.
    """
    if not isinstance(operation, dict):
        raise TypeError("SharePoint queue operation must be an object")
    operation = dict(operation)
    operation.setdefault("id", str(uuid.uuid4()))
    with _Lock(blocking=True):
        current = _read_queue()
        operation_id = str(operation["id"])
        if any(str(item.get("id", "")) == operation_id for item in current):
            return False
        _write_queue(current + [operation])
    return True


# A descriptive alias for callers that prefer queue-oriented naming.
enqueue = enqueue_operation


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
# Execute a guarded canonical skill publish operation
# ---------------------------------------------------------------------------

def _run_skill_publish_operation(op: dict) -> tuple[bool, str]:
    """Publish one existing canonical skill in place via the no-TOTP queue.

    The publisher verifies the manifest/hash baseline before overwrite and
    re-reads hashes/eTags afterwards. It never creates another skill folder.
    """
    skill_id = str(op.get("skill_id", "")).strip()
    summary = str(op.get("summary", "")).strip()
    source, sep, name = skill_id.partition(":")
    if not sep or source not in SKILL_ID_ALLOWLIST or not name or "/" in name or ".." in name:
        return False, "publish_skill requires allowlisted skill_id '<source>:<skill-name>'"
    if not summary:
        return False, "publish_skill requires a non-empty change summary"
    if not SKILL_PUBLISHER.exists():
        return False, f"Skill publisher not found at {SKILL_PUBLISHER}"
    try:
        result = subprocess.run(
            ["python3", str(SKILL_PUBLISHER), skill_id, "--summary", summary],
            capture_output=True, text=True, timeout=180,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Timed out after 180 seconds"
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Execute immutable binary uploads (used by the receipt evidence chain)
# ---------------------------------------------------------------------------

def _run_binary_upload_operation(op: dict) -> tuple[bool, str]:
    sp_path = str(op.get("path", "")).strip()
    source_path = Path(str(op.get("source_path", "")).strip())
    mime_type = str(op.get("mime_type", "")).strip()
    if not sp_path or not source_path or not mime_type:
        return False, "upload_binary requires path, source_path and mime_type"
    if not source_path.is_file():
        return False, f"Original binary unavailable: {source_path}"
    expected_hash = str(op.get("content_sha256", "")).strip().lower()
    if not _is_sha256(expected_hash):
        return False, "upload_binary requires a valid content_sha256"
    actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        return False, (
            "upload_binary content_sha256 does not match the original binary "
            f"(expected {expected_hash}, received {actual_hash})"
        )
    if not SP_SCRIPT.exists():
        return False, f"sharepoint.py not found at {SP_SCRIPT}"
    try:
        result = subprocess.run(
            ["python3", str(SP_SCRIPT), "upload", sp_path, "--content-file", str(source_path), "--mime-type", mime_type],
            capture_output=True, text=True, timeout=90,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return False, output
        try:
            proof = json.loads(output)
        except json.JSONDecodeError:
            return False, "receipt upload returned no machine-readable JSON proof"
        if (
            not isinstance(proof, dict)
            or proof.get("status") not in {"uploaded", "exists"}
            or proof.get("path") != sp_path
            or not isinstance(proof.get("etag"), str)
            or not proof["etag"].strip()
            or proof.get("readback_sha256") != expected_hash
        ):
            return False, (
                "receipt upload proof must contain status uploaded/exists, "
                "the requested path, a resulting eTag, and a readback_sha256 "
                "matching the original binary"
            )
        return True, output
    except subprocess.TimeoutExpired:
        return False, "Timed out after 90 seconds"
    except Exception as exc:
        return False, str(exc)


def _run_workbook_update_operation(op: dict) -> tuple[bool, str]:
    """Execute a canonical XLSX update using the exact queued bytes."""
    import base64
    import binascii

    sp_path = str(op.get("path", "")).strip()
    allowed, rejection = _validate_update_protocol(op)
    if not allowed:
        return False, rejection
    try:
        content = base64.b64decode(
            str(op.get("content_base64", "")), validate=True
        )
    except (ValueError, binascii.Error) as exc:
        return False, f"content_base64 is not valid strict base64: {exc}"
    expected_content_hash = str(op.get("content_sha256", "")).strip().lower()
    actual_content_hash = hashlib.sha256(content).hexdigest()
    if actual_content_hash != expected_content_hash:
        return False, (
            "content_sha256 does not match the exact decoded XLSX bytes "
            f"(expected {expected_content_hash}, received {actual_content_hash})"
        )
    expected_semantic = _workbook_semantic_field(op).lower()
    try:
        actual_semantic = _workbook_semantic_sha256(content)
    except Exception as exc:
        return False, f"Invalid XLSX workbook payload: {exc}"
    if actual_semantic != expected_semantic:
        return False, (
            "semantic_sha256 does not match the queued workbook cells/tables "
            f"(expected {expected_semantic}, received {actual_semantic})"
        )
    if not SP_SCRIPT.exists():
        return False, f"sharepoint.py not found at {SP_SCRIPT}"

    content_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".xlsx",
            prefix="oc-sp-workbook-",
            delete=False,
            dir="/tmp",
        ) as tf:
            tf.write(content)
            tf.flush()
            content_file = tf.name

        cmd = [
            "python3",
            str(SP_SCRIPT),
            "update_workbook",
            sp_path,
            "--content-file",
            content_file,
            "--content-sha256",
            expected_content_hash,
            "--base-etag",
            str(op["base_etag"]),
            "--expected-source-sha256",
            str(op["expected_source_sha256"]),
            "--semantic-sha256",
            expected_semantic,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return False, output

        proof = _extract_write_proof(output)
        readback_hash = str(proof.get("readback_sha256", "")).strip().lower()
        resulting_etag = str(proof.get("resulting_etag", "")).strip()
        proof_semantic = str(
            proof.get("semantic_sha256")
            or proof.get("semantic_workbook_sha256")
            or proof.get("readback_semantic_workbook_sha256")
            or ""
        ).strip().lower()
        if (
            not _is_sha256(readback_hash)
            or not resulting_etag
            or proof_semantic != expected_semantic
        ):
            return False, (
                "ERROR: Canonical workbook write proof is missing or invalid; "
                "expected exact remote readback_sha256, resulting_etag and "
                f"semantic_sha256={expected_semantic}"
            )
        return True, output
    except subprocess.TimeoutExpired:
        return False, "Timed out after 90 seconds"
    except Exception as exc:
        return False, str(exc)
    finally:
        if content_file:
            try:
                Path(content_file).unlink(missing_ok=True)
            except OSError:
                pass


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
    protocol_allowed, protocol_rejection = _validate_update_protocol(op)
    if not protocol_allowed:
        return False, protocol_rejection
    if operation == "update_workbook":
        return _run_workbook_update_operation(op)
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
    if operation in {"update", "append"}:
        if op.get("base_etag"):
            cmd += ["--base-etag", str(op["base_etag"])]
        if op.get("expected_source_sha256"):
            cmd += ["--expected-source-sha256", str(op["expected_source_sha256"])]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output  = (result.stdout + result.stderr).strip()
        success = result.returncode == 0
        if success and (
            str(op.get("operation", "")).lower() in {"update", "append"}
            and _is_authoritative_update_path(op.get("path", ""))
        ):
            proof = _extract_write_proof(output)
            expected_hash = str(op.get("content_sha256", "")).strip()
            readback_hash = str(proof.get("readback_sha256", "")).strip()
            resulting_etag = str(proof.get("resulting_etag", "")).strip()
            sha_valid = (
                len(readback_hash) == 64
                and readback_hash == readback_hash.lower()
                and all(char in "0123456789abcdef" for char in readback_hash)
            )
            if (
                not resulting_etag
                or not sha_valid
                or not expected_hash
                or readback_hash != expected_hash
            ):
                return False, (
                    "ERROR: Authoritative write proof is missing or invalid; "
                    "expected SP_WRITE_PROOF with nonempty resulting_etag and "
                    f"readback_sha256 matching content_sha256 ({expected_hash or 'missing'})"
                )
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


def _extract_write_proof(output: str) -> dict:
    """Extract the CLI's final machine-readable write proof."""
    match = re.search(r"(?m)^SP_WRITE_PROOF:\s*(\{.*\})\s*$", output or "")
    if not match:
        return {}
    try:
        proof = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return proof if isinstance(proof, dict) else {}


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


def _write_results_json(results: list[dict]) -> None:
    """Persist bounded machine-readable delivery proof for asynchronous consumers."""
    prior: list[dict] = []
    try:
        loaded = json.loads(RESULT_JSON.read_text())
        prior = loaded if isinstance(loaded, list) else []
    except (OSError, json.JSONDecodeError):
        pass
    # Last result per queue ID is sufficient for idempotent receipt replay.
    merged = {str(item.get("id")): item for item in prior if isinstance(item, dict) and item.get("id")}
    for item in results:
        merged[str(item.get("id"))] = item
    bounded = sorted(merged.values(), key=lambda item: str(item.get("processed_at", "")))[-1000:]
    tmp = RESULT_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(bounded, indent=2, sort_keys=True))
    tmp.replace(RESULT_JSON)


def _successful_operation_ids() -> set[str]:
    """Return IDs already durably acknowledged by a prior successful run."""
    try:
        loaded = json.loads(RESULT_JSON.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(loaded, list):
        return set()
    return {
        str(item.get("id"))
        for item in loaded
        if isinstance(item, dict) and item.get("id") and item.get("success") is True
    }


def _pending_after_processing(original: list[dict], current: list[dict],
                              results: list[dict],
                              completed_ids: set[str] | None = None) -> list[dict]:
    """Merge retries with entries added while this batch was running.

    The processor owns only the entries it observed at batch start.  Reading
    the file again before replacing it prevents a producer that queued work
    during a slow Graph request from being erased by the retry write.
    """
    result_by_id = {str(item.get("id")): item for item in results if item.get("id")}
    completed_ids = completed_ids or set()
    pending: list[dict] = []
    seen: set[str] = set()

    # Failed original entries must remain available for retry.  This applies
    # to create/update/append as well as the other queue operations.
    for op in original:
        op_id = str(op.get("id", ""))
        if op_id in completed_ids:
            continue
        result = result_by_id.get(op_id)
        if result is None or (
            not result.get("success", False) and result.get("retryable", False)
        ):
            if op_id not in seen:
                pending.append(op)
                seen.add(op_id)

    # Preserve entries a producer added after the initial snapshot.  A
    # successful ID is intentionally omitted: operation IDs are idempotency
    # keys, so replaying that ID must not write twice.
    for op in current:
        op_id = str(op.get("id", ""))
        # IDs processed in this batch are represented by the original entry
        # above (only retryable failures are retained).  Do not re-add the
        # stale copy that a plain-file producer may have left in place.
        if op_id in completed_ids or op_id in result_by_id or op_id in seen:
            continue
        pending.append(op)
        seen.add(op_id)
    return pending


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        with _Lock():
            queue = _read_queue()
            if not queue:
                return

            log(f"Queue processor starting — {len(queue)} item(s) to process")
            results   = []
            seen_ids  = set()
            completed_ids = _successful_operation_ids()

            for op in queue:
                op_id      = op.get("id", str(uuid.uuid4())[:8])
                op_name    = op.get("operation", "?")
                path       = op.get("path", "?")
                op_id      = str(op_id)
                if not op.get("id"):
                    op["id"] = op_id
                log(f"Processing [{op_id}] {op_name.upper()} {path}")

                # A queue ID is an idempotency key.  This handles both
                # duplicate producer entries in one file and replay after a
                # successful prior processor run.
                if op_id in seen_ids or op_id in completed_ids:
                    log(f"  SKIPPED duplicate/completed operation ID {op_id}")
                    continue
                seen_ids.add(op_id)

                op_lower = op_name.lower()
                # Skills remain protected from generic paths; only the guarded
                # publish_skill operation can use the canonical skill publisher.
                if op_lower in SKILL_RELEASE_OPERATIONS:
                    allowed, rejection = True, ""
                else:
                    allowed, rejection = _queue_path_allowed(path)
                if op_lower == "move":
                    dest_allowed, dest_rejection = _queue_path_allowed(op.get("destination", ""))
                    if not dest_allowed:
                        allowed, rejection = False, f"Unsafe move destination: {dest_rejection}"
                if allowed:
                    protocol_allowed, protocol_rejection = _validate_update_protocol(op)
                    if not protocol_allowed:
                        allowed, rejection = False, protocol_rejection
                if not allowed:
                    log(f"  REJECTED: {rejection}")
                    conflict = _conflict_proof(rejection)
                    results.append({
                        "id": op_id, "operation": op_name, "path": path,
                        "success": False, "output": rejection,
                        "retryable": False,
                        **(
                            {
                                "error_code": "rebase_required",
                                "rebase_required": True,
                                "conflict": conflict,
                            }
                            if conflict else {}
                        ),
                        "requested_at": op.get("requested_at", ""),
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    continue

                if op_lower in SKILL_RELEASE_OPERATIONS:
                    success, output = _run_skill_publish_operation(op)
                elif op_lower in READ_OPERATIONS:
                    success, output = _run_read_binary_operation(op)
                elif op_lower in BINARY_UPLOAD_OPERATIONS:
                    success, output = _run_binary_upload_operation(op)
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
                        f"Skill publish: {', '.join(sorted(SKILL_RELEASE_OPERATIONS))}. "
                        f"Move operations: {', '.join(sorted(MOVE_OPERATIONS))}. "
                        f"Folder delete: {', '.join(sorted(FOLDER_DELETE_OPERATIONS))}. "
                        f"Read operations: {', '.join(sorted(READ_OPERATIONS))}. "
                        f"For plain text files, read directly from "
                        f"~/.openclaw/workspace/sharepoint-cache/<path>."
                    )
                    log(f"  REJECTED: {msg}")
                    results.append({
                        "id": op_id, "operation": op_name, "path": path,
                        "success": False, "output": msg,
                        "retryable": False,
                        "requested_at": op.get("requested_at", ""),
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    continue

                status = "OK" if success else "FAILED"
                log(f"  → {status}: {output[:120]}")
                conflict = _conflict_proof(output) if not success else None
                retryable = (
                    not success
                    and not conflict
                    and op_lower in (WRITE_OPERATIONS | BINARY_UPLOAD_OPERATIONS)
                )

                results.append({
                    "id":           op_id,
                    "operation":    op_name,
                    "path":         path,
                    "success":      success,
                    "output":       output,
                    "retryable":    retryable,
                    **(
                        {
                            "error_code": "rebase_required",
                            "rebase_required": True,
                            "conflict": conflict,
                        }
                        if conflict else {}
                    ),
                    **(
                        {
                            "etag": _extract_write_proof(output).get(
                                "etag", _extract_write_proof(output).get("resulting_etag")
                            ),
                            "resulting_etag": _extract_write_proof(output).get(
                                "resulting_etag", _extract_write_proof(output).get("etag")
                            ),
                            "readback_sha256": _extract_write_proof(output).get("readback_sha256"),
                            "semantic_sha256": _extract_write_proof(output).get("semantic_sha256"),
                            "semantic_workbook_sha256": _extract_write_proof(output).get(
                                "semantic_workbook_sha256",
                                _extract_write_proof(output).get("semantic_sha256"),
                            ),
                            "readback_semantic_workbook_sha256": _extract_write_proof(
                                output
                            ).get(
                                "readback_semantic_workbook_sha256",
                                _extract_write_proof(output).get("semantic_sha256"),
                            ),
                        }
                        if op_lower in WRITE_OPERATIONS and success else {}
                    ),
                    "requested_at": op.get("requested_at", ""),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "delivery":     op.get("delivery"),
                })

            # Re-read after Graph work so producers that queued entries while
            # this batch was running are merged, not overwritten.
            current_queue = _read_queue()
            retryable = _pending_after_processing(queue, current_queue, results, completed_ids)
            _write_queue(retryable)
            _write_results(results)
            _write_results_json(results)
            ok_count   = sum(1 for r in results if r["success"])
            fail_count = len(results) - ok_count
            log(f"Done — {ok_count} succeeded, {fail_count} failed. Results in SHAREPOINT_RESULT.md")

    except RuntimeError as e:
        log(f"Skipped: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
