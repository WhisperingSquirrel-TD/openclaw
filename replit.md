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

## Token Efficiency (Pi Config)

The install script applies these automatically via `setdefault` (all preserving any manual overrides):

| Setting                  | Value         | Effect                                                                                  |
| ------------------------ | ------------- | --------------------------------------------------------------------------------------- |
| `heartbeat.lightContext` | `true`        | Heartbeat only sends `HEARTBEAT.md`, **not** SOUL.md/memory. ~70% cut in heartbeat cost |
| `heartbeat.every`        | `60m`         | Once per hour (default 30m) — halves background API calls                               |
| `heartbeat.activeHours`  | `07:00–23:00` | Zero calls midnight–7am                                                                 |
| `heartbeat.ackMaxChars`  | `150`         | Heartbeat replies capped at 150 chars                                                   |
| `bootstrapMaxChars`      | `10000`       | Each workspace file (SOUL.md etc.) capped at 10KB                                       |
| `contextPruning.mode`    | `cache-ttl`   | Prunes conversation history >2h old (Claude only)                                       |

**What still gets sent on every interactive message:** SOUL.md + memory files (up to 10KB each). Keep these files focused — every line costs tokens on every exchange.

**Skills vs inline context:** OpenClaw's skill system means tool descriptions are injected on-demand, not in the system prompt. No changes needed there.

## Raspberry Pi Deployment

### Prerequisites (all handled automatically by the install script)

- **Node.js >= 22.12.0** (required by upstream since 2026.3.8 — auto-upgraded via `n`, `nvm`, or `fnm`; installs `n` if no version manager found)
- **pnpm** (installed automatically if missing)
- **Git** access to `https://github.com/WhisperingSquirrel-TD/openclaw.git`

### Install / Update

```bash
bash ~/install-forked-openclaw.sh
```

**Single command — no manual steps needed.** The script handles everything:

- Pulls the latest code from GitHub first (Step 0), before doing anything else
- Copies the freshly-pulled version of itself over `~/install-forked-openclaw.sh` and re-execs it
- This guarantees the newest script logic always runs, even if `~/install-forked-openclaw.sh` is months old
- `OPENCLAW_REEXEC=1` env var is passed through `exec` to prevent infinite re-exec loops

### What the install script does (in order)

1. Stops L1 (`~/l1-stop.sh`)
2. Uninstalls old global OpenClaw (`npm uninstall -g`, `pnpm unlink --global`)
3. Installs pnpm if missing
4. Clones or pulls the fork (`~/openclaw/`)
5. `pnpm install` (resolves dependencies)
6. `rm -rf dist && pnpm run build` (clean rebuild with tsdown)
7. `pnpm link --global` (makes `openclaw` command available)
8. Updates `~/.openclaw/openclaw.json` using `setdefault` for all fields (safe to re-run — never overwrites existing user customizations). Sets: WhatsApp watch mode, TOTP approval, exec host=gateway, watch action scanner. Type guards ensure malformed values (e.g. `null` where a dict is expected) are repaired rather than crashing.
9. Sets file protections (`chattr +a` audit log, `chattr +i` TOTP secrets, `chattr +i` config)
10. Starts L1 (`~/l1-start.sh`)
11. Updates integrity hashes

### Manual operations on the Pi

- **Stop**: `systemctl --user stop openclaw-gateway.service`
- **Start**: `systemctl --user start openclaw-gateway.service`
- **Restart**: `systemctl --user restart openclaw-gateway.service`
- **Status**: `systemctl --user status openclaw-gateway.service`
- **Quick update**: `bash ~/install-forked-openclaw.sh` — handles pull + build + config + restart automatically. If it hangs, it's waiting on `git pull` credentials.
- **Direct debug** (shows startup errors in terminal): `cd ~/openclaw && node dist/index.js gateway`
- **Config file**: `~/.openclaw/openclaw.json` (locked with `chattr +i`)
  - Unlock: `sudo chattr -i ~/.openclaw/openclaw.json`
  - Re-lock: `sudo chattr +i ~/.openclaw/openclaw.json`
- **Logs**: `~/.openclaw/gateway.log` (journald does NOT collect user logs on this Pi — always use the file)
- **TOTP debug**: Look for "TOTP" in logs. Common issues: "unauthorized sender" (message from non-owner), "TOTP code rejected" (wrong code or replay), "approval window expired"

### Pi restart notes

- Systemd service name is `openclaw-gateway.service` (not `openclaw`)
- journald returns "No journal files were found" for user services on this Pi — use `tail ~/.openclaw/gateway.log` instead
- The CLI entry point is `node dist/index.js` with subcommand `gateway` to run the gateway directly
- If `install-forked-openclaw.sh` hangs, it's waiting on `git pull` credentials — Ctrl+C and run steps manually
- **Config migration**: if openclaw reports `agent.*` is deprecated, run `cd ~/openclaw && node dist/index.js doctor --fix` to auto-migrate
- **Pi performance** (from doctor): add to `~/.openclaw/.env` for faster CLI starts:
  ```
  NODE_COMPILE_CACHE=/var/tmp/openclaw-compile-cache
  OPENCLAW_NO_RESPAWN=1
  ```
  And: `mkdir -p /var/tmp/openclaw-compile-cache`

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

**Permanently blocked commands** (must always remain in `denyCommands`, verified by config-check/check.py):

- `calendar.add` / `calendar.update` — calendar writes must go through the Outlook/Microsoft integration only (`poll.py`), not any generic calendar provider (e.g. Google Calendar). Unblocking these globally would allow L1 to write to the wrong calendar.
- `calendar.delete` — destructive, never permitted
- `message.react`, `camera.snap`, `camera.clip`, `screen.record`, `contacts.add`, `reminders.add`

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
- `agents.defaults.totpWindowMinutes: 1–60` (always `2` on Pi — enforced by install script)

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
- Watch mode data: `watch-transcripts`, `watch-actions`, `pending-actions.json` (prevents L1 from reading or tampering with WhatsApp surveillance data)

This denylist is evaluated before TOTP approval, so even an active approval window cannot authorize these commands.

Additionally, when `approvalMode: "totp"` (hardened mode), any command flagged by the obfuscation detector (`src/infra/exec-obfuscation-detect.ts`) is hard-blocked (not just warned). This prevents bypass via base64 encoding, shell heredocs, eval/exec wrappers, curl-pipe-shell, variable expansion chains, and similar techniques.

### Audit Log Tamper Protection

The audit log (`<state-dir>/audit/outbound-audit.jsonl`) is:

- Opened with `0600` permissions
- Set to append-only (`chattr +a`) on creation (best-effort, requires root)
- Protected by the exec denylist (agent cannot reference the file in exec commands)
- The install script additionally sets `chattr +a` on the audit log and `chattr +i` on TOTP secret files

## Agent Rule — Always End With Deployment Instructions

**After every session where any file in this repo is changed**, always close with:

> To deploy everything changed in this session, run on the Pi:
>
> ```bash
> cd ~/openclaw && git pull
> bash ~/install-forked-openclaw.sh
> ```

This applies regardless of how the change is deployed to the Pi. The rule is:

- `git pull` → pulls the latest commit from GitHub
- `bash ~/install-forked-openclaw.sh` → redeploys all code, services, and skills in one command

Never assume the user knows to run this. Always say it explicitly.

The install script is the single source of truth for deployment. Any new file, skill, service, or integration added to the repo **must** be wired into `install-forked-openclaw.sh` or `scripts/setup-dev-workflow.sh` (which install calls) — never as a separate manual step. If a file isn't deployed by install, it doesn't count as deployed.

---

## Upstream Sync Playbook

Lessons from applying upstream changes — follow this checklist every sync.

### Before merging

- **Never overwrite these 5 files from upstream** — they contain our fork-specific logic and upstream versions are incompatible:
  - `src/channels/plugins/actions/discord.ts`
  - `src/channels/plugins/actions/signal.ts`
  - `src/channels/plugins/actions/telegram.ts`
  - `src/channels/plugins/agent-tools/whatsapp-login.ts`
  - `src/line/accounts.ts`
- Check if upstream has added new build scripts. Any new `scripts/*.mjs` step that upstream wires into `package.json build` must be reviewed — it may reference upstream-only modules that don't exist in our fork. Trim `scripts/lib/plugin-sdk-entrypoints.json` accordingly.

### After merging — build checks

- **Plugin manifests**: `tsdown` does NOT copy `openclaw.plugin.json` files. The `scripts/copy-plugin-manifests.mjs` step must remain in the `build` and `build:strict-smoke` scripts in `package.json`. If plugin loader says "plugin not found" at startup, this step was dropped.
- **`root-alias.cjs`**: Must not be deleted. It is a CJS-to-ESM shim for legacy plugin `require()` support and is not captured by upstream tarballs.
- **`manage-package-manager-versions=false`** in `.npmrc`: Must never be removed.
- Run `pnpm run build` and verify the dist file count is comparable to last sync (~600 files). A large drop means entry points were lost.

### Scheduling constraint — avoid 06:xx

The CRM runs at 06:00 every morning and another job runs at 07:00. No background jobs should be scheduled in the 06:xx or 07:xx windows. All timed tasks should be scheduled at 08:00 or later. The Garmin poller is set to 09:00 for this reason. Enforce this for any new pollers or cron jobs added in future.

### Garmin poller — self-healing auth via credentials

`poll-garmin-cookie.py` now supports two auth modes, tried in this order:

1. **Garth/credential mode (preferred)** — reads `GARMIN_EMAIL` + `GARMIN_PASSWORD` from `~/.openclaw/.env`, authenticates via the `garminconnect` library (garth OAuth2). Tokens cached in `~/.garth/` and auto-refreshed every few weeks. **No manual cookie setup needed, never expires like cookies do.**
2. **Cookie fallback** — reads browser session cookies from `garmin-cookies.json`. Used only if credentials are not in `.env` or garth auth fails. Cookies expire every 7–14 days requiring manual `--setup`.

- **Primary script**: `~/.openclaw/integrations/garmin/poll-garmin-cookie.py`
- **Credential setup** (one-time): add `GARMIN_EMAIL=your@email.com` and `GARMIN_PASSWORD=yourpassword` to `~/.openclaw/.env`. The install script checks for these and skips the cookie warning when found.
- **Manual cookie setup** (fallback only): log into connect.garmin.com, run `python3 ~/.openclaw/integrations/garmin/poll-garmin-cookie.py --setup`, paste SESSIONID from devtools
- **Cookie file** (cookie mode): `~/.openclaw/integrations/garmin/garmin-cookies.json`
- **Garth token cache**: `~/.garth/` (auto-managed by the garth library)
- **Legacy fallback**: `poll-garmin.py` (old garth-based poller) kept on disk but not in cron
- The mgmt-bot `/garmin` command uses the cookie poller if present, legacy if not
- If garth login fails with MFA, run the poller manually once from a terminal to complete MFA interactively — tokens are then cached and subsequent runs are non-interactive

### Background services (Pi)

- Python pollers must run as **systemd user services**, not bare background processes. They will not survive a Pi reboot or openclaw restart otherwise. The install script creates `openclaw-email-microsoft` and `openclaw-email-gmail` services automatically.
- `loginctl enable-linger $USER` is required so user services start at boot without a login session. The install script applies this.
- If a service shows `inactive (dead)` after install, check whether credentials/token files exist — the services are intentionally not started until auth is complete.

### Microsoft OAuth — unified scope strategy (IMPORTANT)

**Why reauth keeps happening and how to stop it:**  Microsoft's device-code consent is scope-bound at the time of first sign-in. If a token was originally created with `Mail.Send offline_access`, subsequent refresh requests for `Files.ReadWrite` are silently ignored — the token looks valid but 403s on SharePoint. Every new capability added to the system would historically trigger a new reauth.

**The fix — one reauth per account, all scopes at once:**

- `sharepoint.py`'s `cmd_reauth` now requests `FULL_CONSENT_SCOPES` (not just `REQUIRED_SCOPES`):
  ```
  Mail.Send  Mail.Read  Files.ReadWrite  Sites.ReadWrite.All
  Calendars.ReadWrite  Tasks.ReadWrite  User.Read  offline_access
  ```
- This superset covers email, SharePoint, calendar and tasks permanently for that account.
- Once consented, any future token refresh requesting a *subset* of these scopes will succeed — no new consent needed.
- **No further reauth is required** unless the token file is deleted or the user revokes API access in Entra/Azure.

**How to trigger reauth from Telegram (no SSH needed):**

- `/ms-reauth` — re-auth `assistant@stackstoneconsulting.co.uk` (email + SharePoint + calendar + tasks)
- `/ms-reauth-personal` — re-auth `tom@` personal account (email + calendar)

The bot displays the Microsoft device-code URL and code in Telegram. Sign in on any device. The bot sends a "complete" message when the token is updated. The whole thing runs in the background — the bot stays responsive throughout.

**Token file locations — canonical paths:**

| Account | Canonical token file | Used by |
|---|---|---|
| `assistant@stackstoneconsulting.co.uk` | `~/.openclaw/integrations/microsoft/token-assistant.json` | SharePoint (all), send.py, poll.py `--account assistant`, **poll-calendar.py (default)** |
| `tom@ personal` | `~/.openclaw/integrations/microsoft/token-microsoft.json` | poll.py `--account microsoft`, poll-calendar.py `--account microsoft` |

One `/ms-reauth` in Telegram updates `token-assistant.json` and all three services (email, calendar, SharePoint) benefit immediately — no service restarts needed.

**`REQUIRED_SCOPES` vs `FULL_CONSENT_SCOPES` in sharepoint.py:**

- `REQUIRED_SCOPES` = what the script requests on token refresh (minimal set, avoids surprising scope grants)
- `FULL_CONSENT_SCOPES` = what `cmd_reauth` requests at initial consent time (complete superset)
- Microsoft grants from the consented superset — so refresh with `REQUIRED_SCOPES` works fine as long as `FULL_CONSENT_SCOPES` was used at reauth time.

### Microsoft OAuth token format

- The Microsoft auth library (MSAL) stores tokens in PascalCase format: `AccessToken`, `RefreshToken`, `AppMetadata`. Our poller expects a flat format: `access_token`, `refresh_token`, `tenant_id`, `client_id`.
- `poll.py` auto-detects and converts the MSAL cache format on first load, writing back a simple flat file. No manual conversion needed on new installs.
- If `tenant_id` is missing, default to `"common"` — works for personal Microsoft accounts.
- Microsoft Graph API returns `429 Too Many Requests` when polled too rapidly after a restart (multiple restart cycles cause burst). The poller handles this by reading the `Retry-After` header and waiting before retrying.

### Google OAuth tokens

- Gmail tokens expire and can be revoked. If the poller logs `invalid_grant`, delete `gmail-token.json` and re-run the poller manually to trigger a fresh OAuth flow.
- Credential file naming: the install script expects `gmail-credentials.json` and `gmail-token.json`. Older setups may have `credentials.json` / `token.json` — copy and rename if needed.
- The Google Tasks integration (for WhatsApp watch actions) uses a separate token at `~/.openclaw/oauth/google/tasks-token.json` — different from Gmail.

### SharePoint CRM housekeeping

**Script**: `attached_assets/integrations/microsoft/sharepoint_housekeeping.py`
**Deployed to**: `~/.openclaw/integrations/microsoft/sharepoint_housekeeping.py` (symlink via install script)

Entity-by-entity CRM normalisation using the Anthropic batch API (50% cost saving). Follows the same two-phase cron model as the YouTube channel poller.

**Two-phase cron model:**
- First nightly run: discovers entities, builds one Anthropic batch request per entity, submits batch, saves state
- Second nightly run: collects batch results, executes safe writes via `sharepoint-queue.json`, writes report to Telegram

**Decision classes (mirrors the crm-sharepoint skill):**
- `safe` — auto-executed in execute mode (renaming to canonical date format, creating missing Current.md, updating stale Current.md)
- `ambiguous` — never auto-written; surfaced in report for Tom/L1 judgement
- `blocked` — reported only; no write attempted

**Arguments:**
- `--mode execute|dry-run` (default: execute)
- `--scope all|accounts|opportunities|entity:<name>` (default: all; accounts processed before opportunities)
- `--sync` — skip batch API, process entities immediately (used by `/sp-housekeep` Telegram command)

**Output files:**
- Execute mode → `~/.openclaw/workspace/HOUSEKEEPING_REPORT.md`
- Dry-run mode → `~/.openclaw/workspace/HOUSEKEEPING_PROPOSAL.md`
- Both modes → Telegram notification with summary on completion

**Cron schedule**: nightly at 02:00 (`0 2 * * *`) — execute mode, all scope
**Telegram command**: `/sp-housekeep [dry-run] [accounts|opportunities|entity:<name>]`
  - `/sp-housekeep` — full sweep, execute, sync
  - `/sp-housekeep dry-run` — propose only, no writes
  - `/sp-housekeep accounts` — execute, accounts only
  - `/sp-housekeep entity:Harken Health` — execute, one entity

**State file**: `~/.openclaw/integrations/microsoft/sp-housekeeping-state.json` (tracks pending batch IDs)

**Important constraints:**
- Never processes file-by-file; the unit of work is one entity (one Account or Opportunity folder)
- Writes are grouped per entity and verified before moving on
- Ambiguous items (unclear dates, possible duplicates, cross-entity files) are always surfaced, never force-organised
- If system state is degraded (stale manifest, blocked writes), prefers reporting blocked over partial noisy attempts
- Requires `ANTHROPIC_API_KEY` in `.env`

### TOTP behaviour

- The TOTP wait window is **2 minutes** from when the code is requested. Once a valid code is accepted, the approval window is **5 minutes** by default. L1's SOUL.md should reflect this so it doesn't misinform the user about timing.
- Invalid codes now immediately cancel any pending approval request (`rejectPendingApprovals`) — but only if there is an active pending request. If there is none (e.g., a replayed old Telegram message at startup), the rejection is a no-op so L1 is not affected.
- Email polling is **never** a TOTP-gated action. If L1 tries to use `exec.run` to refresh email feeds, that is wrong — the pollers run as systemd services and self-recover. SOUL.md should make this explicit.

### After every install on the Pi

- Check `systemctl --user status openclaw-email-microsoft` and `openclaw-email-gmail` — both should show `active (running)`.
- Check `tail ~/.openclaw/workspace/memory/poll-microsoft-log.txt` and `poll-gmail-log.txt` — should show `Poll complete` lines.
- If feeds are stale: check logs for auth errors first (expired token), then check service status.

---

## Key File Locations on the Pi

### Email integration

| File                                                      | Purpose                                                                                   |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `~/.openclaw/integrations/known-contacts.txt`             | Shared trusted contacts list — read by all pollers. One email per line.                   |
| `~/.openclaw/integrations/microsoft/poll.py`              | Microsoft Graph email poller — parameterised, serves both personal and assistant accounts |
| `~/.openclaw/integrations/microsoft/token-microsoft.json` | Personal Microsoft OAuth token (tom@stackstoneconsulting.co.uk)                           |
| `~/.openclaw/integrations/microsoft-l1/token.json`        | Assistant account OAuth token (assistant@stackstoneconsulting.co.uk)                      |
| `~/.openclaw/integrations/google/gmail_poll.py`           | Gmail email poller script                                                                 |
| `~/.openclaw/integrations/google/gmail-credentials.json`  | Gmail OAuth app credentials (from Google Cloud Console)                                   |
| `~/.openclaw/integrations/google/gmail-token.json`        | Gmail OAuth token (delete and re-run poller to re-auth)                                   |

### Feed files (read by L1 directly via `cat` — no TOTP needed)

| File                                          | Purpose                                                |
| --------------------------------------------- | ------------------------------------------------------ |
| `~/.openclaw/workspace/MICROSOFT_INBOX.md`    | Personal Microsoft trusted inbox (tom@)                |
| `~/.openclaw/workspace/MICROSOFT_EXTERNAL.md` | Personal Microsoft external/unknown senders            |
| `~/.openclaw/workspace/ASSISTANT_INBOX.md`    | Assistant inbox (assistant@stackstoneconsulting.co.uk) |
| `~/.openclaw/workspace/ASSISTANT_EXTERNAL.md` | Assistant external/unknown senders                     |
| `~/.openclaw/workspace/GMAIL_INBOX.md`        | Trusted Gmail inbox summary                            |
| `~/.openclaw/workspace/GMAIL_EXTERNAL.md`     | External/unknown Gmail inbox                           |

### Poll logs (debug here first when feeds go stale)

| File                                                  | Purpose                                           |
| ----------------------------------------------------- | ------------------------------------------------- |
| `~/.openclaw/workspace/memory/poll-microsoft-log.txt` | Personal Microsoft poller — check for auth errors |
| `~/.openclaw/workspace/memory/poll-assistant-log.txt` | Assistant poller — check for auth errors          |
| `~/.openclaw/workspace/memory/poll-gmail-log.txt`     | Gmail poller — check for `invalid_grant`          |

### Systemd services

| Service                            | Command                                                                    |
| ---------------------------------- | -------------------------------------------------------------------------- |
| `openclaw-email-microsoft.service` | `systemctl --user restart openclaw-email-microsoft.service`                |
| `openclaw-email-assistant.service` | `systemctl --user restart openclaw-email-assistant.service`                |
| `openclaw-email-gmail.service`     | `systemctl --user restart openclaw-email-gmail.service`                    |
| `openclaw-gateway.service`         | `systemctl --user restart openclaw-gateway.service` — restarts main L1 app |

### Security & config

| File                                     | Purpose                                                                   |
| ---------------------------------------- | ------------------------------------------------------------------------- |
| `~/.openclaw/openclaw.json`              | Main gateway config (locked with `chattr +i`)                             |
| `~/.openclaw/audit/outbound-audit.jsonl` | Append-only outbound message audit log                                    |
| `~/.openclaw/totp/totp-secret.enc`       | Encrypted TOTP secret (locked with `chattr +i`)                           |
| `/mnt/l1-secure/SOUL.md`                 | L1 personality and context file — edit with `nano /mnt/l1-secure/SOUL.md` |
| `~/l1-hashes.txt`                        | SHA-256 integrity hashes of secure files — regenerated on every install   |

### SharePoint mirror (read-only local cache + write queue)

| File / Path                                                 | Purpose                                                                                                                       |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `~/.openclaw/workspace/SHAREPOINT_INDEX.md`                 | Full document tree: all paths, sizes, cached vs. skipped status                                                               |
| `~/.openclaw/workspace/sharepoint-cache/<SP-path>`          | Local mirror of `.md`/`.txt` files (≤500 KB). Read directly — no queue needed. Each file starts with a sync-timestamp header. |
| `~/.openclaw/workspace/sharepoint-cache/.manifest.json`     | Per-file cache status (path, cached, reason_skipped, last_synced)                                                             |
| `~/.openclaw/sharepoint-queue.json`                         | Write queue — L1 writes JSON entries directly (no exec/TOTP). Processor runs every 1 min.                                     |
| `~/.openclaw/workspace/SHAREPOINT_RESULT.md`                | Write results — check ~1 min after queuing to confirm success/failure                                                         |
| `~/.openclaw/integrations/microsoft/sp-cache-poller.log`    | Cache poller log — check if index or cache is not updating                                                                    |
| `~/.openclaw/integrations/microsoft/sp-queue-processor.log` | Queue processor log — check if writes are failing                                                                             |
| `~/.openclaw/skills/sharepoint/SKILL.md`                    | L1 skill — read/write patterns, queue format, error states                                                                    |

Cache refreshes every **15 minutes** via cron. Non-`.md`/`.txt` files (docx, pdf, xlsx) are indexed but not cached; use the queue to request content.

### YouTube transcripts

| File                                                         | Purpose                                                                           |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| `~/.openclaw/integrations/youtube/transcript.py`             | YouTube transcript extractor — no API key needed                                  |
| `~/.openclaw/integrations/youtube/channel_poller.py`         | Channel monitor — RSS polling, transcript fetch, AI summary, Markdown file writer |
| `~/.openclaw/integrations/youtube/channels.json`             | Channel list — edit directly or use `/yt-add` from mgmt-bot                       |
| `~/.openclaw/integrations/youtube/channel-poller-state.json` | Seen-video state (auto-managed, do not edit)                                      |
| `~/.openclaw/integrations/youtube/channel-poller.log`        | Poller log                                                                        |
| `~/.openclaw/workspace/reference/transcripts/`               | Output directory — YYYY-MM-DD - slug.md per video                                 |
| `~/.openclaw/skills/youtube-transcript/SKILL.md`             | L1 skill — usage patterns, URL formats, exit codes                                |

**transcript.py:** Accepts YouTube URLs or bare video IDs. Returns plain text transcript (manual or auto-generated captions). Use `--timestamps` for timestamped output, `--lang XX` for specific language, `--list-langs` to see available languages. Exit code 1 means no captions available.

**channel_poller.py:** Two-phase, two-mode design.

_Cron mode (default — every 30 min, skips 06:xx–07:xx):_

1. Phase 1 — checks `pending_batches` in state; for each completed Anthropic batch, retrieves results, writes Markdown files, sends Telegram notifications.
2. Phase 2 — polls RSS for new videos, fetches transcripts, submits all new videos as a **single Anthropic Message Batch** (50% cost saving). Videos are added to `pending_video_ids` immediately so they won't be re-fetched; files appear on the next run (~30 min). If batch submission fails, falls back to synchronous processing automatically. If only OpenAI is configured (no Anthropic key), also falls back to sync.

_Sync mode (`--sync` flag — used by `/yt-run` in mgmt-bot):_

- Each video is processed immediately: transcript → summary → file write → Telegram notification in one run. More expensive but gives instant feedback. The mgmt-bot passes `--sync` automatically.

_Single-video mode (`--video <url>` — always synchronous):_

- For interactive testing. Does not use batch API.

**State file fields:** `processed_ids` (fully done), `pending_video_ids` (claimed for a batch, not yet written), `pending_batches` (list of `{batch_id, submitted_at, videos[]}`). Batches older than 23h are dropped before Anthropic expires them at 24h.

**Adding channels:**

- From Telegram: `/yt-add https://www.youtube.com/@channelname Label` (mgmt-bot)
- Direct edit: `nano ~/.openclaw/integrations/youtube/channels.json`
- Accepted formats: channel URL (`@handle`, `/c/name`, `/user/name`), or bare channel ID (`UC...`)
- Trigger manually: `/yt-run` in mgmt-bot (sync mode, immediate result)
- Manual test run: `python3 ~/.openclaw/integrations/youtube/channel_poller.py --sync`
- Single-video test: `python3 ~/.openclaw/integrations/youtube/channel_poller.py --video <url>`

**AI summary:** Uses `ANTHROPIC_API_KEY` from `.env` (batch API in cron, sync in `/yt-run`), falls back to `OPENAI_API_KEY` (always sync — OpenAI has no batch API). If neither is present, raw transcript is saved without a summary. Model override: `OPENCLAW_AI_MODEL` env var. Transcript is truncated to 6000 chars for the prompt (cost control). Full raw transcript always saved.

### Skills path configuration

- Workspace skills live at `~/.openclaw/workspace/skills/` (32 skills as of Apr 2026)
- Must be declared in `openclaw.json` under `skills.paths` or openclaw skips them with "resolves outside configured root" warnings
- Correct config: `"skills": {"paths": ["/home/tomdean88/.openclaw/workspace/skills"]}`
- System skills (10 core ones) live at `~/.openclaw/skills/` — auto-loaded, no config needed

### Web search (Tavily — native provider)

Tavily is integrated as a **native `web_search` provider** in OpenClaw's built-in tool system. No exec or Python script needed — L1 calls `web_search` directly.

- Auto-detected from `TAVILY_API_KEY` in `~/.openclaw/.env`
- **Cannot** be forced via `tools.web.search.provider` — "tavily" is not a valid value (allowed: brave, perplexity, grok, gemini, kimi). Setting it crashes the gateway. Tavily only works via auto-detection.
- Auto-detection priority: Perplexity → Tavily → Brave → Gemini → Grok → Kimi
- `web_search` must be in `tools.alsoAllow` array in `openclaw.json` when using the `coding` profile, otherwise it is blocked regardless of key presence
- The Python script at `~/.openclaw/integrations/tavily/search.py` is a redundant fallback

### Google Tasks (WhatsApp watch actions)

| File                                        | Purpose                                                              |
| ------------------------------------------- | -------------------------------------------------------------------- |
| `~/.openclaw/oauth/google/credentials.json` | Google OAuth app credentials (shared with Tasks + older Gmail setup) |
| `~/.openclaw/oauth/google/tasks-token.json` | Google Tasks OAuth token (separate from Gmail token)                 |

---

---

## Quick Reference: Debugging & Diagnostics

### Log files — always use these, journald does NOT work for user services on this Pi

| What                        | Log path                                                                          |
| --------------------------- | --------------------------------------------------------------------------------- |
| **Gateway (L1)**            | `~/.openclaw/gateway.log`                                                         |
| Daily model reset           | `~/.openclaw/workspace/memory/daily-reset.log`                                    |
| Garmin poller               | `~/.openclaw/workspace/memory/poll-garmin-log.txt`                                |
| CRM poller                  | `~/.openclaw/workspace/memory/poll-crm-log.txt`                                   |
| SharePoint cache poller     | `~/.openclaw/integrations/microsoft/sp-cache-poller.log`                          |
| SharePoint queue processor  | `~/.openclaw/integrations/microsoft/sp-queue-processor.log`                       |
| SharePoint housekeeping     | `~/.openclaw/integrations/microsoft/sp-housekeeping.log`                          |
| Stackstone report poller    | `~/.openclaw/integrations/stackstone/poller.log`                                  |
| Stackstone enquiry poller   | `~/.openclaw/integrations/stackstone/enquiry-poller.log`                          |
| YouTube channel poller      | `~/.openclaw/integrations/youtube/channel-poller.log`                             |
| Health check                | `~/.openclaw/integrations/health/health-check.log`                                |
| Stackstone poll (cron)      | `/tmp/l1-stackstone-poll.log`                                                     |

**Live tail of gateway:**
```bash
tail -f ~/.openclaw/gateway.log
```

**Watch what happens when you send L1 a message:**
```bash
tail -f ~/.openclaw/gateway.log   # then send message in Telegram
```

---

### Key paths

| What                            | Path                                                                |
| ------------------------------- | ------------------------------------------------------------------- |
| Main config (locked)            | `~/.openclaw/openclaw.json`                                         |
| API keys / secrets              | `~/.openclaw/.env`                                                  |
| System skills (10 core)         | `~/.openclaw/skills/`                                               |
| Workspace skills (32 custom)    | `~/.openclaw/workspace/skills/`                                     |
| L1 memory files                 | `~/.openclaw/workspace/memory/`                                     |
| Session transcripts             | `~/.openclaw/agents/main/sessions/`                                 |
| All integrations                | `~/.openclaw/integrations/`                                         |
| Microsoft tokens                | `~/.openclaw/integrations/microsoft/token-*.json`                   |
| Google OAuth tokens             | `~/.openclaw/oauth/google/`                                         |
| Daily reset script              | `~/.openclaw/integrations/provider-switch/daily-reset.py`           |
| SharePoint manifest/cache       | `~/.openclaw/integrations/microsoft/sharepoint-manifest.json`       |
| SharePoint write queue          | `~/.openclaw/integrations/microsoft/sharepoint-queue.json`          |

---

### Systemd user services on this Pi

| Service                              | Purpose                          |
| ------------------------------------ | -------------------------------- |
| `openclaw-gateway.service`           | Main L1 gateway                  |
| `openclaw-mgmt-bot.service`          | Telegram management bot          |
| `openclaw-email-assistant.service`   | Email assistant channel          |
| `openclaw-email-gmail.service`       | Gmail poller                     |
| `openclaw-email-microsoft.service`   | Microsoft mail poller            |
| `openclaw-calendar-google.service`   | Google Calendar poller           |
| `openclaw-calendar-microsoft.service`| Microsoft Calendar poller        |

**Commands:**
```bash
systemctl --user status openclaw-gateway.service
systemctl --user restart openclaw-gateway.service
systemctl --user start openclaw-gateway.service
systemctl --user stop openclaw-gateway.service
```

---

### First-check diagnostics — run these when L1 is silent or stuck

```bash
# 1. Is the gateway actually running?
systemctl --user status openclaw-gateway.service

# 2. What's in the gateway log right now?
tail -30 ~/.openclaw/gateway.log

# 3. Is the config valid JSON?
python3 -c "import json; json.load(open('/home/tomdean88/.openclaw/openclaw.json')); print('JSON OK')"

# 4. What model is L1 using?
python3 -c "import json; cfg=json.load(open('/home/tomdean88/.openclaw/openclaw.json')); print(cfg.get('agents',{}).get('defaults',{}).get('model',{}))"

# ⚠️  NEVER set agent model like this — introduces legacy key that crashes gateway:
#   cfg.setdefault('agent', {})['model'] = 'openai/gpt-5.4'   ← WRONG (old schema)
#
# ALWAYS use this form:
#   cfg.setdefault('agents',{}).setdefault('defaults',{}).setdefault('model',{})['primary'] = 'openai/gpt-5.4'

# 5. Check for rate limit / compaction error
grep -i "usage limit\|compaction\|summarization failed" ~/.openclaw/gateway.log | tail -5

# 6. Check all errors in gateway log
grep -i "error\|warn\|fail" ~/.openclaw/gateway.log | tail -20
```

---

### Config editing (locked file)

```bash
sudo chattr -i ~/.openclaw/openclaw.json   # unlock
# ... edit ...
sudo chattr +i ~/.openclaw/openclaw.json   # re-lock
systemctl --user restart openclaw-gateway.service
```

**Always validate JSON before restarting:**
```bash
python3 -c "import json; json.load(open('/home/tomdean88/.openclaw/openclaw.json')); print('OK')"
```

---

## Known Failure Patterns & Diagnostics

### OpenAI model routing: codex vs standard

- `openai-codex/*` models route through the ChatGPT Plus account — subject to ChatGPT Plus usage limits (~221 min cooldown when hit)
- `openai/*` models use the standard OpenAI API key — separate limits, not affected by ChatGPT Plus cap
- Symptom of hitting the Plus cap: `[compaction] Summarization failed: You have hit your ChatGPT usage limit (plus plan)` — L1 goes silent
- Fix: switch model to `anthropic/claude-sonnet-4-5` or `openai/gpt-5.4` until limit resets (~221 min)
- **Daily reset at 4am always resets back to `openai-codex/gpt-5.4`** — this is intentional. Manual swap when cap hits, codex is the default.

### Gateway crash-loop: "Unknown model: export VAR=value"

**Symptom:** Telegram mgmt-bot shows repeated cycles of:

```
✅ New session started · model: export openclaw_codex_mini_model=openai-codex/gpt-5.3-codex
⚠️ Agent failed before reply: Unknown model: export openclaw_codex_mini_model=openai-codex/gpt-5.3-codex
```

**Root cause:** A shell env-var assignment line (`export OPENCLAW_CODEX_MINI_MODEL=openai-codex/gpt-5.3-codex`) was stored verbatim as the primary model string in `openclaw.json`. The gateway reads this at startup, cannot resolve the model, crashes, auto-restarts, and loops indefinitely.

**Why it happened:** An old version of `cmd_switch` in mgmt-bot read the raw env var value (which in some `.env` formats is the full `export VAR=value` line) and wrote it straight into the config without stripping the prefix.

**Defenses now in place (as of 2026-04-18):**

1. `cmd_switch` in mgmt-bot strips `export VAR=` prefix and trailing `.` before writing any model string to `openclaw.json`
2. The install script's model migration step (`_clean_model_string`) strips corruption from every string in the entire config tree on every `bash ~/install-forked-openclaw.sh` run
3. `daily-reset.py` sanitizes on both read (`_get_current_model`) and write (`_set_model`) paths

**Fix when you see this:**

```bash
cd ~/openclaw && git pull && bash ~/install-forked-openclaw.sh
```

The install script detects and strips the corrupted value, writes the correct model, and restarts the gateway. If the install script itself is too old to have the fix, the `git pull` step fetches the self-updating script which will re-exec the newer version automatically.

**Prevention:** Never write raw env var values from `.env` into `openclaw.json` without stripping the `export VAR=` prefix. The `_load_dotenv()` helper in each integration already does this correctly — the bug only appeared when a different code path read from `os.environ` and the shell line had leaked in a different way.

---

### Source fixes in place (git pull safe as of 2026-04-22)

The following bugs were fixed directly on the Pi in previous sessions. They are now fixed **in source** in this repo so they survive `git pull && bash ~/install-forked-openclaw.sh`:

| Fix | Source file | What was changed |
|-----|-------------|-----------------|
| `daily-reset.py` timeout crash | `attached_assets/integrations/provider-switch/daily-reset.py` | `l1-start.sh` call now wrapped in `try/except TimeoutExpired` — falls through to `systemctl --user` if start script takes >120s |
| `daily-reset.py` not executable | `attached_assets/install-forked-openclaw.sh` | Added `chmod +x "$RESET_DST"` after symlink creation |
| `web_search` blocked after reinstall | `attached_assets/install-forked-openclaw.sh` | Added `alsoAllow` block that idempotently inserts `youtube_transcript` and `web_search` into `tools.alsoAllow` in `openclaw.json` — coding profile blocks both by default |

After the next `bash ~/install-forked-openclaw.sh` these three will be applied automatically. No manual Pi edits needed.

---

### Garmin poller — confirmed endpoint map

`poll-garmin-cookie.py` uses `curl --compressed` with browser-like headers to pass Cloudflare. Auth requires **three things**: full cookie string (19+ cookies), `Connect-Csrf-Token` header value, and the curl backend (not urllib).

**Confirmed working endpoints (as of 2026-04-18):**

| Data           | Endpoint                                                                                      | Notes                                                                    |
| -------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Sleep          | `/gc-api/sleep-service/sleep/dailySleepData?date=YYYY-MM-DD`                                  | Full sleep DTO with stages, score, HRV                                   |
| Resting HR     | `/gc-api/wellness-service/wellness/dailyHeartRate/{date}`                                     | Returns `restingHeartRate`                                               |
| HRV            | `/gc-api/hrv-service/hrv/{date}`                                                              | Returns `weeklyAvg`, `lastNight`, `status`                               |
| Wellness chart | `/gc-api/wellness-service/wellness/dailySummaryChart/{date}`                                  | Hourly list — step values are **cumulative** (take `max()`, not `sum()`) |
| Body battery   | `/gc-api/wellness-service/wellness/bodyBattery/messagingToday?date=YYYY-MM-DD`                | Returns `deltaValue` dict                                                |
| Stress         | `/gc-api/wellness-service/wellness/dailyStress/{date}`                                        | Overrides avg stress; adds `maxStressLevel`                              |
| Activities     | `/gc-api/activitylist-service/activities/search/activities?startDate=...&endDate=...&limit=1` | Most recent activity                                                     |

**Stats/calories — try in order:**

1. `/gc-api/wellness-service/wellness/dailySummary/{date}` — flat dict with `totalKilocalories`, `totalSteps`, `activeKilocalories`, `activeMinutes`
2. `/gc-api/usersummary-service/usersummary/daily/{date}` — fallback
3. The old `/gc-api/userstats-service/statistics/daily` returns **403 Forbidden** — do not use

**Known dead endpoints:**

- `/gc-api/wellness-service/wellness/dailySpo2?calendarDate=...` → 404 (try `/dailySpo2/{date}` path form first; 404 likely means device doesn't support SpO2)
- `/gc-api/userstats-service/statistics/daily` → 403 Forbidden
- `/gc-api/wellness-service/wellness/dailySummaryChart` with query params for steps → values are cumulative totals per interval, not incremental — summing them gives wrong (low) results

**Status code handling:** 401 → cookies expired (fatal, exit and prompt `--setup`); 403 → endpoint forbidden for this account/device (skip, continue); 404 → endpoint path wrong or device doesn't support it (skip); 429 → rate limited (back off).

**Garmin cookie setup:** Run `python3 ~/.openclaw/integrations/garmin/poll-garmin-cookie.py --setup`. You need: (1) the full cookie string from browser devtools on connect.garmin.com, and (2) the `Connect-Csrf-Token` header value from any `/gc-api/` request. Both are stored in `garmin-cookies.json`.

---

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

These exist in upstream code (not our files). They cause warnings during `tsc` but don't affect the `tsdown` build:

- `safe-regex.ts` — `testRegexWithBoundedInput` missing export (referenced by Discord exec-approvals, exec-approval-forwarder). Only affects Discord channel — harmless for our setup.
- `rate-limiter.ts` — `maxMessagesPerMinute`/`maxMessagesPerHour` on Discord config
- `vite.config.ts` — `allowedHosts` type mismatch
- Various `TS7006` implicit-any errors in `compaction.ts`, `pi-embedded-helpers`, `pi-embedded-runner`, `pdf-tool.helpers.ts`, `commands-core.ts`, `get-reply-inline-actions.ts`, `memory-flush.ts`, `post-compaction-context.ts`, `heartbeat-runner.ts`, `process-message.ts`

**Previously upstream errors that we fixed:**

- `dm-policy-shared.ts` — `resolvePinnedMainDmOwnerFromAllowlist` was removed by upstream but still imported by all channel handlers. We re-implemented it (see "Recreated/restored upstream exports" below).

**Build fix**: `tsconfig.plugin-sdk.dts.json` has `noEmitOnError: false` (upstream has `true`) so the `build:plugin-sdk:dts` step emits declarations despite these upstream errors. Without this, the build fails on the Pi.

### Recreated/restored upstream exports

- `src/plugin-sdk/root-alias.cjs` — CJS-to-ESM proxy shim for legacy plugin `require()` support. Was missing after upstream sync (`.cjs` files not captured in tarball extraction). Recreated based on test expectations and upstream plugin-sdk loader behavior. Inlines `emptyPluginConfigSchema` for fast access; lazily loads full ESM index via `require("./index.js")` (works in Node 22.12+ which supports `require()` of ESM modules).
- `resolvePinnedMainDmOwnerFromAllowlist` in `src/security/dm-policy-shared.ts` — Function removed by upstream refactor but still imported by Telegram, WhatsApp, Discord, Signal, Slack, iMessage, and Line channel handlers. Without it, all inbound DM message processing crashes with `ReferenceError`. Re-implemented: returns the single pinned DM owner from the allowlist when `dmScope` is `"main"` and exactly one non-wildcard entry exists; returns `null` otherwise.
- `testRegexWithBoundedInput` in `src/security/safe-regex.ts` — Still missing (only used by Discord exec-approvals and exec-approval-forwarder, neither of which we use). Will cause runtime error if Discord channel is enabled.

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
- `src/web/auto-reply/watch-action-scanner.ts` — Reads watch transcript JSONL, tracks cursor, returns new messages for analysis
- `src/web/auto-reply/watch-action-classifier.ts` — AI-powered action detection using cheap model (Haiku/4o-mini/Flash). Conversation-aware: considers full thread context so resolved actions aren't flagged
- `src/web/auto-reply/watch-action-notify.ts` — Sends Telegram inline keyboard cards for detected actions
- `src/web/auto-reply/watch-action-store.ts` — Pending action store (JSON file) for callback button handling
- `src/web/auto-reply/watch-action-scheduler.ts` — Scan scheduler: event-driven (45s debounce after each message) + 2-min tick + 5-min interval throttle. Active 8am-10pm. Exports `triggerWatchActionScanDebounced()` called from `monitor.ts` on every new message.
- `src/web/auto-reply/watch-action-google-tasks.ts` — Google Tasks integration. Device Authorization Flow (TV-style: user visits accounts.google.com/device and enters a code). Credentials at `~/.openclaw/oauth/google/credentials.json`, token at `~/.openclaw/oauth/google/tasks-token.json`. Shopping actions → "Shopping" task list (auto-created). Other actions → default task list.
- `src/agents/soul-integrity.ts` — SOUL.md hash verification
- `src/agents/soul-vault.ts` — Encrypted SOUL.md at rest
- `attached_assets/install-forked-openclaw.sh` — Pi install/upgrade script (self-updating: re-execs from repo copy if newer)
- `attached_assets/integrations/config-check/check.py` — Config drift detector: verifies exec.host=gateway, totpWindowMinutes=5, telegram.dmPolicy=allowlist, whatsapp.mode=watch. Logs to `~/.openclaw/workspace/memory/config-alerts.log`. Run automatically at end of install.
- `attached_assets/integrations/docx-converter/convert.py` — Watches `~/.openclaw/media/inbound/` for .docx files, converts to .txt via LibreOffice headless. Logs to `workspace/memory/docx-conversions.log`.
- `attached_assets/integrations/microsoft/poll.py` — Microsoft Graph email poller: inbox + sent items, per-contact state tracking in `last-seen-emails.md`, immediate alert file on new email from known contact, shorter poll interval for known contacts (2min vs 5min general). Auto-detects and converts MSAL token cache format. Handles 429 rate limiting with `Retry-After` backoff.
- `attached_assets/integrations/google/gmail_poll.py` — Gmail email poller: identical guardrails to Microsoft poller (prompt-injection headers, known-contacts.txt filtering). Writes to `GMAIL_INBOX.md` / `GMAIL_EXTERNAL.md`. Uses Google OAuth2 (`gmail-credentials.json` + `gmail-token.json`).
- `attached_assets/integrations/tavily/search.py` — Tavily web search. Reads `TAVILY_API_KEY` from `~/.openclaw/.env`. Supports `--max-results`, `--include-answer`, `--search-depth basic|advanced`, `--topic general|news`, `--raw-json`. Deployed to `~/.openclaw/integrations/tavily/search.py`.
- `attached_assets/scripts/whatsapp_recent.sh` — Generates `~/.openclaw/workspace/WHATSAPP_RECENT.md` (last 48h, max 400 lines) from the full `WHATSAPP_LOG.md`. Cron every 15 min. L1 reads `WHATSAPP_RECENT.md`; full log stays untouched as archive. Deployed and cron-installed automatically.
- `attached_assets/prospector/process_queue.sh` — Bounce/unsub queue processor. L1 appends email addresses to `~/prospector/pending_bounces.txt` or `~/prospector/pending_unsubs.txt` (plain file append, no exec/TOTP needed). Cron runs every 30 min and calls `python3 ~/prospector/manage.py bounce|unsub [email]` for each queued address, then clears the files. Logs to `~/prospector/logs/queue_processor.log`. Deployed and cron-installed automatically by install script.
- `scripts/copy-plugin-manifests.mjs` — Copies `openclaw.plugin.json` from each `extensions/*/` source directory to the corresponding `dist/extensions/*/` output directory. Run as part of `pnpm build` and `build:strict-smoke`. Without this, the plugin loader cannot find plugins at startup.

## WhatsApp Watch Action Scanner

Periodically scans WhatsApp watch-mode transcripts for actionable items using a cheap AI model, then surfaces them as Telegram inline keyboard cards.

Config in `openclaw.json` under `channels.whatsapp`:

```json
{
  "channels": {
    "whatsapp": {
      "mode": "watch",
      "watchActions": {
        "enabled": true,
        "activeHoursStart": 8,
        "activeHoursEnd": 22,
        "intervalMinutes": 60,
        "model": "anthropic/claude-haiku-4-20250414"
      }
    }
  }
}
```

- `enabled` (default false) — must be true to activate
- `activeHoursStart`/`activeHoursEnd` (default 8/22) — scan window
- `intervalMinutes` (default 60) — how often to scan during active hours
- `model` (optional) — override the cheap model used for classification. If unset, auto-selects cheapest model from your configured provider (Haiku for Anthropic, 4o-mini for OpenAI, Flash for Google)

Action types detected: shopping, calendar, task, reminder, urgent. The AI analyses full conversation threads so it understands when actions have been resolved by follow-up messages.

Telegram cards have inline buttons: "Add to list" / "Ignore". Button callbacks update the action store and edit the card message.

## Environment Variables

See `.env.example` for all options. Key variables:

- `OPENCLAW_GATEWAY_TOKEN` — auth token for the gateway
- `OPENCLAW_VAULT_PASSPHRASE` — passphrase for SOUL.md encryption at rest
- AI provider keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.
- Channel tokens: `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, `SLACK_BOT_TOKEN`, etc.
