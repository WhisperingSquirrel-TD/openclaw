# OpenClaw

## Overview
OpenClaw is a multi-channel personal AI assistant gateway. It runs on your own devices and answers on channels you already use (WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, WebChat, etc.). The Gateway is the control plane; the product is the assistant.

## Architecture
- **Monorepo** managed with `pnpm` workspaces
- **Backend** (`src/`): Node.js/TypeScript gateway server
- **Frontend** (`ui/`): Vite + Lit web components (OpenClaw Control UI)
- **Packages** (`packages/`): `clawdbot`, `moltbot`
- **Extensions** (`extensions/`): Channel extension plugins
- **Build tool**: `tsdown` (esbuild-based bundler) — replaced `tsc` for builds. Entry points defined in `tsdown.config.ts`, output to `dist/`. Build command: `pnpm run build`.

## Development Setup

### Running the app
The workflow runs:
```
/nix/store/61lr9izijvg30pcribjdxgjxvh3bysp4-pnpm-10.26.1/bin/pnpm install && node scripts/ui.js dev
```
This installs dependencies then launches the Vite dev server at **port 5000**.

### Key Configuration
- **`.npmrc`**: `manage-package-manager-versions=false` — **never remove** — disables pnpm corepack auto-switching (needed because the project pins `pnpm@10.23.0` in `packageManager` but Replit has `10.26.1`)
- **`ui/vite.config.ts`**: Configured for `host: "0.0.0.0"`, `port: 5000`, `allowedHosts: "all"` for Replit proxy compatibility
- **`pnpm-workspace.yaml`**: Workspace root + `ui/`, `packages/*`, `extensions/*`

## Deployment (Replit)
- **Type**: Static site (builds the control UI)
- **Build command**: `pnpm run build` (builds to `dist/control-ui/`)
- **Public directory**: `dist/control-ui`

## Raspberry Pi Deployment

### Prerequisites (all handled automatically by the install script)
- **Node.js >= 22.12.0** (required by upstream since 2026.3.8 — auto-upgraded via `n`, `nvm`, or `fnm`; installs `n` if no version manager found)
- **pnpm** (installed automatically if missing)
- **Git** access to `https://github.com/WhisperingSquirrel-TD/openclaw.git`

### Install / Update
```bash
bash ~/install-forked-openclaw.sh
```
The script is self-updating — it copies the latest version from `attached_assets/install-forked-openclaw.sh` on each run.

### What the install script does (in order)
1. Stops L1 (`~/l1-stop.sh`)
2. Uninstalls old global OpenClaw (`npm uninstall -g`, `pnpm unlink --global`)
3. Installs pnpm if missing
4. Clones or pulls the fork (`~/openclaw/`)
5. `pnpm install` (resolves dependencies)
6. `rm -rf dist && pnpm run build` (clean rebuild with tsdown)
7. `pnpm link --global` (makes `openclaw` command available)
8. Updates `~/.openclaw/openclaw.json` (sets WhatsApp watch mode, TOTP approval, etc.)
9. Sets file protections (`chattr +a` audit log, `chattr +i` TOTP secrets, `chattr +i` config)
10. Starts L1 (`~/l1-start.sh`)
11. Updates integrity hashes

### Manual operations on the Pi
- **Stop**: `~/l1-stop.sh`
- **Start**: `~/l1-start.sh`
- **Direct debug**: `cd ~/openclaw && node dist/entry.js gateway run`
- **Quick update** (no config changes): `~/l1-stop.sh && cd ~/openclaw && git pull && pnpm install && pnpm run build && ~/l1-start.sh`
- **Config file**: `~/.openclaw/openclaw.json` (locked with `chattr +i`)
  - Unlock: `sudo chattr -i ~/.openclaw/openclaw.json`
  - Re-lock: `sudo chattr +i ~/.openclaw/openclaw.json`
- **Logs**: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
- **TOTP debug**: Look for "TOTP code input ignored: approvalMode is socket" or "unauthorized sender" in logs

### Pi restart notes
- Use `~/l1-stop.sh && ~/l1-start.sh`, NOT `openclaw gateway restart`
- The gateway entry point is `node dist/entry.js gateway run`

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
1. Agent attempts a gated action (`message.send` or `exec.run` at `trustLevel >= 1`)
2. Trust gate checks for an active approval window — if open, action proceeds immediately
3. If no window: owner is prompted to send their 6-digit code on Telegram
4. Owner sends code → window opens for `totpWindowMinutes` (default 5) → all queued and future gated actions proceed
5. Window expires → new code required

**Gated actions:**
- `message.send` — outbound messages to any channel (email, WhatsApp, Discord, etc.)
- `exec.run` — shell command execution on the gateway host (closes the exec bypass gap where scripts could send emails via `exec` without TOTP)

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

**Replay protection:** Each TOTP code can only be used once. A monotonic counter is persisted at `<state-dir>/totp/totp-last-counter.txt` — codes at or below the last-used counter step are rejected even within the ±1 window.

**Files:**
- `src/infra/totp/totp.ts` — RFC 6238 TOTP core (generate, verify, URI, replay protection)
- `src/infra/totp/totp-setup.ts` — Secret generation, encrypted storage, setup helper
- `src/infra/totp/totp-session.ts` — In-memory approval window manager
- `src/infra/outbound/trust-gate.ts` — Trust gate with TOTP mode support
- `src/auto-reply/reply/commands-totp.ts` — Telegram command handlers

### Exec Security Denylist
A hardcoded denylist in `src/agents/bash-tools.exec-host-gateway.ts` blocks exec commands that could tamper with system protections, regardless of TOTP approval. Blocked patterns include:
- `chattr` (any use — prevents removing immutable/append-only flags)
- References to `openclaw.json`, TOTP secret files, audit log, `SOUL.md.enc`, vault passphrase
- `systemctl stop/disable/mask openclaw`, `l1-stop.sh`
- System files (`/etc/passwd`, `/etc/shadow`, `.bashrc`)

This denylist is evaluated before TOTP approval, so even an active approval window cannot authorize these commands.

Additionally, when `approvalMode: "totp"` (hardened mode), any command flagged by the obfuscation detector (`src/infra/exec-obfuscation-detect.ts`) is hard-blocked (not just warned). This prevents bypass via base64 encoding, shell heredocs, eval/exec wrappers, curl-pipe-shell, variable expansion chains, and similar techniques.

### Audit Log Tamper Protection
The audit log (`<state-dir>/audit/outbound-audit.jsonl`) is:
- Opened with `0600` permissions
- Set to append-only (`chattr +a`) on creation (best-effort, requires root)
- Protected by the exec denylist (agent cannot reference the file in exec commands)
- The install script additionally sets `chattr +a` on the audit log and `chattr +i` on TOTP secret files

## Upstream Sync
Fork base: `d911b02` (2026-02-27). Last synced: **2026-03-08** (upstream commit `d15b6af7`, version 2026.3.8).
- 2,395 files synced from upstream (777 new, 1618 modified)
- 5 conflict files manually merged: `exec-host-gateway.ts`, `outbound.ts`, `auto-reply/monitor.ts`, `inbound/monitor.ts`, `node-command-policy.ts`
- Upstream remote: `https://github.com/openclaw/openclaw.git`
- Fork remote: `https://github.com/WhisperingSquirrel-TD/openclaw.git`
- Key upstream changes: Gemini 3.1 Flash Lite, exec approval refactoring (`exec-host-shared.ts`), `createConnectedChannelStatusPatch`, `normalizeDeviceMetadataForPolicy`, MCP bootstrap improvements, CLI restart fixes
- Build tool changed from `tsc` to `tsdown` (esbuild bundler) — `dist/` now contains bundled JS, not 1:1 transpiled files

### Merge details for conflict files
These files had both upstream refactoring and our security customizations. In each case, upstream was used as the base and our customizations were carefully re-applied:

1. **`src/agents/bash-tools.exec-host-gateway.ts`** — Upstream refactored approval context into shared helpers (`resolveExecHostApprovalContext`, `createDefaultExecApprovalRequestContext`, `resolveBaseExecApprovalDecision`, `resolveApprovalDecisionOrUndefined` from `bash-tools.exec-host-shared.js`, plus `buildExecApprovalRequesterContext`, `buildExecApprovalTurnSourceContext`, `registerExecApprovalRequestForHostOrThrow` from `bash-tools.exec-approval-request.js`). Our denylist, TOTP gate (`requestExecApproval` from `trust-gate.ts`), and obfuscation hard-block all run BEFORE the upstream approval context resolution.

2. **`src/web/outbound.ts`** — Upstream added `cfg` parameter to all outbound functions and switched to account resolution via `resolveWhatsAppAccount()`. Our `assertNotWatchMode(account)` guard and audit logging on block preserved.

3. **`src/web/auto-reply/monitor.ts`** — Upstream added `createConnectedChannelStatusPatch` and `resolveWhatsAppMediaMaxBytes`. Our watch mode routing (`isWatchMode` check), `appendWatchTranscript` for message capture, and conditional read receipt/debounce suppression preserved. The old `DEFAULT_WEB_MEDIA_BYTES` constant import was replaced with `resolveWhatsAppMediaMaxBytes(cfg)`.

4. **`src/web/inbound/monitor.ts`** — Upstream refactored into helper functions (`normalizeInboundMessage`, `enrichInboundMessage`, `enqueueInboundMessage`). Our watch mode features preserved: presence update bypass, access control bypass for all senders, read receipt suppression, composing indicator suppression, and `sendMedia`/`reply` function blocking.

5. **`src/gateway/node-command-policy.ts`** — Upstream added `PlatformId` type system and `normalizeDeviceMetadataForPolicy`. Our `resolveChannelDenyCommands` function preserved.

### `ChannelMode` type (our addition)
Upstream removed the `ChannelMode` type and `mode` field from `src/web/accounts.ts` — these are our additions for watch mode. Re-added in two places:
- **Runtime type**: `export type ChannelMode = "active" | "watch"` and `mode?: ChannelMode` on `ResolvedWhatsAppAccount` in `src/web/accounts.ts`, with safe cast from config via `resolveWhatsAppMode()` returning `"active"` as default
- **Config schema**: `mode: z.enum(["active", "watch"]).optional().default("active")` added to `WhatsAppSharedSchema` in `src/config/zod-schema.providers-whatsapp.ts` — inherited by both `WhatsAppConfigSchema` (root level) and `WhatsAppAccountSchema` (per-account). Required because both schemas use `.strict()` which rejects unknown keys.

### Pre-existing upstream TypeScript errors
These exist in upstream code (not our files) and should not be fixed by us:
- `rate-limiter.ts` — `maxMessagesPerMinute`/`maxMessagesPerHour` on Discord config
- `dm-policy-shared.js` consumers — `resolvePinnedMainDmOwnerFromAllowlist` missing export
- `vite.config.ts` — `allowedHosts` type mismatch

### Recreated upstream files
- `src/plugin-sdk/root-alias.cjs` — CJS-to-ESM proxy shim for legacy plugin `require()` support. Was missing after upstream sync (`.cjs` files not captured in tarball extraction). Recreated based on test expectations and upstream plugin-sdk loader behavior. Inlines `emptyPluginConfigSchema` for fast access; lazily loads full ESM index via `require("./index.js")` (works in Node 22.12+ which supports `require()` of ESM modules).

## Custom Files Index
All files unique to our fork (not present in upstream):
- `src/infra/totp/totp.ts` — TOTP core
- `src/infra/totp/totp-setup.ts` — TOTP secret management
- `src/infra/totp/totp-session.ts` — Approval window manager
- `src/infra/outbound/trust-gate.ts` — Trust gate (TOTP + socket modes)
- `src/infra/outbound/audit-log.ts` — Outbound audit logger
- `src/infra/exec-obfuscation-detect.ts` — Exec obfuscation detector
- `src/auto-reply/reply/commands-totp.ts` — Telegram TOTP commands
- `src/web/watch-mode.ts` — Watch mode error/helper
- `src/web/auto-reply/watch-transcript.ts` — Watch mode transcript writer
- `src/agents/soul-integrity.ts` — SOUL.md hash verification
- `src/agents/soul-vault.ts` — Encrypted SOUL.md at rest
- `attached_assets/install-forked-openclaw.sh` — Pi install/upgrade script

## Environment Variables
See `.env.example` for all options. Key variables:
- `OPENCLAW_GATEWAY_TOKEN` — auth token for the gateway
- `OPENCLAW_VAULT_PASSPHRASE` — passphrase for SOUL.md encryption at rest
- AI provider keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.
- Channel tokens: `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, `SLACK_BOT_TOKEN`, etc.
