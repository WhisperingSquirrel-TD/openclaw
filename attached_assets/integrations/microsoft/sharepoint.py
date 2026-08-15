#!/usr/bin/env python3
"""
OpenClaw SharePoint document-management layer.
Uses the assistant@ Microsoft Graph identity for audit trail and version history.

COMMANDS
--------
  sharepoint.py list   <sp-path>
  sharepoint.py read   <sp-file-path>
  sharepoint.py create <sp-file-path> --content-file /tmp/oc-sp-content.txt
  sharepoint.py update <sp-file-path> --content-file /tmp/oc-sp-content.txt
  sharepoint.py append <sp-file-path> --content-file /tmp/oc-sp-content.txt
  sharepoint.py upload <sp-file-path> --content-file /path/to/original-binary --mime-type image/jpeg
  sharepoint.py move          <sp-source-path> --destination <sp-destination-path>
  sharepoint.py delete_folder <sp-folder-path>   # only succeeds if folder is empty

PATHS
-----
All paths are relative to the document library root, e.g.:
  /Stackstone CRM/Opportunities/Harken Health.md
  /Stackstone CRM/Accounts/Croyde Medical.md

PROHIBITED OPERATIONS
---------------------
Deleting files is not implemented by design. Use move to relocate files to an Archive/ folder.
Deleting non-empty folders is blocked — the folder must be empty before delete_folder will proceed.

REQUIRED ENV VARS (in ~/.openclaw/.env)
---------------------------------------
  SHAREPOINT_HOST        e.g.  seerepeat.sharepoint.com
  SHAREPOINT_SITE_PATH   optional, default /sites/StackstoneConsulting
  SHAREPOINT_DRIVE_NAME  optional, default Documents  (the library name)

GRAPH PERMISSIONS REQUIRED
---------------------------
  Files.ReadWrite          read + write files in user's OneDrive/SP libraries
  Sites.ReadWrite.All      access SharePoint site drives
  offline_access           maintain refresh token

The assistant@ token currently authorises: Mail.Send offline_access
New scopes need a one-time re-auth — see RE-AUTH below.

RE-AUTH
-------
After deploying this script, re-authenticate assistant@ with the new scopes:

  python3 ~/.openclaw/integrations/microsoft-l1/sharepoint.py reauth

That opens a browser URL. Complete the consent flow, paste the redirect URL
back. The existing token file is updated in-place so mail/calendar still work.

EXIT CODES
----------
  0  success
  1  auth error
  2  API / Graph error
  3  bad arguments / content file missing
  4  file already exists (create --no-overwrite)
  5  file not found
"""

import argparse
import json
import sys
import requests
from datetime import datetime
from pathlib import Path

STATE_DIR  = Path.home() / ".openclaw"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SP_CACHE   = STATE_DIR / "integrations/microsoft/sharepoint-cache.json"

# Scopes needed at runtime by this script
REQUIRED_SCOPES = "Files.ReadWrite Sites.ReadWrite.All offline_access"

# Full consent scope set for the assistant@ account — used at reauth time so that
# ONE consent covers every capability the system will ever need for this account.
# Adding a new integration in future will NOT require another reauth as long as
# its scopes are already listed here.
#
#   Mail.Send          — send email as assistant@
#   Mail.Read          — read assistant@ inbox (email poller)
#   Files.ReadWrite    — read + write SharePoint / OneDrive files
#   Sites.ReadWrite.All— access SharePoint site drives
#   Calendars.ReadWrite— read + write calendar events
#   Tasks.ReadWrite    — read + write Microsoft To Do / Tasks
#   User.Read          — basic profile (required for some Graph calls)
#   offline_access     — maintain refresh token across sessions
FULL_CONSENT_SCOPES = (
    "Mail.Send Mail.Read Files.ReadWrite Sites.ReadWrite.All "
    "Calendars.ReadWrite Tasks.ReadWrite User.Read offline_access"
)


# ---------------------------------------------------------------------------
# .env loader (same pattern as other pollers)
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    import os
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
# Arg parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="OpenClaw SharePoint document manager (assistant@ identity)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("command", choices=["list", "read", "create", "update", "append", "upload", "move", "delete_folder", "reauth"],
                   help="Operation to perform")
    p.add_argument("path", nargs="?", default="",
                   help="SharePoint path, e.g. /Stackstone CRM/Opportunities/Harken Health.md")
    p.add_argument("--content-file", default=None,
                   help="Path to temp file containing content (required for create/update/append)")
    p.add_argument("--allow-overwrite", action="store_true",
                   help="For create: overwrite if file already exists (default: fail)")
    p.add_argument("--mime-type", default=None,
                   help="For upload: original binary MIME type (required)")
    p.add_argument("--destination", default=None,
                   help="Destination SharePoint path (required for move)")
    p.add_argument("--account", default="assistant",
                   help="Token account slug (default: assistant)")
    p.add_argument("--token-file", default=None,
                   help="Explicit path to OAuth token JSON file")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Token helpers (same pattern as send.py / create-event.py)
# ---------------------------------------------------------------------------

def _resolve_token_file(args: argparse.Namespace) -> Path:
    if args.token_file:
        return Path(args.token_file)
    slug = args.account
    candidates = [
        STATE_DIR / f"integrations/microsoft/token-{slug}.json",
        STATE_DIR / f"integrations/microsoft-{slug}/token-{slug}.json",
        STATE_DIR / "integrations/microsoft/token-assistant.json",
        Path(__file__).parent / "token.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"No token file found for account '{slug}'. Tried:\n"
        + "\n".join(f"  {c}" for c in candidates)
        + "\nRun: python3 sharepoint.py reauth"
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
    except json.JSONDecodeError as first_err:
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(raw.strip())
            if isinstance(data, dict):
                print(f"WARNING: Token file corrupted — auto-recovered.", file=sys.stderr)
                _write_atomic(path, data)
                return data
        except json.JSONDecodeError:
            pass
        raise ValueError(f"Token file unreadable: {path}\n{first_err}") from first_err


def _load_token(args: argparse.Namespace) -> tuple[dict, Path]:
    token_file = _resolve_token_file(args)
    data = _load_json_resilient(token_file)
    if "RefreshToken" in data and "AccessToken" in data:
        at_list  = list(data.get("AccessToken",  {}).values())
        rt_list  = list(data.get("RefreshToken", {}).values())
        app_list = list(data.get("AppMetadata",  {}).values())
        at  = at_list[0]  if at_list  else {}
        rt  = rt_list[0]
        app = app_list[0] if app_list else {}
        simple = {
            "client_id":     at.get("client_id") or app.get("client_id", ""),
            "client_secret": "",
            "tenant_id":     at.get("realm", "common"),
            "refresh_token": rt["secret"],
            "access_token":  at.get("secret", ""),
        }
        _write_atomic(token_file, simple)
        return simple, token_file
    return data, token_file


def _refresh_access_token(token_data: dict, token_file: Path) -> str:
    tenant = token_data.get("tenant_id", "common")
    body: dict = {
        "client_id":     token_data["client_id"],
        "refresh_token": token_data["refresh_token"],
        "grant_type":    "refresh_token",
        "scope":         REQUIRED_SCOPES,
    }
    secret = token_data.get("client_secret", "")
    if secret:
        body["client_secret"] = secret

    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data=body,
        timeout=15,
    )
    if not resp.ok:
        err = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        print(
            f"Token refresh failed ({resp.status_code}): {err}",
            file=sys.stderr,
        )
        if "AADSTS65001" in str(err) or "invalid_grant" in str(err):
            print(
                "\nThe assistant@ token does not have SharePoint/Files scope.\n"
                "Run: python3 sharepoint.py reauth\n"
                "to grant the new permissions.",
                file=sys.stderr,
            )
        sys.exit(1)

    new = resp.json()
    token_data["access_token"]  = new["access_token"]
    token_data["refresh_token"] = new.get("refresh_token", token_data["refresh_token"])
    _write_atomic(token_file, token_data)
    return token_data["access_token"]


def get_access_token(args: argparse.Namespace) -> str:
    token_data, token_file = _load_token(args)
    return _refresh_access_token(token_data, token_file)


# ---------------------------------------------------------------------------
# Re-auth (device code flow — no browser redirect needed on the Pi)
# ---------------------------------------------------------------------------

def cmd_reauth(args: argparse.Namespace) -> None:
    """
    Device-code re-auth flow. Requests FULL_CONSENT_SCOPES so that this one
    consent covers every Microsoft capability the system will ever need for
    this account — email, SharePoint, calendar, tasks.  No future reauth
    should be needed unless the token file is deleted or access is revoked.
    """
    import time

    account = args.account  # "assistant" or "microsoft" (personal)

    # Choose the right full scope set per account type
    # Both accounts request the same superset — simpler and future-proof.
    consent_scopes = FULL_CONSENT_SCOPES

    token_data, token_file = _load_token(args)
    client_id = token_data.get("client_id", "")
    tenant    = token_data.get("tenant_id", "common")

    if not client_id:
        print("ERROR: client_id missing from token file. Cannot reauth.", file=sys.stderr)
        sys.exit(1)

    # Device code flow — works on Pi without a browser or redirect
    init_resp = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode",
        data={"client_id": client_id, "scope": consent_scopes},
        timeout=15,
    )
    if not init_resp.ok:
        print(f"Device code request failed: {init_resp.status_code} {init_resp.text}",
              file=sys.stderr)
        sys.exit(1)

    flow = init_resp.json()
    print("\n" + "=" * 65)
    print(f"  Microsoft re-auth — account: {account}")
    print(f"  Granting ALL scopes in one go — no future reauth needed")
    print(f"  Scopes: {consent_scopes}")
    print("=" * 65)
    print(f"\n  {flow['message']}\n")
    print("  (Waiting for you to complete the sign-in…)\n")

    interval    = flow.get("interval", 5)
    device_code = flow["device_code"]
    expires_in  = flow.get("expires_in", 900)
    deadline    = time.time() + expires_in

    while time.time() < deadline:
        time.sleep(interval)
        poll = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id":   client_id,
                "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
            timeout=15,
        )
        data = poll.json()
        if "access_token" in data:
            token_data["access_token"]  = data["access_token"]
            token_data["refresh_token"] = data.get("refresh_token",
                                                    token_data.get("refresh_token", ""))
            _write_atomic(token_file, token_data)
            print(f"\n  ✓ Token updated: {token_file}")
            print(f"  ✓ All Microsoft scopes granted for {account} account.")
            print(f"  Email, SharePoint, calendar and tasks all authorised.\n")
            return
        err = data.get("error", "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        print(f"  Auth failed: {data.get('error_description', err)}", file=sys.stderr)
        sys.exit(1)

    print("  Timed out waiting for sign-in.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# SharePoint site + drive resolution (cached)
# ---------------------------------------------------------------------------

import os

def _get_sp_config() -> tuple[str, str, str]:
    """Return (host, site_path, drive_name) from env."""
    host       = os.environ.get("SHAREPOINT_HOST", "").strip()
    site_path  = os.environ.get("SHAREPOINT_SITE_PATH",  "/sites/StackstoneConsulting").strip()
    drive_name = os.environ.get("SHAREPOINT_DRIVE_NAME", "Documents").strip()
    if not host:
        print(
            "ERROR: SHAREPOINT_HOST not set.\n"
            "Add it to ~/.openclaw/.env, e.g.:\n"
            "  SHAREPOINT_HOST=seerepeat.sharepoint.com",
            file=sys.stderr,
        )
        sys.exit(3)
    return host, site_path, drive_name


def _load_sp_cache() -> dict:
    try:
        if SP_CACHE.exists():
            return json.loads(SP_CACHE.read_text())
    except Exception:
        pass
    return {}


def _save_sp_cache(data: dict) -> None:
    _write_atomic(SP_CACHE, data)


def _resolve_site_and_drive(access_token: str) -> tuple[str, str]:
    """
    Return (site_id, drive_id). Uses a local cache to avoid extra API calls.
    Cache is keyed by host+site_path+drive_name so changing config busts it.
    """
    host, site_path, drive_name = _get_sp_config()
    cache_key = f"{host}{site_path}|{drive_name}"
    cache = _load_sp_cache()

    if cache.get("key") == cache_key and cache.get("site_id") and cache.get("drive_id"):
        return cache["site_id"], cache["drive_id"]

    headers = {"Authorization": f"Bearer {access_token}"}

    # Resolve site
    if site_path.strip("/"):
        site_url = f"{GRAPH_BASE}/sites/{host}:{site_path}"
    else:
        site_url = f"{GRAPH_BASE}/sites/{host}"

    resp = requests.get(site_url, headers=headers, timeout=15)
    if not resp.ok:
        print(
            f"ERROR: Could not resolve SharePoint site.\n"
            f"  Host: {host}\n  Site path: {site_path}\n"
            f"  Graph response: {resp.status_code} {resp.text[:300]}",
            file=sys.stderr,
        )
        sys.exit(2)
    site_id = resp.json()["id"]

    # Resolve drive by name
    drives_resp = requests.get(
        f"{GRAPH_BASE}/sites/{site_id}/drives",
        headers=headers,
        timeout=15,
    )
    if not drives_resp.ok:
        print(f"ERROR: Could not list drives: {drives_resp.status_code} {drives_resp.text[:300]}",
              file=sys.stderr)
        sys.exit(2)

    drives = drives_resp.json().get("value", [])
    drive_id = None
    for d in drives:
        if d.get("name", "").lower() == drive_name.lower():
            drive_id = d["id"]
            break

    if not drive_id:
        available = [d.get("name", "?") for d in drives]
        print(
            f"ERROR: Document library '{drive_name}' not found.\n"
            f"  Available libraries: {available}\n"
            f"  Set SHAREPOINT_DRIVE_NAME in ~/.openclaw/.env",
            file=sys.stderr,
        )
        sys.exit(2)

    _save_sp_cache({"key": cache_key, "site_id": site_id, "drive_id": drive_id,
                    "cached_at": datetime.utcnow().isoformat()})
    return site_id, drive_id


def _drive_item_url(site_id: str, drive_id: str, sp_path: str) -> str:
    """Build the Graph URL for a drive item by path."""
    clean = sp_path.strip("/")
    return f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{clean}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_path(sp_path: str) -> str:
    if not sp_path:
        print("ERROR: SharePoint path is required.", file=sys.stderr)
        sys.exit(3)
    return "/" + sp_path.strip("/")


def _read_content_file(path: str) -> bytes:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: Content file not found: {path}", file=sys.stderr)
        sys.exit(3)
    return p.read_bytes()


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _file_exists(access_token: str, site_id: str, drive_id: str, sp_path: str) -> bool:
    url  = _drive_item_url(site_id, drive_id, sp_path)
    resp = requests.get(url, headers=_headers(access_token), timeout=15)
    return resp.status_code == 200


def _print_item(item: dict, prefix: str = "") -> None:
    name      = item.get("name", "?")
    is_folder = "folder" in item
    size      = item.get("size", 0)
    modified  = (item.get("lastModifiedDateTime") or "")[:16].replace("T", " ")
    icon      = "📁" if is_folder else "📄"
    if is_folder:
        print(f"{prefix}{icon}  {name}/")
    else:
        print(f"{prefix}{icon}  {name}  ({size:,} bytes, modified {modified})")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(access_token: str, sp_path: str, site_id: str, drive_id: str) -> None:
    sp_path = _normalise_path(sp_path)
    clean   = sp_path.strip("/")

    if clean:
        url = f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{clean}:/children"
    else:
        url = f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root/children"

    resp = requests.get(url, headers=_headers(access_token), timeout=15)

    if resp.status_code == 404:
        print(f"ERROR: Folder not found: {sp_path}", file=sys.stderr)
        sys.exit(5)
    if not resp.ok:
        print(f"ERROR: List failed ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
        sys.exit(2)

    items = resp.json().get("value", [])
    print(f"\nContents of {sp_path}  ({len(items)} item(s))\n")
    if not items:
        print("  (empty)")
    else:
        for item in sorted(items, key=lambda x: (0 if "folder" in x else 1, x.get("name", ""))):
            _print_item(item, prefix="  ")
    print()


def cmd_read(access_token: str, sp_path: str, site_id: str, drive_id: str) -> None:
    sp_path = _normalise_path(sp_path)
    url     = _drive_item_url(site_id, drive_id, sp_path) + ":/content"

    resp = requests.get(url, headers=_headers(access_token), timeout=30)

    if resp.status_code == 404:
        print(f"ERROR: File not found: {sp_path}", file=sys.stderr)
        sys.exit(5)
    if not resp.ok:
        print(f"ERROR: Read failed ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
        sys.exit(2)

    print(resp.text)


def cmd_create(access_token: str, sp_path: str, site_id: str, drive_id: str,
               content_file: str, allow_overwrite: bool) -> None:
    sp_path = _normalise_path(sp_path)
    content = _read_content_file(content_file)

    if not allow_overwrite:
        if _file_exists(access_token, site_id, drive_id, sp_path):
            print(
                f"ERROR: File already exists: {sp_path}\n"
                "Use --allow-overwrite to replace it, or use 'update' to replace with versioning.",
                file=sys.stderr,
            )
            sys.exit(4)

    url = _drive_item_url(site_id, drive_id, sp_path) + ":/content"
    headers = _headers(access_token)
    headers["Content-Type"] = "text/markdown; charset=utf-8"

    resp = requests.put(url, headers=headers, data=content, timeout=30)

    if not resp.ok:
        print(f"ERROR: Create failed ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
        sys.exit(2)

    item    = resp.json()
    version = item.get("eTag", "").strip('"')[:12]
    size    = item.get("size", len(content))
    print(f"✓ Created: {sp_path}")
    print(f"  Size:    {size:,} bytes")
    if version:
        print(f"  eTag:    {version}")
    print(f"  URL:     {item.get('webUrl', '(unavailable)')}")


def cmd_upload(access_token: str, sp_path: str, site_id: str, drive_id: str,
               content_file: str, mime_type: str) -> None:
    """Upload an original receipt binary and emit machine-readable proof.

    Existing content is never overwritten: callers derive a content-addressed
    filename and a retry treats Graph's conflict as a harmless blocked state.
    """
    sp_path = _normalise_path(sp_path)
    if not mime_type or "/" not in mime_type or "\n" in mime_type:
        print("ERROR: --mime-type must be a valid MIME type", file=sys.stderr)
        sys.exit(3)
    content = _read_content_file(content_file)
    existing = requests.get(_drive_item_url(site_id, drive_id, sp_path), headers=_headers(access_token), timeout=15)
    if existing.status_code == 200:
        item = existing.json()
        print(json.dumps({"status": "exists", "path": sp_path, "url": item.get("webUrl"),
                          "etag": item.get("eTag"), "size": item.get("size"),
                          "mime_type": mime_type}, sort_keys=True), flush=True)
        return
    if existing.status_code not in (404,):
        print(f"ERROR: Upload existence check failed ({existing.status_code}): {existing.text[:300]}", file=sys.stderr)
        sys.exit(2)
    response = requests.put(
        _drive_item_url(site_id, drive_id, sp_path) + ":/content",
        headers={**_headers(access_token), "Content-Type": mime_type},
        data=content, timeout=60,
    )
    if not response.ok:
        print(f"ERROR: Upload failed ({response.status_code}): {response.text[:300]}", file=sys.stderr)
        sys.exit(2)
    item = response.json()
    print(json.dumps({
        "status": "uploaded", "path": sp_path, "url": item.get("webUrl"),
        "etag": item.get("eTag"), "size": item.get("size", len(content)),
        "mime_type": mime_type,
    }, sort_keys=True), flush=True)


def cmd_update(access_token: str, sp_path: str, site_id: str, drive_id: str,
               content_file: str) -> None:
    sp_path = _normalise_path(sp_path)
    content = _read_content_file(content_file)

    if not _file_exists(access_token, site_id, drive_id, sp_path):
        print(
            f"ERROR: File not found: {sp_path}\n"
            "Use 'create' to create a new file.",
            file=sys.stderr,
        )
        sys.exit(5)

    url = _drive_item_url(site_id, drive_id, sp_path) + ":/content"
    headers = _headers(access_token)
    headers["Content-Type"] = "text/markdown; charset=utf-8"

    resp = requests.put(url, headers=headers, data=content, timeout=30)

    if not resp.ok:
        print(f"ERROR: Update failed ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
        sys.exit(2)

    item    = resp.json()
    version = item.get("eTag", "").strip('"')[:12]
    size    = item.get("size", len(content))
    print(f"✓ Updated: {sp_path}")
    print(f"  Size:    {size:,} bytes")
    if version:
        print(f"  eTag:    {version}")
    print(f"  SharePoint versioning creates a new version automatically if enabled.")
    print(f"  URL:     {item.get('webUrl', '(unavailable)')}")


def cmd_append(access_token: str, sp_path: str, site_id: str, drive_id: str,
               content_file: str) -> None:
    sp_path    = _normalise_path(sp_path)
    new_chunk  = _read_content_file(content_file)

    # Read existing content
    read_url = _drive_item_url(site_id, drive_id, sp_path) + ":/content"
    read_resp = requests.get(read_url, headers=_headers(access_token), timeout=30)

    if read_resp.status_code == 404:
        print(
            f"ERROR: File not found: {sp_path}\n"
            "Use 'create' to create it first.",
            file=sys.stderr,
        )
        sys.exit(5)
    if not read_resp.ok:
        print(f"ERROR: Could not read file before append ({read_resp.status_code}): {read_resp.text[:300]}",
              file=sys.stderr)
        sys.exit(2)

    existing = read_resp.content

    # Join: ensure a blank line between existing content and new chunk
    separator = b"\n\n" if not existing.endswith(b"\n\n") else b""
    if existing.endswith(b"\n"):
        separator = b"\n"
    combined = existing + separator + new_chunk

    # Write back
    write_url = _drive_item_url(site_id, drive_id, sp_path) + ":/content"
    headers   = _headers(access_token)
    headers["Content-Type"] = "text/markdown; charset=utf-8"

    resp = requests.put(write_url, headers=headers, data=combined, timeout=30)

    if not resp.ok:
        print(f"ERROR: Append write failed ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
        sys.exit(2)

    item    = resp.json()
    version = item.get("eTag", "").strip('"')[:12]
    print(f"✓ Appended: {sp_path}")
    print(f"  Added:   {len(new_chunk):,} bytes")
    print(f"  Total:   {item.get('size', len(combined)):,} bytes")
    if version:
        print(f"  eTag:    {version}")
    print(f"  URL:     {item.get('webUrl', '(unavailable)')}")


def cmd_delete_folder(access_token: str, sp_path: str,
                      site_id: str, drive_id: str) -> None:
    """Delete a folder — only if it contains zero items.

    Safety check: lists the folder's children first. If anything is inside
    (files or subfolders) the operation is refused with exit code 2.
    This prevents any accidental data loss — move files out first, then call
    delete_folder once the folder is empty.
    """
    sp_path = _normalise_path(sp_path)

    # 1. Verify it exists and is a folder
    meta_url  = _drive_item_url(site_id, drive_id, sp_path)
    meta_resp = requests.get(meta_url, headers=_headers(access_token), timeout=15)
    if meta_resp.status_code == 404:
        print(f"ERROR: Folder not found: {sp_path}", file=sys.stderr)
        sys.exit(5)
    if not meta_resp.ok:
        print(f"ERROR: Could not read item metadata ({meta_resp.status_code}): {meta_resp.text[:300]}",
              file=sys.stderr)
        sys.exit(2)
    meta = meta_resp.json()
    if "folder" not in meta:
        print(
            f"ERROR: '{sp_path}' is a file, not a folder. "
            "File deletion is not permitted — use move to relocate files.",
            file=sys.stderr,
        )
        sys.exit(2)

    # 2. Check it is empty
    children_url  = _drive_item_url(site_id, drive_id, sp_path) + ":/children"
    children_resp = requests.get(children_url, headers=_headers(access_token), timeout=15)
    if not children_resp.ok:
        print(f"ERROR: Could not list folder contents ({children_resp.status_code}): {children_resp.text[:300]}",
              file=sys.stderr)
        sys.exit(2)
    children = children_resp.json().get("value", [])
    if children:
        names = ", ".join(c.get("name", "?") for c in children[:5])
        extra = f" … and {len(children) - 5} more" if len(children) > 5 else ""
        print(
            f"ERROR: Folder is not empty ({len(children)} item(s)): {names}{extra}\n"
            "Move or relocate all contents first, then retry delete_folder.",
            file=sys.stderr,
        )
        sys.exit(2)

    # 3. Delete the empty folder
    del_url  = _drive_item_url(site_id, drive_id, sp_path)
    del_resp = requests.delete(del_url, headers=_headers(access_token), timeout=15)
    if del_resp.status_code == 404:
        print(f"ERROR: Folder not found (may have already been deleted): {sp_path}", file=sys.stderr)
        sys.exit(5)
    if not del_resp.ok:
        print(f"ERROR: Delete failed ({del_resp.status_code}): {del_resp.text[:300]}", file=sys.stderr)
        sys.exit(2)

    print(f"✓ Deleted empty folder: {sp_path}")


def cmd_move(access_token: str, sp_path: str, destination: str,
             site_id: str, drive_id: str) -> None:
    """Move (and optionally rename) a file or folder to a new path.

    Uses the Graph API PATCH endpoint with parentReference + name.
    The destination folder is created automatically by SharePoint if it
    doesn't exist only when the parent path already exists — otherwise
    the call fails cleanly with a 404/409 so no silent data loss occurs.
    """
    sp_path     = _normalise_path(sp_path)
    destination = _normalise_path(destination)

    # Derive destination parent folder and new filename
    dest_parts  = destination.rsplit("/", 1)
    dest_folder = dest_parts[0] if len(dest_parts) > 1 else ""
    dest_name   = dest_parts[1] if len(dest_parts) > 1 else destination.strip("/")

    # Build the parentReference path that Graph expects:
    #   /drives/{drive-id}/root:/{folder-path}
    if dest_folder.strip("/"):
        parent_path = f"/drives/{drive_id}/root:/{dest_folder.strip('/')}"
    else:
        parent_path = f"/drives/{drive_id}/root:"

    url  = _drive_item_url(site_id, drive_id, sp_path)
    hdrs = _headers(access_token)
    hdrs["Content-Type"] = "application/json"

    body = {
        "parentReference": {"path": parent_path},
        "name": dest_name,
    }

    resp = requests.patch(url, headers=hdrs, json=body, timeout=30)

    if resp.status_code == 404:
        print(f"ERROR: Source not found: {sp_path}", file=sys.stderr)
        sys.exit(5)
    if resp.status_code == 409:
        print(
            f"ERROR: Destination conflict — a file named '{dest_name}' already exists at "
            f"{dest_folder or '(root)'}. Rename the destination path to avoid overwriting.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not resp.ok:
        print(f"ERROR: Move failed ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
        sys.exit(2)

    item = resp.json()
    print(f"✓ Moved:  {sp_path}")
    print(f"  → To:   {destination}")
    print(f"  URL:    {item.get('webUrl', '(unavailable)')}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _load_dotenv()
    args = parse_args()

    # reauth doesn't need a valid SharePoint path
    if args.command == "reauth":
        cmd_reauth(args)
        return

    sp_path = args.path
    if not sp_path and args.command != "list":
        print("ERROR: A SharePoint path is required for this command.", file=sys.stderr)
        sys.exit(3)

    if args.command in ("create", "update", "append", "upload") and not args.content_file:
        print(
            f"ERROR: --content-file is required for '{args.command}'.\n"
            "Write your content to /tmp/oc-sp-content.txt first, then pass --content-file /tmp/oc-sp-content.txt",
            file=sys.stderr,
        )
        sys.exit(3)

    if args.command == "upload" and not args.mime_type:
        print("ERROR: --mime-type is required for 'upload'.", file=sys.stderr)
        sys.exit(3)

    if args.command == "move" and not args.destination:
        print("ERROR: --destination is required for 'move'.", file=sys.stderr)
        sys.exit(3)

    try:
        access_token = get_access_token(args)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    site_id, drive_id = _resolve_site_and_drive(access_token)

    if args.command == "list":
        cmd_list(access_token, sp_path, site_id, drive_id)
    elif args.command == "read":
        cmd_read(access_token, sp_path, site_id, drive_id)
    elif args.command == "create":
        cmd_create(access_token, sp_path, site_id, drive_id,
                   args.content_file, args.allow_overwrite)
    elif args.command == "upload":
        cmd_upload(access_token, sp_path, site_id, drive_id, args.content_file, args.mime_type)
    elif args.command == "update":
        cmd_update(access_token, sp_path, site_id, drive_id, args.content_file)
    elif args.command == "append":
        cmd_append(access_token, sp_path, site_id, drive_id, args.content_file)
    elif args.command == "move":
        cmd_move(access_token, sp_path, args.destination, site_id, drive_id)
    elif args.command == "delete_folder":
        cmd_delete_folder(access_token, sp_path, site_id, drive_id)


if __name__ == "__main__":
    main()
