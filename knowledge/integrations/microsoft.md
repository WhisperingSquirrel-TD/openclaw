# Integration: Microsoft (Email, Calendar, SharePoint)

> Part of the OpenClaw knowledge base. Map: [`../../replit.md`](../../replit.md) · Knowledge index: [`../README.md`](../README.md).
> Related: [Integrations: Google](./google.md) · [Pi deployment: background services](../pi-deployment.md#background-services-pi) · [Pi reference](../pi-reference.md) · [Security: permanently blocked calendar writes](../security.md#per-channel-denycommands-req-8)

## Microsoft OAuth — unified scope strategy (IMPORTANT)

**Why reauth keeps happening and how to stop it:** Microsoft's device-code consent is scope-bound at the time of first sign-in. If a token was originally created with `Mail.Send offline_access`, subsequent refresh requests for `Files.ReadWrite` are silently ignored — the token looks valid but 403s on SharePoint. Every new capability added to the system would historically trigger a new reauth.

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

## Microsoft OAuth token format

- The Microsoft auth library (MSAL) stores tokens in PascalCase format: `AccessToken`, `RefreshToken`, `AppMetadata`. Our poller expects a flat format: `access_token`, `refresh_token`, `tenant_id`, `client_id`.
- `poll.py` auto-detects and converts the MSAL cache format on first load, writing back a simple flat file. No manual conversion needed on new installs.
- If `tenant_id` is missing, default to `"common"` — works for personal Microsoft accounts.
- Microsoft Graph API returns `429 Too Many Requests` when polled too rapidly after a restart (multiple restart cycles cause burst). The poller handles this by reading the `Retry-After` header and waiting before retrying.

## SharePoint CRM housekeeping

**Script**: `attached_assets/integrations/microsoft/sharepoint_housekeeping.py`
**Deployed to**: `~/.openclaw/integrations/microsoft/sharepoint_housekeeping.py` (symlink via install script)

Entity-by-entity CRM normalisation using the Anthropic batch API (50% cost saving). Follows the same two-phase cron model as the [YouTube channel poller](./youtube.md).

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

## SharePoint mirror (read-only local cache + write queue)

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

## Email & calendar files

Poller scripts, feed files, token paths, poll logs and systemd services are consolidated in [Pi reference](../pi-reference.md). Calendar writes are restricted to this integration only — see [Security](../security.md#per-channel-denycommands-req-8).
