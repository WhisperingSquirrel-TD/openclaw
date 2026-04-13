#!/usr/bin/env bash
# setup-dev-workflow.sh
# One-time bootstrap for the OpenClaw Telegram dev workflow.
# Run on the Pi after pulling the latest openclaw repo:
#   git -C ~/openclaw pull && bash ~/openclaw/scripts/setup-dev-workflow.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC}  $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
info() { echo -e "      $1"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_DIR="$HOME/.openclaw"
WORKSPACE_DIR="$OPENCLAW_DIR/workspace"
SKILLS_DIR="$WORKSPACE_DIR/skills"
SPECS_DIR="$WORKSPACE_DIR/specs"
REFERENCE_DIR="$WORKSPACE_DIR/reference"
PROJECTS_DIR="$WORKSPACE_DIR/projects"
INTEGRATIONS_DIR="$OPENCLAW_DIR/integrations"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  OpenClaw Dev Workflow Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Create workspace directories ──────────────────────────────────────────

echo "Creating workspace directories..."
mkdir -p "$SKILLS_DIR" "$SPECS_DIR" "$REFERENCE_DIR" "$PROJECTS_DIR"
mkdir -p "$INTEGRATIONS_DIR/github"
ok "Workspace directories ready"
info "  $SPECS_DIR"
info "  $REFERENCE_DIR"
info "  $PROJECTS_DIR"
echo ""

# ── 2. Deploy skills ──────────────────────────────────────────────────────────

echo "Deploying skills..."
SKILLS_SOURCE="$REPO_DIR/attached_assets/skills"

for skill in app-plan app-init app-build app-test app-deploy app-patch; do
    src="$SKILLS_SOURCE/$skill/SKILL.md"
    dst_dir="$SKILLS_DIR/$skill"
    dst="$dst_dir/SKILL.md"

    if [[ ! -f "$src" ]]; then
        fail "Source skill not found: $src"
        exit 1
    fi

    mkdir -p "$dst_dir"
    ln -sf "$src" "$dst"
    ok "Linked $skill → $src"
done
echo ""

# ── 3. Deploy GitHub helper ───────────────────────────────────────────────────

echo "Deploying GitHub repo creation helper..."
GITHUB_HELPER_SRC="$REPO_DIR/attached_assets/integrations/github/create-repo.py"
GITHUB_HELPER_DST="$INTEGRATIONS_DIR/github/create-repo.py"

if [[ ! -f "$GITHUB_HELPER_SRC" ]]; then
    fail "GitHub helper not found: $GITHUB_HELPER_SRC"
    exit 1
fi

ln -sf "$GITHUB_HELPER_SRC" "$GITHUB_HELPER_DST"
ok "GitHub helper linked → $GITHUB_HELPER_SRC"

RETRO_PUSH_SRC="$REPO_DIR/attached_assets/integrations/github/retro-push.py"
RETRO_PUSH_DST="$INTEGRATIONS_DIR/github/retro-push.py"

if [[ ! -f "$RETRO_PUSH_SRC" ]]; then
    fail "retro-push helper not found: $RETRO_PUSH_SRC"
    exit 1
fi

ln -sf "$RETRO_PUSH_SRC" "$RETRO_PUSH_DST"
ok "Retro-push helper linked → $RETRO_PUSH_SRC"
echo ""

# ── 4. Install Vercel CLI ─────────────────────────────────────────────────────

echo "Checking Vercel CLI..."
if command -v vercel &>/dev/null; then
    VERCEL_VER=$(vercel --version 2>/dev/null | head -1)
    ok "Vercel CLI already installed ($VERCEL_VER)"
else
    echo "Installing Vercel CLI..."
    VERCEL_EXIT=0
    npm install -g vercel > /tmp/vercel-install.log 2>&1 || VERCEL_EXIT=$?
    if [[ $VERCEL_EXIT -eq 0 ]] && command -v vercel &>/dev/null; then
        VERCEL_VER=$(vercel --version 2>/dev/null | head -1)
        ok "Vercel CLI installed ($VERCEL_VER)"
    else
        warn "Vercel CLI installation failed (exit $VERCEL_EXIT) — install manually:"
        info "  npm install -g vercel"
        info "  Install log: /tmp/vercel-install.log"
    fi
fi
echo ""

# ── 5. Verify tokens ──────────────────────────────────────────────────────────

echo "Checking environment tokens..."
ENV_FILE="$OPENCLAW_DIR/.env"
MISSING_TOKENS=()

check_token() {
    local key="$1"
    local label="$2"
    # Strip quotes and whitespace from the value to check it is non-empty
    local val
    val=$(grep "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | sed 's/[[:space:]]//g; s/"//g')
    if [[ -n "$val" ]]; then
        ok "${label} — present"
        return 0
    else
        warn "${label} — NOT SET in $ENV_FILE"
        MISSING_TOKENS+=("$label")
        return 1
    fi
}

if [[ -f "$ENV_FILE" ]]; then
    check_token "GITHUB_TOKEN" "GITHUB_TOKEN"
    check_token "VERCEL_TOKEN" "VERCEL_TOKEN"
else
    warn ".env file not found at $ENV_FILE"
    MISSING_TOKENS+=("GITHUB_TOKEN" "VERCEL_TOKEN")
fi
echo ""

# ── 6. Patch SOUL with dev workflow principles ───────────────────────────────

echo "Patching SOUL with dev workflow principles..."
SOUL_PATCH_SCRIPT="$REPO_DIR/scripts/patch-soul-dev-workflow.mjs"

if [[ ! -f "$SOUL_PATCH_SCRIPT" ]]; then
    warn "SOUL patch script not found: $SOUL_PATCH_SCRIPT"
    info "  Re-pull the repo and retry."
else
    VAULT_FILE="$OPENCLAW_DIR/vault/SOUL.md.enc"
    PASSPHRASE_SET=false
    if grep -q "^OPENCLAW_VAULT_PASSPHRASE=" "$ENV_FILE" 2>/dev/null; then
        PP=$(grep "^OPENCLAW_VAULT_PASSPHRASE=" "$ENV_FILE" | cut -d= -f2- | sed 's/[[:space:]]//g; s/"//g')
        [[ -n "$PP" ]] && PASSPHRASE_SET=true
    fi
    [[ -n "${OPENCLAW_VAULT_PASSPHRASE:-}" ]] && PASSPHRASE_SET=true

    if [[ "$PASSPHRASE_SET" == "false" ]]; then
        warn "OPENCLAW_VAULT_PASSPHRASE not set — skipping SOUL patch"
        info "  Set it in $ENV_FILE and re-run this script to apply principles."
    elif [[ ! -f "$VAULT_FILE" ]]; then
        warn "Encrypted SOUL not found at $VAULT_FILE — skipping SOUL patch"
        info "  Ensure OpenClaw has been run at least once to create the vault."
    else
        if node "$SOUL_PATCH_SCRIPT"; then
            ok "SOUL patched with dev workflow principles"
        else
            warn "SOUL patch failed — check output above"
            info "  You can run manually: node $SOUL_PATCH_SCRIPT"
        fi
    fi
fi
echo ""

# ── 7. Reference file stubs ───────────────────────────────────────────────────

TEMPLATE_REF="$REFERENCE_DIR/template-repo.txt"
if [[ ! -f "$TEMPLATE_REF" ]]; then
    echo "# Template repo reference" > "$TEMPLATE_REF"
    echo "# Set this to your GitHub template repo in owner/name format." >> "$TEMPLATE_REF"
    echo "# Example:" >> "$TEMPLATE_REF"
    echo "# tomsmith/openclaw-app-template" >> "$TEMPLATE_REF"
    echo "" >> "$TEMPLATE_REF"
    warn "Template repo reference created (not yet configured)"
    info "  Edit: $TEMPLATE_REF"
else
    TEMPLATE_VALUE=$(grep -v "^#" "$TEMPLATE_REF" | grep -v "^$" | head -1)
    if [[ -n "$TEMPLATE_VALUE" ]]; then
        ok "Template repo reference: $TEMPLATE_VALUE"
    else
        warn "Template repo reference exists but not configured"
        info "  Edit: $TEMPLATE_REF"
    fi
fi
echo ""

# ── 7. Summary ────────────────────────────────────────────────────────────────

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Skills deployed:"
echo "  app-plan   → $SKILLS_DIR/app-plan/SKILL.md"
echo "  app-init   → $SKILLS_DIR/app-init/SKILL.md"
echo "  app-build  → $SKILLS_DIR/app-build/SKILL.md"
echo "  app-test   → $SKILLS_DIR/app-test/SKILL.md"
echo "  app-deploy → $SKILLS_DIR/app-deploy/SKILL.md"
echo "  app-patch  → $SKILLS_DIR/app-patch/SKILL.md"
echo ""

if [[ ${#MISSING_TOKENS[@]} -gt 0 ]]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "  ${YELLOW}One-time manual setup still required${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [[ " ${MISSING_TOKENS[*]} " =~ " GITHUB_TOKEN " ]]; then
        echo "1. GitHub Personal Access Token"
        echo ""
        echo "   Go to: https://github.com/settings/tokens/new"
        echo "   Token type: Classic"
        echo "   Required scopes:"
        echo "     [x] repo  (Full control of private repositories)"
        echo "         This includes: repo:status, repo_deployment, public_repo,"
        echo "         repo:invite, security_events"
        echo "         (public_repo alone is enough if all projects will be public)"
        echo ""
        echo "   No expiry recommended (or set 1 year and calendar a renewal)."
        echo ""
        echo "   Add to ~/.openclaw/.env:"
        echo "     GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx"
        echo ""
    fi

    if [[ " ${MISSING_TOKENS[*]} " =~ " VERCEL_TOKEN " ]]; then
        echo "2. Vercel Account and API Token"
        echo ""
        echo "   a) Sign up (free): https://vercel.com/signup"
        echo "      Use your GitHub account for easiest repo connection."
        echo ""
        echo "   b) Create an API token:"
        echo "      Go to: https://vercel.com/account/tokens"
        echo "      Click 'Create' — name it 'openclaw-pi'"
        echo "      Copy the token immediately (shown once only)"
        echo ""
        echo "   c) Add to ~/.openclaw/.env:"
        echo "      VERCEL_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx"
        echo ""
        echo "   Note: Free hobby tier available. For commercial projects,"
        echo "   Vercel Pro is \$20/month per member."
        echo ""
    fi

    echo "3. Create and register your template repo"
    echo ""
    echo "   a) Create a new GitHub repo (e.g. 'openclaw-app-template')"
    echo "      Set it up with: Next.js, Tailwind CSS, TypeScript"
    echo "      Recommended starter:"
    echo "        npx create-next-app@latest . --typescript --tailwind --eslint --app"
    echo "      Add a .env.example file with your typical env var keys."
    echo "      Add npm scripts: lint, typecheck, build, test"
    echo ""
    echo "   b) Register it in OpenClaw:"
    echo "      echo 'youruser/openclaw-app-template' > $TEMPLATE_REF"
    echo ""
    echo "   Then re-run this script to confirm everything is set."
    echo ""
fi

echo "Workflow:"
echo "  Plan    → Tell L1: 'Plan a new project called X'"
echo "  Init    → Tell L1: 'Initialise project X' (after approving spec)"
echo "  Build   → Tell L1: 'Build phase 1 of X'"
echo "  Test    → Tell L1: 'Run tests on X'"
echo "  Deploy  → Tell L1: 'Deploy X' (after reviewing preview)"
echo ""
