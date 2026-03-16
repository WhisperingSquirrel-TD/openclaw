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
    ("agents", "defaults", "totpWindowMinutes"): 2,
    ("channels", "telegram", "dmPolicy"): "allowlist",
    ("channels", "whatsapp", "mode"): "watch",
    ("agents", "defaults", "approvalMode"): "totp",
}

# Commands that must remain permanently blocked in denyCommands
MUST_DENY = [
    "calendar.delete", # destructive — never permitted under any circumstance
]

# Commands that must be in requireApproval (TOTP-gated, not freely callable)
# calendar.add/update are here — L1 must use the proper tool and the TOTP prompt
# will name the exact action so the user knows what they're approving.
# exec.run is here as the backstop against code-based bypass routes.
MUST_REQUIRE_APPROVAL = [
    "calendar.add",    # TOTP-gated calendar write via proper tool
    "calendar.update", # TOTP-gated calendar edit via proper tool
    "exec.run",        # TOTP-gated shell — prevents silent code-based bypasses
]

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

    # Check that permanently blocked commands remain in denyCommands
    deny = get_nested(config, "gateway", "nodes", "denyCommands") or []
    for cmd in MUST_DENY:
        if cmd not in deny:
            msg = f"{cmd} is NOT in denyCommands (must remain permanently blocked)"
            log_alert(f"Security drift: {msg}")
            mismatches.append(msg)
        else:
            print(f"[OK] denyCommands contains {cmd}")

    # Check that TOTP-gated commands are in requireApproval (not silently callable)
    require = get_nested(config, "agents", "defaults", "requireApproval") or []
    for cmd in MUST_REQUIRE_APPROVAL:
        if cmd not in require:
            msg = f"{cmd} is NOT in requireApproval (must be TOTP-gated)"
            log_alert(f"Security drift: {msg}")
            mismatches.append(msg)
        else:
            print(f"[OK] requireApproval contains {cmd}")

    # Sanity: calendar.add/update must not appear in denyCommands (they'd be uncallable
    # instead of TOTP-gated, which is wrong — they should go through the approval flow)
    for cmd in ["calendar.add", "calendar.update"]:
        if cmd in deny:
            msg = f"{cmd} is in denyCommands — should be in requireApproval instead (TOTP-gated)"
            log_alert(f"Config mismatch: {msg}")
            mismatches.append(msg)

    if mismatches:
        print(f"\n{len(mismatches)} mismatch(es) found — see {LOG_PATH}")
        sys.exit(1)
    else:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{ts}] All config checks passed.")

if __name__ == "__main__":
    main()
