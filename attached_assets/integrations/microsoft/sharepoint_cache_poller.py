#!/usr/bin/env python3
"""
SharePoint content mirror & cache poller for OpenClaw.

Runs every 15 minutes via cron. Does two things:
  1. Builds SHAREPOINT_INDEX.md — the full document tree (names, sizes, dates).
  2. Fetches full content of eligible files into a local mirror so the AI can
     read them instantly without any queue or wait.

LOCAL MIRROR
------------
~/.openclaw/workspace/sharepoint-cache/<SP-path>
  e.g. sharepoint-cache/Stackstone CRM/Opportunities/Croyde Medical.md

Each cached file has a sync-timestamp header so the AI always knows how fresh
the data is. A manifest JSON tracks every file — cached or skipped — so the
AI is never silently unaware of missing context.

ELIGIBILITY FOR CACHING
------------------------
  • File extension is .md or .txt
  • File size <= 500 KB  (SHAREPOINT_MAX_FILE_KB env var overrides)
  • Contained in a configured sync path  (SHAREPOINT_SYNC_PATHS env var,
    comma-separated, default = sync everything)

SKIPPED FILES
-------------
Files that are not eligible are recorded in the manifest and listed in a
dedicated section of SHAREPOINT_INDEX.md. The AI always knows what it is
missing and why.

ORPHAN CLEANUP
--------------
Local cache files with no matching SharePoint source are deleted automatically.

READS
-----
The AI reads from the local cache directly — no queue entry needed for reads.
The sharepoint_queue_processor.py handles writes (create/update/append) only.

CRON SCHEDULE: every 15 minutes (installed by install-forked-openclaw.sh)
"""

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

STATE_DIR   = Path.home() / ".openclaw"
WORKSPACE   = STATE_DIR / "workspace"
INDEX_MD    = WORKSPACE / "SHAREPOINT_INDEX.md"
CACHE_DIR   = WORKSPACE / "sharepoint-cache"
MANIFEST    = CACHE_DIR / ".manifest.json"
LOG_FILE    = STATE_DIR / "integrations/microsoft/sp-cache-poller.log"
GRAPH_BASE  = "https://graph.microsoft.com/v1.0"
MAX_DISPLAY_DEPTH = 5   # Tree display in SHAREPOINT_INDEX.md — folders beyond this depth are summarised

CACHEABLE_EXTENSIONS   = {".md", ".txt"}
MAX_FILE_KB_DEFAULT    = 500

BINARY_MAX_FILE_KB_DEFAULT = 5000  # 5 MB — binaries larger than this are skipped

# Folders that should remain visible in SharePoint at the tree level but should
# not be recursively traversed for local content mirroring. These are typically
# dependency/build/cache folders that create a lot of low-value IO on the Pi.
EXCLUDED_PATH_SEGMENTS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    "coverage",
    ".turbo",
    ".cache",
    ".venv",
    "venv",
    "__pycache__",
}

# Binary extraction is imported lazily so the poller works even if the
# extractor module or its dependencies are not yet installed.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
try:
    from sharepoint_binary_extractor import (  # type: ignore
        extract_text as _extract_binary_text,
        EXTRACTABLE_EXTENSIONS as _EXTRACTABLE_EXTENSIONS,
    )
    EXTRACTABLE_EXTENSIONS: frozenset[str] = _EXTRACTABLE_EXTENSIONS
except ImportError:
    _extract_binary_text      = None        # type: ignore
    EXTRACTABLE_EXTENSIONS    = frozenset()


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
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with LOG_FILE.open("a") as fh:
            fh.write(line)
        _trim_log()
    except OSError:
        pass
    print(line, end="")


def _trim_log(max_lines: int = 1000) -> None:
    try:
        lines = LOG_FILE.read_text().splitlines()
        if len(lines) > max_lines:
            LOG_FILE.write_text("\n".join(lines[-max_lines:]) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Token helpers (mirrors sharepoint.py exactly)
# ---------------------------------------------------------------------------

REQUIRED_SCOPES = "Files.ReadWrite Sites.ReadWrite.All offline_access"


def _resolve_token_file() -> Path:
    candidates = [
        STATE_DIR / "integrations/microsoft/token-assistant.json",
        STATE_DIR / "integrations/microsoft-l1/token.json",
        STATE_DIR / "integrations/microsoft-assistant/token.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        "No assistant@ token found. Run:\n"
        "  python3 ~/.openclaw/integrations/microsoft-l1/sharepoint.py reauth"
    )


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _load_json_resilient(path: Path) -> dict:
    raw = path.read_text()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(raw.strip())
            if isinstance(data, dict):
                _write_atomic(path, data)
                return data
        except json.JSONDecodeError:
            pass
        raise ValueError(f"Token file unreadable: {path}")


def _get_access_token() -> str:
    token_file = _resolve_token_file()
    data = _load_json_resilient(token_file)

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
        _write_atomic(token_file, data)

    tenant = data.get("tenant_id", "common")
    body: dict = {
        "client_id":     data["client_id"],
        "refresh_token": data["refresh_token"],
        "grant_type":    "refresh_token",
        "scope":         REQUIRED_SCOPES,
    }
    if data.get("client_secret"):
        body["client_secret"] = data["client_secret"]

    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data=body, timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text[:300]}")

    new = resp.json()
    data["access_token"]  = new["access_token"]
    data["refresh_token"] = new.get("refresh_token", data["refresh_token"])
    _write_atomic(token_file, data)
    return data["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# SharePoint site / drive resolution
# ---------------------------------------------------------------------------

def _resolve_site_and_drive(token: str) -> tuple[str, str]:
    host       = os.environ.get("SHAREPOINT_HOST",       "seerepeat.sharepoint.com").strip()
    site_path  = os.environ.get("SHAREPOINT_SITE_PATH",  "/sites/StackstoneConsulting").strip()
    drive_name = os.environ.get("SHAREPOINT_DRIVE_NAME", "Documents").strip()

    site_resp = requests.get(
        f"{GRAPH_BASE}/sites/{host}:{site_path}",
        headers=_headers(token), timeout=15,
    )
    if not site_resp.ok:
        raise RuntimeError(f"Site lookup failed ({site_resp.status_code}): {site_resp.text[:300]}")
    site_id = site_resp.json()["id"]

    drives_resp = requests.get(
        f"{GRAPH_BASE}/sites/{site_id}/drives",
        headers=_headers(token), timeout=15,
    )
    if not drives_resp.ok:
        raise RuntimeError(f"Drive listing failed ({drives_resp.status_code})")

    drives = drives_resp.json().get("value", [])
    for d in drives:
        if d.get("name", "").lower() == drive_name.lower():
            return site_id, d["id"]

    if drives:
        return site_id, drives[0]["id"]
    raise RuntimeError("No drives found on SharePoint site")


# ---------------------------------------------------------------------------
# Recursive folder listing — returns tree lines AND flat file list
# ---------------------------------------------------------------------------

def _list_children(token: str, site_id: str, drive_id: str, path: str) -> list[dict]:
    """List immediate children of a SharePoint folder path.

    Returns [] only for genuine 404 (folder does not exist).
    Raises RuntimeError for all other API failures so callers can detect
    partial enumeration and gate orphan cleanup accordingly.
    """
    clean = path.strip("/")
    if clean:
        url = f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{clean}:/children"
    else:
        url = f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root/children"

    items = []
    while url:
        resp = requests.get(url, headers=_headers(token), timeout=15)
        if resp.status_code == 404:
            return []
        if not resp.ok:
            raise RuntimeError(
                f"Graph listing failed for '{path}' "
                f"({resp.status_code}): {resp.text[:200]}"
            )
        data = resp.json()
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return items


def _collect_all_files(
    token: str, site_id: str, drive_id: str,
    path: str, all_files: list[dict],
) -> None:
    """Recursively enumerate every file in the drive with no depth limit.

    All files are collected regardless of type, size, or sync-path filter —
    filtering happens in the sync loop so every file is represented in the
    manifest or index (either cached or skipped with an explicit reason).
    """
    children = _list_children(token, site_id, drive_id, path)
    for item in children:
        name    = item.get("name", "(unknown)")
        is_dir  = "folder" in item
        sp_path = (path.rstrip("/") + "/" + name).lstrip("/")

        if _has_excluded_path_segment(sp_path):
            continue

        if is_dir:
            _collect_all_files(token, site_id, drive_id, sp_path, all_files)
        else:
            all_files.append({
                "name":     name,
                "sp_path":  sp_path,
                "size":     item.get("size", 0),
                "modified": item.get("lastModifiedDateTime", ""),
                "item_id":  item.get("id", ""),
                "etag":     item.get("eTag") or item.get("@odata.etag", ""),
                # Graph's cTag is the content-version identity.  Item ID is
                # a conservative fallback for tenants that omit cTag.
                # cTag is the content-version identity.  Do not fall back to
                # the drive item ID: it remains stable across content
                # replacements and cannot prove that cached bytes are current.
                "version":  item.get("cTag") or item.get("ctag") or "",
            })


def _build_display_tree(
    token: str, site_id: str, drive_id: str,
    path: str, depth: int, lines: list[str], indent: str,
) -> None:
    """Build the visual document tree for SHAREPOINT_INDEX.md.

    Display is capped at MAX_DISPLAY_DEPTH for readability. File collection
    for caching/reporting is done separately via _collect_all_files so the
    depth cap never prevents files from being discovered.
    """
    if depth > MAX_DISPLAY_DEPTH:
        lines.append(f"{indent}  _(deeper contents cached but not shown — see manifest)_")
        return

    children = _list_children(token, site_id, drive_id, path)
    children.sort(key=lambda x: (0 if "folder" in x else 1, x.get("name", "").lower()))

    for item in children:
        name     = item.get("name", "(unknown)")
        is_dir   = "folder" in item
        modified = item.get("lastModifiedDateTime", "")[:10]
        size     = item.get("size", 0)
        sp_path  = (path.rstrip("/") + "/" + name).lstrip("/")

        if is_dir:
            child_count = item.get("folder", {}).get("childCount", "?")
            lines.append(f"{indent}- 📁 **{name}/** ({child_count} items)")
            _build_display_tree(
                token, site_id, drive_id,
                sp_path, depth + 1, lines, indent + "  ",
            )
        else:
            size_str = f"{size:,} bytes" if size else "empty"
            lines.append(f"{indent}- 📄 {name} — _{modified}, {size_str}_")


# ---------------------------------------------------------------------------
# Sync-path filtering
# ---------------------------------------------------------------------------

def _in_sync_paths(sp_path: str, sync_paths: list[str]) -> bool:
    """Return True if the file should be cached (matches a configured sync path).

    Matching is done at path-segment boundaries to prevent false matches.
    e.g. sync_path "Foo" matches "Foo/bar.md" but NOT "FooBar/baz.md".
    """
    if not sync_paths:
        return True
    sp_lower = sp_path.lower().lstrip("/")
    for raw in sync_paths:
        prefix = raw.lower().strip("/")
        # Exact match (file is in the root of the sync path folder itself)
        # or starts with the prefix followed by a path separator
        if sp_lower == prefix or sp_lower.startswith(prefix + "/"):
            return True
    return False


def _has_excluded_path_segment(sp_path: str) -> bool:
    """Return True if the SharePoint path contains a low-value technical folder.

    This preserves broad SharePoint visibility while avoiding recursive mirroring
    of dependency/build/cache trees that create disproportionate load.
    """
    segments = [segment.lower() for segment in Path(sp_path).parts if segment not in ("", "/")]
    return any(segment in EXCLUDED_PATH_SEGMENTS for segment in segments)


# ---------------------------------------------------------------------------
# File content fetching
# ---------------------------------------------------------------------------

def _fetch_file_content(
    token: str, site_id: str, drive_id: str, sp_path: str,
    if_match: str | None = None,
) -> str:
    """Fetch raw text content of a SharePoint file via Graph."""
    clean = sp_path.strip("/")
    url   = f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{clean}:/content"
    headers = {"Authorization": f"Bearer {token}"}
    if if_match:
        headers["If-Match"] = if_match
    resp  = requests.get(
        url,
        headers=headers,
        timeout=30,
        allow_redirects=True,
    )
    if not resp.ok:
        raise RuntimeError(f"Content fetch failed ({resp.status_code}): {resp.text[:200]}")
    response_headers = getattr(resp, "headers", {}) or {}
    response_etag = str(
        response_headers.get("ETag") or response_headers.get("etag") or ""
    ).strip()
    if if_match and response_etag and response_etag != if_match:
        raise RuntimeError(
            f"Content response eTag {response_etag!r} did not match "
            f"conditional eTag {if_match!r}"
        )
    try:
        return resp.content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Content is not valid UTF-8: {exc}") from exc


def _fetch_file_metadata(
    token: str, site_id: str, drive_id: str, sp_path: str
) -> dict:
    """Fetch the current Graph identity for one drive item.

    A listing snapshot can race the subsequent content download.  The
    content-sync loop therefore obtains metadata immediately before and after
    each download and only publishes bytes when both identities agree.
    """
    clean = sp_path.strip("/")
    url = f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{clean}"
    resp = requests.get(url, headers=_headers(token), timeout=15)
    if not resp.ok:
        raise RuntimeError(
            f"Metadata fetch failed ({resp.status_code}): {resp.text[:200]}"
        )
    item = resp.json()
    if not isinstance(item, dict):
        raise RuntimeError("Metadata fetch returned a non-object response")
    etag = item.get("eTag") or item.get("@odata.etag") or ""
    version = item.get("cTag") or item.get("ctag") or ""
    if not etag or not version:
        raise RuntimeError(
            f"Graph metadata for '{sp_path}' lacks exact eTag/cTag content identity"
        )
    return {"etag": str(etag), "version": str(version)}


def _fetch_consistent_file_content(
    token: str, site_id: str, drive_id: str, sp_path: str,
    *, binary: bool = False, attempts: int = 2,
) -> tuple[object, dict]:
    """Download bytes/text only when metadata is stable around the download."""
    fetch = _fetch_file_bytes if binary else _fetch_file_content
    last_error = "metadata changed while downloading"
    for _ in range(max(1, attempts)):
        before = _fetch_file_metadata(token, site_id, drive_id, sp_path)
        content = fetch(
            token, site_id, drive_id, sp_path, if_match=before["etag"],
        )
        after = _fetch_file_metadata(token, site_id, drive_id, sp_path)
        if before == after:
            return content, after
        last_error = (
            f"remote metadata changed during download "
            f"(before={before!r}, after={after!r})"
        )
    raise RuntimeError(last_error)


def _fetch_file_bytes(
    token: str, site_id: str, drive_id: str, sp_path: str,
    if_match: str | None = None,
) -> bytes:
    """Fetch raw binary content of a SharePoint file via Graph."""
    clean = sp_path.strip("/")
    url   = f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{clean}:/content"
    headers = {"Authorization": f"Bearer {token}"}
    if if_match:
        headers["If-Match"] = if_match
    resp  = requests.get(
        url,
        headers=headers,
        timeout=60,
        allow_redirects=True,
    )
    if not resp.ok:
        raise RuntimeError(f"Binary fetch failed ({resp.status_code}): {resp.text[:200]}")
    response_headers = getattr(resp, "headers", {}) or {}
    response_etag = str(
        response_headers.get("ETag") or response_headers.get("etag") or ""
    ).strip()
    if if_match and response_etag and response_etag != if_match:
        raise RuntimeError(
            f"Binary response eTag {response_etag!r} did not match "
            f"conditional eTag {if_match!r}"
        )
    return resp.content


# ---------------------------------------------------------------------------
# Local cache write
# ---------------------------------------------------------------------------

def _local_path_for(sp_path: str) -> Path:
    """Convert a SharePoint path to a local cache path."""
    clean = sp_path.strip("/")
    return CACHE_DIR / clean


def _atomic_text_write(path: Path, content: str) -> None:
    """Write a cache artifact with replace-based atomic publication."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _cached_body_bytes(raw: bytes) -> bytes:
    """Remove exactly the poller header and its one separator line.

    User content is never normalised: leading blank lines, non-ASCII UTF-8,
    and all other body bytes remain byte-for-byte intact.
    """
    newline = raw.find(b"\n")
    if newline < 0:
        return raw
    first_line = raw[:newline].rstrip(b"\r")
    if not (
        first_line.startswith(b"<!-- sharepoint-cache:")
        or first_line.startswith(b"<!-- sharepoint-binary-extract:")
    ) or not first_line.endswith(b"-->"):
        return raw
    body_start = newline + 1
    if raw[body_start:body_start + 2] == b"\r\n":
        body_start += 2
    elif raw[body_start:body_start + 1] == b"\n":
        body_start += 1
    return raw[body_start:]


def _cached_body(raw: str) -> str:
    """Return the strictly decoded document body represented by a cache file."""
    return _cached_body_bytes(raw.encode("utf-8")).decode("utf-8")


def _content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _cached_file_sha256(path: Path) -> str:
    return hashlib.sha256(_cached_body_bytes(path.read_bytes())).hexdigest()


def _raw_file_sha256(path: Path) -> str:
    """Hash the exact bytes published in a local cache artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_cached_file(local_path: Path, sp_path: str, content: str, synced_at: str) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"<!-- sharepoint-cache: /{sp_path} | synced: {synced_at} -->\n\n"
    )
    _atomic_text_write(local_path, header + content)


def _write_extracted_file(
    local_path: Path, sp_path: str, extracted_text: str, synced_at: str,
) -> None:
    """Write binary-extracted text to <original-path>.extracted.md."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"<!-- sharepoint-binary-extract: /{sp_path} | synced: {synced_at} -->\n\n"
    )
    _atomic_text_write(local_path, header + extracted_text)


def _get_cached_extracted_synced(extracted_path: Path) -> str | None:
    """Read synced timestamp from .extracted.md header.
    
    Returns ISO timestamp string or None if file doesn't exist or header missing.
    """
    if not extracted_path.exists():
        return None
    try:
        content = extracted_path.read_text(encoding="utf-8")
        first_line = content.split("\n")[0]
        # <!-- sharepoint-binary-extract: /path | synced: 2026-05-23T11:00:00Z -->
        if "synced:" in first_line:
            synced = first_line.split("synced:")[1].split("-->")[0].strip()
            return synced
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Orphan cleanup
# ---------------------------------------------------------------------------

def _cleanup_orphans(should_be_cached: set[str]) -> list[str]:
    """Delete local cache files that should no longer be cached.

    `should_be_cached` is the set of SP relative paths that were successfully
    cached this run. Files on disk that are NOT in this set are removed — this
    handles both:
      • Files deleted from SharePoint (SP orphans)
      • Files that have become ineligible (e.g. grew past 500 KB, changed
        extension to .pdf, or are now filtered out by SHAREPOINT_SYNC_PATHS)
    """
    deleted = []
    if not CACHE_DIR.exists():
        return deleted

    for local_file in CACHE_DIR.rglob("*"):
        if not local_file.is_file():
            continue
        if local_file.name.startswith("."):
            continue
        rel = str(local_file.relative_to(CACHE_DIR)).replace("\\", "/")
        if rel not in should_be_cached:
            try:
                local_file.unlink()
                deleted.append(rel)
                log(f"  Orphan/ineligible deleted: {rel}")
                # Remove now-empty parent dirs
                parent = local_file.parent
                while parent != CACHE_DIR:
                    try:
                        parent.rmdir()
                        parent = parent.parent
                    except OSError:
                        break
            except OSError as e:
                log(f"  WARN: Could not delete {rel}: {e}")
    return deleted


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def _write_manifest(
    cached: dict, skipped: dict, orphans_deleted: list[str], synced_at: str,
    extracted: dict | None = None,
) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    extracted     = extracted or {}
    files_stale   = sum(1 for v in cached.values() if v.get("stale"))
    files_fresh   = len(cached) - files_stale
    manifest = {
        "synced_at":           synced_at,
        "files_cached":        len(cached),
        "files_fresh":         files_fresh,
        "files_stale":         files_stale,
        "files_extracted":     len(extracted),
        "files_skipped":       len(skipped),
        "orphans_deleted":     orphans_deleted,
        "cached":              cached,
        "extracted":           extracted,
        "skipped":             skipped,
    }
    _atomic_text_write(
        MANIFEST,
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    )


def _load_previous_manifest() -> dict:
    """Load prior metadata so a retained stale body keeps its own identity."""
    try:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# Write SHAREPOINT_INDEX.md
# ---------------------------------------------------------------------------

def _write_index(
    tree_lines: list[str],
    host: str, site_path: str,
    cached: dict, skipped: dict,
    synced_at: str,
    extracted: dict | None = None,
) -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# SharePoint Document Index",
        "",
        f"> Site: `{host}{site_path}` | Library: `Documents`",
        f"> Index refreshed: {now}",
        f"> Content mirror synced: {synced_at}",
        "",
        "---",
        "",
        "## Reading files",
        "",
        "**Do not queue read requests.** Read cached files directly:",
        "",
        "```",
        "~/.openclaw/workspace/sharepoint-cache/<SP-path>",
        "```",
        "",
        "Example:",
        "```",
        "~/.openclaw/workspace/sharepoint-cache/Stackstone CRM/Opportunities/Croyde Medical.md",
        "```",
        "",
        "Each cached file starts with a sync timestamp comment so you know exactly how fresh it is.",
        "The manifest with full metadata is at:",
        "```",
        "~/.openclaw/workspace/sharepoint-cache/.manifest.json",
        "```",
        "",
        "**To write** (create/update/append): use the locked `enqueue_operation` helper",
        "from `sharepoint_queue_processor.py`; do not edit the queue JSON directly.",
        "The helper preserves concurrent producers and the queue processor executes",
        "it within 1 minute without requiring TOTP approval.",
        "",
        "---",
        "",
        "## /Documents",
        "",
    ] + tree_lines

    extracted = extracted or {}

    if cached:
        lines += [
            "",
            "---",
            "",
            f"## Cached files ({len(cached)} text files — instant read)",
            "",
        ]
        for rel_path in sorted(cached.keys()):
            meta    = cached[rel_path]
            size_kb = meta.get("size", 0) // 1024
            synced  = meta.get("synced_at", "")[:16].replace("T", " ")
            lines.append(f"- `sharepoint-cache/{rel_path}` — _{size_kb} KB, synced {synced}_")

    if extracted:
        lines += [
            "",
            "---",
            "",
            f"## Extracted binary files ({len(extracted)} files — text extracted, instant read)",
            "",
            "_Text (and images where available) have been extracted from these binary files._",
            "_Read the `.extracted.md` file directly — no queue entry needed._",
            "",
        ]
        for rel_path in sorted(extracted.keys()):
            meta     = extracted[rel_path]
            sp_path  = meta.get("sp_path", "")
            orig_ext = meta.get("original_ext", "")
            size_kb  = meta.get("size", 0) // 1024
            synced   = meta.get("synced_at", "")[:16].replace("T", " ")
            lines.append(
                f"- `sharepoint-cache/{rel_path}` "
                f"← `{sp_path}` ({orig_ext}, {size_kb} KB, extracted {synced})"
            )

    if skipped:
        lines += [
            "",
            "---",
            "",
            f"## Skipped files ({len(skipped)} — NOT in local cache)",
            "",
            "_These files exist in SharePoint but were not cached. Size and reason shown for each._",
            "",
        ]
        for rel_path in sorted(skipped.keys()):
            meta     = skipped[rel_path]
            reason   = meta.get("reason_detail", meta.get("reason", "unknown"))
            size     = meta.get("size", 0)
            size_str = f"{size // 1024:,} KB" if size else "empty"
            lines.append(f"- `/{rel_path}` ({size_str}) — ⚠️ {reason}")

    lines += [
        "",
        "_Index auto-generated by sharepoint_cache_poller.py_",
    ]

    INDEX_MD.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log("SharePoint cache poller starting")

    host      = os.environ.get("SHAREPOINT_HOST", "").strip()
    site_path = os.environ.get("SHAREPOINT_SITE_PATH", "/sites/StackstoneConsulting").strip()

    if not host:
        log("ERROR: SHAREPOINT_HOST not set in ~/.openclaw/.env — skipping")
        sys.exit(1)

    max_file_bytes = int(os.environ.get("SHAREPOINT_MAX_FILE_KB", MAX_FILE_KB_DEFAULT)) * 1024

    sync_paths_raw = os.environ.get("SHAREPOINT_SYNC_PATHS", "").strip()
    sync_paths     = [p.strip() for p in sync_paths_raw.split(",") if p.strip()] \
                     if sync_paths_raw else []
    if sync_paths:
        log(f"Sync paths filter: {sync_paths}")
    else:
        log("Sync paths: all (no SHAREPOINT_SYNC_PATHS filter)")

    try:
        token = _get_access_token()
        log("Token refreshed OK")
    except Exception as e:
        log(f"ERROR: Token refresh failed: {e}")
        sys.exit(1)

    try:
        site_id, drive_id = _resolve_site_and_drive(token)
        log(f"Site: {site_id[:20]}…  Drive: {drive_id[:20]}…")
    except Exception as e:
        log(f"ERROR: Site/drive resolution failed: {e}")
        sys.exit(1)

    # Step 1: Collect every file recursively with no depth limit.
    # This is kept separate from display-tree building so the depth cap on the
    # visual index never silently prevents files from being cached or reported.
    # full_scan_ok is set to False if any listing call fails — orphan cleanup
    # is skipped in that case to avoid deleting valid cache files whose folders
    # could not be listed due to a transient Graph error.
    all_files:    list[dict] = []
    full_scan_ok: bool       = True
    try:
        _collect_all_files(token, site_id, drive_id, "", all_files)
        log(f"File collection complete: {len(all_files)} files found (unlimited depth)")
    except Exception as e:
        log(f"ERROR: File collection failed — orphan cleanup will be skipped: {e}")
        full_scan_ok = False
        if not all_files:
            # Total failure — nothing to sync
            sys.exit(1)
        log(f"  Partial scan: {len(all_files)} files collected before error — continuing with sync only")

    # Step 2: Build the display tree independently (depth-limited for readability).
    tree_lines: list[str] = []
    try:
        _build_display_tree(token, site_id, drive_id, "", 1, tree_lines, "")
        log(f"Display tree built: {len(tree_lines)} lines")
    except Exception as e:
        log(f"WARN: Display tree build failed (non-fatal): {e}")
        tree_lines = [f"_(Tree build failed: {e})_"]

    # Sync file contents
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    previous_manifest = _load_previous_manifest()
    previous_cached = previous_manifest.get("cached", {})
    previous_extracted = previous_manifest.get("extracted", {})
    if not isinstance(previous_cached, dict):
        previous_cached = {}
    if not isinstance(previous_extracted, dict):
        previous_extracted = {}
    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cached:  dict = {}
    skipped: dict = {}

    # eligible_sp_paths tracks files that SHOULD exist in the local cache:
    # they are in SharePoint, match the sync-path filter, and pass eligibility
    # (correct extension + within size limit). Fetch failures do NOT remove a
    # path from this set — the previous cached version is kept until the file
    # is genuinely removed from SharePoint or becomes ineligible.
    eligible_sp_paths: set[str] = set()

    binary_max_file_bytes = int(
        os.environ.get("SHAREPOINT_MAX_BINARY_KB", BINARY_MAX_FILE_KB_DEFAULT)
    ) * 1024

    extracted: dict = {}  # rel_path → metadata for binary-extracted files

    for file_info in all_files:
        sp_path  = file_info["sp_path"]
        name     = file_info["name"]
        size     = file_info["size"]
        modified = file_info["modified"]
        ext      = Path(name).suffix.lower()
        rel_path = sp_path.strip("/")

        # Filter by sync paths (out-of-scope files are not eligible for caching)
        if sync_paths and not _in_sync_paths(sp_path, sync_paths):
            continue

        # ── Text files (.md / .txt) ─────────────────────────────────────────
        if ext in CACHEABLE_EXTENSIONS:
            if size > max_file_bytes:
                size_kb   = size // 1024
                limit_kb  = max_file_bytes // 1024
                skipped[rel_path] = {
                    "sp_path": sp_path, "size": size, "sp_modified": modified,
                    "reason": "file_too_large",
                    "reason_detail": f"File is {size_kb:,} KB — limit is {limit_kb:,} KB",
                }
                log(f"  SKIP [file_too_large] {sp_path} ({size_kb} KB > {limit_kb} KB limit)")
                continue

            eligible_sp_paths.add(rel_path)
            local_path = _local_path_for(sp_path)
            try:
                content, remote = _fetch_consistent_file_content(
                    token, site_id, drive_id, sp_path,
                )
                _write_cached_file(local_path, sp_path, content, synced_at)
                cached[rel_path] = {
                    "sp_path":     sp_path,
                    "size":        size,
                    "sp_modified": modified,
                    "etag":        remote["etag"],
                    "version":     remote["version"],
                    "synced_at":   synced_at,
                    "local_path":  str(local_path.relative_to(WORKSPACE)),
                    "content_sha256": _cached_file_sha256(local_path),
                    "raw_content_sha256": _raw_file_sha256(local_path),
                    "source_content_sha256": _content_sha256(content),
                }
                log(f"  CACHED {sp_path} ({size // 1024} KB)")
            except Exception as e:
                skipped[rel_path] = {
                    "sp_path": sp_path, "size": size, "sp_modified": modified,
                    "reason": "fetch_error",
                    "reason_detail": f"Fetch error: {str(e)[:150]}",
                }
                log(f"  SKIP [fetch_error] {sp_path}: {e}")
                # Keep in eligible_sp_paths — the previous local copy is still valid
            continue

        # ── Binary files (.docx / .pdf / .pptx / .msg) ─────────────────────
        if ext in EXTRACTABLE_EXTENSIONS:
            if _extract_binary_text is None:
                # Extractor module not installed — record as skipped
                skipped[rel_path] = {
                    "sp_path": sp_path, "size": size, "sp_modified": modified,
                    "reason": "extractor_unavailable",
                    "reason_detail": "sharepoint_binary_extractor not installed",
                }
                continue

            if size > binary_max_file_bytes:
                size_kb  = size // 1024
                limit_kb = binary_max_file_bytes // 1024
                skipped[rel_path] = {
                    "sp_path": sp_path, "size": size, "sp_modified": modified,
                    "reason": "binary_too_large",
                    "reason_detail": f"Binary is {size_kb:,} KB — extraction limit is {limit_kb:,} KB",
                }
                log(f"  SKIP [binary_too_large] {sp_path} ({size_kb} KB > {limit_kb} KB limit)")
                continue

            # Extracted text lives at <original-path>.extracted.md
            extracted_rel  = rel_path + ".extracted.md"
            extracted_path = _local_path_for(sp_path + ".extracted.md")
            image_dir      = extracted_path.parent / (Path(name).stem + ".images")
            eligible_sp_paths.add(extracted_rel)

            # Check if already extracted and up-to-date
            try:
                remote = _fetch_file_metadata(token, site_id, drive_id, sp_path)
            except Exception as e:
                skipped[rel_path] = {
                    "sp_path": sp_path, "size": size, "sp_modified": modified,
                    "reason": "metadata_error",
                    "reason_detail": f"Metadata error: {str(e)[:150]}",
                }
                log(f"  SKIP [metadata_error] {sp_path}: {e}")
                continue
            cached_synced = _get_cached_extracted_synced(extracted_path)
            previous_entry = previous_extracted.get(extracted_rel, {})
            metadata_unchanged = (
                isinstance(previous_entry, dict)
                and previous_entry.get("etag")
                and previous_entry.get("version")
                and previous_entry.get("etag") == remote["etag"]
                and previous_entry.get("version") == remote["version"]
            )
            if cached_synced and cached_synced >= modified and metadata_unchanged:
                # File hasn't changed since last extraction — skip re-extraction
                extracted[extracted_rel] = {
                    "sp_path":        sp_path,
                    "original_ext":   ext,
                    "size":           size,
                    "sp_modified":    modified,
                    "etag":           remote["etag"],
                    "version":        remote["version"],
                    "synced_at":      cached_synced,
                    "local_path":     str(extracted_path.relative_to(WORKSPACE)),
                    "content_sha256": _cached_file_sha256(extracted_path),
                    "raw_content_sha256": _raw_file_sha256(extracted_path),
                    "source_content_sha256": previous_entry.get(
                        "source_content_sha256", ""
                    ),
                }
                log(f"  CACHED (unchanged) {sp_path}")
                continue

            try:
                raw_bytes, remote = _fetch_consistent_file_content(
                    token, site_id, drive_id, sp_path, binary=True,
                )
                extracted_text = _extract_binary_text(name, raw_bytes, image_dir=image_dir)
                _write_extracted_file(extracted_path, sp_path, extracted_text, synced_at)
                extracted[extracted_rel] = {
                    "sp_path":        sp_path,
                    "original_ext":   ext,
                    "size":           size,
                    "sp_modified":    modified,
                    "etag":           remote["etag"],
                    "version":        remote["version"],
                    "synced_at":      synced_at,
                    "local_path":     str(extracted_path.relative_to(WORKSPACE)),
                    "content_sha256": _cached_file_sha256(extracted_path),
                    "raw_content_sha256": _raw_file_sha256(extracted_path),
                    "source_content_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                }
                log(f"  EXTRACTED {sp_path} ({size // 1024} KB) → {extracted_rel}")
            except Exception as e:
                skipped[rel_path] = {
                    "sp_path": sp_path, "size": size, "sp_modified": modified,
                    "reason": "extraction_error",
                    "reason_detail": f"Extraction error: {str(e)[:150]}",
                }
                log(f"  SKIP [extraction_error] {sp_path}: {e}")
                # Keep extracted_rel in eligible_sp_paths — previous extracted copy kept
            continue

        # ── Other file types — indexed only, not cached ─────────────────────
        skipped[rel_path] = {
            "sp_path": sp_path, "size": size, "sp_modified": modified,
            "reason": "non_cacheable_type",
            "reason_detail": (
                f"File type `{ext or 'no extension'}` is not cached. "
                f"Only .md/.txt are cached; .docx/.pdf/.pptx/.msg are extracted."
            ),
        }
        log(f"  SKIP [non_cacheable_type] {sp_path}")

    log(f"Content sync done: {len(cached)} text cached, {len(extracted)} binary extracted, {len(skipped)} skipped")

    # Orphan cleanup — only performed when the Graph enumeration was complete.
    # If _collect_all_files raised at any point (full_scan_ok=False), we skip
    # deletion entirely to prevent valid cached files from being purged because
    # their parent folder could not be listed in this run.
    # What gets removed when full_scan_ok:
    # • Files deleted from SharePoint (not in any SP file listing)
    # • Files that became ineligible (wrong type, grew too large, out of sync-path)
    # • Fetch-failed files are NOT removed — eligible_sp_paths preserves them
    orphans_deleted: list[str] = []
    if full_scan_ok:
        orphans_deleted = _cleanup_orphans(eligible_sp_paths)
        if orphans_deleted:
            log(f"Orphans/ineligible deleted: {len(orphans_deleted)}")
    else:
        log("WARN: Orphan cleanup skipped — scan was incomplete (Graph error above)")

    # Build true on-disk manifest: includes freshly fetched files AND files kept
    # from previous sync runs where this run had a transient fetch error.
    # Walk the eligible set and add any locally-present file not already in cached.
    # Build a lookup from rel_path → SP metadata for quick access
    sp_meta_by_rel: dict[str, dict] = {f["sp_path"].strip("/"): f for f in all_files}

    for rel_path in eligible_sp_paths:
        already_handled = rel_path in cached or rel_path in extracted
        if already_handled:
            continue  # freshly processed — already correct
        local_path = CACHE_DIR / rel_path
        if not local_path.exists():
            continue  # not on disk (never fetched, or just deleted as orphan)
        # File is on disk from a previous run — record it with a "stale" note
        is_extracted = rel_path.endswith(".extracted.md")
        prior_entries = previous_extracted if is_extracted else previous_cached
        prior_entry = prior_entries.get(rel_path, {})
        if not isinstance(prior_entry, dict):
            prior_entry = {}
        # For extracted files, the SP path is the rel_path minus ".extracted.md"
        sp_key = rel_path[: -len(".extracted.md")] if is_extracted else rel_path
        sp_meta = sp_meta_by_rel.get(sp_key, {})
        try:
            file_size = local_path.stat().st_size
        except OSError:
            file_size = 0
        stale_synced_at = ""
        try:
            first_line = local_path.read_text(encoding="utf-8", errors="ignore").split("\n", 1)[0]
            if "synced:" in first_line:
                stale_synced_at = first_line.split("synced:")[-1].strip(" -->").strip()
        except OSError:
            pass
        entry = {
            "sp_path":     sp_meta.get("sp_path", "/" + sp_key),
            "size":        sp_meta.get("size", file_size),
            "sp_modified": sp_meta.get("modified", ""),
            "etag":        prior_entry.get("etag") or sp_meta.get("etag", ""),
            "version":     prior_entry.get("version") or sp_meta.get("version", ""),
            "synced_at":   stale_synced_at or "(previous run)",
            "local_path":  str(local_path.relative_to(WORKSPACE)),
            "stale":       True,
        }
        if not entry["etag"] or not entry["version"]:
            # An item ID is not a content version.  Without an exact remote
            # identity this local body cannot be published as authoritative
            # manifest metadata, even as a retained stale copy.
            log(f"  STALE NOT PUBLISHED: {rel_path} lacks exact remote identity")
            continue
        try:
            entry["content_sha256"] = _cached_file_sha256(local_path)
            entry["raw_content_sha256"] = _raw_file_sha256(local_path)
            entry["source_content_sha256"] = prior_entry.get(
                "source_content_sha256", ""
            )
        except (OSError, UnicodeError):
            entry["content_sha256"] = (
                prior_entry.get("content_sha256", "")
            )
        if is_extracted:
            entry["original_ext"] = Path(sp_key).suffix.lower()
            extracted[rel_path]   = entry
        else:
            cached[rel_path] = entry
        log(f"  STALE RETAINED: {rel_path} (previous copy kept)")

    log(
        f"On-disk manifest: {len(cached)} text files, "
        f"{len(extracted)} extracted binaries "
        f"(freshly synced + retained from previous runs)"
    )

    # Write manifest — fatal on failure: /sp-sync depends on fresh manifest data,
    # so a manifest write failure must not silently produce an ambiguous success.
    try:
        _write_manifest(cached, skipped, orphans_deleted, synced_at, extracted)
        log(f"Manifest written: {MANIFEST}")
    except Exception as e:
        log(f"ERROR: Manifest write failed — aborting: {e}")
        sys.exit(1)

    # Write index
    try:
        _write_index(tree_lines, host, site_path, cached, skipped, synced_at, extracted)
        log(f"SHAREPOINT_INDEX.md written ({INDEX_MD.stat().st_size:,} bytes)")
    except Exception as e:
        log(f"ERROR: Index write failed: {e}")
        sys.exit(1)

    total_cache_kb = sum(
        f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file() and not f.name.startswith(".")
    ) // 1024
    log(f"Done. Total cache size: {total_cache_kb:,} KB")


if __name__ == "__main__":
    main()
