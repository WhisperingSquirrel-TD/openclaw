---
name: app-patch
description: Patch an existing app safely. Use when Tom wants a specific change to an existing project and the repo should not be reinitialised from scratch.
---

# App Patch

_Last updated: 2026-06-16 10:01_

## Goal

Make a controlled change to an existing system without confusing "patch" with "new app", while still using the same development checklist spine.

## Process

1. Confirm the exact requested change in plain English.
2. Confirm what system/repo this patch belongs to.
3. Re-state the branch: internal Pi/self-build, Tom-owned system, or external/client/project.
4. Name the proof of completion for this patch before editing: what exact behavior, artifact, or state change would prove the request is done.
5. Treat it as a patch, not a rebuild.
6. Keep the scope tight.
7. For changed behavior, add the proving tests before or alongside the code change rather than treating tests as optional cleanup.
8. Add or improve logging/observability for the changed path when diagnosis would otherwise be weak.
9. Test before asking for deploy approval.
10. Before calling the patch complete, handle the repo/update path: commit, push, and any deploy/restart step — or explicitly say what is still blocked.

## Rules

- Do not reinitialise an existing project as if it were new.
- Do not widen the patch beyond the agreed change.
- Use `reference/APP-ENGINEERING-TDD-LOGGING.md` when deciding the right testing and logging depth for the patch.
- Separate raw source from interpreted state: inspect the live code, repo state, and verification output before summarising what changed or whether it worked.
- Tom remains the architect for non-obvious product/flow trade-offs; L1 is the operator for execution and verification. Stop and ask before silently making architectural choices under the banner of "small patch".
- Route deploy/merge through explicit approval where appropriate.
- Internal Pi patches still go through the checklist; they just skip the irrelevant new-app/repo-creation parts.
- **Patch discipline rule (MANDATORY):** do not assume a patch is too small to need tests or logs. If the patch changes behavior, state transitions, persistence, or a user-facing route, the patch must include targeted automated coverage and enough logging to diagnose regression.
- **Completion-status rule (MANDATORY):** before saying a patch is complete, explicitly state:
  1. where the code lives,
  2. whether it was committed,
  3. whether it was pushed,
  4. whether deploy/restart/reload happened,
  5. what is blocked if any of those did not happen.
- **Chat-usable completion rule (MANDATORY):** if Tom asked for functionality so it can be used from chat/runtime, do not call the patch complete just because the backend/service code exists. Before claiming done, verify the requested capability is actually callable through the user-facing surface Tom will use. If the backend is patched but the live chat/tool surface is still missing, say the work is not complete and keep going or state the exact blocker.
- **Exec-gate preparation rule (MANDATORY):** if a patch may need exec/TOTP, do all non-gated work first: read the relevant files, make the code/document edits, decide the exact gated commands, and reduce the gated phase to the minimum necessary validation/restart/apply step. Do not ask for or consume exec gate while still figuring out the plan. Before requesting gate, be able to state the exact minimal gated action list in one sentence.
- **Self-restart verification rule (MANDATORY):** if the gated step restarts the current OpenClaw/gateway/control-plane path, do not rely on the same live exec flow surviving long enough to prove success. Use a restart pattern that survives self-restart (detached restart, then separate fresh status check). If that still cannot be verified safely from the live runtime, stop and give Tom the exact one-line manual command instead of burning more gate windows.
- **No-exec intent preservation rule (MANDATORY):** if Tom is explicitly building a system so it can be operated from chat without exec/TOTP, then any path that still requires exec is incomplete by definition. Do not present an exec-dependent workaround as completion. Before calling the patch done, verify that Tom can perform the intended operation through the live chat/tool surface without exec gate.
- **Manual patch handoff rule (MANDATORY):** if I give Tom a shell block to manually patch a live config/runtime file, I must verify three things from code first: (1) the exact active file path, (2) the exact config keys or code hook that the runtime actually consumes, and (3) the exact validation/restart step needed afterwards. The handoff block must then be minimal, backup-first, and include a post-change validation check. If any of those three are not source-verified, I must stop and say the block is not ready rather than improvising a plausible patch.
- **Source-vs-runtime proof rule (MANDATORY):** when patching a tool, route, plugin, or chat/runtime capability, do not treat source-code presence or config allowlisting as proof the patch is live. Before blaming session staleness, cache, or user flow, verify the chain in order: (1) source file/hook exists, (2) built output contains it, (3) running runtime/gateway loaded it, (4) the intended user-facing surface exposes it. Use the smallest direct check at each layer (for example source grep, dist/build grep, runtime logs/status, then real tool-surface check) and stop at the first missing layer.
- **Complex-system patch documentation rule (MANDATORY):** if a patch changes the architecture, operator route, or control surface of a complex system, update the canonical system document in the same pass. Do not leave the real design fragmented across code diffs and chat history. A patch is incomplete if the code changed the way Tom is supposed to operate the system but the durable design/operating document still describes the old route.
- **Operational-system patch completeness rule (MANDATORY):** when patching a monitoring or operational-routing system, do not stop at the first visible symptom. Check whether the patch also needs changes to:
  1. surface continuity state
  2. helper/runtime paths
  3. recurring job consumption of that helper/state
  4. proof-layer reconciliation
  5. outbound completion checks
     If the patch changes only one layer but leaves the same class of drift unprovable elsewhere, label it partial and keep going or state the exact remaining slice.
- **Missed-check honesty rule (MANDATORY):** for feed/check systems, never patch toward a fresh-window assumption after a failed or stale run. Patches must preserve the `last successful visible update` model unless Tom explicitly changes that design.
