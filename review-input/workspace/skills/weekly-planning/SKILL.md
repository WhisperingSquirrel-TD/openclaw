---
name: weekly-planning
description: Tom's weekly planning session. Sets the week BEFORE Monday starts. Creates/updates WEEK_PLAN.md with top-level focus + 3 big things + exercise plan. Runs Sunday evening at 20:00.
last_edited: 2026-05-23 18:29
reads_on_demand:
  - WEEK_PLAN.md
  - OUTLOOK_CALENDAR.md
  - GOOGLE_CALENDAR.md
  - GARMIN_DAILY.md
  - GARMIN_ARCHIVE.md
  - stackstone/crm.md
  - TASKS.md
  - BACKLOG.md
assumes_loaded:
  - MEMORY.md
  - USER.md
---

# Weekly Planning

## When
Sunday 20:00 (cron)

## Purpose
Set the week BEFORE Monday starts.

**Output:** `WEEK_PLAN.md` with clear weekly focus + priorities + exercise plan

## Execution order
1. **Read last week's plan** (if exists)
   - `WEEK_PLAN.md` — what was the focus last week?
   - What moved? What didn't?

2. **Read operational context**
   - `OUTLOOK_CALENDAR.md` — what's fixed for the week ahead? (meetings, travel, social)
   - `GARMIN_DAILY.md` / `GARMIN_ARCHIVE.md` (if available) — recovery trend, recent training load
   - `stackstone/crm.md` — what opportunities/accounts need momentum this week?
   - `TASKS.md` — any deliverables due this week?
   - `BACKLOG.md` — any urgent system/technical work?
   - **Calendar-anchoring rule (MANDATORY):** before naming any "live meetings", "booked meetings", or day/date pair in the weekly output, verify them against the calendar feed rather than paraphrasing from a prior summary. If a weekday/date pair cannot be verified from source, state the date or person only, not both.

3. **Check health trajectory**
   - When was the last run/gym session? (from `GARMIN_DAILY.md` or calendar)
   - Is Tom trending toward more fit or less fit?
   - Are there 2+ days this week where exercise is realistically possible?

4. **Propose weekly objective (MANDATORY)**
   - **Every week MUST have a clear objective** — this is non-negotiable
   - If Tom hasn't defined one yet, prompt for it before continuing
   - Single top-level direction for the week (one sentence)
   - Must align with Tom's bigger-picture goals (revenue growth, job search, capacity building, recovery)
   - Examples:
     - "Revenue momentum — chase warm leads, send C3, close one new paid engagement"
     - "Job search push — 5 quality applications, LinkedIn active, network warm-up"
     - "Consolidation week — finish Andy report, tidy CRM, prep Harken F2F"
     - "Recovery + rebuild — prioritise sleep, 3 solid runs, lighter work load"
   - Use current reality (calendar, CRM, health state) to shape the recommendation
   - Tom can confirm, refine, or replace it
   - **If missing:** Ask Tom directly: "What's the main objective for this week? What matters most?"

5. **Define 3 big things**
   - What are the 3 most important outcomes for this week?
   - Be specific: "Send C3 to 100 contacts" not "do outreach"
   - Include at least one health/exercise commitment if relevant
   - These 3 big things are the steering wheel for the daily standups: every morning standup must make today's main work clearly serve one or more of them, and every afternoon standup must check whether they actually moved.
   - If Tom has already named a concrete campaign / offer / build path as the route to growth (for example **Campaign C4**), write that exact named route into the weekly big thing rather than abstracting it into vague business-development language.

6. **Plan exercise sessions**
   - Which specific days/slots for runs or gym? (not vague intent)
   - Where do PT client sessions fit?
   - Where is recovery/lighter movement needed?
   - If the week is packed, explicitly decide which days are realistic for exercise vs which are admin/recovery days

7. **Flag risks**
   - Sleep protection: any late evenings this week that threaten recovery?
   - Capacity bottlenecks: any days with back-to-back commitments?
   - Momentum risks: warm opportunities going cold if not chased this week?

8. **Write WEEK_PLAN.md** (max 10 lines)
   ```
   # Week Plan — [Week starting Date]
   
   **Weekly objective:** [one sentence — MANDATORY, must exist]
   
   **3 big things:**
   - [outcome 1]
   - [outcome 2]
   - [outcome 3]
   
   **Exercise plan:**
   - [specific days/slots]
   
   **Risks to watch:**
   - [capacity/sleep/momentum risks]
   ```

9. **Send to Tom**
   - Present the plan on Telegram
   - Ask for confirmation or adjustments
   - **If weekly objective is missing:** Ask Tom to define it before proceeding
   - If Tom tweaks it, update `WEEK_PLAN.md` accordingly

## Output format
```
📅 Weekly Planning — [Week starting Date]

**Proposed weekly objective:** [one sentence — MANDATORY]

**3 big things:**
1. [outcome 1]
2. [outcome 2]
3. [outcome 3]

**Exercise plan:** [specific days/slots]

**Risks to watch:** [capacity/sleep/momentum risks]

Confirm or adjust?

-- L1
```

## Rules / constraints
- **Max 10 lines** in `WEEK_PLAN.md` — keep it tight
- **Be directive:** Suggest a weekly focus based on current reality, don't wait passively
- **Exercise must be specific:** "Mon/Wed/Fri runs" not "run 3x this week"
- **Balance realism:** Don't overpack the week, leave buffer for slippage
- **Use CRM momentum:** Surface warm opportunities that need chasing this week
- **Health trajectory matters:** If Tom is drifting less fit, make exercise a bigger part of the weekly focus
- **Sleep protection:** If calendar shows late evenings, flag them as risks to recovery
- **Tom can override:** This is a proposal, not a command — Tom adjusts before it's locked

## Data source paths
```
~/.openclaw/workspace/WEEK_PLAN.md
~/.openclaw/workspace/OUTLOOK_CALENDAR.md
~/.openclaw/workspace/GARMIN_DAILY.md
~/.openclaw/workspace/GARMIN_ARCHIVE.md
~/.openclaw/workspace/stackstone/crm.md
~/.openclaw/workspace/TASKS.md
~/.openclaw/workspace/BACKLOG.md
```

## Relationship to other crons
- **Feeds into:** Morning standup (07:00) — daily focus aligns with weekly direction
- **Feeds into:** Afternoon standup (13:45) — redirect uses weekly focus as context
- **Complements:** Weekly reflection (Fri 21:00) — reflects on last week, this plans next week
- **Complements:** Weekly AI briefing (Mon 07:00) — AI trends feed into strategic thinking

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
