#!/usr/bin/env python3
from __future__ import annotations

import io
import base64
import hashlib
import json
import os
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

import sys
sys.path.insert(0, '/home/tomdean88/.openclaw/integrations/microsoft-l1')
import sharepoint as sp

ROOT = Path('/home/tomdean88')
OPENCLAW = ROOT / '.openclaw'
WORKSPACE = OPENCLAW / 'workspace'
INTEGRATIONS = OPENCLAW / 'integrations'
PROSPECTOR = ROOT / 'prospector'
PROSPECTS = ROOT / 'prospects'
AUDIT_EXPORTS = WORKSPACE / 'reference/pi-audit-exports/2026-06-03'
TMP_ROOT = OPENCLAW / 'tmp/sharepoint-backup-staging'
STATE_FILE = OPENCLAW / 'integrations/microsoft/sharepoint-backup-state.json'
LOCAL_CLEANUP_JOURNAL = OPENCLAW / 'integrations/microsoft/sharepoint-local-archive-cleanup.json'
LOG_FILE = WORKSPACE / 'memory/sharepoint-backup-log.txt'
BACKUP_ROOT = '/OpenClaw Backups'
TODAY = datetime.now(timezone.utc).strftime('%Y-%m-%d')
STAMP = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
RETENTION_DAYS = 7
LOCAL_BACKUP_ROOT = ROOT / 'l1-backups'
LOCAL_BACKUP_REMOTE_ROOT = f'{BACKUP_ROOT}/local-archives'
LOCAL_BACKUP_PATTERNS = ('l1-config-*.tar.gz', 'l1-vault-*.tar.gz')

RUNBOOK_FILES = [
    'reference/PI-PORTABILITY-BACKUP-PLAN.md',
    'reference/PI-BACKUP-IMPLEMENTATION-CHECKLIST.md',
    'reference/PI-BACKUP-SCOPE.md',
    'reference/PI-INVENTORY.md',
    'reference/PI-SECRETS-RECOVERY-MAP.md',
    'reference/PI-RESTORE-RUNBOOK.md',
]

EXCLUDE_NAMES = {
    '.git', 'node_modules', '__pycache__', '.pytest_cache', 'tmp', '.venv'
}
EXCLUDE_SUFFIXES = {
    '.tmp', '.log', '.pyc', '.tar', '.gz'
}
EXCLUDE_REL_PATTERNS = [
    'reference/pi-audit-exports',
    'sharepoint-cache',
]
EXCLUDE_FILES = {
    'ASSISTANT_EXTERNAL.md', 'ASSISTANT_INBOX.md',
    'GMAIL_EXTERNAL.md', 'GMAIL_INBOX.md',
    'MICROSOFT_EXTERNAL.md', 'MICROSOFT_INBOX.md',
    'OUTLOOK_CALENDAR.md', 'GOOGLE_CALENDAR.md',
    'STACKSTONE_ENQUIRIES.md', 'STACKSTONE_LEADS.md', 'STACKSTONE_REPORTS.md',
    'WHATSAPP_LOG.md', 'WHATSAPP_RECENT.md', 'SYSTEM_HEALTH.md',
    'GARMIN_DAILY.md', 'INVOICE_TRACKER.md', 'INVOICE_TRACKER.json',
    'memory/last-seen-emails.md',
}


def log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(f'[{ts}] [sharepoint-backup] {msg}\n')
    print(msg)


def write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def _write_cleanup_journal(journal: dict):
    LOCAL_CLEANUP_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    temporary = LOCAL_CLEANUP_JOURNAL.with_suffix('.tmp')
    temporary.write_text(json.dumps(journal, indent=2), encoding='utf-8')
    os.replace(temporary, LOCAL_CLEANUP_JOURNAL)


def _read_cleanup_journal() -> dict:
    try:
        return json.loads(LOCAL_CLEANUP_JOURNAL.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def should_exclude(rel: str, path: Path) -> bool:
    rel = rel.lstrip('./')
    if any(rel == p or rel.startswith(p + '/') for p in EXCLUDE_REL_PATTERNS):
        return True
    if rel in EXCLUDE_FILES:
        return True
    if path.name in EXCLUDE_NAMES:
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    return False


def add_path_to_tar(tf: tarfile.TarFile, src: Path, arc_prefix: str = ''):
    if not src.exists():
        return
    if src.is_file():
        rel = f'{arc_prefix}{src.name}' if arc_prefix else src.name
        if should_exclude(rel, src):
            return
        tf.add(src, arcname=rel, recursive=False)
        return

    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        rel_root = root_path.relative_to(src)
        dirs[:] = [d for d in dirs if not should_exclude(str((rel_root / d)).replace('\\','/'), root_path / d)]
        for f in files:
            p = root_path / f
            rel = str((rel_root / f)).replace('\\', '/')
            rel_with_prefix = f'{arc_prefix}{rel}' if arc_prefix else rel
            if should_exclude(rel_with_prefix, p):
                continue
            tf.add(p, arcname=rel_with_prefix, recursive=False)


def create_tar(output: Path, entries: Iterable[tuple[Path, str]]):
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz') as tf:
        for src, prefix in entries:
            add_path_to_tar(tf, src, prefix)
    return output


def graph_headers(access_token: str) -> dict:
    return {'Authorization': f'Bearer {access_token}'}


def ensure_folder(access_token: str, site_id: str, drive_id: str, sp_path: str) -> None:
    sp_path = '/' + sp_path.strip('/')
    parts = [p for p in sp_path.strip('/').split('/') if p]
    current = ''
    for part in parts:
        current = f'{current}/{part}'
        meta_url = f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{current.strip('/')}"
        resp = requests.get(meta_url, headers=graph_headers(access_token), timeout=30)
        if resp.status_code == 200:
            continue
        if resp.status_code != 404:
            raise RuntimeError(f'Folder lookup failed for {current}: {resp.status_code} {resp.text[:300]}')
        parent = '/'.join(current.strip('/').split('/')[:-1])
        parent_url = f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root/children" if not parent else f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{parent}:/children"
        payload = {
            'name': part,
            'folder': {},
            '@microsoft.graph.conflictBehavior': 'replace'
        }
        create = requests.post(parent_url, headers={**graph_headers(access_token), 'Content-Type': 'application/json'}, json=payload, timeout=30)
        if create.status_code not in (200, 201):
            raise RuntimeError(f'Folder create failed for {current}: {create.status_code} {create.text[:300]}')


def delete_folder_if_exists(access_token: str, site_id: str, drive_id: str, sp_path: str) -> bool:
    url = f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{sp_path.strip('/')}"
    resp = requests.get(url, headers=graph_headers(access_token), timeout=30)
    if resp.status_code == 404:
        return False
    if not resp.ok:
        raise RuntimeError(f'Folder lookup failed for delete {sp_path}: {resp.status_code} {resp.text[:300]}')
    del_resp = requests.delete(url, headers=graph_headers(access_token), timeout=60)
    if del_resp.status_code not in (204, 200):
        raise RuntimeError(f'Folder delete failed for {sp_path}: {del_resp.status_code} {del_resp.text[:300]}')
    return True


def _local_sha1_base64(local_path: Path) -> str:
    digest = hashlib.sha1()
    with local_path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode('ascii')


def _local_sha256(local_path: Path) -> str:
    digest = hashlib.sha256()
    with local_path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _remote_item(access_token: str, site_id: str, drive_id: str, sp_path: str) -> dict:
    url = f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{sp_path.strip('/')}"
    resp = requests.get(url, headers=graph_headers(access_token), timeout=60)
    if resp.status_code == 404:
        raise FileNotFoundError(sp_path)
    if not resp.ok:
        raise RuntimeError(f'Remote verification lookup failed for {sp_path}: {resp.status_code} {resp.text[:300]}')
    item = resp.json()
    if 'folder' in item or 'file' not in item:
        raise RuntimeError(f'Remote verification target is not a file: {sp_path}')
    return item


def verify_remote_file(
    access_token: str,
    site_id: str,
    drive_id: str,
    local_path: Path,
    sp_path: str,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
) -> dict:
    """Re-read a remote item and prove it matches the local source.

    SharePoint commonly returns a base64 SHA-1 in file.hashes. When it does
    not, download the remote content and compare SHA-256 instead. Size alone
    is deliberately never considered sufficient proof for local deletion.
    """
    item = _remote_item(access_token, site_id, drive_id, sp_path)
    local_size = local_path.stat().st_size if expected_size is None else expected_size
    if item.get('size') != local_size:
        raise RuntimeError(
            f'Remote size mismatch for {sp_path}: remote={item.get("size")} local={local_size}'
        )

    hashes = item.get('file', {}).get('hashes', {})
    remote_sha1 = hashes.get('sha1Hash')
    if remote_sha1:
        local_sha1 = _local_sha1_base64(local_path)
        if remote_sha1 != local_sha1:
            raise RuntimeError(f'Remote SHA-1 mismatch for {sp_path}')
        proof = {'algorithm': 'sha1', 'digest': local_sha1}
    else:
        url = f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{sp_path.strip('/')}:/content"
        resp = requests.get(
            url,
            headers=graph_headers(access_token),
            timeout=300,
            allow_redirects=True,
            stream=True,
        )
        if not resp.ok:
            raise RuntimeError(f'Remote content verification failed for {sp_path}: {resp.status_code}')
        remote_digest = hashlib.sha256()
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            remote_digest.update(chunk)
        local_digest = expected_sha256 or _local_sha256(local_path)
        if remote_digest.hexdigest() != local_digest:
            raise RuntimeError(f'Remote SHA-256 mismatch for {sp_path}')
        proof = {'algorithm': 'sha256', 'digest': local_digest}

    return {
        'path': sp_path,
        'item_id': item.get('id'),
        'etag': item.get('eTag'),
        'size': item.get('size'),
        'proof': proof,
    }


def upload_file(access_token: str, site_id: str, drive_id: str, local_path: Path, sp_path: str) -> dict:
    size = local_path.stat().st_size
    if size < 4 * 1024 * 1024:
        url = f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{sp_path.strip('/')}:/content"
        with local_path.open('rb') as f:
            resp = requests.put(url, headers={**graph_headers(access_token), 'Content-Type': 'application/octet-stream'}, data=f, timeout=120)
        if not resp.ok:
            raise RuntimeError(f'Upload failed for {sp_path}: {resp.status_code} {resp.text[:300]}')
        return resp.json()

    session_url = f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{sp_path.strip('/')}:/createUploadSession"
    session_payload = {'item': {'@microsoft.graph.conflictBehavior': 'replace'}}
    session = requests.post(session_url, headers={**graph_headers(access_token), 'Content-Type': 'application/json'}, json=session_payload, timeout=60)
    if not session.ok:
        raise RuntimeError(f'Create upload session failed for {sp_path}: {session.status_code} {session.text[:300]}')
    upload_url = session.json()['uploadUrl']

    chunk_size = 5 * 1024 * 1024
    sent = 0
    with local_path.open('rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            start = sent
            end = sent + len(chunk) - 1
            headers = {
                'Content-Length': str(len(chunk)),
                'Content-Range': f'bytes {start}-{end}/{size}'
            }
            resp = requests.put(upload_url, headers=headers, data=chunk, timeout=300)
            if resp.status_code not in (200, 201, 202):
                raise RuntimeError(f'Chunk upload failed for {sp_path}: {resp.status_code} {resp.text[:300]}')
            sent += len(chunk)
    return resp.json()


def _local_archive_files() -> list[Path]:
    """Return only the explicitly generated archive names at the backup root."""
    if not LOCAL_BACKUP_ROOT.is_dir() or LOCAL_BACKUP_ROOT.is_symlink():
        return []
    files: set[Path] = set()
    for pattern in LOCAL_BACKUP_PATTERNS:
        files.update(
            path for path in LOCAL_BACKUP_ROOT.glob(pattern)
            if path.is_file() and not path.is_symlink() and path.parent == LOCAL_BACKUP_ROOT
        )
    return sorted(files)


def cleanup_uploaded_local_archives(
    access_token: str,
    site_id: str,
    drive_id: str,
) -> list[dict]:
    """Upload, independently verify, and remove old local backup archives.

    Recent archives are retained locally. Every older candidate is kept unless
    its deterministic SharePoint counterpart is proven to match exactly and
    the local file has not changed during the operation.
    """
    cutoff = datetime.now().timestamp() - (RETENTION_DAYS * 24 * 60 * 60)
    outcomes: list[dict] = []
    journal = _read_cleanup_journal()
    for local_path in _local_archive_files():
        journal_key = str(local_path)
        if local_path.stat().st_mtime > cutoff:
            outcomes.append({'file': str(local_path), 'status': 'retained_recent'})
            continue

        remote_path = f'{LOCAL_BACKUP_REMOTE_ROOT}/{local_path.name}'
        try:
            before = local_path.stat()
            expected_size = before.st_size
            expected_sha256 = _local_sha256(local_path)
            prior = journal.get(journal_key, {})
            prior_matches = (
                prior.get('remote_path') == remote_path
                and prior.get('size') == expected_size
                and prior.get('sha256') == expected_sha256
                and prior.get('mtime_ns') == before.st_mtime_ns
                and prior.get('status') in ('uploaded', 'verified')
            )
            proof = None
            if prior_matches:
                try:
                    proof = verify_remote_file(
                        access_token, site_id, drive_id, local_path, remote_path,
                        expected_size=expected_size, expected_sha256=expected_sha256,
                    )
                    log(f'Resumed verified local archive without re-upload: {local_path}')
                except Exception:
                    log(f'Previous remote proof is no longer valid; re-uploading: {local_path}')

            if proof is None:
                journal[journal_key] = {
                    'remote_path': remote_path,
                    'size': expected_size,
                    'sha256': expected_sha256,
                    'mtime_ns': before.st_mtime_ns,
                    'status': 'pending',
                    'updated_utc': datetime.now(timezone.utc).isoformat(),
                }
                _write_cleanup_journal(journal)
                upload_file(access_token, site_id, drive_id, local_path, remote_path)
                journal[journal_key].update({
                    'status': 'uploaded',
                    'updated_utc': datetime.now(timezone.utc).isoformat(),
                })
                _write_cleanup_journal(journal)
                proof = verify_remote_file(
                    access_token, site_id, drive_id, local_path, remote_path,
                    expected_size=expected_size, expected_sha256=expected_sha256,
                )
            after = local_path.stat()
            if after.st_size != expected_size or after.st_mtime_ns != before.st_mtime_ns:
                raise RuntimeError('Local archive changed during upload; deletion refused')
            journal[journal_key].update({
                'status': 'verified',
                'remote_item_id': proof.get('item_id'),
                'remote_etag': proof.get('etag'),
                'proof': proof.get('proof'),
                'updated_utc': datetime.now(timezone.utc).isoformat(),
            })
            _write_cleanup_journal(journal)
            local_path.unlink()
            journal[journal_key].update({
                'status': 'deleted',
                'updated_utc': datetime.now(timezone.utc).isoformat(),
            })
            _write_cleanup_journal(journal)
            outcomes.append({
                'file': str(local_path),
                'remote_path': remote_path,
                'status': 'deleted_after_verified_upload',
                'proof': proof,
            })
            log(f'✓ Verified and deleted local archive: {local_path} -> {remote_path}')
        except Exception as exc:
            outcomes.append({
                'file': str(local_path),
                'remote_path': remote_path,
                'status': 'retained_upload_or_verification_failed',
                'error': str(exc),
            })
            log(f'WARN: Kept local archive after failed verification: {local_path}: {exc}')
    return outcomes


def main():
    sp._load_dotenv()
    class Args: pass
    args = Args(); args.account='assistant'; args.token_file=None
    access = sp.get_access_token(args)
    site_id, drive_id = sp._resolve_site_and_drive(access)

    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    current_core = TMP_ROOT / 'current/core'
    current_sensitive = TMP_ROOT / 'current/sensitive'
    current_inventory = TMP_ROOT / 'current/inventory'
    current_runbooks = TMP_ROOT / 'current/runbooks'
    snapshot_root = TMP_ROOT / 'snapshots' / TODAY
    for p in [current_core, current_sensitive, current_inventory, current_runbooks, snapshot_root]:
        p.mkdir(parents=True, exist_ok=True)

    artifacts = []
    artifacts.append(create_tar(current_core / 'workspace.tar.gz', [(WORKSPACE, 'workspace/')]))
    artifacts.append(create_tar(current_core / 'integrations.tar.gz', [(INTEGRATIONS, 'integrations/')]))
    if PROSPECTOR.exists():
        artifacts.append(create_tar(current_core / 'prospector.tar.gz', [(PROSPECTOR, 'prospector/')]))
    if PROSPECTS.exists():
        artifacts.append(create_tar(current_core / 'prospects.tar.gz', [(PROSPECTS, 'prospects/')]))

    for cfg in [OPENCLAW / 'openclaw.json', OPENCLAW / 'sharepoint-queue.json']:
        if cfg.exists():
            target = current_core / cfg.name
            target.write_bytes(cfg.read_bytes())
            artifacts.append(target)

    sensitive_entries = []
    for p in [OPENCLAW / '.env', OPENCLAW / 'credentials', OPENCLAW / 'oauth', OPENCLAW / 'identity', ROOT / '.garth']:
        if p.exists():
            sensitive_entries.append((p, f'{p.name}/' if p.is_dir() else ''))
    if sensitive_entries:
        artifacts.append(create_tar(current_sensitive / 'sensitive.tar.gz', sensitive_entries))

    if AUDIT_EXPORTS.exists():
        artifacts.append(create_tar(current_inventory / 'inventory-exports.tar.gz', [(AUDIT_EXPORTS, 'pi-audit-exports/')]))

    runbook_entries = []
    for rel in RUNBOOK_FILES:
        src = WORKSPACE / rel
        if src.exists():
            runbook_entries.append((src, ''))
    if runbook_entries:
        artifacts.append(create_tar(current_runbooks / 'runbooks.tar.gz', runbook_entries))

    log(f'Staging complete. Artifacts: {[p.name for p in artifacts]}')

    manifest = {
        'updated_utc': datetime.now(timezone.utc).isoformat(),
        'backup_root': BACKUP_ROOT,
        'site_id': site_id,
        'drive_id': drive_id,
        'artifacts': [{'name': p.name, 'size': p.stat().st_size, 'local_path': str(p)} for p in artifacts],
    }
    manifest_path = TMP_ROOT / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    artifacts.append(manifest_path)

    remote_dirs = [
        f'{BACKUP_ROOT}/current/core',
        f'{BACKUP_ROOT}/current/sensitive',
        f'{BACKUP_ROOT}/current/inventory',
        f'{BACKUP_ROOT}/current/runbooks',
        f'{BACKUP_ROOT}/snapshots/{TODAY}/core',
        f'{BACKUP_ROOT}/snapshots/{TODAY}/sensitive',
        f'{BACKUP_ROOT}/snapshots/{TODAY}/inventory',
        f'{BACKUP_ROOT}/snapshots/{TODAY}/runbooks',
        LOCAL_BACKUP_REMOTE_ROOT,
    ]
    for d in remote_dirs:
        ensure_folder(access, site_id, drive_id, d)

    # Retention: keep only the most recent N daily snapshot folders.
    snapshots_root = f'{BACKUP_ROOT}/snapshots'
    try:
        url = f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{snapshots_root.strip('/')}:/children"
        resp = requests.get(url, headers=graph_headers(access), timeout=30)
        if resp.ok:
            folders = []
            for item in resp.json().get('value', []):
                if 'folder' in item and item.get('name', '').count('-') == 2:
                    folders.append(item['name'])
            folders = sorted(folders)
            if len(folders) > RETENTION_DAYS:
                for old in folders[:-RETENTION_DAYS]:
                    old_path = f'{snapshots_root}/{old}'
                    log(f'Retention pruning old snapshot folder {old_path}')
                    delete_folder_if_exists(access, site_id, drive_id, old_path)
    except Exception as e:
        log(f'WARN: retention pruning skipped: {e}')

    artifact_proofs = []
    for p in artifacts:
        before = p.stat()
        expected_size = before.st_size
        expected_sha256 = _local_sha256(p)
        if p.parent == current_core:
            targets = [f'{BACKUP_ROOT}/current/core/{p.name}', f'{BACKUP_ROOT}/snapshots/{TODAY}/core/{p.name}']
        elif p.parent == current_sensitive:
            targets = [f'{BACKUP_ROOT}/current/sensitive/{p.name}', f'{BACKUP_ROOT}/snapshots/{TODAY}/sensitive/{p.name}']
        elif p.parent == current_inventory:
            targets = [f'{BACKUP_ROOT}/current/inventory/{p.name}', f'{BACKUP_ROOT}/snapshots/{TODAY}/inventory/{p.name}']
        elif p.parent == current_runbooks:
            targets = [f'{BACKUP_ROOT}/current/runbooks/{p.name}', f'{BACKUP_ROOT}/snapshots/{TODAY}/runbooks/{p.name}']
        else:
            targets = [f'{BACKUP_ROOT}/current/manifest.json', f'{BACKUP_ROOT}/snapshots/{TODAY}/manifest.json']
        for target in targets:
            log(f'Uploading {p.name} ({p.stat().st_size} bytes) -> {target}')
            upload_file(access, site_id, drive_id, p, target)
            proof = verify_remote_file(
                access, site_id, drive_id, p, target,
                expected_size=expected_size, expected_sha256=expected_sha256,
            )
            artifact_proofs.append(proof)
        after = p.stat()
        if after.st_size != expected_size or after.st_mtime_ns != before.st_mtime_ns:
            raise RuntimeError(f'Local staged artifact changed during upload; cleanup refused: {p}')

    local_archive_cleanup = cleanup_uploaded_local_archives(access, site_id, drive_id)

    write_state({
        'updated_utc': datetime.now(timezone.utc).isoformat(),
        'backup_root': BACKUP_ROOT,
        'snapshot_date': TODAY,
        'artifacts': [{'name': p.name, 'size': p.stat().st_size} for p in artifacts],
        'remote_proofs': artifact_proofs,
        'local_archive_cleanup': local_archive_cleanup,
        'status': 'ok',
    })
    for p in artifacts:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    for directory in sorted({p.parent for p in artifacts}, key=lambda path: len(path.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    log('SharePoint backup completed successfully.')


if __name__ == '__main__':
    main()
