#!/usr/bin/env python3
from __future__ import annotations

import io
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
LOG_FILE = WORKSPACE / 'memory/sharepoint-backup-log.txt'
BACKUP_ROOT = '/OpenClaw Backups'
TODAY = datetime.now(timezone.utc).strftime('%Y-%m-%d')
STAMP = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
RETENTION_DAYS = 7

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


def upload_file(access_token: str, site_id: str, drive_id: str, local_path: Path, sp_path: str) -> None:
    size = local_path.stat().st_size
    if size < 4 * 1024 * 1024:
        url = f"{sp.GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/root:/{sp_path.strip('/')}:/content"
        with local_path.open('rb') as f:
            resp = requests.put(url, headers={**graph_headers(access_token), 'Content-Type': 'application/octet-stream'}, data=f, timeout=120)
        if not resp.ok:
            raise RuntimeError(f'Upload failed for {sp_path}: {resp.status_code} {resp.text[:300]}')
        return

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

    for p in artifacts:
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

    write_state({
        'updated_utc': datetime.now(timezone.utc).isoformat(),
        'backup_root': BACKUP_ROOT,
        'snapshot_date': TODAY,
        'artifacts': [{'name': p.name, 'size': p.stat().st_size} for p in artifacts],
        'status': 'ok',
    })
    log('SharePoint backup completed successfully.')


if __name__ == '__main__':
    main()
