# Architecture & Local Development

> Part of the OpenClaw knowledge base. Map: [`../replit.md`](../replit.md).
> Related: [Pi deployment](./pi-deployment.md) · [Token efficiency](./token-efficiency.md) · [Pi reference](./pi-reference.md)

## Overview

OpenClaw is a multi-channel personal AI assistant gateway. It runs on your own devices and answers on channels you already use (WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, WebChat, etc.). The Gateway is the control plane; the product is the assistant.

## Architecture

- **Monorepo** managed with `pnpm` workspaces
- **Backend** (`src/`): Node.js/TypeScript gateway server
- **Frontend** (`ui/`): Vite + Lit web components (OpenClaw Control UI)
- **Packages** (`packages/`): `clawdbot`, `moltbot`
- **Extensions** (`extensions/`): Channel extension plugins
- **Build tool**: `tsdown` (esbuild-based bundler) — replaced `tsc` for builds. Entry points defined in `tsdown.config.ts`, output to `dist/`. Build command: `pnpm run build`.

## Development Setup (Replit workspace)

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

## Deployment (Replit static site)

- **Type**: Static site (builds the control UI)
- **Build command**: `pnpm run build` (builds to `dist/control-ui/`)
- **Public directory**: `dist/control-ui`

> The Raspberry Pi runtime (the actual assistant) is deployed separately — see [Pi deployment](./pi-deployment.md).

## Environment Variables

See `.env.example` for all options. Key variables:

- `OPENCLAW_GATEWAY_TOKEN` — auth token for the gateway
- `OPENCLAW_VAULT_PASSPHRASE` — passphrase for SOUL.md encryption at rest (see [Security](./security.md))
- AI provider keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.
- Channel tokens: `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, `SLACK_BOT_TOKEN`, etc.

On the Pi, these live in `~/.openclaw/.env` — see [Pi reference](./pi-reference.md).
