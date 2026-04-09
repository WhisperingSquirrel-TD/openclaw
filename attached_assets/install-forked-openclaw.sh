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
# Auto-load ~/.openclaw/.env so callers never need to `source` manually.
# set -a exports every variable defined while active; set +a turns it off.
# ─────────────────────────────────────────────────────────────────────────────
ENV_FILE="$HOME/.openclaw/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
    info ".env loaded from $ENV_FILE"
else
    warn ".env not found at $ENV_FILE — some integrations may not configure correctly"
fi

# ─────────────────────────────────────────────────────────────────────────────
# SOUL.md preservation — back up before ANYTHING runs, restore at exit.
# Handles three cases:
#   1. Normal file: back up and restore as usual.
#   2. Broken symlink (target mount gone): remove symlink, heal from SOUL_PENDING.md
#      or create a starter so L1 always has a live SOUL.md.
#   3. Missing entirely: create a starter at exit.
# ─────────────────────────────────────────────────────────────────────────────
SOUL_MD_PATH="$HOME/.openclaw/workspace/SOUL.md"
SOUL_PENDING_PATH="$HOME/.openclaw/workspace/SOUL_PENDING.md"
SOUL_MD_BACKUP="/tmp/openclaw-soul-backup.md"

# --- Detect and remove broken symlink BEFORE backup ---
# -L is true if the path is a symlink (even broken); -e is false if target missing.
# NOTE: SOUL_PENDING.md is a staging/backlog file — NOT a backup of SOUL.md.
# It contains unreviewed proposals and must NEVER be auto-promoted to SOUL.md.
if [ -L "$SOUL_MD_PATH" ] && [ ! -e "$SOUL_MD_PATH" ]; then
    echo "[soul] WARNING: SOUL.md is a broken symlink (mount gone). Removing symlink."
    rm -f "$SOUL_MD_PATH"
    echo "[soul] SOUL.md removed — a starter will be created at end of install."
    echo "[soul] IMPORTANT: SOUL_PENDING.md is your backlog of proposed changes."
    echo "[soul]   Do NOT use it as a replacement for SOUL.md — it contains unreviewed items."
    echo "[soul]   After install, manually restore your SOUL.md content."
fi

# Back up only if the file is a real, non-empty file
# (use -f which follows symlinks — at this point any broken symlink was already removed)
if [ -f "$SOUL_MD_PATH" ] && [ -s "$SOUL_MD_PATH" ]; then
    cp "$SOUL_MD_PATH" "$SOUL_MD_BACKUP"
    echo "[soul] SOUL.md backed up to $SOUL_MD_BACKUP ($(wc -c < "$SOUL_MD_PATH") bytes)"
fi

restore_soul_md() {
    mkdir -p "$(dirname "$SOUL_MD_PATH")"
    if [ -f "$SOUL_MD_BACKUP" ] && [ -s "$SOUL_MD_BACKUP" ]; then
        # Remove any broken symlink that might have re-appeared
        [ -L "$SOUL_MD_PATH" ] && rm -f "$SOUL_MD_PATH"
        cp "$SOUL_MD_BACKUP" "$SOUL_MD_PATH"
        rm -f "$SOUL_MD_BACKUP"
        echo "[soul] SOUL.md restored from backup"
    elif [ ! -f "$SOUL_MD_PATH" ] || [ ! -s "$SOUL_MD_PATH" ]; then
        # No backup and no live file — create a minimal starter
        [ -L "$SOUL_MD_PATH" ] && rm -f "$SOUL_MD_PATH"
        cat > "$SOUL_MD_PATH" << 'SOUL_STARTER'
# SOUL.md — L1 Identity & Operating Principles

## Who you are
You are L1, Tom Dean's personal AI chief of staff. You operate via OpenClaw
on a Raspberry Pi 4. You work across Telegram (2-way), WhatsApp (read-only
watch mode), Microsoft 365, Gmail, Google Calendar, and Stackstone Consulting
business systems.

## Core priorities (in order)
1. Revenue-critical: new website enquiries, client responses, inbound leads
2. Time-sensitive: meetings, deadlines, calendar conflicts
3. Operational: daily briefing, health checks, cron monitoring
4. Background: CRM updates, report delivery, prospecting

## Operating principles
- Direct website enquiries are revenue-critical — surface immediately
- Default to action over clarification for anything time-sensitive
- Never include ⚙️ SYSTEM HEALTH in the morning briefing unless SYSTEM_HEALTH.md is non-empty
- Always use file-based args (--body-file, --title-file) for exec commands — never embed content in shell args
- TOTP approval required for any outbound action (email, calendar, exec)

## What this file is NOT
Avoid putting command paths, file locations, script names, or temp-file
flows here. Those belong in skills, memory, or implementation files.
SOUL_STARTER
        echo "[soul] WARNING: SOUL.md was missing — starter created. Please update with your full persona."
    fi
}
trap restore_soul_md EXIT

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

pnpm link --global || sudo npm link || warn "Global link failed — will use wrapper script instead"

# Write a real wrapper at /usr/local/bin/openclaw rather than a symlink.
# A symlink to the pnpm shim breaks because the shim resolves paths relative
# to its own location using HOME, which is wrong under sudo/script invocations.
# A wrapper that calls node with an absolute path is always correct.
OPENCLAW_MJS="$HOME/openclaw/openclaw.mjs"
SYSTEM_BIN="/usr/local/bin/openclaw"
if [ -f "$OPENCLAW_MJS" ]; then
    sudo tee "$SYSTEM_BIN" > /dev/null << WRAPPER
#!/bin/bash
exec node $OPENCLAW_MJS "\$@"
WRAPPER
    sudo chmod +x "$SYSTEM_BIN"
    info "Wrapper written: $SYSTEM_BIN → node $OPENCLAW_MJS"
else
    warn "openclaw.mjs not found at $OPENCLAW_MJS — wrapper not created"
fi
info "OpenClaw linked"

# Step 9: Verify
if command -v openclaw &> /dev/null; then
    info "OpenClaw available: $(openclaw --version 2>/dev/null || echo 'installed')"
else
    warn "openclaw command not in PATH — run: sudo tee /usr/local/bin/openclaw <<'EOF'
#!/bin/bash
exec node $HOME/openclaw/openclaw.mjs \"\$@\"
EOF"
fi

# Step 9b: Install QMD memory backend
# QMD provides local-first semantic memory search — no API keys, no cloud.
# Default: BM25 keyword search (lightweight, works on all Pi hardware).
# The Pi 4 8GB is sufficient for full semantic (vsearch) mode — see DONE summary.
#
# npm install -g requires root unless we redirect the global prefix to a
# user-writable directory. We use ~/.npm-packages and add its bin to PATH.
echo ""
warn "Installing QMD memory backend..."

QMD_NPM_PREFIX="$HOME/.npm-packages"
mkdir -p "$QMD_NPM_PREFIX"
npm config set prefix "$QMD_NPM_PREFIX" 2>/dev/null || true
export PATH="$QMD_NPM_PREFIX/bin:$PATH"

# Persist PATH addition so qmd is available in future shells
PROFILE_LINE='export PATH="$HOME/.npm-packages/bin:$PATH"'
for rcfile in "$HOME/.bashrc" "$HOME/.profile"; do
    if [ -f "$rcfile" ] && ! grep -qF ".npm-packages/bin" "$rcfile"; then
        echo "$PROFILE_LINE" >> "$rcfile"
    fi
done

if ! command -v qmd &> /dev/null; then
    npm install -g @tobilu/qmd 2>&1 || warn "QMD install failed — memory backend will fall back to builtin"
    if command -v qmd &> /dev/null; then
        info "QMD installed: $(qmd --version 2>/dev/null || echo 'ok')"
    fi
else
    info "QMD already installed: $(qmd --version 2>/dev/null || echo 'installed')"
fi

# Index the workspace collection.
# qmd collection add fails if the collection already exists, so we check first.
QMD_WORKSPACE="$HOME/.openclaw/workspace"
if command -v qmd &> /dev/null && [ -d "$QMD_WORKSPACE" ]; then
    QMD_EXISTING=$(qmd collection list 2>/dev/null | grep -c "workspace" || true)
    if [ "$QMD_EXISTING" -gt 0 ]; then
        info "QMD workspace collection already indexed — skipping"
    else
        QMD_OUT=$(qmd collection add "$QMD_WORKSPACE" --name workspace 2>&1)
        if [ $? -eq 0 ]; then
            info "QMD workspace collection indexed: $QMD_WORKSPACE"
        else
            warn "QMD collection indexing failed: $QMD_OUT"
            warn "L1 will use builtin memory until resolved"
        fi
    fi
else
    warn "QMD not available or workspace missing — skipping collection indexing"
fi

# Step 10: Update config — set WhatsApp to watch mode
echo ""
warn "Updating openclaw.json — setting WhatsApp to watch mode..."

CONFIG_FILE="/home/tomdean88/.openclaw/openclaw.json"

sudo chattr -i "$CONFIG_FILE" 2>/dev/null || true

python3 -c "
import json, os, sys

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

# Lock down Discord DM channel to owner only (prevents unsolicited exec/read requests)
# Set DISCORD_OWNER_USER_ID in ~/.openclaw/.env to enable this lockdown.
# Find your Discord user ID: Settings -> Advanced -> Enable Developer Mode,
# then right-click your username anywhere and click 'Copy User ID'.
discord_owner_id = os.environ.get('DISCORD_OWNER_USER_ID', '').strip()
if 'discord' in c.get('channels', {}):
    dc = c['channels']['discord']
    if not isinstance(dc, dict):
        dc = {}
        c['channels']['discord'] = dc
    if discord_owner_id:
        current_policy = dc.get('dmPolicy', 'open')
        if current_policy == 'allowlist' and dc.get('allowFrom') == [f'discord:{discord_owner_id}']:
            print(f'Discord dmPolicy: already locked to allowlist for user {discord_owner_id}')
        else:
            dc['dmPolicy'] = 'allowlist'
            dc['allowFrom'] = [f'discord:{discord_owner_id}']
            print(f'Discord dmPolicy: locked to allowlist for user {discord_owner_id} (was: {current_policy})')
    else:
        print('WARNING: DISCORD_OWNER_USER_ID not set in environment.')
        print('  Discord DM channel is NOT locked down — anyone who finds the bot can trigger sessions.')
        print('  To fix: add DISCORD_OWNER_USER_ID=<your_discord_user_id> to ~/.openclaw/.env')
        print('  Then source ~/.openclaw/.env and re-run this script.')
elif discord_owner_id:
    print('INFO: DISCORD_OWNER_USER_ID set but no Discord channel in config — skipping lockdown')
else:
    print('INFO: No Discord channel in config and DISCORD_OWNER_USER_ID not set — skipping Discord lockdown')

# denyCommands:
# - message.send: removed (watch mode enforces it instead)
# - calendar.add, calendar.update, calendar.delete: remain permanently blocked.
#   The requireApproval trust gate only intercepts exec.run and message.send (hardcoded
#   in the trust gate). There is no mechanism to TOTP-gate calendar at the tool level
#   without a code change. Keeping them in denyCommands is the only reliable enforcement.
#   L1 bypassing via exec.run still hits the exec.run TOTP gate.
deny = c.get('gateway', {}).get('nodes', {}).get('denyCommands', [])
if not isinstance(deny, list):
    deny = []
    c.setdefault('gateway', {}).setdefault('nodes', {})['denyCommands'] = deny
if 'message.send' in deny:
    deny.remove('message.send')
    print('Removed message.send from denyCommands — watch mode enforces this now')
for cmd in ['calendar.add', 'calendar.update', 'calendar.delete',
            'reminders.add',   # same risk as calendar.add — bypass route
            'contacts.add',    # prevent L1 silently writing to contacts
            ]:
    if cmd not in deny:
        deny.append(cmd)
        print(f'Added {cmd} to denyCommands — permanently blocked')

# Set up TOTP approval mode for trust gate (Pi-compatible, replaces socket-based approval)
c.setdefault('agents', {})
if not isinstance(c['agents'], dict):
    c['agents'] = {}
agents = c['agents'].setdefault('defaults', {})
if not isinstance(agents, dict):
    c['agents']['defaults'] = {}
    agents = c['agents']['defaults']
agents.setdefault('approvalMode', 'totp')
# totpWindowMinutes must always be 5 — migrate any other value
if agents.get('totpWindowMinutes') != 5:
    old = agents.get('totpWindowMinutes', 'unset')
    agents['totpWindowMinutes'] = 5
    print(f'totpWindowMinutes: {old} -> 5 (corrected)')
else:
    agents['totpWindowMinutes'] = 5
agents.setdefault('trustLevel', 1)
# requireApproval: only exec.run and message.send are intercepted by the trust gate
# (these are the only two actions with hardcoded trust gate enforcement in the codebase).
# Adding other tool names here has no effect — the gate doesn't call them.
required = agents.setdefault('requireApproval', [])
if not isinstance(required, list):
    agents['requireApproval'] = []
    required = agents['requireApproval']
for cmd in ['exec.run', 'message.send']:
    if cmd not in required:
        required.append(cmd)
        print(f'Added {cmd} to requireApproval')
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

# Token efficiency settings
# These reduce API cost significantly without degrading quality.
# All use setdefault — never overwrites values you've manually set.
agent_defaults = c.setdefault('agents', {}).setdefault('defaults', {})
if not isinstance(agent_defaults, dict):
    c['agents']['defaults'] = {}
    agent_defaults = c['agents']['defaults']

# 1. Heartbeat light context: heartbeat only sends HEARTBEAT.md, not SOUL.md + memory.
#    This alone cuts heartbeat token cost by ~70%.
hb = agent_defaults.setdefault('heartbeat', {})
if not isinstance(hb, dict):
    agent_defaults['heartbeat'] = {}
    hb = agent_defaults['heartbeat']
hb.setdefault('lightContext', True)

# 2. Heartbeat interval: every 60 min instead of default 30 min.
#    Halves the number of background API calls.
hb.setdefault('every', '60m')

# 3. Heartbeat active hours: no nighttime heartbeats (midnight → 7am = zero calls).
active_hours = hb.setdefault('activeHours', {})
if not isinstance(active_hours, dict):
    hb['activeHours'] = {}
    active_hours = hb['activeHours']
active_hours.setdefault('start', '07:00')
active_hours.setdefault('end', '23:00')

# 4. Cap heartbeat acknowledgement at 150 chars (it just needs to confirm tasks, not essay).
hb.setdefault('ackMaxChars', 150)

# 5. Bootstrap file size cap: each workspace file (SOUL.md, HEARTBEAT.md, memory.md)
#    truncated at 10KB instead of the default 20KB. Forces you to keep files tight.
agent_defaults.setdefault('bootstrapMaxChars', 10000)

# 6. Context pruning (Claude only): prune conversation history older than 2 hours.
#    Prevents sessions from growing unbounded. Silently skipped on non-Claude providers.
pruning = agent_defaults.setdefault('contextPruning', {})
if not isinstance(pruning, dict):
    agent_defaults['contextPruning'] = {}
    pruning = agent_defaults['contextPruning']
pruning.setdefault('mode', 'cache-ttl')
pruning.setdefault('ttl', '2h')
pruning.setdefault('keepLastAssistants', 5)

print(f'Token efficiency: lightContext={hb[\"lightContext\"]}, heartbeat every={hb[\"every\"]}, ' +
      f'activeHours={active_hours[\"start\"]}-{active_hours[\"end\"]}, ' +
      f'bootstrapMaxChars={agent_defaults[\"bootstrapMaxChars\"]}')

# Set up QMD as the memory backend — only when qmd binary is available.
# Migrates from builtin or any other value. Falls back with a clear warning
# if the qmd install above failed so the config stays consistent.
# searchMode="search" = BM25 keyword (lightweight, works on Pi 4 8GB).
import shutil as _shutil
if not isinstance(c.get('memory'), dict):
    c['memory'] = {}
memory = c['memory']
prev_backend = memory.get('backend', 'unset')
if _shutil.which('qmd'):
    memory['backend'] = 'qmd'
    if prev_backend != 'qmd':
        print(f'Memory backend: {prev_backend} -> qmd (migrated)')
    else:
        print('Memory backend: qmd (already set)')
    qmd_cfg = memory.setdefault('qmd', {})
    if not isinstance(qmd_cfg, dict):
        memory['qmd'] = {}
        qmd_cfg = memory['qmd']
    qmd_cfg.setdefault('searchMode', 'search')
    limits = qmd_cfg.setdefault('limits', {})
    if not isinstance(limits, dict):
        qmd_cfg['limits'] = {}
        limits = qmd_cfg['limits']
    limits.setdefault('timeoutMs', 15000)
    scope = qmd_cfg.setdefault('scope', {})
    if not isinstance(scope, dict):
        qmd_cfg['scope'] = {}
        scope = qmd_cfg['scope']
    scope.setdefault('default', 'allow')
    print(f'Memory QMD config: searchMode={qmd_cfg[\"searchMode\"]}, timeout={limits[\"timeoutMs\"]}ms, scope.default={scope[\"default\"]}')
else:
    print('WARNING: qmd binary not found — memory backend left as builtin (FLAG TO TOM: QMD install failed, re-run script after fixing npm)')
    memory.setdefault('backend', 'builtin')

# ---------------------------------------------------------------------------
# Model migration — replace any deprecated Anthropic model IDs with the
# current one. Runs every install so pulling and re-running fixes it.
# ---------------------------------------------------------------------------
DEPRECATED_MODELS = [
    'claude-3-5-sonnet-20241022',
    'claude-3-7-sonnet-20250219',
    'claude-3-5-haiku-20241022',
]
CURRENT_ANTHROPIC_MODEL = 'anthropic/claude-sonnet-4-5'

def _replace_model_recursive(obj):
    if isinstance(obj, dict):
        return {k: _replace_model_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_model_recursive(v) for v in obj]
    if isinstance(obj, str) and obj in DEPRECATED_MODELS:
        print(f'Model migrated: {obj} -> {CURRENT_ANTHROPIC_MODEL}')
        return CURRENT_ANTHROPIC_MODEL
    return obj

c = _replace_model_recursive(c)

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
deploy_integration "$INTEGRATIONS_SRC/microsoft/poll-calendar.py"  "$INTEGRATIONS_DST/microsoft/poll-calendar.py"
deploy_integration "$INTEGRATIONS_SRC/microsoft/send.py"           "$INTEGRATIONS_DST/microsoft/send.py"
deploy_integration "$INTEGRATIONS_SRC/microsoft/create-event.py"   "$INTEGRATIONS_DST/microsoft/create-event.py"
# sharepoint.py is intentionally NOT deployed to microsoft/ — all SharePoint
# writes must go through assistant@ only (audit trail, version history ownership).
mkdir -p "$INTEGRATIONS_DST/microsoft-l1"
deploy_integration "$INTEGRATIONS_SRC/microsoft/send.py"           "$INTEGRATIONS_DST/microsoft-l1/send.py"
deploy_integration "$INTEGRATIONS_SRC/microsoft/create-event.py"   "$INTEGRATIONS_DST/microsoft-l1/create-event.py"
deploy_integration "$INTEGRATIONS_SRC/microsoft/sharepoint.py"     "$INTEGRATIONS_DST/microsoft-l1/sharepoint.py"

# SharePoint env-var check (host is required; site_path and drive_name have sensible defaults)
if [ -z "${SHAREPOINT_HOST:-}" ]; then
    warn "SHAREPOINT_HOST not set — SharePoint commands will fail."
    warn "  Add to ~/.openclaw/.env:"
    warn "    SHAREPOINT_HOST=seerepeat.sharepoint.com"
    warn "    SHAREPOINT_SITE_PATH=/sites/StackstoneConsulting   # optional — this is the default"
    warn "    SHAREPOINT_DRIVE_NAME=Documents                    # optional — this is the default"
    warn "  Then re-run this script."
    warn "  One-time re-auth also required:"
    warn "    python3 $INTEGRATIONS_DST/microsoft-l1/sharepoint.py reauth"
else
    info "SHAREPOINT_HOST=$SHAREPOINT_HOST (SharePoint ready)"
fi
deploy_integration "$INTEGRATIONS_SRC/google/gmail_poll.py"        "$INTEGRATIONS_DST/google/gmail_poll.py"

# ---------------------------------------------------------------------------
# Garmin Connect daily health poller
# Fetches resting HR, HRV, sleep, stress, body battery, steps, last activity.
# Writes GARMIN_DAILY.md once per day at 06:10.
# First-run: tokens are cached interactively; subsequent runs are unattended.
# Requires GARMIN_EMAIL and GARMIN_PASSWORD in ~/.openclaw/.env
# ---------------------------------------------------------------------------
GARMIN_POLLER_SRC="$HOME/openclaw/attached_assets/integrations/garmin/poll-garmin.py"
GARMIN_POLLER_DST="$HOME/.openclaw/integrations/garmin/poll-garmin.py"
GARMIN_TOKEN_STORE="$HOME/.openclaw/integrations/garmin/tokens"
GARMIN_LOG="$HOME/.openclaw/workspace/memory/poll-garmin-log.txt"

if [ -f "$GARMIN_POLLER_SRC" ]; then
    mkdir -p "$HOME/.openclaw/integrations/garmin"
    mkdir -p "$GARMIN_TOKEN_STORE"
    cp "$GARMIN_POLLER_SRC" "$GARMIN_POLLER_DST"
    chmod +x "$GARMIN_POLLER_DST"
    info "Garmin poller deployed: $GARMIN_POLLER_DST"

    # Install garminconnect library (idempotent)
    if pip3 show garminconnect &>/dev/null; then
        info "garminconnect already installed: $(pip3 show garminconnect | grep ^Version | awk '{print $2}')"
    else
        warn "Installing garminconnect Python library..."
        pip3 install --quiet --break-system-packages --timeout 120 garminconnect || warn "garminconnect install failed — run manually: pip3 install --break-system-packages garminconnect"
    fi

    # Cron job at 09:00 daily (idempotent).
    # NOT 06:xx (CRM runs at 06:00) and NOT 07:xx (another job runs there).
    if [ -n "${GARMIN_EMAIL:-}" ] && [ -n "${GARMIN_PASSWORD:-}" ]; then
        GARMIN_CRON="0 9 * * * GARMIN_EMAIL=$GARMIN_EMAIL GARMIN_PASSWORD=$GARMIN_PASSWORD python3 $GARMIN_POLLER_DST >> $GARMIN_LOG 2>&1"
        ( crontab -l 2>/dev/null | grep -v "poll-garmin.py"; echo "$GARMIN_CRON" ) | crontab -
        info "Garmin cron installed: daily at 09:00"
    else
        warn "GARMIN_EMAIL / GARMIN_PASSWORD not set — Garmin cron not installed."
        warn "  Add them to ~/.openclaw/.env, source it, then re-run this script."
        warn "  First run: python3 $GARMIN_POLLER_DST  (interactive MFA if required)"
    fi
else
    warn "Garmin poller not found at $GARMIN_POLLER_SRC — skipping"
fi

# ── Daily provider reset (04:00) ──────────────────────────────────────────────
# Resets L1 to the Codex OAuth model at 4am each day — cheapest option first.
# User can switch during the day via /openai, /anthropic, /codex.
RESET_SRC="$HOME/openclaw/attached_assets/integrations/provider-switch/daily-reset.py"
RESET_DST="$HOME/.openclaw/integrations/provider-switch/daily-reset.py"
RESET_LOG="$HOME/.openclaw/workspace/memory/daily-reset.log"

if [ -f "$RESET_SRC" ]; then
    mkdir -p "$(dirname "$RESET_DST")"
    cp "$RESET_SRC" "$RESET_DST"
    chmod +x "$RESET_DST"
    RESET_CRON="0 4 * * * $PYTHON3_BIN $RESET_DST >> $RESET_LOG 2>&1"
    ( crontab -l 2>/dev/null | grep -v "daily-reset.py"; echo "$RESET_CRON" ) | crontab -
    info "Daily provider reset cron installed: 04:00 daily → ${OPENCLAW_CODEX_MODEL:-openai-codex/gpt-5.4}"
else
    warn "daily-reset.py not found at $RESET_SRC — skipping"
fi

# ── CRM lead importer (no LLM, replaces agentTurn cron) ──────────────────────
# Scheduled at 08:00 — after the prospector runs at 06:00, before Garmin at 09:00.
# NOT 06:xx (prospector/CRM cron) and NOT 07:xx (another job runs there).
CRM_POLLER_SRC="$HOME/openclaw/attached_assets/integrations/crm/poll-crm.py"
CRM_POLLER_DST="$HOME/.openclaw/integrations/crm/poll-crm.py"
CRM_LOG="$HOME/.openclaw/workspace/memory/poll-crm-log.txt"

if [ -f "$CRM_POLLER_SRC" ]; then
    mkdir -p "$(dirname "$CRM_POLLER_DST")"
    cp "$CRM_POLLER_SRC" "$CRM_POLLER_DST"
    chmod +x "$CRM_POLLER_DST"
    info "CRM importer deployed: $CRM_POLLER_DST"

    # Idempotent cron registration at 08:00 daily
    CRM_CRON="0 8 * * * python3 $CRM_POLLER_DST >> $CRM_LOG 2>&1"
    ( crontab -l 2>/dev/null | grep -v "poll-crm.py"; echo "$CRM_CRON" ) | crontab -
    info "CRM cron installed: daily at 08:00"
else
    warn "CRM importer not found at $CRM_POLLER_SRC — skipping"
fi

# ---------------------------------------------------------------------------
# System health check
# Runs at 06:55 daily — BEFORE the morning briefing active-hours window (07:00).
# Checks all cron logs and feed files for staleness / errors.
# Writes SYSTEM_HEALTH.md to the workspace — L1 reads it during morning briefing
# and prepends ⚙️ SYSTEM HEALTH section only when there are issues to report.
# ---------------------------------------------------------------------------
HEALTH_SRC="$HOME/openclaw/attached_assets/integrations/health/health_check.py"
HEALTH_DST="$HOME/.openclaw/integrations/health/health_check.py"
HEALTH_LOG="$HOME/.openclaw/integrations/health/health-check.log"

if [ -f "$HEALTH_SRC" ]; then
    mkdir -p "$HOME/.openclaw/integrations/health"
    cp "$HEALTH_SRC" "$HEALTH_DST"
    chmod +x "$HEALTH_DST"
    info "System health check deployed: $HEALTH_DST"

    HEALTH_CRON="55 6 * * * python3 $HEALTH_DST >> $HEALTH_LOG 2>&1"
    ( crontab -l 2>/dev/null | grep -v "health_check.py"; echo "$HEALTH_CRON" ) | crontab -
    info "System health check cron installed: daily at 06:55"
else
    warn "System health check not found at $HEALTH_SRC — skipping"
fi

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

# ---------------------------------------------------------------------------
# Prospector: bounce/unsub queue processor
# Deploys process_queue.sh and installs a 30-minute cron job.
# L1 appends email addresses to pending_bounces.txt / pending_unsubs.txt
# (no exec.run / no TOTP needed); this script picks them up and calls manage.py.
# ---------------------------------------------------------------------------
PROSPECTOR_DIR="$HOME/prospector"
PROSPECTOR_SCRIPT_SRC="$HOME/openclaw/attached_assets/prospector/process_queue.sh"
PROSPECTOR_SCRIPT_DST="$PROSPECTOR_DIR/process_queue.sh"

if [ -f "$PROSPECTOR_SCRIPT_SRC" ]; then
    mkdir -p "$PROSPECTOR_DIR/logs"
    cp "$PROSPECTOR_SCRIPT_SRC" "$PROSPECTOR_SCRIPT_DST"
    chmod +x "$PROSPECTOR_SCRIPT_DST"
    info "Prospector queue processor deployed: $PROSPECTOR_SCRIPT_DST"

    # Touch queue files so L1 can append to them immediately
    touch "$PROSPECTOR_DIR/pending_bounces.txt"
    touch "$PROSPECTOR_DIR/pending_unsubs.txt"

    # Install cron job (idempotent — removes any old entry first)
    CRON_JOB="*/30 * * * * bash $PROSPECTOR_SCRIPT_DST >> $PROSPECTOR_DIR/logs/queue_processor.log 2>&1"
    ( crontab -l 2>/dev/null | grep -v "process_queue.sh"; echo "$CRON_JOB" ) | crontab -
    info "Cron job installed: runs every 30 minutes"
else
    warn "Prospector script not found at $PROSPECTOR_SCRIPT_SRC — skipping queue processor setup"
fi

# ---------------------------------------------------------------------------
# SharePoint cache poller — runs every 15 min, writes SHAREPOINT_INDEX.md
# so L1 can read the document tree without exec.run / TOTP.
# ---------------------------------------------------------------------------
SP_CACHE_SRC="$HOME/openclaw/attached_assets/integrations/microsoft/sharepoint_cache_poller.py"
SP_CACHE_DST="$HOME/.openclaw/integrations/microsoft/sharepoint_cache_poller.py"
SP_CACHE_LOG="$HOME/.openclaw/integrations/microsoft/sp-cache-poller.log"

if [ -f "$SP_CACHE_SRC" ]; then
    mkdir -p "$HOME/.openclaw/integrations/microsoft"
    cp "$SP_CACHE_SRC" "$SP_CACHE_DST"
    chmod +x "$SP_CACHE_DST"
    info "SharePoint cache poller deployed: $SP_CACHE_DST"

    SP_CACHE_CRON="*/15 * * * * python3 $SP_CACHE_DST >> $SP_CACHE_LOG 2>&1"
    ( crontab -l 2>/dev/null | grep -v "sharepoint_cache_poller.py"; echo "$SP_CACHE_CRON" ) | crontab -
    info "SharePoint cache poller cron installed: every 15 minutes → SHAREPOINT_INDEX.md"
else
    warn "SharePoint cache poller not found at $SP_CACHE_SRC — skipping"
fi

# ---------------------------------------------------------------------------
# SharePoint queue processor — runs every 1 min, executes ops L1 writes
# to sharepoint-queue.json without exec.run / TOTP.
# ---------------------------------------------------------------------------
SP_QUEUE_SRC="$HOME/openclaw/attached_assets/integrations/microsoft/sharepoint_queue_processor.py"
SP_QUEUE_DST="$HOME/.openclaw/integrations/microsoft/sharepoint_queue_processor.py"
SP_QUEUE_LOG="$HOME/.openclaw/integrations/microsoft/sp-queue-processor.log"

if [ -f "$SP_QUEUE_SRC" ]; then
    mkdir -p "$HOME/.openclaw/integrations/microsoft"
    cp "$SP_QUEUE_SRC" "$SP_QUEUE_DST"
    chmod +x "$SP_QUEUE_DST"
    info "SharePoint queue processor deployed: $SP_QUEUE_DST"

    # Initialise empty queue if it doesn't exist yet
    QUEUE_FILE="$HOME/.openclaw/sharepoint-queue.json"
    [ -f "$QUEUE_FILE" ] || echo "[]" > "$QUEUE_FILE"

    SP_QUEUE_CRON="* * * * * python3 $SP_QUEUE_DST >> $SP_QUEUE_LOG 2>&1"
    ( crontab -l 2>/dev/null | grep -v "sharepoint_queue_processor.py"; echo "$SP_QUEUE_CRON" ) | crontab -
    info "SharePoint queue processor cron installed: every 1 minute → SHAREPOINT_RESULT.md"
else
    warn "SharePoint queue processor not found at $SP_QUEUE_SRC — skipping"
fi

# ---------------------------------------------------------------------------
# Stackstone networking report poller
# Polls /api/integration/reports every 5 minutes and sends unsent reports
# as branded emails via MS Graph. No tunnel or endpoint needed on the Pi.
# ---------------------------------------------------------------------------
SS_POLLER_SRC="$HOME/openclaw/attached_assets/integrations/stackstone/report_poller.py"
SS_POLLER_DST="$HOME/.openclaw/integrations/stackstone/report_poller.py"
SS_POLLER_LOG="$HOME/.openclaw/integrations/stackstone/poller.log"

if [ -f "$SS_POLLER_SRC" ]; then
    mkdir -p "$HOME/.openclaw/integrations/stackstone"
    cp "$SS_POLLER_SRC" "$SS_POLLER_DST"
    chmod +x "$SS_POLLER_DST"
    info "Stackstone report poller deployed: $SS_POLLER_DST"

    SS_CRON="*/5 * * * * python3 $SS_POLLER_DST >> $SS_POLLER_LOG 2>&1"
    ( crontab -l 2>/dev/null | grep -v "stackstone/report_poller.py"; echo "$SS_CRON" ) | crontab -
    info "Stackstone report poller cron installed: runs every 5 minutes"
else
    warn "Stackstone report poller not found at $SS_POLLER_SRC — skipping"
fi

# ---------------------------------------------------------------------------
# Stackstone website enquiry poller  [REVENUE CRITICAL]
# Polls /api/integration/enquiries every 2 minutes.
# Fires immediate Telegram alert for each new contact-form lead.
# Separate from report views — this is direct inbound, must alert immediately.
# ---------------------------------------------------------------------------
SS_ENQ_SRC="$HOME/openclaw/attached_assets/integrations/stackstone/enquiry_poller.py"
SS_ENQ_DST="$HOME/.openclaw/integrations/stackstone/enquiry_poller.py"
SS_ENQ_LOG="$HOME/.openclaw/integrations/stackstone/enquiry-poller.log"

if [ -f "$SS_ENQ_SRC" ]; then
    mkdir -p "$HOME/.openclaw/integrations/stackstone"
    cp "$SS_ENQ_SRC" "$SS_ENQ_DST"
    chmod +x "$SS_ENQ_DST"
    info "Stackstone enquiry poller deployed: $SS_ENQ_DST"

    SS_ENQ_CRON="*/2 * * * * python3 $SS_ENQ_DST >> $SS_ENQ_LOG 2>&1"
    ( crontab -l 2>/dev/null | grep -v "stackstone/enquiry_poller.py"; echo "$SS_ENQ_CRON" ) | crontab -
    info "Stackstone enquiry poller cron installed: runs every 2 minutes"
else
    warn "Stackstone enquiry poller not found at $SS_ENQ_SRC — skipping"
fi

# ---------------------------------------------------------------------------
# OpenClaw Management Bot
# Separate Telegram bot that intercepts system commands BEFORE the LLM.
# Works even when OpenAI is rate-limited or the gateway is completely down.
# Commands: /status /openai /anthropic /restart /pull /reboot
# Requires a SECOND Telegram bot token (separate from the main OpenClaw bot).
# ---------------------------------------------------------------------------
MGMT_BOT_SRC="$HOME/openclaw/attached_assets/integrations/mgmt-bot/mgmt-bot.py"
MGMT_BOT_DST="$HOME/.openclaw/integrations/mgmt-bot/mgmt-bot.py"
MGMT_SERVICE="openclaw-mgmt-bot.service"
MGMT_SERVICE_FILE="$HOME/.config/systemd/user/$MGMT_SERVICE"

if [ -f "$MGMT_BOT_SRC" ]; then
    mkdir -p "$HOME/.openclaw/integrations/mgmt-bot"
    cp "$MGMT_BOT_SRC" "$MGMT_BOT_DST"
    chmod +x "$MGMT_BOT_DST"
    info "Management bot deployed: $MGMT_BOT_DST"

    # Write systemd user service
    mkdir -p "$HOME/.config/systemd/user"
    cat > "$MGMT_SERVICE_FILE" << EOF
[Unit]
Description=OpenClaw Management Bot (provider switch, restart, reboot, pull)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $MGMT_BOT_DST
Restart=always
RestartSec=10
EnvironmentFile=-$HOME/.openclaw/.env
StandardOutput=append:$HOME/.openclaw/integrations/mgmt-bot/mgmt-bot.log
StandardError=append:$HOME/.openclaw/integrations/mgmt-bot/mgmt-bot.log

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload

    # Install cryptography package (needed for /soul SOUL.md re-encryption)
    if pip3 show cryptography &>/dev/null; then
        info "cryptography package already installed"
    else
        warn "Installing cryptography Python package (needed for /soul command)…"
        pip3 install --quiet --break-system-packages --timeout 120 cryptography \
            || warn "cryptography install failed — run manually: pip3 install --break-system-packages cryptography"
    fi

    # Env-var check before enabling
    if [ -z "${MGMT_BOT_TOKEN:-}" ] || [ -z "${MGMT_BOT_CHAT_ID:-}" ]; then
        warn "MGMT_BOT_TOKEN or MGMT_BOT_CHAT_ID not set — management bot not started."
        warn "  Steps to set up:"
        warn "  1. Message @BotFather on Telegram → /newbot → copy the token"
        warn "  2. Message @userinfobot on Telegram → copy your numeric chat ID"
        warn "  3. Add to ~/.openclaw/.env:"
        warn "       MGMT_BOT_TOKEN=<token>"
        warn "       MGMT_BOT_CHAT_ID=<your_numeric_id>"
        warn "       OPENCLAW_OPENAI_MODEL=openai/gpt-5.4"
        warn "       OPENCLAW_ANTHROPIC_MODEL=anthropic/claude-sonnet-4-5"
        warn "  4. Re-run this install script to start the service"
    else
        systemctl --user enable "$MGMT_SERVICE" 2>/dev/null || true
        systemctl --user restart "$MGMT_SERVICE"
        info "Management bot service enabled and started: $MGMT_SERVICE"
        info "  Test: send /status to your management bot on Telegram"
    fi
else
    warn "Management bot not found at $MGMT_BOT_SRC — skipping"
fi

# ---------------------------------------------------------------------------
# WhatsApp rolling recent file
# Generates WHATSAPP_RECENT.md (last 48h) from the full WHATSAPP_LOG.md.
# L1 reads WHATSAPP_RECENT.md — keeps context small without losing history.
# ---------------------------------------------------------------------------
WA_RECENT_SRC="$HOME/openclaw/attached_assets/scripts/whatsapp_recent.sh"
WA_RECENT_DST="$HOME/.openclaw/scripts/whatsapp_recent.sh"

if [ -f "$WA_RECENT_SRC" ]; then
    mkdir -p "$HOME/.openclaw/scripts"
    cp "$WA_RECENT_SRC" "$WA_RECENT_DST"
    chmod +x "$WA_RECENT_DST"
    info "WhatsApp recent-file script deployed: $WA_RECENT_DST"

    # Run it immediately so WHATSAPP_RECENT.md exists right after install
    bash "$WA_RECENT_DST" || true

    # Install cron job (idempotent)
    WA_CRON="*/15 * * * * bash $WA_RECENT_DST"
    ( crontab -l 2>/dev/null | grep -v "whatsapp_recent.sh"; echo "$WA_CRON" ) | crontab -
    info "WhatsApp recent-file cron installed: runs every 15 minutes"
else
    warn "WhatsApp recent script not found at $WA_RECENT_SRC — skipping"
fi

# Create shared known-contacts.txt (read by ALL email pollers — Microsoft, Gmail, etc.)
# This is the single source of truth for trusted senders across all email channels.
KNOWN_CONTACTS_FILE="$HOME/.openclaw/integrations/known-contacts.txt"
if [ ! -f "$KNOWN_CONTACTS_FILE" ]; then
    mkdir -p "$(dirname "$KNOWN_CONTACTS_FILE")"
    cat > "$KNOWN_CONTACTS_FILE" << 'EOF'
# Known/trusted email contacts — shared across all email integrations
# One email address per line. Lines starting with # are ignored.
# Both Microsoft (Outlook) and Gmail pollers read from this file.
# Emails from these addresses get body previews in *_INBOX.md.
# All other senders → metadata only in *_EXTERNAL.md (no body, no injection risk).
stuart.hobin@croydemedical.co.uk
emily.thomas@croydemedical.co.uk
john@reveela.com
ed.patchett@7thsense.one
johnjamesmarsh@hotmail.com
andy.barrett@sjpp.co.uk
olivia.collington@collingtonwinter.co.uk
EOF
    info "Created shared known-contacts.txt"
else
    info "known-contacts.txt already exists — not overwritten"
fi

# Create per-provider last-seen state files (provider-specific, not shared)
LAST_SEEN_MS="$HOME/.openclaw/workspace/memory/last-seen-emails-microsoft.md"
LAST_SEEN_OLD="$HOME/.openclaw/workspace/memory/last-seen-emails.md"
if [ ! -f "$LAST_SEEN_MS" ]; then
    mkdir -p "$(dirname "$LAST_SEEN_MS")"
    if [ -f "$LAST_SEEN_OLD" ]; then
        # Migrate existing state so the poller doesn't re-alert on already-seen emails
        cp "$LAST_SEEN_OLD" "$LAST_SEEN_MS"
        info "Migrated last-seen-emails.md → last-seen-emails-microsoft.md"
    else
        cat > "$LAST_SEEN_MS" << 'EOF'
# Last Seen Emails — Microsoft (Known Contacts)
# Format: contact-email | last-seen-timestamp (ISO 8601)
stuart.hobin@croydemedical.co.uk | 
emily.thomas@croydemedical.co.uk | 
john@reveela.com | 
ed.patchett@7thsense.one | 
johnjamesmarsh@hotmail.com | 
andy.barrett@sjpp.co.uk | 
olivia.collington@collingtonwinter.co.uk | 
EOF
        info "Created last-seen-emails-microsoft.md template"
    fi
else
    info "last-seen-emails-microsoft.md already exists — not overwritten"
fi

LAST_SEEN_GM="$HOME/.openclaw/workspace/memory/last-seen-emails-gmail.md"
if [ ! -f "$LAST_SEEN_GM" ]; then
    mkdir -p "$(dirname "$LAST_SEEN_GM")"
    cat > "$LAST_SEEN_GM" << 'EOF'
# Last Seen Emails — Gmail (Known Contacts)
# Format: contact-email | last-seen-date-header
stuart.hobin@croydemedical.co.uk | 
emily.thomas@croydemedical.co.uk | 
john@reveela.com | 
ed.patchett@7thsense.one | 
johnjamesmarsh@hotmail.com | 
andy.barrett@sjpp.co.uk | 
olivia.collington@collingtonwinter.co.uk | 
EOF
    info "Created last-seen-emails-gmail.md template"
else
    info "last-seen-emails-gmail.md already exists — not overwritten"
fi

# Gmail poller setup note
GMAIL_CREDS="$HOME/.openclaw/integrations/google/gmail-credentials.json"
if [ ! -f "$GMAIL_CREDS" ]; then
    warn "Gmail poller not yet authorised. To enable:"
    warn "  1. Go to console.cloud.google.com → enable Gmail API"
    warn "  2. Create OAuth 2.0 Client ID (Desktop app)"
    warn "  3. Download credentials JSON → $GMAIL_CREDS"
    warn "  4. pip3 install google-auth google-auth-oauthlib google-api-python-client"
    warn "  5. Run once manually: python3 $INTEGRATIONS_DST/google/gmail_poll.py"
    warn "     (opens browser for consent, saves token automatically)"
else
    info "Gmail credentials file found — poller ready to run"
fi

# Migrate old Outlook feed file names → Microsoft
# The poller now writes MICROSOFT_INBOX.md / MICROSOFT_EXTERNAL.md.
# If the old OUTLOOK_*.md files still exist, rename them so content isn't lost
# and SOUL.md references (once updated) resolve immediately.
MEMORY_DIR="$HOME/.openclaw/workspace/memory"
for OLD_NAME in OUTLOOK_INBOX OUTLOOK_EXTERNAL; do
    NEW_NAME="${OLD_NAME/OUTLOOK/MICROSOFT}"
    OLD_FILE="$MEMORY_DIR/${OLD_NAME}.md"
    NEW_FILE="$MEMORY_DIR/${NEW_NAME}.md"
    if [ -f "$OLD_FILE" ] && [ ! -f "$NEW_FILE" ]; then
        mv "$OLD_FILE" "$NEW_FILE"
        info "Migrated ${OLD_NAME}.md → ${NEW_NAME}.md"
    elif [ -f "$OLD_FILE" ] && [ -f "$NEW_FILE" ]; then
        rm "$OLD_FILE"
        info "Removed stale ${OLD_NAME}.md (${NEW_NAME}.md already exists)"
    fi
done

# Run config drift check immediately after deploy
if [ -f "$INTEGRATIONS_DST/config-check/check.py" ]; then
    echo ""
    warn "Running config drift check..."
    python3 "$INTEGRATIONS_DST/config-check/check.py" || true
fi

# Step 11c: Email poller systemd user services
# These run the Python pollers as managed background services — they survive
# reboots, restart automatically on failure, and never require exec.run or
# manual intervention to keep email feeds current.
warn "Setting up email poller services..."
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"
PYTHON3_BIN="$(which python3 2>/dev/null || echo /usr/bin/python3)"
MS_POLLER="$HOME/.openclaw/integrations/microsoft/poll.py"
GM_POLLER="$HOME/.openclaw/integrations/google/gmail_poll.py"
MS_LOG="$HOME/.openclaw/workspace/memory/poll-microsoft-log.txt"
AS_LOG="$HOME/.openclaw/workspace/memory/poll-assistant-log.txt"
GM_LOG="$HOME/.openclaw/workspace/memory/poll-gmail-log.txt"

# Backwards-compat: migrate old flat token.json → token-microsoft.json so the
# parameterised poller (--account microsoft) finds its token automatically.
OLD_MS_TOKEN="$HOME/.openclaw/integrations/microsoft/token.json"
NEW_MS_TOKEN="$HOME/.openclaw/integrations/microsoft/token-microsoft.json"
if [ -f "$OLD_MS_TOKEN" ] && [ ! -f "$NEW_MS_TOKEN" ]; then
    cp "$OLD_MS_TOKEN" "$NEW_MS_TOKEN"
    info "Migrated token.json → token-microsoft.json for multi-account support"
fi

cat > "$SYSTEMD_USER_DIR/openclaw-email-microsoft.service" << SVCEOF
[Unit]
Description=OpenClaw Microsoft Email Poller (personal)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart=$PYTHON3_BIN $MS_POLLER --account microsoft --label "Tom Outlook"
Restart=on-failure
RestartSec=60
StandardOutput=append:$MS_LOG
StandardError=append:$MS_LOG

[Install]
WantedBy=default.target
SVCEOF

cat > "$SYSTEMD_USER_DIR/openclaw-email-assistant.service" << SVCEOF
[Unit]
Description=OpenClaw Microsoft Email Poller (assistant@)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart=$PYTHON3_BIN $MS_POLLER --account assistant --label "L1 Assistant"
Restart=on-failure
RestartSec=60
StandardOutput=append:$AS_LOG
StandardError=append:$AS_LOG

[Install]
WantedBy=default.target
SVCEOF

CAL_POLLER="$HOME/.openclaw/integrations/microsoft/poll-calendar.py"
CAL_LOG="$HOME/.openclaw/workspace/memory/poll-calendar-log.txt"

cat > "$SYSTEMD_USER_DIR/openclaw-calendar-microsoft.service" << SVCEOF
[Unit]
Description=OpenClaw Microsoft Calendar Poller (next 14 days)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart=$PYTHON3_BIN $CAL_POLLER
Restart=on-failure
RestartSec=60
StandardOutput=append:$CAL_LOG
StandardError=append:$CAL_LOG

[Install]
WantedBy=default.target
SVCEOF

cat > "$SYSTEMD_USER_DIR/openclaw-email-gmail.service" << SVCEOF
[Unit]
Description=OpenClaw Gmail Email Poller
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart=$PYTHON3_BIN $GM_POLLER
Restart=on-failure
RestartSec=60
StandardOutput=append:$GM_LOG
StandardError=append:$GM_LOG

[Install]
WantedBy=default.target
SVCEOF

# Allow user services to start at boot even without an active login session
loginctl enable-linger "$USER" 2>/dev/null || true

systemctl --user daemon-reload

# Personal Microsoft poller — start if token exists
systemctl --user enable openclaw-email-microsoft.service 2>/dev/null || true
if [ -f "$NEW_MS_TOKEN" ] || [ -f "$OLD_MS_TOKEN" ]; then
    systemctl --user restart openclaw-email-microsoft.service && \
        info "Microsoft email poller (personal) running" || \
        warn "Microsoft email poller (personal) failed to start — check $MS_LOG"
else
    warn "Microsoft poller (personal) enabled but not started — token missing, run auth first"
fi

# Assistant poller — credentials live in the existing microsoft-l1 folder
# (set up previously for assistant@stackstoneconsulting.co.uk)
AS_TOKEN_L1="$HOME/.openclaw/integrations/microsoft-l1/token.json"
AS_TOKEN_NEW="$HOME/.openclaw/integrations/microsoft/token-assistant.json"
# Resolve whichever token path exists
if [ -f "$AS_TOKEN_L1" ]; then
    RESOLVED_AS_TOKEN="$AS_TOKEN_L1"
elif [ -f "$AS_TOKEN_NEW" ]; then
    RESOLVED_AS_TOKEN="$AS_TOKEN_NEW"
else
    RESOLVED_AS_TOKEN=""
fi

systemctl --user enable openclaw-email-assistant.service 2>/dev/null || true

if [ -n "$RESOLVED_AS_TOKEN" ]; then
    # Rewrite the service unit to pass the correct token path
    cat > "$SYSTEMD_USER_DIR/openclaw-email-assistant.service" << SVCEOF2
[Unit]
Description=OpenClaw Microsoft Email Poller (assistant@)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart=$PYTHON3_BIN $MS_POLLER --account assistant --label "L1 Assistant" --token-file $RESOLVED_AS_TOKEN
Restart=on-failure
RestartSec=60
StandardOutput=append:$AS_LOG
StandardError=append:$AS_LOG

[Install]
WantedBy=default.target
SVCEOF2
    systemctl --user daemon-reload
    systemctl --user restart openclaw-email-assistant.service && \
        info "Assistant email poller running — token: $RESOLVED_AS_TOKEN → ASSISTANT_INBOX.md" || \
        warn "Assistant email poller failed to start — check $AS_LOG"
else
    warn "Assistant email poller not started — no token found at $AS_TOKEN_L1 or $AS_TOKEN_NEW"
    warn "Once token exists, run: systemctl --user restart openclaw-email-assistant.service"
fi

# Gmail poller — start only if both credentials AND token exist
GM_CREDS="$HOME/.openclaw/integrations/google/gmail-credentials.json"
GM_TOKEN="$HOME/.openclaw/integrations/google/gmail-token.json"
systemctl --user enable openclaw-email-gmail.service 2>/dev/null || true
if [ -f "$GM_CREDS" ] && [ -f "$GM_TOKEN" ]; then
    systemctl --user restart openclaw-email-gmail.service && \
        info "Gmail email poller running (systemd service)" || \
        warn "Gmail email poller failed to start — check $GM_LOG"
elif [ -f "$GM_CREDS" ]; then
    warn "Gmail poller enabled but not started — run it once manually to complete OAuth"
else
    info "Gmail poller not started (credentials not configured yet)"
fi

# Calendar poller — shares the same token as the personal Microsoft email poller
systemctl --user enable openclaw-calendar-microsoft.service 2>/dev/null || true
if [ -f "$NEW_MS_TOKEN" ] || [ -f "$OLD_MS_TOKEN" ]; then
    systemctl --user restart openclaw-calendar-microsoft.service && \
        info "Calendar poller running — writing OUTLOOK_CALENDAR.md every 15 min" || \
        warn "Calendar poller failed to start — check $CAL_LOG"
else
    warn "Calendar poller enabled but not started — Microsoft token missing, run auth first"
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

# Step 12b-pre: Patch gateway service unit to include ~/.npm-packages/bin in PATH.
# The systemd user service doesn't inherit the shell PATH set in .bashrc, so
# the gateway can't find qmd (installed to ~/.npm-packages/bin) at runtime.
# We inject an Environment=PATH= line so every restart picks it up.
GATEWAY_SVC="$HOME/.config/systemd/user/openclaw-gateway.service"
NPM_BIN="$HOME/.npm-packages/bin"

if [ -f "$GATEWAY_SVC" ]; then
    if grep -q "npm-packages" "$GATEWAY_SVC"; then
        info "Gateway service PATH already includes ~/.npm-packages/bin"
    else
        # Insert Environment line after [Service] section header
        sed -i "/^\[Service\]/a Environment=\"PATH=$NPM_BIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"" \
            "$GATEWAY_SVC"
        systemctl --user daemon-reload
        info "Gateway service patched — PATH now includes $NPM_BIN"
    fi
else
    warn "Gateway service unit not found at $GATEWAY_SVC — skipping PATH patch"
fi

# Step 12b: Restart L1 — prefer the systemd gateway service; fall back to l1-start.sh
echo ""
warn "Restarting L1..."
if systemctl --user is-enabled openclaw-gateway.service 2>/dev/null | grep -q "enabled\|static"; then
    systemctl --user restart openclaw-gateway.service && \
        info "openclaw-gateway.service restarted — new code is live" || \
        warn "Failed to restart openclaw-gateway.service"
else
    # Fallback: kill any stale node process then use the start script
    pkill -f "node.*openclaw" 2>/dev/null || true
    pkill -f "ts-node.*openclaw" 2>/dev/null || true
    sleep 2
    ~/l1-start.sh
fi

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
echo "  Stackstone report poller:"
echo "    Runs every 5 min — polls stackstoneconsulting.co.uk/api/integration/reports"
echo "    Uses INTEGRATION_API_KEY (already configured) and the MS Graph token."
echo "    If STACKSTONE_BASE_URL is not set it defaults to https://stackstoneconsulting.co.uk"
echo "    To override (e.g. for testing against a Replit dev URL):"
echo "      export STACKSTONE_BASE_URL=https://your-replit-dev-url.replit.dev"
echo "    Logs: ~/.openclaw/integrations/stackstone/poller.log"
echo "    Test manually: python3 ~/.openclaw/integrations/stackstone/report_poller.py"
echo ""
echo "  Stackstone WEBSITE ENQUIRY poller [REVENUE CRITICAL — separate from report views]:"
echo "    Runs every 2 min — polls stackstoneconsulting.co.uk/api/integration/enquiries"
echo "    Fires immediate Telegram alert for each new contact form / website lead"
echo "    Alert includes: name, company, role, email, phone, message summary"
echo "    Staleness alert fires if no enquiries seen in 24h (every 6h max)"
echo "    Requires website to expose: GET /api/integration/enquiries"
echo "                                PATCH /api/integration/enquiries/:id/alerted"
echo "    State:  ~/.openclaw/integrations/stackstone/enquiry-poller-state.json"
echo "    Logs:   ~/.openclaw/integrations/stackstone/enquiry-poller.log"
echo "    Test manually: python3 ~/.openclaw/integrations/stackstone/enquiry_poller.py"
echo ""
echo "  System health check (automated — runs at 06:55 daily):"
echo "    Checks: all cron logs (staleness + ERROR patterns), all feed files (freshness)"
echo "    Writes: ~/.openclaw/workspace/SYSTEM_HEALTH.md (empty = all OK)"
echo "    L1 reads this file at morning briefing start and includes ⚙️ SYSTEM HEALTH"
echo "    section only when non-empty. No section shown when everything is fine."
echo "    Logs:   ~/.openclaw/integrations/health/health-check.log"
echo "    Test manually: python3 ~/.openclaw/integrations/health/health_check.py"
echo "    Force a warning (for testing): touch -d '2 hours ago' ~/.openclaw/workspace/MICROSOFT_INBOX.md"
echo "    ── SOUL.md instruction to add (morning briefing section): ──────────────"
echo "    At the start of your morning briefing, read SYSTEM_HEALTH.md."
echo "    If it is non-empty, prepend this BEFORE anything else:"
echo "      ⚙️ SYSTEM HEALTH"
echo "      [paste content verbatim — one bullet per issue]"
echo "    If SYSTEM_HEALTH.md is empty or missing, omit this section entirely."
echo "    ─────────────────────────────────────────────────────────────────────────"
echo ""
echo "  Calendar poller (systemd service: openclaw-calendar-microsoft):"
echo "    Polls Outlook calendar every 15 min — writes OUTLOOK_CALENDAR.md (next 14 days)"
echo "    Shares the Microsoft OAuth token (token-microsoft.json)"
echo "    Logs: ~/.openclaw/workspace/memory/poll-calendar-log.txt"
echo "    Status: systemctl --user status openclaw-calendar-microsoft.service"
echo ""
echo "  Management Bot (pre-LLM Telegram commands — works even when OpenAI is rate-limited):"
echo "    Service: systemctl --user status openclaw-mgmt-bot.service"
echo "    Logs:    ~/.openclaw/integrations/mgmt-bot/mgmt-bot.log"
echo "    Commands (send to your SECOND Telegram bot, not the main L1 bot):"
echo "      /status    — model, gateway state, uptime, reboot safety"
echo "      /health    — run system health check now"
echo "      /logs      — recent errors across all poller logs"
echo "      /disk      — disk space on the Pi"
echo "      /openai    — switch to OpenAI model + restart gateway"
echo "      /anthropic — switch to Anthropic model + restart gateway"
echo "      /restart   — restart L1 gateway"
echo "      /garmin    — manually trigger Garmin poller"
echo "      /pull      — git pull latest from GitHub"
echo "      /reboot    — reboot Pi (refused if auto-start not configured)"
echo "      /soul      — upload new SOUL.md as .docx → converts, encrypts, restarts"
echo "    Soul update flow: send /soul → bot prompts → upload .docx → done"
echo "    Requires in ~/.openclaw/.env:"
echo "      MGMT_BOT_TOKEN=<second bot token from BotFather>"
echo "      MGMT_BOT_CHAT_ID=<your numeric Telegram ID from @userinfobot>"
echo "      OPENCLAW_OPENAI_MODEL=openai/gpt-5.4"
echo "      OPENCLAW_ANTHROPIC_MODEL=anthropic/claude-sonnet-4-5"
echo "      OPENCLAW_VAULT_PASSPHRASE=<already set if vault is in use>"
echo ""
echo "  SharePoint document management (assistant@ identity — write-only via L1):"
echo "    Script: ~/.openclaw/integrations/microsoft-l1/sharepoint.py"
echo "    Commands: list <path> | read <path> | create <path> --content-file <tmp>"
echo "              update <path> --content-file <tmp> | append <path> --content-file <tmp>"
echo "    No delete / rename / move — excluded by design. Clean up originals manually in the SP web UI."
echo "    Requires in ~/.openclaw/.env:"
echo "      SHAREPOINT_HOST=seerepeat.sharepoint.com"
echo "      SHAREPOINT_SITE_PATH=/sites/StackstoneConsulting   # this is already the default"
echo "      SHAREPOINT_DRIVE_NAME=Documents                    # this is already the default"
echo "    One-time re-auth (device code — works on Pi without a browser):"
echo "      python3 ~/.openclaw/integrations/microsoft-l1/sharepoint.py reauth"
echo "    Test: python3 ~/.openclaw/integrations/microsoft-l1/sharepoint.py list /"
echo ""
echo "  Garmin Connect poller:"
echo "    Runs daily at 09:00 — writes GARMIN_DAILY.md (resting HR, HRV, sleep, stress, body battery, steps, last activity)"
echo "    Also writes GARMIN_ARCHIVE.md — rolling 28-day compact history for L1 trend analysis"
echo "    (09:00 chosen — 06:xx busy with CRM, 07:xx busy with another job)"
echo "    Requires GARMIN_EMAIL and GARMIN_PASSWORD in ~/.openclaw/.env"
echo "    First-run (interactive MFA if needed): python3 ~/.openclaw/integrations/garmin/poll-garmin.py"
echo "    Logs: ~/.openclaw/workspace/memory/poll-garmin-log.txt"
echo ""
echo "  CRM lead importer (no LLM — replaces agentTurn cron):"
echo "    Runs daily at 08:00 — imports new leads from ~/prospects/YYYYMMDD/ CSVs into crm.md"
echo "    Zero LLM overhead — pure Python CSV parse + markdown append (~1 second runtime)"
echo "    Bounce/unsubscribe/reply detection still handled by L1 during inbox reads"
echo "    Logs: ~/.openclaw/workspace/memory/poll-crm-log.txt"
echo "    Test manually: python3 ~/.openclaw/integrations/crm/poll-crm.py"
echo ""
echo "  Memory backend: QMD (local-first search, no API keys, no cloud)"
echo "    Mode: search (BM25 keyword — fast, reliable, Pi-safe)"
echo "    L1 can now search SOUL.md, notes, and workspace files across sessions"
echo "    Verify: openclaw doctor"
echo "    (One-time note: if memory_search is absent, index the collection manually:"
echo "      qmd collection add ~/.openclaw/workspace --name workspace"
echo "      then: systemctl --user restart openclaw-gateway.service)"
echo "    Upgrade to semantic search (Pi 4 8GB supports it):"
echo "      sudo chattr -i ~/.openclaw/openclaw.json"
echo "      # edit: memory.qmd.searchMode = \"vsearch\""
echo "      sudo chattr +i ~/.openclaw/openclaw.json"
echo "      systemctl --user restart openclaw-gateway.service"
echo ""
