---
name: daily-plan
description: Build Tom's daily plan from priorities, calendar, health rules, exercise, relationships, and work; create only the necessary plan nudges.
---

# Daily Plan

## When to trigger
- Tom says "plan my day", "let's plan today", or shares a list of things he wants to achieve
- Monday morning stand-up (weekly review + week ahead)
- After morning briefing when Tom adds priorities
- When health/exercise has drifted, use this process proactively to rebuild the week around exercise rather than waiting for Tom to remember

## Data sources to read
1. `OUTLOOK_CALENDAR.md` — canonical calendar source for events and anchors
2. `GARMIN_DAILY.md` — if exists, check recovery score / HRV before scheduling exercise
3. `WEEK_PLAN.md` — if exists, pull this week's themes/commitments
4. `PLAN.md` — if exists from yesterday, wipe it (today is a clean slate)

## Existing cron slots — DO NOT schedule [TODAY] crons at these times
Full master schedule is in SYSTEM_MAP.md. Key blocked slots:
- :00, :15, :30, :45 of any hour — Pi scripts (whatsapp trim, report poller, stackstone poll)
- 06:00, 06:25, 07:00, 08:00, 08:30, 09:00 — Pi prospecting + OpenClaw morning jobs
- 10:25, 10:35, 13:25, 13:35, 16:25, 16:35, 19:25, 19:35 — inbox watches
- 21:00, 22:00 — LinkedIn draft + end-of-day cleanup

Safe nudge slots: 09:30, 10:00, 11:00, 11:30, 12:00, 12:30, 14:00, 14:30, 15:00, 15:30, 17:00, 17:30, 18:00, 20:00, 20:30

## Planning rules

### 🏃 Fitness — non-negotiable, plan this FIRST
Tom is currently getting less fit. Fitness blocks must be scheduled before work tasks, not around them.

**Every day must include at least one:**
- **Run** — minimum 1 hour block (run + shower). Good for strong/average recovery days.
- **Gym/strength session** — 45–60 min. Good for any recovery level.
- **Dog walk** — Tom walks the dogs every day. When he is at home, morning dog walk is the default routine unless he is away or has a PT client. If he is around, an afternoon/evening dog walk around 16:30 is also normal unless PT clients or work commitments change it. This is baseline, NOT a fitness session. Do not count it as exercise.

**Fitness scheduling rules:**
- Pick the fitness block FIRST. Then fill work around it.
- Morning is the best slot (pre-10am if no early calls). If morning is blocked, find another slot — don't skip.
- Run = minimum 1 hour clear (run + shower). Never schedule into a gap smaller than 60 min.
- If Garmin shows poor recovery: swap run for walk or strength. Don't skip entirely.
- If 2+ days have passed with no run/gym entry in GARMIN_DAILY.md or calendar, flag it and make today a run day regardless.
- PT sessions are fixed anchors — treat as immovable.

**Weekly targets (prompt Tom if falling behind):**
- 3+ runs or gym sessions per week
- No more than 2 consecutive days without intentional exercise
- At least 1 longer effort (45+ min run or full gym) per week

### 🍎 Nutrition & recovery
- Use Tom's hierarchy from `HEALTH.md`: **Sleep first → good nutrition → exercise/recovery → repeatable habits**
- **Alcohol:** Tom is actively cutting out drinking. Include "No alcohol today" as a daily commitment in every plan. Don't skip this.
- Every daily plan should make a judgment call on all four layers:
  - sleep: what protects tonight's sleep?
  - nutrition: what should eating look like today?
  - exercise/recovery: train, move lightly, or deliberately recover?
  - repetition: what structure makes this easier to repeat?
- If Garmin shows low HRV or poor sleep — flag it explicitly and suggest lighter exercise + earlier sleep tonight
- Sleep is part of the plan. If it's past 21:30 and Tom hasn't mentioned wind-down, add a nudge
- When work conflicts with health, bias toward protecting sleep and nutrition first, then finding a realistic exercise/recovery choice rather than dropping health entirely

### 📋 Other planning rules
- **Hard stops** — diary events are non-negotiable; plan around them
- **Work batching** — group deep work (outreach, writing, strategy) in morning blocks; admin/calls in afternoon
- **Relationships** — if Lauren is home, flag evening as protected time unless she's out
- **Flexibility buffer** — leave 30–60 min unscheduled per half-day for slippage
- Be realistic. A half-day in London means the morning is for work, not the whole day.
- If CRM shows a momentum-critical `Next Step`, make room for it in the plan rather than treating it as optional background context.
- Treat stale or due CRM `Next Step` items as actionable prompts for Tom, especially on warm opportunities.

## Operating framework (MANDATORY)
Every daily plan must explicitly decide and use these control fields before building the task list:
- **Day mode:** `recovery` | `steady-execution` | `deep-work` | `admin-containment`
- **Support mode:** `execution` | `momentum` | `protection` | `push`
- **Health move:** the single health/recovery action to protect first
- **Revenue move:** the single money-moving block that must happen today
- **Admin limit:** the maximum shape/time admin/legal is allowed to take
- **Drift risk:** what is most likely to steal the day if not contained

### How to choose support mode
- **execution** — Tom already knows what needs doing; give sequence, time-boxing, and fewer words
- **momentum** — Tom is sticky/drifting/avoidant; give a smaller next move, sharper prioritisation, and a traction-creating suggestion
- **protection** — Tom is depleted/overloaded, or it is a weekend/evening where work should be contained; reduce scope, protect health, and stop guilt from writing the plan
- **push** — Tom has capacity/space; be more ambitious and use the day properly

### Weekend / evening default
Respect weekends and evenings by default.
- Tom does **not work weekends** unless he explicitly opts in or there is a genuinely urgent exception
- Do not let open tasks alone justify turning Saturday/Sunday into work periods
- On weekends, default to rest / social time / recovery, plus only truly necessary logistics
- On evenings, default to protecting wind-down unless Tom explicitly wants a push
- Prefer no work blocks on weekends; only include one if there is a real immovable reason or Tom has asked for it

## Daily Focus — generate this first
Before building the schedule, synthesise a single-sentence focus recommendation:

**Inputs:**
- `GARMIN_DAILY.md` — recovery score, HRV vs baseline, sleep quality, resting HR
- Day of week — Mon = strategy/momentum, Fri = wrap-up, mid-week = execution
- Open priorities — job applications pending? Stackstone replies? Property actions? Warm follow-ups due (Jess Harrold, Tim Ward, Stuart Hobin etc.)?
- `stackstone/crm.md` — especially Opportunities/Accounts `Last Touch` and `Next Step` for momentum-critical follow-up work
- Life context — travel today? Lauren home tonight? Social plans?

**Recovery → mode mapping:**
- Strong recovery (HRV at/above baseline, good sleep) → Deep work mode. Protect a 2–3 hour uninterrupted block. Good day for hard creative or strategic tasks.
- Average recovery → Normal mode. Mix of work and lighter tasks. Exercise fine if energy is there.
- Poor recovery (HRV well below baseline, bad sleep, high resting HR) → Light mode. Admin only, no big asks, no hard exercise. Rest is the priority.
- No Garmin data → Don't guess. Ask Tom how he's feeling before recommending exercise.

**Balance rule:**
- Do not assume the right answer is always "do more exercise today".
- Review recent effort and recovery first: what Tom has already done this week, any recent runs/gym sessions, sleep quality, calendar load, and whether he is carrying fatigue.
- If Tom is already pushing hard or recovery looks poor, explicitly recommend easing off, resting, or keeping the day lighter.
- Health support must involve a short judgment call about balance, not just inserting exercise by default.

**Output format:**
> **Today's focus: [mode] — [one sentence reason + recommended priority].**

Example:
> **Today's focus: Deep work — strong recovery, clear morning before London. Use it for job applications or C3 planning.**

> **Today's focus: Light admin — poor sleep flagged by Garmin, travelling at lunch. Inbox + property enquiries only.**

## PLAN.md format
PLAN.md is injected into every session — keep it SHORT. Bullet list only. No tables, no headers, no schedule blocks.

```
# Plan — [Day Date]
- Mode: [day mode] / [support mode]
- 🏃 [health move]
- 💷 [revenue move]
- 🚫 No alcohol
- ⏱️ Admin limit: [limit]
- ⚠️ Drift risk: [main risk]
- [supporting task 1]
- [supporting task 2 / diary anchor]
```

Max 8 lines. If it's longer, cut it.

## [TODAY] crons
- Name every cron `[TODAY] [description]` — this makes them easy to find and delete
- Use `sessionTarget: main`, `deleteAfterRun: true`
- Keep nudge text short and direct — what Tom needs to do or check RIGHT NOW
- Create a maximum of 4–5 nudges per day (quality > quantity)

## End-of-day
PLAN.md is wiped by the standing 22:00 cleanup cron. [TODAY] crons delete themselves after firing.

## Monday stand-up
On Mondays, also read/create `WEEK_PLAN.md`:
- What is the weekly focus? (single top-level direction for the week)
- What are the 3 big things this week?
- Any fixed commitments (meetings, travel, social)?
- What are the planned exercise sessions this week? (specific slots, not vague intent)
- Job search / business-development actions this week?
- Which warm opportunities or diary-filling actions matter this week?
- Is sleep protection likely to be an issue any evening this week?
Keep it to 10 lines max. This becomes context for daily planning all week.

**Weekly focus rule:**
- A weekly focus should be explicitly set on Monday.
- L1 should suggest a weekly focus based on current context, priorities, momentum risks, diary anchors, and health state — not just wait for Tom to invent one from scratch.
- Tom can confirm, refine, or replace the suggestion.
- Daily plans and briefings should reinforce that focus during the week rather than drifting into generic task lists.
- If Tom states a weekly focus directly, treat it as governing context for the rest of the week unless he changes it.

## Late-evening sleep protection
- If Tom is still messaging about non-urgent work/admin late in the evening, briefly warn him that being on the phone this late is working against the sleep goal.
- Default threshold: after 21:30, be willing to give a short sleep-protective nudge; after 22:00, be more direct unless the matter is genuinely urgent.
- Keep it brief and practical: suggest stopping for the night rather than continuing to expand the discussion.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
