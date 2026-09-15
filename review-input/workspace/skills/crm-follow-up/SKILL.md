---
name: crm-follow-up
description: Choose the right commercial next step—chase, wait, keep warm, redirect, or close—using current relationship context, timing, and evidence rather than momentum.
---

# CRM Follow-Up

Use this skill at the moment a next action is being chosen.

## Purpose
Turn vague commercial momentum into the right action:
- chase now
- schedule a later follow-up
- keep warm without nudging yet
- wait/watch
- close the loop / no action
- redirect to a different person only when there is a real route

This skill exists to stop false urgency, socially tone-deaf chasing, and invented alternate routes.

## Required inputs
Check as many of these as are available:
- `stackstone/crm.md`
- relevant SharePoint `Current.md` / recent dated artifacts
- recent inbox/sent context
- TASKS context if the follow-up is tied to a live work item
- explicit user-provided context from Tom

## Decision rule
Before choosing a next step, answer these in order:
1. Is the thread commercially live?
2. Is there a real reason to contact them now?
3. Is there any source-backed reason not to contact them now?
4. Does Tom have a real relationship path to the proposed person?
5. What is the lightest correct action?

## Context blockers (fail closed)
Default away from "chase now" if any of these are true unless stronger evidence overrides:
- the person is on leave / unavailable
- there was recent meaningful movement already
- the thread is explicitly waiting on an external date or decision
- the next step belongs to someone else for now
- Tom has no real relationship route to the alternate contact being proposed
- the only reason to chase is that the opportunity feels important

If a blocker exists, prefer one of:
- `Watch only / waiting`
- `Keep warm later`
- `Review on <date>`
- `No action until <condition>`

## Alternate-contact rule
Do not suggest "reach out to X instead" unless at least one is true:
- Tom already has a live relationship with X
- the CRM/SharePoint notes explicitly identify X as the right next route
- the current contact explicitly redirected Tom to X

If none are true, do not invent the route.

## Output contract
Every chosen next step should be expressible in this shape:
`Next action date: YYYY-MM-DD or review date | Owner: Tom/L1/Waiting external | State: due/scheduled/waiting/watch/blocked/done | Next best action: <clear action or explicit no-action condition>`

## Action types
### 1. Chase now
Use when:
- the thread is live
- Tom is the right person to act
- there is no context blocker
- a nudge is commercially sensible and socially normal

### 2. Schedule later
Use when follow-up is right, but not yet.
Examples:
- after leave ends
- after a meeting/board review
- after a promised review date

### 3. Keep warm
Use when the relationship matters but an ask/chase would be premature.
Prefer a dated review point rather than passive forgetting.

### 4. Watch only / waiting
Use when there is a clear external dependency or a deliberate reason to leave the thread alone for now.

### 5. Redirect
Use only when there is a real evidenced route to another person.

### 6. Close / no action
Use when there is genuinely nothing useful to do now.

## Where this must be applied
- morning/afternoon standup when surfacing warm contacts or nudges
- `crm-update` when maintaining `Next Step`
- `crm-sharepoint` when updating `Current.md` control truth
- any operational output that recommends a named follow-up

## Fail-closed test
Before finalizing a follow-up recommendation, ask:
- Am I recommending action because it is actually timely, or just because I want momentum?
- If Tom followed this today, would it feel context-aware or pushy?
- If I am naming an alternate person, do I have proof of route, not just a guess?

If uncertain, choose the lighter action and make the review date explicit.

## Mandatory end-of-use review
After real use, do a short explicit check with Tom on whether the follow-up judgment rule itself needs tightening.
