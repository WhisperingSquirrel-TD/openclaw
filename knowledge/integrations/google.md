# Integration: Google (Gmail OAuth & Google Tasks)

> Part of the OpenClaw knowledge base. Map: [`../../replit.md`](../../replit.md) · Knowledge index: [`../README.md`](../README.md).
> Related: [Integrations: Microsoft](./microsoft.md) · [WhatsApp watch actions](../whatsapp.md) · [Pi reference](../pi-reference.md)

## Google OAuth tokens (Gmail)

- Gmail tokens expire and can be revoked. If the poller logs `invalid_grant`, run
  `python3 ~/.openclaw/integrations/google/gmail_poll.py --auth`, complete the
  phone-first localhost callback prompt, restart the Gmail service, and verify
  that the feed refreshes. Do not delete the existing token before a
  replacement succeeds.
- Credential file naming: the install script expects `gmail-credentials.json` and `gmail-token.json`. Older setups may have `credentials.json` / `token.json` — copy and rename if needed.
- The Google Tasks integration (for WhatsApp watch actions) uses a separate token at `~/.openclaw/oauth/google/tasks-token.json` — different from Gmail.

Feed files, poller scripts and log locations are in [Pi reference](../pi-reference.md).

## Google Calendar OAuth

If Calendar reports a missing, revoked, or stale token, run:

```bash
python3 ~/.openclaw/integrations/google/poll-calendar-google.py --auth
```

Open the printed Google consent URL on the phone and paste the complete
`http://localhost:8765/` callback into the waiting prompt. Restart
`openclaw-calendar-google.service` and verify the `GOOGLE_CALENDAR.md`
freshness marker and poller log before calling recovery complete.

## Google Tasks (WhatsApp watch actions)

Used by the [WhatsApp watch action scanner](../whatsapp.md) "Add to list" button.

| File                                        | Purpose                                                              |
| ------------------------------------------- | -------------------------------------------------------------------- |
| `~/.openclaw/oauth/google/credentials.json` | Google OAuth app credentials (shared with Tasks + older Gmail setup) |
| `~/.openclaw/oauth/google/tasks-token.json` | Google Tasks OAuth token (separate from Gmail token)                 |
