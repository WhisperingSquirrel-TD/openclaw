# TOTP Approval System

> Part of the OpenClaw knowledge base. Map: [`../replit.md`](../replit.md).
> Related: [Security & control](./security.md) (trust gate, exec denylist) · [Pi reference](./pi-reference.md)

When `approvalMode: "totp"` is set, the trust gate uses a 6-digit authenticator code (RFC 6238 TOTP) instead of macOS socket-based approval. This is the Pi-compatible alternative for gated actions. It works together with [Trust Level Enforcement](./security.md#trust-level-enforcement-req-14).

## How it works

1. Agent attempts a gated action (`message.send` or `exec.run` at `trustLevel >= 1`)
2. Trust gate checks for an active approval window — if open, action proceeds immediately
3. If no window: owner is prompted to send their 6-digit code on Telegram
4. Owner sends code → window opens for `totpWindowMinutes` (default 5) → all queued and future gated actions proceed
5. Window expires → new code required

## Gated actions

- `message.send` — outbound messages to any channel (email, WhatsApp, Discord, etc.)
- `exec.run` — shell command execution on the gateway host (closes the exec bypass gap where scripts could send emails via `exec` without TOTP)

## Setup

1. Set config: `agents.defaults.approvalMode: "totp"`, optionally `totpWindowMinutes: 5`
2. Send `/totp-setup` on Telegram → get `otpauth://` URI to scan in Google Authenticator/Authy
3. When prompted, send 6-digit code to approve

## Commands

- `/totp-setup [accountName]` — Generate new TOTP secret, returns URI for authenticator app
- `/totp-status` — Show whether TOTP is configured and window status
- `/totp-lock` — Manually close the approval window immediately
- `123456` (any 6-digit number) — Automatically checked as TOTP code when `approvalMode: "totp"`

## Config

- `agents.defaults.approvalMode: "socket" | "totp"` (default: `"socket"`)
- `agents.defaults.totpWindowMinutes: 1–60` (always `2` on Pi — enforced by the [install script](./pi-deployment.md))

## Secret storage

`<state-dir>/totp/totp-secret.enc` (AES-256-GCM, encrypted with `OPENCLAW_VAULT_PASSPHRASE`) or `totp-secret.txt` (plaintext fallback). The install script sets `chattr +i` on TOTP secret files; the [exec denylist](./security.md#exec-security-denylist) blocks the agent from referencing them.

## Replay protection

Each TOTP code can only be used once. A monotonic counter is persisted at `<state-dir>/totp/totp-last-counter.txt` — codes at or below the last-used counter step are rejected even within the ±1 window.

## Files

- `src/infra/totp/totp.ts` — RFC 6238 TOTP core (generate, verify, URI, replay protection)
- `src/infra/totp/totp-setup.ts` — Secret generation, encrypted storage, setup helper
- `src/infra/totp/totp-session.ts` — In-memory approval window manager
- `src/infra/outbound/trust-gate.ts` — Trust gate with TOTP mode support
- `src/auto-reply/reply/commands-totp.ts` — Telegram command handlers

## Runtime behaviour (operational notes)

- The TOTP wait window is **2 minutes** from when the code is requested. Once a valid code is accepted, the approval window is **5 minutes** by default. L1's SOUL.md should reflect this so it doesn't misinform the user about timing.
- Invalid codes immediately cancel any pending approval request (`rejectPendingApprovals`) — but only if there is an active pending request. If there is none (e.g., a replayed old Telegram message at startup), the rejection is a no-op so L1 is not affected.
- Email polling is **never** a TOTP-gated action. If L1 tries to use `exec.run` to refresh email feeds, that is wrong — the pollers run as systemd services and self-recover. SOUL.md should make this explicit. See [Pi deployment: background services](./pi-deployment.md#background-services-pi).
