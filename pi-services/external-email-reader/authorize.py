#!/usr/bin/env python3
"""Provision the separate read-only token used by external-email-reader.

The authorization flow is deliberately interactive, but the cache handling is
local and fail-closed: cache files are owner-only regular files, never
symlinks, and are replaced atomically. This helper requests Mail.Read only; it
cannot send mail, change mailbox rules, or alter the trusted-contact boundary.
"""

import os
import stat
import uuid
from pathlib import Path

import msal


CLIENT_ID = "57d4abf8-8d48-4f89-a8a8-3dd18ca57c57"
TENANT_ID = "f3f0da70-6bad-4320-975f-a468b8c565b9"
SCOPES = ["Mail.Read"]
TOKEN_FILE = Path.home() / ".openclaw/integrations/microsoft/token-external-microsoft-read.json"

PRIVATE_FILE_MODE = 0o600
PRIVATE_DIR_MODE = 0o700
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", None)


def _owner_uid() -> int | None:
    getuid = getattr(os, "getuid", None)
    return getuid() if getuid is not None else None


def _check_owner(path: Path, metadata: os.stat_result) -> None:
    owner_uid = _owner_uid()
    if owner_uid is not None and metadata.st_uid != owner_uid:
        raise PermissionError(f"Credentials path is not owned by the current user: {path}")


def _ensure_private_directory(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError(f"Credentials directory must not be a symlink: {path}")
    path.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    metadata = os.lstat(path)
    if not stat.S_ISDIR(metadata.st_mode):
        raise NotADirectoryError(f"Credentials path is not a directory: {path}")
    _check_owner(path, metadata)
    if stat.S_IMODE(metadata.st_mode) != PRIVATE_DIR_MODE:
        os.chmod(path, PRIVATE_DIR_MODE, follow_symlinks=False)
        metadata = os.lstat(path)
        if stat.S_IMODE(metadata.st_mode) != PRIVATE_DIR_MODE:
            raise PermissionError(f"Credentials directory is not owner-only: {path}")


def _ensure_private_directories(path: Path) -> None:
    """Create and validate the cache directory chain below the home directory."""
    parent = path.parent
    parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)

    home = Path.home()
    try:
        relative_parts = parent.relative_to(home).parts
    except ValueError:
        directories = (parent,)
    else:
        current = home
        directories = []
        for part in relative_parts:
            current /= part
            directories.append(current)

    for directory in directories:
        _ensure_private_directory(directory)


def _private_file_metadata(path: Path) -> os.stat_result:
    if path.is_symlink():
        raise RuntimeError(f"Credentials cache must not be a symlink: {path}")
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"Credentials cache must be a regular file: {path}")
    _check_owner(path, metadata)
    return metadata


def _read_private_cache(path: Path) -> str | None:
    """Read a cache without following links, repairing legacy broad modes."""
    _ensure_private_directories(path)
    try:
        metadata = _private_file_metadata(path)
    except FileNotFoundError:
        return None

    if stat.S_IMODE(metadata.st_mode) & 0o077:
        os.chmod(path, PRIVATE_FILE_MODE, follow_symlinks=False)

    if _O_NOFOLLOW is None:
        raise RuntimeError("Secure credential-cache reads require no-symlink filesystem support")
    fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"Credentials cache must be a regular file: {path}")
        _check_owner(path, metadata)
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise PermissionError(f"Credentials cache is not owner-only: {path}")
        with os.fdopen(fd, encoding="utf-8") as stream:
            fd = -1
            return stream.read()
    finally:
        if fd != -1:
            os.close(fd)


def _atomic_write_private_cache(path: Path, content: str) -> None:
    """Replace a credentials cache atomically using a fresh owner-only file."""
    _ensure_private_directories(path)
    if path.is_symlink():
        raise RuntimeError(f"Credentials cache must not be a symlink: {path}")
    if _O_NOFOLLOW is None:
        raise RuntimeError("Secure credential-cache writes require no-symlink filesystem support")

    descriptor = None
    temporary_path = None
    for _ in range(8):
        candidate = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        try:
            descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW,
                PRIVATE_FILE_MODE,
            )
        except FileExistsError:
            continue
        temporary_path = candidate
        break
    if descriptor is None or temporary_path is None:
        raise FileExistsError(f"Could not allocate a private temporary cache next to {path}")

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        metadata = _private_file_metadata(path)
        if stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE:
            raise PermissionError(f"Credentials cache is not owner-only: {path}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def main() -> None:
    cache = msal.SerializableTokenCache()
    serialized_cache = _read_private_cache(TOKEN_FILE)
    if serialized_cache is not None:
        cache.deserialize(serialized_cache)

    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache,
    )
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    if not isinstance(result, dict) or "access_token" not in result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(
                flow.get("error_description", "Microsoft device authorization could not start")
            )
        print(flow["message"], flush=True)
        result = app.acquire_token_by_device_flow(flow)
    if not isinstance(result, dict) or "access_token" not in result:
        error = result.get("error_description") if isinstance(result, dict) else None
        raise RuntimeError(error or "Microsoft device authorization failed")

    _atomic_write_private_cache(TOKEN_FILE, cache.serialize())
    print("External read-only Microsoft authorization complete.", flush=True)


if __name__ == "__main__":
    main()
