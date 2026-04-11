#!/bin/bash
# provision-workspace.sh — Full workspace provisioning and verification
# Sets up the Telegram-controlled coding environment on the Pi.
#
# Usage (after git pull):
#   bash ~/openclaw/attached_assets/provision-workspace.sh
#
# Rules:
#   - NEVER overwrites existing files (safe to re-run)
#   - Creates missing directories and files from templates
#   - Runs the full verification checklist
#   - Prints a clear PASS/FAIL summary

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0

info()  { echo -e "${GREEN}[✓] $1${NC}"; ((PASS++)); }
warn()  { echo -e "${YELLOW}[!] $1${NC}"; ((WARN++)); }
fail()  { echo -e "${RED}[✗] $1${NC}"; ((FAIL++)); }
head()  { echo -e "\n${BLUE}── $1 ──${NC}"; }

REPO="$HOME/openclaw"
TEMPLATES="$REPO/attached_assets/workspace-templates"
WORKSPACE="$HOME/.openclaw/workspace"

# ── Load .env ─────────────────────────────────────────────────────────────────
ENV_FILE="$HOME/.openclaw/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║     OpenClaw Workspace Provisioning & Verification   ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── Step 1: Pi environment ─────────────────────────────────────────────────────
head "1. Pi environment"

CURRENT_USER=$(whoami)
if [ "$CURRENT_USER" = "tomdean88" ]; then
    info "User: $CURRENT_USER"
else
    warn "User is $CURRENT_USER (expected tomdean88)"
fi

if [ -d "$HOME" ]; then
    info "Home directory: $HOME"
else
    fail "Home directory not found"
fi

OS=$(grep -i "^ID=" /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')
if echo "$OS" | grep -qiE "debian|raspbian|ubuntu"; then
    info "OS: $OS (Debian-based ✓)"
else
    warn "OS: $OS (expected Debian/Raspbian)"
fi

# ── Step 2: OpenClaw ──────────────────────────────────────────────────────────
head "2. OpenClaw"

if command -v openclaw &>/dev/null; then
    info "openclaw binary found: $(which openclaw)"
else
    fail "openclaw not found on PATH"
fi

GATEWAY_SVC="$HOME/.config/systemd/user/openclaw-gateway.service"
if [ -f "$GATEWAY_SVC" ]; then
    info "Gateway service unit found"
    if systemctl --user is-active openclaw-gateway.service &>/dev/null; then
        info "Gateway service: running"
    else
        warn "Gateway service: not running — attempting restart"
        systemctl --user restart openclaw-gateway.service 2>/dev/null && \
            info "Gateway restarted" || fail "Gateway restart failed"
    fi
else
    fail "Gateway service unit not found at $GATEWAY_SVC"
fi

# ── Step 3: Workspace directory ───────────────────────────────────────────────
head "3. Workspace directory"

mkdir -p "$WORKSPACE"
mkdir -p "$WORKSPACE/skills"
mkdir -p "$WORKSPACE/reference"
mkdir -p "$WORKSPACE/memory"

if [ -d "$WORKSPACE" ]; then
    info "Workspace exists: $WORKSPACE"
else
    fail "Could not create workspace at $WORKSPACE"
fi

# ── Step 4: Core workspace files ──────────────────────────────────────────────
head "4. Core workspace files (install if missing)"

install_if_missing() {
    local src="$1"
    local dst="$2"
    local name=$(basename "$dst")
    if [ -f "$dst" ] && [ -s "$dst" ]; then
        info "$name — already exists (not overwriting)"
    elif [ -f "$src" ]; then
        cp "$src" "$dst"
        info "$name — installed from template"
    else
        warn "$name — template not found at $src"
    fi
}

install_if_missing "$TEMPLATES/core/USER.md"         "$WORKSPACE/USER.md"
install_if_missing "$TEMPLATES/core/SYSTEM_MAP.md"   "$WORKSPACE/SYSTEM_MAP.md"
install_if_missing "$TEMPLATES/core/ORGANIZATION.md" "$WORKSPACE/ORGANIZATION.md"
install_if_missing "$TEMPLATES/core/TASKS.md"        "$WORKSPACE/TASKS.md"
install_if_missing "$TEMPLATES/core/BACKLOG.md"      "$WORKSPACE/BACKLOG.md"
install_if_missing "$TEMPLATES/core/PLAN.md"         "$WORKSPACE/PLAN.md"
install_if_missing "$TEMPLATES/core/MEMORY.md"       "$WORKSPACE/MEMORY.md"

# Create HEARTBEAT.md if missing (minimal starter)
if [ ! -f "$WORKSPACE/HEARTBEAT.md" ] || [ ! -s "$WORKSPACE/HEARTBEAT.md" ]; then
    cat > "$WORKSPACE/HEARTBEAT.md" << 'EOF'
# HEARTBEAT.md — Session Continuity

_Reset each session. Used for open loops and continuity between sessions._

## Open loops
(none)

## Last session summary
(none yet)
EOF
    info "HEARTBEAT.md — created starter"
else
    info "HEARTBEAT.md — already exists"
fi

# Create SYSTEM_HEALTH.md if missing (empty by design)
if [ ! -f "$WORKSPACE/SYSTEM_HEALTH.md" ]; then
    echo "# SYSTEM_HEALTH.md" > "$WORKSPACE/SYSTEM_HEALTH.md"
    info "SYSTEM_HEALTH.md — created empty"
else
    info "SYSTEM_HEALTH.md — already exists"
fi

# SOUL_PENDING.md — create if missing
if [ ! -f "$WORKSPACE/SOUL_PENDING.md" ]; then
    cat > "$WORKSPACE/SOUL_PENDING.md" << 'EOF'
# SOUL_PENDING.md — Proposed SOUL Changes

⚠️ This is a STAGING file. NEVER auto-promote to SOUL.md.
Present proposals to Tom for review only.

## Proposed changes
(none yet)
EOF
    info "SOUL_PENDING.md — created"
else
    info "SOUL_PENDING.md — already exists"
fi

# ── Step 5: SOUL.md safety check ──────────────────────────────────────────────
head "5. SOUL.md safety (encrypted-only)"

if [ -f "$WORKSPACE/SOUL.md" ] || [ -L "$WORKSPACE/SOUL.md" ]; then
    warn "Plaintext SOUL.md found in workspace — removing (SOUL is encrypted-only)"
    rm -f "$WORKSPACE/SOUL.md"
    info "Removed plaintext SOUL.md"
else
    info "No plaintext SOUL.md in workspace (correct)"
fi

VAULT_ENC="${OPENCLAW_VAULT_DIR:-$HOME/.openclaw/vault}/SOUL.md.enc"
if [ -f "$VAULT_ENC" ]; then
    info "Encrypted SOUL vault found: $VAULT_ENC"
else
    warn "No SOUL.md.enc found at $VAULT_ENC — use /soul in Telegram to upload"
fi

# ── Step 6: Skills directory ──────────────────────────────────────────────────
head "6. Skills (install if missing)"

install_skill() {
    local name="$1"
    local src="$TEMPLATES/skills/$name/SKILL.md"
    local dst="$WORKSPACE/skills/$name/SKILL.md"
    mkdir -p "$WORKSPACE/skills/$name"
    if [ -f "$dst" ] && [ -s "$dst" ]; then
        info "skills/$name/SKILL.md — already exists"
    elif [ -f "$src" ]; then
        cp "$src" "$dst"
        info "skills/$name/SKILL.md — installed"
    else
        warn "skills/$name/SKILL.md — template not found"
    fi
}

install_skill "learning"
install_skill "daily-plan"
install_skill "briefing"
install_skill "weekly-review"
install_skill "expenses"
install_skill "coding"

SKILL_COUNT=$(find "$WORKSPACE/skills" -name "SKILL.md" 2>/dev/null | wc -l)
info "Skills present: $SKILL_COUNT"

# ── Step 7: Reference directory ───────────────────────────────────────────────
head "7. Reference files (install if missing)"

install_if_missing "$TEMPLATES/reference/CRONS.md"           "$WORKSPACE/reference/CRONS.md"
install_if_missing "$TEMPLATES/reference/POLLERS.md"         "$WORKSPACE/reference/POLLERS.md"
install_if_missing "$TEMPLATES/reference/AI-INTEL-OPTIONS.md" "$WORKSPACE/reference/AI-INTEL-OPTIONS.md"

# ── Step 8: qmd PATH fix ──────────────────────────────────────────────────────
head "8. qmd PATH (gateway service)"

NPM_BIN="$HOME/.npm-packages/bin"
if [ -f "$NPM_BIN/qmd" ]; then
    info "qmd found: $("$NPM_BIN/qmd" --version 2>/dev/null || echo 'installed')"
    if [ -f "$GATEWAY_SVC" ]; then
        if grep -q "npm-packages" "$GATEWAY_SVC"; then
            info "Gateway service PATH already includes ~/.npm-packages/bin"
        else
            sed -i "/^\[Service\]/a Environment=\"PATH=$NPM_BIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"" "$GATEWAY_SVC"
            systemctl --user daemon-reload
            info "Gateway service patched with qmd PATH"
        fi
    fi
elif command -v qmd &>/dev/null; then
    info "qmd available on PATH: $(which qmd)"
else
    warn "qmd not found — memory search unavailable (run: npm install -g @tobilu/qmd --prefix ~/.npm-packages)"
fi

# ── Step 9: TOTP check ────────────────────────────────────────────────────────
head "9. TOTP controls"

if [ -n "${TOTP_SECRET:-}" ]; then
    info "TOTP_SECRET is set — TOTP gate active"
else
    warn "TOTP_SECRET not found in .env — sensitive actions may not be gated"
fi

# ── Step 10: Cron check ───────────────────────────────────────────────────────
head "10. Cron jobs"

CRON_LIST=$(crontab -l 2>/dev/null || echo "")
check_cron() {
    local pattern="$1"
    local label="$2"
    if echo "$CRON_LIST" | grep -q "$pattern"; then
        info "Cron: $label"
    else
        warn "Cron missing: $label"
    fi
}

check_cron "poll-garmin.py"               "Garmin (09:00)"
check_cron "health_check.py"              "System health (06:55)"
check_cron "poll-crm.py"                  "CRM import (08:00)"
check_cron "enquiry_poller.py"            "Enquiry poller (every 2 min)"
check_cron "report_poller.py"             "Report poller (every 5 min)"
check_cron "sharepoint_cache_poller.py"   "SharePoint cache (every 15 min)"
check_cron "sharepoint_queue_processor.py" "SharePoint queue (every 1 min)"
check_cron "daily-reset.py"               "Provider reset (04:00)"

# ── Step 11: Python & Node ────────────────────────────────────────────────────
head "11. Runtimes"

if command -v python3 &>/dev/null; then
    info "Python3: $(python3 --version 2>&1)"
else
    fail "python3 not found"
fi

if command -v node &>/dev/null; then
    info "Node: $(node --version)"
else
    warn "node not found"
fi

if command -v npm &>/dev/null; then
    info "npm: $(npm --version)"
fi

# ── Step 12: Gateway restart (if patched) ─────────────────────────────────────
head "12. Gateway restart"

systemctl --user daemon-reload 2>/dev/null || true
if systemctl --user restart openclaw-gateway.service 2>/dev/null; then
    info "Gateway restarted with updated config"
else
    warn "Could not restart gateway — check systemctl --user status openclaw-gateway.service"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║                  Provision Summary                   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "  ${GREEN}Passed: $PASS${NC}   ${YELLOW}Warnings: $WARN${NC}   ${RED}Failed: $FAIL${NC}"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}Action required: fix the failed checks above before using the system.${NC}"
elif [ "$WARN" -gt 0 ]; then
    echo -e "${YELLOW}System provisioned with warnings. Review items above.${NC}"
else
    echo -e "${GREEN}All checks passed. System is ready.${NC}"
fi

echo ""
echo "  Next steps:"
echo "  1. Send a message in Telegram: 'Read SYSTEM_MAP.md and tell me what it contains'"
echo "  2. If that works, try: 'Plan my day'"
echo "  3. For coding work: 'Use a subagent to review BACKLOG.md'"
echo "  4. Weekly: 'Run weekly review' (or cron triggers it on Friday)"
echo ""
echo "  Useful Telegram commands:"
echo "    /status   /health   /logs   /soul   /pull   /install"
echo "    /subagents list    /subagents spawn l1 <task>"
echo ""
