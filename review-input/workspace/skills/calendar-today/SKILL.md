---
name: calendar-today
description: Get today's calendar events from all calendars. Use for morning briefings, pre-meeting prep, or when Tom asks what's on today. Returns time+title only — compact output.
metadata: { "openclaw": { "emoji": "📅" } }
---

# Calendar Today

## When to use
- Morning briefing
- When Tom asks "what's on today?" or "any meetings?"
- Pre-meeting prep (check what's coming in next hour)
- Calendar conflict detection

## Calendar files (read with cat or read tool — NO TOTP needed)
```
~/.openclaw/workspace/OUTLOOK_CALENDAR.md   # Work / Outlook feed
~/.openclaw/workspace/GOOGLE_CALENDAR.md    # Gmail / Google calendar feed
```
**Staleness check:** Always read the `Last updated:` line first. If either calendar feed is >24h old, note that rather than treating absence as proof of no events.

## Workflow
1. Read both OUTLOOK_CALENDAR.md and GOOGLE_CALENDAR.md
2. When Tom asks about "today", "tomorrow", or whether a meeting exists, check both feeds before answering
3. Filter to the requested date
4. Merge and sort by time
5. Flag conflicts (overlapping times)
6. Return compact list

## Output format
```
TODAY [date]:
[HH:MM] [Title]
[HH:MM] [Title]
⚠ CONFLICT: [event1] overlaps [event2]
No events today: ✓
```

## Rules
- Time + title only — no descriptions, no attendees, no locations unless asked
- Flag events starting within 60 minutes as imminent
- When Tom says "calendar" without specifying provider, assume he means the combined calendar view across both Outlook and Google.
- Do not answer calendar-presence questions from one feed alone if a second calendar feed exists.
- Never write to Tom's Google Calendar
- Never write to Tom's personal Outlook calendar
- Calendar writes only via L1's Outlook (TOTP required)

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
