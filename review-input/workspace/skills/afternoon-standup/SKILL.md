---
name: afternoon-standup
description: Tom's afternoon check-in at 13:45. Quick progress check + redirect if the day drifted. This is now part of the integrated standup system that covers both morning and afternoon contexts.
last_edited: 2026-07-08 15:30
reads_on_demand:
  - PLAN.md
  - WEEK_PLAN.md
  - TASKS.md
  - OUTLOOK_CALENDAR.md
  - GOOGLE_CALENDAR.md
  - MICROSOFT_INBOX.md
  - MICROSOFT_EXTERNAL.md
  - GMAIL_INBOX.md
  - WHATSAPP_RECENT.md
  - STACKSTONE_ENQUIRIES.md
  - GARMIN_DAILY.md
  - GARMIN_INTRADAY.md
  - reference/GARMIN-INTRADAY-POLLING.md
  - stackstone/crm.md
  - reference/CRM-NEXT-ACTION-SYSTEM.md
  - memory/last-seen-emails.md
assumes_loaded:
  - MEMORY.md
  - USER.md
---

# Afternoon Standup

## When
13:45 daily (cron)

## Purpose
Quick progress check + redirect if the day drifted.

**Answers:** Did those 3 things move, or do we need to redirect?

The afternoon standup is not just a fresh mini-briefing. Its core job is to check whether the morning plan actually advanced the weekly priorities and, if not, redirect the rest of the day toward the most important remaining move.

## Execution order
1. **Read current plan**
   - `PLAN.md` — what was committed this morning?
   - `WEEK_PLAN.md` (if exists) — what is the weekly objective and what are the 3 big things?
   - `TASKS.md` — read it as a focus-lane surface. Check which Revenue now, Revenue next, Offer/product, and admin-risk items were suggested this morning and which moved.
   - Explicitly identify which weekly big thing(s) today's plan was supposed to move
   - Check: did the suggested tasks from TASKS.md actually get done?
   - Do not reintroduce System-handled/Cleared items as active pressure unless a new failure has occurred.

2. **Action-state reconciliation gate (MANDATORY — before any named action or progress claim)**
   - Treat `PLAN.md`, CRM Next Steps and `TASKS.md` as candidate controls, not proof that work remains outstanding or did not move.
   - For every named task, follow-up, invoice, meeting or progress claim, check the freshest owning evidence in this order: current calendar/invite; current sent/inbound email or message thread; invoice tracker; SharePoint Current/dated artifact; CRM; TASKS/PLAN.
   - A newer accepted invite, booked meeting, outbound follow-up, closure/no-further-action message, paid/held invoice, or explicit future wait supersedes the older control. Suppress it; do not reframe it as an afternoon nudge.
   - If source evidence is stale, hidden, missing or contradictory, use `coverage incomplete`; do not claim that work did not move or turn an expired date into pressure.
   - Before delivery, run a contradiction pass over every surfaced action: if a newer source says scheduled, done, paid, closed, waiting or no action, remove/reclassify it and route control-record repair.

3. **Check for new urgent items** (since morning)
   - `MICROSOFT_INBOX.md`, `MICROSOFT_EXTERNAL.md`, `GMAIL_INBOX.md` — newer than last standup
   - `WHATSAPP_RECENT.md` — any new actionable messages since morning
   - `STACKSTONE_ENQUIRIES.md` — any new website enquiries since morning
   - `TASKS.md` — check whether any active focus-lane items still remain unaddressed from the morning view, especially Revenue now/current-client work, Revenue next/warm pipeline, Offer/product work, or due/overdue/admin-critical items. Ignore System-handled/Cleared rows unless a new failure makes them active again.
   - `stackstone/crm.md` — current Opportunities and Accounts rows if you are going to mention pipeline follow-ups by name
   - `reference/CRM-NEXT-ACTION-SYSTEM.md` — use this as the interpretation model for `Next Step` / next-action-date / owner / state
   - Treat CRM `Next Step` rows as reconciliation candidates, not automatic steering commitments; they may drive the standup only after the Action-state reconciliation gate passes. Check whether any warm named contacts/accounts/opportunities still have meaningful next steps that have not moved today.
   - If a row carries a same-day or overdue `Next action date`, explicitly say whether it moved today.
   - Use `last_scan_timestamp` from `memory/last-seen-emails.md` as cutoff

4. **Calendar check**
   - `OUTLOOK_CALENDAR.md` + `GOOGLE_CALENDAR.md` — any events added/changed since morning?
   - Anything starting in next 60 mins that needs prep?

5. **Re-check operating mode**
   - Read both `GARMIN_DAILY.md` and `GARMIN_INTRADAY.md` if available. The Garmin poller is expected to refresh same-day activity evidence before the afternoon standup; `GARMIN_INTRADAY.md` is the preferred source for current steps/active minutes/latest activity if it is fresher than `GARMIN_DAILY.md`.
   - Expected refresh pattern: pre-morning and pre-afternoon `GARMIN_DAILY.md` refreshes plus additive intraday polling for `GARMIN_INTRADAY.md` during the active day.
   - Specifically check whether Garmin now shows evidence of a morning movement session or newer activity since the morning standup (for example steps, active minutes, calories, or `Most Recent Activity`).
   - **Freshness-first rule (MANDATORY):** before concluding that the health move is still open, compare the timestamps on `GARMIN_DAILY.md` and `GARMIN_INTRADAY.md`. If neither has refreshed since the morning period, fail closed to `activity not yet Garmin-verified` rather than claiming the activity did not happen.
   - If Garmin clearly shows a completed workout/activity after the morning standup, count the health move as having moved even if chat context never mentioned it.
   - If Garmin still shows no credible activity evidence and the Garmin files are genuinely fresh for the afternoon window, treat the health move as still open and nudge it gently.
   - Decide whether Tom is now best served by:
     - **execution** — crack on with the work-list
     - **momentum** — nudge/push/creative unblock
     - **protection** — reduce scope / stop drift / protect energy
     - **push** — use the remaining day aggressively
   - Base this on what actually moved, current energy/strain, Garmin activity/recovery context, and whether the main revenue move is still alive

6. **Generate evening priorities**
   - If morning plan is on track → reinforce it
   - If morning plan drifted → suggest 2-3 redirect priorities for the evening
   - If new urgent items landed → surface them + reprioritise
   - Explicitly check whether the day has tipped into cognitive/emotional strain rather than productive difficulty; if so, consider a rhythmic-movement nudge before more work
   - If support mode is `execution`, be brief and sequential
   - If support mode is `momentum`, give a smaller next move plus one traction-creating / creative unlock
   - If support mode is `protection`, cut scope and contain admin/legal expansion
   - If support mode is `push`, make the remaining priorities more ambitious and direct
   - **Weekend non-work rule:** on weekends, default to not expanding work at all. Only surface truly urgent items or logistics unless Tom explicitly wants to work.
   - **Evening respect rule:** in the evening, default to containing work rather than expanding it. Only push if there is a genuinely urgent reason or Tom explicitly wants the push.

7. **Update state**
   - Update `last_scan_timestamp` in `memory/last-seen-emails.md`

## Output format
```
🕐 Afternoon Standup — [Day Date]

📋 MORNING PLAN
[What was committed this morning — including specific tasks from TASKS.md]

✅ PROGRESS CHECK
[What moved? What didn't? 
 - Did the weekly big thing(s) actually move?
 - Which suggested tasks from TASKS.md got done?
 - Which are still pending?]

🚨 NEW SINCE MORNING
[New urgent items if any — otherwise skip this section]

🧭 SUPPORT MODE
[execution / momentum / protection / push — with one short reason]

🎯 EVENING PRIORITIES
[2-3 specific tasks/actions for the rest of the day:
 - Unfinished tasks from TASKS.md that should still happen today
 - New urgent items
 - Next step to move weekly objective forward
 Be directive: name specific tasks, not vague intentions]

-- L1
```

## Rules / constraints
- **Time cap:** 2 minutes max
- **Not a full briefing:** Only flag NEW items since morning standup
- **Redirect, don't nag:** If something didn't happen, suggest what to do instead — don't just repeat the morning plan
- **Weekly-priority enforcement:** If the morning plan has drifted away from the weekly big things, explicitly call that out and steer the remainder of the day back toward the single most important weekly move unless a genuinely urgent item overrides it.
- **Admin-obligation enforcement:** If `TASKS.md` still contains a due/overdue or admin-critical item from the morning view (for example forms, filings, legal paperwork, or submissions), the afternoon standup must explicitly say whether it moved and, if not, whether it should be done today or consciously deferred.
- **Defined-campaign completion rule:** when new business is a stated priority and a concrete campaign/build path already exists (e.g. C4 landing page, outreach copy, target list, booking flow), the standup should push completion of that campaign backbone before suggesting looser prospecting activity.
- **Proactive stall detection:** if a named campaign/deliverable is still the clearest route to a current priority but has not moved by the afternoon, explicitly call out the stall and redirect the remainder of the day toward the next smallest meaningful step.
- **Skip empty sections:** If nothing new, don't say "nothing new" — just omit the section
- **Calendar prep:** If something starts <60 mins, flag it
- **Balance check:** If Tom has been working solidly since morning, suggest a short break or walk before the evening push
- **Health reminder:** If the morning plan included exercise and it hasn't happened yet, gently nudge it for the afternoon/evening slot
- **Garmin evidence rule (MANDATORY):** when Garmin is available and fresh, prefer Garmin evidence over silence in chat when deciding whether Tom actually did the morning activity. Do not say exercise "wasn't confirmed" if `GARMIN_DAILY.md` already shows a same-day workout or meaningful activity signal after the morning standup.
- **Garmin freshness honesty rule:** if Garmin is available but still not refreshed after the morning period, say activity status is not yet Garmin-verified rather than claiming it definitely did or did not happen.
- **Recent-outbound rule:** Before suggesting a chase/follow-up for a named contact/account, check whether Tom already emailed/messaged them recently. If he did, count that as movement and do not suggest another touchpoint yet unless there is a specific reason or agreed follow-up timing.
- **Sent-state distinction rule (MANDATORY):** If a named opportunity has both (a) a recent follow-up email/message from Tom and (b) a separate generated asset/send-state object (for example an AI briefing pack marked `generated_not_sent`), do not collapse those into one claim like "the next step hasn't landed" or "it still needs following up". Distinguish the layers explicitly:
  1. communication movement — did Tom already send the follow-up?
  2. asset/send-state movement — has the separate pack/proposal/document itself been sent yet?
  If the follow-up email already went out, count the opportunity as having moved even if the related asset remains unsent.
- **CRM-backing rule:** Before nudging Tom on named pipeline work, check the current Opportunities/Accounts rows in `stackstone/crm.md`, then validate them against fresher owning evidence. CRM last-touch and next-step fields are operational controls, not source truth when a later calendar, sent/inbound thread, tracker or SharePoint record exists.
- **Named-next-step continuity rule (MANDATORY):** if a strategically live named contact/account/opportunity still has a meaningful CRM next step by afternoon, explicitly say whether it moved today. If it did not move and still matters, redirect Tom toward it by name rather than replacing it with generic admin/work wording.
- **CRM-next-step quality rule:** if the current CRM next step is too vague to steer the afternoon standup (for example `awaiting reply`), treat that as a maintenance gap and say the row needs a clearer chase/nudge action rather than silently dropping the entity from guidance.
- **Next-action-date accountability rule (MANDATORY):** if the CRM row encodes `Next action date: today` or an overdue date, the afternoon standup must treat that row as a checkable commitment. It should not disappear behind softer wording like `still warm` or `keep an eye on it`.
- **Sent-items verification rule (MANDATORY):** When making a claim about whether a named opportunity/account "moved", "was followed up", or "is still unfinished", verify the recent sent-items layer as well as `stackstone/crm.md`. If a sent item exists within the relevant recent window, treat that as movement and phrase any remaining issue more narrowly (for example: "follow-up sent, pack still not sent") rather than implying no movement.

## Data source paths
```
~/.openclaw/workspace/PLAN.md
~/.openclaw/workspace/WEEK_PLAN.md
~/.openclaw/workspace/OUTLOOK_CALENDAR.md
~/.openclaw/workspace/MICROSOFT_INBOX.md
~/.openclaw/workspace/MICROSOFT_EXTERNAL.md
~/.openclaw/workspace/GMAIL_INBOX.md
~/.openclaw/workspace/WHATSAPP_RECENT.md
~/.openclaw/workspace/STACKSTONE_ENQUIRIES.md
~/.openclaw/workspace/memory/last-seen-emails.md
```

## Delivery resilience
- The primary afternoon standup must run in the main Telegram session, not through an isolated-agent announce handoff.
- A separate recovery check may run 30 minutes after the primary slot. It may re-run the primary once **only** when the primary run is absent, errored, or timed out.
- For a main-session primary run, `deliveryStatus: not-requested` is normal scheduler metadata, not a delivery failure. A completed `lastRunStatus: ok` must suppress recovery.
- Before a recovery run is forced, inspect both `lastRunStatus` and the primary run history. Force only if no successful primary run is recorded for that day's scheduled slot.
- Do not issue a duplicate standup when the primary completed successfully. Scheduler transport metadata is not proof of user receipt; the primary main-session output is the delivery record.

## Relationship to other crons
- **Complements:** Morning standup (07:00)
- **Does NOT replace:** Inbox watch crons (10:25 / 13:25 / 16:25 / 19:25) — those continue to run for known-contact alerting
- **Weekly context:** Uses `WEEK_PLAN.md` from Monday's weekly planning

## Model routing pattern (MANDATORY)
Use the `local-llm` route for backend pre-processing such as rough clustering, first-pass synthesis of new inputs, or draft redirect options before the final standup is written **only when** the work can be kept to one small working slice at a time.
Small slice = one feed slice or one clean subsection that can stand alone.
Use the stronger cloud route for final standup wording, redirect judgement, and any source-backed claims.
Do not use the local route for broad cross-feed judgement, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
