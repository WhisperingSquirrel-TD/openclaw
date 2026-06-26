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

| Setting                              | Value         | Effect                                                                                  |
| ------------------------------------ | ------------- | --------------------------------------------------------------------------------------- |
| `heartbeat.lightContext`             | `true`        | Heartbeat only sends `HEARTBEAT.md`, **not** SOUL.md/memory. ~70% cut in heartbeat cost |
| `heartbeat.every`                    | `60m`         | Once per hour (default 30m) — halves background API calls                               |
| `heartbeat.activeHours`              | `07:00–23:00` | Zero calls midnight–7am                                                                 |
| `heartbeat.ackMaxChars`              | `150`         | Heartbeat replies capped at 150 chars                                                   |
| `bootstrapMaxChars`                  | `10000`       | Each workspace file (SOUL.md etc.) capped at 10KB                                       |
| `contextPruning.mode`                | `cache-ttl`   | Prunes conversation history >2h old (Claude only)                                       |
| `providerTimeoutSeconds.ollama`      | `1800`        | Ollama session timeout = 30 min. Force-assigned (not setdefault) so re-running install always corrects lower values. A real session has 10k–20k input tokens; at Pi 4 prefill rates of 20–50 tok/s that's 200–1000 s before any output is generated. |
| `memory.qmd.update.embedActiveHoursStart` / `embedActiveHoursEnd` | `2` / `5` | Confines `qmd embed` (heavy CPU — observed at 343% on a 4-core Pi) to 02:00–05:00. Outside this window `shouldRunEmbed()` short-circuits, leaving CPU free for Ollama fallback. Force-assigned each install. Implemented in `src/memory/qmd-manager.ts` (`isWithinEmbedActiveHours`) with config in `src/config/types.memory.ts` / `zod-schema.ts` / `backend-config.ts`. |

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

### Garmin poller — garminconnect library (DI OAuth, login once)

`poll-garmin.py` is the single canonical poller, built on the maintained
[`cyberjunky/python-garminconnect`](https://github.com/cyberjunky/python-garminconnect)
library (Garmin's current DI OAuth flow). The old cookie poller
(`poll-garmin-cookie.py`) and the legacy garth poller are **retired and deleted** —
both cookie scraping (deprecated `/proxy/` paths returned empty `{}`) and direct
garth logins (Cloudflare-blocked + per-account 429 bans lasting 24–72h) are dead ends.

**Auth model — you log in ONCE:**

- **Setup** (`--setup`, or `/garmin-setup` on Telegram): reads `GARMIN_EMAIL` +
  `GARMIN_PASSWORD` from `~/.openclaw/.env`, logs in (MFA prompt only if the
  account has MFA — this account does not), and caches a self-renewing token in
  `~/.garminconnect/` (`oauth1_token.json` + `oauth2_token.json`).
- **Scheduled run** (cron, 09:00): constructs the client with **no credentials**
  and resumes from the cached token, auto-refreshing it. It can therefore **never
  fall through to a credential login** — the path that caused the 429 spiral is
  structurally impossible from cron.
- **Token-rejected / missing**: the run logs a `FLAG TO TOM` to re-run setup and
  exits cleanly — it never retries a login.
- **429 guard**: any 429 writes `~/.openclaw/integrations/garmin/.garmin_429_backoff`;
  for the next 24h all runs skip immediately so a ban is never made worse.

**Data collected** (for L1 exercise/recovery advice): resting HR, post-workout
recovery HR (from activity details), HRV (last night / status / weekly), **training
readiness** (Garmin's recovery-readiness score), sleep stages + score, SpO2,
stress, Body Battery high/low, VO2max, steps/calories/intensity minutes, and recent
activities. Written to `GARMIN_DAILY.md` (full snapshot) and `GARMIN_ARCHIVE.md`
(rolling 28-day compact history).

- **Script**: `~/.openclaw/integrations/garmin/poll-garmin.py`
- **Token cache**: `~/.garminconnect/` (override dir via `GARMINTOKENS` env var)
- **Commands**: `--setup` (one-time login), `--status` (token validity/age, never
  logs in), `--backfill N` (N days of history into the archive); plus mgmt-bot
  `/garmin`, `/garmin-setup`, `/garmin-status`
- **Library dep**: `garminconnect` — installed/upgraded automatically by the install script
- If the account ever enables MFA, run `--setup` from a terminal so the code can be entered interactively

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

### AI Briefing Pipeline

Weekly automated briefing: RSS collection → heuristic ranking → Claude synthesis → `AI_BRIEFING_CURRENT.md`.

| File | Purpose |
| ---- | ------- |
| `~/.openclaw/integrations/ai-briefing/collect.py` | Fetch + deduplicate items from ~16 RSS/Atom feeds |
| `~/.openclaw/integrations/ai-briefing/rank.py` | Heuristic pre-filter, title-word clustering, Haiku scoring; fallback to heuristics if API fails |
| `~/.openclaw/integrations/ai-briefing/synthesize.py` | Tavily enrichment (top 4 items, 3000-char cap), Sonnet synthesis, writes `AI_BRIEFING_CURRENT.md`; fallback to structured plain-text |
| `~/.openclaw/integrations/ai-briefing/run.py` | Orchestrator: runs collect→rank→synthesize, updates `state.json`, exit codes 0/1/2 |
| `~/.openclaw/ai-briefing/AI_BRIEFING_CURRENT.md` | Latest briefing handoff file for L1 to read |
| `~/.openclaw/ai-briefing/state.json` | Pipeline state (last run, per-stage summaries, error) |
| `~/.openclaw/ai-briefing/seen-items.json` | URL-hash dedup across runs (prevents repeats) |
| `~/.openclaw/ai-briefing/included-items.json` | "New since last briefing" tracking |
| `~/.openclaw/ai-briefing/raw/` | Raw collected JSON per run |
| `~/.openclaw/ai-briefing/ranked/` | Ranked JSON per run |
| `~/.openclaw/ai-briefing/briefings/` | Archived briefing Markdown files |
| `~/.openclaw/integrations/ai-briefing/pipeline.log` | Cron log |
| `reference/AI-BRIEFING-POLICY.md` | Scoring policy, inclusion/exclusion rules, format contract |
| `reference/ai-briefing-sources.yaml` | Machine-readable source list with weights |

**Scoring:** 4 dimensions (Relevance, Novelty, Actionability, Credibility) × 1–5 pts each = max 20. Shortlist ≥10; Tavily enrichment ≥14; quiet-week threshold: <2 items ≥10.

**Cron:** every Monday at 06:00 → `run.py`. On-demand via `/ai-briefing run` in mgmt-bot or `python3 ~/.openclaw/integrations/ai-briefing/run.py` directly.

**mgmt-bot commands:**
- `/ai-briefing` — show pipeline status from `state.json`
- `/ai-briefing run` — run the full pipeline now (2–5 min)
- `/ai-briefing read` — preview first 3000 chars of `AI_BRIEFING_CURRENT.md`

**Resilience:** partial source failure is tolerated (per-feed try/except); Haiku failures fall back to heuristic ranking; Sonnet failures fall back to structured plain-text briefing; pipeline always writes an output file unless zero items are collected.

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
| AI briefing pipeline        | `~/.openclaw/integrations/ai-briefing/pipeline.log`                               |
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

**Fixed in source (2026-04-18).** Cause: a raw `export VAR=value` line leaked from `.env` and was written verbatim as the model string in `openclaw.json`, so the gateway couldn't resolve the model and crash-looped. Now defended in three places: `cmd_switch` (mgmt-bot) strips the `export VAR=`/trailing-`.`, the install script's `_clean_model_string` sanitizes the whole config tree on every run, and `daily-reset.py` sanitizes on read+write. If you ever see it, run `cd ~/openclaw && git pull && bash ~/install-forked-openclaw.sh` — install strips the bad value and restarts. **Rule:** never write a raw `.env` value into `openclaw.json` without stripping the `export VAR=` prefix.

---

### Outstanding items requiring Pi access

| Item | Status | Pi commands |
|------|--------|-------------|
| Desktop taskbar (LXPanel) | Unresolved — terminal and file-manager buttons disappeared after reboot | `lxpanelctl restart` to reload panel; if buttons still missing: right-click panel → Add/Remove Panel Items → add Application Launch Bar → add lxterminal and pcmanfm |
| `apply_patch`/`cron` alsoAllow warnings | Baked into OpenClaw's `coding` profile — not our config | Cannot fix without a plugin override; warnings are cosmetic |

---

### OpenClaw auth debugging playbook (2026-04-27)

**Symptom:** L1 silent — `⚠️ Agent failed before reply: All models failed (N): ... No API key found for provider "ollama"`

**Quick triage steps (in order):**

1. **Check gateway is running** — `openclaw logs --follow`. If "Gateway not reachable": run `openclaw doctor` → say Yes to "Start gateway service now?"
2. **Check provider cooldowns** — shown in `openclaw doctor` output. openai-codex rate-limits clear within ~40 min automatically, no action needed.
3. **Check Ollama auth** — see fix below.

**Ollama auth fix (the correct one):**

OpenClaw resolves provider auth via three paths in order:
1. `auth-profiles.json` — entries must be inside `data["profiles"]` dict, AND a matching top-level key at root level with credentials. Profiles is a **list** of name strings, not a dict — the actual credential objects ARE top-level keys.
2. **Environment variable** — `OLLAMA_API_KEY` env var (simplest, most reliable)
3. `models.json` custom `apiKey` field — unreliable, `normalizeOptionalSecretInput` may return null

**The fix that actually works:**
```bash
mkdir -p ~/.config/environment.d/
echo 'OLLAMA_API_KEY=ollama' > ~/.config/environment.d/openclaw-ollama.conf
systemctl --user daemon-reload
systemctl --user restart openclaw-gateway.service openclaw-mgmt-bot.service
```
This persists across reboots. The value `"ollama"` can be any non-empty string — Ollama doesn't validate it.

**auth-profiles.json structure (for reference):**
```json
{
  "version": 1,
  "profiles": ["anthropic:default", "openai-codex:default"],  // LIST of active profile names
  "anthropic:default": { "accessToken": "...", ... },         // top-level credential objects
  "openai-codex:default": { ... },
  "lastGood": ["anthropic"],
  "usageStats": { ... }
}
```
The `profiles` list is what OpenClaw scans. Credentials for each profile are stored as **top-level keys** (same name). Our earlier failed attempts wrote `"ollama:ollama-local"` either at top-level only (not in the list) or inside a `profiles` dict (but profiles is a list, not a dict). The env var approach bypasses all of this.

**Source file for auth logic:**
`~/openclaw/node_modules/.pnpm/openclaw@2026.2.24_*/node_modules/openclaw/dist/auth-profiles-BLqWs5Ho.js`
Search for `resolveEnvApiKey` and `getCustomProviderApiKey` to trace the lookup chain.

**auth-profiles.json is overwritten on every gateway start** — never manually edit it while the gateway or mgmt-bot is running. Always: stop both services → edit → start both.

**Services to stop/start:**
```bash
systemctl --user stop openclaw-mgmt-bot.service openclaw-gateway.service
# ... edit ...
systemctl --user start openclaw-gateway.service openclaw-mgmt-bot.service
```

**Logs location:** `/tmp/openclaw/openclaw-YYYY-MM-DD.log` (NOT journalctl — no journal files exist)
```bash
grep -i "ollama\|error\|failed" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -30
```

---

### Garmin poller — data source

The poller no longer talks to `/gc-api/` endpoints directly — the `garminconnect`
library owns all endpoint mapping, Cloudflare handling, and token refresh. Field
extraction lives in `poll-garmin.py::extract()`, which reads the library's typed
responses (`get_stats`, `get_heart_rates`, `get_hrv_data`, `get_sleep_data`,
`get_spo2_data`, `get_stress_data`, `get_training_readiness`, `get_body_battery`,
`get_max_metrics`, `get_activities` / `get_activity`). Note the library exposes
`get_rhr_day` / `get_heart_rates` — there is **no** `get_resting_heart_rate`. If a
field is missing on a given account/device the poller writes `n/a` and continues;
upgrade the library (`pip3 install --break-system-packages --upgrade garminconnect`)
if Garmin changes a response shape.

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

The 2026-03-08 sync had 5 files carrying both upstream refactors and our security customizations. Upstream was used as the base and our customizations re-applied. On any future sync, preserve these per file:

- **`src/agents/bash-tools.exec-host-gateway.ts`** — our denylist, TOTP gate (`requestExecApproval`), and obfuscation hard-block must run BEFORE upstream's approval-context resolution.
- **`src/web/outbound.ts`** — keep `assertNotWatchMode(account)` guard + audit logging on block (upstream added a `cfg` param).
- **`src/web/auto-reply/monitor.ts`** — keep watch-mode routing, `appendWatchTranscript`, read-receipt/debounce suppression.
- **`src/web/inbound/monitor.ts`** — keep presence/access-control/read-receipt/composing bypasses and `sendMedia`/`reply` blocking.
- **`src/gateway/node-command-policy.ts`** — keep `resolveChannelDenyCommands`.

Also our addition: `ChannelMode = "active" | "watch"` + `mode` field on `ResolvedWhatsAppAccount` (`src/web/accounts.ts`) and in `WhatsAppSharedSchema` (`zod-schema.providers-whatsapp.ts`) — upstream keeps removing these.

### Durable build warnings (must not regress)

- **`tsconfig.plugin-sdk.dts.json` must keep `noEmitOnError: false`** (upstream defaults to `true`) — otherwise `build:plugin-sdk:dts` fails on the Pi due to pre-existing upstream `tsc` errors (these are `tsc`-only; the `tsdown` build is unaffected).
- **`src/plugin-sdk/root-alias.cjs` must exist** — CJS-to-ESM shim for legacy plugin `require()`; not captured by upstream tarballs.
- **`resolvePinnedMainDmOwnerFromAllowlist` in `src/security/dm-policy-shared.ts`** — re-implemented by us; upstream removed it but every channel handler still imports it. Without it, all inbound DM processing crashes with `ReferenceError`.
- **`testRegexWithBoundedInput` in `src/security/safe-regex.ts`** — still missing upstream; only used by Discord exec-approvals. Will throw at runtime if the Discord channel is enabled.

> Index of fork-unique files removed to save context — reconstruct from the repo with `git diff --name-only` against the upstream base, or read each file's header comment. The behavioral details for these live in the feature sections above (Security & Control Features, WhatsApp Watch Mode/Action Scanner, the integration runbooks).

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
