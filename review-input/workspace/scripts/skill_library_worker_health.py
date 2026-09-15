#!/usr/bin/env python3
"""Exit non-zero if the autonomous skill-library pull worker is missing/stale/blocked."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
state_path=Path('/home/tomdean88/.openclaw/runtime/skill-library-sync/worker-state.json')
if not state_path.exists(): print('BLOCKED: worker has never run'); raise SystemExit(2)
state=json.loads(state_path.read_text())
try: age=(datetime.now(timezone.utc)-datetime.fromisoformat(state['last_run_utc'])).total_seconds()
except Exception: print('BLOCKED: invalid worker timestamp'); raise SystemExit(2)
if age>20*60: print(f'BLOCKED: worker stale ({age:.0f}s)'); raise SystemExit(2)
if state.get('status')!='ok': print('BLOCKED: '+json.dumps({'conflicts':state.get('conflicts',[]),'errors':state.get('errors',[]),'stderr':state.get('stderr','')})); raise SystemExit(2)
print(f"OK: worker fresh ({age:.0f}s), applied={len(state.get('applied',[]))}")
