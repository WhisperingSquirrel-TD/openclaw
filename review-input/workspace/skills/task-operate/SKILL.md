---
name: task-operate
description: Operate L1-ready structured-task subtasks by loading context, executing safely, handling gates or blockers, and completing or patching state with proof.
last_edited: 2026-06-27 21:38
---

# Task Operate

## Purpose
The task system is not just storage. If a subtask is genuinely L1-owned, execute-ready, and safe, L1 should actively pick it up rather than waiting for Tom to re-instruct.

This skill governs the **pickup/execution cycle** after tasks have been decomposed.

Use `skills/task-decompose/SKILL.md` to create/refine subtasks. Use this skill to operate the queue.

## Trigger
Run this skill when:
- Tom says to work from the task system
- Tom asks what L1 can do next
- a selected-priority task has been decomposed and includes L1-owned executable subtasks
- a standup/check-in needs to progress L1-owned work
- the GUI/task-system shows L1-ready subtasks for a task already selected for active work
- a previous L1 subtask completed by this agent and there may be a next eligible L1 subtask
- a runtime event, cron, GUI transition hook, or explicit user message reports that Tom/external work changed a task/subtask state

Do not run this merely because a task was captured. Capture-only items remain in `decompose_ready` until selected.

### Trigger-source honesty rule
Task-system state changes made outside the current agent turn are not a trigger by themselves unless something delivers them to the agent. Do not claim “completion triggers me to continue” unless the completion is one of:
- a subtask completion this agent just performed in the same operating cycle,
- an explicit Tom/user message,
- a scheduled task-operator cron/check,
- a runtime/GUI transition event wired to invoke this skill.

If the intended workflow depends on Tom completing a review/decision in the GUI and L1 automatically continuing afterwards, there must be a real invocation path such as a cron or transition hook. Without that, report the gap and do not describe the workflow as autonomous.

## Core rule
If a subtask is:
- `owner=L1`
- `state=todo` or equivalent active state
- `execute_ready=true`
- `missing_execute_ready_fields=[]`
- not blocked
- and within the permitted risk/gate rules

then L1 should pick it up in a bounded cycle.

Do not wait for Tom unless the subtask requires Tom input, Tom oversight, a gate/TOTP, external approval, or clarification.

## Pickup eligibility

### Eligible to auto-pick
- `owner=L1`
- `risk=LOW`
- `execution_mode=do_now`
- no blockers
- enough context/source refs exist

### Eligible to prepare, but not finalise externally
- `owner=L1`
- `risk=MEDIUM`
- `execution_mode=prepare_for_review`
- no blockers
- later Tom oversight checkpoint exists for the medium-risk output, or the work is clearly only preparation and not final consequence

### Not eligible to auto-pick
- `owner=Tom`
- `risk=HIGH` unless explicitly bounded as L1 preparation
- `execution_mode=review_with_tom`
- `execution_mode=blocked`
- missing execute-ready fields
- external send/write requiring TOTP where prep is not already separated
- unclear success definition or source context

## Operating cycle

### 1. Discover
Query the task system for L1-owned todo subtasks:
- `task_system view subtasks_by_owner_state owner=L1 state=todo`

If focused on a parent task, filter by `parent_id=<task_id>`.

### 2. Filter
For each candidate, check:
- `execute_ready`
- `effective_readiness`
- `missing_execute_ready_fields`
- `blockers_json`
- `risk`
- `execution_mode`
- parent task context, especially later Tom oversight if `risk=MEDIUM`

### 3. Prioritise
Default order:
1. already-current parent task Tom just discussed
2. `risk=LOW` + `do_now`
3. `risk=MEDIUM` + `prepare_for_review` where a later Tom oversight checkpoint exists
4. oldest active L1-ready item
5. items blocking Tom-owned review/send decisions

Maintain WIP discipline: normally start one subtask at a time unless the subtasks are trivial and independent.

### 4. Start
Before doing material work, call:
- `task_system subtask_start id=<subtask_id>`

If start fails because readiness changed, stop and patch/report the blocker rather than working around it.

### 5. Load context
Canonical contract: `projects/workspace-control-panel/TASK_EXECUTION_CONTEXT_CONTRACT.md`

Read/build a task packet from stored state:
- `task_system entity_context kind=subtask id=<subtask_id>`
- parent chain
- parent task context fields, especially `current_focus`, `next_action`, `intent`, `success_definition`, `priority_rank`, blockers, and any compact brief/summary field the GUI surfaces first
- parent task timeline when recent GUI/Tom edits may have changed task-level intent, approval semantics, blockers, or whether older subtasks are now stale
- subtask timeline when `current_focus` contains `ROLLBACK NOTE` / `RESTART REQUESTED` or recent state looks regressed
- sibling subtasks if dependency order matters
- `primary_source_ref`
- relevant source files/docs
- governing domain skills if the work touches CRM, email, docs, code, invoices, expenses, calendar, etc.

Task execution must be source-reconstructed, not chat-inherited. Treat live chat memory as advisory only. If same-session execution is used, explicitly reload the task packet first.

Do not do broad retrieval when the source refs are enough. Escalate context only when needed.

**Email-draft no-gate rule (MANDATORY):** For an L1-owned email-draft subtask, load the bounded message/WhatsApp/entity packet through the context broker and create the unsent Outlook draft without requesting TOTP or using `exec`. A missing entity/profile/source binding is a task-system repair obligation: patch/register the bounded binding or retain its exact broker coverage error. Never turn that implementation gap into a request for Tom to unlock ordinary drafting.

**Broker-identifier integrity rule (MANDATORY):** Before diagnosing a broker load as an authorisation, binding, or TOTP problem, read the selected task and its direct subtask(s) and validate request shape against the broker contract: `task_id` must identify the parent task, `subtask_id` must identify its direct execution child, and `entity_id` (for example an `email_auto_*` selector) is never a substitute for a subtask. Use the existing `execute` route for a task-bound no-send draft when it is available; do not call the package-only writer with raw context. If the pair/profile is unavailable, preserve the exact `TASK_SUBTASK_NOT_FOUND`/coverage error and repair the task chain rather than asking Tom for TOTP.

Rollback/regression rule:
- If `current_focus` starts `ROLLBACK NOTE:` or `CHANGES REQUESTED:`, do not treat the subtask as isolated rework. First perform a rollback/change-request impact assessment: read the regression/change note, parent task, and sibling subtasks; classify the change as minor rework, major rework affecting downstream done/review subtasks, or restart/refactor; patch affected parent/sibling states before proceeding. Then address the specific issue Tom named, and completion proof must say `Redone per rollback note — ...`, `Updated per Tom change request — ...`, or equivalent.
- If `current_focus` starts `RESTART REQUESTED:` or `blockers_json` includes `restart_requested: true`, do **not** start or pick up the subtask. This is a task-level refactor signal; leave it blocked until Tom clears the blocker and updates context.
- If rollback repair leaves L1-owned work in `todo`/execute-ready state, call `operator_signal` after the chain is patched. Do not assume a prior signal survived the rollback or operator cycle.

Task-system input impact-assessment rule (MANDATORY):
- Any note, input, clarification, change request, rollback, regression, or frontend edit on a task/subtask is operational input, not passive prose.
- Before starting, continuing, or completing a subtask, read recent parent/subtask timeline events and ask: does any input change intent, scope, constraints, audience, recipients, BCC/CC route, approval route, output format, external wording, blockers, dependencies, success definition, or whether existing outputs are still valid?
- If no chain impact, leave/record it as context and proceed.
- If it changes execution semantics, do not leave it only as a timeline event. Patch the parent task and affected subtasks so `next_action`, `success_definition`, `current_focus`, `blockers_json`, `readiness_state`, and output-link expectations match the input.
- If an already-done output is made stale by the input, reopen/mark the producing subtask for rework or mark the output conditional/superseded.
- If downstream done/review subtasks depend on the changed upstream work, block or mark them conditional until the revised upstream output is complete.
- If L1 work remains, call `operator_signal` after patching the chain.

**Recent-change decay rule (MANDATORY):** not every fresh patch should keep a claimed subtask in review limbo. When a recent change is only the normal result of upstream L1 work completing (for example: an audit/classification step promotes a bounded successor to `execute_ready` and clarifies `current_focus`), treat that patch as a short reassessment trigger, not a durable blocker. The operating pass must quickly collapse the review point into one of two outcomes:
1. `safe to proceed now` — continue the claimed successor if the subtask is still within allowed L1 risk/execution rules and no new external consequence was introduced; or
2. `actually needs review/block` — write the exact blocker/review reason onto the subtask if the patch truly changed intent, audience, consequence, or approval semantics.

Do not leave a claimed successor stalled just because it was recently promoted by the normal audit→successor flow.

Tom-note chain propagation rule (MANDATORY):
- A Tom-authored note on a review/checkpoint subtask is not necessarily local to that subtask. Treat it as a possible upstream output requirement change.
- If the note says or implies changes to a list, candidate set, contacts, recipients, BCC/CC route, email/copy/wording/draft, output format, approval route, or “let’s build/change/add/include/remove that”, inspect sibling subtasks and the parent task before deciding it is context-only.
- If a sibling L1 producer created the affected output and is already `done`, `waiting_tom`, `blocked`, or `superseded`, reopen or mark it stale for L1 rework; do not leave Tom’s review checkpoint ready against stale output.
- Block the dependent Tom review/send checkpoint until the upstream L1 output is revised.
- Patch parent `current_focus`/`next_action` so the GUI shows the real next step.
- Signal the operator after chain repair. A note that creates L1 work must result in `work_waiting=true`; merely storing the note is incomplete.

Tom-feedback execution-return rule (MANDATORY):
- When a Tom-authored task/subtask event contains an approval, change request, correction, or explicit “make that happen” style instruction, do not stop at classification or timeline storage.
- In the same operating pass, do one of three things before considering the system healthy:
  1. patch/create/reopen the concrete L1-owned subtask(s) now required,
  2. patch an explicit visible blocker such as `reanalysis_required` / `operator_wiring_missing`, or
  3. truthfully report that no L1 action remains after impact assessment.
- `work_waiting=false` is not a valid resting state if Tom’s note has created new L1 work and the chain has not yet been repaired.
- If the runtime path that should auto-trigger L1 is missing or unverified, fail closed: record that gap on the task/subtask and tell Tom plainly rather than implying the operator will naturally pick it up later.
- Mechanism test for this rule: after any qualifying Tom-authored event, re-run parent/subtask timeline assessment, then verify one of these is true before stopping: an eligible L1 todo subtask exists, an explicit blocker exists, or the note was assessed as genuinely context-only with no remaining L1 action.

### 6. Execute
Do the smallest complete unit matching the subtask’s `next_action` and `success_definition`.

**Delegated-execution proof rule (MANDATORY):** when L1 delegates a system/task remediation pass to a subagent or background worker, delegation is not completion and is not sufficient proof that work is progressing cleanly. Before reporting the work as underway, ensure the parent task has an execution-visible state (decomposed/committed or an explicit bounded implementation subtask) with a concrete success definition. Before reporting the work as complete, verify the delegate has returned a result, identify changed files/artifacts, and check the stated tests/proof output. If the delegate remains active beyond the bounded execution window or has not returned proof, report `in progress / proof pending` and the exact state; do not imply the issue has been resolved. If the task remains only `captured` while delegated work is running, patch or flag that state mismatch immediately.

For L1-medium preparation:
- create the draft/package/analysis/send pack
- mark assumptions and open questions
- do not perform final external action
- ensure a later Tom oversight checkpoint exists or patch/create one if missing

### 7. Verify
Before completing, check the result against `success_definition`.

If proof is file-based, verify the file exists or was updated.
If proof is system-based, re-read the target state.
If proof is only a draft/prep artifact, label it as draft/prep and do not imply external completion.

### 8. Complete or patch
If done:
- refresh the parent task’s live context fields when direction/status changed: `current_focus`, `next_action`, blockers, and priority if needed
- attach any created output files/URLs to the relevant task/subtask `links_json` before or alongside completion, so the GUI can surface navigable outputs
- `task_system subtask_complete` with `completion_note` and `proof_summary`

Output-link rule:
- Durable outputs created by L1 work must not live only in chat, completion notes, or unlinked folder paths.
- Before reporting a document-producing subtask as complete, verify the output exists or the external URL is valid enough for the current context.
- Patch the completing/producing subtask with a link object such as `{ "label": "Source bundle", "path": "stackstone/reference/sales/...", "type": "markdown", "role": "output" }`.
- Roll up every important output link to the parent task `links_json` so the GUI can surface task-level documents without Tom opening each subtask.
- If a Tom-owned review/checkpoint subtask depends on the artifact, patch that review subtask `links_json` with the relevant output links too.
- If an output supersedes or changes the status of an earlier artifact, mark older context/links as draft, superseded, or conditional rather than leaving multiple documents ambiguous.
- Do not report a document-producing subtask as complete if the produced document is not linked from at least the producing subtask and the parent task.

If blocked:
- patch the subtask immediately so the GUI shows the failure clearly
- set concrete blocker data (`blockers_json`) with exact reason and unblock condition
- refresh parent-task context fields if the blockage changes the live direction/status
- tell Tom in chat that L1 started the task but discovered it could not complete it

Mid-flight failure rule:
- If L1 starts a subtask believing it is executable, then discovers during execution that it cannot actually complete it, this must be surfaced in **both** places:
  1. on the subtask/task in the task system / GUI
  2. to Tom in chat
- Do not leave the subtask looking healthy or merely "in progress" after discovering the failure.
- Distinguish planned `waiting_tom` / review checkpoints from true `blocked` discovery.
- Chat update must say: what L1 tried, what blocked it, whether any partial useful output exists, and the exact next step needed from Tom or the system.

If clarification needed:
- stop and ask Tom one tight question; do not invent missing context.
- after Tom answers, patch the relevant task/subtask context before continuing
- then reassess upward: a seemingly small subtask clarification may invalidate the parent task, sequencing, or decomposition

Clarification propagation rule:
- Treat Tom clarification as a state-changing event, not just chat memory.
- Write the clarification back into the relevant task/subtask fields and timeline/audit trail.
- Then decide whether the clarification:
  1. only unblocks the current subtask,
  2. changes the decomposition/sequence, or
  3. invalidates the current parent task entirely.
- If the parent task is invalidated, do not keep operating from stale subtasks.

### 9. Continue or stop
After completion, check whether the next L1 subtask in the same parent task is now eligible.

**Successor-readiness rule (MANDATORY):** if the subtask just completed was an upstream discovery/audit/classification/proof step whose purpose was to determine whether a later L1-owned sibling can now proceed, do not stop at "audit complete". In the same operating pass:
1. inspect the next sibling(s) in the same parent task,
2. decide whether the completed evidence has removed the uncertainty/blocker for the successor,
3. patch the successor subtask to `readiness_state=execute_ready` / equivalent active state if it is now safe and fully specified,
4. update the parent task `current_focus` / `next_action` if the live direction changed,
5. call `operator_signal` if L1-owned work is now waiting,
6. then continue the cycle or truthfully report why the chain still cannot advance.

Do not leave the next bounded L1 step sitting in `planned` merely because an earlier audit finished. If the audit proved the next step is safe, the system state must reflect that immediately.

Archive/recreate rule:
- If a clarification or discovery means the current full task should be archived, superseded, or deleted, add a clear audit note to the old task explaining why.
- If a replacement task is created, carry forward a detailed handover into the new task: what changed, what remains true, what outputs/artifacts still matter, what should happen next, and links/source refs from the prior task.
- Do not make Tom reconstruct context from the archived task by hand.

Continue only if:
- it is safe
- token/time budget is reasonable
- no gate/rate limit/quiet-hour issue exists
- no Tom review/input is now required

Otherwise stop and report concise status.

## Rate limits, token limits, and system load

### Rate limits / 429s
If a tool/API returns rate limit or retry-after:
1. stop rapid retries
2. record the blocker on the subtask or leave a completion note if partial work is useful
3. schedule or suggest a retry after the retry window if appropriate
4. continue with another independent low-risk local subtask only if it does not depend on the limited service

### Token budget
Prefer:
- source refs over broad scans
- summaries over full files
- one parent task at a time
- deterministic checks before LLM reasoning

If context becomes too large, create a source-bundle subtask/output rather than holding everything in chat.

### Long-running work
For long or multi-file work:
- use a subagent when appropriate
- keep the parent session as orchestrator
- ensure completion writes back to task-system state

### Gate/TOTP closed
If a subtask needs a gate:
- do all prep possible
- patch/leave the final gated subtask for Tom
- do not keep asking repeatedly if the prep is not ready

### Quiet hours
Do not proactively message Tom during quiet hours unless safety/revenue-critical rules require it. Internal low-risk work may be queued, but user-facing updates wait.

## Reporting style
Task-system user-facing updates sent to Tom on Telegram should be visually obvious in a noisy chat. Prefix them with a clear task-system marker such as `🧩 Task system:`.

**Silent operator-cron proof rule:** When an operator cron explicitly says to stay silent for `idle`, `deferred`, or `watch`, run `operator_check` first and return exactly `NO_REPLY` only after its outcome is verified. Do not substitute an acknowledgement or skip the call. If a later user challenges that pass or explicitly asks to complete the original cron again, re-run `operator_check` before replying and give one compact factual final result (outcome, reason, and whether a subtask was claimed); do not repeat `NO_REPLY` in response to that challenge and do not claim a subtask was operated unless the check actually claimed one. Treat a verified `NO_REPLY` as a deliberate silent completion, not evidence that no tool call happened; it may nevertheless be perceived as an acknowledgement on chat surfaces. On challenge, re-check the live operator state rather than defending the prior response, then give the requested compact factual final result from that re-check. The challenge response must explicitly distinguish `operator_check executed` from its outcome and name whether a subtask was claimed; never repeat a silent acknowledgement in that response.

**Long-cycle visibility rule (MANDATORY):** when Tom explicitly asks L1 to run a live task-system test or operation that requires more than one lifecycle/broker call, send one minimal in-progress marker immediately after the task is created/claimed and before continuing the remaining calls: `🧩 Task system: running the requested test now — I’ll report the verified outcome.` Do not substitute this marker for the final proof, and do not add further progress narration unless blocked. This prevents a queued message from reasonably looking like inaction while preserving token-conscious execution.

After a cycle, report only:
- what was picked up
- what was completed/blocked
- proof or blocker
- next eligible L1 subtask, if any

If the update is specifically about a mid-flight failure, make that unmistakable, e.g. `🧩 Task system blocked:`.

Do not narrate every internal read/check.

## Completion checklist
Before claiming the cycle worked:
- [ ] queried L1-ready subtasks
- [ ] selected eligible subtask by risk/gate/context rules
- [ ] started it via task-system lifecycle
- [ ] loaded context/source refs
- [ ] ran any governing domain skill needed
- [ ] verified against success_definition
- [ ] completed or patched blocker state
- [ ] checked whether another L1 subtask is now eligible
