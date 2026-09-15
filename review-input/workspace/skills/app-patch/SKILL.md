---
name: app-patch
description: Patch an existing app safely. Use when Tom wants a specific change to an existing project and the repo should not be reinitialised from scratch.
---

# App Patch

_Last updated: 2026-06-16 10:01_

## Goal

Make a controlled change to an existing system without confusing "patch" with "new app", while still using the same development checklist spine.

## Process

### Bounded investigation gate (MANDATORY)
Before any recursive search, broad file read, or diagnostic command:
1. name the exact question it must answer;
2. list the smallest relevant source/test directories;
3. exclude session transcripts, generated state, caches, backups and `node_modules` unless they are the subject of the investigation;
4. set an output cap and a timeout appropriate to the bounded search.
If the search scope cannot be stated in one sentence, stop and narrow it before running. Prefer targeted `grep`/file reads over workspace-wide recursion. A timeout or truncated result is `coverage_incomplete`, not permission to repeat the same broad search.

**Mechanism test:** a draft-system caller search must inspect only the draft implementation, its direct caller scripts and focused tests—not `/home/tomdean88/.openclaw` or session logs wholesale.

**Context-tool selection rule (MANDATORY):** For a large/unknown file, JSONL transcript, session registry, log, or command likely to exceed the output cap, use the smallest relevant helper in `scripts/README-context-tools.md` before returning content to the main conversation: `context_extract.py` for a known file slice, `session_query.py` for history, `context_dashboard.py` for session state, and `worker_wrapper.py` for command output. For a cross-file, potentially noisy, or long-running investigation, use an isolated sub-agent with an explicit source allowlist, exclusions, per-source/output caps, and the README's compact hand-off schema. The sub-agent must never return raw tool output; it must provide that compact schema on success, error, **and timeout**. Broad/raw context remains allowed when it is the actual object of work, but must be explicitly deliberate rather than an accidental diagnostic by-product.

## Process

1. Confirm the exact requested change in plain English.
2. Confirm what system/repo this patch belongs to.
3. Re-state the branch: internal Pi/self-build, Tom-owned system, or external/client/project.
4. Name the proof of completion for this patch before editing: what exact behavior, artifact, or state change would prove the request is done.
5. Treat it as a patch, not a rebuild.
6. Keep the scope tight.
6b. **Generality gate:** When the requested system is intended to accept arbitrary work briefs, do not optimise a patch around the current example/task. Define the reusable intake contract first: brief → bounded context packet → work-type interpretation → source-backed work plan → execution/review chain. Use the current case as an acceptance scenario only. A patch is incomplete if it passes the example by hard-coding its client, task, source type, wording, or output shape instead of proving the generic route.
6a. **Operational-system contract gate:** Before inspecting or changing any monitoring, reconciliation, poller, watcher, alert, cron, continuity-state, ledger, or delivery runtime, read the relevant system-specific contract under `reference/OPERATIONAL-SYSTEM-CHARTERS.md` (or create/update one if absent). State its purpose, owner/source of truth, non-goals, invariant, and both happy- and failure-path proof before proposing the technical patch. The contract constrains the patch; do not begin from the nearest script symptom.
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
- **Mutation-authorisation rule (MANDATORY):** every create/update/delete or other state-changing route must enforce authorisation at the server/runtime boundary, not only in the UI or tool definition. Before calling such a patch complete, test the direct mutation path with no TOTP/authorisation and verify a rejection plus no state change; then test the approved path separately. Treat any writable list, endpoint, or callable tool as a high-integrity surface and fail closed when the gate is absent, invalid, expired, or unavailable.
- **Completion-status rule (MANDATORY):** before saying a patch is complete, explicitly state:
  1. where the code lives,
  2. whether it was committed,
  3. whether it was pushed,
  4. whether deploy/restart/reload happened,
  5. what is blocked if any of those did not happen.
- **Chat-usable completion rule (MANDATORY):** if Tom asked for functionality so it can be used from chat/runtime, do not call the patch complete just because the backend/service code exists. Before claiming done, verify the requested capability is actually callable through the user-facing surface Tom will use. If the backend is patched but the live chat/tool surface is still missing, say the work is not complete and keep going or state the exact blocker.
- **Real-work outcome proof rule (MANDATORY):** for an automated user-visible workflow (for example inbound → draft), mocks and synthetic packets prove only component seams. Before claiming the workflow works, run one bounded live acceptance case using a current real source item and verify the promised destination artifact (for example a Drafts-folder-verified Outlook draft ID/link). If the live case returns a retryable coverage/adaptor failure, the workflow remains not operational and the next patch must target that exact hand-off rather than adding more wrapper tests.
- **Exec-gate preparation rule (MANDATORY):** if a patch may need exec/TOTP, do all non-gated work first: read the relevant files, make the code/document edits, decide the exact gated commands, and reduce the gated phase to the minimum necessary validation/restart/apply step. Do not ask for or consume exec gate while still figuring out the plan. Before requesting gate, be able to state the exact minimal gated action list in one sentence.
- **Main-model ownership rule (MANDATORY):** For a user-directed system patch involving high-integrity communication, task routing, authorisation boundaries, or a production recovery, implement and reason through the patch in the current primary cloud session. Do not delegate the patch or its diagnosis to a local LLM as a substitute for this work. A local model may be used only if Tom explicitly requests it and only for a clearly non-authoritative, low-stakes bounded subtask; its output is never source proof or a basis for production changes.
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
- **End-to-end chain-map rule (MANDATORY):** before changing a cross-service operational flow, make a bounded chain map from intake through destination proof: source event → normalisation/router → continuity/ledger gate → worker/runtime trigger → task/queue state → execution context → destination write → post-write verification → user-facing result. Read the canonical system design plus every governing contract for the touched hand-offs. Name which layer owns each transition and the exact happy- and failure-path proof. A local code fix is only a partial patch until the chain map shows its runtime consumer and destination-proof layers are compatible.
- **Patch-context sufficiency gate (MANDATORY):** before editing an existing system, record a compact patch brief from source-backed context: (1) intended end-user outcome, (2) current observed behaviour, (3) canonical design and governing contracts, (4) every runtime consumer/dependent state touched, (5) invariants and non-goals, and (6) end-to-end acceptance and failure cases. If any item is unknown, investigate it before changing code; do not infer it from the nearest failing script or call a local change a fix. For a repeated failure, re-read the brief and relevant runtime evidence before proposing the next modification.
- **Missed-check honesty rule (MANDATORY):** for feed/check systems, never patch toward a fresh-window assumption after a failed or stale run. Patches must preserve the `last successful visible update` model unless Tom explicitly changes that design.
