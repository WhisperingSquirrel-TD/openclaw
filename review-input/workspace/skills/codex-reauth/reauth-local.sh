#!/bin/bash
# Local Codex Re-Authentication Script
# Usage: Run this when you have desktop/VNC access to the Pi

set -euo pipefail

echo "🔐 OpenAI Codex Re-Authentication (Local Mode)"
echo ""
echo "This will:"
echo "  1. Open a browser for OAuth"
echo "  2. Copy tokens to OpenClaw"
echo "  3. Restart the gateway (requires TOTP approval)"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Step 1: Opening browser for authentication..."
echo "----------------------------------------"
echo "(If browser doesn't open, check the URL in the terminal)"
echo ""

codex login

if [ ! -f ~/.codex/auth.json ]; then
    echo "❌ ERROR: ~/.codex/auth.json not found"
    echo "The codex login command may have failed."
    exit 1
fi

echo ""
echo "Step 2: Copying tokens to OpenClaw..."
echo "----------------------------------------"

python3 << 'EOF'
import json
from pathlib import Path

codex_auth = json.loads((Path.home() / ".codex/auth.json").read_text())
openclaw_auth_path = Path.home() / ".openclaw/agents/main/agent/auth-profiles.json"
openclaw_auth = json.loads(openclaw_auth_path.read_text())

openclaw_auth['profiles']['openai-codex:default'] = {
    "type": "oauth",
    "provider": "openai-codex",
    "access": codex_auth['tokens']['access_token'],
    "refresh": codex_auth['tokens']['refresh_token'],
    "expires": codex_auth['tokens'].get('expires_at', 0),
    "accountId": codex_auth['tokens']['account_id']
}

openclaw_auth_path.write_text(json.dumps(openclaw_auth, indent=2))
print("✅ Tokens copied successfully")
EOF

echo ""
echo "Step 3: Restarting OpenClaw gateway..."
echo "----------------------------------------"
systemctl --user restart openclaw-gateway.service

echo ""
echo "✅ Done! OpenAI Codex OAuth has been re-authenticated."
echo ""
echo "Verify with:"
echo "  openclaw config auth-status 2>&1 | grep -A 5 'openai-codex'"
