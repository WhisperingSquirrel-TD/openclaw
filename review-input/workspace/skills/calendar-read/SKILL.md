---
name: calendar-read
description: Read calendar data with exact date, weekday, time, ordering, and timezone integrity before mentioning events or schedule claims.
last_edited: 2026-06-09 15:17
---

# Calendar Read

Use this skill whenever a reply will mention:
- a calendar event
- a day of week tied to a date
- a date tied to an event
- a time tied to an event
- wording like "today", "tomorrow", "this Thursday", "Friday 12 June"

## Purpose
Treat calendar data as high-integrity operational data.
Do not paraphrase from memory.

## Source order
1. `OUTLOOK_CALENDAR.md`
2. `GOOGLE_CALENDAR.md`
3. only then other corroborating sources if needed

## Process
1. Read the relevant calendar source entry directly.
2. Copy the ISO date/time exactly from source into working notes.
3. Convert UTC to Europe/London when presenting times from `OUTLOOK_CALENDAR.md`.
4. Verify weekday from the ISO date before stating it.
   - Preferred: inline date-offset reasoning from today's verified date
   - If needed, use Python date logic outside exec reasoning flow
   - If still not confident, fail closed to date-only wording rather than guessing the weekday
5. Build the final phrase from the verified pair:
   - date from source
   - weekday from verification
   - time from converted source
6. Final cross-check before replying:
   - does weekday match the source date?
   - does the date number match the source date?
   - does the time match the converted source time?
   - am I mixing details from two different events?
7. If any element is uncertain, fail closed:
   - state date only, or
   - state time only with explicit uncertainty, or
   - ask Tom a short clarification

## Hard rules
- Never write calendar details from memory after reading them.
- Never trust a cron/subagent's day-name claim without checking the source entry.
- Never collapse two nearby events into one summary line without checking both entries.
- If the event source is stale, say that instead of bluffing.

## Output discipline
Good:
- "Friday 12 June, 08:30–13:00"
- "12 June at 08:30 BST"

Bad:
- "Thursday 12 June" when weekday wasn't verified
- "Friday 13 June" after verifying a different date
- "tomorrow" unless the target date was explicitly checked against today

## Fail-closed trigger
If Tom could reply "that date/day/time is wrong," this skill should have been used.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".