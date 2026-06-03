---
name: google-auth
description: Re-authorize Google integrations on the Pi, especially Google Calendar and Gmail pollers. Use when Google Calendar or Gmail feeds are stale, token refresh fails, `token.json` / `gmail-token.json` is missing or revoked, or Tom says to run the Google auth skill. Default to the phone-first route when Tom is remote and not on the same network as the Pi.
---

# Google Auth

Use this skill for Google OAuth recovery on the Pi.

## Scope

- Google Calendar poller re-auth
- Gmail poller re-auth
- Token-missing / token-revoked recovery
- Stale Google feed recovery when the root cause is auth

## Default route

Prefer the **phone-first route** unless Tom is clearly local to the Pi and wants a different method.

## Phone-first Google Calendar route

1. Confirm the failing component from `reference/POLLERS.md` and the relevant log/output file.
2. If shell access is gated, ask Tom to open the gate first.
3. Start auth on the Pi:
   ```bash
   python3 /home/tomdean88/openclaw/attached_assets/integrations/google/poll-calendar-google.py --auth
   ```
4. Send Tom the Google consent URL printed by the script.
5. Have Tom complete consent on his phone and paste the full callback URL (`http://localhost:8765/...`) back into chat.
6. Complete the callback locally on the Pi by requesting that exact localhost URL.
7. Restart the service:
   ```bash
   systemctl --user restart openclaw-calendar-google.service
   ```
8. Verify completion:
   - service is running
   - `GOOGLE_CALENDAR.md` has a fresh `Last updated:` timestamp
   - log shows a successful update, not just token creation

## Key rule

Do **not** stop at “token saved”. The job is only complete once the poller/service is running again and the generated feed has actually refreshed.

## Files and commands

- Poller detail: `/home/tomdean88/.openclaw/workspace/reference/POLLERS.md`
- Durable route note: `/home/tomdean88/.openclaw/workspace/reference/OPENCLAW-ROUTES.md`
- Calendar auth helper: `/home/tomdean88/.openclaw/integrations/google/auth.py`
- Calendar poller: `/home/tomdean88/openclaw/attached_assets/integrations/google/poll-calendar-google.py`
- Calendar token: `/home/tomdean88/.openclaw/integrations/google/token.json`
- Gmail token: `/home/tomdean88/.openclaw/integrations/google/gmail-token.json`
- Calendar service: `systemctl --user status openclaw-calendar-google.service`
- Log: `/home/tomdean88/.openclaw/workspace/memory/poll-calendar-google-log.txt`

## Fail-closed checks

- If the token file is replaced but the service is not restarted, the fix is incomplete.
- If the service is running but `GOOGLE_CALENDAR.md` is still stale, the fix is incomplete.
- Treat pasted callback URLs as sensitive auth material; use them only to complete the local callback.
- If Tom is remote, do not default to SSH-tunnel instructions first; use the phone-first route.
