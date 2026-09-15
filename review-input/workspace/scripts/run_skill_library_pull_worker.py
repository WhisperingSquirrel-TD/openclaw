#!/usr/bin/env python3
"""Pi-native autonomous wrapper for the version-gated SharePoint skill pull.

No chat/TOTP interaction. It calls the release synchroniser, retains bounded
machine-readable proof, and emits health state. A conflict/error never changes
local skill files beyond releases proven safe by the synchroniser.
"""
from __future__ import annotations
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path('/home/tomdean88/.openclaw/workspace')
SYNC = WORKSPACE / 'scripts/sync_skill_library_from_sharepoint.py'
RUNTIME = Path('/home/tomdean88/.openclaw/runtime/skill-library-sync')
STATE = RUNTIME / 'worker-state.json'
LOG = RUNTIME / 'worker.log'
MAX_LOG_LINES = 200

def now(): return datetime.now(timezone.utc).isoformat()
def write_atomic(path: Path, content: str):
    temp = path.with_suffix('.tmp'); temp.write_text(content); temp.replace(path)
def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    started = now()
    result = subprocess.run([sys.executable, str(SYNC)], cwd=WORKSPACE, text=True, capture_output=True, timeout=900)
    raw = (result.stdout or '').strip()
    try: summary = json.loads(raw) if raw else {}
    except json.JSONDecodeError: summary = {'raw_output': raw[-2000:]}
    state = {
        'last_run_utc': now(), 'started_utc': started, 'exit_code': result.returncode,
        'applied': summary.get('applied', []), 'conflicts': summary.get('conflicts', []),
        'errors': summary.get('errors', []), 'stderr': (result.stderr or '')[-2000:],
        'status': 'ok' if result.returncode == 0 else 'blocked',
    }
    write_atomic(STATE, json.dumps(state, indent=2) + '\n')
    line = f"{state['last_run_utc']} status={state['status']} applied={len(state['applied'])} conflicts={len(state['conflicts'])} errors={len(state['errors'])}\n"
    existing = LOG.read_text().splitlines() if LOG.exists() else []
    write_atomic(LOG, '\n'.join((existing + [line.rstrip()])[-MAX_LOG_LINES:]) + '\n')
    print(json.dumps(state, indent=2))
    return result.returncode
if __name__ == '__main__':
    try: raise SystemExit(main())
    except subprocess.TimeoutExpired:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        write_atomic(STATE, json.dumps({'last_run_utc':now(),'status':'blocked','reason':'synchroniser timeout'},indent=2)+'\n')
        raise SystemExit(2)
