---
name: task-decompose
description: Decompose captured work into discrete, capability-aware subtasks with clear ownership, tools, risk, review gates, and executable outcomes.
last_edited: 2026-06-27 17:30
---

# Task Decompose

## Purpose
Turn broad work into discrete subtasks that Tom and L1 can actually execute without losing context, blocking unnecessarily, or assigning unsafe work to the wrong owner.

The unit of execution is the **subtask**, not the task.

A task may contain a mix of:
- L1 low-risk subtasks that should be executed autonomously
- L1 medium-risk subtasks that can be prepared/executed but require a sensible Tom oversight checkpoint before the parent task completes
- Tom high-risk subtasks
- Tom-only subtasks because L1 lacks the tool/access/context, even if the risk is low

## Trigger
Use this skill only after the work has been selected for decomposition.

Do **not** run this skill for cheap capture-only task intake. If Tom merely says “add/capture/put this task in the system”, use `skills/task-capture/SKILL.md` and stop unless he explicitly asks to break it down.

Use this skill before committing or materially changing decomposed task-system work when any of these apply:
- Tom explicitly asks to decompose/break down/work the task
- the task is selected as a priority during day/week planning
- a broad task needs breaking down for active execution
- owner/risk/execution mode is being assigned at subtask level
- Tom asks what L1 can do vs what Tom must do
- a task is blocked because capability/tool access was not checked
- a medium/high-risk task needs review gates
- importing selected-priority work from transcripts, CRM, SharePoint, email, GUI/Replit, or planning notes into executable subtasks

## Core rule
Never assign ownership at task level and assume it applies to all subtasks.

For every subtask, decide separately:
1. what exactly needs doing
2. who owns it
3. risk level
4. whether L1 has the tools/access/context
5. execution mode
6. review/approval requirement
7. proof of completion
8. source/provenance

## Decomposition workflow

### 1. Preserve task-level context
Before splitting, identify:
- objective / desired outcome
- task intent
- source material
- constraints
- non-goals
- known deadlines
- relevant people/systems

Do not create tiny subtasks that lose the reason they exist. Each subtask should keep enough parent/source context to be picked up honestly.

**Context-loading completeness rule (MANDATORY):** before marking a decomposed task/subtask `execute_ready`, load the obvious first-hop context required for the first L1 subtask to act. If the task references a known event, talk, invite, meeting, campaign, URL, file, client, contact, company, or source artifact, check the relevant canonical source(s) and attach the findings or mark the missing context as a blocker. For event/invitation tasks, this means checking calendar/source notes/web-visible event links where available and recording at minimum: event name/title, date/time if known, location/format, audience constraint, and URL/booking/promo link if found. Do not make L1 rediscover context that should have been attached during decomposition.

**Internal communication trail rule (MANDATORY):** if the task names or implies a person/company/event organiser/contact, context loading must include a targeted check of available internal communication mirrors for that contact/entity/event before relying on generic web search or memory. Search/read recent sent/inbox/WhatsApp/Teams mirrors for the named contact, company, event title, URL keywords, or obvious related terms; attach any discovered links/logistics/source wording to the parent task/subtask. If the mirrors are unavailable/gated/stale or the target cannot be searched, record `coverage incomplete` or a blocker rather than calling the task fully context-loaded.

**Source-ladder context rule (MANDATORY):** selected tasks are not ready for decomposition just because the latest prompt is clear. Before committing subtasks or marking them `execute_ready`, build a compact source bundle from the relevant first-hop systems. Choose sources based on the task, but the default ladder is:
1. latest user instruction / source artifact that triggered the task
2. memory search (`MEMORY.md` + `memory/*.md`) for prior decisions, preferences, URLs, people, dates, and todos
3. CRM summary (`stackstone/crm.md`) for known accounts/opportunities/leads/contacts and current next steps
4. SharePoint/local SharePoint cache/account-current files for rich entity truth where the task touches a client, opportunity, partner, event, or reusable deliverable
5. communication mirrors (sent/inbox/WhatsApp/Teams) for named contacts, companies, event organisers, URLs, and exact wording
6. operational activity log / task timeline for recent L1 actions or proof state
7. calendar feeds for date/time/location integrity
8. relevant reference/sales/project docs for reusable positioning, campaign/event material, or prior artifacts
9. web search only after internal sources have been checked or explicitly judged insufficient

**SharePoint priority rule (MANDATORY):** when the brief names a client/account/opportunity or asks for a draft/pack/report/recommendation/update built from existing work, treat SharePoint/current files and local SharePoint cache as default first-hop context, not an optional later lookup. The decomposition pass must actively look for prior reports, working drafts, dated communication artifacts, and the entity `Current.md` / equivalent before deciding the task is context-loaded. Do not let the source ladder collapse to CRM + email only when richer SharePoint truth likely exists.

Record the result compactly on the parent task or subtasks: `sources checked`, `key facts found`, `links/artifacts attached`, and `coverage gaps/blockers`. Do not let L1 pickup work that depends on hidden context without either attaching that context or marking the missing source as a blocker/coverage gap.

**Blocker-vs-guidance rule (MANDATORY):** do not turn every ambiguity into a blocker. Before writing `blockers_json`, ask: "Does this prevent the current next internal action, or only affect later external use/review?" If L1 can continue safely by drafting/researching conservatively and leaving the ambiguity for Tom review before send/publish, record it in `current_focus`, `next_action`, or `verified_summary` as guidance/caution rather than `blockers_json`. Use `blockers_json` only when the current next action genuinely cannot proceed without the missing input/access/decision.

### 2. Split by executable action
Each subtask should be one clear executable unit.

Good:
- “Extract meeting actions from transcript into opportunity Current.md”
- “Draft follow-up email for Tom review”
- “Tom approves wording and sends to client”
- “Run backend integration test and capture proof”

Bad:
- “Sort CRM Oxford”
- “Do proposal”
- “Follow up stuff”
- “Make progress”

### 3. Capability/tool-access check
Before assigning `owner: L1`, verify L1 can actually do it with available tools/access.

Check:
- Is there a first-class tool for this? Prefer it.
- Is shell/exec needed, and is a gate/TOTP likely required?
- Is an external send/write involved requiring Tom approval/TOTP?
- Does L1 have the source files or only a claim that they exist?
- Does a specialist governing skill exist?
- Is the relevant API/backend reachable?

If L1 lacks access or the gate is closed:
- either assign to Tom
- or make an L1 preparation subtask plus a separate gated execution/review subtask
- or mark blocked with a concrete unblock condition

### 3a. Gated external action split
If work involves an external send/share/write that ultimately requires Tom approval, TOTP, or a gate, do **not** assign the whole action to Tom.

Split it into:
1. L1 prepares everything safely possible: draft wording, package/file, recipient list, subject, body, attachments/links, send command/path, and proof checklist.
2. Tom reviews/approves/fires the final gated action with TOTP or explicit approval.
3. L1 records proof/updates follow-up state after the send if appropriate.

This applies even when the final send must be Tom-owned. The gate controls the final irreversible action, not the preparatory work.

### 4. Risk classification
Risk is about consequence if wrong, not whether L1 is technically capable.

- `LOW`: contained, reversible, internal, unlikely to damage trust/money/delivery
- `MEDIUM`: meaningful external/live-system consequence but recoverable with review
- `HIGH`: could materially damage trust, client outcome, money, legal/compliance position, or system integrity

### 5. Ownership rule
Apply per subtask:

| Risk / capability | Owner rule |
|---|---|
| L1 can do + LOW | `owner: L1`; L1 should execute without waiting |
| L1 can do + MEDIUM | `owner: L1` for bounded work **only if** the ordered subtask chain includes a later Tom oversight checkpoint covering that L1-medium output before parent completion, unless Tom explicitly waived it |
| HIGH | `owner: Tom` by default |
| L1 lacks tool/access | `owner: Tom` or `owner: L1` blocked/prep-only with explicit unblock |
| Mixed work | split into separate L1/Tom subtasks |

### 6. Medium-risk output oversight checkpoint
If a parent task includes L1-owned medium-risk work, the ordered subtask chain must include a later sensible Tom oversight checkpoint covering the output of that L1-medium work before the parent task can be considered complete, unless Tom explicitly waived review.

This is not one-review-per-medium-subtask. It is an output-oversight rule.

Examples:
- `L1-low → L1-low → L1-low` can complete without Tom oversight.
- `L1-low → L1-medium → L1-low` needs a later Tom oversight checkpoint before parent completion.
- `Tom-high → L1-low → L1-low` does not need another Tom checkpoint just because Tom is already doing the high-risk work.
- `Tom-high → L1-low → L1-medium` needs an extra later Tom oversight checkpoint, because the earlier Tom-high step did not review the later L1-medium output.

Pattern:
1. L1 prepares/drafts/implements bounded medium-risk output.
2. A later Tom-owned review/send/share/approval/input subtask covers that output at the sensible decision point before the action/parent task completes.
3. L1 records proof/updates state after Tom's decision if appropriate.
4. Only then can the parent task move to complete, unless Tom explicitly waived review.

Do not create duplicate Tom review subtasks just because there are multiple L1 medium-risk subtasks if one later oversight checkpoint covers the same output/decision.
Do not count an earlier Tom-owned high-risk subtask as oversight for later L1-medium output.
Do not hide review inside an L1 subtask if Tom has to make a judgement.
Do not mark the parent task complete while L1 medium-risk output has no later Tom oversight checkpoint.

### 7. High-risk default
High-risk work is always Tom-owned unless Tom explicitly delegates a bounded preparation step.

For high-risk work, L1 may still create adjacent low/medium subtasks such as:
- gather facts
- draft options
- prepare comparison
- assemble evidence
- write first-pass wording for Tom review

But the high-risk decision/commit/send/approval remains Tom.

### 8. Required fields for every executable subtask
Each executable subtask must have:
- `title`
- `next_action`
- `success_definition`
- `owner`
- `risk`
- `execution_mode`
- `readiness_state`
- `primary_source_kind`
- `primary_source_ref`
- enough `verified_summary` or parent context to act

If these are missing, the subtask is not execute-ready.

### 9. Recommended execution modes
Use clear modes:
- `do_now` — safe and ready now
- `do_when_gate_open` — needs TOTP/shell/external system gate
- `prepare_for_review` — L1 prepares; Tom reviews before consequence
- `review_with_tom` — Tom judgement required
- `do_later` — intentionally sequenced after another subtask
- `blocked` — cannot proceed until named blocker clears

**Successor-state rule (MANDATORY):** when decomposing a chain like `audit/check -> safe L1 cleanup/update -> Tom review if needed`, do not leave the middle L1 step permanently vague just because it depends on the audit. Choose one of two honest patterns:
1. if the successor is already specific enough and the audit is only confirming safety/scope, make the successor `execute_ready` now and let the operator continue once the audit completes; or
2. if the audit may materially change what the successor even is, encode that explicitly in the successor's `next_action`/`blockers_json`, and require the operating pass that completes the audit to patch the successor into `execute_ready` or `blocked` immediately.

Do not leave a likely next L1 subtask stranded in `planned` after its only real dependency has been resolved.

### 10. Completion proof
Every subtask needs a proof-shaped success definition.

Examples:
- “Integration test passes and gateway route returns 200 for X”
- “Draft email exists for Tom review and references source Y”
- “CRM row has Last Touch and Next Step updated; SharePoint Current.md confirmed”
- “Tom has approved/sent the final message”

## Output checklist before committing subtasks
Before committing a decomposition, verify:
- [ ] Work is split at subtask level, not just task level
- [ ] L1/Tom ownership is assigned per subtask
- [ ] L1 capability/tool access was checked for every L1 subtask
- [ ] Every HIGH-risk subtask is Tom-owned unless explicitly bounded as preparation only
- [ ] If any L1-owned MEDIUM-risk output exists, the ordered subtask chain has a later Tom oversight checkpoint covering that output before completion, unless Tom explicitly waived review
- [ ] Earlier Tom-owned HIGH-risk work has not been incorrectly counted as oversight for later L1-medium output
- [ ] Duplicate Tom review subtasks have been avoided unless there are genuinely separate outputs/decision points
- [ ] LOW-risk L1 subtasks are execute-ready and not blocked by missing context
- [ ] Each subtask has next action, success definition, risk, execution mode, and source ref
- [ ] Any subtask expected to create a durable document/output says in its success definition that the artifact must be linked on the producing subtask and rolled up to the parent task `links_json`; if Tom must review it, the Tom-review subtask should also receive the artifact link
- [ ] Parent task retains enough context to keep the subtasks coherent
- [ ] Dependencies/sequencing are reflected in execution modes or next actions
- [ ] If any L1-owned subtask is immediately eligible for pickup, the parent task is in an operator-admissible state (`open` or `active` in the current runtime contract), `operator_signal` has been called, and live operator/checker readback proves both `work_waiting=true` and that the intended subtask is eligible/admissible before claiming it will be picked up on the next cycle

## Post-commit operator signal rule (MANDATORY)
When decomposition creates or updates any subtask that is:
- `owner=L1`
- `state=todo` or equivalent active subtask state
- `execute_ready=true`
- not blocked
- within allowed operator risk/mode guardrails

then the decomposition pass is not complete until the pickup path is signalled and verified:
1. Confirm the parent task is in an operator-admissible state. In the current runtime contract, parent task `todo` is **not enough** for autonomous pickup; use `open` or `active` unless/until the operator spec changes.
2. Call `task_system operator_signal` for the parent task, naming the eligible L1 subtask/reason.
3. Immediately read `task_system operator_state` and, where available, run a checker/admission readback.
4. Confirm `work_waiting=true` **and** that the intended L1 subtask appears as eligible/admissible, or that the only blocker is a temporary admission condition such as CPU load.
5. If `work_waiting=false`, the intended subtask is not eligible, or parent state is wrong, fix that state once or report the exact blocker; do not merely say the subtask is ready for next cycle.

Do not treat a previous successful `operator_signal` call as durable proof after another operator cycle has run. Do not treat `work_waiting=true` alone as proof of pickup readiness. The source of truth for “will be picked up next cycle” is current live operator state plus checker/admission evidence that an intended L1 subtask is eligible under the current parent-task state and risk/mode rules.

## Input impact / chain-repair rule (MANDATORY)
If Tom or the GUI adds any note/input/clarification/change request/rollback to a task or subtask, reassess the decomposition before continuing. Treat the input as new source material, not passive commentary.

Cross-reference: `projects/workspace-control-panel/TASK_EXECUTION_CONTEXT_CONTRACT.md` — execution should use reconstructed task context, not inherited chat context.

Assessment questions:
- Does this change the task intent or desired outcome?
- Does it change the next action, output format, audience, recipient handling, BCC/CC/send route, approval route, blockers, dependency order, success definition, or risk?
- Does it make any already-done output stale, conditional, or superseded?
- Does it mean a downstream Tom review/send/reconciliation subtask should wait?

Outcomes:
- No chain impact: keep as context and continue.
- Minor local rework: patch only the affected subtask and parent context if downstream outputs remain valid.
- Major rework: if downstream completed/review subtasks depend on the changed upstream output, move or mark those affected subtasks back to `todo`/waiting/rework as appropriate, or clearly mark their outputs stale pending the revised upstream result.
- Restart/refactor: block the affected chain and wait for Tom/refactor rather than letting L1 continue stale subtasks.

After chain repair, re-signal the operator if any L1-ready work remains.

## If uncertain
If capability, risk, or ownership is unclear:
- split preparation from decision
- assign preparation to L1 if safe
- assign decision/approval to Tom
- mark uncertainty in blockers or verified/inferred summary

Do not leave ambiguity hidden in a broad task.
