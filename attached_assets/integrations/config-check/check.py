#!/usr/bin/env python3
"""
OpenClaw config drift detector.
Checks that critical config values match expected settings.
Logs warnings to config-alerts.log and exits non-zero if any mismatch found.
"""
import json
import sys
import os
from datetime import datetime

CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")
LOG_PATH = os.path.expanduser("~/.openclaw/workspace/memory/config-alerts.log")

EXPECTED = {
    ("tools", "exec", "host"): "gateway",
    ("agents", "defaults", "totpWindowMinutes"): 5,
    ("channels", "telegram", "dmPolicy"): "allowlist",
    ("channels", "whatsapp", "mode"): "watch",
    ("agents", "defaults", "approvalMode"): "totp",
}

def get_nested(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d

def log_alert(message):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] WARN: {message}\n"
    with open(LOG_PATH, "a") as f:
        f.write(line)
    print(line, end="")

def main():
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    except FileNotFoundError:
        log_alert(f"Config file not found: {CONFIG_PATH}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        log_alert(f"Config file invalid JSON: {e}")
        sys.exit(1)

    mismatches = []
    for keys, expected in EXPECTED.items():
        actual = get_nested(config, *keys)
        key_str = ".".join(keys)
        if actual != expected:
            msg = f"{key_str} = {repr(actual)} (expected {repr(expected)})"
            log_alert(f"Config mismatch: {msg}")
            mismatches.append(msg)
        else:
            print(f"[OK] {key_str} = {repr(actual)}")

    if mismatches:
        print(f"\n{len(mismatches)} mismatch(es) found — see {LOG_PATH}")
        sys.exit(1)
    else:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{ts}] All config checks passed.")

if __name__ == "__main__":
    main()
