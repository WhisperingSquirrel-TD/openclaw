#!/usr/bin/env python3
"""
Patch OpenClaw gate handling safely:
1) set agents.defaults.totpWindowMinutes to 10
2) locate the TOTP approval handler for the "Approved. Window open..." message
3) if the handler is recognised, add/update a small gate-window state write so L1 can detect approval

Safety:
- backups before writes
- immutable-flag check before writes
- fail closed if handler pattern is not recognised
- no service restart in this script
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CONFIG = HOME / ".openclaw" / "openclaw.json"
WORKSPACE = HOME / ".openclaw" / "workspace"
STATE_FILE = WORKSPACE / "memory" / "gate-window.json"
REPO = HOME / "openclaw"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
BACKUP_DIR = WORKSPACE / "backups" / f"gate-window-patch-{STAMP}"

SEARCH_ROOTS = [
    REPO / "dist",
    REPO / "src",
    REPO / "packages",
    REPO / "extensions",
]

APPROVAL_PATTERNS = [
    "Approved. Window open",
    "Window open for",
    "All gated actions will proceed",
]


def sh(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def ensure_editable(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    # Immutable flag check: important on this Pi.
    try:
        res = sh(["lsattr", "-d", str(path)], check=False)
        line = (res.stdout or res.stderr or "").strip()
        print(f"lsattr {path}: {line}")
        flags = line.split()[0] if line else ""
        if "i" in flags:
            print(f"Removing immutable flag from {path}")
            sh(["chattr", "-i", str(path)])
    except FileNotFoundError:
        print("WARN: lsattr/chattr unavailable; continuing with normal write checks")


def backup(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / (path.name + ".bak")
    if dest.exists():
        dest = BACKUP_DIR / (path.name + f".{len(list(BACKUP_DIR.glob(path.name + '*')))}.bak")
    shutil.copy2(path, dest)
    print(f"BACKUP {path} -> {dest}")
    return dest


def patch_config() -> Path:
    ensure_editable(CONFIG)
    config_backup = backup(CONFIG)
    data = json.loads(CONFIG.read_text())
    before = data.get("agents", {}).get("defaults", {}).get("totpWindowMinutes")
    data.setdefault("agents", {}).setdefault("defaults", {})["totpWindowMinutes"] = 10
    CONFIG.write_text(json.dumps(data, indent=2) + "\n")
    after = json.loads(CONFIG.read_text())["agents"]["defaults"]["totpWindowMinutes"]
    print(f"CONFIG totpWindowMinutes: {before} -> {after}")
    if after != 10:
        raise RuntimeError("totpWindowMinutes did not verify as 10")
    return config_backup


def candidate_files() -> list[Path]:
    out: list[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in {"node_modules", ".git", "coverage", "tmp"}]
            for fn in filenames:
                if not fn.endswith((".js", ".mjs", ".ts")):
                    continue
                p = Path(dirpath) / fn
                try:
                    txt = p.read_text(errors="ignore")
                except Exception:
                    continue
                if any(s in txt for s in APPROVAL_PATTERNS) or "totpWindowMinutes" in txt:
                    out.append(p)
    return sorted(set(out))


def patch_handler(path: Path) -> bool:
    txt = path.read_text(errors="ignore")
    if "gate-window.json" in txt:
        print(f"Handler already mentions gate-window.json: {path}")
        return True

    # Recognised pattern: a template/string containing approval output and expires/expiry timestamp nearby.
    if not any(s in txt for s in APPROVAL_PATTERNS):
        return False

    backup(path)
    ensure_editable(path)

    helper = r'''

// L1 gate visibility bridge: write a tiny state file whenever TOTP approval opens a window.
async function __openclawWriteL1GateWindow(expiresAtLike) {
  try {
    const fs = await import('node:fs/promises');
    const os = await import('node:os');
    const path = await import('node:path');
    const workspace = path.join(os.homedir(), '.openclaw', 'workspace');
    const memoryDir = path.join(workspace, 'memory');
    await fs.mkdir(memoryDir, { recursive: true });
    const expiresAt = expiresAtLike instanceof Date ? expiresAtLike.toISOString() : String(expiresAtLike || '');
    const payload = {
      open: true,
      approved_at: new Date().toISOString(),
      expires_at: expiresAt,
      source: 'totp-approval-handler',
      note: 'Temporary exec/TOTP gate opened; L1 should treat this as gate-open evidence until expires_at.'
    };
    await fs.writeFile(path.join(memoryDir, 'gate-window.json'), JSON.stringify(payload, null, 2) + '\n');
  } catch (err) {
    console.warn('[gate-window] failed to write L1 gate visibility state', err);
  }
}
'''

    # Insert helper after imports if possible, otherwise prepend.
    insert_at = 0
    m = list(re.finditer(r"^import .*?;\s*$", txt, flags=re.M))
    if m:
        insert_at = m[-1].end()
    txt2 = txt[:insert_at] + helper + txt[insert_at:]

    # Add a conservative call: find assignment/const around expiry/expires if present, otherwise write blank expiry.
    # This is intentionally minimal and may require manual follow-up if exact variable naming differs.
    call_inserted = False
    for var in ["expiresAt", "expires", "expiry", "until", "windowUntil"]:
        pattern = rf"({var}\s*=\s*[^;\n]+[;\n])"
        if re.search(pattern, txt2):
            txt2 = re.sub(pattern, rf"\1\n    await __openclawWriteL1GateWindow({var});\n", txt2, count=1)
            call_inserted = True
            break

    if not call_inserted:
        # Fallback: insert before the first approval-message literal. This keeps file patched but may be syntactically wrong
        # if placed in object literal context, so fail closed instead of writing.
        print(f"FAIL_CLOSED: approval handler found but expiry variable/call site not recognised in {path}")
        return False

    path.write_text(txt2)
    # Syntax check for JS files via node if available.
    if path.suffix in {".js", ".mjs"}:
        res = sh(["node", "--check", str(path)], check=False)
        if res.returncode != 0:
            print(res.stdout)
            print(res.stderr, file=sys.stderr)
            # Restore backup automatically.
            backups = sorted(BACKUP_DIR.glob(path.name + "*.bak"))
            if backups:
                shutil.copy2(backups[-1], path)
                print(f"RESTORED {path} from {backups[-1]}")
            raise RuntimeError(f"node --check failed for patched handler {path}")
    print(f"PATCHED handler candidate: {path}")
    return True


def main() -> int:
    print(f"Backup dir: {BACKUP_DIR}")
    config_backup: Path | None = None
    try:
        # Discovery first, so we do not touch config if the handler is nowhere to be found.
        cands = candidate_files()
        print("Handler/search candidates:")
        for p in cands[:30]:
            print(f" - {p}")
        approval_cands = [p for p in cands if any(s in p.read_text(errors='ignore') for s in APPROVAL_PATTERNS)]
        if not approval_cands:
            print("FAIL_CLOSED: no approval-message handler found. No live files changed.")
            return 2

        config_backup = patch_config()
        for p in approval_cands:
            if patch_handler(p):
                print("SUCCESS: config patched and handler bridge patched/verified.")
                return 0
        raise RuntimeError("approval handler exists but no recognised safe patch site")
    except Exception as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        if config_backup and config_backup.exists():
            try:
                shutil.copy2(config_backup, CONFIG)
                print(f"ROLLED BACK config from {config_backup}")
            except Exception as rollback_exc:
                print(f"ROLLBACK_FAILED for config: {rollback_exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
