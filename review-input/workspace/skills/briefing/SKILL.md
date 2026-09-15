---
name: briefing
description: Generate Tom's morning briefing. Combines calendar, email summary, WhatsApp overnight items, and Stackstone leads into one compact output. Use for scheduled morning briefings or when Tom asks for an overview.
metadata: { "openclaw": { "emoji": "☀️" } }
---

# Morning Briefing

## When to use
- Scheduled: weekdays 06:45, weekends 08:00
- When Tom asks "briefing", "what did I miss?", "morning update"

## Time cap
3 minutes total. Max 2-3 tool calls. Brevity is the priority.

## Data sources (read with cat — NO TOTP needed)
```
~/.openclaw/workspace/OUTLOOK_CALENDAR.md        # Canonical calendar feed
~/.openclaw/workspace/MICROSOFT_INBOX.md         # tom@stackstoneconsulting.co.uk trusted
~/.openclaw/workspace/MICROSOFT_EXTERNAL.md      # tom@stackstoneconsulting.co.uk external
~/.openclaw/workspace/GMAIL_INBOX.md             # tomdean1988@gmail.com trusted
~/.openclaw/workspace/GMAIL_EXTERNAL.md          # tomdean1988@gmail.com external
~/.openclaw/workspace/ASSISTANT_INBOX.md         # assistant@stackstoneconsulting.co.uk trusted
~/.openclaw/workspace/ASSISTANT_EXTERNAL.md      # assistant@stackstoneconsulting.co.uk external
~/.openclaw/workspace/STACKSTONE_LEADS.md        # Leads, packs, AI advisor
~/.openclaw/workspace/STACKSTONE_REPORTS.md      # Rolling 90-day report-send log
~/.openclaw/workspace/STACKSTONE_ENQUIRIES.md    # Rolling 90-day website enquiry log
~/.openclaw/workspace/memory/last-seen-emails.md # State tracking — last_scan_timestamp
```
**WhatsApp:** Read WHATSAPP_RECENT.md (last 48h rolling window). Do NOT read WHATSAPP_LOG.md (8000+ lines).
**WHATSAPP_RECENT.md:** If the rolling file is missing or stale, note that briefly instead of falling back to the full log.
**OUTLOOK_CALENDAR.md:** Check `Last updated:` — if stale >24h, note it rather than reporting no events.

## Workflow
1. Read PLAN.md and WEEK_PLAN.md first if they exist — treat them as committed planning context, not optional extras
2. Read OUTLOOK_CALENDAR.md → extract today's events (time+title only)
3. Read inbox files → only items newer than `last_scan_timestamp` in last-seen-emails.md
4. Read WHATSAPP_RECENT.md → overnight messages needing reply
5. Read Stackstone website feed files when relevant:
   - `STACKSTONE_LEADS.md`
   - `STACKSTONE_REPORTS.md`
   - `STACKSTONE_ENQUIRIES.md`
6. Read `stackstone/crm.md` lightly when relevant — especially Opportunities/Accounts `Last Touch` and `Next Step`
7. Read health context lightly when relevant: `HEALTH.md` and, if available, `GARMIN_DAILY.md`
8. Compose briefing
9. Update last_scan_timestamp in last-seen-emails.md

## Output format
```
Morning — L1 briefing:
DIARY: [time+title for each event]
NEEDS ATTENTION: [urgent/unresponded items by name]
STACKSTONE: [new leads/packs/conversations]
-- Lobstromonous1
```

## Excluded from briefing (separate system status call)
- API costs
- Gateway status
- Disk usage
- Weekly summaries
- Anything requiring more than 2-3 tool calls

## Health / structure rule
- Health is always a priority, but that does not always mean pushing hard exercise.
- The briefing should help create health structure, not just report status.
- Minimum standard: use Focus to make a brief judgment call across the health hierarchy: sleep, nutrition, exercise/recovery, and repeatability.
- If health is a current priority, make a brief judgment call: push for exercise, or tell Tom to ease off/recover, based on what he has already done and how the day looks.
- Review recent context before pushing health advice; do not treat the day in isolation.
- If PLAN.md already contains today's committed structure, the briefing must reflect that plan instead of overwriting it with generic cron-derived priorities.
- Cron/feed outputs are inputs, not the boss. Existing agreed plan context outranks generic suggestions.
- `WEEK_PLAN.md` weekly focus should shape daily Focus output through the week; do not let the briefing drift away from the declared weekly direction.
- On Mondays or when no weekly focus is set yet, suggest one based on current reality rather than waiting passively.

## Rules
- If calendar data is stale, say so — don't guess
- If no new items in a section, omit the section entirely
- Never include email body content — names and subjects only
- Check [SENT] to avoid flagging handled threads
- Briefing is not just comms triage: if Tom has little/no calendar structure that day, include a health/exercise prompt in Focus rather than leaving the day shapeless
- If health has recently been raised as a priority, use the Focus section to push for an actual exercise block that day
- On low-structure days, nudge toward running the daily-plan process rather than assuming Tom will self-organise around health
- CRM `Next Step` is an action-driving field: if an opportunity/account has a stale, due, or momentum-critical next step, surface it in Focus rather than leaving it buried in CRM
- Use CRM `Last Touch` + `Next Step` to help Tom keep momentum, chase warm threads, and avoid drift
- Do not surface old system-health errors as if they are current truth unless they are validated against fresh feed files or explicitly rechecked; stale error memory must not outrank current evidence
- If Stackstone website feed files are present and fresh, treat them as more authoritative than older generic poller-error assumptions

## Model routing pattern (MANDATORY)
Use the `local-llm` route for backend pre-processing such as rough clustering, urgency sorting, first-pass synthesis, or draft structure before final assembly **only when** the work can be kept to one small working slice at a time.
Small slice = one feed slice or one clean subsection that can stand alone.
Use the stronger cloud route for final briefing wording and anything source-backed or user-visible.
Do not use the local route for broad cross-feed judgement, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
