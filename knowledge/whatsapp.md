# WhatsApp Watch Mode & Action Scanner

> Part of the OpenClaw knowledge base. Map: [`../replit.md`](../replit.md).
> Related: [Security & control](./security.md) · [Integrations: Google](./integrations/google.md) (Tasks for watch actions) · [Pi reference](./pi-reference.md)

## Watch Mode

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

> Watch-mode data files are protected from the agent by the [exec denylist](./security.md#exec-security-denylist).

## Watch Action Scanner

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

Telegram cards have inline buttons: "Add to list" / "Ignore". Button callbacks update the action store and edit the card message. The "Add to list" path uses [Google Tasks](./integrations/google.md).
