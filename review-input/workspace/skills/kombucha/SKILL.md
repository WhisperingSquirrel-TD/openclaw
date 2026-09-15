---
name: kombucha
description: Track kombucha batches, recipes, bottling and tasting dates, and weather-adjusted fermentation reminders.
last_edited: 2026-07-13 21:46
---

# Kombucha

## Purpose
Provide a repeatable kombucha workflow so batches, recipes, timings, and reminders are not handled ad hoc.

## Canonical files
- Tracker: `/home/tomdean88/.openclaw/workspace/reference/KOMBUCHA.md`
- Reminder state: live cron objects

## When to use this skill
Use when Tom:
- starts a new batch
- bottles a batch
- changes the recipe
- asks when to taste or bottle
- mentions weather/temperature affecting timing
- wants reassurance that reminders are actually set

## Core rules
1. **Track every batch durably** in `reference/KOMBUCHA.md`
2. **Set/verify reminders before claiming completion** — this means creating/updating a live cron reminder, not just writing a date in the tracker
3. **Keep recipe details with each batch** so future comparisons are possible
4. **Adjust tasting guidance for warmth** — if the next few days look warmer than usual, suggest tasting earlier rather than blindly waiting for the nominal day
5. **Fail closed on reminders** — if the reminder is not in live cron state, the task is not complete
6. **Tracker date is not proof of reminder** — a `Reminder target` line in `reference/KOMBUCHA.md` is planning context only, not evidence that a live cron exists
7. **Timing answers must verify reminder state when relevant** — if Tom asks when to bottle/taste and the answer depends on whether a reminder should already have fired, check live cron state in the same pass and explicitly say whether the reminder existed or was missing
8. **Two-touch delivery chain (mandatory):** for every new batch, create both (a) a taste-check reminder around day 12/13 and (b) a day-14 failsafe decision reminder. A one-shot early reminder does not close the batch. The failsafe must tell Tom to ignore it only if the batch has already been bottled, and it must be separately verified as a live cron object.
9. **Missed-reminder audit:** when a batch is bottled without a preceding reminder, inspect tracker and live cron evidence separately. Mark delivery `unverified` unless a live job/run proves it; never infer delivery from a tracker target alone.

## Standard workflow

### A. New batch started
1. Read `reference/KOMBUCHA.md`
2. Add a new batch entry with:
   - batch number
   - start date
   - recipe
   - inherited notes (for example “same recipe as batch 5”)
   - provisional bottling target
3. Create or update a live cron reminder for the bottling/taste check
4. Verify the cron reminder exists in live cron state
5. Record the reminder target in `reference/KOMBUCHA.md`
6. Tell Tom the batch was logged and when he’ll be reminded

### B. Bottling completed
1. Read `reference/KOMBUCHA.md`
2. Mark the batch as bottled with date and notes
3. If Tom says a new batch was also started, create the new batch entry immediately
4. Update/remake reminders accordingly

### C. Timing / weather check
If Tom asks whether to taste early or bottle now:
1. Identify active batch from `reference/KOMBUCHA.md`
2. If the timing question intersects with an expected reminder window, check live cron state in the same pass
3. Check the local weather forecast using the `weather` skill if timing is materially weather-sensitive
4. Use a cautious rule:
   - warmer spell → suggest tasting earlier
   - cooler spell → default timing may hold longer
5. Phrase it as a recommendation, not false precision
6. If the tracker shows a reminder target but live cron state is missing, say that plainly and treat it as a reminder failure rather than silently assuming Tom was reminded

## Default reminder guidance
Use as a starting point unless Tom says otherwise:
- reminder around day 13 for bottling check
- in warmer conditions, suggest a day-12 taste check if appropriate

## Required tracker fields
For each batch, capture:
- batch number
- start date
- bottle date (when known)
- recipe
- notes
- reminder date
- status (`fermenting`, `bottled`, `finished`, etc.)

## Completion test
Before saying done, be able to point to:
- the updated tracker entry in `reference/KOMBUCHA.md`
- the live cron reminder object

If either is missing, the kombucha workflow is incomplete.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
