# OpenClaw

## Overview
OpenClaw is a multi-channel personal AI assistant gateway. It runs on your own devices and answers on channels you already use (WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, WebChat, etc.). The Gateway is the control plane; the product is the assistant.

## Architecture
- **Monorepo** managed with `pnpm` workspaces
- **Backend** (`src/`): Node.js/TypeScript gateway server
- **Frontend** (`ui/`): Vite + Lit web components (OpenClaw Control UI)
- **Packages** (`packages/`): `clawdbot`, `moltbot`
- **Extensions** (`extensions/`): Channel extension plugins

## Development Setup

### Running the app
The workflow runs:
```
/nix/store/61lr9izijvg30pcribjdxgjxvh3bysp4-pnpm-10.26.1/bin/pnpm install && node scripts/ui.js dev
```
This installs dependencies then launches the Vite dev server at **port 5000**.

### Key Configuration
- **`.npmrc`**: `manage-package-manager-versions=false` — disables pnpm corepack auto-switching (needed because the project pins `pnpm@10.23.0` in `packageManager` but Replit has `10.26.1`)
- **`ui/vite.config.ts`**: Configured for `host: "0.0.0.0"`, `port: 5000`, `allowedHosts: "all"` for Replit proxy compatibility
- **`pnpm-workspace.yaml`**: Workspace root + `ui/`, `packages/*`, `extensions/*`

## Deployment
- **Type**: Static site (builds the control UI)
- **Build command**: `pnpm run build` (builds to `dist/control-ui/`)
- **Public directory**: `dist/control-ui`

## WhatsApp Watch Mode
The WhatsApp channel supports a `mode` config field (`"active"` or `"watch"`):
- **`active`** (default): Normal two-way messaging
- **`watch`**: Read-only mode — all outbound is hard-blocked (messages, reactions, polls, read receipts, typing indicators, presence, pairing replies). Inbound messages from all senders (including own) are captured to a structured JSONL transcript at `<state-dir>/credentials/whatsapp/watch-transcripts/whatsapp-watch-<accountId>.jsonl`

### Config
Set at root or per-account level:
```json
{ "channels": { "whatsapp": { "mode": "watch" } } }
```
or per-account:
```json
{ "channels": { "whatsapp": { "accounts": { "personal": { "mode": "watch" } } } } }
```

### Key files
- `src/web/watch-mode.ts` — `WatchModeBlockError`, `assertNotWatchMode()` helper
- `src/web/auto-reply/watch-transcript.ts` — JSONL transcript writer
- `src/web/outbound.ts` — Send-block guards on all outbound functions
- `src/web/inbound/monitor.ts` — Presence/read-receipt/composing suppression, access control bypass in watch mode
- `src/web/auto-reply/monitor.ts` — Routes messages to transcript writer instead of agent in watch mode

## Security & Control Features

### Per-Channel denyCommands (Req #8)
Extends the global `gateway.nodes.denyCommands` to per-channel scoping. Setting `channels.whatsapp.denyCommands: ["message.send"]` blocks sends only for WhatsApp while leaving other channels unaffected.
- Config: `channels.<channel>.denyCommands: string[]` (WhatsApp, Telegram)
- Files: `src/gateway/node-command-policy.ts` (`resolveChannelDenyCommands`), channel config schemas

### Immutable System Prompt (Req #10)
Adds `agents.defaults.systemPrompt` — an immutable preamble injected before SOUL.md in every agent session. Not subject to bootstrap character limits.
- Config: `agents.defaults.systemPrompt: string`
- Files: `src/agents/system-prompt.ts`, `src/config/zod-schema.agent-defaults.ts`

### SOUL.md Integrity Verification (Req #9)
SHA-256 hash of SOUL.md computed on first load and verified before every session. Per-workspace scoped. If SOUL.md is modified at runtime, sessions are refused with an error.
- Files: `src/agents/soul-integrity.ts`, `src/agents/bootstrap-files.ts`

### Outbound Message Audit Log (Req #12)
Append-only JSONL log for all outbound messages (sent or blocked). Each entry includes timestamp, channel, recipient, content (truncated to 10K chars), blocked status, block reason, and session ID.
- Log path: `<state-dir>/audit/outbound-audit.jsonl`
- Block reasons: `watch_mode`, `deny_commands`, `rate_limit`, `trust_gate`
- Files: `src/infra/outbound/audit-log.ts`, `src/infra/outbound/deliver.ts`, `src/web/outbound.ts`

### Rate Limiting on Agent Output (Req #13)
Sliding-window rate limiter per channel+account with configurable per-minute and per-hour limits. Overflow behavior: `queue` (default, throws RateLimitError) or `drop` (silently skips).
- Config: `channels.<channel>.maxMessagesPerMinute`, `maxMessagesPerHour`, `rateLimitOverflow` (WhatsApp, Telegram, Discord)
- Files: `src/infra/outbound/rate-limiter.ts`, `src/infra/outbound/deliver.ts`

### Session Isolation Between Channels (Req #11)
Config option `session.outboundContextScope: "channel-isolated" | "shared"`. When channel-isolated, the system prompt instructs the agent to never leak content between channels. Outbound messages are tagged with `[channel:<name>]` in transcripts.
- Config: `session.outboundContextScope`
- Files: `src/config/zod-schema.session.ts`, `src/agents/system-prompt.ts`

### Trust Level Enforcement (Req #14)
At `trustLevel >= 1`, outbound messages are held and routed through the exec approval system for owner approval. Denied or timed-out messages are logged to the audit trail.
- Config: `agents.defaults.trustLevel: number`, `agents.defaults.requireApproval: string[]`
- Files: `src/infra/outbound/trust-gate.ts`, `src/infra/outbound/deliver.ts`

### Encrypted SOUL.md at Rest (Req #7)
AES-256-GCM encryption for SOUL.md using a passphrase (via `OPENCLAW_VAULT_PASSPHRASE` env var). Encrypted file stored at `<state-dir>/vault/SOUL.md.enc`. Decrypted only in RAM (via `/dev/shm` or in-memory buffer). Plaintext is wiped after initial encryption. Shutdown hooks ensure cleanup.
- Env: `OPENCLAW_VAULT_PASSPHRASE`
- Files: `src/agents/soul-vault.ts`, `src/agents/workspace.ts`

### TOTP-Based Approval System
When `approvalMode: "totp"` is set, the trust gate uses a 6-digit authenticator code (RFC 6238 TOTP) instead of macOS socket-based approval. This is the Pi-compatible alternative for gated actions.

**How it works:**
1. Agent attempts a gated action (e.g. `message.send` at `trustLevel >= 1`)
2. Trust gate checks for an active approval window — if open, action proceeds immediately
3. If no window: owner is prompted to send their 6-digit code on Telegram
4. Owner sends code → window opens for `totpWindowMinutes` (default 5) → all queued and future gated actions proceed
5. Window expires → new code required

**Setup:**
1. Set config: `agents.defaults.approvalMode: "totp"`, optionally `totpWindowMinutes: 5`
2. Send `/totp-setup` on Telegram → get `otpauth://` URI to scan in Google Authenticator/Authy
3. When prompted, send 6-digit code to approve

**Commands:**
- `/totp-setup [accountName]` — Generate new TOTP secret, returns URI for authenticator app
- `/totp-status` — Show whether TOTP is configured and window status
- `/totp-lock` — Manually close the approval window immediately
- `123456` (any 6-digit number) — Automatically checked as TOTP code when `approvalMode: "totp"`

**Config:**
- `agents.defaults.approvalMode: "socket" | "totp"` (default: `"socket"`)
- `agents.defaults.totpWindowMinutes: 1–60` (default: `5`)

**Secret storage:** `<state-dir>/totp/totp-secret.enc` (AES-256-GCM, encrypted with `OPENCLAW_VAULT_PASSPHRASE`) or `totp-secret.txt` (plaintext fallback)

**Files:**
- `src/infra/totp/totp.ts` — RFC 6238 TOTP core (generate, verify, URI)
- `src/infra/totp/totp-setup.ts` — Secret generation, encrypted storage, setup helper
- `src/infra/totp/totp-session.ts` — In-memory approval window manager
- `src/infra/outbound/trust-gate.ts` — Trust gate with TOTP mode support
- `src/auto-reply/reply/commands-totp.ts` — Telegram command handlers

## Environment Variables
See `.env.example` for all options. Key variables:
- `OPENCLAW_GATEWAY_TOKEN` — auth token for the gateway
- `OPENCLAW_VAULT_PASSPHRASE` — passphrase for SOUL.md encryption at rest
- AI provider keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.
- Channel tokens: `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, `SLACK_BOT_TOKEN`, etc.
