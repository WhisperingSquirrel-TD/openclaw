# Inbound Watch Router

_Last updated: 2026-06-15 10:05_

Canonical name for the Pi-native watch-layer router that reviews mirrored email + WhatsApp items, applies shared inbound routing flags, and gives expense signals the strongest fail-closed treatment.

## Naming / compatibility

The live code path still runs from the legacy directory:

- `/home/tomdean88/openclaw/pi-services/expense-intake-watcher/`

That path remains valid on purpose to avoid breaking the current systemd path and any existing operational muscle memory.

Use **Inbound Watch Router** as the durable conceptual/runtime name going forward.

Compatibility rules:

- legacy service/path names may continue to say `expense-intake-watcher`
- docs should describe that as the **legacy runtime path** for the broader inbound watch router
- runtime state is now written to both:
  - `~/.openclaw/runtime/inbound-watch-router/`
  - `~/.openclaw/runtime/expense-intake-watcher/`

## Scope

This is broader than expenses.
It currently performs watch-layer routing for:

- email inbox items
- email sent items
- WhatsApp recent-feed items

Primary flags:

- `ALERT`
- `FOLLOW_UP`
- `CRM`
- `OUTBOUND_CONTEXT`
- `EXPENSE`
- `DIARY`
- `IGNORE`

## Why the rename matters

`expense-intake-watcher` was structurally misleading once the watch layer started doing:

- non-expense classification
- CRM/state-change surfacing
- diary/follow-up detection
- WhatsApp routing
- closure-state proof support

The old name can stay as a compatibility shell, but the operating model is now a general inbound router with expense-first fail-closed behavior.
