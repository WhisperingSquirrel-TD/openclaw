#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}[✓] $1${NC}"; }
warn() { echo -e "${YELLOW}[!] $1${NC}"; }
fail() { echo -e "${RED}[✗] $1${NC}"; exit 1; }

echo ""
echo "========================================="
echo "  L1 — Install Forked OpenClaw"
echo "========================================="
echo ""

# Step 1: Stop L1
warn "Stopping L1..."
~/l1-stop.sh 2>/dev/null || true
info "L1 stopped"

# Step 2: Uninstall existing OpenClaw
warn "Uninstalling current OpenClaw..."
sudo npm uninstall -g openclaw 2>/dev/null || true
sudo pnpm unlink --global 2>/dev/null || true
info "Old OpenClaw removed"

# Step 3: Install pnpm if not present
if ! command -v pnpm &> /dev/null; then
    warn "Installing pnpm..."
    sudo npm install -g pnpm || fail "pnpm install failed"
    info "pnpm installed"
else
    info "pnpm already installed: $(pnpm --version)"
fi

# Step 4: Clone or pull the fork
if [ -d ~/openclaw ]; then
    warn "Fork already cloned — pulling latest changes..."
    cd ~/openclaw
    git pull || fail "Git pull failed. Check your connection."
    info "Code updated"
else
    warn "Cloning fork from GitHub..."
    cd ~
    git clone https://github.com/WhisperingSquirrel-TD/openclaw.git || fail "Clone failed. Check your connection and repo name."
    cd ~/openclaw
    info "Fork cloned"
fi

# Step 5: Install dependencies with pnpm
warn "Installing dependencies with pnpm (this may take a few minutes on Pi)..."
cd ~/openclaw
pnpm install || fail "pnpm install failed"
info "Dependencies installed"

# Step 6: Build TypeScript
warn "Building from TypeScript source (this may take a while on Pi)..."
cd ~/openclaw
pnpm run build || fail "Build failed — check for TypeScript errors"
info "Build complete"

# Step 7: Link globally with pnpm (not npm — must match the package manager)
warn "Linking openclaw globally..."
cd ~/openclaw

# Ensure pnpm global bin directory exists and is configured
export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
mkdir -p "$PNPM_HOME"
if ! echo "$PATH" | grep -q "$PNPM_HOME"; then
    export PATH="$PNPM_HOME:$PATH"
fi
# Add to .bashrc if not already there
if ! grep -q 'PNPM_HOME' ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# pnpm global bin" >> ~/.bashrc
    echo "export PNPM_HOME=\"\$HOME/.local/share/pnpm\"" >> ~/.bashrc
    echo "export PATH=\"\$PNPM_HOME:\$PATH\"" >> ~/.bashrc
    info "Added PNPM_HOME to ~/.bashrc"
fi

pnpm link --global || sudo npm link || warn "Global link failed — L1 will still work via l1-start.sh"
info "OpenClaw linked"

# Step 8: Verify
if command -v openclaw &> /dev/null; then
    info "OpenClaw available: $(openclaw --version 2>/dev/null || echo 'installed')"
else
    warn "openclaw command not in PATH — use ~/l1-start.sh to run instead"
fi

# Step 9: Update config — set WhatsApp to watch mode
echo ""
warn "Updating openclaw.json — setting WhatsApp to watch mode..."

CONFIG_FILE="/home/tomdean88/.openclaw/openclaw.json"

sudo chattr -i "$CONFIG_FILE" 2>/dev/null || true

python3 -c "
import json, sys

config_path = '$CONFIG_FILE'

try:
    with open(config_path, 'r') as f:
        c = json.load(f)
except FileNotFoundError:
    print(f'ERROR: {config_path} not found')
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f'ERROR: Invalid JSON in {config_path}: {e}')
    sys.exit(1)

c.setdefault('channels', {})

# Merge watch mode into WhatsApp config (preserves accounts/credentials)
wa = c['channels'].setdefault('whatsapp', {})
wa['mode'] = 'watch'
wa['dmPolicy'] = 'open'
wa['groupPolicy'] = 'open'
wa['debounceMs'] = 3000
# selfChatMode and allowFrom are valid schema fields
wa['selfChatMode'] = True
wa['allowFrom'] = ['*']
wa['groupAllowFrom'] = ['*']

# Make sure Telegram stays active
if 'telegram' not in c['channels']:
    print('WARNING: Telegram config missing — check manually')
else:
    tg = c['channels']['telegram']
    has_token = 'botToken' in tg or any(
        'botToken' in (acc or {})
        for acc in (tg.get('accounts') or {}).values()
    )
    print(f'Telegram config preserved (botToken present: {has_token})')

# Remove message.send from denyCommands if present (watch mode handles it now)
deny = c.get('gateway', {}).get('nodes', {}).get('denyCommands', [])
if 'message.send' in deny:
    deny.remove('message.send')
    print('Removed message.send from denyCommands — watch mode enforces this now')

# Set up TOTP approval mode for trust gate (Pi-compatible, replaces socket-based approval)
agents = c.setdefault('agents', {}).setdefault('defaults', {})
if 'approvalMode' not in agents:
    agents['approvalMode'] = 'totp'
    agents.setdefault('totpWindowMinutes', 5)
    agents.setdefault('trustLevel', 1)
    agents.setdefault('requireApproval', ['message.send'])
    print('TOTP approval mode configured (trustLevel=1, window=5min)')
else:
    print(f'Approval mode already set: {agents[\"approvalMode\"]}')

# Ensure restart is still disabled (safe setdefault)
c.setdefault('commands', {})['restart'] = False

# Ensure sandbox exec (safe setdefault)
c.setdefault('tools', {}).setdefault('exec', {})['host'] = 'sandbox'

with open(config_path, 'w') as f:
    json.dump(c, f, indent=2)

print('Config updated successfully')
" || fail "Config update failed"

sudo chattr +i "$CONFIG_FILE"
info "Config updated and locked"

# Step 10: Start L1
echo ""
warn "Starting L1..."
~/l1-start.sh

# Step 11: Update hashes
md5sum /mnt/l1-secure/*.md > ~/l1-hashes.txt 2>/dev/null || true
info "Hashes updated"

echo ""
echo "========================================="
echo "  DONE"
echo "========================================="
echo ""
echo "  Fork installed from: github.com/WhisperingSquirrel-TD/openclaw"
echo "  WhatsApp: watch mode (read-only, silent)"
echo "  Telegram: active (2-way with Tom)"
echo "  Trust gate: TOTP approval (5-min window)"
echo "  Config: locked"
echo ""
echo "  TOTP setup (first time only):"
echo "    Send /totp-setup on Telegram"
echo "    Scan the URI with Google Authenticator or Authy"
echo ""
echo "  To pull future updates:"
echo "    cd ~/openclaw && git pull && pnpm run build && openclaw gateway restart"
echo ""
echo "  To check status:"
echo "    openclaw doctor"
echo ""
