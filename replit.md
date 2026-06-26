# OpenClaw — System Map

OpenClaw is a multi-channel personal AI assistant gateway. It runs on your own devices and answers on channels you already use (WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, WebChat, etc.). The Gateway is the control plane; the product is the assistant.

This file is the **map**. Detailed knowledge lives in [`knowledge/`](./knowledge/) and is loaded on demand so only the relevant detail costs tokens. Read the section below to find the right file, then open it. Each knowledge file cross-links to its related files.

---

## Critical rules — always apply (do not need to open a sub-file)

These are guardrails that apply on every session. Detail is linked, but the rule itself lives here so it is never missed.

1. **End every session that changed any repo file** with the Pi deploy instructions:
   > To deploy everything changed in this session, run on the Pi:
   > ```bash
   > cd ~/openclaw && git pull
   > bash ~/install-forked-openclaw.sh
   > ```
   Never assume the user knows this. → [pi-deployment.md](./knowledge/pi-deployment.md)
2. **The install script is the single source of truth for deployment.** Any new runtime file/skill/service/integration must be wired into `install-forked-openclaw.sh` (or `scripts/setup-dev-workflow.sh`). If install doesn't deploy it, it isn't deployed. (Docs under `knowledge/` and `replit.md` are repo-only reference, intentionally not deployed.)
3. **The workspace cannot `git push`/`pull`/`fetch` from the CLI** — push via the Replit Git pane, then run the two Pi commands above. GitHub is authoritative.
4. **Never remove `manage-package-manager-versions=false`** from `.npmrc`. → [architecture.md](./knowledge/architecture.md)
5. **Never schedule cron/background jobs in the 06:xx or 07:xx windows** (CRM 06:00, another job 07:00). Use 08:00+. → [pi-deployment.md](./knowledge/pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx)
6. **On upstream sync, never overwrite the 5 fork-specific files** and preserve our security customizations — the permanently-blocked `denyCommands`, watch-mode guards, trust gate, and exec denylist must survive every merge. → [upstream-sync.md](./knowledge/upstream-sync.md), [security.md](./knowledge/security.md)
7. **Config edits use the `agents.defaults.*` schema, never legacy `agent.*`**, and never write a raw `.env` value (`export VAR=…`) into `openclaw.json`. → [troubleshooting.md](./knowledge/troubleshooting.md)

---

## Where to find things

Start at the knowledge index: [`knowledge/README.md`](./knowledge/README.md).

**Build & run**
- Monorepo layout, local dev, Replit deploy, env vars → [knowledge/architecture.md](./knowledge/architecture.md)
- Pi install / update / manual ops / services / scheduling → [knowledge/pi-deployment.md](./knowledge/pi-deployment.md)
- API/token cost-cutting config → [knowledge/token-efficiency.md](./knowledge/token-efficiency.md)

**Operate & debug the Pi**
- File locations, log map, key paths, systemd services, first-check diagnostics → [knowledge/pi-reference.md](./knowledge/pi-reference.md)
- Known failure patterns, model routing, auth/Ollama playbook → [knowledge/troubleshooting.md](./knowledge/troubleshooting.md)

**Security & control**
- denyCommands, prompts, SOUL integrity/encryption, audit log, rate limiting, trust gate, exec denylist → [knowledge/security.md](./knowledge/security.md)
- TOTP approval system → [knowledge/totp.md](./knowledge/totp.md)
- WhatsApp watch mode + action scanner → [knowledge/whatsapp.md](./knowledge/whatsapp.md)

**Integrations** ([knowledge/integrations/](./knowledge/integrations/))
- Garmin → [garmin.md](./knowledge/integrations/garmin.md) · Microsoft (email/calendar/SharePoint) → [microsoft.md](./knowledge/integrations/microsoft.md) · Google (Gmail/Tasks) → [google.md](./knowledge/integrations/google.md)
- YouTube → [youtube.md](./knowledge/integrations/youtube.md) · AI briefing → [ai-briefing.md](./knowledge/integrations/ai-briefing.md) · Web search (Tavily) → [web-search.md](./knowledge/integrations/web-search.md) · Skills paths → [skills.md](./knowledge/integrations/skills.md)

**Upstream sync**
- Sync checklist, files never to overwrite, conflict-merge details, durable build warnings, sync log → [knowledge/upstream-sync.md](./knowledge/upstream-sync.md)

---

## User Preferences

- **Documentation structure:** keep `replit.md` as a thin system map; put detailed knowledge in topic files under `knowledge/` with cross-references between related files. When adding new knowledge, create/extend the right topic file and add a one-line pointer here — don't grow this map back into a monolith.
- **Deployment:** always finish with the Pi deploy instructions (rule #1 above).
