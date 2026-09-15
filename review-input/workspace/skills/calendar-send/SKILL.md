---
name: calendar-send
description: Create calendar events or Teams meetings after approved TOTP authorization, using the safe file-first route and confirming the resulting event details.
---

# Calendar Send

Use this skill whenever Tom wants a calendar event or Teams meeting created.

## Default behaviour
- Default to **creating a Teams meeting** unless Tom explicitly asks for in-person / no Teams
- Use the file-first pattern: write title and attendees to temp files, then run the exact documented command
- Never embed the title or attendee list directly in the shell command
- ALWAYS ask Tom which account/calendar to send the invite from before creating any event. Never assume the organiser account.

## Rules
- NEVER create external calendar invites without valid TOTP or an approved open gate
- ALWAYS ask which account/calendar the invite should come from before sending (e.g. assistant@ vs Tom@). Never assume.
- State the full event details before creating it:
  - title
  - organiser account
  - date/time
  - duration
  - attendees
  - Teams or no Teams
- **Participant-intent rule (MANDATORY):** when Tom describes attendees conversationally (e.g. "me and him", "us", "both of us"), convert that into a concrete attendee check before sending. Do not collapse the list to only the external attendee.
- **Fail-closed attendee rule:** before running the create-event command, explicitly verify that the final attendee file matches the participant set Tom asked for. If Tom said he should be on the invite and Tom is missing from the attendee set, stop and fix it before sending.
- **Tom-on-invite default:** if Tom asks to book a meeting that includes himself, include `tom@stackstoneconsulting.co.uk` on the attendee list unless he explicitly says not to.
- If a code was already pasted recently in chat, use it immediately instead of re-challenging Tom
- Do NOT improvise alternative calendar/invite routes
- Log every created invite to `memory/email_log.md` until a dedicated calendar log exists

## Temp files
Write these first with the `write` tool:
- `/tmp/oc-event-title.txt`
- `/tmp/oc-event-attendees.txt` (one email per line)

## Commands
### With Teams link (default — always use unless told otherwise)
```bash
python3 ~/.openclaw/integrations/microsoft-l1/create-event.py \
  --title-file /tmp/oc-event-title.txt \
  --attendees-file /tmp/oc-event-attendees.txt \
  --start "YYYY-MM-DDTHH:MM" \
  --duration 60
```

### Without Teams link
```bash
python3 ~/.openclaw/integrations/microsoft-l1/create-event.py \
  --title-file /tmp/oc-event-title.txt \
  --attendees-file /tmp/oc-event-attendees.txt \
  --start "YYYY-MM-DDTHH:MM" \
  --duration 60 \
  --no-teams
```

## Workflow
1. Confirm exact event details with Tom
2. Determine whether Teams is wanted (default yes)
3. Write title file and attendees file
4. Obtain valid 6-digit TOTP or use approved open gate
5. Run the exact documented command via exec
6. Verify the resulting event/invite details from the command output or readable result
7. Confirm success/failure to Tom
8. Log what was created

## Completion-not-detection rule (MANDATORY)
This skill is not complete when an event is merely proposed or the command is merely attempted.
Completion means the event/invite was actually created, or the pass failed closed with the exact blocker.

## Ambiguity / ask-Tom rule (MANDATORY)
If you are not materially certain about organiser account, attendee set, timing, duration, or Teams-vs-non-Teams intent, ask Tom a short clarification question instead of guessing.

## Failure rule
- If creation fails, treat it first as a command/path/interface problem before assuming TOTP failed
- Never invent wrapper commands or heredocs
- If blocked, report the exact command attempted

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
