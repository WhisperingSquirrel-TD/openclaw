# Current code and skill audit

Audit date: 2026-09-15.

## Status and scope

**The current-skill/source audit is complete. Live operational verification and
the whole-product repair are not complete.**

The live SkilzVolt catalogue contained 75 skills. All **70 non-cartoon skills**
were inspected at their approved, version-pinned bodies, including continuation
chunks. Five cartoon skills were excluded at the owner's request. Catalogue
revision `b95e7feae0186f85306d6000a48ca6c144aeec030d58cfc5e7e171931cb79b12`
was rechecked after retrieval and reported unchanged.

| Coverage                                         | Included | Detail and machine-readable evidence                                       |
| ------------------------------------------------ | -------: | -------------------------------------------------------------------------- |
| Finance, expenses, CRM and invoices              |       14 | [Report](skills-finance-audit.md), [JSON](skills-finance-audit.json)       |
| Intake, tasks, messaging and reminders           |       11 | [Report](skills-operations-audit.md), [JSON](skills-operations-audit.json) |
| Platform, authentication and skill governance    |       18 | [Report](skills-platform-audit.md), [JSON](skills-platform-audit.json)     |
| Planning, calendars and other non-cartoon skills |       27 | [Report](skills-other-audit.md), [JSON](skills-other-audit.json)           |
| Runtime ownership and retirement                 |        — | [Source/installer inventory](runtime-ownership-audit.md)                   |

The detailed reports distinguish current approved skill instructions, repository
capabilities, installer declarations, archived snapshots and unknown live state.
They record source references, skill versions, inputs, invocation paths,
approval boundaries, executors, destinations and readback gaps. Scanner cautions
did not withhold the inspected content; it was treated as untrusted audit input,
not executed.

Earlier `review-brief.md`, `activation-matrix.md` and `repair-status.md` describe
historical snapshot/repair stages. They are not the current skill catalogue or
proof of today's deployment. This file is the entry point for the current audit.

## Findings that require action

### 1. Management-bot Git credential exposure — confirmed source defect

The clone path embeds `GITHUB_TOKEN` in a Git URL passed in process arguments.
Git can persist that URL in the destination repository's configuration.
The related push path also needs review. See the platform report's
`SEC-MGMT-BOT-GITHUB-URL-CREDENTIAL-EXPOSURE` finding and
`attached_assets/integrations/mgmt-bot/mgmt-bot.py:3044-3058,3100-3118`.

Remove credentials from URLs and arguments using an appropriate credential
helper or ephemeral authentication mechanism. Add offline tests for argv,
stored origin URLs and failure-output redaction. This audit did not invoke
the vulnerable operation, inspect credentials or establish a live leak.

### 2. Runtime ownership and deployment — unresolved live evidence

The source-controlled five-minute expense timer conflicts with operating
guidance describing its retirement in favour of a central router invocation.
The current checkout does not establish the central unit's deployment.
Other service, schedule and source-copy declarations also require live mapping.

Do not enable both paths, replace the router, or delete sidecars based on these
documents alone. Establish active readers/writers and observe the relevant
schedule interval before retirement.

### 3. Skill/source contract differences — confirmed text/source differences

- Google authentication references a helper/flow not established by the
  checked-in implementation.
- WhatsApp documentation uses different 48-hour and 72-hour windows.
- Skill creation and skill update guidance differ over the retired
  SharePoint skill-library authority.
- Some installer schedule declarations conflict with scheduling guidance.
- Invoice skills name specific executors absent from this checkout.
  Their presence on the live machine or another source tree is unknown.

These findings warrant reconciliation with the actual executor and approved
contract. They are not, individually, proof of a failed live service.

### 4. Central CRM and other end-to-end journeys — unverified, not absent

`crm-update` and its related skills are procedural capabilities delivered to
the model through SkilzVolt. They do not necessarily require a dedicated CRM
worker. The narrow CSV importer is only one source-controlled subroute;
its limitations do not prove the broader skill is unimplemented.

The missing evidence is actual invocation with complete inputs, correct
entity/contact/speaker attribution, authorised writes, and independent
destination readback. CRM is a priority for that verification.

Apply the same standard to invoice, email, calendar, task and reminder paths.
Do not infer approval bypass from an automatic queue consumer alone. Direct
TOTP-gated execution and signed exact-draft permits can be different legitimate
routes; trace the real producer, authorisation and final executor.

### 5. Excel authority — preserve the implemented contract

The finance and expense contracts use living SharePoint `.xlsx` ledgers,
native version/eTag protection and destination readback. Do not replace them
with Markdown or a separate independently editable SQLite authority.
The inspected source has substantive boundary and recovery tests, but those
tests do not establish which code is running on the Pi.

## Live audit completion gate

The available SkilzVolt connection exposes skills, not a remote terminal,
service units or runtime logs. No current active-instance identity was
established through this workspace.

Before calling the product verified, obtain:

1. Active service identity, executable realpath, working directory, profile,
   state path, port, checkout commit and relevant deployed source hashes.
2. Effective skill-provider configuration and a current skill retrieval trace.
3. Complete user/system timers, OS cron and native gateway cron inventory,
   with invocation/delivery evidence rather than schedule text alone.
4. Producer → approval gate → final executor evidence for protected routes.
5. Independent destination receipts for CRM, Excel/receipts, invoice, email,
   calendar, task continuation and reminders.
6. Consumer migration and schedule-interval parity before any runtime removal.

Do not collect credential values or unrestricted environment/config dumps.
Read-only evidence gathering must identify the installation before any
deployment, restart, permission change or live mutation.

## Changes and verification during this audit

Only audit documents and an outdated Git-capability statement in `replit.md`
were changed. No production code, live skill, schedule, permission, ledger or
service was changed. No app workflow was restarted.

Validation covers JSON parsing, unique catalogue coverage, report consistency,
source-reference review and diff hygiene. Existing automated-test evidence is
labelled as such in the reports; no new runtime test pass or live journey is
claimed by this audit.
