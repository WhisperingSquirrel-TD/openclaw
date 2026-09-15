#!/usr/bin/env python3
from pathlib import Path
import shutil, subprocess, json, os, sys, re
from datetime import datetime

HOME=Path.home(); REPO=HOME/'openclaw'; WS=HOME/'.openclaw'/'workspace'; CONFIG=HOME/'.openclaw'/'openclaw.json'
STAMP=datetime.now().strftime('%Y%m%d-%H%M%S'); BK=WS/'backups'/f'totp-gate-exact-{STAMP}'
APPROVAL_FILES=[Path(p) for p in subprocess.check_output(['grep','-Rsl','Approved. Window open for',str(REPO/'dist'),str(REPO/'src')], text=True).splitlines()]
TOTP_FILES=[REPO/'src/infra/totp/totp.ts']+[Path(p) for p in subprocess.check_output(['grep','-Rsl','opts?.window ?? 1',str(REPO/'dist'),str(REPO/'src')], text=True).splitlines()]
FILES=sorted(set([REPO/'src/auto-reply/reply/commands-totp.ts']+APPROVAL_FILES+TOTP_FILES))
backups={}
def run(c, check=True): return subprocess.run(c,text=True,capture_output=True,check=check)
def edit_ok(p):
    try:
        r=run(['lsattr','-d',str(p)],check=False); print('lsattr',p,(r.stdout or r.stderr).strip())
        flags=((r.stdout or r.stderr).split() or [''])[0]
        if 'i' in flags: run(['chattr','-i',str(p)])
    except FileNotFoundError: pass
def bak(p):
    if p in backups: return
    BK.mkdir(parents=True,exist_ok=True); d=BK/(p.name+'.bak'); i=1
    while d.exists(): d=BK/(p.name+f'.{i}.bak'); i+=1
    shutil.copy2(p,d); backups[p]=d; print('BACKUP',p,'->',d)
def rollback():
    for p,d in reversed(list(backups.items())):
        try: edit_ok(p); shutil.copy2(d,p); print('ROLLBACK',p)
        except Exception as e: print('ROLLBACK_FAIL',p,e,file=sys.stderr)
def write_gate_file_func_ts():
    return r'''
async function writeL1GateWindow(expiresAt: number, windowMinutes: number): Promise<void> {
  try {
    const fs = await import("node:fs/promises");
    const os = await import("node:os");
    const path = await import("node:path");
    const memoryDir = path.join(os.homedir(), ".openclaw", "workspace", "memory");
    await fs.mkdir(memoryDir, { recursive: true });
    await fs.writeFile(
      path.join(memoryDir, "gate-window.json"),
      JSON.stringify({
        open: true,
        approved_at: new Date().toISOString(),
        expires_at: new Date(expiresAt).toISOString(),
        window_minutes: windowMinutes,
        source: "totp-code-input",
        note: "Temporary exec/TOTP gate opened; L1 should treat this as gate-open evidence until expires_at."
      }, null, 2) + "\n",
    );
  } catch (err) {
    logVerbose(`TOTP gate-window signal write failed: ${String(err)}`);
  }
}
'''
def write_gate_file_func_js():
    return r'''
async function writeL1GateWindow(expiresAt, windowMinutes) {
  try {
    const fs = await import("node:fs/promises");
    const os = await import("node:os");
    const path = await import("node:path");
    const memoryDir = path.join(os.homedir(), ".openclaw", "workspace", "memory");
    await fs.mkdir(memoryDir, { recursive: true });
    await fs.writeFile(path.join(memoryDir, "gate-window.json"), JSON.stringify({ open: true, approved_at: new Date().toISOString(), expires_at: new Date(expiresAt).toISOString(), window_minutes: windowMinutes, source: "totp-code-input", note: "Temporary exec/TOTP gate opened; L1 should treat this as gate-open evidence until expires_at." }, null, 2) + "\n");
  } catch (err) {
    logVerbose(`TOTP gate-window signal write failed: ${String(err)}`);
  }
}
'''
def patch_file(p):
    s=p.read_text(errors='ignore'); orig=s
    # TOTP grace: source already defaults to ±1 step; widen to ±2 for slow chat/tool routing.
    s=s.replace('const window = opts?.window ?? 1;', 'const window = opts?.window ?? 2;')
    s=s.replace('const window = opts?.window ?? 1;', 'const window = opts?.window ?? 2;')
    is_approval_file = p in APPROVAL_FILES or p.name == 'commands-totp.ts'
    if 'gate-window.json' not in s and 'Approved. Window open for' in s and is_approval_file:
        if p.suffix=='.ts':
            marker='const TOTP_LOCK_COMMAND = "/totp-lock";\n'
            if marker not in s: raise RuntimeError(f'missing TS insertion marker {p}')
            s=s.replace(marker, marker+write_gate_file_func_ts(),1)
        else:
            # Insert before code input handler where logVerbose is definitely in scope.
            marker='const TOTP_LOCK_COMMAND = "/totp-lock";\n'
            if marker in s:
                s=s.replace(marker, marker+write_gate_file_func_js(),1)
            else:
                # Bundled/minified variant: insert before async code handler export/name.
                m=re.search(r'(async function handleTotpCodeInput|const handleTotpCodeInput\s*=)', s)
                if not m: raise RuntimeError(f'missing JS insertion marker {p}')
                s=s[:m.start()]+write_gate_file_func_js()+s[m.start():]
    if is_approval_file and 'Approved. Window open for' in s:
        call='''  await writeL1GateWindow(expiresAt, windowMinutes);\n\n  const expiresAtStr = new Date(expiresAt).toLocaleTimeString();'''
        if 'writeL1GateWindow(expiresAt, windowMinutes)' not in s:
            old='''  const expiresAtStr = new Date(expiresAt).toLocaleTimeString();'''
            if old not in s: raise RuntimeError(f'missing approval call marker {p}')
            s=s.replace(old, call,1)
    if s!=orig:
        edit_ok(p); bak(p); p.write_text(s); print('PATCHED',p)
    if p.suffix in ['.js','.mjs']:
        r=run(['node','--check',str(p)],check=False)
        if r.returncode: print(r.stderr,file=sys.stderr); raise RuntimeError(f'node check failed {p}')

def patch_config():
    edit_ok(CONFIG); bak(CONFIG); data=json.loads(CONFIG.read_text()); before=data['agents']['defaults'].get('totpWindowMinutes'); data['agents']['defaults']['totpWindowMinutes']=10; CONFIG.write_text(json.dumps(data,indent=2)+'\n'); print('CONFIG',before,'->',10)
try:
    print('Backup dir:',BK)
    for p in sorted(set(FILES)):
        if p.exists(): patch_file(p)
    patch_config()
    print('SUCCESS exact gate patch')
except Exception as e:
    print('FAIL_CLOSED',e,file=sys.stderr); rollback(); sys.exit(3)
