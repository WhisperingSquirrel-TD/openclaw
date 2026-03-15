#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}[✓] $1${NC}"; }
warn() { echo -e "${YELLOW}[!] $1${NC}"; }
fail() { echo -e "${RED}[✗] $1${NC}"; exit 1; }

# ─────────────────────────────────────────────────────────────────────────────
# Step 0: Pull latest code FIRST, then self-update and re-exec.
# This guarantees we always run the newest version of this script.
# OPENCLAW_REEXEC=1 is set on the re-exec to prevent an infinite loop.
# ─────────────────────────────────────────────────────────────────────────────
if [ -z "${OPENCLAW_REEXEC:-}" ]; then
    echo ""
    echo "========================================="
    echo "  L1 — Fetching latest code from GitHub"
    echo "========================================="
    echo ""
    if [ -d "$HOME/openclaw" ]; then
        warn "Pulling latest changes..."
        git -C "$HOME/openclaw" stash 2>/dev/null || true
        git -C "$HOME/openclaw" pull || warn "Git pull failed — proceeding with existing code"
        git -C "$HOME/openclaw" stash pop 2>/dev/null || true
        info "Code updated"
    else
        warn "Cloning fork from GitHub..."
        git clone https://github.com/WhisperingSquirrel-TD/openclaw.git "$HOME/openclaw" \
            || fail "Clone failed. Check your connection and repo URL."
        info "Fork cloned"
    fi
    # Copy the freshly-pulled script over ~/install-forked-openclaw.sh and re-exec it
    REPO_SCRIPT="$HOME/openclaw/attached_assets/install-forked-openclaw.sh"
    SELF="$HOME/install-forked-openclaw.sh"
    if [ -f "$REPO_SCRIPT" ]; then
        cp "$REPO_SCRIPT" "$SELF"
        chmod +x "$SELF"
        info "Install script updated from repo"
    fi
    exec env OPENCLAW_REEXEC=1 bash "$SELF" "$@"
fi

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

# Step 3: Ensure Node.js >= 22.12.0 (required by upstream since 2026.3.8)
REQUIRED_NODE_MAJOR=22
REQUIRED_NODE_MINOR=12
CURRENT_NODE_VERSION=$(node -v 2>/dev/null | sed 's/^v//')
CURRENT_NODE_MAJOR=$(echo "$CURRENT_NODE_VERSION" | cut -d. -f1)
CURRENT_NODE_MINOR=$(echo "$CURRENT_NODE_VERSION" | cut -d. -f2)

node_needs_update() {
    if [ -z "$CURRENT_NODE_VERSION" ]; then return 0; fi
    if [ "$CURRENT_NODE_MAJOR" -lt "$REQUIRED_NODE_MAJOR" ] 2>/dev/null; then return 0; fi
    if [ "$CURRENT_NODE_MAJOR" -eq "$REQUIRED_NODE_MAJOR" ] && [ "$CURRENT_NODE_MINOR" -lt "$REQUIRED_NODE_MINOR" ] 2>/dev/null; then return 0; fi
    return 1
}

if node_needs_update; then
    warn "Node.js ${CURRENT_NODE_VERSION:-not found} is below required v${REQUIRED_NODE_MAJOR}.${REQUIRED_NODE_MINOR}.0 — upgrading..."
    if command -v n &> /dev/null; then
        sudo n install $REQUIRED_NODE_MAJOR || fail "Node.js upgrade via n failed"
        hash -r
    elif command -v nvm &> /dev/null; then
        nvm install $REQUIRED_NODE_MAJOR || fail "Node.js upgrade via nvm failed"
        nvm use $REQUIRED_NODE_MAJOR
    elif command -v fnm &> /dev/null; then
        fnm install $REQUIRED_NODE_MAJOR || fail "Node.js upgrade via fnm failed"
        fnm use $REQUIRED_NODE_MAJOR
    else
        warn "No version manager (n, nvm, fnm) found — installing n..."
        sudo npm install -g n || fail "Failed to install n"
        sudo n install $REQUIRED_NODE_MAJOR || fail "Node.js upgrade via n failed"
        hash -r
    fi
    export PATH="/usr/local/bin:$PATH"
    hash -r 2>/dev/null
    NEW_NODE=$(node -v 2>/dev/null | sed 's/^v//')
    NEW_MAJOR=$(echo "$NEW_NODE" | cut -d. -f1)
    NEW_MINOR=$(echo "$NEW_NODE" | cut -d. -f2)
    if [ "$NEW_MAJOR" -lt "$REQUIRED_NODE_MAJOR" ] 2>/dev/null || \
       { [ "$NEW_MAJOR" -eq "$REQUIRED_NODE_MAJOR" ] && [ "$NEW_MINOR" -lt "$REQUIRED_NODE_MINOR" ]; } 2>/dev/null; then
        fail "Node.js upgrade produced v${NEW_NODE} but v${REQUIRED_NODE_MAJOR}.${REQUIRED_NODE_MINOR}.0+ is required. Check PATH or upgrade manually."
    fi
    info "Node.js upgraded to v$NEW_NODE"
else
    info "Node.js $CURRENT_NODE_VERSION (meets >= v${REQUIRED_NODE_MAJOR}.${REQUIRED_NODE_MINOR}.0)"
fi

# Step 4: Install pnpm if not present
if ! command -v pnpm &> /dev/null; then
    warn "Installing pnpm..."
    sudo npm install -g pnpm || fail "pnpm install failed"
    info "pnpm installed"
else
    info "pnpm already installed: $(pnpm --version)"
fi

# Step 5: Confirm repo is ready (already pulled in Step 0)
cd "$HOME/openclaw"
info "Repo ready: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"

# Step 6: Install dependencies with pnpm (with retries for flaky Pi networking)
warn "Installing dependencies with pnpm (this may take a few minutes on Pi)..."
cd ~/openclaw
PNPM_OK=false
for attempt in 1 2 3; do
    if pnpm install --fetch-timeout 120000; then
        PNPM_OK=true
        break
    fi
    if [ "$attempt" -lt 3 ]; then
        warn "pnpm install failed (attempt $attempt/3) — retrying in 15s..."
        sleep 15
    fi
done
$PNPM_OK || fail "pnpm install failed after 3 attempts. Check your internet connection and try again."
info "Dependencies installed"

# Step 7: Build TypeScript
warn "Building from TypeScript source (this may take a while on Pi)..."
cd ~/openclaw
rm -rf dist 2>/dev/null || true
pnpm run build || fail "Build failed — check for TypeScript errors"
COMMIT_SHORT=$(cd ~/openclaw && git rev-parse --short HEAD 2>/dev/null || echo "unknown")
info "Build complete (commit: $COMMIT_SHORT)"

# Step 8: Link globally with pnpm (not npm — must match the package manager)
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

# Step 9: Verify + keep install script up to date
if command -v openclaw &> /dev/null; then
    info "OpenClaw available: $(openclaw --version 2>/dev/null || echo 'installed')"
else
    warn "openclaw command not in PATH — use ~/l1-start.sh to run instead"
fi

# Step 10: Update config — set WhatsApp to watch mode
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
if not isinstance(c['channels'], dict):
    c['channels'] = {}

# Merge watch mode into WhatsApp config (preserves accounts/credentials)
# Uses setdefault for all fields — never overwrites values you've manually changed
wa = c['channels'].setdefault('whatsapp', {})
if not isinstance(wa, dict):
    c['channels']['whatsapp'] = {}
    wa = c['channels']['whatsapp']
wa.setdefault('mode', 'watch')
wa.setdefault('dmPolicy', 'open')
wa.setdefault('groupPolicy', 'open')
wa.setdefault('debounceMs', 3000)
wa.setdefault('selfChatMode', True)
wa.setdefault('allowFrom', ['*'])
wa.setdefault('groupAllowFrom', ['*'])
print(f'WhatsApp config: mode={wa[\"mode\"]}')

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

# denyCommands: remove message.send only (watch mode handles it)
# calendar.add and calendar.update remain blocked — calendar writes must go
# through the Outlook/Microsoft integration only, not any generic calendar provider
deny = c.get('gateway', {}).get('nodes', {}).get('denyCommands', [])
if not isinstance(deny, list):
    deny = []
    c.setdefault('gateway', {}).setdefault('nodes', {})['denyCommands'] = deny
if 'message.send' in deny:
    deny.remove('message.send')
    print('Removed message.send from denyCommands — watch mode enforces this now')

# Set up TOTP approval mode for trust gate (Pi-compatible, replaces socket-based approval)
c.setdefault('agents', {})
if not isinstance(c['agents'], dict):
    c['agents'] = {}
agents = c['agents'].setdefault('defaults', {})
if not isinstance(agents, dict):
    c['agents']['defaults'] = {}
    agents = c['agents']['defaults']
agents.setdefault('approvalMode', 'totp')
# totpWindowMinutes must always be 2 — migrate any other value
if agents.get('totpWindowMinutes') != 2:
    old = agents.get('totpWindowMinutes', 'unset')
    agents['totpWindowMinutes'] = 2
    print(f'totpWindowMinutes: {old} -> 2 (corrected)')
else:
    agents['totpWindowMinutes'] = 2
agents.setdefault('trustLevel', 1)
agents.setdefault('requireApproval', ['message.send', 'exec.run'])
print(f'Approval mode: {agents[\"approvalMode\"]} (window={agents[\"totpWindowMinutes\"]}min)')

# Ensure restart is still disabled (safe setdefault)
c.setdefault('commands', {}).setdefault('restart', False)

# Set exec host to gateway (allows TOTP-gated shell commands on the Pi)
# Uses setdefault so manual overrides (e.g. back to sandbox) are preserved
c.setdefault('tools', {})
if not isinstance(c['tools'], dict):
    c['tools'] = {}
tools_exec = c['tools'].setdefault('exec', {})
if not isinstance(tools_exec, dict):
    c['tools']['exec'] = {}
    tools_exec = c['tools']['exec']
if tools_exec.get('host') == 'sandbox':
    tools_exec['host'] = 'gateway'
    print('Exec host: sandbox -> gateway (migrated)')
else:
    tools_exec.setdefault('host', 'gateway')
    print(f'Exec host: {tools_exec[\"host\"]}')

# Enable WhatsApp watch action scanner (AI-powered action detection from WhatsApp messages)
wa_actions = wa.setdefault('watchActions', {})
if not isinstance(wa_actions, dict):
    wa['watchActions'] = {}
    wa_actions = wa['watchActions']
wa_actions.setdefault('enabled', True)
wa_actions.setdefault('activeHoursStart', 8)
wa_actions.setdefault('activeHoursEnd', 22)
wa_actions.setdefault('intervalMinutes', 5)
print(f'Watch actions: enabled={wa_actions[\"enabled\"]}, hours={wa_actions[\"activeHoursStart\"]}-{wa_actions[\"activeHoursEnd\"]}, interval={wa_actions[\"intervalMinutes\"]}min')

with open(config_path, 'w') as f:
    json.dump(c, f, indent=2)

print('Config updated successfully')
" || fail "Config update failed"

sudo chattr +i "$CONFIG_FILE"
info "Config updated and locked"

# Step 11: Deploy integration scripts from repo
echo ""
warn "Deploying integration scripts..."

INTEGRATIONS_SRC="$HOME/openclaw/attached_assets/integrations"
INTEGRATIONS_DST="$HOME/.openclaw/integrations"

deploy_integration() {
    local src="$1"
    local dst="$2"
    if [ -f "$src" ]; then
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        chmod +x "$dst"
        info "Deployed: $dst"
    fi
}

deploy_integration "$INTEGRATIONS_SRC/config-check/check.py"      "$INTEGRATIONS_DST/config-check/check.py"
deploy_integration "$INTEGRATIONS_SRC/docx-converter/convert.py"   "$INTEGRATIONS_DST/docx-converter/convert.py"
deploy_integration "$INTEGRATIONS_SRC/microsoft/poll.py"           "$INTEGRATIONS_DST/microsoft/poll.py"

# Deploy Google Tasks credentials template (only if no credentials file exists yet)
GOOGLE_CREDS="$HOME/.openclaw/oauth/google/credentials.json"
if [ ! -f "$GOOGLE_CREDS" ]; then
    mkdir -p "$(dirname "$GOOGLE_CREDS")"
    cp "$INTEGRATIONS_SRC/google/credentials-template.json" "$GOOGLE_CREDS" 2>/dev/null || \
    cat > "$GOOGLE_CREDS" << 'GCEOF'
{
  "clientId": "YOUR_GOOGLE_CLIENT_ID",
  "clientSecret": "YOUR_GOOGLE_CLIENT_SECRET"
}
GCEOF
    warn "Google Tasks credentials template created at: $GOOGLE_CREDS"
    warn "To enable 'Add to list': fill in your Google OAuth credentials there."
    warn "  1. Go to console.cloud.google.com"
    warn "  2. Create a project, enable Tasks API"
    warn "  3. APIs & Services → Credentials → Create OAuth 2.0 Client (Desktop app)"
    warn "  4. Edit $GOOGLE_CREDS with your Client ID and Secret"
else
    info "Google Tasks credentials file already exists — not overwritten"
fi

# FIX 1: Create last-seen-emails.md template if it doesn't exist
LAST_SEEN="$HOME/.openclaw/workspace/memory/last-seen-emails.md"
if [ ! -f "$LAST_SEEN" ]; then
    mkdir -p "$(dirname "$LAST_SEEN")"
    cat > "$LAST_SEEN" << 'EOF'
# Last Seen Emails — Known Contacts
# Format: contact-email | last-seen-timestamp (ISO 8601)
stuart.hobin@croydemedical.co.uk | 
emily.thomas@croydemedical.co.uk | 
john@reveela.com | 
ed.patchett@7thsense.one | 
johnjamesmarsh@hotmail.com | 
andy.barrett@sjpp.co.uk | 
olivia.collington@collingtonwinter.co.uk | 
EOF
    info "Created last-seen-emails.md template"
else
    info "last-seen-emails.md already exists — not overwritten"
fi

# Run config drift check immediately after deploy
if [ -f "$INTEGRATIONS_DST/config-check/check.py" ]; then
    echo ""
    warn "Running config drift check..."
    python3 "$INTEGRATIONS_DST/config-check/check.py" || true
fi

# Step 12a: Set audit log append-only (tamper protection)
AUDIT_DIR="$HOME/.openclaw/audit"
if [ -d "$AUDIT_DIR" ]; then
    sudo chattr +a "$AUDIT_DIR/outbound-audit.jsonl" 2>/dev/null && info "Audit log set append-only" || true
fi
TOTP_DIR="$HOME/.openclaw/totp"
if [ -d "$TOTP_DIR" ]; then
    sudo chattr +i "$TOTP_DIR/totp-secret.enc" 2>/dev/null || true
    sudo chattr +i "$TOTP_DIR/totp-secret.txt" 2>/dev/null || true
    info "TOTP secret files protected"
fi

# Step 12b: Start L1
echo ""
warn "Starting L1..."
~/l1-start.sh

# Step 13: Update integrity hashes
md5sum /mnt/l1-secure/*.md > ~/l1-hashes.txt 2>/dev/null || true
info "Hashes updated"

echo ""
echo "========================================="
echo "  DONE"
echo "========================================="
echo ""
echo "  Fork installed from: github.com/WhisperingSquirrel-TD/openclaw"
echo "  Commit: ${COMMIT_SHORT:-unknown}"
echo "  WhatsApp: watch mode (read-only, silent)"
echo "  WhatsApp actions: AI scanner enabled (8am-10pm, hourly)"
echo "  Telegram: active (2-way with Tom)"
echo "  Exec host: gateway (TOTP-gated)"
echo "  Trust gate: TOTP approval"
echo "  Config: locked"
echo ""
echo "  TOTP setup (first time only):"
echo "    Send /totp-setup on Telegram"
echo "    Scan the URI with Google Authenticator or Authy"
echo ""
echo "  To update in future (single command — handles everything):"
echo "    bash ~/install-forked-openclaw.sh"
echo ""
echo "  To check status:"
echo "    openclaw doctor"
echo ""
