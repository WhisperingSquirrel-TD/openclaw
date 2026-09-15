#!/usr/bin/env python3
"""Content-addressed SharePoint skill-library primitives.

The canonical skill file is overwritten in place. SharePoint native version
history is the sole release history; the manifest carries current content
hashes and canonical paths only, never a release counter.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle_files(directory: Path) -> list[dict[str, Any]]:
    files = []
    for path in sorted(p for p in directory.rglob('*') if p.is_file()):
        raw = path.read_bytes()
        files.append({'path': path.relative_to(directory).as_posix(), 'bytes': len(raw), 'sha256': sha256(raw)})
    return files


def bundle_hash(files: list[dict[str, Any]]) -> str:
    canonical = '\n'.join(f"{x['path']}\0{x['bytes']}\0{x['sha256']}" for x in files).encode()
    return sha256(canonical)


def release_record(canonical_path: str, directory: Path) -> dict[str, Any]:
    files = bundle_files(directory)
    return {'canonical_path': canonical_path.strip('/'), 'bundle_sha256': bundle_hash(files), 'files': files}


def validate_release(record: dict[str, Any]) -> None:
    required = {'canonical_path', 'bundle_sha256', 'files'}
    if not required <= set(record) or 'version' in record:
        raise ValueError('release record must be content-addressed with no version counter')
    paths = [x.get('path') for x in record['files']]
    if len(paths) != len(set(paths)) or any(not p or '..' in Path(p).parts for p in paths):
        raise ValueError('release file list invalid')
    if bundle_hash(record['files']) != record['bundle_sha256']:
        raise ValueError('bundle hash does not match listed files')


def manifest_template(releases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for record in releases.values():
        validate_release(record)
    return {'schema_version': SCHEMA_VERSION, 'skills': releases}


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get('schema_version') != SCHEMA_VERSION or not isinstance(manifest.get('skills'), dict):
        raise ValueError('manifest schema invalid')
    paths = []
    for skill_id, record in manifest['skills'].items():
        if not skill_id or not isinstance(record, dict):
            raise ValueError('manifest skill key/record invalid')
        validate_release(record)
        paths.append(record['canonical_path'])
    if len(paths) != len(set(paths)):
        raise ValueError('duplicate canonical paths')


def permitted_pull(local_bundle: str | None, remote: dict[str, Any]) -> str:
    """Return new|update|noop or raise when content/state is unsafe."""
    validate_release(remote)
    remote_bundle = remote['bundle_sha256']
    if local_bundle is None:
        return 'new'
    return 'noop' if local_bundle == remote_bundle else 'update'
