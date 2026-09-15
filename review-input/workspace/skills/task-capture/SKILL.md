---
name: task-capture
description: Capture non-code actions into the right visible holding layer without automatically decomposing or operating them; use TASKS.md by default and BACKLOG.md for technical work.
last_edited: 2026-06-29 14:36
---

# Task Capture

## Purpose
Capture work cheaply, visibly, and with enough context to be useful later — without spending unnecessary tokens decomposing or operating on tasks Tom has not selected for active work.

**Key boundary:** `TASKS.md` is the default cheap capture and visible prioritisation surface for non-code/action work. The structured task system is the selected/decomposed/operated layer, not the default destination for every captured item.

Cheap capture does **not** mean context-free capture. If Tom or a source gives useful detail, preserve the important context compactly at capture time, then defer heavy research/source-bundling until selection/decomposition.

## Lifecycle

1. **Capture in the right holding layer**
   - `TASKS.md` for non-code/admin/business/personal/action work
   - `BACKLOG.md` for technical/system/build/replit/runtime work
   - `L1-IMPROVEMENTS.md` for non-breakage behavioural/workflow/quality improvements
   - structured task system only when explicitly selected or required by workflow
2. **Select**
   - chosen during weekly planning, morning planning, explicit Tom instruction, or urgent trigger
3. **Decompose**
   - use `skills/task-decompose/SKILL.md`; build the source bundle and create task/subtask chain
4. **Operate**
   - use `skills/task-operate/SKILL.md`; L1 executes eligible subtasks
5. **Close / defer / system-handle**
   - move completed/noisy/system-monitored items out of the active visible surface, leaving a brief reason/evidence note

## Trigger

Use this skill when:
- Tom says “add this task”, “put this in the system”, “capture this”, “remember this task”, “put this on TASKS.md”, or similar
- Tom provides information that creates a follow-up, even if he frames it casually
- a transcript/resource upload contains an action Tom explicitly approves for capture
- an email, Teams item, WhatsApp item, LinkedIn item, calendar item, website enquiry, or other inbound surface reveals a task-worthy follow-up
- CRM, partnership, invoice, expense, SharePoint, meeting-copilot, or file-organisation work creates a follow-up task
- L1 discovers a necessary follow-up while moving files, updating CRM/SharePoint, operating a task, reconciling feeds, or fixing a system
- importing or cleaning legacy items from `TASKS.md`

Do **not** decompose by default.

## Classification gate

Before creating/changing records, classify the request as one of:

### `list_capture_only`
Default for ordinary capture.

Use:
- `TASKS.md` for non-code/admin/business/client/personal/action work
- `BACKLOG.md` for technical/system/build/Replit/runtime work
- `L1-IMPROVEMENTS.md` for quality/behaviour/process improvements that are not active technical breakages

Do **not** create structured task-system records, assign execution readiness, or create subtasks. Stop after capture.

Use this when Tom says “task list”, “add it”, “capture it”, “remember this”, or “we should add X” without explicitly naming the structured task system or asking L1 to work it now.

### `structured_capture_only`
Use only when:
- Tom explicitly names the structured task system
- the item is selected work but should not yet be decomposed
- a governing workflow requires structured state
- a GUI/operator workflow needs a parent record for selected work

Create a lightweight structured task under the right strategy/objective if useful. Do not create subtasks.

Set:
- `readiness_state=decompose_ready`
- `state=open`
- `next_action` = next known concrete action or “select for decomposition when prioritised”
- `success_definition` if obvious; otherwise note what is missing
- source/provenance
- concise verified/inferred summary

### `decompose_now`
Only if:
- Tom explicitly asks to break it down/decompose/work it
- it is selected in day/week planning
- it is urgent/high-priority now
- it blocks current client delivery, new-business momentum, or a time-sensitive relationship move

Then run `skills/task-decompose/SKILL.md`.

### `operate_now`
Only after:
- decomposition has produced L1-owned execute-ready subtasks, or
- Tom explicitly asks L1 to start work

Then run `skills/task-operate/SKILL.md`.

## Focus-lane rule for `TASKS.md`

Every active `TASKS.md` item should sit in a focus lane so the list helps Tom and L1 prioritise rather than becoming a flat dumping ground.

Default lanes:
1. **Revenue now — current client / paid work**
2. **Revenue next — warm pipeline / partnerships**
3. **Offer / product building**
4. **Operational / admin risk**
5. **Personal / deferred**
6. **System-handled / cleared**

When capturing, choose the lane that best answers: “Why does this matter to Tom’s current focus?”

Revenue/client/new-business lanes should usually outrank generic admin unless a hard deadline or legal/financial risk overrides.

## Mandatory capture metadata

Whenever something is added to a task list, preserve these fields or their equivalent:
- `Added` date
- `Updated` date if modifying existing item
- `Source / context ref`
- `Why it matters`
- `Next concrete action`
- `Owner hint` — Tom / L1 / Mixed / System watch / Unknown
- `Status` — Active / Waiting / Blocked / Backlog / Deferred / System-handled / Done
- `Capture state` — Captured / Needs context / Ready to decompose / Selected / In task-system / Operating / Waiting Tom / Cleared

If a compact dashboard cannot fit all fields, keep the most important in the dashboard and put the rest in detailed notes below.

## Context preservation rule

If Tom gives task context, capture the substance even in cheap capture.

Do:
- keep relevant names, dates, URLs, constraints, and “why this matters”
- link to CRM/SharePoint/transcript/email/calendar/source files when known
- preserve Tom’s stated intent rather than reducing the item to a vague label

Do not:
- throw away detail just because the item is not selected yet
- run broad context gathering for every unselected item
- invent missing facts to make the row look complete

If the source detail is rich and durable, route to the relevant owning skill as well as capturing the task.

## System-handled items

If another system already watches the item naturally, do not keep it in active `TASKS.md` just because it once mattered.

Examples:
- campaign reply/bounce/unsubscribe monitoring handled by inbox/watch/router logic
- recurring health/feed checks handled by heartbeat/system health
- invoice chase dates handled by invoice tracker/watch process

Move these to **System-handled / cleared** with a short note, unless Tom explicitly wants them visible.

## When to ask Tom

Ask a clarification only if:
- the task title would be ambiguous later
- the owner/timing is materially unclear and affects placement/visibility
- the task cannot be safely captured without inventing facts
- the capture could create unwanted work or external action

Otherwise capture cheaply and defer questions to decomposition.

## Jump-off points

### Upstream sources that may create tasks
- `skills/resource-intake/SKILL.md` — uploaded docs/resources that contain actions
- `skills/transcript-resource/SKILL.md` — transcripts/notes with approved actions
- `skills/email-check/SKILL.md` — inbox-derived actions
- `skills/whatsapp-check/SKILL.md` — WhatsApp-derived actions
- `skills/crm-update/SKILL.md` — CRM/entity movement creating next steps
- `skills/crm-sharepoint/SKILL.md` — SharePoint/account-current follow-ups
- `skills/crm-partnership/SKILL.md` — strategic partner follow-ups
- `reference/INBOUND-OPERATING-STANDARD.md` and `reference/INBOUND-ROUTING.md` — monitored inbound routing and proof expectations
- `reference/SHAREPOINT-ORIGIN-RECONCILIATION-WATCHER.md` — SharePoint-origin actions and reconciliation
- `reference/TEAMS-INFORMATION-FLOW-PLAN.md` — Teams-derived visibility and routing

### Downstream routes after capture
- `skills/task-decompose/SKILL.md` — selected/priority work breakdown
- `skills/task-operate/SKILL.md` — L1-ready execution cycle
- `skills/morning-standup/SKILL.md` — daily focus/task suggestions
- `skills/afternoon-standup/SKILL.md` — progress check and redirect
- `skills/weekly-planning/SKILL.md` — weekly objective and big-things selection
- `reference/TASK-CAPTURE-FUNNEL.md` — design bridge between `TASKS.md` and structured task system
- `projects/workspace-control-panel/TASK_SYSTEM_OPERATOR_SPEC.md` — structured operator semantics

## Completion rule

After capture-only, stop. Do not silently continue into decomposition or L1 execution.

Report briefly:
- captured/updated item title
- where it went (`TASKS.md`, `BACKLOG.md`, `L1-IMPROVEMENTS.md`, or structured task system)
- focus lane / capture state
- what would trigger decomposition or operation
