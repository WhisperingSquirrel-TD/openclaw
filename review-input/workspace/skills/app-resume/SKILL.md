---
name: app-resume
description: Resume an in-flight app project cleanly. Use when continuing app work after a pause and you need to re-establish scope, status, and next step before touching files.
---

# App Resume

_Last updated: 2026-06-15 14:41_

## Goal
Restart app work from primary evidence instead of guessing where things left off.

## Process
1. Re-state what the project is.
2. Identify the primary raw sources for current state before summarising anything. If the project contains `PROGRESS.md`, read it first; then read the canonical plan/spec, repo status/log, test output, deploy record, and tracker it points to. Treat `PROGRESS.md` as a navigation/resume log, not as a substitute for raw proof.
3. Identify the current phase (plan/build/test/deploy/patch).
4. Confirm what was last completed, citing the proof artifact if one exists.
5. Confirm the immediate next step.
6. State the architect/operator split if scope or product shape is still moving:
   - Tom decides intent, trade-offs, and approval
   - L1 executes, verifies, and escalates ambiguity early

## Rules
- Do not resume a project by guessing from fragments.
- Re-anchor the workflow before making changes.
- Treat an in-flight app/system project as an app project even when the current slice is backend, task-system, or infrastructure work; do not bypass this resume step because the subsystem has its own governing skill.
- Separate raw source from interpreted state: read the live source first, then summarise it.
- **Context-efficient resume rule:** resume from the smallest primary raw artifacts named by the project, using `scripts/README-context-tools.md` for large/unknown files, session history, registries, logs, and test output. Do not reconstruct a project by loading a broad repo, transcript, or session registry into the main conversation. Use a bounded sub-agent only for cross-file investigation and require its compact hand-off schema on every outcome.
- If completion cannot be proven from a current artifact, say "state inferred, not yet proven" rather than upgrading a summary into fact.
- After resume, route implementation through the current phase skill: `app-build` for agreed new implementation, `app-patch` for existing-code changes, `app-test` for verification, and `app-deploy` only after explicit approval.
- Bound automation on resume: only continue autonomously within the already-approved slice; stop and ask before widening scope, changing architecture, or treating ambiguity as permission.

## Model routing pattern (MANDATORY)
Use the `local-llm` route for rough project-state synthesis, first-pass summarisation of recent work, or draft next-step structuring **only when** the work can be kept to one small working slice at a time.
Small slice = one recent log, one doc section, or one clean batch of recent context that can stand alone.
Use the stronger cloud route for final technical judgement, patch plans, and anything where a weak inference could send work down the wrong path.
Do not use the local route for broad cross-project judgement, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
