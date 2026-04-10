#!/bin/bash
# Fix: inject ~/.npm-packages/bin into the gateway systemd service PATH
# so the gateway can find qmd at runtime (fixes "spawn qmd ENOENT").
#
# Usage: bash scripts/fix-qmd-path.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
info() { echo -e "${GREEN}[✓] $1${NC}"; }
warn() { echo -e "${YELLOW}[!] $1${NC}"; }
fail() { echo -e "${RED}[✗] $1${NC}"; exit 1; }

GATEWAY_SVC="$HOME/.config/systemd/user/openclaw-gateway.service"
NPM_BIN="$HOME/.npm-packages/bin"

# 1. Verify qmd is actually installed where we expect it
if [ ! -f "$NPM_BIN/qmd" ]; then
    warn "qmd not found at $NPM_BIN/qmd"
    warn "Installing qmd now..."
    npm install -g @tobilu/qmd --prefix "$HOME/.npm-packages" \
        || fail "qmd install failed — check npm is working"
fi
info "qmd found: $("$NPM_BIN/qmd" --version 2>/dev/null || echo 'installed')"

# 2. Verify the gateway service file exists
if [ ! -f "$GATEWAY_SVC" ]; then
    fail "Gateway service unit not found at $GATEWAY_SVC — has openclaw been installed?"
fi

# 3. Patch the service unit if not already patched
if grep -q "npm-packages" "$GATEWAY_SVC"; then
    info "Gateway service PATH already includes ~/.npm-packages/bin — no change needed"
else
    sed -i "/^\[Service\]/a Environment=\"PATH=$NPM_BIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"" \
        "$GATEWAY_SVC"
    info "Gateway service patched with PATH=$NPM_BIN:..."
fi

# 4. Reload systemd and restart the gateway
systemctl --user daemon-reload
info "systemd daemon reloaded"

systemctl --user restart openclaw-gateway.service \
    && info "openclaw-gateway.service restarted — qmd is now available to L1" \
    || fail "Failed to restart openclaw-gateway.service"

echo ""
info "Done. Ask L1 to search for something to confirm qmd is working."
