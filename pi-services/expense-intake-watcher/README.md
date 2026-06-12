# Expense Intake Watcher

Pi-native route-agnostic expense watcher.

## Purpose

If something expense-shaped shows up anywhere in the mirrored operational surfaces, the system should **jump on it immediately** rather than waiting for Tom to ask.

The guarantee now lives at the **mirror/watch layer**, not only at the full-body extraction layer.

## Current sources

- `/home/tomdean88/.openclaw/workspace/GMAIL_INBOX.md`
- `/home/tomdean88/.openclaw/workspace/MICROSOFT_INBOX.md`
- `/home/tomdean88/.openclaw/workspace/ASSISTANT_INBOX.md`
- both **Inbox** and **Sent Items** sections from those files
- `/home/tomdean88/.openclaw/workspace/WHATSAPP_RECENT.md`

## Core behavior

For every newly seen item:

1. decide whether it is an expense candidate
2. if not a candidate, mark it `not_needed`
3. if it is a candidate, do **not** let it disappear
4. try the full-body trusted reader route where available
5. if extraction succeeds, log the expense
6. if extraction fails or detail is insufficient, create a **pending expense signal** with an exact blocker
7. write/update closure state in `memory/monitored-items-state.json`

## State

Runtime state lives in:

- `~/.openclaw/runtime/expense-intake-watcher/state.json`
- `~/.openclaw/runtime/expense-intake-watcher/watcher.log`

State now tracks:

- `scanned_non_candidates`
- `item_states`
- `last_run`
- `last_summary`

This avoids the previous failure mode where blocked items were treated as fully done just because they had been seen once.

## Important design rule

The watcher is not allowed to silently drop a suspicious item.
Every candidate must end each pass as one of:

- logged
- duplicate
- pending with blocker
- not needed

## Readers used

- Microsoft: `/home/tomdean88/openclaw/pi-services/trusted-email-reader/read_email.py`
- Gmail: `/home/tomdean88/openclaw/pi-services/trusted-email-reader/read_gmail.py`

## Current limits

- full-body email extraction still depends on the trusted reader route succeeding
- WhatsApp can only create pending signals from the recent feed; it cannot inspect hidden media/audio without richer source access
- SharePoint evidence filing is still separate from this watcher

## Goal

Make expense capture fail-closed across email, outbox, and WhatsApp recent feed, so visible candidates become operational items immediately rather than passive messages.
