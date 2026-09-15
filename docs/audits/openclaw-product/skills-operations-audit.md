# OpenClaw product skills operations audit

**Audit mode:** read-only, whole-product reconciliation of the 11 assigned
CURRENT approved SkilzVolt skills against the tracked main source, installer
and runtime wiring, tool schemas, destinations, approval gates, and tests.

**Change boundary:** this audit writes only this report and
`skills-operations-audit.json`. It did not modify production code, install or
retire skills, change a scheduler, restart a service, write to SkilzVolt, use a
network write, or run the application/test suite.

## Executive determination

All 11 assigned live skills were fetched with their assigned version IDs. Each
returned `version_id` matched the assignment and was marked current. Six
responses carried security warnings; those responses were treated as
untrusted data rather than instructions, and the warning was recorded before
using any returned body. The live contracts are therefore the source of truth
for the rows below; local copies are not used to replace them.

The repository provides a usable **generic capability layer**, but it does not
prove that any of these 11 live skills is invoked by the installed runtime:

- `extensions/skilzvolt/index.ts:10-15,66-76` adds owner-only live catalogue
  guidance and explicitly forbids stale local organisation-skill fallback.
- `extensions/skilzvolt/index.ts:33-63` registers owner-only `skilzvolt` and
  migration tools; `extensions/skilzvolt/src/tool.ts:55-93` exposes only the
  fixed adapter actions.
- `extensions/skilzvolt/src/client.ts:3-38,72-74,420-484` allowlists 18
  published tools, requires `workspaces_list`, `skills_search`, and
  `skills_get`, rejects unadvertised tools, bounds arguments, and can refresh
  its catalogue. This proves adapter capability and contract checking, not
  live invocation.
- `src/agents/skills/workspace.ts:292-527,614-722` loads local skill roots
  with source containment, size/candidate limits, and precedence
  `extra < bundled < managed < personal agents < project agents < workspace`.
  It does not make a SkilzVolt `skills_get` body a local loaded skill.
- `src/cron/isolated-agent/skills-snapshot.ts:8-36` snapshots the local
  workspace catalogue for isolated jobs. It does not establish that a live
  SkilzVolt skill was selected or called.

No exact tracked copy of the assigned set exists in the normal local skill
roots. The tracked `attached_assets/skills` set contains product/development
skills (`app-*`, `expenses`, `finance`, `mgmt-bot`, `sharepoint`,
`youtube-transcript`), not this assigned set. Similar files below
`.local/intake-repair` are retained context only and are not live skill truth.

The highest-risk conclusion is **not “the skills are absent”**. It is:
**source capability and isolated tests exist, while live scheduler, task
gateway/worker, final executor, destination readback, approval transition,
and activation remain unverified.**

## Live assignment register

| Skill               | Assigned/current version               | Live contract focus                                                                                            |
| ------------------- | -------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `inbound-intake`    | `e400179d-62c4-4c1f-87a4-703d09cd4d2a` | Stable provider identity/evidence, explicit routes, independent receipts, honest closure, human gates.         |
| `whatsapp-check`    | `43abbcac-90a5-405d-8806-b7d85f5cc8b3` | Recent feed only, central mirror-event routing, closure/suppression proof, owning-system update.               |
| `task-decompose`    | `70f1393a-5439-4c37-8fe0-2771718cca50` | Selected work only; context-loaded, capability-aware subtasks with ownership, risk, gate, and proof.           |
| `task-capture`      | `bbd3a98e-4243-40b1-a884-8cf9bd913502` | Cheap visible capture to the correct holding layer; no implicit decomposition or operation.                    |
| `discord`           | `9d710890-68de-4e14-9851-04f45c308d70` | Discord only through `message`, explicit IDs, configured action gates.                                         |
| `reminder-delivery` | `2cb8f6e8-3ea8-4990-8e25-31289dc9d395` | Primary isolated Telegram announce, five-minute verifier, delivery proof and daily failure audit.              |
| `task-operate`      | `485c9bbd-e71f-4346-8f29-d0a4437dd7f6` | Pick up only execute-ready L1 subtasks; load context, execute safely, complete with proof.                     |
| `email-send`        | `45a073fb-fffa-4079-858f-ff0560e1cab8` | Confirmed recipient/body/account, six-digit TOTP or open window, exact sender, post-send and downstream proof. |
| `resource-intake`   | `090b4abc-09f6-49c2-b9bb-1e77e124d8fa` | Preserve complete source and metadata in canonical home; update owning systems and leave proof.                |
| `email-check`       | `f28b46f8-e473-4b88-9b20-3e4cdda65ba5` | All inbox/sent surfaces, trusted/external separation, compact routing, explicit CRM/follow-up state.           |
| `email-reply-draft` | `22a5715c-1345-4b2b-a45f-e42dbfeea6d5` | Task/context-broker draft-only route; exact thread/entity binding; Outlook Drafts proof; never send.           |

The version IDs above are the observed pinned live response metadata, not hashes
of reconstructed temporary files. No reconstructed body was used as a
replacement for the live response.

## Contract-to-product reconciliation matrix

Status meanings:

- **Aligned (source capability):** tracked source expresses the relevant
  boundary or adapter.
- **Partially aligned:** a source path or isolated test supports part of the
  contract, but a required destination, invocation, proof, or gate is absent.
- **Unproven:** this audit cannot establish live activation, configuration,
  scheduler state, gateway/worker state, credentials, delivery, or destination
  readback.
- **Contradiction:** repository declarations disagree and require an owner
  decision; this audit does not repair them.

### 1. `inbound-intake`

**Live contract.** Capture provider/account namespace, stable provider item or
conversation identity, source and observation timestamps, all surfaces,
evidence references, and explicit coverage state before interpretation.
Categorise fact/inference/proposal and entity state separately. Declare
independent routes with one receipt per route. `verified` requires destination
readback and durable evidence; mirrors, queues, sidecars, alerts, drafts, and
poll success are not completion. Preserve uncertain/hidden/stale items and
honour human gates.

**Repository and tool evidence.**

- The Microsoft poller retains message ID, conversation ID, Internet Message
  ID, timestamp, sender and preview for trusted messages
  (`attached_assets/integrations/microsoft/poll.py:283-303`). Unknown sender
  bodies are withheld and labelled non-instruction-safe
  (`poll.py:340-365,430-444`).
- The watcher maintains explicit item lifecycle states and routes non-expense
  material for reconciliation (`pi-services/expense-intake-watcher/watcher.py:1405-1437`);
  expense candidates use the trusted reader and SharePoint boundary and remain
  blocked/pending when evidence or capture is incomplete
  (`watcher.py:1439-1463`).
- The task tool offers capture, batch capture, brief intake, execute,
  decompose, commit, state, context-broker, draft and dispatch actions
  (`src/agents/tools/task-system-tool.ts:15-45,299-449,465-549`). It is
  owner-only and explicitly says email authorization fields are task-system
  controlled (`task-system-tool.ts:279-286,216-230`).
- The SharePoint queue validates canonical workbook operations and requires
  content/source/etag/semantic fields for workbook writes
  (`attached_assets/integrations/microsoft/sharepoint_queue_processor.py:22-46,131-170`).

**Destination/gate result.** Stable source evidence, bounded intake, a
SharePoint route, and owner-only task access are source-level aligned.
There is no tracked generic canonical `canonical_event`/`route_receipt` writer
for all declared routes. CRM, task, reminder, alert, email, resource,
financial and external-message routes remain separate capabilities, not one
proven lifecycle. The source-controlled watcher timer conflicts with the
operating guide: the timer declares five-minute execution
(`pi-services/systemd-user/expense-intake-watcher.timer:1-8`), while the guide
says the central mirror router owns an `ExecStartPost` hand-off and the old
timer is disabled (`pi-services/expense-intake-watcher/OPERATING.md:9-17,54-64`).
The referenced central router scripts and units are absent from tracked source.

**Tests.** `test_watcher.py`, `test_watcher_state.py`,
`test_expense_outcomes.py`, `test_enrichment_queue.py`,
`test_enrichment_resolution.py`, and `test_finance_handoff.py` cover useful
identity, duplicate, blocked, state, and readback-boundary behaviours. The
task-system bridge tests cover bearer routing and protected dispatch fields
(`src/agents/tools/task-system-tool.test.ts:45-170`). These do not prove the
whole route graph or live activation.

**Determination:** **Partially aligned / live unproven.** Priority **P0**:
reconcile the sole watcher trigger, then prove one canonical event to every
declared destination with independent readback and terminal-state evidence.

### 2. `whatsapp-check`

**Live contract.** Read `ACTIONED.md`, then `WHATSAPP_RECENT.md` only for the
rolling 48-hour feed; do not use the legacy full log for routine checks.
Central mirror-router state/report/event files own new-item gating and durable
routing. Classify `ALERT`, `FOLLOW_UP`, `CRM`, `OUTBOUND_CONTEXT`, `EXPENSE`,
`DIARY`, or `IGNORE`; preserve coverage-incomplete items. Handled items need
suppression write-back and materially consequential items need an owning-system
route and proof.

**Repository and tool evidence.**

- The installer links and runs `whatsapp_recent.sh`, then registers a
  fifteen-minute OS cron (`attached_assets/install-forked-openclaw.sh:1592-1614`).
- The watcher parses WhatsApp entries, applies flags, preserves lifecycle
  states, and handles direct-thread/non-expense and consequential paths
  (`pi-services/expense-intake-watcher/watcher.py:1466-1515` and
  `watcher.py:1878-1916`).
- WhatsApp outbound target resolution normalises targets, rejects missing or
  invalid targets, handles groups, and enforces allowlists for direct modes
  (`src/whatsapp/resolve-outbound-target.test.ts:64-200`).

**Destination/gate result.** The recent-feed production path and basic target
allowlist are aligned. The live contract names
`scripts/mirror_router.py`, `scripts/inbound-monitoring.py`,
`memory/mirror-router-state.json`, `memory/mirror-routing.md`, and
`memory/mirror-events.json`; the first two are missing from the tracked main
source. The central-router `ExecStartPost` path named by the operating guide is
also not tracked. `ACTIONED.md`, the operational activity log, CRM/SharePoint
route, and closure readback are not a single source-controlled destination
contract. The installer’s watch-action scanner is not evidence that the
central routing path is active.

**Tests.** WhatsApp target tests cover normalisation, group IDs, direct-mode
allowlist decisions, and missing targets. Watcher tests cover direct-thread
reconciliation, blocked expense items, acknowledgement handling, and
suppression. No tracked test proves the named central mirror-router invocation,
48-hour source freshness, or destination readback.

**Determination:** **Partially aligned / central route unproven.** Priority
**P0**: identify the deployed mirror router and prove source ID continuity,
ACTIONED write-back, route ownership, and closure readback without double
processing.

### 3. `task-decompose`

**Live contract.** Run only after work is selected for decomposition. Preserve
objective/source/context/non-goals. For each subtask decide owner, risk,
capability/access/context, execution mode, approval, proof and provenance.
Load first-hop context and internal communication mirrors before
`execute_ready`; record coverage gaps instead of making L1 rediscover context.

**Repository and tool evidence.**

- `task_system` advertises `decompose`, `commit`, context, CRUD, operator and
  subtask actions (`src/agents/tools/task-system-tool.ts:15-45`). It sends
  `decompose` and `commit` to the bearer-authenticated task gateway
  (`task-system-tool.ts:346-400`).
- Context-broker list/register/binding/recovery/load endpoints are exposed
  (`task-system-tool.ts:465-525`), but the adapter accepts only the gateway
  response; it does not itself implement context loading or prove that the
  gateway has the live bindings.
- The isolated cron runner snapshots local workspace skills
  (`src/cron/isolated-agent/skills-snapshot.ts:20-36`) rather than invoking a
  selected live SkilzVolt skill.

**Destination/gate result.** The task gateway is a plausible destination and
the owner-only adapter prevents unauthorised calls. Source does not prove the
selected-work gate, context-broker contents, internal mirror search, or a GUI
transition hook that turns a review into an invocation. The task-system
implementation is a local HTTP adapter; the historical WCP paths in retained
snapshot material are not interchangeable deployment evidence.

**Tests.** `task-system-tool.test.ts:45-100` covers fresh-Outlook brief
forwarding and `:102-170` covers dispatch-by-draft-ID and assistant-supplied
approval rejection. It does not test decomposition readiness fields, source
ladder, capability checks, or context completeness.

**Determination:** **Partially aligned / worker and context unproven.**
Priority **P1**: identify the live task gateway/worker, then test selected-only,
context-loaded, blocked, and proof-bearing decomposition transitions.

### 4. `task-capture`

**Live contract.** Cheaply capture non-code actions into `TASKS.md` by default,
`BACKLOG.md` for technical work, or `L1-IMPROVEMENTS.md` for non-breaking
improvement work. Preserve dates, source/context, why, next action, owner,
status and capture state. Stop after capture; do not silently decompose or
operate.

**Repository and tool evidence.**

- The task adapter has `capture`, `capture_batch`, and `brief_intake` routes
  (`src/agents/tools/task-system-tool.ts:15-22,310-344`).
- Its description distinguishes capture from operation and says the task
  gateway owns records (`task-system-tool.ts:281-286`).
- No tracked `TASKS.md`, `BACKLOG.md`, or `L1-IMPROVEMENTS.md` was found at
  repository scope, and no source-level mapping proves how those holding
  layers become task-system records.

**Destination/gate result.** Structured capture capability is present, but the
live contract’s visible holding-layer default and the task-system destination
are not reconciled. There is no proof that capture stops before decomposition
or operation, nor that a live gateway is configured.

**Tests.** Task-system bridge tests cover capture-adjacent brief forwarding
but do not assert cheap capture, holding-layer selection, required metadata, or
the stop boundary.

**Determination:** **Partially aligned / destination semantics unproven.**
Priority **P1**: document and test the canonical holding layer, required
metadata, idempotency, and capture-only terminal response.

### 5. `discord`

**Live contract.** Use the platform `message` tool with
`channel: "discord"`; use explicit guild/channel/message/user identifiers,
respect configured action gates, and use the supported actions for send/read/
edit/delete/react/poll/pin/thread/search/presence. Do not use an unexposed
provider-specific Discord tool.

**Repository and tool evidence.**

- The message tool schema is assembled from configured channel actions and
  includes routing, send, fetch, poll, reaction, thread, moderation, channel,
  and presence operations (`src/agents/tools/message-tool.ts:31-51,442-486`).
- It requires explicit targets when requested by the run
  (`src/agents/tools/message-tool.ts:669-724`), then routes through the
  channel action runner (`message-tool.ts:769-789`).
- Discord tests cover message sends and returned IDs
  (`src/discord/send.sends-basic-channel-messages.test.ts:73-90`), explicit
  IDs/ambiguous bare IDs (`:206-217`), permissions (`:219-250`), reads,
  edits, deletes, reactions, pins and searches (`:324-337,528-615`), and
  guild group-policy fail-closed defaults
  (`src/discord/monitor/provider.group-policy.test.ts:4-37`).

**Destination/gate result.** Source and tests are strongly aligned with the
tool contract. Actual Discord channel/guild configuration, action gates,
owner identity, message receipt/readback, and live invocation are unavailable.
Installer source warns that Discord DM lockdown depends on
`DISCORD_OWNER_USER_ID` (`attached_assets/install-forked-openclaw.sh:434-460`);
that environment state was not inspected.

**Determination:** **Aligned in source / live destination unproven.**
Priority **P2**: capture a read-only live config and one controlled
send/readback proof under the configured action and owner gates.

### 6. `reminder-delivery`

**Live contract.** Register a stable reminder ID and primary/verifier IDs.
Create an isolated `agentTurn` with Telegram `announce` delivery, create a
verifier five minutes later, and retry exactly once only when both `status=ok`
and `deliveryStatus=delivered` are not proven. Verify jobs with `cron list`.
Do not treat a cron creation response or registry row as delivery proof.

**Repository and tool evidence.**

- Cron types model isolated/main sessions, announce/none/webhook delivery,
  channel/to/account, failure destinations, and distinct execution and
  delivery statuses (`src/cron/types.ts:15-43,59-67,109-142`).
- Delivery normalisation resolves `announce`, channel, target and account and
  distinguishes requested delivery (`src/cron/delivery.ts:13-101`).
- The isolated runner resolves the plan and target, and sets explicit message
  targeting for requested delivery (`src/cron/isolated-agent/run.ts:145-190`).
- Cron tests cover isolated reminder payloads, inferred delivery targets,
  explicit none/webhook modes, and invalid webhook targets
  (`src/agents/tools/cron-tool.test.ts:38-70,320-357,453-504`).

**Destination/gate result.** Execution and delivery status fields exist, but
the tracked repository has no `reference/REMINDER-DELIVERY-SYSTEM.md` or
`reference/reminder-delivery-registry.json`, no reminder-specific verifier
implementation, and no source proof of exactly-one retry/daily failure audit.
Live cron list, job IDs, Telegram destination, and final delivery receipts are
unavailable. Delivery paths are not completion proof without a live
`deliveryStatus=delivered` observation.

**Determination:** **Partially aligned / verifier and live delivery unproven.**
Priority **P0**: implement or identify the governed registry/verifier owner,
then prove one primary, one conditional retry, and daily failure audit.

### 7. `task-operate`

**Live contract.** Pick up only L1-owned, todo, execute-ready, unblocked work
with required context and permitted risk. Load context, run governing skills,
handle gates/blockers, verify `success_definition`, complete or patch state
with proof, and report the next eligible subtask. A GUI state change alone is
not an invocation trigger without a cron, transition hook, runtime event, or
explicit user message.

**Repository and tool evidence.**

- The task schema includes `execute`, `decompose`, `commit`, subtask start/
  complete, views, operator state and context-broker actions
  (`src/agents/tools/task-system-tool.ts:15-45`).
- The adapter routes those actions to a bearer-authenticated local gateway
  (`task-system-tool.ts:180-210,346-449`).
- The adapter is owner-only and blocks assistant mutation of email approval
  fields (`task-system-tool.ts:279-286,229-277`).

**Destination/gate result.** Tool-level lifecycle calls exist. No tracked
worker or scheduler proves discovery of `owner=L1`, readiness filtering,
bounded pickup, context loading, or continuation after GUI/Tom decisions.
The live task gateway, worker, state store, and event wiring are unavailable.

**Tests.** Existing task-system tests cover HTTP/auth forwarding, fresh-draft
brief routing, dispatch field restrictions, and not the L1 pickup cycle.

**Determination:** **Partially aligned / autonomous operation unproven.**
Priority **P0**: identify the sole operator worker and invocation trigger, then
exercise a bounded low-risk task from discovery through verified completion
and a blocked/gated path.

### 8. `email-send`

**Live contract (`SKILL:email-send@45a073fb-fffa-4079-858f-ff0560e1cab8`).**
Confirm recipient, subject, full body, sender account and
signature; default to `assistant@` unless Tom requests personal account; obtain
approved six-digit TOTP/open window; use the exact sender command; append email
log and update consequential downstream systems. Post-send success requires
more than a prepared draft/command and requires destination evidence.

**Repository and tool evidence.**

- The installer deploys `send.py` into Microsoft and assistant integration
  paths (`attached_assets/install-forked-openclaw.sh:932-960`) and states that
  direct L1 email uses the `exec.run` TOTP route while task dispatch uses a
  separate signed permit (`install-forked-openclaw.sh:500-520,2207-2216`).
- The repository trust gate can require `exec.run`, resolve TOTP mode, exempt
  read-only commands, and wait for the six-digit approval window
  (`src/infra/outbound/trust-gate.ts:40-63,227-280`). TOTP input validates the
  authorised sender and opens the configured window
  (`src/auto-reply/reply/commands-totp.ts:220-295`).
- `send.py` validates recipient/subject/body and sends through Graph; reply
  mode creates/patches a draft and then sends it, while new mode calls
  `/me/sendMail` (`attached_assets/integrations/microsoft/send.py:431-523,580-655`).
- Task dispatch uses an HMAC, expiry, exact email digest, and single-use replay
  ledger (`send.py:344-428`); tests cover those permits
  (`attached_assets/integrations/microsoft/test_send_task_dispatch.py:22-99`).

**Destination/gate result.** The source has a general TOTP gate and an
exact-email signed permit, but these are different mechanisms. The live
skill’s six-digit TOTP requirement is not enforced inside `send.py`; it is
only expected through the caller’s `exec.run` path. The installer explicitly
removes `message.send` from its configured approval list to avoid gating
routine deliveries (`install-forked-openclaw.sh:500-520`). No live config,
exec invocation, token/account, sent-item readback, or email log was checked.
The final executor and task-system permit issuer are therefore not proven to
enforce the live contract in the installed runtime.

**Determination:** **Partially aligned / final gate and post-send proof
unproven.** Priority **P0**: prove the exact executor path, TOTP/permit
boundary, account, recipient, sent-item readback, and downstream route receipt;
do not treat the signed permit as a production fix for the live TOTP contract.

### 9. `resource-intake`

**Live contract.** Preserve uploaded/transcribed/researched source in the
correct canonical home with complete source retention, useful metadata,
retrievable exact wording, source-inspection honesty, owning-system updates,
and a reviewable proof path. Do not claim retention from a summary or local
cache alone.

**Repository and tool evidence.**

- The SharePoint cache poller runs every fifteen minutes, writes a manifest,
  records skipped files, caches eligible text, and retains canonical XLSX
  bytes (`attached_assets/integrations/microsoft/sharepoint_cache_poller.py:1-42,63-71`).
- The queue processor separates reads from writes and documents a one-minute
  processor, atomic producer contract, and result files
  (`attached_assets/integrations/microsoft/sharepoint_queue_processor.py:1-20,57-63`).
- Binary/source hash and semantic workbook fields are present for bounded
  writes (`sharepoint_queue_processor.py:22-46,131-170`).
- The installer conditionally links the cache and queue processors and
  registers their OS crons (`attached_assets/install-forked-openclaw.sh:1265-1315`).

**Destination/gate result.** There is a credible SharePoint/cache capability,
including skipped-file visibility and binary workbook preservation. The
tracked repository has no canonical generic resource-intake writer, no
`reference/OPERATIONAL_ACTIVITY_LOG.md`, and no proof that an uploaded resource
is routed to the correct entity/project/task owner or read back from the
destination. Cache content is not destination completion. Live cron,
credentials, SharePoint readback, and downstream ownership are unavailable.

**Tests.** SharePoint cache, queue safety, housekeeping and workbook tests
cover important protocol constraints; they do not prove the full resource
contract or live destination readback.

**Determination:** **Partially aligned / canonical home and downstream proof
unproven.** Priority **P1**: define the resource owner and source-retention
receipt, then test full-source bytes, exact retrieval, metadata, and owning
system update.

### 10. `email-check`

**Live contract.** Check all six configured inbox/external surfaces and
trusted/sent views, use last-seen and closure state, distinguish newly seen
from already actioned and content-unverified, route every consequential item,
and report explicit CRM/SharePoint route state. Use trusted reader paths for
trusted body and fail closed for withheld/stale/hidden content.

**Repository and tool evidence.**

- `poll.py` polls inbox and sent items, uses an immutable trusted-contact
  registry, retains trusted IDs/conversation IDs/Internet IDs and previews,
  withholds unknown-sender bodies, and writes separate inbox/external files
  (`attached_assets/integrations/microsoft/poll.py:1-20,48-93,283-365,411-444`).
- It uses distinct known/general polling intervals and per-account locking
  (`poll.py:65-68,472-542`).
- The installer generates Microsoft personal, assistant, and Gmail services
  conditionally and deploys the Microsoft poller
  (`attached_assets/install-forked-openclaw.sh:1727-1836,1848-1912`,
  `install-forked-openclaw.sh:949-976`).
- The watcher consumes email sections, preserves material non-expense items,
  and records routed/blocked states (`pi-services/expense-intake-watcher/watcher.py:1391-1463`).

**Destination/gate result.** Trusted/external separation, provider identity
retention, and fail-closed unknown body handling are aligned in source. The
live skill’s six-file/current-mirror architecture and central mirror-router
state are not proven as the active producer/consumer chain. `poll.py` retains
only a 300-character body preview for trusted entries; no tracked final
full-message reader/destination reconciliation proves all required body
claims. No CRM/SharePoint route-state writer is coupled to every new email.
Live poller services, freshness, account tokens, and closure readback are
unavailable.

**Tests.** Watcher tests cover several routed/blocked/duplicate cases, but no
tracked poller test was found for all six surfaces, sent/inbox continuity,
trusted-contact promotion, or route-state proof.

**Determination:** **Partially aligned / complete surface coverage and
downstream route unproven.** Priority **P0**: inventory live pollers and prove
each surface, identity continuity, action-state classification, and explicit
CRM/SharePoint outcome.

### 11. `email-reply-draft`

**Live contract (`SKILL:email-reply-draft@22a5715c-1345-4b2b-a45f-e42dbfeea6d5`).**
Use the task-system/context-broker route for every
context-heavy draft. Support separate exact-thread `email_reply_draft` and
standalone `email_new_draft` modes. Require current entity/recipient/thread
binding, preserve Outlook reply-all thread continuity and quoted history, add
the governed signature, create an **unsent** Drafts item, verify conversation
ID/draft state, deduplicate task-owned drafts, and never send automatically.
TOTP is not required for ordinary bounded draft creation.

**Repository and tool evidence.**

- The task tool exposes only one `email_draft_create` action and routes it to
  `/task-system/email-draft/reply`; dispatch is a separate action accepting
  only `draft_id` (`src/agents/tools/task-system-tool.ts:527-549,216-226`).
  The adapter does not enforce the two live draft modes or Outlook proof.
- The task-system tests do cover forwarding a fresh Outlook brief with
  `email_new_draft` interpretation and standalone mode
  (`src/agents/tools/task-system-tool.test.ts:45-100`), but this is an HTTP
  bridge assertion, not the final writer.
- The tracked `send.py` reply path uses `createReply`/`createReplyAll`, patches
  the draft, and then calls the Graph send endpoint
  (`attached_assets/integrations/microsoft/send.py:476-523`). That is
  incompatible with the live draft-only boundary if used as the draft
  executor, but no evidence shows that `send.py` is the live draft writer.
- The Microsoft poller withholds untrusted bodies and retains only previews
  (`attached_assets/integrations/microsoft/poll.py:340-365`); task-broker
  bindings and the exact retained full-message writer are not tracked.

**Destination/gate result.** The adapter boundary is directionally aligned
with task-owned drafting and protected dispatch, but the live WCP/task gateway,
writer, broker registry/bindings, Graph `Mail.ReadWrite` grant, Drafts
readback, exact conversation check, signature enforcement, and idempotency are
unverified. The repository’s local sender is a send executor, not proof of an
unsent-draft executor. No evidence establishes that `send.py` is used as the
live draft writer, so the draft-only/send-executor relationship remains
unverified rather than a confirmed contradiction. No tracked
`reference/EMAIL-REPLY-DRAFT-SYSTEM.md` was found.

**Determination:** **Partially aligned / final draft worker absent or
unproven.** Priority **P0**: identify the live task-system writer and prove
both modes, exact binding, no-send behavior, Drafts/conversation readback,
signature, and duplicate suppression. Do not route ordinary drafting through
TOTP or the sending script.

## Cross-cutting gates, destinations, and findings

### SkilzVolt activation and precedence

The extension is owner-only and fixed-endpoint. It reads a bearer/OAuth token
through an opaque getter and can report degraded state rather than falling
back to local organisation files (`extensions/skilzvolt/index.ts:17-76`,
`extensions/skilzvolt/openclaw.plugin.json:1-33`). The installer enables the
plugin, allows proposals, and sets `agentIds`/organisation names
(`attached_assets/install-forked-openclaw.sh:553-590`). Those settings prove
registration intent only. They do not prove that the assigned live skill
catalogue is called, selected, injected, or obeyed by a cron/subagent.

### Local skill loader versus live skill bodies

The local loader can load links placed in configured extra/plugin skill
directories, but only from files present at scan time
(`src/agents/skills/workspace.ts:445-509`). The SkilzVolt hook appends a
metadata catalogue and instructs the agent to read full content via the tool;
it does not write live bodies into those roots (`extensions/skilzvolt/index.ts:66-76`).
Therefore a local `.local/intake-repair` body, an ignored snapshot, or a
reconstructed temporary body cannot establish activation.
This is an evidence boundary, not a live-skill/local-loader contradiction:
activation requires a live prompt/tool trace showing the current pinned body
was selected and consumed.

### Scheduler and delivery state

The native cron model has explicit execution and delivery statuses
(`src/cron/types.ts:109-131`) and failure destinations
(`src/cron/delivery.ts:104-208`). These are valuable schemas, not live state.
No live `cron list`, job history, Telegram receipt, Discord readback, task
worker state, service state, or destination readback was inspected.

### Expense watcher duplicate-trigger contradiction

`OPERATING.md` says the five-minute timer is disabled and a central mirror
router invokes the watcher as `ExecStartPost`, but the tracked timer still
declares `OnUnitActiveSec=5min`. The central-router source and units named by
the guide are missing from tracked main. This is an unresolved possible
duplicate lifecycle, not permission to enable, disable, delete, or redirect
anything.

### Email authorization-route verification gap

The pinned live `email-send` contract
(`SKILL:email-send@45a073fb-fffa-4079-858f-ff0560e1cab8`) requires six-digit
TOTP. The repository has a
TOTP trust gate for `exec.run`, and the installer says direct email uses that
route. Separately, the final `send.py` enforces a signed task-system permit
when invoked with `--task-dispatch-permit`, not a TOTP code. These are
intentionally separate authorization routes, not a repository contradiction:
direct `exec.run` plus TOTP and task-system signed exact-draft permits have
different callers and ownership. The installer also removes `message.send`
from `requireApproval` to avoid gating routine deliveries. Which route is
active and whether the final executor receives the required gate are not
proven. The permit tests prove permit integrity, not live contract activation.

### SharePoint/cache distinction

The cache and queue are useful capability paths, and their tests cover hashes,
locks, and readback protocol. A cache file, result file, accepted queue entry,
or local state update is not an authoritative destination receipt. The
watcher’s operating guide correctly says canonical workbook readback is
required (`pi-services/expense-intake-watcher/OPERATING.md:38-64`).

## Existing test coverage versus required proof

| Area                 | Existing source tests                                                                                                                                                                                                                                                             | What remains unproved                                                                                                            |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| SkilzVolt adapter    | Owner-only registration; fixed allowlist; required-tool contract; token redaction; oversized responses; notification refresh; degraded catalogue (`extensions/skilzvolt/index.test.ts`, `extensions/skilzvolt/src/client.test.ts`, `extensions/skilzvolt/src/catalogue.test.ts`). | Live skill invocation, activation, prompt selection, current workspace, and destination operations.                              |
| Task system          | Bearer bridge, brief intake, dispatch-by-draft-ID, protected approval fields (`src/agents/tools/task-system-tool.test.ts`).                                                                                                                                                       | Live gateway/worker, selection/readiness, context broker, decomposition/operation transitions, receipt state.                    |
| Cron/delivery        | Normalisation, inferred targets, isolated payloads, webhook validation (`src/agents/tools/cron-tool.test.ts`).                                                                                                                                                                    | Live reminder registry/verifier, five-minute retry logic, `cron list`, delivery receipt and read acknowledgement.                |
| Discord              | Permissions, policy, send/read/edit/delete/react/pin/search and explicit IDs (`src/discord/*.test.ts`).                                                                                                                                                                           | Live configured action gates, owner identity, destination readback and skill invocation.                                         |
| WhatsApp/watcher     | Target allowlists plus watcher lifecycle, duplicates, suppression, blocked expense and readback boundaries (`src/whatsapp/resolve-outbound-target.test.ts`, `pi-services/expense-intake-watcher/test_*.py`).                                                                      | Central router source/activation, complete mirror coverage, route receipts, live feed freshness.                                 |
| Microsoft email      | Signed permit integrity and Graph send/reply mechanics; no direct poller contract suite was found (`attached_assets/integrations/microsoft/test_send_task_dispatch.py`).                                                                                                          | Active account/token services, TOTP at final executor, complete six-surface state, sent/Drafts readback, downstream route proof. |
| SharePoint/resources | Queue/cache safety, source/semantic hash and readback protocol (`attached_assets/integrations/microsoft/test_sharepoint_*.py`).                                                                                                                                                   | Resource-intake owner, full-source retention route, live credentials, canonical destination and consumer updates.                |

No tests were run as part of this read-only audit. Existing test files are
evidence of intended source coverage only.

## Repair priorities and acceptance gates

### P0 — activation, duplicate lifecycle, and consequential destination proof

1. Obtain read-only live inventory for the active user: plugin config,
   installed checkout/commit, realpaths/hashes, `systemctl --user cat/show`,
   enabled/active timers, complete crontab, native OpenClaw cron jobs, gateway
   process/ports, task gateway/worker, credentials presence (not secret
   values), and destination receipt/state paths.
2. Reconcile the five-minute expense timer against the central mirror-router
   `ExecStartPost`; prove one sole owner or an explicit idempotent dual owner.
3. Identify `scripts/mirror_router.py` and
   `scripts/inbound-monitoring.py` provenance. Do not promote `.local` repair
   copies without source/commit/deployment proof.
4. Prove inbound/email/WhatsApp stable IDs through route allocation and
   independent task/CRM/SharePoint/expense/alert readbacks.
5. Prove email final executor gate: direct six-digit TOTP versus task permit,
   exact account and recipient, sent-item readback, and email log. Keep the
   signed permit as a separate mechanism until contract ownership is decided.
6. Identify task worker and email-draft writer; prove no-send, Drafts-folder
   state, conversation continuity, and duplicate suppression.
7. Identify reminder registry/verifier; prove primary delivery, one conditional
   retry, and daily failure audit.

### P1 — holding layers, context, resources, and complete coverage

1. Reconcile `TASKS.md`/`BACKLOG.md`/`L1-IMPROVEMENTS.md` with structured task
   capture and prove the capture-only stop boundary.
2. Prove task decomposition first-hop context, internal communication source
   ladder, capability/risk gates, and `execute_ready`.
3. Establish the resource canonical-home owner, complete source retention,
   metadata, exact retrieval cue, and owning-system update receipt.
4. Prove all email source surfaces, body-hidden/coverage states, sent/inbox
   continuity and explicit CRM/SharePoint route state.

### P2 — already strong source capability

1. Capture live Discord configuration/action gates and one controlled
   message/readback trace.
2. Retain current SkilzVolt adapter tests and add an activation smoke test that
   proves a selected current skill was called without treating prompt
   catalogue metadata as activation.

## Required evidence bundle before any “active/complete/retired” claim

For each skill and route, retain:

- live skill ID/version/current response metadata and warning status;
- installed realpath, symlink target, SHA-256, checkout root and commit;
- configured agent/plugin/skill roots and effective precedence;
- native cron job IDs, schedules, session targets, channels, account and
  destination; complete user timers and crontab;
- gateway/worker process, port, unit and state owner;
- source identity and stable provider IDs;
- route state, blocker/error code, retry condition and next review;
- independent destination reference and readback (Graph item, Outlook Drafts
  conversation, SharePoint row/workbook hash, task record, Discord message,
  Telegram delivery status);
- focused regression tests and one controlled end-to-end proof;
- owner approval and rollback record before any retirement or destructive
  change.

## Final boundary

The repository is capable of supporting substantial portions of the 11
contracts, especially fixed SkilzVolt access, owner-only task/SkilzVolt tools,
Discord message operations, email identity/body quarantine, SharePoint queue
validation, watcher lifecycle states, and cron delivery schemas. It does not
establish that the assigned live skills are invoked or that their final
destinations, approval gates, receipts, and activation state are wired in the
installed runtime. The correct operational result is to preserve the
unverified paths, resolve the P0 evidence gaps, and avoid claiming completion,
activation, retirement, or deployment from source declarations, snapshots,
queues, mirrors, alerts, drafts, or tests alone.
