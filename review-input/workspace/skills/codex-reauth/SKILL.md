---
name: codex-reauth
description: Re-authenticate OpenAI Codex OAuth when tokens expire or become invalid, using the approved CLI and token-copy workflow.
---

# Codex Re-Authentication Skill

**Purpose:** Re-authenticate OpenAI Codex OAuth when tokens expire or become invalid.

**Last updated:** 2026-06-01 10:14

---

## What We Learned (2026-06-01)

**The Problem:**
- OpenClaw's built-in OAuth flow for Codex doesn't work reliably
- Direct browser OAuth redirects to ChatGPT instead of returning auth codes
- Session tokens from browser cookies can't be used directly via curl/API

**The Solution:**
- Use the official `@openai/codex` CLI tool
- It handles OAuth properly and stores tokens in `~/.codex/auth.json`
- Copy those tokens into OpenClaw's `auth-profiles.json`

**Two Modes:**
1. **Local mode:** `codex login` (requires browser, use when on desktop/VNC)
2. **Remote mode:** `codex login --device-auth` (headless, use from anywhere)

---

## Quick Reference

### Check if Codex is working
```bash
openclaw config auth-status 2>&1 | grep -A 5 "openai-codex"
```

### Remote Re-Auth (Preferred)
```bash
~/.openclaw/workspace/skills/codex-reauth/reauth-remote.sh
```

### Local Re-Auth (Desktop/VNC only)
```bash
~/.openclaw/workspace/skills/codex-reauth/reauth-local.sh
```

---

## When to Use This Skill

**Symptoms of expired/invalid Codex auth:**
- `refresh_token_reused` errors in logs
- `token_expired` errors
- Codex requests falling back to Claude
- `openclaw config auth-status` shows Codex OAuth errors

**Trigger conditions:**
- Tom asks to "fix Codex auth"
- Tom asks to "re-authenticate OpenAI"
- OAuth errors appear in gateway logs
- Tom mentions Codex not working

---

## Process

### Remote Mode (from anywhere)

1. **Run the remote re-auth script:**
   ```bash
   ~/.openclaw/workspace/skills/codex-reauth/reauth-remote.sh
   ```

2. **Follow the prompts:**
   - Script will show a URL and a device code
   - Open the URL on any device (phone, laptop, etc.)
   - Enter the device code when prompted
   - Authorize the app

3. **Script automatically:**
   - Copies tokens from `~/.codex/auth.json` to OpenClaw
   - Restarts the gateway
   - Verifies the new tokens work

### Local Mode (on Pi desktop/VNC)

1. **Run the local re-auth script:**
   ```bash
   ~/.openclaw/workspace/skills/codex-reauth/reauth-local.sh
   ```

2. **Browser opens automatically:**
   - Sign in to OpenAI
   - Authorize the app
   - Browser closes

3. **Script automatically completes the rest**

---

## Implementation Notes

**Why this works:**
- The official Codex CLI uses the correct OAuth client ID and scopes
- It handles token refresh properly
- OpenClaw can reuse these tokens without modification

**Token locations:**
- Source: `~/.codex/auth.json` (Codex CLI)
- Destination: `~/.openclaw/agents/main/agent/auth-profiles.json` (OpenClaw)

**Token lifetime:**
- Access tokens: ~24 hours
- Refresh tokens: ~10 days (but can be invalidated if reused)

**Dependencies:**
- Node.js 18+ (already installed)
- `@openai/codex` npm package (installed globally)

---

## Troubleshooting

**"codex: command not found"**
First check the common local install locations on this Pi:
```bash
ls -l ~/.npm-packages/bin/codex ~/.local/share/pnpm/codex /usr/local/bin/codex 2>/dev/null
```
If none exist, install/reinstall:
```bash
npm install -g @openai/codex
```

**"Tokens copied but Codex still failing"**
```bash
# Check if access token is actually valid
curl -s https://api.openai.com/v1/models \
  -H "Authorization: Bearer $(jq -r .tokens.access_token ~/.codex/auth.json)" \
  | head -20
```

**"Browser won't open"**
- Use remote mode: `codex login --device-auth`
- Or manually visit the URL shown in the terminal

**"TOTP required for remote script"**
- This is expected - the script restarts the gateway (gated operation)
- Send the 6-digit code when prompted

---

## Future Improvements

**Nice to have:**
- Automatic re-auth when refresh fails (cron-based health check)
- Alert Tom *before* tokens expire (proactive renewal)
- Support for multiple OpenAI accounts

**Blocked by:**
- OpenAI doesn't provide long-lived API keys for Codex (only OAuth)
- No headless OAuth flow without device-auth
