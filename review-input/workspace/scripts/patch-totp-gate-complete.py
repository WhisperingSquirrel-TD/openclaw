#!/usr/bin/env python3
"""
Complete TOTP gate patch, designed for a short approval window.

Goals:
1) Increase post-approval exec gate from 5 minutes to 10 minutes.
2) Add TOTP validation grace (accept adjacent 30s TOTP step where the verifier supports a window option).
3) Make successful approval visible to L1 by writing ~/.openclaw/workspace/memory/gate-window.json.

Safety:
- Discovery first.
- Back up every touched file before writing.
- Check immutable flags (lsattr/chattr -i) before writing.
- Patch only recognised patterns.
- JS syntax-check patched JS/MJS files.
- Roll back all touched files if any required change fails.
- Restart services is intentionally outside this script.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
CONFIG = HOME / ".openclaw" / "openclaw.json"
WORKSPACE = HOME / ".openclaw" / "workspace"
REPO = HOME / "openclaw"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
BACKUP_DIR = WORKSPACE / "backups" / f"totp-gate-complete-{STAMP}"

SEARCH_ROOTS = [REPO / "dist", REPO / "src", REPO / "packages", REPO / "extensions", HOME / ".openclaw" / "integrations"]
APPROVAL_MARKERS = ["Approved. Window open", "Window open for", "All gated actions will proceed"]
INVALID_MARKERS = ["Invalid code", "invalid code", "TOTP", "totp"]

backups: dict[Path, Path] = {}


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def ensure_editable(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        res = run(["lsattr", "-d", str(path)], check=False)
        line = (res.stdout or res.stderr or "").strip()
        print(f"lsattr {path}: {line}")
        flags = line.split()[0] if line else ""
        if "i" in flags:
            print(f"Removing immutable flag: {path}")
            run(["chattr", "-i", str(path)])
    except FileNotFoundError:
        print("WARN: lsattr/chattr unavailable; continuing")


def backup(path: Path) -> Path:
    if path in backups:
        return backups[path]
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / (path.name + ".bak")
    n = 1
    while dest.exists():
        dest = BACKUP_DIR / f"{path.name}.{n}.bak"
        n += 1
    shutil.copy2(path, dest)
    backups[path] = dest
    print(f"BACKUP {path} -> {dest}")
    return dest


def rollback() -> None:
    for path, bak in reversed(list(backups.items())):
        try:
            ensure_editable(path)
            shutil.copy2(bak, path)
            print(f"ROLLED BACK {path} <- {bak}")
        except Exception as exc:
            print(f"ROLLBACK FAILED {path}: {exc}", file=sys.stderr)


def read_text(path: Path) -> str:
    return path.read_text(errors="ignore")


def candidate_files() -> list[Path]:
    out: list[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in {"node_modules", ".git", "coverage", "tmp", "backups"}]
            for fn in filenames:
                if not fn.endswith((".js", ".mjs", ".ts", ".py", ".json")):
                    continue
                p = Path(dirpath) / fn
                try:
                    txt = read_text(p)
                except Exception:
                    continue
                if any(m in txt for m in APPROVAL_MARKERS + INVALID_MARKERS) or "totpWindowMinutes" in txt:
                    out.append(p)
    return sorted(set(out))


def patch_config() -> None:
    ensure_editable(CONFIG)
    backup(CONFIG)
    data = json.loads(CONFIG.read_text())
    before = data.get("agents", {}).get("defaults", {}).get("totpWindowMinutes")
    data.setdefault("agents", {}).setdefault("defaults", {})["totpWindowMinutes"] = 10
    CONFIG.write_text(json.dumps(data, indent=2) + "\n")
    after = json.loads(CONFIG.read_text())["agents"]["defaults"]["totpWindowMinutes"]
    print(f"CONFIG totpWindowMinutes: {before} -> {after}")
    if after != 10:
        raise RuntimeError("totpWindowMinutes did not verify as 10")


def patch_totp_grace(path: Path) -> bool:
    txt = read_text(path)
    original = txt

    # Python pyotp: totp.verify(code) or pyotp.TOTP(...).verify(code) supports valid_window=1.
    txt = re.sub(
        r"(\.verify\(\s*[^\)\n]+?)(\))",
        lambda m: m.group(0) if "valid_window" in m.group(0) else m.group(1) + ", valid_window=1" + m.group(2),
        txt,
    ) if path.suffix == ".py" and "verify(" in txt and ("TOTP" in txt or "pyotp" in txt or "Invalid code" in txt) else txt

    # speakeasy.totp.verify({...}) supports window: 1.
    def add_js_window(m: re.Match[str]) -> str:
        body = m.group(1)
        if "window" in body:
            return m.group(0)
        return "totp.verify({" + body.rstrip() + ", window: 1 })"

    if path.suffix in {".js", ".mjs", ".ts"}:
        txt = re.sub(r"totp\.verify\(\{([\s\S]{0,500}?token[\s\S]{0,500}?)\}\)", add_js_window, txt, count=1)
        # otplib authenticator.verify({ token, secret }) accepts window via options on some versions; avoid risky patch unless object already has options shape.
        txt = re.sub(
            r"authenticator\.verify\(\{([\s\S]{0,500}?token[\s\S]{0,500}?secret[\s\S]{0,500}?)\}\)",
            lambda m: m.group(0) if "window" in m.group(1) else "authenticator.verify({" + m.group(1).rstrip() + ", window: 1 })",
            txt,
            count=1,
        )

    if txt == original:
        return False
    ensure_editable(path)
    backup(path)
    path.write_text(txt)
    print(f"PATCHED TOTP grace in {path}")
    syntax_check(path)
    return True


def patch_gate_visibility(path: Path) -> bool:
    txt = read_text(path)
    if "gate-window.json" in txt:
        print(f"Gate visibility already present in {path}")
        return True
    if not any(m in txt for m in APPROVAL_MARKERS):
        return False

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

    # Insert after imports where possible.
    imports = list(re.finditer(r"^import .*?;\s*$", txt, flags=re.M))
    insert_at = imports[-1].end() if imports else 0
    txt2 = txt[:insert_at] + helper + txt[insert_at:]

    # Find an expiry variable after approval duration calculation.
    expiry_vars = ["expiresAt", "expires", "expiry", "until", "windowUntil", "approvedUntil"]
    call_inserted = False
    for var in expiry_vars:
        # Insert immediately after first assignment to that var.
        pat = rf"(^\s*(?:const|let|var)?\s*{var}\s*=\s*[^;\n]+[;\n])"
        if re.search(pat, txt2, flags=re.M):
            txt2 = re.sub(pat, rf"\1\n    await __openclawWriteL1GateWindow({var});\n", txt2, count=1, flags=re.M)
            call_inserted = True
            break

    if not call_inserted:
        # If the approval message itself uses an until/expires expression inside a template, do not guess.
        return False

    ensure_editable(path)
    backup(path)
    path.write_text(txt2)
    print(f"PATCHED L1 gate visibility in {path}")
    syntax_check(path)
    return True


def syntax_check(path: Path) -> None:
    if path.suffix in {".js", ".mjs"}:
        res = run(["node", "--check", str(path)], check=False)
        if res.returncode != 0:
            print(res.stdout)
            print(res.stderr, file=sys.stderr)
            raise RuntimeError(f"node --check failed for {path}")
    elif path.suffix == ".py":
        res = run(["python3", "-m", "py_compile", str(path)], check=False)
        if res.returncode != 0:
            print(res.stdout)
            print(res.stderr, file=sys.stderr)
            raise RuntimeError(f"py_compile failed for {path}")


def main() -> int:
    print(f"Backup dir: {BACKUP_DIR}")
    try:
        cands = candidate_files()
        print("Candidates:")
        for p in cands[:80]:
            print(f" - {p}")

        approval_cands = [p for p in cands if any(m in read_text(p) for m in APPROVAL_MARKERS)]
        totp_cands = [p for p in cands if any(m in read_text(p) for m in INVALID_MARKERS)]
        if not approval_cands:
            raise RuntimeError("no approval handler candidate found")
        if not totp_cands:
            raise RuntimeError("no TOTP validation candidate found")

        patched_grace = False
        for p in totp_cands:
            if patch_totp_grace(p):
                patched_grace = True
                break
        if not patched_grace:
            raise RuntimeError("TOTP validation file found, but no recognised pyotp/speakeasy/authenticator verify pattern patched")

        patched_visibility = False
        for p in approval_cands:
            if patch_gate_visibility(p):
                patched_visibility = True
                break
        if not patched_visibility:
            raise RuntimeError("approval handler found, but no recognised expiry variable for gate visibility patch")

        patch_config()
        print("SUCCESS: TOTP grace + L1 gate visibility + 10-minute window patched. Restart services now.")
        return 0
    except Exception as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        rollback()
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
