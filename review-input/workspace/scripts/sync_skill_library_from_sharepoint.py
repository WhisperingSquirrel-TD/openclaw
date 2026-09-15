#!/usr/bin/env python3
"""Content-addressed pull from the canonical SharePoint skill library.

SharePoint native version history is the release history. The local ledger is
only a hash/eTag receipt and never a version gate.
"""
from __future__ import annotations
import argparse, importlib.util, json, os, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from skill_library_release import sha256, bundle_files, bundle_hash, validate_manifest, permitted_pull

WORKSPACE = Path('/home/tomdean88/.openclaw/workspace')
STATE = Path('/home/tomdean88/.openclaw/runtime/skill-library-sync/hash-ledger.json')
ROOT = '/skills/openclaw-skill-estate'
DESTINATIONS = {'workspace-skills': WORKSPACE / 'skills', 'openclaw-skills': Path('/home/tomdean88/openclaw/skills')}

def sharepoint_client():
    spec = importlib.util.spec_from_file_location('sp', '/home/tomdean88/.openclaw/integrations/microsoft-l1/sharepoint.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module._load_dotenv()
    class Args: account = 'assistant'; token_file = None
    token = module.get_access_token(Args()); site_id, drive_id = module._resolve_site_and_drive(token)
    return f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}', {'Authorization': f'Bearer {token}'}

def get(base, headers, path):
    result = requests.get(base + f'/root:{path}:/content', headers=headers, timeout=90)
    if not result.ok: raise RuntimeError(f'GET {path}: {result.status_code} {result.text[:160]}')
    return result.content, result.headers.get('ETag')

def local_dir(canonical_path):
    source, separator, tail = canonical_path.strip('/').partition('/')
    if not separator or source not in DESTINATIONS or '..' in Path(tail).parts: raise ValueError(f'unsafe canonical path: {canonical_path}')
    return DESTINATIONS[source] / tail

def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True); fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.skill-sync-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def remote_bundle(base, headers, record):
    out = {}
    for entry in record['files']:
        raw, _ = get(base, headers, ROOT + '/' + record['canonical_path'] + '/' + entry['path'])
        if sha256(raw) != entry['sha256'] or len(raw) != entry['bytes']: raise RuntimeError(f"remote file mismatch: {entry['path']}")
        out[entry['path']] = raw
    reconstructed = [{'path': p, 'bytes': len(raw), 'sha256': sha256(raw)} for p, raw in sorted(out.items())]
    if bundle_hash(reconstructed) != record['bundle_sha256']: raise RuntimeError('remote bundle hash mismatch')
    return out

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--dry-run', action='store_true'); args = parser.parse_args()
    base, headers = sharepoint_client(); manifest_raw, manifest_etag = get(base, headers, ROOT + '/MANIFEST.json')
    manifest = json.loads(manifest_raw); validate_manifest(manifest)
    ledger = json.loads(STATE.read_text()) if STATE.exists() else {'schema_version': 1, 'skills': {}}
    next_ledger = {'schema_version': 1, 'updated_at_utc': datetime.now(timezone.utc).isoformat(), 'skills': dict(ledger.get('skills', {}))}
    applied, conflicts, errors = [], [], []
    for skill_id, record in manifest['skills'].items():
        try:
            local = local_dir(record['canonical_path'])
            local_hash = bundle_hash(bundle_files(local)) if local.exists() else None
            action = permitted_pull(local_hash, record)
            if action == 'noop':
                next_ledger['skills'][skill_id] = {'bundle_sha256': record['bundle_sha256'], 'canonical_path': record['canonical_path'], 'manifest_etag': manifest_etag}
                continue
            bundle = remote_bundle(base, headers, record)
            if args.dry_run: applied.append({'skill': skill_id, 'action': action, 'dry_run': True}); continue
            for relative, raw in bundle.items(): atomic_write(local / relative, raw)
            installed_hash = bundle_hash(bundle_files(local))
            if installed_hash != record['bundle_sha256']: raise RuntimeError('post-install local bundle verification failed')
            next_ledger['skills'][skill_id] = {'bundle_sha256': record['bundle_sha256'], 'canonical_path': record['canonical_path'], 'manifest_etag': manifest_etag}
            applied.append({'skill': skill_id, 'action': action})
        except Exception as exc: conflicts.append({'skill': skill_id, 'reason': str(exc)})
    if not args.dry_run: atomic_write(STATE, json.dumps(next_ledger, indent=2).encode())
    print(json.dumps({'applied': applied, 'conflicts': conflicts, 'errors': errors, 'ledger': str(STATE)}, indent=2))
    if conflicts or errors: raise SystemExit(1)
if __name__ == '__main__': main()
