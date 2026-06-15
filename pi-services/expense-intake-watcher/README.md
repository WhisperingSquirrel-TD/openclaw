# Expense Intake Watcher (legacy runtime path)

_Last updated: 2026-06-15 10:47_

This directory remains the **backward-compatible runtime path** for the broader **Inbound Watch Router**.

## Canonical name now

Use **Inbound Watch Router** when referring to the watch-layer system overall.

Why:

- the runtime now routes more than expenses
- it classifies email + sent items + WhatsApp using shared inbound flags
- it preserves closure-state proof for materially important non-expense items too

## Compatibility promise

The current working path is intentionally unchanged:

- `/home/tomdean88/openclaw/pi-services/expense-intake-watcher/watcher.py`

That avoids breaking:

- existing systemd units
- existing scripts/docs that still point at the old path
- operator muscle memory

## Runtime state

State is dual-written for transition safety:

- canonical: `~/.openclaw/runtime/inbound-watch-router/`
- legacy compatibility: `~/.openclaw/runtime/expense-intake-watcher/`

## Actual role

Pi-native watch-layer monitor for inbound/outbound operational surfaces, with expense handling as the strongest automatic route.

Current sources:

- `/home/tomdean88/.openclaw/workspace/GMAIL_INBOX.md`
- `/home/tomdean88/.openclaw/workspace/MICROSOFT_INBOX.md`
- `/home/tomdean88/.openclaw/workspace/ASSISTANT_INBOX.md`
- both **Inbox** and **Sent Items** sections from those files
- `/home/tomdean88/.openclaw/workspace/WHATSAPP_RECENT.md`

Primary flags:

- `ALERT`
- `FOLLOW_UP`
- `CRM`
- `OUTBOUND_CONTEXT`
- `EXPENSE`
- `DIARY`
- `IGNORE`

## Important design rule

The watcher is not allowed to silently drop a suspicious item.
Every candidate must end each pass as one of:

- logged
- duplicate
- pending with blocker
- not needed

## WhatsApp direct-thread interpretation

- direct-chat interpretation now treats outbound `Me:` lines as first-class thread context rather than disposable noise
- unresolved inbound asks in direct chats should surface only when they remain the latest actionable state in that thread
- later `Me:` replies suppress older inbound asks unless the later context itself becomes the hanging item
- if Tom sent the most recent direct follow-up/chase and no later reply is visible, the watcher can surface that as a hanging outbound thread
- priority contacts are now treated more narrowly: only real asks/logistics/questions should surface, not generic chatter, acknowledgements, or media
- noisy group/pod/broadcast traffic is suppressed more aggressively, especially link-dumps, generic greetings, and media floods in known low-signal groups
- recency weighting is intentionally conservative: stale/resolved direct chatter should drop out instead of being repeatedly surfaced
- stale WhatsApp pending/surfaced artifacts are pruned from both the monitored ledger and pending-expense rows when the originating live signal is no longer present/actionable

## Current limits

- full-body email extraction still depends on the trusted reader route succeeding
- WhatsApp thread inference for unlabeled direct `Me:` lines is heuristic because the export format does not carry an explicit peer/thread id on those lines
- WhatsApp can only create pending signals from the recent feed; it cannot inspect hidden media/audio without richer source access
- SharePoint evidence filing is still separate from this watcher

## Related docs

- `/home/tomdean88/openclaw/pi-services/inbound-watch-router/README.md`
- `~/.openclaw/workspace/reference/INBOUND-ROUTING.md`
- `~/.openclaw/workspace/reference/INBOUND-MONITORING-RUNTIME-JOBS.md`
- `~/.openclaw/workspace/reference/EXPENSE-SIGNAL-HANDLING.md`
