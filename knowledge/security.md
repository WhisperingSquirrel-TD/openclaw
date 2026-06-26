# Security & Control Features

> Part of the OpenClaw knowledge base. Map: [`../replit.md`](../replit.md).
> Related: [TOTP approval](./totp.md) · [WhatsApp watch mode](./whatsapp.md) · [Upstream sync](./upstream-sync.md) (these customizations must survive merges) · [Pi reference](./pi-reference.md)

Most of these features were added as numbered requirements (Req #N) and must be preserved across upstream syncs — see [Upstream sync: merge details](./upstream-sync.md#merge-details-for-conflict-files).

## Per-Channel denyCommands (Req #8)

Extends the global `gateway.nodes.denyCommands` to per-channel scoping. Setting `channels.whatsapp.denyCommands: ["message.send"]` blocks sends only for WhatsApp while leaving other channels unaffected.

- Config: `channels.<channel>.denyCommands: string[]` (WhatsApp, Telegram)
- Files: `src/gateway/node-command-policy.ts` (`resolveChannelDenyCommands`), channel config schemas

**Permanently blocked commands** (must always remain in `denyCommands`, verified by config-check/check.py):

- `calendar.add` / `calendar.update` — calendar writes must go through the Outlook/Microsoft integration only (`poll.py`), not any generic calendar provider (e.g. Google Calendar). Unblocking these globally would allow L1 to write to the wrong calendar. See [Integrations: Microsoft](./integrations/microsoft.md).
- `calendar.delete` — destructive, never permitted
- `message.react`, `camera.snap`, `camera.clip`, `screen.record`, `contacts.add`, `reminders.add`

## Immutable System Prompt (Req #10)

Adds `agents.defaults.systemPrompt` — an immutable preamble injected before SOUL.md in every agent session. Not subject to bootstrap character limits.

- Config: `agents.defaults.systemPrompt: string`
- Files: `src/agents/system-prompt.ts`, `src/config/zod-schema.agent-defaults.ts`

## SOUL.md Integrity Verification (Req #9)

SHA-256 hash of SOUL.md computed on first load and verified before every session. Per-workspace scoped. If SOUL.md is modified at runtime, sessions are refused with an error.

- Files: `src/agents/soul-integrity.ts`, `src/agents/bootstrap-files.ts`

## Outbound Message Audit Log (Req #12)

Append-only JSONL log for all outbound messages (sent or blocked). Each entry includes timestamp, channel, recipient, content (truncated to 10K chars), blocked status, block reason, and session ID.

- Log path: `<state-dir>/audit/outbound-audit.jsonl`
- Block reasons: `watch_mode`, `deny_commands`, `rate_limit`, `trust_gate`
- Files: `src/infra/outbound/audit-log.ts`, `src/infra/outbound/deliver.ts`, `src/web/outbound.ts`

See [Audit Log Tamper Protection](#audit-log-tamper-protection) below.

## Rate Limiting on Agent Output (Req #13)

Sliding-window rate limiter per channel+account with configurable per-minute and per-hour limits. Overflow behavior: `queue` (default, throws RateLimitError) or `drop` (silently skips).

- Config: `channels.<channel>.maxMessagesPerMinute`, `maxMessagesPerHour`, `rateLimitOverflow` (WhatsApp, Telegram, Discord)
- Files: `src/infra/outbound/rate-limiter.ts`, `src/infra/outbound/deliver.ts`

## Session Isolation Between Channels (Req #11)

Config option `session.outboundContextScope: "channel-isolated" | "shared"`. When channel-isolated, the system prompt instructs the agent to never leak content between channels. Outbound messages are tagged with `[channel:<name>]` in transcripts.

- Config: `session.outboundContextScope`
- Files: `src/config/zod-schema.session.ts`, `src/agents/system-prompt.ts`

## Trust Level Enforcement (Req #14)

At `trustLevel >= 1`, outbound messages are held and routed through the exec approval system for owner approval. Denied or timed-out messages are logged to the audit trail. On the Pi this approval is delivered via [TOTP](./totp.md).

- Config: `agents.defaults.trustLevel: number`, `agents.defaults.requireApproval: string[]`
- Files: `src/infra/outbound/trust-gate.ts`, `src/infra/outbound/deliver.ts`

## Encrypted SOUL.md at Rest (Req #7)

AES-256-GCM encryption for SOUL.md using a passphrase (via `OPENCLAW_VAULT_PASSPHRASE` env var). Encrypted file stored at `<state-dir>/vault/SOUL.md.enc`. Decrypted only in RAM (via `/dev/shm` or in-memory buffer). Plaintext is wiped after initial encryption. Shutdown hooks ensure cleanup.

- Env: `OPENCLAW_VAULT_PASSPHRASE` (see [Architecture: env vars](./architecture.md#environment-variables))
- Files: `src/agents/soul-vault.ts`, `src/agents/workspace.ts`

## Exec Security Denylist

A hardcoded denylist in `src/agents/bash-tools.exec-host-gateway.ts` blocks exec commands that could tamper with system protections, regardless of TOTP approval. Blocked patterns include:

- `chattr` (any use — prevents removing immutable/append-only flags)
- References to `openclaw.json`, TOTP secret files, audit log, `SOUL.md.enc`, vault passphrase
- `systemctl stop/disable/mask openclaw`, `l1-stop.sh`
- System files (`/etc/passwd`, `/etc/shadow`, `.bashrc`)
- Watch mode data: `watch-transcripts`, `watch-actions`, `pending-actions.json` (prevents L1 from reading or tampering with WhatsApp surveillance data — see [WhatsApp watch mode](./whatsapp.md))

This denylist is evaluated before TOTP approval, so even an active approval window cannot authorize these commands.

Additionally, when `approvalMode: "totp"` (hardened mode), any command flagged by the obfuscation detector (`src/infra/exec-obfuscation-detect.ts`) is hard-blocked (not just warned). This prevents bypass via base64 encoding, shell heredocs, eval/exec wrappers, curl-pipe-shell, variable expansion chains, and similar techniques.

## Audit Log Tamper Protection

The audit log (`<state-dir>/audit/outbound-audit.jsonl`) is:

- Opened with `0600` permissions
- Set to append-only (`chattr +a`) on creation (best-effort, requires root)
- Protected by the exec denylist (agent cannot reference the file in exec commands)
- The install script additionally sets `chattr +a` on the audit log and `chattr +i` on TOTP secret files (see [Pi deployment](./pi-deployment.md))
