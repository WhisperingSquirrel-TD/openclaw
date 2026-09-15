# Invoice integration contract repair

**Status:** five governed corrections are pending human review; the live
executor contract remains blocked.

**Scope:** invoice-create, invoice-generate, invoice-chase, invoice-update, and
invoice-close only. This record makes no ledger, tracker, SharePoint, email,
credential, installer, schedule, or active live-skill mutation.

## Decision

Do not substitute a checkout implementation for the invoice commands named by
the live skills. The checkout has no authoritative copy of either named
executor and no verified Invoice tracker adapter/schema. Therefore no command
may report a tracker update, PDF upload, email send, chase, closure, or
generation success from this checkout.

This is intentionally narrower than the finance/expense boundary. The existing
SharePoint-authoritative XLSX contract remains unchanged; it does not prove an
Invoice tracker command contract and must not be repurposed as one.

## Evidence reviewed

| Evidence                                                                                                                                                  | What it establishes                                                                                                                                                                           | What it does not establish                                                                                                          |
| --------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `skills-finance-audit.md` §§invoice-close, invoice-chase, invoice-generate, invoice-create, invoice-update; `skills-finance-audit.json` `INVOICE-ABSENCE` | The checkout and installer do not contain/link `invoice_ops.py` or `invoice_generate.py`; generic Microsoft send transport is not invoice orchestration.                                      | That either executable is absent from the external/live Pi.                                                                         |
| Current pinned SkilzVolt reads                                                                                                                            | All five invoice skills are unarchived and current at the IDs/hashes listed below; their command layers name the external scripts. No attached resource contains an executor.                 | Executable contents, options, tracker fields, approval enforcement, deployed hash, or a live readback.                              |
| `attached_assets/Pasted--Invoice-billing-files-under-home-tomdean88-openclaw-ho_1788454201296.txt:142-145`                                                | A retained file listing recorded the two paths under a prior/other `~/.openclaw` tree.                                                                                                        | A current file, its contents, provenance, hash, permissions, or runtime activation. A pathname listing is not an executor recovery. |
| Repository and retained source search                                                                                                                     | No `invoice_ops.py`, `invoice_generate.py`, `generate-invoice.py`, or Invoice tracker adapter was recovered. Git history contains only the separate laptop package for tracked invoice files. | That untracked/live source can safely be copied, invoked, or replaced.                                                              |
| `invoice-laptop-package/README.txt:4-5,24-34`                                                                                                             | The retained laptop generator is an offline preparation tool with local draft JSON save/load. It explicitly never sends, updates a tracker, or marks an invoice sent.                         | Compatibility with the live tracker, PDF upload, email send, TOTP gate, or an integration executor.                                 |
| `.local/intake-repair/scripts/invoice_payment_reconciliation.py:1-10,46-102` and its test                                                                 | The retained reconciliation helper is deterministic and non-mutating; it emits pending/blocked receipt proposals only.                                                                        | Invoice tracker schema, payment closure authority, approval, or destination readback. It is not `invoice_ops.py`.                   |

### Pinned live-skill reads

These were fetched read-only through `mcpSkilzVolt_skillsGet` with the stated
`skill_id` and `version_id`. Each response reported `archived=false`,
`version_is_current=true`, no resources, and `origin=workspace-authored`
untrusted content. The content hashes match the finance audit.

| Skill            | Pinned version                         | SHA-256                                                            | Named command family                                     |
| ---------------- | -------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------- |
| invoice-create   | `7ca3b387-fe08-446c-b23f-bfbfbcf2fff4` | `91af50038a0792efc6a4f188a4341372117858afb63a14924da40c5e0ec53db7` | `invoice_ops.py create` / `create-from-context`          |
| invoice-generate | `f95cf1d6-dd81-4ed0-91ac-6fd7a9cd5b02` | `a26673c85ae6b7ee5d91e4b60b300f6044b1eab08e5a78bde6ee41d772092d3a` | `invoice_generate.py`; `invoice_ops.py find/list/update` |
| invoice-chase    | `9c2574bf-a7ca-448f-8996-dd33fadcf87b` | `96e577bf4f74b25d2053064d0db43cb85d655ccff6bc77e598856f432491ba8c` | `invoice_ops.py chase --dry-run` / `--send`              |
| invoice-update   | `03fa23f0-abd2-46da-aef9-a5f6362dfac7` | `fc4bdefb2adf56f39da482b49f5580df454a6ce38d92e1759da3d637d7d56e72` | `invoice_ops.py find/list/update`                        |
| invoice-close    | `21d04288-e654-49e1-bf43-c4555f2729db` | `e3f7d97c3707e88078ed93b0c619203495202f8bcff0e775490a7ec681687bf5` | `invoice_ops.py update`                                  |

## Fixed

1. **Checkout compatibility is explicitly fail closed.** No recovered source is
   presented as `invoice_ops.py` or `invoice_generate.py`, and no wrapper,
   worker, schema, spreadsheet writer, or send path was added.
2. **The safe retained behaviours are preserved.** The laptop package remains
   draft/print-only, and the payment helper remains a non-mutating
   proposal-builder. Neither is promoted into the protected invoice path.
3. **A minimal, ready-to-apply live-skill correction is specified below.** It
   removes the unsafe implication that a command named in a skill is available
   from every checkout, while retaining the existing draft, exact-row,
   ambiguity, signoff/TOTP, PDF verification, and destination-readback rules.

No executor behavior has been declared fixed. In particular, “fixed” above
does **not** mean an invoice was generated, stored, sent, updated, chased, or
closed.

## Blocked

| Blocker                              | Effect                                                                                     | Required evidence before unblocking                                                                                                                  |
| ------------------------------------ | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| No recovered executor source         | Cannot safely adapt, test, or install the named implementation.                            | Authoritative source location/owner plus immutable content hash for both executable files.                                                           |
| No verified live command contract    | Command flags and output cannot be inferred from skill prose.                              | Read-only `--help`/documented interface evidence and fixture-safe invocation evidence for each used command.                                         |
| No Invoice tracker schema or adapter | No field name, selector, ID allocation, or update semantics can be invented.               | Read-only exact-row result and adapter/schema contract, including ambiguity behavior and current-destination authority.                              |
| No approval binding evidence         | TOTP/open-window and any signed-send permit cannot be assumed to reach the final executor. | Producer → approval/signoff → final-executor trace for create/update/close/chase/send/generate.                                                      |
| No destination receipts              | Draft, local PDF, queue acknowledgement, or mirror is not completion.                      | Independent tracker readback; for generation, PDF extraction comparison and retained-file proof; for send/chase, send receipt plus tracker readback. |

Until all applicable evidence exists, state explicitly that the invoice
executor contract is unverified. Preserve a draft/proposal if one already
exists, name the missing evidence, and do not issue a success claim or perform
a retry against a guessed command.

## Precise safe skill correction

Each submitted full-body proposal adds this paragraph immediately before the
existing **Command layer** (or, for invoice-generate, before **The Invoice
Generator Script**). It retains the named executor paths as compatibility
references rather than silently replacing them. Other than the targeted
availability qualifiers in invoice-generate, the proposals preserve the
complete current body, including business, draft, ambiguity, approval/TOTP,
XLSX/ledger, PDF verification, and readback requirements.

> **Executor-contract guard (MANDATORY):** The command names below identify a
> separately deployed invoice integration; they are not supplied by this
> checkout. Before an action that can create or alter an authoritative tracker
> row, upload/retain a PDF, send a message, or change chase/closure state, a
> maintainer must verify the deployed executable identity and hash, documented
> command/options, current tracker adapter/schema, approval binding, and
> destination readback route using read-only evidence. Do not infer any of
> these from a local mirror, generic Microsoft sender, generic SharePoint
> queue, prior invoice, or a pathname listing. If that evidence is unavailable,
> preserve any draft and fail closed as
> state that the invoice executor contract is unverified, identify the missing
> proof, and do not run a guessed command, write a ledger/tracker, upload, send,
> or report completion.

The submit rationale and exact body differences additionally qualify
invoice-generate's unsupported statements that the executable is present in
this checkout or that it will perform upload/tracker/send work. They now state
those as required evidence from the verified deployed implementation. No
generic schema, `send.py` permit mapping, alternative executor, or executable
error code was invented.

### Governed proposal status

Pending proposals were checked first for all five skill IDs; each returned an
empty pending list. The following version-pinned, full-body proposals were then
submitted with no metadata or resource changes. Their review packages were
retrieved; each word diff is ready, merge state is clean, and the next action
is `await_human_review`.

| Skill            | Base version                           | Proposal ID                            | Proposed body SHA-256                                              | Review snapshot SHA-256                                            | Status                |
| ---------------- | -------------------------------------- | -------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------ | --------------------- |
| invoice-create   | `7ca3b387-fe08-446c-b23f-bfbfbcf2fff4` | `24cbc8f8-564e-4861-8446-f03b85774b6b` | `59be044d49b1ca59775f62357693f3b8d26304d1025865344dfc541bd72d09db` | `306223036ad7cac51a1cb29585424fed06aab566d5f6b1f017f37f206599064b` | pending, human, clean |
| invoice-generate | `f95cf1d6-dd81-4ed0-91ac-6fd7a9cd5b02` | `2e495692-435e-402c-8446-7868b83d9311` | `7aee66f1efe20521a1e6db23fb2b5af7042770b3dcda73d0365661ea28aab4cd` | `fc2002c0226bb0128372d3006b69b187728fca409eb901c4d8dd079c154dda00` | pending, human, clean |
| invoice-chase    | `9c2574bf-a7ca-448f-8996-dd33fadcf87b` | `03c130e9-3736-4e3f-907e-1f1b299b4bef` | `01023d100cebac82a07ba403770eee60c342b8cd2165c7a20c6e2d704d763b83` | `bcfbe7ee689c98d6328cbd0510923ee31ee41b880a66ac2f246c74c241364518` | pending, human, clean |
| invoice-update   | `03fa23f0-abd2-46da-aef9-a5f6362dfac7` | `a46ffb78-6fed-424a-b4c6-8838afc40a21` | `66d22aecb0af111ab629a84b00d6c33db7efc30e64b912c21dfc7803f993ccf6` | `9da9321c2c542441418b63ddfcdaf2e78be6ddac69e2f3907a969eb4b25d7af8` | pending, human, clean |
| invoice-close    | `21d04288-e654-49e1-bf43-c4555f2729db` | `f07c0fce-e068-4a10-b23c-dccba3b73d18` | `3f45f6df0b7e8170344db16e1177c76e332273dd4e3b7e7640762241713d541a` | `6ebbfe79f5d825821ddd88c8decd17e0e0a3c2323f62e4c9b984d645a49dc4df` | pending, human, clean |

These are not active edits, and no originating-agent review was submitted:
human approval remains required. No resulting version ID exists at this point.

## Offline verification boundary

No integration code was adapted because no authoritative executor was
preserved. The retained non-mutating payment-helper tests are the only
identified invoice-domain offline tests:

`.local/intake-repair/tests/test_invoice_payment_reconciliation.py`

They cover exact, partial, duplicate, mismatched-reference, currency-mismatch,
overpayment, and integer-minor-unit proposal cases. They do not exercise—and
must not be represented as exercising—Invoice tracker writes, XLSX handling,
PDF upload, email send, TOTP, or live readback.

When authoritative source is supplied, add fixture-only tests at its owning
location before any deployment change:

1. exact selector versus multiple/zero matches;
2. dry-run has no tracker, XLSX, SharePoint, email, or ledger side effect;
3. mutation refused without the real approval binding;
4. create/update/close/chase results stay blocked without independent
   destination readback;
5. generation PDF text matches the selected source row after the documented
   date conversion;
6. send/chase proves recipient, idempotency, send receipt, and post-send
   tracker readback.

## Unblock procedure

1. Obtain a read-only, bounded inventory from the owning live checkout:
   executable realpath, owner, content SHA-256, interpreter/dependency
   identity, and supported command help. Do not collect credentials or dump
   unrestricted environment/configuration.
2. Obtain a redacted, read-only tracker contract showing stable row identity,
   selectors, accepted mutation fields, duplicate/ambiguity behavior, and
   readback proof. Do not derive it from this document or an XLSX ledger.
3. Trace and verify the actual approval/signoff/TOTP route to the final
   executor, separately from any generic send permit.
4. Recover source only when ownership and hash establish it is the
   authoritative implementation. Preserve it as a reviewed source change;
   do not overwrite the unknown live copy.
5. Run fixture-only tests, then a separately approved operational validation
   with independent receipts. Only then replace the guarded skill wording with
   verified executable citations.
