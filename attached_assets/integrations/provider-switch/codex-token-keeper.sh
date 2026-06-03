#!/usr/bin/env bash
# codex-token-keeper.sh
# Proactively probes the openai-codex OAuth token every 20 minutes so it is
# refreshed against a stable network connection rather than on-demand during
# a user conversation (where a brief network blip causes total auth failure).
#
# How it works:
#   - `models status --probe --probe-provider openai-codex` makes a live API
#     call through the full OpenClaw auth stack.
#   - If the access token has just expired, this triggers a refresh NOW while
#     the network is idle — not mid-conversation.
#   - If the token is still valid, the call succeeds instantly (no refresh).
#   - Result (ok / error) is logged with a timestamp for diagnostics.
#
# Scheduled by install script: */20 * * * *

set -euo pipefail

LOG="$HOME/.openclaw/workspace/memory/codex-token-keeper-log.txt"
OPENCLAW_BIN="$HOME/openclaw/dist/index.js"
ENV_FILE="$HOME/.openclaw/.env"
LOG_MAX=500
LOG_TRIM=400

mkdir -p "$(dirname "$LOG")"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

log_line() {
    local line="[$(ts)] [codex-keeper] $1"
    echo "$line"
    # Trim log if over limit
    if [ -f "$LOG" ]; then
        local count
        count=$(wc -l < "$LOG" 2>/dev/null || echo 0)
        if [ "$count" -ge "$LOG_MAX" ]; then
            tail -n "$LOG_TRIM" "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
        fi
    fi
    echo "$line" >> "$LOG"
}

# Load env vars (OPENCLAW_VAULT_PASSPHRASE etc.)
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

# Pi perf optimisations (fast node startup, no self-respawn)
export NODE_COMPILE_CACHE="${NODE_COMPILE_CACHE:-/var/tmp/openclaw-compile-cache}"
export OPENCLAW_NO_RESPAWN=1
mkdir -p "$NODE_COMPILE_CACHE" 2>/dev/null || true

if [ ! -f "$OPENCLAW_BIN" ]; then
    log_line "SKIP — dist/index.js not found (not yet built)"
    exit 0
fi

# Run the live probe — exits 0 on success, non-zero on auth failure
if node "$OPENCLAW_BIN" models status \
        --probe \
        --probe-provider openai-codex \
        --probe-timeout 20000 \
        > /tmp/codex-keeper-out.txt 2>&1; then
    log_line "OK — openai-codex token alive/refreshed"
else
    EXIT=$?
    OUTPUT=$(cat /tmp/codex-keeper-out.txt 2>/dev/null | tail -3 | tr '\n' ' ')
    log_line "WARN — probe failed (exit $EXIT): $OUTPUT"
    log_line "ACTION NEEDED: run on Pi: node ~/openclaw/dist/index.js models auth login --provider openai-codex"
fi
