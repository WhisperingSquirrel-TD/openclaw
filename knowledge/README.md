# OpenClaw Knowledge Base — Index

> This directory holds the detailed operational knowledge for the OpenClaw fork.
> The top-level map is [`../replit.md`](../replit.md) — start there. Each file below is loaded on demand so only the relevant detail costs tokens.
>
> These docs are **repo-only agent reference** — they are not deployed to the Pi (see [Pi deployment](./pi-deployment.md)).

## Core

| File | What's in it |
|------|--------------|
| [architecture.md](./architecture.md) | Overview, monorepo layout, local dev setup, Replit static-site deploy, env vars |
| [token-efficiency.md](./token-efficiency.md) | Pi config table that cuts API/token cost (heartbeat, pruning, embed windows) |
| [pi-deployment.md](./pi-deployment.md) | Pi install script, manual ops, restart notes, background services, scheduling constraint, the deploy rule |
| [pi-reference.md](./pi-reference.md) | File locations, log map, key paths, systemd services, first-check diagnostics, config editing |
| [troubleshooting.md](./troubleshooting.md) | Known failure patterns: model routing, crash-loops, the auth/Ollama debugging playbook |
| [upstream-sync.md](./upstream-sync.md) | Sync checklist, files never to overwrite, conflict-merge details, durable build warnings, sync log |

## Security & control

| File | What's in it |
|------|--------------|
| [security.md](./security.md) | denyCommands, immutable prompt, SOUL integrity/encryption, audit log, rate limiting, trust gate, exec denylist |
| [totp.md](./totp.md) | TOTP approval system + runtime behaviour |
| [whatsapp.md](./whatsapp.md) | WhatsApp watch mode + watch action scanner |

## Integrations ([`./integrations/`](./integrations/))

| File | What's in it |
|------|--------------|
| [integrations/garmin.md](./integrations/garmin.md) | garminconnect poller (login-once OAuth, 429 guard, data collected) |
| [integrations/microsoft.md](./integrations/microsoft.md) | OAuth unified scopes, token format, SharePoint housekeeping + mirror, calendar |
| [integrations/google.md](./integrations/google.md) | Gmail OAuth, Google Tasks (WhatsApp watch actions) |
| [integrations/youtube.md](./integrations/youtube.md) | Transcript extractor + two-phase channel poller |
| [integrations/ai-briefing.md](./integrations/ai-briefing.md) | Weekly RSS → rank → synthesize briefing pipeline |
| [integrations/web-search.md](./integrations/web-search.md) | Tavily native `web_search` provider |
| [integrations/skills.md](./integrations/skills.md) | Skills path configuration |
