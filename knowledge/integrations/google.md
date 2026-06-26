# Integration: Google (Gmail OAuth & Google Tasks)

> Part of the OpenClaw knowledge base. Map: [`../../replit.md`](../../replit.md) · Knowledge index: [`../README.md`](../README.md).
> Related: [Integrations: Microsoft](./microsoft.md) · [WhatsApp watch actions](../whatsapp.md) · [Pi reference](../pi-reference.md)

## Google OAuth tokens (Gmail)

- Gmail tokens expire and can be revoked. If the poller logs `invalid_grant`, delete `gmail-token.json` and re-run the poller manually to trigger a fresh OAuth flow.
- Credential file naming: the install script expects `gmail-credentials.json` and `gmail-token.json`. Older setups may have `credentials.json` / `token.json` — copy and rename if needed.
- The Google Tasks integration (for WhatsApp watch actions) uses a separate token at `~/.openclaw/oauth/google/tasks-token.json` — different from Gmail.

Feed files, poller scripts and log locations are in [Pi reference](../pi-reference.md).

## Google Tasks (WhatsApp watch actions)

Used by the [WhatsApp watch action scanner](../whatsapp.md) "Add to list" button.

| File                                        | Purpose                                                              |
| ------------------------------------------- | -------------------------------------------------------------------- |
| `~/.openclaw/oauth/google/credentials.json` | Google OAuth app credentials (shared with Tasks + older Gmail setup) |
| `~/.openclaw/oauth/google/tasks-token.json` | Google Tasks OAuth token (separate from Gmail token)                 |
