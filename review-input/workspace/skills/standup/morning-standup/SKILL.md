---
name: morning-standup
description: Tom's focused morning standup. Combines briefing + daily plan + capacity check into ONE check-in at 07:00. Replaces separate briefing and plan crons. Answers "What are the 3 things that matter TODAY?"
last_edited: 2026-05-23 18:29
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

# Morning Standup

## When
06:30 daily (cron)

## Purpose
One focused morning check-in that replaces separate briefing + plan crons.

**Answers:** What are the 3 things that matter TODAY?

## Scheduled-delivery integrity (MANDATORY)
A cron run that produces a standup, or is marked `delivered`, is **not** proof that Tom received it in Telegram. For scheduled standups:
- treat the cron run record as execution evidence only;
- where delivery is routed through an isolated-run completion/announce path, treat that handoff as **delivery unverified** until a Telegram outbound-delivery record proves the message was sent;
- if the run took materially longer than its scheduled window, or delivery proof is unavailable, do not silently rely on the scheduled output: surface the standup through the active direct session when possible and flag the delivery path as an incident rather than claiming success;
- incident diagnosis must inspect the cron run record, gateway/outbound Telegram logs, and the actual user receipt before closing the issue.
- **Receipt-gated recovery (MANDATORY):** at the 07:35 recovery check, accept the 06:30 standup only when the Telegram outbound-delivery record shows a message containing `☀️ Morning Standup —` for that date. A successful cron run, an announce/completion event, or a generated standup artifact is not a receipt. If that record is absent or inaccessible, force the primary job once; if forcing is unavailable, render the full skill-format standup directly in the active user session and log the delivery path as `coverage incomplete`. Never substitute a shortened recovery summary for the standup.
- **Quiet-hours non-override:** the 06:30 scheduled standup is a user-facing delivery, not a heartbeat/no-op. A general quiet-hours policy must never be treated as permission to suppress it. If the primary run is skipped, timed out or errored, the recovery trigger must force one bounded retry outside the quiet window and suppress the retry only when the primary run is already proven successful.

## Positioning anchor (MANDATORY)
Treat Stackstone’s current positioning as:
- **independent AI advisory + practical implementation**
- helping small and mid-market businesses **put AI to work inside the business**
- finding where AI genuinely adds value, **designing the process around it**, and **building practical systems teams can trust**
- maintaining the judgment to say when the right answer is **not AI**, but structured automation / deterministic workflow instead

When the standup surfaces AI-relevant work, examples, nudges, or strategic direction, bias toward:
- practical implementation and working systems
- process/workflow design
- trust, auditability, approvals, and operational reality
- AI embedded into real business processes
- commercially useful examples of where deterministic automation beats AI

Do not drift back into generic "AI strategy" or generic AI-news framing when a more operational/process-design interpretation is available.

## Integration with existing skills
This skill **consolidates** the content from:
- `skills/briefing/SKILL.md` — email/WhatsApp/calendar/leads triage
- `skills/daily-plan/SKILL.md` — fitness-first planning, recovery check, health hierarchy

It does **not** duplicate them. It calls the same data sources and follows the same rules, but delivers them as ONE unified check-in.

## Execution order
1. **System health check (CRITICAL)**
   - Check poller staleness for all critical feeds
   - Read the authoritative freshness timestamp from each file and compare to current time
   - Flag any stale feeds and alert Tom IMMEDIATELY
   - **Timestamp parsing rule:** do not assume every feed uses `Last updated:`. For `SHAREPOINT_INDEX.md`, use `Index refreshed:` as the authoritative freshness field and treat it as UTC unless the file explicitly says otherwise. Convert to the runtime timezone only for display, not for freshness math.
   - If a freshness field is recent but another nearby timestamp/line is older or differently formatted, prefer the file's explicit authoritative refresh field rather than guessing from surrounding text
   - **Cycle-aware stale rule (MANDATORY):** for feeds with a known runtime cadence from `reference/CRONS.md` or `reference/POLLERS.md`, do not freehand staleness from raw age alone. Compare the file's last successful visible update against the feed's expected refresh cycle.
   - Treat a feed as stale only when at least one expected refresh cycle has actually been missed beyond a small grace window. If the next expected cycle has not yet been missed, do not over-report it as stale just because the raw age looks large.
   - Known cadence anchors for standup freshness:
     - `STACKSTONE_LEADS.md` → user crontab `*/15 * * * *` Stackstone poller
     - `STACKSTONE_ENQUIRIES.md` → user crontab `*/2 * * * *` enquiry poller
     - `WHATSAPP_RECENT.md` → user crontab `*/15 * * * *` `whatsapp_recent.sh`
     - `GARMIN_DAILY.md` → user crontab `35 6 * * *` Garmin poller
   - If cadence is unknown, fall back to the raw age thresholds below.
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
   - **Partial-sync Garmin rule (MANDATORY):** if same-day Garmin files have partially refreshed but core recovery fields are mostly blank or internally mixed (for example: body battery/stress present but sleep, HRV, readiness, steps, or current body battery are missing), treat the Garmin state as potentially out of sync rather than a clean low-readiness signal.
     - In that case, explicitly cross-check `GARMIN_DAILY.md` against `GARMIN_INTRADAY.md` timestamps and overlapping fields before making a recovery call.
     - If the files share the same refresh time but still show a fragmented state, fail closed to `Garmin partial / possibly out of sync` wording and avoid directional claims like `not a push day`, `poor recovery`, or `steady-not-pushy` unless a second source clearly supports them.
     - Allowed output in that state: factual description of what is present/missing + a neutral/flexible health suggestion.
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

3. **Action-state reconciliation gate (MANDATORY — before operational recommendations)**
   - Treat CRM `Next Step` fields and `TASKS.md` rows as **candidate controls**, not proof that an action remains outstanding.
   - For every candidate diary claim or named action (meeting, chase, follow-up, delivery, invoice, billing route, task), first check the freshest owning evidence in this order:
     1. exact current calendar/invite entry;
     2. current sent/inbound email or message thread;
     3. invoice tracker for invoice/payment claims;
     4. current SharePoint `Current.md` / dated artifact cache;
     5. local CRM control row;
     6. `TASKS.md`.
   - A newer accepted invitation, booked meeting, outbound follow-up, closure email, paid/held invoice state, or explicit customer wait instruction **supersedes** an older CRM/task action. Suppress the stale action; do not restate it as a suggestion.
   - Never manufacture a diary absence or meeting timing from CRM/task text. Only the calendar/invite source can establish a diary event or its date/time.
   - If the owning evidence is missing, stale, body-hidden, contradictory or otherwise cannot settle whether the action remains live, classify it as `coverage incomplete`. Do not turn an expired CRM date into an instruction.
   - Before final output, run a contradiction pass over every surfaced action: `Does any newer source show this is scheduled, done, paid, closed, waiting until a future date, or explicitly no action?` If yes, remove/reclassify it and repair the local CRM/task control through the governing CRM route.
   - Specific suppression rules:
     - accepted/secured Teams slot → never recommend a further slot chase;
     - explicit no-further-action/customer-will-ask → never assign prep, scope, configuration or follow-up work;
     - paid/hold/auto-chase-disabled invoice → never surface billing action;
     - recent sent chase → never recommend another chase without fresh evidence or an explicit new review date;
     - future-dated waiting contact → watch only until its review date or new inbound evidence.

4. **Read operational feeds** (same as briefing skill)
   - `OUTLOOK_CALENDAR.md` + `GOOGLE_CALENDAR.md` — today's events from both calendars (time+title only)
   - **Calendar-integrity rule (MANDATORY):** before writing any event time/date/day wording into `📅 DIARY`, `📋 PLAN`, `🎯 TODAY'S FOCUS`, or `🎯 CONCRETE NEXT MOVE`, read and apply `skills/calendar-read/SKILL.md` in the same run. Treat calendar mentions as high-integrity operational output, not loose summary text.
   - **Standup diary final-check (MANDATORY):** for every surfaced diary event, verify the exact source entry, convert Outlook UTC times to Europe/London, and fail closed to date-only wording if any time conversion or event mapping is uncertain.
   - `MICROSOFT_INBOX.md`, `MICROSOFT_EXTERNAL.md`, `GMAIL_INBOX.md` — newer than `last_scan_timestamp`
   - `WHATSAPP_RECENT.md` — last 48h only
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
   - **`stackstone/crm.md`** — MANDATORY: read the full Opportunities and Accounts tables as an active next-step system, using `reference/CRM-NEXT-ACTION-SYSTEM.md` as the interpretation model. Extract ALL Next Step entries as reconciliation candidates, then surface only the entries that pass the Action-state reconciliation gate and are:
     - due today or overdue
     - momentum-critical (warm opportunities that need chasing)
     - revenue-blocking (paid work waiting on Tom's action)
     - stale (Last Touch >7 days and Next Step still pending)
     - strategically live named threads Tom would reasonably expect L1 to keep on top of, even if not perfectly dated yet
     - carrying a same-day or overdue `Next action date` encoded in the row
   - **Named-CRM follow-up rule (MANDATORY):** if a live CRM entity has a concrete next step and it materially serves Tom's current goals, the standup must either surface it explicitly by name or have a source-backed reason not to (for example it moved very recently, is intentionally waiting on an external date, or has been consciously deprioritised).
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

## Delivery integrity
- If this standup is generated in a child/cron run and later relayed to Tom, preserve it as the **Morning Standup**.
- Do not rename/reframe it as a generic "morning view", "summary", or other casual label unless Tom explicitly asked for a shortened version.
- Default delivery behavior: forward the standup in its skill-defined structure (or clearly label it as a shortened standup if compression was explicitly requested).
- If you compress it for any reason, do not imply it is a different artifact from the standup.

## Output format
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

## Rules / constraints
- **Time cap:** 3 minutes total
- **Brevity first:** Skip empty sections entirely
- **Fitness is non-negotiable:** Plan it FIRST, then fill work around it
- **Recovery drives mode:** Don't guess — use Garmin or ask Tom
- **Governing-path rule:** if a morning standup is being delivered, rewritten, verified, or converted into a user-facing message (including from a cron/sub-agent result), this skill still governs the final output. Do not treat the child result as a substitute for the skill process.
- **No light-forwarding shortcut:** for morning standup delivery, do not bypass this skill with a minimal "forward + quick diary check" path. The standup message must still be produced under this skill's rules, including CRM/SharePoint drift enforcement.
- **TASKS enforcement is MANDATORY:** Read `TASKS.md` every single standup and surface ALL non-code items that are due today, overdue, due within 48h, or clearly legal/admin/compliance critical. Do not quietly skip them because revenue work feels more strategic.
- **Admin-critical carry-forward rule:** if `TASKS.md` contains a committed paperwork/forms/submission item that Tom has already decided matters (for example Companies House forms), it must remain eligible for active reminder across refreshes until completed, explicitly deprioritised, or overtaken by a stronger same-day emergency.
- **CRM Next Steps are MANDATORY candidates, not automatic actions:** Read `stackstone/crm.md` every single standup and review all Next Steps that are due/overdue/stale (Last Touch >7 days)/momentum-critical/revenue-blocking. Surface only those that pass the Action-state reconciliation gate: an expired CRM date is never sufficient on its own. Record or repair a contradicted local control rather than recommending it.
- **CRM-backing rule:** If you name a company/contact as a pipeline priority or suggest chasing/following up, that recommendation must be backed by the current CRM row (stage, last touch, next step). Do not generate named pipeline nudges from memory or vague session context.
- **Follow-up-governance rule (MANDATORY):** when the standup is about to recommend a named chase/nudge/follow-up, read and apply `skills/crm-follow-up/SKILL.md` at the point of choosing that action, not afterwards.
- **Warm-contact section rule:** When the weekly objective includes revenue movement, networking, follow-up discipline, or warm pipeline, the standup must include `🤝 WARM CONTACTS / NUDGES` unless there are genuinely no live commercial contacts. It must explicitly separate: `Chase today`, `Keep warm this week`, and `Watch only / waiting`, so Tom can see who needs active nudging versus passive monitoring.
- **Contact temperature rule:** Rank warm contacts by practical commercial temperature, not just recency: current clients/revenue blockers first, then live opportunities with recent engagement, then strategic partners/events with dated next actions, then older relationship-maintenance nudges. Weak wording like `awaiting reply` should not hide a warm contact; decide whether it is chase/warm/watch and say so.
- **Context-before-chase rule (MANDATORY):** before surfacing any named follow-up/chase in the standup, check for source-backed context that makes a nudge inappropriate right now — for example recent meaningful movement, an explicit external wait, temporary leave/absence, a stated review date, or lack of an actual relationship path to the proposed person. If that context exists, fail closed to `Keep warm later` or `Watch only / waiting` instead of inventing a chase just because the thread is commercially live.
- **Next-action-date steering rule (MANDATORY):** when CRM rows encode `Next action date`, use that field as the primary steering date for warm-contact ranking. `Today/overdue` rows belong in `Chase today`; rows due within the next few days belong in `Keep warm this week`; true external waits with later review dates belong in `Watch only / waiting`.
- **No-relationship-route rule (MANDATORY):** do not suggest `reach out to X instead` unless the source-backed context shows Tom actually has a sensible relationship path to that person or the CRM/task notes explicitly say that alternate contact is the intended route. If the named primary contact is unavailable and no valid alternate route is evidenced, default to leave it alone.
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
- **Replaces:** Daily briefing (06:25) + Daily plan (06:30)
- **Complements:** Afternoon standup (13:45)
- **Weekly context:** Weekly focus prompt (Mon 05:35), Weekly AI briefing (Mon 07:00)
- **Cleanup:** End-of-day cleanup (22:00) wipes PLAN.md and deletes [TODAY] crons

## Model routing pattern (MANDATORY)
Use the `local-llm` route for backend pre-processing such as rough clustering, first-pass synthesis of inputs, or draft plan structure before the final standup is written **only when** the work can be kept to one small working slice at a time.
Small slice = one feed slice or one clean subsection that can stand alone.
Use the stronger cloud route for final standup wording, priority judgement, and any source-backed claims.
Do not use the local route for broad cross-feed judgement, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
