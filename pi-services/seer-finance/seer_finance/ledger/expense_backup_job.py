"""Scheduled, SQLite-consistent expense-ledger backup and restore verification."""
from __future__ import annotations
import os

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .backup_restore import create_backup, verify_backup

ROOT = Path(os.environ.get('SEER_FINANCE_ROOT', '/var/lib/seer-finance'))
DATABASE = ROOT / 'data' / 'expense-ledger.sqlite3'
BACKUPS = ROOT / 'backups' / 'scheduled'
HEALTH = ROOT / 'data' / 'expense-ledger-health.json'
RETENTION_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temp.replace(path)


def _watermark() -> str:
    con = sqlite3.connect(DATABASE)
    try:
        value = con.execute('select max(observed_timestamp) from expenses').fetchone()[0]
        return value or 'no-captured-expenses'
    finally:
        con.close()


def _prune(now: datetime) -> None:
    cutoff = now - timedelta(days=RETENTION_DAYS)
    for path in BACKUPS.glob('expense-ledger-*'):
        if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
            path.unlink()


def main() -> int:
    now = _now()
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    try:
        if not DATABASE.exists():
            raise RuntimeError('production expense ledger database is absent')
        BACKUPS.mkdir(parents=True, exist_ok=True)
        backup = BACKUPS / f'expense-ledger-{stamp}.sqlite3'
        manifest = BACKUPS / f'expense-ledger-{stamp}.manifest.json'
        restore = BACKUPS / f'expense-ledger-{stamp}.restore-check.sqlite3'
        restore_manifest = BACKUPS / f'expense-ledger-{stamp}.restore-check.manifest.json'
        created = create_backup(source=DATABASE, backup_destination=backup, manifest_destination=manifest, source_watermark=_watermark())
        verified = verify_backup(backup=backup, backup_manifest=manifest, verification_destination=restore, verification_manifest_destination=restore_manifest, source_path=DATABASE)
        _prune(now)
        _atomic(HEALTH, {'status': 'ok', 'checked_at': now.isoformat(), 'last_successful_backup': str(backup), 'backup_manifest': str(manifest), 'restore_verification_manifest': str(restore_manifest), 'source_watermark': _watermark(), 'retention_days': RETENTION_DAYS})
        print(json.dumps({'status': 'ok', 'backup': created['backup_path'], 'verification': verified['integrity_check']}))
        return 0
    except Exception as exc:
        _atomic(HEALTH, {'status': 'blocked', 'checked_at': now.isoformat(), 'error': f'{type(exc).__name__}:{exc}'})
        raise

if __name__ == '__main__':
    raise SystemExit(main())
