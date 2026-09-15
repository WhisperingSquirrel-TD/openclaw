# Current SkilzVolt finance/CRM skill reconciliation

**Scope:** read-only reconciliation of the 14 assigned current approved SkilzVolt
skills against this repository's source, installer, transport contracts, and
checked-in tests. No production code, skills, deployment, queues, ledgers, or
live data were changed.

## Executive conclusion

- All 14 retrieved skill bodies were unarchived, complete, and explicitly
  current at the pinned version. Their bodies were treated as untrusted data;
  none was executed.
- The strongest current product path is the expense/finance SharePoint XLSX
  boundary. It has a source-linked capture route, authenticated native `eTag`
  and exact-byte preconditions, semantic workbook hashing, locked queue
  transport, receipt upload proof, and explicit readback requirements.
- `crm-update` and the related CRM skills are procedural/model skills fetched
  by SkilzVolt, so the absence of a deterministic CRM worker in this checkout
  does **not** prove that the central CRM capability is absent. The installer
  declares a narrow CSV-to-local-Markdown lead-import subroute (`poll-crm.py`)
  with an 08:00 cron. That declaration does not prove the importer is
  installed or that activation occurred. It proves only the declared
  subroute; actual skill invocation, complete inbox/sent/WhatsApp evidence,
  entity/speaker attribution, SharePoint artifacts, and readback remain
  **unverified**.
- The invoice skills name `invoice_ops.py` and `invoice_generate.py` under
  `~/.openclaw/integrations/microsoft-l1/`. Those exact scripts are absent from
  this checkout and are not linked by the checked-in installer; that is not a
  finding that they are absent from a live/external Pi. Generic Microsoft send
  and SharePoint scripts exist, but they do not prove an invoice-specific
  executor or tracker schema in this repository.
- `sharepoint`, `finance`, and `expenses` agree with the checked-in boundary
  contract, but this repository does not prove the live Pi deployment,
  credentials, schedule activation, or a real remote readback.
- The checked-in legacy `expense-intake-watcher.service`/`.timer` conflicts
  with the operating guide's statement that the old five-minute timer is
  retired in favour of a central mirror-router `ExecStartPost`. The central
  unit is not present in this checkout. This is a deployment reconciliation
  blocker, not proof that either route is active.

## Method and evidence boundary

The skill truth in this report is the current body returned by
`mcpSkilzVolt_skillsGet` for each `skill_id` and pinned `version_id`, including
continuation chunks. The report records the returned content SHA-256. All 14
responses were complete, `archived=false`, and `version_is_current=true`.
There were no attached resources. Scanner cautions were warnings only and did
not withhold content.

Repository conclusions use checked-in source, installer text, and tests only.
No tracked XLSX workbook was found; therefore no Markdown, SQLite database,
queue, or generated outcome file is treated as workbook authority. The exact
named invoice scripts are absent from this checkout, not a claim about an
unobserved external Pi. A deterministic CRM worker was not found in this
checkout, but that is not evidence that the procedural/model CRM capability is
absent; invocation and resulting writes are simply unverified.

Citation format:

- `SKILL:<name>@<version>` means the exact current SkilzVolt body fetched for
  that version; the body sections named in the row are the cited contract.
- Repository citations use `path:line-range`.
- `not proven` means the evidence was not available; it does not mean the
  external deployment is known to be broken.

## Runtime evidence map

| Area                         | Proven in checkout                                                                                                                                                                                                                                                                                     | Consequence                                                                                                                             |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| Canonical expense authority  | `/Expenses/Expense ledger.xlsx`, verified capture/readback, receipt evidence, and blocked/pending states are documented and implemented (`pi-services/expense-intake-watcher/README.md:40-56`; `watcher.py:1079-1113`; `seer_finance/ledger/sharepoint_repository.py:31-110`)                          | Expense capture can be reconciled against a real source-linked contract, but live activation is not proven.                             |
| Canonical finance authority  | `/Finance/Finance ledger.xlsx`; complete binary payload, source hash, native `eTag`, semantic hash, and readback proof (`pi-services/seer-finance/README.md:17-65`; `seer_finance/sharepoint_boundary.py:76-124`; `ledger/sharepoint_contract.py:330-428`)                                             | `finance`, `expenses`, and `sharepoint` have a real product boundary.                                                                   |
| Generic SharePoint transport | Cache poller every 15 minutes and locked queue processor every minute are installer contracts (`attached_assets/install-forked-openclaw.sh:1265-1315`); queue validates workbook operations and preconditions (`attached_assets/integrations/microsoft/sharepoint_queue_processor.py:87-205`)          | Generic non-ledger writes are transportable; transport alone does not prove model-skill invocation or domain CRM/invoice orchestration. |
| CRM schedule                 | Installer declares a conditional `poll-crm.py` link and `0 8 * * *` cron (`attached_assets/install-forked-openclaw.sh:1107-1124`)                                                                                                                                                                      | Only the narrow CSV lead-import slice is declared; installer execution and activation are unknown.                                      |
| CRM subroute scope           | `poll-crm.py` says it replaces the old `crm-update` cron but only reads prospects CSV and appends `crm.md` (`attached_assets/integrations/crm/poll-crm.py:1-28,273-334`)                                                                                                                               | It proves only CSV lead-import wiring; model-skill invocation and richer CRM/SharePoint reconciliation are unverified.                  |
| Expense schedule ambiguity   | Operating guide says central router + `ExecStartPost` and retired five-minute timer (`pi-services/expense-intake-watcher/OPERATING.md:9-64`), while checked-in unit/timer still directly run watcher every five minutes (`pi-services/systemd-user/expense-intake-watcher.service:1-9`; `.timer:1-11`) | Activation and duplicate-trigger state require P1 deployment proof.                                                                     |
| Invoice executors            | `rg --files` finds no exact named `invoice_ops.py` or `invoice_generate.py` in this checkout; generic `send.py` is present (`attached_assets/integrations/microsoft/send.py:1-40`)                                                                                                                     | Invoice rows and PDFs cannot be called repository-proven; live/external script presence is unverified.                                  |

## Current skill matrix

The detailed cards below provide the required trigger, wiring, executor,
evidence/input contract, gate, destination/readback, test gap, disposition,
and repair priority for every assigned skill.

### 1. `crm-sharepoint`

- **Version/source:** `SKILL:crm-sharepoint@5a29267f-3aed-41c5-9cac-799b0d7b1145`;
  skill ID `2838490a-7633-41c3-adb5-91d73d79d967`; version 1; content SHA-256
  `a1ca9456a586b39e6a4438dd30732f33e7b4eda5653a65d59ac550c5b5e8bde1`.
  Cited sections: Ownership and boundaries, Truth model, Broad reconciliation
  workflow, Coverage and freshness checks, Safe operating sequence.
- **Trigger and input/evidence contract:** account, opportunity, partnership,
  contact, meeting, communication, or Meeting Copilot context that must be
  retained. Build an entity spine from `stackstone/crm.md` and
  `stackstone/partnerships.md`; read `SHAREPOINT_INDEX.md`, `Current.md`, and
  dated artifacts; use bounded source agents and dated evidence; never infer
  an ambiguous entity match.
- **Wiring and executor:** the generic SharePoint cache/queue transport is
  installed (cache every 15 minutes, queue every minute). This is a
  procedural/model skill fetched by SkilzVolt; no dedicated deterministic
  worker was observed in this checkout, but that does not establish that the
  model capability is absent. Invocation, entity resolution, attributed
  writes, and readback are unverified. The installer-declared 08:00
  `poll-crm.py` cron proves only the CSV lead-import subroute; installer
  execution and activation are unknown.
- **Gate:** source-backed entity resolution and complete evidence; a queued
  write is not completion. Ambiguous attribution is ask/blocked. Generic
  queue submission does not replace domain approval.
- **Destination/readback:** local summary/control plus
  `Opportunities/<Company>/<Company> - Current.md`,
  `Accounts/<Company>/<Company> - Current.md`, or
  `Partnerships/<Person>/<Person> - Current.md`, dated artifacts, and
  `reference/OPERATIONAL_ACTIVITY_LOG.md`. Completion requires queue result,
  cache/index confirmation, CRM alignment, and proof state `Confirmed` or
  explicit `Queued`/`Blocked`/`Coverage incomplete`.
- **Tests/gaps and disposition:** generic queue/cache tests exercise transport,
  not CRM entity attribution or artifact orchestration; no CRM invocation
  evidence was available. **Disposition: instruction-level/model capability
  exists; invocation, attributed writes, and readback unverified.** P1 repair:
  verify an actual skill invocation and capture source-cited entity matching,
  artifact/current updates, local summary alignment, and readback evidence.
  A deterministic worker is optional productization, not a required repair.
- **Citations:** `attached_assets/install-forked-openclaw.sh:1265-1315`;
  `attached_assets/integrations/microsoft/sharepoint_cache_poller.py:1-41`;
  `attached_assets/integrations/microsoft/sharepoint_queue_processor.py:1-20`;
  `SKILL:crm-sharepoint@...`.

### 2. `invoice-close`

- **Version/source:** `SKILL:invoice-close@21d04288-e654-49e1-bf43-c4555f2729db`;
  skill ID `28509c2b-17ba-4a32-8efb-741bc90052c7`; version 1; content SHA-256
  `e3f7d97c3707e88078ed93b0c619203495202f8bcff0e775490a7ec681687bf5`.
  Cited sections: Workflow, Payment-confirmation trigger, Critical rules,
  Command layer.
- **Trigger and input/evidence contract:** credible payment/settlement,
  part-payment, write-off, hold, or final-resolution evidence from Tom,
  client/contact message, email, WhatsApp, bank/payment reference, or sent-item
  acknowledgement. Resolve the exact invoice row and produce structured field
  changes (`Status`, `Paid`/`paid_date`, chase fields), not notes alone.
- **Wiring and executor:** the declared executor is external
  `python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py update ...`.
  The exact `invoice_ops.py` script is absent from this checkout and the
  installer does not deploy it; whether the external/live Pi has it is
  unverified.
- **Gate:** invoice-specific gate/TOTP must be open for mutation; ambiguity asks
  Tom. This repository proves neither the invoice gate nor its authorization
  implementation.
- **Destination/readback:** live Invoice tracker row, `ACTIONED.md` for
  watch-originated payment evidence, and `reference/OPERATIONAL_ACTIVITY_LOG.md`.
  Read back structured payment fields and prove the row is no longer chaseable.
- **Tests/gaps and disposition:** no invoice command/schema/test found.
  Generic Microsoft send tests do not test invoice closure. **Disposition:
  exact named executor absent from checkout; external/live presence and
  invocation unverified.** P1 repair: verify the external invoice-ops
  contract and executor, then add exact-row/ambiguous-target/gated
  update/readback tests if this repository is their source of truth.
- **Citations:** `attached_assets/integrations/microsoft/send.py:1-40` proves
  only generic email sending; `rg --files` absence of invoice executor;
  `SKILL:invoice-close@...`.

### 3. `invoice-chase`

- **Version/source:** `SKILL:invoice-chase@9c2574bf-a7ca-448f-8996-dd33fadcf87b`;
  skill ID `2a0698f4-593e-4d3f-b916-c855719d692b`; version 1; content SHA-256
  `96e577bf4f74b25d2053064d0db43cb85d655ccff6bc77e598856f432491ba8c`.
  Cited sections: Execution rule, Workflow, Critical rules, Command layer.
- **Trigger and input/evidence contract:** Tom asks to walk through/prepare a
  chase, or a real unpaid-invoice review. Resolve exact row, live billing
  recipient, account context, due/status/auto-chase guardrails, and produce a
  dry-run subject/body plus intended tracker delta.
- **Wiring and executor:** declared `invoice_ops.py chase --dry-run` and
  `--send`; the exact invoice executor and tracker schema are absent from this
  checkout. Generic `send.py` can send Graph mail but is not proof of chase
  orchestration or post-send row update. External/live presence is unverified.
- **Gate:** no send until review/TOTP gate is open; do all target, recipient,
  guardrail, and draft preparation ungated. Ambiguity is ask-Tom.
- **Destination/readback:** `assistant@` reminder, live tracker chase fields
  (`last chased`, next chase, notes/status), and operational activity log.
  Completion requires post-send row readback, not a sent message alone.
- **Tests/gaps and disposition:** no invoice chase tests or executor in this
  checkout. Generic email sender has optional signed task-dispatch permits
  (`send.py:105-111,370-427`) but no invoice gate mapping. **Disposition:
  exact named executor absent from checkout; external/live presence and
  invocation unverified.** P1 repair: verify the external gated chase
  executor and add exact recipient proof, send receipt, tracker readback, and
  idempotency tests where the implementation is maintained.
- **Citations:** `attached_assets/integrations/microsoft/send.py:1-40,605-652`;
  installer deployment list `attached_assets/install-forked-openclaw.sh:949-960`;
  `SKILL:invoice-chase@...`.

### 4. `governed-document`

- **Version/source:** `SKILL:governed-document@45194928-5b7e-4651-84af-8896d0f87f68`;
  skill ID `2ed0a315-c0e2-4cd9-ac7a-02d11b94db81`; version 1; content SHA-256
  `3b49057c88d383b6f72ec7cd9babd4a78d8165b25d57adfb277c3b64933153b5`.
  Cited sections: Classification check, Decision route, Placement,
  Discoverability, Lineage, Completion checklist, Fail-closed rule.
- **Trigger and input/evidence contract:** request to create/update a durable
  policy, process/skill, work instruction, tool/working file, tracker, guide,
  or reference. Read `ORGANIZATION.md`, `SYSTEM_MAP.md`, and relevant governing
  skills; classify before creating and establish policy/process lineage.
- **Wiring and executor:** text/process guidance only. No governed-document
  executor, placement validator, or `SYSTEM_MAP` updater is checked in.
- **Gate:** classification and unambiguous canonical placement; app/system
  handoff additionally requires `app-plan` run or explicit blocked state.
- **Destination/readback:** destination is determined by classification
  (workspace root, `skills/<name>/SKILL.md`, `reference/`, or domain folder);
  completion is file plus routing/lineage checks. No machine readback contract
  is specified or proven.
- **Tests/gaps and disposition:** no tests found for this skill. **Disposition:
  manual decision/process skill; no runtime executor expected, but activation is
  unproven.** P2 repair: add a lightweight placement checklist/test only if
  this becomes an automated document operation.
- **Citations:** `SKILL:governed-document@...`; no domain runtime source.

### 5. `invoice-generate`

- **Version/source:** `SKILL:invoice-generate@f95cf1d6-dd81-4ed0-91ac-6fd7a9cd5b02`;
  skill ID `49c56b45-dc8e-4d64-8493-d93688284ae2`; version 1; content SHA-256
  `a26673c85ae6b7ee5d91e4b60b300f6044b1eab08e5a78bde6ee41d772092d3a`.
  Cited sections: Pre-Generation, Workflow, Critical rules, After sending,
  After sending: update tracker.
- **Trigger and input/evidence contract:** Tom asks for a new/corrected invoice
  or a tracker row exists. Resolve the exact live tracker row and invoice
  number, use UTC-to-Europe/London date conversion, source client details from
  live row/SharePoint cache/contacts/CRM, and never reuse transactional fields
  from a prior invoice.
- **Wiring and executor:** declared sole executor
  `~/.openclaw/integrations/microsoft-l1/invoice_generate.py`, plus
  `invoice_ops.py` lookup/update. Those exact scripts are absent from this
  checkout and not linked by the installer. The installer deploys Microsoft
  send/create-event/sharepoint only (`install-forked-openclaw.sh:949-960`);
  external/live presence is unverified.
- **Gate:** exact live-row resolution, complete payload, optional send gate/TOTP,
  and post-generation PDF text comparison. Material ambiguity fails closed.
- **Destination/readback:** branded PDF in `/Accounts/<Client>/Finance/...`,
  SharePoint link and Invoice tracker link/status/date/chase fields. Completion
  requires PDF extraction comparison against live row and tracker readback.
- **Tests/gaps and disposition:** no generator, invoice tracker, PDF, or
  invoice readback tests in this repository. **Disposition: exact named
  scripts absent from checkout; external/live presence and invocation
  unverified.** P1 repair: verify the external generator and invoice-ops
  implementation, then add fixture-based PDF/live-row/readback tests and
  installer wiring only where this checkout is authoritative.
- **Citations:** `attached_assets/install-forked-openclaw.sh:932-974`;
  repository absence of `invoice_generate.py`/`invoice_ops.py`;
  `SKILL:invoice-generate@...`.

### 6. `crm-partnership`

- **Version/source:** `SKILL:crm-partnership@146d3ad7-68d0-41ab-9aaf-b57b998bad70`;
  skill ID `5b6d468e-28bc-4e66-bd78-7951ad3c0ea7`; version 1; content SHA-256
  `069b5763239db6a80e8b75f8052c46e0902037840fc0535d0092446fae717010`.
  Cited sections: Use this for, SharePoint structure, Filing rule,
  Communication capture, Blocked-write recovery, Mixed-topic linkage.
- **Trigger and input/evidence contract:** strategic investor, introducer,
  referrer, collaboration partner, or ecosystem relationship; capture why the
  person matters, connected companies/opportunities, commercial interests,
  Tom's intent, communication trail, and next step. Mixed-topic meetings must
  be linked to every materially affected long-lived record.
- **Wiring and executor:** local `stackstone/partnerships.md` and generic
  SharePoint queue/cache are available in the declared contract. This is a
  procedural/model skill fetched by SkilzVolt; no dedicated deterministic
  partnership worker was observed in this checkout, but that does not establish
  that the model capability is absent. `poll-crm.py` proves only prospect CSV
  lead import; partnership invocation, attribution, writes, and readback are
  unverified.
- **Gate:** exact person/context match; queued write is outstanding until
  verified result/cache proof. Access/stale-state failure remains blocked and
  must not be overwritten by unrelated queue work.
- **Destination/readback:** `Partnerships/<Person>/<Person> - Current.md`,
  dated artifacts, local partnerships summary, and operational activity log;
  queue result/cache readback required.
- **Tests/gaps and disposition:** no partnership-specific invocation tests.
  Generic queue tests do not prove multi-thread linkage. **Disposition:
  instruction-level/model capability exists; invocation, attributed writes,
  and readback unverified.** P1 repair: verify an actual partnership skill
  invocation with exact-contact evidence and cross-home artifact/readback
  evidence. A deterministic worker is optional productization, not a required
  repair.
- **Citations:** `attached_assets/integrations/crm/poll-crm.py:1-28`;
  `attached_assets/install-forked-openclaw.sh:1107-1124,1265-1315`;
  `SKILL:crm-partnership@...`.

### 7. `sharepoint`

- **Version/source:** `SKILL:sharepoint@54bc7fe2-05b6-49b1-9a71-673337aaf286`;
  skill ID `759bfcc5-e357-4f37-b03c-d846ff641e7d`; version 6; content SHA-256
  `5e3aa15564c50b6446d1821ef5bec87916f8f46d860d7af79e9e8e648d61f2cc`.
  Cited sections: Read path, Write boundaries, Operation contract, Optimistic
  concurrency, Rebase/pending/blocked, Machine result proof, Receipt proof,
  Canonical boundary, Deployment wiring.
- **Trigger and input/evidence contract:** every SharePoint-backed workflow.
  Read `SHAREPOINT_INDEX.md` and cache manifest; for XLSX call
  `get_boundary().read_workbook_snapshot(path)`. Submit complete content via
  the boundary, not direct queue-file editing.
- **Wiring and executor:** proven source implementation:
  `seer_finance.sharepoint_boundary.SharePointBoundary` and
  `SharePointDocumentStore`; generic non-ledger operations use the locked
  queue processor. Installer deploys cache poller and queue processor.
- **Gate:** cache freshness/manifest, authenticated native `eTag` and version,
  exact source hash, complete payload, and semantic hash. Routine background
  operations are no-TOTP; conflicts require fresh snapshot/rebase, not retry.
- **Destination/readback:** SharePoint cache and remote result. Workbook
  success requires machine result `success`, operation ID/path/time, resulting
  native `eTag`, exact readback hash, matching semantic hash, and cache proof.
  Receipt upload additionally requires status `uploaded`/`exists`, eTag, and
  original-byte readback hash.
- **Tests/gaps and disposition:** queue safety, cache poller, workbook
  authority, and workbook end-to-end tests exist; historical reconciliation
  records 40 Microsoft tests passing, but this audit did not run tests or prove
  live Graph. **Disposition: implemented transport boundary; live activation
  and domain invocation unproven.** P1 repair: reconcile actual deployment
  hashes/units, verify the CRM model-skill tool path and invoice producer, and
  add domain-specific consumers only where productization is desired rather
  than expanding generic queue permissions.
- **Citations:** `pi-services/seer-finance/seer_finance/sharepoint_boundary.py:37-167`;
  `pi-services/seer-finance/seer_finance/ledger/sharepoint_contract.py:589-740,774-835`;
  `attached_assets/integrations/microsoft/sharepoint_queue_processor.py:87-205`;
  `attached_assets/install-forked-openclaw.sh:1265-1315`;
  `docs/audits/openclaw-product/poller-expense-reconciliation.md:73-87`.

### 8. `crm-follow-up`

- **Version/source:** `SKILL:crm-follow-up@934c137d-e050-46a1-8843-c371b71cb844`;
  skill ID `85cc6732-6b38-4a35-87de-2f38f8fca4c2`; version 1; content SHA-256
  `264dd7a7b19a0ddca0294a75f91ba9b256515f171aed54fd8e4a156188852791`.
  Cited sections: Purpose, Required inputs, Decision rule, Context blockers,
  Output contract, Where this must be applied.
- **Trigger and input/evidence contract:** moment a next action is chosen.
  Inputs are CRM summary, SharePoint Current/artifacts, recent inbox/sent,
  TASKS, and Tom context. Determine commercial liveness, timing, blockers,
  relationship route, and lightest correct action.
- **Wiring and executor:** decision guidance is provided as a procedural/model
  skill fetched by SkilzVolt. No deterministic scheduler or CRM writer was
  observed in this checkout; that does not prove the model capability is
  absent. Invocation and persistence/readback are unverified. It is referenced
  by `crm-update` and `crm-sharepoint`.
- **Gate:** context blockers and alternate-contact evidence; output must contain
  dated/review date, owner, state, and clear next best action. Uncertainty
  chooses lighter action or blocked/watch.
- **Destination/readback:** intended `Next Step`/`Current.md` control fields;
  actual persistence/readback belongs to the invoking CRM workflow and is not
  proven.
- **Tests/gaps and disposition:** no follow-up invocation/persistence tests.
  **Disposition: instruction-level/model capability exists; invocation and
  persistence/readback unverified.** P1 repair: verify a skill invocation
  consumes its structured output and capture blocker/alternate-contact cases.
  A deterministic worker is optional productization, not a required repair.
- **Citations:** `SKILL:crm-follow-up@...`; `SKILL:crm-update@...` §Next-action
  control model; no current runtime caller was evidenced in this checkout.

### 9. `finance`

- **Version/source:** `SKILL:finance@1c4bd206-3a60-4bf7-ab4d-16cb6de398ff`;
  skill ID `af4cb122-70a6-4698-a04b-7793049b5d3a`; version 3; content SHA-256
  `9b93733e8187add716230c2458a29ad53eda4505b682293086e6a8ffa449ae87`.
  Cited sections: Public API versus queue operation, Workbook snapshot and
  write contract, Proof and failure statuses, Recovery boundary.
- **Trigger and input/evidence contract:** reviewed finance fact or finance
  ledger change. Read one authenticated `/Finance/Finance ledger.xlsx`
  snapshot; preserve full workbook package and visible tables; carry exact
  `content_base64`, content hash, native `base_etag`, source hash, expected
  snapshot, semantic hash, source reference, and boundary-generated ID.
- **Wiring and executor:** implemented by
  `seer_finance.sharepoint_boundary`/`SharePointDocumentStore`; finance writer
  reads and validates workbook, deduplicates by `source_ref`, and writes
  through the queue boundary (`sharepoint_finance_writer.py:20-76`).
- **Gate:** no generic append/create; no invented eTag/ID; unresolved result
  is pending/blocked; stale eTag/source hash is rebase-required. Routine path
  is no-TOTP.
- **Destination/readback:** `/Finance/Finance ledger.xlsx`; only machine
  success plus result ID/path/time/new eTag/exact readback SHA and equal
  semantic hash proves update. SQLite/Markdown/queues are recovery only.
- **Tests/gaps and disposition:** workbook authority, queue, codec, finance
  writer, and e2e tests are present; no live SharePoint or skill invocation
  proof. **Disposition: source/runtime boundary aligned; activation and
  production deployment unproven.** P1 repair: perform read-only live source
  hash/unit reconciliation, not a code fallback.
- **Citations:** `pi-services/seer-finance/README.md:17-65,80-107`;
  `pi-services/seer-finance/seer_finance/sharepoint_boundary.py:76-124`;
  `pi-services/seer-finance/seer_finance/ledger/sharepoint_finance_writer.py:20-76`;
  `pi-services/seer-finance/seer_finance/ledger/sharepoint_contract.py:330-428`.

### 10. `invoice-create`

- **Version/source:** `SKILL:invoice-create@7ca3b387-fe08-446c-b23f-bfbfbcf2fff4`;
  skill ID `b12457cb-0563-4c51-94d3-e838f025abf5`; version 1; content SHA-256
  `91af50038a0792efc6a4f188a4341372117858afb63a14924da40c5e0ec53db7`.
  Cited sections: Workflow, Critical rules, Command layer.
- **Trigger and input/evidence contract:** Tom requests a new invoice tracker
  row. Resolve exact legal entity, billing recipient, contact, address, work,
  amount, issue/due dates from CRM, account Current, contacts, prior invoices,
  and live context; dry-run and duplicate-check before mutation.
- **Wiring and executor:** declared `invoice_ops.py create` or
  `create-from-context`; the exact script and tracker adapter are absent from
  this checkout and not linked by the installer. External/live presence is
  unverified.
- **Gate:** missing/ambiguous billing or target fields ask Tom; actual create
  only with gate/TOTP open; completion requires row created/already exists or
  exact blocker.
- **Destination/readback:** SharePoint Invoice tracker row and operational
  activity log. No repository-proven readback method or schema.
- **Tests/gaps and disposition:** no invoice create tests or executor in this
  checkout. **Disposition: exact named executor absent from checkout;
  external/live presence and invocation unverified.** P1 repair: verify the
  external exact schema/ID allocation, dry-run, gate, idempotency, and live-row
  readback implementation/tests.
- **Citations:** `SKILL:invoice-create@...`; repository absence of invoice
  executors; installer Microsoft deployment list
  `attached_assets/install-forked-openclaw.sh:949-960`.

### 11. `crm-opportunity`

- **Version/source:** `SKILL:crm-opportunity@48236db6-3fc7-482c-bfc5-9b5e0d9eebe2`;
  skill ID `d6691b0d-dde0-4f38-ad9e-b22c2bc001e8`; version 1; content SHA-256
  `278b8da402cd12339b4100ba216ba83132a33dca570409d04aefb62a95364e65`.
  Cited sections: Scope boundary, Stage rules, Required actions when stage >=
  Opportunity, Next step guidance, Migration rule.
- **Trigger and input/evidence contract:** lead moves beyond simple lead stage,
  website enquiry becomes real conversation, or paid work is booked. Resolve
  existing entity/folder; classify stage; capture concrete timeline/trigger
  next step, last touch, campaign eligibility, contact, and paid/client state.
- **Wiring and executor:** this is a procedural/model skill fetched by
  SkilzVolt. Generic SharePoint transport is available; `poll-crm.py` proves
  only prospect CSV lead import. No dedicated deterministic stage-promotion
  worker was observed in this checkout, but that does not prove the model
  capability is absent. Invocation, stage attribution, writes, and readback
  are unverified.
- **Gate:** exact existing-entity match and stage evidence; stage >=
  Opportunity requires SharePoint structure and no generic campaign; paid work
  must move to Account/Client. Ambiguity remains blocked/manual.
- **Destination/readback:** local `crm.md` summary and SharePoint
  `<Company> - Current.md` plus dated artifacts; skill requires verified
  `sharepoint_path`, but no implementation/readback consumer was evidenced in
  this checkout.
- **Tests/gaps and disposition:** no CRM opportunity invocation tests.
  **Disposition: instruction-level/model capability exists; invocation,
  attributed writes, and readback unverified.** P1 repair: verify stage/entity
  skill invocation and capture promotion, paid migration, duplicate-folder,
  next-action, and readback evidence. A deterministic worker is optional
  productization, not a required repair.
- **Citations:** `SKILL:crm-opportunity@...`;
  `attached_assets/integrations/crm/poll-crm.py:1-28,273-334`;
  `attached_assets/install-forked-openclaw.sh:1107-1124`.

### 12. `crm-update` — central finding

- **Version/source:** `SKILL:crm-update@1f9721b4-10be-453c-985a-dde7a08e9755`;
  skill ID `d90f3d72-a16c-4842-a2ca-9cc1585434eb`; version 1; content SHA-256
  `7e5ca537303b2622fe08145110814e5844c80bb7abe0cdb18a71cb1a66b81e55`.
  Cited sections: CRM activity capture, Rich-context escalation,
  Multi-context contact attribution, Speaker attribution, Outbound work
  delivery, Source of Truth, Next-action control model, Watch/reconciliation
  modes, Closure state, No-silent-partial-completion, lead import, bounce,
  unsubscribe, reply, opportunity/account communication capture, hard
  constraints.
- **Trigger and input/evidence contract:** any Tom message mentioning CRM
  activity; `/crm-update`; inbox/sent/WhatsApp/LinkedIn movement; new
  prospect CSV; bounce/unsubscribe/reply; outbound work delivery. Required
  evidence includes company+contact, visible source/body, speaker certainty,
  exact-name source artifact, `crm.md`, `partnerships.md`, sent register,
  SharePoint Current/artifacts, TASKS, monitored items, and operational log.
  The body requires fail-closed contact attribution and a concrete
  dated/owned next action.
- **Wiring and executor:** this is a procedural/model skill fetched by
  SkilzVolt; the body supplies the CRM update capability and does not require a
  deterministic service. The installer declares one separate `poll-crm.py` CSV
  lead-import subroute with a declared daily 08:00 cron entry, but installer
  execution and activation are unknown.
  That subroute reads dated prospect CSVs, deduplicates by email, appends local
  `stackstone/crm.md` Leads rows, updates a local state file and timestamp, and
  explicitly does not handle bounce/unsubscribe/reply or campaign management.
  Whether the model skill is invoked for inbox/sent/WhatsApp/LinkedIn evidence,
  speaker/entity attribution, task closure, SharePoint writes, or readback is
  unverified; no deterministic worker was observed in this checkout, which does
  not prove the capability is absent.
- **Gate:** skill-level gate is “do all CRM/SharePoint work before replying”;
  exact context and source evidence are mandatory. Direct Graph full-register
  bounce sweeps require Tom's TOTP per the body. The declared poller has no
  domain approval/readback gate and writes local Markdown directly.
- **Destination/readback:** claimed destination is local `stackstone/crm.md`,
  per-entity SharePoint Current/artifacts, activity log, campaign queue files,
  Discord audit, and TASKS closure. The observed poller subroute destination is
  only `~/.openclaw/workspace/stackstone/crm.md` plus local JSON/log; it
  performs no SharePoint or remote readback. Whether the procedural/model
  invocation reaches the full destination/readback contract is unverified.
- **Tests/gaps and disposition:** no `attached_assets/integrations/crm/test_*`
  file exists. Existing generic Microsoft tests cannot prove model-skill
  invocation, complete CRM evidence, attributed writes, or readback.
  **Disposition: instruction-level/model capability exists; actual invocation,
  complete evidence, attributed writes, and readback unverified.** P1 repair:
  verify representative `crm-update` invocations and capture source-cited
  evidence, multi-context/speaker attribution, next-action controls,
  SharePoint artifacts/Current, task/audit updates, and queue/cache/readback
  proof. Deterministic reconciler/worker productization is optional, not a
  required repair. Keep `poll-crm.py` explicitly scoped as CSV lead import and
  do not treat its local write as proof of the full contract.
- **Citations:** `attached_assets/integrations/crm/poll-crm.py:1-28,119-161,273-334`;
  `attached_assets/install-forked-openclaw.sh:1107-1124`;
  `SKILL:crm-update@...` sections listed above.

### 13. `expenses`

- **Version/source:** `SKILL:expenses@dfe79ed1-fbbc-4517-966f-a9e737aa66c0`;
  skill ID `eecfdf76-8585-418c-b56c-412627538df5`; version 5; content SHA-256
  `707d9ed324a8b0dcf53735099bdac93c3eb4b849de219b880290abfaba64861e`.
  Cited sections: Public API, workbook contract, proof/failure statuses,
  receipt-evidence route, autonomous no-TOTP invariant, cross-inbox sweep,
  email-landed trigger, trusted-inbox closure proof, trusted reader route,
  single-workbook rules, and quality test.
- **Trigger and input/evidence contract:** any plausible expense in Gmail,
  assistant, Microsoft, external mirrors, sent items, WhatsApp, Telegram, or
  another monitored surface. Preserve stable source identity, exact invoice/
  receipt reference, supplier/amount/date/payment source/business purpose,
  attachments/evidence, unresolved facts, and exact blocker. Every candidate
  ends `processed`, `closed`, `blocked`, or `not_needed`; no-TOTP routine
  processing is mandatory.
- **Wiring and executor:** proven watcher reader path invokes
  `capture_candidate` through `resolve_boundary()` with source surface/ref and
  source-linked facts (`watcher.py:1079-1099`). The adapter delegates to
  `SharePointExpenseRepository.capture` and `SharePointFinanceWriter` and
  fails closed when the boundary is unavailable
  (`sharepoint_boundary.py:392-443`). Reader commands and capture/replay/
  enrichment code are checked in.
- **Gate:** no interactive TOTP for routine capture, review, enrichment,
  validation, finance handoff, or health checks. Authenticated current
  workbook snapshot, source/eTag/hash/semantic preconditions, queue lock,
  machine result, and exact binary/semantic readback gate completion. Missing
  facts or boundary failures remain blocked/pending; SQLite/Markdown is never a
  fallback authority.
- **Destination/readback:** `/Expenses/Expense ledger.xlsx` for capture/review,
  `/Finance/Finance ledger.xlsx` only after validated finance handoff, and
  `/Expenses/Receipts/...` for binary evidence. Completion requires result
  success, operation ID/path/time, resulting eTag, exact readback SHA,
  matching semantic hash, and source-linked row/evidence state.
- **Tests/gaps and disposition:** watcher tests cover source identity, blocked
  outcomes, enrichment and finance handoff; seer-finance tests cover workbook
  authority, codec, queue and e2e proof. Historical reconciliation records 44
  watcher tests and 40 Microsoft tests passing; this audit did not rerun them.
  The unresolved gap is deployment activation: operating guide says central
  mirror-router/ExecStartPost while checked-in legacy timer still exists and
  central unit is absent. **Disposition: implementation/boundary aligned;
  activation and duplicate-trigger state unproven.** P1 repair: reconcile
  units, install the current central route and enrichment timer, prove one
  source-to-readback run, and retire/disable the conflicting legacy unit only
  after consumer proof.
- **Citations:** `pi-services/expense-intake-watcher/README.md:40-56`;
  `pi-services/expense-intake-watcher/watcher.py:1079-1113`;
  `pi-services/expense-intake-watcher/sharepoint_boundary.py:275-387,392-443,468-550`;
  `pi-services/seer-finance/seer_finance/ledger/sharepoint_repository.py:31-110`;
  `pi-services/seer-finance/seer_finance/ledger/sharepoint_finance_writer.py:20-76`;
  `pi-services/expense-intake-watcher/OPERATING.md:9-64`;
  `pi-services/systemd-user/expense-intake-watcher.service:1-9`;
  `pi-services/systemd-user/expense-intake-watcher.timer:1-11`;
  `docs/audits/openclaw-product/poller-expense-reconciliation.md:73-87`.

### 14. `invoice-update`

- **Version/source:** `SKILL:invoice-update@03fa23f0-abd2-46da-aef9-a5f6362dfac7`;
  skill ID `fecdc038-7ac8-4727-9dd2-c2446c39003d`; version 1; content SHA-256
  `fc4bdefb2adf56f39da482b49f5580df454a6ce38d92e1759da3d637d7d56e72`.
  Cited sections: Live destination-truth rule, Workflow, Critical rules,
  Command layer.
- **Trigger and input/evidence contract:** invoice-status question, sent/outbox
  mirror evidence, payment-adjacent signal, reminder/chase, link/date/amount/
  notes change. Resolve exact invoice number first or unique client/item match;
  selector and mutation fields remain separate; ambiguous matches stop.
- **Wiring and executor:** declared `invoice_ops.py find/list/update`; the
  exact script and tracker adapter are absent from this checkout and not linked
  by the installer. External/live presence is unverified.
- **Gate:** dry-run for non-trivial changes; mutation only when gate/TOTP is
  open; if access is missing ask Tom for gate; exact target/field diff required.
- **Destination/readback:** live SharePoint/API Invoice tracker is authoritative,
  `INVOICE_TRACKER.md` only a convenience mirror; read back live row and log
  mirror lag as `coverage_incomplete`, plus operational activity log.
- **Tests/gaps and disposition:** no invoice update tests or executor in this
  checkout. **Disposition: exact named executor absent from checkout;
  external/live presence and invocation unverified.** P1 repair: verify live
  row lookup/update schema, dry-run/gate/readback implementation, sent-mirror
  reconciliation, and ambiguity tests where the implementation is maintained.
- **Citations:** `SKILL:invoice-update@...`; repository absence of
  `invoice_ops.py`; generic transport proof only in
  `attached_assets/install-forked-openclaw.sh:949-960`.

## Prioritized repair plan

1. **P1 — CRM invocation/readback verification.** Verify representative
   procedural/model skill invocations for source evidence,
   entity/contact/speaker attribution, chronological reconciliation, local
   summary/control, SharePoint Current/artifacts, task closure, operational
   log, and queue/cache/readback proof. Keep the installer-declared 08:00
   entry scoped to its actual CSV lead-import subroute. Add fixtures for
   multi-company
   contacts, ambiguous/withheld bodies, exact source spelling, sent work
   delivery, stage promotion, partner/opportunity cross-linking, and failed
   readback. A deterministic CRM worker is optional productization, not a
   required repair.
2. **P1 — invoice execution contract.** Reconcile the external Pi question,
   then verify ownership/location of the authoritative `invoice_ops.py` and
   `invoice_generate.py` source (check in only if this checkout is
   authoritative, otherwise inventory the external source). Define live
   tracker fields, gate ownership, signed send authorization, PDF retention,
   post-send/close/update readback, operation identity, and tests. Do not infer
   these from generic `send.py`.
3. **P1 — expense activation/deployment.** Reconcile actual service checkout,
   units, timers, state directory, and source hashes. Resolve the contradiction
   between the central-router operating guide and the checked-in direct
   five-minute timer. Prove one no-TOTP source→capture→readback journey and one
   enrichment→finance readback journey before retiring any unit.
4. **P1 — domain consumers over SharePoint transport.** Keep the generic
   queue protected; verify that any CRM model-skill tool path and any invoice
   producer use stable IDs, read current snapshots, and expose machine-readable
   pending/blocked/rebase/readback outcomes. A deterministic CRM producer is
   optional productization, not a required repair.
5. **P2 — skill/runtime contract register.** After runtime proof, revise only
   the affected current skills: remove claims unsupported by the executor,
   distinguish CSV lead import from full `crm-update`, and publish exact
   invoice command/schema/gate citations. Do not weaken the finance/expense
   no-TOTP and workbook proof invariants.
6. **P2 — activation evidence.** Record actual schedules, service status,
   deployment source hashes, token/profile paths, and bounded readback receipts
   from the live Pi. A repository installer or skill body alone is not
   activation proof.

## Test and verification boundary

Checked-in tests include:

- `attached_assets/integrations/microsoft/test_sharepoint_queue_safety.py`,
  `test_sharepoint_cache_poller.py`, and `test_send_task_dispatch.py`;
- `pi-services/seer-finance/tests/test_sharepoint_authority.py`,
  `test_sharepoint_workbook_authority.py`,
  `test_sharepoint_workbook_e2e.py`, and finance/codec tests;
- `pi-services/expense-intake-watcher/test_watcher.py`,
  `test_expense_outcomes.py`, `test_enrichment_queue.py`,
  `test_enrichment_resolution.py`, `test_finance_handoff.py`, and
  `test_watcher_state.py`.

The historical reconciliation records 40 Microsoft tests and 44 watcher tests
passing (`docs/audits/openclaw-product/poller-expense-reconciliation.md:73-87`).
Those are regression evidence, not live Graph authentication, deployment,
schedule delivery, or invoice/CRM activation proof. No live write or workflow
was run for this audit.
