---
name: standup
description: Tom's integrated daily standup. Combines briefing + daily plan + progress check into one unified system that covers both morning and afternoon contexts.
last_edited: 2026-07-08 15:07
reads_on_demand:
  - SYSTEM_MAP.md
  - WEEK_PLAN.md
  - PLAN.md
  - TASKS.md
  - OUTLOOK_CALENDAR.md
  - GOOGLE_CALENDAR.md
  - MICROSOFT_INBOX.md
  - MICROSOFT_EXTERNAL.md
  - GMAIL_INBOX.md
  - GMAIL_EXTERNAL.md
  - ASSISTANT_INBOX.md
  - WHATSAPP_RECENT.md
  - STACKSTONE_LEADS.md
  - STACKSTONE_ENQUIRIES.md
  - GARMIN_DAILY.md
  - TRAINING_NOTES.md
  - GARMIN_INTRADAY.md
  - reference/HEALTH-TRAINING-DECISION-MODEL.md
  - reference/GARMIN-INTRADAY-POLLING.md
  - stackstone/crm.md
  - stackstone/partnerships.md
  - reference/CRM-NEXT-ACTION-SYSTEM.md
  - SHAREPOINT_INDEX.md
  - SYSTEM_HEALTH.md
  - memory/last-seen-emails.md
assumes_loaded:
  - MEMORY.md
  - USER.md
  - HEARTBEAT.md
  - HEALTH.md
---

# Integrated Standup

## When
07:00 daily (morning) and 13:45 daily (afternoon)

## Purpose
One unified standup system that serves both morning and afternoon contexts. This integrated approach combines the functions of:
- Morning briefing and planning  
- Daily plan creation and focus setting
- Afternoon progress check and redirection

**Answers:** What are the 3 things that matter TODAY? and Did those 3 things move, or do we need to redirect?

## Positioning anchor (MANDATORY)
Treat Stackstone’s current positioning as:
- **independent AI advisory + practical implementation**
- helping small and mid-market businesses **put AI to work inside the business**
- finding where AI genuinely adds value, **designing the process around it**, and **building practical systems teams can trust**
- maintaining the judgment to say when the right answer is **not AI**, but structured automation / deterministic workflow instead

When standups surface AI-relevant work, client angles, examples, or strategic steering, bias toward:
- practical implementation and working systems
- process/workflow design
- trust, auditability, approvals, and operational reality
- AI embedded into real business processes
- commercially useful examples of where deterministic automation beats AI

Do not drift back into generic AI-strategy or generic AI-news framing when a more operational/process-design interpretation is available.

## Integrated Execution Flow

### Morning Standup (07:00)
1. **System health check (CRITICAL)**
   - Check poller staleness for all critical feeds
   - Flag any stale feeds and alert Tom IMMEDIATELY
   - **Timestamp parsing rule:** do not assume every feed uses `Last updated:`. For `SHAREPOINT_INDEX.md`, use `Index refreshed:` as the authoritative freshness field and treat it as UTC unless the file explicitly says otherwise. Convert to the runtime timezone only for display, not for freshness math.
   - **Cycle-aware stale rule (MANDATORY):** for feeds with a known runtime cadence from `reference/CRONS.md` or `reference/POLLERS.md`, do not freehand staleness from raw age alone. Compare the file's last successful visible update against the feed's expected refresh cycle.
   - Known cadence anchors for standup freshness:
     - `STACKSTONE_LEADS.md` → user crontab `*/15 * * * *` Stackstone poller
     - `STACKSTONE_ENQUIRIES.md` → user crontab `*/2 * * * *` enquiry poller
     - `WHATSAPP_RECENT.md` → user crontab `*/15 * * * *` `whatsapp_recent.sh`
     - `GARMIN_DAILY.md` → user crontab `35 6 * * *` Garmin poller
   - If cadence is unknown, fall back to raw age thresholds.
   - Raw-age fallback thresholds:
     - OUTLOOK_CALENDAR.md: >2 hours = STALE
     - GOOGLE_CALENDAR.md: >2 hours = STALE
     - MICROSOFT_INBOX.md / MICROSOFT_EXTERNAL.md: >2 hours = STALE
     - GMAIL_INBOX.md / GMAIL_EXTERNAL.md: >2 hours = STALE
     - ASSISTANT_INBOX.md: >2 hours = STALE
     - STACKSTONE_LEADS.md: >4 hours = STALE
     - GARMIN_DAILY.md: >24 hours = STALE
     - WHATSAPP_RECENT.md: >2 hours = STALE
     - SHAREPOINT_INDEX.md: >30 mins = STALE
   - **Honesty rule:** if a feed is currently stale by cycle logic but later refreshes before Tom sees the standup, that means the stale alert was transient, not necessarily wrong. Phrase it as a missed-refresh issue, not a claim that the feed is generally broken.
   - **Acceptable-drift suppression rule (MANDATORY):** do not surface a feed issue in the standup just because one expected refresh cycle was missed or a file looks briefly stale. If the issue is still within the designed acceptable system window and there is no stronger evidence of persistent failure, keep it internal.
   - **Failure-threshold rule (MANDATORY):** only surface a system-health/feed issue to Tom when it looks like a real failure against system intent — for example the watcher/poller is disabled, repeated cycles are being missed beyond the acceptable window, coverage is materially incomplete for a revenue/operations-critical surface, or a blocked downstream dependency means the system can no longer do what it was built to do.
   - If a critical feed crosses that failure threshold, surface it at the TOP of the standup output

2. **Read planning context**
   - `WEEK_PLAN.md` (if exists) — what's the weekly objective?
   - **If weekly objective is missing and it's Monday:** Prompt Tom to set it before continuing with daily planning
   - **If weekly objective is missing mid-week:** Prompt Tom to set it when convenient (after standup)
   - `PLAN.md` — if it already contains explicit user-captured constraints/anchors for today (for example client times, dog walks, arrivals, or no-exercise notes added the night before), treat those as authoritative planning inputs for the standup rather than wiping them blindly
   - Only wipe/replace `PLAN.md` after you have extracted and preserved any same-day user-provided anchors from it
   - **User-captured-anchors rule:** when Tom has pre-loaded tomorrow's shape into `PLAN.md`, the standup must plan around those anchors, not overwrite them with a cleaner invented day

3. **Check capacity/recovery**
   - `GARMIN_DAILY.md` (if exists) — recovery score, HRV, sleep quality, resting HR
   - If `GARMIN_DAILY.md` has already refreshed for today before the standup, treat it as the preferred recovery source for the morning check-in.
   - **Same-day freshness gate (MANDATORY):** do not derive this morning's readiness/capacity prescription from a `GARMIN_DAILY.md` file whose heading/date or effective recovery values are still for yesterday.
     - Yesterday's Garmin daily file may be useful background only.
     - It is **not** allowed to drive language like `don't push it`, `recovery day`, `poor readiness`, or similar this morning unless there is a fresher same-day source backing that call.
   - **Fresh-source precedence order (MANDATORY):** for the morning standup, use recovery sources in this order:
     1. same-day `GARMIN_DAILY.md`
     2. same-day `GARMIN_INTRADAY.md` / live current-body-battery style Garmin source if available before standup
     3. a clearly-dated manual update from Tom referring to this morning / last night
     4. if none of the above exist, mark recovery as unverified and ask Tom for a quick manual check-in instead of making a confident push/caution recommendation
   - **No stale-caution rule (MANDATORY):** if no fresh same-day recovery source exists, fail closed to neutral/provisional wording. You may recommend a flexible health move, but you must not present a confident cautionary readiness judgment based on stale overnight data.
   - **Alcohol attribution rule:** If GARMIN_DAILY.md shows alcohol consumed, check the DATE of the entry. Only say "last night" if it was actually the previous evening. If it was 2+ nights ago, don't attribute recent poor recovery to it.
   - Use today's / last night's recovery data to drive today's plan
   - Before using stale/unavailable Garmin, check whether Tom has already provided a newer manual recovery update in day memory / current context
   - If a newer manual recovery update exists and it clearly refers to last night / this morning, use that instead of stale Garmin
   - If a manual recovery update exists but the date/time is unclear, ask Tom which night/morning it refers to before using it
   - If Garmin is stale/unavailable and no newer manual update exists, ask Tom manually for a short recovery update and use that in place of Garmin: sleep duration/quality, energy, soreness, alcohol, and anything notable
   - Record that manual update in the day memory so later standups/planning can reuse it
   - Use daily-plan recovery→mode mapping:
     - Strong recovery → deep work mode
     - Average → normal mode
     - Poor recovery → light mode, admin only
     - No data → ask Tom how he's feeling
   - **Recovery-prescription consistency rule (MANDATORY):** after summarising recovery + recent training load, choose ONE clear health prescription for today and keep it consistent across `📊 RECOVERY`, `🧭 TODAY'S OPERATING FRAME`, `📋 PLAN`, `📋 SUGGESTED TASKS`, and `🎯 CONCRETE NEXT MOVE`.
     - If today is a recovery / low-intensity day, prescribe only one of: walk, mobility, easy recovery run, or easy gym/strength session.
     - Do **not** mix `not a push day / recovery day` language with a second, harder or longer recommendation elsewhere in the same standup.
     - If strain/recovery cues argue against intensity but still support movement, fail closed to the lighter option and label it explicitly as recovery movement.

4. **Read operational feeds** (same as briefing skill)
   - `OUTLOOK_CALENDAR.md` + `GOOGLE_CALENDAR.md` — today's events from both calendars (time+title only)
   - `MICROSOFT_INBOX.md`, `MICROSOFT_EXTERNAL.md`, `GMAIL_INBOX.md` — newer than `last_scan_timestamp`
   - `WHATSAPP_RECENT.md` — last 48h only
   - **Inbound-already-actioned suppression rule (MANDATORY):** before surfacing any email/message under `📧 NEEDS ATTENTION`, check whether Tom already sent a later reply/meeting invite/follow-up in the same thread or to the same contact after the inbound item. If yes, suppress it from alerting unless there is a genuinely newer unanswered movement.
   - **Readable-truth rule (MANDATORY):** if an inbound item comes from a body-withheld mirror (`MICROSOFT_EXTERNAL.md`, `GMAIL_EXTERNAL.md`, LinkedIn notification mail, etc.), do not phrase it as `needs attention`, `reply waiting`, or `X replied` unless the visible source proves it is both new-to-Tom and not already actioned. If the body is withheld, fail closed to factual wording such as `message seen in mirror` / `message exists but content/action state unverified`.
   - `STACKSTONE_LEADS.md`, `STACKSTONE_ENQUIRIES.md` — new website activity
   - **`TASKS.md`** — MANDATORY: read the task list as a focus-lane surface, not a flat backlog. Prioritise in this order unless a hard deadline/risk overrides it: (1) Revenue now/current client work, (2) Revenue next/warm pipeline, (3) Offer/product building, (4) Operational/admin risk, (5) Personal/deferred. Surface any items that are:
     - in the Revenue now lane and still active/waiting/blocking
     - in the Revenue next lane and momentum-critical for new business
     - in Offer/product building and clearly supports near-term revenue
     - due today
     - overdue
     - due within 48 hours
     - legally/compliance/admin critical even if not perfectly dated
     - explicitly described as important paperwork/forms/submissions Tom has decided need doing
     - marked Waiting Tom / Operating / Selected / In task-system
     - **Do not resurface System-handled/Cleared rows as active work unless there is a new failure or Tom asks.**
   - **`stackstone/crm.md`** — MANDATORY: read the full Opportunities and Accounts tables as an active next-step system, using `reference/CRM-NEXT-ACTION-SYSTEM.md` as the interpretation model. Extract ALL Next Step entries and surface any that are:
     - due today or overdue
     - momentum-critical (warm opportunities that need chasing)
     - revenue-blocking (paid work waiting on Tom's action)
     - stale (Last Touch >7 days and Next Step still pending)
     - strategically live named threads Tom would reasonably expect L1 to keep on top of, even if not perfectly dated yet
     - carrying a same-day or overdue `Next action date` encoded in the row
   - **`stackstone/partnerships.md` — MANDATORY:** read the full partnerships control table alongside CRM. Extract every strategically live partnership/connector row with a due, overdue, stale, or momentum-critical next action and surface it by name in `🤝 WARM CONTACTS / NUDGES`; do not let partnership rows disappear merely because they are not in the CRM Opportunities/Accounts tables.
   - **Named-CRM follow-up rule (MANDATORY):** if a live CRM entity or partnership has a concrete next step and it materially serves Tom's current goals, the standup must either surface it explicitly by name or have a source-backed reason not to (for example it moved very recently, is intentionally waiting on an external date, or has been consciously deprioritised).
   - **CRM-stall detection rule (MANDATORY):** when a warm contact/account/opportunity has weak passive wording like `awaiting reply`, treat that as a prompt to ask whether a more useful chase/nudge/action should now be maintained. Do not let warm rows disappear from steering just because the next-step wording is vague.
   - **CRM/SharePoint drift enforcement:** if the standup finds stale CRM/SharePoint truth worth mentioning, do not stop at reporting it. You must either:
     1. fix it in the same run if safe/small,
     2. or create a same-day isolated agentTurn follow-up job to do the maintenance,
     3. or mark the exact blocker.
   - **Dated CRM claim rule:** if you mention a dated opportunity milestone from CRM (for example an F2F, call, workshop, or deadline), do not rely on a stale CRM row alone. Verify the date from a fresher source first — preferably calendar, then fresh SharePoint/current-note context. If you cannot verify it, mention the item without asserting the exact day/date.

5. **Plan fitness FIRST** (daily-plan rules)
   - Every day must include run, gym, or intentional recovery
   - Dog walk is baseline, NOT a fitness session
   - Morning is best slot (pre-10am). If blocked, find another slot — don't skip.
   - Run = minimum 1 hour block (run + shower)
   - If poor recovery: swap run for walk/strength. Don't skip entirely.
   - If 2+ days with no run/gym → flag it, make today a run day
   - **Alcohol:** Tom is cutting it out — include "No alcohol" in every plan

6. **Set the operating framework**
   - Explicitly choose:
     - **Day mode:** recovery / steady-execution / deep-work / admin-containment
     - **Support mode:** execution / momentum / protection / push
     - **Health move:** the one health/recovery action that gets protected first
     - **Revenue move:** the one money-moving block that must happen today
     - **Admin limit:** the maximum shape/time legal/admin is allowed to take
     - **Drift risk:** the most likely thing to steal the day if not contained
   - Use recovery, diary load, revenue pressure, and strain signals to set these
   - **Weekend non-work rule:** if it is Saturday or Sunday, default to non-work. Protect rest/social time/recovery unless Tom has explicitly chosen to work or there is a genuinely urgent reason not to.
   - Do not assign revenue/admin/work blocks on weekends just because open tasks exist.

7. **Generate Today's Focus (driven by TASKS.md + weekly objective)**
   - **MANDATORY: Read TASKS.md and extract by focus lane:**
     - Active Revenue now/current-client items
     - Active Revenue next/warm-pipeline items that can bring in new work
     - Offer/product-building items that support revenue
     - All items due today or overdue
     - All items due within 48 hours
     - Any admin/legal/compliance items Tom has flagged as important
     - Exclude System-handled/Cleared items from suggested work unless a new failure makes them active again
   - **MANDATORY: Check weekly objective from WEEK_PLAN.md:**
     - Which of the 3 big things should today advance?
     - What concrete tasks from TASKS.md serve that objective?
   - **Suggest specific tasks from TASKS.md that:**
     - Have approaching deadlines
     - Align with weekly objective
     - Are momentum-critical for revenue/pipeline
     - Have been sitting too long (added >7 days ago, not yet started)
   - One-sentence judgment call across:
     - Recovery state (from Garmin or manual update)
     - Calendar load
     - Momentum-critical work (CRM Next Steps)
     - Weekly objective (from WEEK_PLAN.md)
     - Strain signals from recent messages / inbox / day context
     - **Specific tasks from TASKS.md that should happen today**
   - **CRM-goal alignment rule (MANDATORY):** when Tom's goals are revenue, follow-up discipline, or business momentum, prefer the most commercially sensible CRM next steps over generic work labels. The standup should help Tom not forget who to chase, nudge, or move forward.
   - Balance rule: review recent effort + recovery BEFORE recommending more exercise
   - If Tom is already pushing hard or recovery is poor, explicitly recommend easing off
   - If strain signals are building and rhythmic movement is likely to help, say so plainly and position the movement as regulation, not just fitness
   - **Stale-but-strong recovery rule:** if the Garmin poller is stale but the latest usable manual/recent read still shows strong signals (e.g. high body battery, balanced HRV, low/normal resting HR, solid sleep score), do not default to vague caution framing just because the data is not same-day fresh. Treat it as a capable day unless there is a stronger contrary signal.
   - **Weekly-steering rule:** explicitly choose which of the week's 3 big things today is serving. Do not let the morning standup become a generic list of work; today's plan must clearly advance the weekly plan unless there is a genuinely urgent override.
   - **Concrete-revenue-path rule:** if Tom has already identified a specific campaign / offer / outreach asset as the route to new business (for example Campaign C4), prefer steering him toward finishing that concrete pipeline-building work over vaguer "do some business development" wording. Existing defined revenue machinery beats abstract prospecting intentions.
   - **Proactive resurfacing rule:** do not wait for Tom to remind you that a named campaign/deliverable exists. If a concrete strategic route is still unfinished and remains the clearest path to a weekly priority (e.g. more pipeline, more revenue, clearer offer), proactively bring it to the forefront in the standup even if it has gone quiet in the chat for a day or two.
   - **Stuck-route check:** when a named campaign/offer/deliverable exists in `WEEK_PLAN.md`, `PLAN.md`, or `TASKS.md`, ask: "Is this still the clearest route to the stated goal, and has it actually moved recently?" If yes to the first and no to the second, surface it explicitly today.
   - **Revenue-anchor carry-forward rule:** when `TASKS.md` contains a named revenue item whose action text explicitly says it is the concrete route to more pipeline/revenue, that item must override generic weekly wording in the standup until one of three things is true: (1) it is completed, (2) Tom explicitly deprioritises/replaces it, or (3) a more urgent revenue-critical item is source-backed that day. In that case, name the item directly in `🎯 TODAY'S FOCUS`, `🧭 Revenue move`, and `🎯 CONCRETE NEXT MOVE` rather than summarising it as general follow-up or biz-dev.
   - **Fail-closed revenue rule:** if the standup sees a named concrete revenue route in `TASKS.md` but cannot tell whether it is still active, do not silently generalise it away. Surface it as the default revenue move with an explicit note that it remains the standing concrete route unless Tom says otherwise.

8. **Build PLAN.md** (max 8 lines, bullet format)
   ```
   # Plan — [Day Date]
   - 🏃 [fitness session]
   - 🚫 No alcohol
   - [specific task from TASKS.md OR CRM Next Step — with clear action]
   - [specific task from TASKS.md OR CRM Next Step — with clear action]
   - [specific task from TASKS.md OR CRM Next Step — with clear action]
   - [any diary anchors worth flagging]
   ```
   **Task selection priority:**
   1. Due/overdue items from TASKS.md
   2. Tasks that serve weekly objective
   3. Momentum-critical CRM Next Steps
   4. Tasks added >7 days ago that haven't moved
   5. Admin/legal items Tom has flagged as important
   
   **Be directive:** Don't just list vague intentions like "follow up on leads" — name the specific task from TASKS.md or CRM like "Chase Stuart re: INV-074 date change" or "Finish AND Digital talk outline"
   - **Date-label rule:** `PLAN.md` is for today. If you include prep for a future event, label it explicitly in the bullet itself, e.g. `Prep for Oliver Longstaff meeting TOMORROW (Mon 11:30)`.
   - **No date collapse:** Never rewrite a tomorrow/future item as if it were today. Preserve the event day in both the standup output and `PLAN.md`.
   - **Correction handling trigger:** If Tom says an item is "not today", "tomorrow", "next week", or similar, check the date wording in `PLAN.md` before editing/removing the item. If the item was future-dated prep, fix the label rather than deleting it.
   - **Today-only output rule:** In the standup message itself, keep `📋 PLAN` to today-only actions. If a bullet is prep for a future event, either label it explicitly as future prep or move it out of the main "today" phrasing so the message does not read like the event is happening today.

9. **Create [TODAY] nudge crons if needed**
   - Max 4-5 nudges per day
   - Use safe slots only (see `reference/CRONS.md`)
   - Name pattern: `[TODAY] [description]`
   - `sessionTarget: main`, `deleteAfterRun: true`

10. **Update state**
    - Update `last_scan_timestamp` in `memory/last-seen-emails.md`

### Afternoon Standup (13:45)
1. **Read current plan and progress**
   - `PLAN.md` — what was committed this morning?
   - `WEEK_PLAN.md` (if exists) — what is the weekly objective and what are the 3 big things?
   - `TASKS.md` — read it as a focus-lane surface. Check which Revenue now, Revenue next, Offer/product, and admin-risk items were suggested this morning and which moved.
   - Explicitly identify which weekly big thing(s) today's plan was supposed to move
   - Check: did the suggested tasks from TASKS.md actually get done?
   - Do not reintroduce System-handled/Cleared items as active pressure unless a new failure has occurred.

2. **Check for new urgent items** (since morning)
   - `MICROSOFT_INBOX.md`, `MICROSOFT_EXTERNAL.md`, `GMAIL_INBOX.md` — newer than last standup
   - `WHATSAPP_RECENT.md` — any new actionable messages since morning
   - `STACKSTONE_ENQUIRIES.md` — any new website enquiries since morning
   - `TASKS.md` — check whether any active focus-lane items still remain unaddressed from the morning view, especially Revenue now/current-client work, Revenue next/warm pipeline, Offer/product work, or due/overdue/admin-critical items. Ignore System-handled/Cleared rows unless a new failure makes them active again.
   - `stackstone/crm.md` — current Opportunities and Accounts rows if you are going to mention pipeline follow-ups by name
   - `reference/CRM-NEXT-ACTION-SYSTEM.md` — use this as the interpretation model for `Next Step` / next-action-date / owner / state
   - Treat CRM `Next Step` rows as active steering commitments, not passive notes. Check whether any warm named contacts/accounts/opportunities still have meaningful next steps that have not moved today.
   - If a row carries a same-day or overdue `Next action date`, explicitly say whether it moved today.
   - Use `last_scan_timestamp` from `memory/last-seen-emails.md` as cutoff

3. **Calendar check**
   - `OUTLOOK_CALENDAR.md` + `GOOGLE_CALENDAR.md` — any events added/changed since morning?
   - Anything starting in next 60 mins that needs prep?

4. **Re-check operating mode**
   - Read `GARMIN_DAILY.md` if available and fresh enough to be useful for same-day activity/recovery context. The Garmin poller is expected to run at `35 6,13 * * *` via the same route as management-bot `/garmin` (`python3 ~/.openclaw/integrations/garmin/poll-garmin.py`), with the 13:35 run shortly before the 13:45 afternoon standup.
   - Specifically check whether Garmin now shows evidence of a morning movement session or newer activity since the morning standup (for example steps, active minutes, calories, or `Most Recent Activity`).
   - If Garmin clearly shows a completed workout/activity after the morning standup, count the health move as having moved even if chat context never mentioned it.
   - If Garmin still shows no credible activity evidence and the morning plan included exercise, treat the health move as still open and nudge it gently.
   - Decide whether Tom is now best served by:
     - **execution** — crack on with the work-list
     - **momentum** — nudge/push/creative unblock
     - **protection** — reduce scope / stop drift / protect energy
     - **push** — use the remaining day aggressively
   - Base this on what actually moved, current energy/strain, Garmin activity/recovery context, and whether the main revenue move is still alive

5. **Generate evening priorities**
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

6. **Update state**
   - Update `last_scan_timestamp` in `memory/last-seen-emails.md`

## Delivery integrity
- For morning standups delivered in a cron run, preserve it as the **Morning Standup**.
- For afternoon standups, deliver as **Afternoon Standup**.
- Do not rename/reframe it as a generic "morning view", "summary", or other casual label unless Tom explicitly asked for a shortened version.
- Default delivery behavior: forward the standup in its skill-defined structure (or clearly label it as a shortened standup if compression was explicitly requested).
- If you compress it for any reason, do not imply it is a different artifact from the standup.

## Output format
### Morning Standup:
```
☀️ Morning Standup — [Day Date]

🚨 SYSTEM HEALTH
[Only include this section if a feed/system has crossed the failure threshold — otherwise skip]
[List only real system failures, blocked critical coverage, or persistent integrity risks worth Tom knowing about]

📊 RECOVERY
[Garmin summary if available, or ask Tom how he's feeling]

📅 DIARY
[Today's events: time+title only]

📧 NEEDS ATTENTION
[Urgent/unresponded items by name only]

📈 STACKSTONE
[New leads/enquiries/packs if any]

🤝 WARM CONTACTS / NUDGES
[Always include when there are live commercial contacts to keep warm. Name 3-7 specific contacts/accounts from `stackstone/crm.md`, `stackstone/partnerships.md` if relevant, and `TASKS.md`, grouped by action type: Chase today / Keep warm this week / Watch only. Each named item needs a source-backed reason: stage, last touch, next step, or live event. Do not bury this inside generic "Suggested tasks".]

🎯 TODAY'S FOCUS
[One-sentence mode + priority recommendation]

🧭 TODAY'S OPERATING FRAME
- Mode: [day mode] / [support mode]
- Weekend note: [only include if relevant — make the lighter-touch/protection stance explicit]
- Health move: [single protected health/recovery move]
- Revenue move: [single money-moving block]
- Admin limit: [max admin/legal footprint]
- Drift risk: [main thing to contain]

📋 PLAN
[Bullet list from PLAN.md — max 8 lines]

✅ WEEKLY LINK
[Which of the 3 big things from WEEK_PLAN.md today is serving — be explicit]

📋 SUGGESTED TASKS (from TASKS.md + CRM)
[List 2-4 specific tasks that should happen today based on:
 - Deadlines (due today, overdue, or within 48h)
 - Weekly objective alignment
 - Momentum-critical CRM Next Steps
 - Long-stalled items (added >7 days ago)]

🎯 CONCRETE NEXT MOVE
[Name the exact campaign / asset / deliverable to move today if one already exists, e.g. "Finish C4 landing page copy" rather than "do some biz-dev"]

-- L1
```

### Afternoon Standup:
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
- **Morning time cap:** 3 minutes total
- **Afternoon time cap:** 2 minutes max
- **Brevity first:** Skip empty sections entirely
- **Fitness is non-negotiable:** Plan it FIRST, then fill work around it
- **Recovery drives mode:** Don't guess — use Garmin or ask Tom
- **Governing-path rule:** if a standup is being delivered, rewritten, verified, or converted into a user-facing message (including from a cron/sub-agent result), this skill still governs the final output. Do not treat the child result as a substitute for the skill process.
- **No light-forwarding shortcut:** For morning standup delivery, do not bypass this skill with a minimal "forward + quick diary check" path. The standup message must still be produced under this skill's rules, including CRM/SharePoint drift enforcement.
- **TASKS enforcement is MANDATORY:** Read `TASKS.md` every single standup and surface ALL non-code items that are due today, overdue, due within 48h, or clearly legal/admin/compliance critical. Do not quietly skip them because revenue work feels more strategic.
- **Admin-critical carry-forward rule:** if `TASKS.md` contains a committed paperwork/forms/submission item that Tom has already decided matters (for example Companies House forms), it must remain eligible for active reminder across refreshes until completed, explicitly deprioritised, or overtaken by a stronger same-day emergency.
- **CRM Next Steps are MANDATORY:** Read `stackstone/crm.md` every single standup and surface ALL Next Steps that are due/overdue/stale (Last Touch >7 days)/momentum-critical/revenue-blocking. Do not just mention a couple in passing — this is a systematic check of the full Opportunities and Accounts tables.
- **CRM-backing rule:** If you name a company/contact as a pipeline priority or suggest chasing/following up, that recommendation must be backed by the current CRM row (stage, last touch, next step). Do not generate named pipeline nudges from memory or vague session context.
- **Warm-contact section rule:** When the weekly objective includes revenue movement, networking, follow-up discipline, or warm pipeline, the standup must include `🤝 WARM CONTACTS / NUDGES` unless there are genuinely no live commercial contacts. It must explicitly separate: `Chase today`, `Keep warm this week`, and `Watch only / waiting`, so Tom can see who needs active nudging versus passive monitoring.
- **Contact temperature rule:** Rank warm contacts by practical commercial temperature, not just recency: current clients/revenue blockers first, then live opportunities with recent engagement, then strategic partners/events with dated next actions, then older relationship-maintenance nudges. Weak wording like `awaiting reply` should not hide a warm contact; decide whether it is chase/warm/watch and say so.
- **Next-action-date steering rule (MANDATORY):** when CRM rows encode `Next action date`, use that field as the primary steering date for warm-contact ranking. `Today/overdue` rows belong in `Chase today`; rows due within the next few days belong in `Keep warm this week`; true external waits with later review dates belong in `Watch only / waiting`.
- **Important-things balance rule:** the standup must hold both categories at once: (1) the clearest revenue route, and (2) due/overdue important obligations from `TASKS.md`. Do not let one erase the other.
- **Weekly focus drives daily priorities:** Don't drift away from the declared weekly direction
- **No double-alerting:** If Tom already replied to an email thread, don't surface it again
- **Calendar staleness:** If `OUTLOOK_CALENDAR.md` is stale >24h, flag it instead of reporting no events
- **Google Calendar re-auth recovery rule:** If `GOOGLE_CALENDAR.md` is stale and the evidence points to the known Google token/auth failure path (for example token missing, invalid_grant, or log instructions to re-authorise), do not stop at reporting staleness. If Tom opens the gate / gives approval for shell actions, initiate the re-auth flow yourself by running `python3 ~/.openclaw/integrations/google/poll-calendar-google.py --auth`, give Tom the generated auth URL, complete the callback if he sends it back, restart `openclaw-calendar-google.service`, and verify `GOOGLE_CALENDAR.md` updates again before claiming recovery. If approval/gate is not available, give Tom the exact re-auth steps rather than a generic stale warning.
- **Source-backing rule:** Every specific meeting/task claim in the standup must be traceable to a current source (`OUTLOOK_CALENDAR.md`, `GOOGLE_CALENDAR.md`, `PLAN.md`, `WEEK_PLAN.md`, `TASKS.md`, or `stackstone/crm.md`). If a specific item is not source-backed, exclude it or label it explicitly as unverified instead of stating it as fact.
- **Meeting-vs-logistics rule:** Do not collapse meeting logistics into a completed conversation. If the source only shows emails, WhatsApp scheduling, room bookings, or calendar holds, describe it as logistics / meeting arranged. Only say a conversation/meeting "happened", "was held", or ask Tom to capture its outcome when there is source-backed evidence that the meeting actually occurred (e.g. calendar event in the past plus outcome evidence, meeting summary, or Tom explicitly saying it happened).
- **WhatsApp scope:** Read `WHATSAPP_RECENT.md` only (last 48h rolling window), never the full log
- **Health hierarchy:** Sleep → nutrition → exercise/recovery → repeatability
- **Balance check:** Review recent context before pushing hard exercise — don't treat the day in isolation
- **Weekend non-work rule:** on weekends, default to not expanding work at all. Only surface truly urgent items or logistics unless Tom explicitly wants to work.
- **Evening respect rule:** in the evening, default to containing work rather than expanding it. Only push if there is a genuinely urgent reason or Tom explicitly wants the push.

## Monday special case
On Mondays, also read/create `WEEK_PLAN.md`:
- What is the weekly focus? (single top-level direction)
- What are the 3 big things this week?
- Any fixed commitments (meetings, travel, social)?
- What are the planned exercise sessions this week? (specific slots)
- Job search / business-dev actions this week?
- Which warm opportunities matter this week?
- Is sleep protection likely to be an issue any evening?

Max 10 lines. This becomes context for daily standups all week.

## Data source paths
All readable via `cat` (no TOTP needed):
```
~/.openclaw/workspace/OUTLOOK_CALENDAR.md
~/.openclaw/workspace/MICROSOFT_INBOX.md
~/.openclaw/workspace/MICROSOFT_EXTERNAL.md
~/.openclaw/workspace/GMAIL_INBOX.md
~/.openclaw/workspace/WHATSAPP_RECENT.md
~/.openclaw/workspace/STACKSTONE_LEADS.md
~/.openclaw/workspace/STACKSTONE_ENQUIRIES.md
~/.openclaw/workspace/GARMIN_DAILY.md
~/.openclaw/workspace/stackstone/crm.md
~/.openclaw/workspace/WEEK_PLAN.md
~/.openclaw/workspace/PLAN.md
~/.openclaw/workspace/memory/last-seen-emails.md
```

## Relationship to other crons
- **Replaces:** Daily briefing (06:25) + Daily plan (06:30) + Afternoon standup (13:45)
- **Complements:** Inbox watch crons (10:25 / 13:25 / 16:25 / 19:25) — those continue to run for known-contact alerting
- **Weekly context:** Weekly focus prompt (Mon 05:35), Weekly AI briefing (Mon 07:00)
- **Cleanup:** End-of-day cleanup (22:00) wipes PLAN.md and deletes [TODAY] crons

## Model routing pattern (MANDATORY)
Use the `local-llm` route for backend pre-processing such as rough clustering, first-pass synthesis of inputs, or draft plan structure before the final standup is written **only when** the work can be kept to one small working slice at a time.
Small slice = one feed slice or one clean subsection that can stand alone.
Use the stronger cloud route for final standup wording, priority judgement, and any source-backed claims.
Do not use the local route for broad cross-feed judgement, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Mandatory end-of-use review *(Updated: 2026-07-08 15:07)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".