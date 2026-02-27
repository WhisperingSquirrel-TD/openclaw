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

## Environment Variables
See `.env.example` for all options. Key variables:
- `OPENCLAW_GATEWAY_TOKEN` — auth token for the gateway
- AI provider keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.
- Channel tokens: `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, `SLACK_BOT_TOKEN`, etc.
