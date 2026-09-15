---
name: crm-sharepoint
description: Capture rich CRM account, opportunity, and contact context in SharePoint while keeping local CRM files as concise summary metadata.
last_edited: 2026-06-13 08:36
---

# CRM SharePoint

Use this skill when detailed account/opportunity context should live in SharePoint rather than local markdown summaries.

## Scope Boundary
This skill owns:
- SharePoint folder/file structure for accounts and opportunities
- artifact organization and cleanup
- `Current.md` maintenance
- preserving context while keeping SharePoint tidy

This skill does **not** own:
- general CRM table maintenance → use `crm-update`
- deciding commercial stage transitions → use `crm-opportunity`

This skill **does** own the filing and triage of SharePoint-delivered meeting artifacts when they belong to accounts/opportunities/strategic relationships, including Stackstone Meeting Copilot outputs. Use `reference/STACKSTONE-MEETING-COPILOT.md` for the exact file-handling rules.

## Purpose
- SharePoint = source of truth for rich account/opportunity/partnership notes and active `Current.md` truth
- Local CRM (`stackstone/crm.md`) = summary layer only
- All document operations happen via assistant@ / Graph so changes are attributable and versioned
- `reference/OPERATIONAL_ACTIVITY_LOG.md` = Tom-facing audit trail of meaningful CRM/SharePoint actions across all routes
- `reference/CRM-NEXT-ACTION-SYSTEM.md` = shared action-control model for daily-readable next-step maintenance across CRM + SharePoint

## Next-action control model (MANDATORY)
Read `reference/CRM-NEXT-ACTION-SYSTEM.md` whenever a SharePoint `Current.md` or dated artifact materially changes what should happen next.

Required rule:
- `Current.md` is not just narrative truth; it must also carry control truth near the top
- when rich context changes, update the SharePoint current file so it expresses:
  - `Last touch`
  - `Next action date`
  - `Owner`
  - `State`
  - `Next best action`
- at the moment you choose that next action, read and apply `skills/crm-follow-up/SKILL.md` so the SharePoint control truth reflects context-aware follow-up judgment
- keep this aligned with the local CRM row in the same pass or explicitly mark the mismatch state

## SharePoint-origin truth rule (MANDATORY)
SharePoint is not just a destination; it is also an origin surface.
If Tom or another agent (for example Claude, meeting-copilot, or another document workflow) changes a meaningful SharePoint file, that change must be treated as new operational truth that may require CRM summary and next-step maintenance.

**Daily-operable-current-file rule (MANDATORY):** `Current.md` must help the next read, not just preserve history. A good current file lets Tom/L1 quickly answer `what is going on?` and `what should happen next, when, and by whom?` If a `Current.md` update improves narrative truth but leaves the next action ambiguous, the update is incomplete.

Required mechanism:
1. Treat entity `Current.md` edits, new dated communication/meeting artifacts, and meeting-copilot drops as first-class monitored signals.
2. On any materially newer SharePoint truth than the CRM row, reconcile `stackstone/crm.md` to it rather than assuming the CRM row is still current.
3. If the SharePoint edit changes what should happen next, update the CRM `Next Step` / `Last Touch` in the same pass.
4. If the SharePoint write is visible but the CRM summary has not yet caught up, classify the state as drift and repair it; do not leave the mismatch as normal.
5. If a SharePoint artifact is ambiguous about owning entity or next step, fail closed and ask Tom rather than guessing.

## Multi-source reconciliation workflow (MANDATORY)

**Trigger:** Tom asks for CRM/SharePoint to be reconciled, made current, checked against mirrors, or applied across Accounts, Opportunities/organisations, Partnerships, or new relationship candidates.

**Canonical sequence:**
1. Build the complete entity spine from `stackstone/crm.md` and `stackstone/partnerships.md`; retain a checklist at `reference/reconciliation/CRM-SHAREPOINT-RECONCILIATION-STATE.md`.
2. Use bounded, read-only source passes (subject agents are appropriate) over current Outlook trusted/external/sent, Gmail, WhatsApp, Teams, LinkedIn, calendar/meeting artifacts, website activity and invoice mirrors. Each pass emits dated, source-cited evidence only: participants, facts explicitly visible, candidate entity/new-record match, and ambiguity.
3. Resolve events centrally against the entity spine, in chronological order. Do not let source agents write CRM or SharePoint. One reconciler owns entity decisions and all writes to prevent duplicate artifacts, conflicting `Current.md` versions, and timeline errors.
4. For each proven event, update the correct local summary/control, create one dated SharePoint artifact where material, refresh `Current.md`, and append the operational proof log. Use the event date—not the processing date—for the timeline.
5. Verify queue results/cache, then clear temporary `queued` language. Terminal entity states are `synced`, `blocked`, or `coverage incomplete`; old/weak controls without newer evidence must be classified `live`, `watch`, or `dormant`, not cosmetically rolled forward.
6. Before claiming a broad pass complete, every checklist entity must be terminally classified and every queued write verified.

**Fail-closed rules:** truncated/withheld content may establish a dated touch but must not establish an outcome, decision, configuration, payment allocation, or meeting result not visible in source. A plausible person/company match is insufficient where contacts span multiple entities.

## Watch mode vs reconciliation mode (MANDATORY)
Before doing SharePoint CRM maintenance, classify the pass as one of:

### Watch mode
- normal capture of a clearly identified new communication/update/artifact
- goal: keep SharePoint current truth moving with day-to-day activity

### Reconciliation mode
- Tom asks for a thorough pass, investigation, or proof that CRM/SharePoint are up to date with recent sent/inbound activity
- used when drift between mailbox reality, `stackstone/crm.md`, and SharePoint `Current.md` is the thing being checked
- if the available evidence is insufficient to prove Current-truth alignment safely, classify the state as `coverage incomplete` rather than current

## Closure-state expectation (MANDATORY)
For materially important SharePoint-triggering activity, there must be a durable proof path for what happened next. At minimum, the outcome should be provable via one or more of:
- verified `SHAREPOINT_RESULT.md`
- SharePoint cache / `SHAREPOINT_INDEX.md`
- `stackstone/crm.md` pending/confirmed wording
- `memory/monitored-items-state.json`
- `reference/OPERATIONAL_ACTIVITY_LOG.md`

If a rich-context update was seen but SharePoint truth cannot yet be proved, classify it as `pending SharePoint confirmation`, `blocked`, or `coverage incomplete` rather than complete.

## Completion-not-detection rule (MANDATORY)
This skill is not complete when a CRM/SharePoint change is merely noticed or queued conceptually.
Completion means the relevant artifact/current-truth maintenance was actually queued and then confirmed, or the pass failed closed with the exact blocker/pending state.

## Reconciliation progress and continuation rule (MANDATORY)
For a user-requested reconciliation that spans more than one entity or requires historical mirror review:
1. create and retain an explicit entity checklist (`not started` / `auditing` / `queued` / `confirmed` / `blocked` / `coverage incomplete`);
2. do not describe an audit as complete from a partial batch or a worker result — completion requires every checklist entity to be terminally classified and every queued write to be verified from `SHAREPOINT_RESULT.md` or cache;
3. while the reconciliation remains active, send Tom a concise factual progress update at least every five minutes or immediately when a material batch completes, stating the completed entities, the next batch, and blockers; and
4. after any interruption, resume from the retained checklist rather than silently ending after the most recent sub-batch.

**Mechanism:** the trigger is any explicit request to reconcile/audit CRM and SharePoint against mirrors. The source of truth is the entity checklist plus `stackstone/crm.md` / `stackstone/partnerships.md`, SharePoint cache/index/results, and the cited mirror evidence. A state of `queued` is never terminal.

## No-silent-partial-completion rule (MANDATORY)
Never describe SharePoint organisation work as `done`, `processed`, `captured`, or `updated` when only part of the chain happened.
For live CRM entities, track and report these layers separately when needed:
1. transcript/artifact retained
2. local CRM summary updated
3. SharePoint `Current.md` updated
4. proof/log layer updated
If any layer is still pending, blocked, or unverified, say that explicitly instead of collapsing everything into a generic success claim.

## Drift-prevention rule (MANDATORY)
The system must reconcile three layers, not just one:
1. SharePoint `Current.md` and dated artifacts
2. local CRM summary row (`stackstone/crm.md` / `stackstone/partnerships.md`)
3. operational log / proof layer

If any one of those moves without the others, the pass is incomplete until the mismatch is repaired or explicitly marked `Queued`, `Blocked`, or `Coverage incomplete`.
Do not treat `Current.md`, CRM, and audit log as separately-okay islands.

## Coverage-audit rule (MANDATORY)
When doing a reconciliation pass, housekeeping sweep, transcript-organisation batch, or any explicit `is SharePoint organised/current?` review, check entity coverage against the live CRM surface rather than looking at SharePoint in isolation.

Minimum audit questions:
1. Does every live Opportunity / Account / strategically live Partnership have the expected SharePoint home?
2. Does it have a usable `Current.md`?
3. Is the `Current.md` materially current relative to the latest visible activity/artifact?
4. Does the proof/log layer show the most recent meaningful state transition?

Flag these states explicitly:
- `missing folder`
- `missing Current.md`
- `stale Current.md`
- `artifact newer than Current.md`
- `CRM newer than SharePoint`
- `SharePoint newer than CRM`
- `proof missing`

Do not answer `SharePoint is organised` if those checks have not been considered for the relevant entities.

## Freshness / staleness rule (MANDATORY)
Treat `Current.md` freshness as a first-class integrity check, not a cosmetic extra.
A `Current.md` should usually be treated as stale when any of the following are true:
- a newer dated transcript/meeting/email artifact exists for the entity and the key outcome is not yet reflected in `Current.md`
- local CRM `Last Touch` / `Next Step` materially post-dates the SharePoint current truth
- the entity is commercially active and there has been meaningful movement in the last 7 days without `Current.md` catch-up
- the current file still reflects a pending/queued state that later proof has already resolved

When staleness is detected:
1. repair it in the same pass if evidence is sufficient
2. otherwise mark it `Coverage incomplete` or ask Tom, rather than leaving the stale file looking current

## Ambiguity / ask-Tom rule (MANDATORY)
If you are not materially certain which entity owns the artifact, whether it belongs under opportunity/account/partnership/internal reference, or what current-truth update should happen, ask Tom a short clarification question instead of guessing.

## Operational activity logging rule (MANDATORY)
When this skill creates, queues, confirms, retries, blocks, or materially reclassifies a CRM/SharePoint update, write a corresponding entry to `reference/OPERATIONAL_ACTIVITY_LOG.md` in the same pass.

Required mechanism:
1. Log after the state transition is known for that pass: `Confirmed`, `Queued`, `Blocked`, or `Coverage incomplete`.
2. Include: entity, trigger/source, action taken, state, proof/source, and follow-up if any.
3. If the SharePoint write is only queued, log it as `Queued` immediately rather than waiting for later confirmation.
4. If later confirmation arrives via `SHAREPOINT_RESULT.md` or cache/index, append/update the log with a `Confirmed` entry/state transition in the confirming pass.
5. Include proof-of-propagation when relevant: artifact path, CRM target, SharePoint `Current.md` target, and confirmation source.
6. Do not claim CRM/SharePoint maintenance complete unless the log entry exists or you explicitly say logging is the remaining undone step.

Fail-closed test: if Tom asks "did you actually capture that and can I review it?" the answer must be visible in `reference/OPERATIONAL_ACTIVITY_LOG.md`.

## CRM activity capture rule (MANDATORY)

**Before replying to ANY message from Tom that mentions:**
- emails/messages sent to opportunity/account contacts
- conversations/meetings with CRM entities
- project progress on active engagements
- WhatsApp screenshots involving known contacts

**STOP and complete these steps:**
1. Identify the entity (company + contact name)
2. Check whether it's in Opportunities or Accounts table in `stackstone/crm.md`
3. Queue SharePoint communication artifact (if communication happened)
4. Update SharePoint Current file (if status/progress changed)
5. Update local CRM Last Touch + Next Step in `stackstone/crm.md`
6. **Only then** reply to Tom

**Test before replying:** Could I list the entities and required updates from Tom's message without asking? If no, I haven't properly identified what needs capturing.

**Pattern examples that trigger this rule:**
- "I've sent follow-ups to Kyle, Diana, and John"
- "I'm speaking to Bekah Richens"
- "I've made a start on Andy's project"
- "Had a call with [known contact]"
- Any WhatsApp screenshot showing conversation with a CRM contact

**DO NOT:**
- Wait for Tom to say "update the CRM"
- Ask "shall I log this to SharePoint?"
- Reply first, update later
- Treat CRM maintenance as optional follow-up work

## Allowed operations
- list
- read
- create
- update
- append
- move
- delete_folder
- read_binary

## Forbidden operations
- delete files
- silent destructive overwrite

## Folder / file model
Use a folder per entity with one canonical current file plus dated artifacts.

**Folder naming rule:** Use the **organization/company name** as the folder name, NOT the individual contact name, unless it's a special case (see below).

### Opportunities
- `Opportunities/<Company>/`
- `Opportunities/<Company>/<Company> - Current.md`
- `Opportunities/<Company>/YYYY-MM-DD - <Type> - <Description>.md`

### Accounts
- `Accounts/<Company>/`
- `Accounts/<Company>/<Company> - Current.md`
- `Accounts/<Company>/YYYY-MM-DD - <Type> - <Description>.md`

### Special cases
**Independent advisers/consultants under umbrella brands:**
- St. James's Place advisers operate independently → use `[Adviser Name] - SJP`
- Example: `Andy Barrett - SJP` not just "Andy Barrett" or "St. James's Place"
- This pattern applies to any network where each person runs their own practice under a shared brand

**Default rule:** If in doubt, use the company name from the CRM company column.

### Rules
- `Current.md` = latest truth / working summary
- dated files = historical artifacts (call notes, emails, meeting summaries, proposals, updates)
- read `Current.md` first
- prefer newest dated artifacts if more detail is needed
- never treat all old files as equally current
- keep a visible **important associated people** list in `Current.md` when multiple people materially relate to the same entity
- treat the entity history as primary: do not fragment account/opportunity history just because a different individual on the client side sends the email
- structure `Current.md` so it stays daily-operable; near the top it should make it easy to find: stage/status, last touch, next action date, owner, state, next best action, current understanding, risks/blockers, and key linked artifacts

---

## How to read SharePoint (no TOTP needed)

**Browse the document tree:**
Read `~/.openclaw/workspace/SHAREPOINT_INDEX.md` — this is refreshed automatically every 15 minutes and contains the full folder/file tree of the Documents library. Use it to find paths, check what exists, and plan writes before queuing them.

**Read markdown and text files:**
For `.md` and `.txt` files, read them directly from the local cache:
- Path: `~/.openclaw/workspace/sharepoint-cache/<SharePoint path>`
- No queue entry needed
- Files are synced every 15 minutes
- Check the sync timestamp in `SHAREPOINT_INDEX.md` to see how fresh the data is

**Read binary files (.docx, .pdf, .pptx, .msg):**
Binary files are automatically extracted to text during the 15-minute sync. The extracted content is saved as `<filename>.extracted.md` in the cache directory.

Example:
- SharePoint file: `/Stackstone CRM/Proposals/Q2 Proposal.docx`
- Local extracted file: `~/.openclaw/workspace/sharepoint-cache/Stackstone CRM/Proposals/Q2 Proposal.docx.extracted.md`

Check the "Extracted binary files" section in `SHAREPOINT_INDEX.md` for a complete list of extracted files with their exact local paths.

**On-demand binary extraction:**
If you need a binary file mid-conversation that hasn't been extracted yet, queue a `read_binary` operation:
```json
[{
  "id": "sp-read-20260413",
  "operation": "read_binary",
  "path": "/Reports/Annual Review.pdf",
  "requested_at": "2026-04-13T10:00:00Z"
}]
```
The extracted file will appear at `sharepoint-cache/Reports/Annual Review.pdf.extracted.txt` within about a minute.

**Size limits:**
- Text files: up to 500 KB
- Binary extraction: up to 5 MB
- Larger files are indexed but not extracted — check `SHAREPOINT_INDEX.md` for the reason

---

## How to write to SharePoint (no TOTP needed)

Write a JSON entry to `~/.openclaw/sharepoint-queue.json`. A queue processor runs every minute and executes it automatically — no exec.run, no TOTP required.

Current architecture:
- **Cache poller** (every 15 mins): refreshes `SHAREPOINT_INDEX.md` + local cache
- **Queue processor** (every 1 min): executes queue operations and writes `SHAREPOINT_RESULT.md`
- **Housekeeping sweep** (02:00 nightly): reviews CRM entities and auto-executes safe organization changes

### Queue entry format
```json
[
  {
    "id": "<short unique id, e.g. 8 chars>",
    "operation": "create" | "update" | "append" | "move" | "delete_folder" | "read_binary",
    "path": "/Opportunities/<Company>/<Company> - Current.md",
    "content": "Markdown content here (for create/update/append)",
    "destination": "/Opportunities/<Company>/Archive/<Filename>.md",
    "requested_at": "<ISO 8601 timestamp>"
  }
]
```

- Always generate a unique `id` per entry (e.g. first 8 chars of a UUID)
- Use `destination` only for `move`
- Omit `content` for `move`, `delete_folder`, and `read_binary`
- For `create`: set `allow_overwrite: true` if you want to replace an existing file
- Multiple operations can be queued at once as an array
- Prefer `move` to de-emphasize loose/raw/source files into `Archive/` or `Source/` rather than leaving them in the active retrieval path
- `delete_folder` is only for empty folders after cleanup

### Check results
Read `~/.openclaw/workspace/SHAREPOINT_RESULT.md` after ~1 minute to confirm success. Never claim a file was created or updated unless you have verified the result.

---

## Workflow
1. **Determine the exact entity first**
   - Who is this about? (person + company)
   - What date is the note/transcript from?
   - Is it definitely this entity, not just thematically similar to another?
   - If uncertain: stop and ask Tom
2. Determine the entity stage from CRM logic:
   - Opportunity → `Opportunities/<Company>/`
   - Active Engagement / Client → `Accounts/<Company>/`

### Collaboration-vs-opportunity routing rule (MANDATORY)
Before filing a new artifact into an existing Opportunity or Account folder, ask one extra routing question:
- Is this artifact primarily about **selling/delivering work to that entity**, or is it primarily about a **strategic partner / collaboration relationship** with them?

Trigger examples that require this check:
- joint offer / joint venture / collaboration deck
- referral/channel partnership material
- co-delivery packaging or shared proposition drafting
- strategic relationship notes that are more about "how we work together" than "how we sell to them"

Required mechanism:
1. If the artifact is mainly about selling to or delivering for that company, keep it in `Opportunities/` or `Accounts/` as normal.
2. If the artifact is mainly about a collaboration partner relationship, do **not** blindly file it only under the existing Opportunity row.
3. Check `skills/crm-partnership/SKILL.md` and decide whether the person/entity needs a `Partnerships/<Person Name>/` home as the primary or parallel record.
4. If both routes are materially true, say so explicitly and either:
   - file/create the partnership record and keep a light pointer in the opportunity folder, or
   - state the ambiguity and ask Tom before creating the wrong canonical home.
5. Do not let an existing CRM row short-circuit this check. Existing placement is evidence, not proof.

Fail-closed rule:
- If a document materially changes the classification question, stop and challenge the location before treating the current folder as canon.
- For high-integrity filing work, "Tom said save it under X" is not enough reason to ignore an obviously better structural home; you must at least surface the mismatch.

3. Read `SHAREPOINT_INDEX.md` first to verify the live folder name/path before writing anything
4. Before creating a new folder/file, search the index for an existing likely match:
   - exact name
   - close spacing/punctuation variants
   - compressed variants (e.g. `CollingtonWinter` vs `Collington Winter`)
4. If an existing folder clearly represents the same entity, reuse it rather than creating a new one
5. Collate relevant artifacts before writing: recent inbox items, sent items, meeting/call notes, and any known context that materially changes understanding of the opportunity/account
6. Queue the operation — then confirm success via `SHAREPOINT_RESULT.md` before updating local CRM
7. Ensure `<Company> - Current.md` exists before writing dated artifacts
8. For new notes/communications, create a dated artifact:
   - `YYYY-MM-DD - <Type> - <Description>.md`
9. For evolving account/opportunity truth, update `<Company> - Current.md`
10. Prefer `append` for logs and historical notes
11. Use `update` for structured summary refreshes in `Current.md`
12. Keep local CRM row updated with SharePoint paths only after the exact live path is verified
13. **Verification-before-claim rule:** when answering about an entity's SharePoint state, do not treat a CRM `sharepoint_path` value as proof that the SharePoint folder/file actually exists. Verify against `SHAREPOINT_INDEX.md` or the cache first. If not verified, say it is only a CRM path value / intended path.
14. **Pending-write CRM marker rule:** when a SharePoint update has been queued but not yet confirmed, do not leave the local CRM summary pretending nothing changed. Update the CRM row/current-summary layer with a clearly marked pending state such as `SharePoint update queued 2026-04-29; not yet confirmed`, or equivalent wording in notes / next step / status context. This gives the summary layer immediate freshness without falsely claiming SharePoint success.
15. **Failure handling rule:** if the SharePoint write later fails, the CRM should already show that the intended update was pending. Then convert that pending marker into either a retried action or a concrete blocked note — do not silently revert to stale truth.
16. **Post-queue completion trigger rule:** when you queue SharePoint work that changes entity truth, you must also create an immediate follow-through step for yourself: read `SHAREPOINT_RESULT.md` after the processor window and finish the CRM transition. Do not leave the entity in a hanging pending state without an explicit verification pass.
17. **Reconciliation drift rule (MANDATORY):** if recent meaningful sent/inbound movement exists but `Current.md` still reflects an older state, treat that as an active reconciliation failure, not a cosmetic lag. In the same pass, either:
   - queue the Current-file refresh,
   - mark the CRM summary as pending SharePoint confirmation,
   - or say `coverage incomplete` / `blocked` with the exact blocker.
   Do not merely note the drift conversationally.
18. **Completion state machine:** the required sequence is:
   1. queue SharePoint write
   2. update CRM/current summary with `pending SharePoint confirmation`
   3. check `SHAREPOINT_RESULT.md`
   4. move CRM/current summary to either `confirmed` or `blocked/retry needed`
   If step 3 has not happened yet, you must say the entity is still in pending state rather than implying completion.
19. **Cache-beats-pending rule (MANDATORY):** if `SHAREPOINT_RESULT.md` is stale or missing but the latest `SHAREPOINT_INDEX.md`/cache clearly shows the target `Current.md` exists and already contains the intended factual update, do not leave CRM/current-summary wording stuck at `queued` / `not yet confirmed`. In that case:
   1. read the cached `Current.md`
   2. verify the intended facts are actually present
   3. clear the stale pending wording from `stackstone/crm.md`
   4. mark the verification basis explicitly as `cache/index confirmed` if useful
   Do not let a stale result file outrank newer cache evidence.
20. **Drift-repair-not-commentary rule (MANDATORY):** when a pass detects CRM summary wording that says `queued`, `pending`, or similar while the SharePoint cache/current file already reflects the newer truth, do not merely mention "there may be drift" conversationally. In the same pass, either:
   - repair the CRM summary wording,
   - or mark the exact blocker as `coverage incomplete` with the missing verification layer named.
   For high-integrity entity state, drift must trigger a repair state transition, not just an observation.
21. **Multi-writer summary rule (MANDATORY):** if more than one automation path can touch the same entity state (for example CRM-summary updates, AI briefing pack handoff updates, housekeeping, or post-meeting capture), the pass must reconcile the live `Current.md` content against the CRM summary row before claiming pending/queued/confirmed state. Do not assume the last process to write CRM summary still reflects the latest SharePoint truth.
22. **Writable-layers sync rule (MANDATORY):** when L1 has both read and write access to the CRM summary layer and the SharePoint current-truth layer, the default expectation is that they should be kept in sync within the same governed pass. Do not normalize divergence as a routine condition. If they are not in sync, the pass must end in exactly one of these states:
   - synced
   - blocked with named blocker
   - coverage incomplete with named missing evidence
   Never present writable-layer divergence as an acceptable steady state.
23. **Same-pass sync closure rule (MANDATORY):** if a reconciliation pass opens an entity specifically to compare CRM summary and SharePoint current truth, and both layers are writable from the current route, the pass is not complete until one of the following happens in that same pass:
   1. CRM summary updated to match SharePoint truth,
   2. SharePoint current file updated to match the intended CRM truth,
   3. exact blocker recorded,
   4. explicit `coverage incomplete` classification recorded.
   Do not stop at diagnosis alone.
24. **Sweep-before-claim rule (MANDATORY):** if Tom asks to "make it happen", "finish", or otherwise close the CRM↔SharePoint sync problem rather than just repair one named entity, do not reply with partial-progress language like "started", "begun", or "one more live case fixed" unless the request was explicitly narrowed. First convert the job into a checklist:
   1. identify likely stale entities,
   2. compare CRM summary against SharePoint current truth,
   3. repair all fixable rows in this pass,
   4. state any exact remaining blockers.
   Before replying, label the whole bundle as **done** or **blocked**, not vague progress.
25. **Search-route blocker rule (MANDATORY):** if a broad sync sweep requires search/scan capability that is unavailable in the current tool path, say that explicitly before implying completion. Name the missing route (for example gated exec search) and ask for/await the exact unblock needed rather than presenting a partial repair as if the wider sync job is underway.
18. Never delete files — you cannot delete, only copy/rename/organize

## Protected scheduled-housekeeping scope (MANDATORY)
The overnight SharePoint housekeeping runtime may discover only these business roots:
- `/Accounts/`
- `/Opportunities/`
- `/Partnerships/`
- `/Prospects/`
- `/Meeting Agent Outputs/` **as an intake/triage root only**

It must never discover, rename, move, create, update, append to, or delete anything under `/skills/`. Skill assets are governed solely through the versioned skill-library release workflow. This exclusion must be enforced in the queue/runtime boundary, not merely stated in an LLM prompt.

### Meeting Agent Outputs completion invariant
A newly dropped Meeting Agent Output is not complete because it was renamed or filed. The required state machine is:
1. read the summary metadata/content and identify exactly one owning entity using attendee domains first, then title/organiser/context;
2. if ownership is ambiguous or no single entity is proven, leave it in `/Meeting Agent Outputs/` and record `blocked` with the reason — do not move, rename or mutate CRM truth;
3. once one owner is proven, file the dated summary and later sibling `.mp4`/`.vtt` assets into that entity's canonical Account, Opportunity, Partnership or Prospect home;
4. if the meeting materially changes client/prospect/partner state, update **both** the entity `Current.md` and the local control record (`stackstone/crm.md` for Accounts/Opportunities/Prospects; `stackstone/partnerships.md` for Partnerships) in the same governed pass;
5. verify SharePoint queue/cache evidence and write the operational-log proof before calling the item confirmed.

A filing-only result where material truth changed is `pending truth refresh`, never `organised` or `complete`.

## Stackstone Meeting Copilot handling
When SharePoint receives meeting-copilot outputs, this skill should triage them using `reference/STACKSTONE-MEETING-COPILOT.md`.

Default handling:
1. Treat the `.md` meeting summary as the primary filing trigger.
2. Use `Attendees (invited)` email domains as the primary entity-matching signal.
3. Route by `Meeting type` (`Sales Call`, `Requirements / Discovery`, etc.) when deciding the dated artifact description and matter context.
4. File the summary first; attach `.mp4` and `.vtt` later as linked supporting assets if/when they arrive.
5. If multiple external domains are present or the meeting was manually entered with weak attendee data, flag ambiguity instead of guessing.
6. If the meeting is clearly internal, file it as internal reference rather than forcing it into CRM.
7. Extract and carry across the meeting's action items when they materially affect account/opportunity truth.

### Artifact-first filing rule (MANDATORY)
If Tom's requested outcome is to take meeting-agent/copilot files that have already been dumped into SharePoint and then file, rename, or organize them, treat the **new artifacts themselves** as the primary trigger and source of truth.

### Working-draft retention rule (MANDATORY)
If Tom sends or references a draft/report/deck/note for a live CRM entity or partnership thread and asks for feedback, prep, storage, or other work that depends on that artifact, default to treating the artifact itself as a retention-triggering object.

Required mechanism:
1. Ask: does this artifact itself need to exist in SharePoint for future retrieval/context, or is conversational feedback alone enough?
2. If the artifact is part of the live entity history, queue/store the artifact itself (or a clearly marked source-capture artifact if binary retention is not yet possible) in the same pass.
3. Do not stop at summarising/commenting around the artifact while leaving the artifact itself uncaptured.
4. Do not claim the artifact was stored unless `SHAREPOINT_RESULT.md` or the cache proves it.
5. If the artifact cannot yet be stored, explicitly mark that as `blocked` / `coverage incomplete` with the exact blocker.

### Full-transcript retention rule (MANDATORY)
When Tom provides a meeting transcript for a live CRM entity and wants it kept, preserve the **full transcript verbatim** in the entity's SharePoint artifact set. Do not treat compressed notes, `Current.md` updates, or CRM row updates as sufficient retention on their own.
If a secondary summary note is helpful, keep it as a companion artifact or summary section, but never as the only stored representation of the transcript.

### Transcript-follow-up output rule (MANDATORY)
When a CRM-linked transcript is supplied, do not finish with filing alone. Return a short explicit list of the actionable next steps Tom is likely to care about from that meeting/transcript, and reflect the strongest commercially relevant next step in CRM/SharePoint context where appropriate.

Do **not** block that workflow merely because a calendar-driven "meeting just ended" detector cannot identify the event.

Required sequence:
1. Inspect the newly dumped artifact(s)
2. Determine entity/date/type from the artifact metadata/content first
3. Route to the correct Account/Opportunity/internal location
4. Rename/file supporting assets consistently
5. Update `Current.md` if the artifact changes current truth
6. Only fall back to calendar context if the artifact itself is insufficient to identify the meeting safely

Fail-closed rule:
- If the artifact clearly identifies the entity/date, proceed without requiring calendar confirmation
- If the artifact is ambiguous, mark it ambiguous/blocked and say exactly why
- Do not invent a calendar-based blocker when the filing task can be completed from the artifact set alone

## Operating modes

### 1. Reactive mode (live entity work)
Use when Tom is actively discussing or working on a specific account/opportunity.

Goal: make the **minimum safe structural changes** needed for that entity right now.

Rules:
- Prioritize retrieval and document accuracy for the entity currently in play
- Capture new material promptly if it materially changes understanding
- Do light cleanup only where it is clearly safe and helpful
- Do **not** turn a live interaction into a broad cleanup sweep
- If there are many structural issues, stabilize the current entity and leave deeper normalization for batch mode

### 2. Batch housekeeping mode
Use for deliberate SharePoint organization sweeps.

Goal: improve SharePoint structure, consistency, and retrieval quality at low cost.

Rules:
- Work **entity by entity**, not random file by random file
- Prioritize **active Accounts first**, then active Opportunities
- Gather all likely changes for one entity before writing anything
- Prefer fewer, grouped writes over many tiny writes
- If the index is stale, the write path is failing, or the entity match is ambiguous, classify the work as blocked instead of forcing it

## Daily housekeeping (priority: active accounts first)
1. Check active account/opportunity folders for new files Tom has added
2. If files are loose/unorganized:
   - Copy to proper location with correct naming convention
   - Ask Tom for context if file purpose is unclear
   - Rename to match convention: `YYYY-MM-DD - <Type> - <Description>.ext`
3. If local/transitional files contain useful context, migrate that context into SharePoint before cleanup
4. Treat local fallback notes, inbox-derived notes, and transitional scaffolding as information sources — not just clutter
5. Only after useful information is migrated should the local/transitional file be marked for cleanup
6. Only create subfolders if they help YOU find recent/important information faster
7. **You own this structure** — keep it optimal for your own retrieval
8. Index and latest information is critical — always know what's recent
9. For anything beyond minimal live cleanup, switch to **batch housekeeping mode**

## Ownership / current-truth rules (MANDATORY)
- Do not stop at saying something "needs judgement" if there is already enough context to make a safe organizational decision.
- Your job is to own the SharePoint structure for retrieval, not just describe folder disorder back to Tom.
- Prefer creating/maintaining one clear current truth plus dated artifacts over leaving many loose ambiguous files in place.
- When old source artifacts still need to be kept, move or recreate them into a clear **Archive** area/foldering pattern rather than leaving them scattered as active-looking material.
- If a file is clearly source/supporting material rather than current truth, classify it as such and organize it accordingly.
- If a current summary is stale relative to newer known facts from CRM/email/Tom, update `Current.md` promptly so retrieval favors the current story over old scheduling/history noise.
- **CRM + SharePoint ownership rule:** treat ongoing CRM freshness and SharePoint current-truth maintenance as agent-owned operational work, not something to merely mention to Tom. If you detect stale account/opportunity truth, missing post-meeting capture, or structural drift, your default action is to fix it or explicitly classify it as blocked by a concrete system issue.
- **No passive drift reporting rule:** do not tell Tom that CRM/SharePoint "needs attention" unless you also state one of: (a) the fix you already made, (b) the exact queued next maintenance action you are taking, or (c) the concrete blocker preventing you from owning it end-to-end.
- **Briefing-pack engagement rule (MANDATORY):** when a website activity feed shows a `briefing_pack` engagement/view event that can be confidently mapped to an existing opportunity/account/lead, treat it as a CRM+SharePoint capture trigger. Create/queue a dated communication artifact and refresh `Current.md` where appropriate so the engagement signal is preserved in entity history, and also ensure `reference/OPERATIONAL_ACTIVITY_LOG.md` records the capture. Do not infer formal send-state from the view alone.

## Current-vs-source decision rule (MANDATORY)
When multiple files exist for the same entity, explicitly classify each as one of:
1. **Current truth** — should shape current advice and retrieval
2. **Dated artifact** — useful historical milestone/note
3. **Source artifact** — raw supporting material kept for traceability only
4. **Archive candidate** — old/duplicate/loose material that should be placed into an Archive area or clearly de-emphasized

Do not leave files unclassified if there is enough evidence to decide safely.

## Retrieval-first housekeeping mechanism (MANDATORY)
Before reporting on a housekeeping sweep, run this check for each reviewed entity:
1. What is the current truth for this entity right now?
2. Which single file should I read first next time?
3. Which loose/older files would mislead me if left looking active?
4. Did any newly found artifact or rename imply a change to current truth?
5. If yes, did I update `Current.md` and the CRM summary state, or consciously mark them not needed / pending / blocked?
6. Can I safely reorganize those misleading files into dated artifacts or Archive without needing Tom?

If yes, do it.
If no, name the exact ambiguity.

## Archive handling
- You cannot delete files, so use Archive as the de-emphasis path for old/duplicate/source material that should not sit in the active retrieval path.
- Prefer entity-local archive structure where helpful, e.g. `Archive/` under the entity folder, or clearly archived dated artifacts.
- When a safe path is obvious, prefer a real `move` into `Archive/` or `Source/` over adding another note that merely describes clutter.
- After moving contents out, use `delete_folder` to remove empty leftover folders when safe.
- The purpose of Archive is retrieval clarity: keep source material available without letting it compete with current truth.

## Batch housekeeping workflow
1. Build the candidate entity list
   - Active Accounts first
   - Then active Opportunities
   - Prefer entities with stale/loose/non-canonical files or recent activity
2. Work one entity at a time
   - Read `Current.md`
   - Read the relevant section of `SHAREPOINT_INDEX.md`
   - Identify all candidate changes before writing
3. Classify each candidate change
   - **Safe auto-organize** — clear rename/recreate/update using known context
   - **Needs Tom judgement** — ambiguous entity, unclear file purpose, uncertain date, possible duplicate with unclear canonical source
   - **Blocked** — stale index, failing write path, missing access, missing extraction, or other system issue
4. Batch the safe changes for that entity
   - Group related creates/updates/appends together
   - Minimize write count
   - Prefer one coherent entity batch over scattered single-file writes
5. Verify results before moving on
   - Check `SHAREPOINT_RESULT.md`
   - Do not claim success until verified
6. Then continue to the next entity

## Write-cost / batching policy
- Default to **fewer, larger, entity-grouped writes**
- Avoid tight loops of one-file-at-a-time writes when a grouped entity batch will do
- Do not repeatedly rediscover the same folder disorder in one run — plan once, then execute deliberately
- If a run surfaces many ambiguous items, stop batching safe work at the appropriate boundary and report the ambiguous set clearly
- If the system is degraded (stale index / failing writes), prefer a high-quality blocked summary over noisy partial attempts

## Housekeeping output contract
When reporting a batch housekeeping run, summarize in this structure:
- **Entities reviewed**
- **Safe structural changes completed**
- **`Current.md` files updated**
- **CRM summary state updated**
- **Needs Tom judgement**
- **Blocked**

For every entity touched, explicitly state:
- whether the work was **organized** (file/folder/rename/archive only) or **maintained** (current-truth also refreshed)
- whether `Current.md` was updated: **yes / no / not needed / blocked**
- whether the local CRM summary state was updated: **yes / pending confirmation / not needed / blocked**
- the concrete blocker if either truth layer was not updated

The aim is not just to say "organized" — it is to make clear what was reviewed, what changed structurally, what changed in current truth, what is ambiguous, and what is prevented by system state.

## Housekeeping completion rule (MANDATORY)
If a housekeeping run touches an entity and does not explicitly confirm the `Current.md` state and CRM summary state for that entity, the run is incomplete.

Fail-closed mechanism:
1. For each touched entity, answer: did this change only structure, or did it also change current truth?
2. If truth may have changed, explicitly check whether `Current.md` and CRM summary were updated
3. If they were not updated, mark the entity as **pending truth refresh** or **blocked**, not complete
4. Do not present a run as fully done if an entity was tidied but its truth layer is still unknown

## Pending-confirmation cleanup rule (MANDATORY)
When a CRM row says a SharePoint update/current refresh was queued or not yet confirmed, and a later verified cache/index read shows that the SharePoint current file now matches the intended state, remove the stale pending wording from CRM promptly.

Required mechanism:
1. Treat "queued / not yet confirmed" as a temporary state, not durable wording
2. On any later maintenance/audit pass that verifies the SharePoint current file, reconcile CRM wording immediately
3. If SharePoint is confirmed but CRM still says pending, fix CRM in the same pass
4. Do not allow confirmed entities to accumulate stale "queued" language, because that creates false drift and undermines trust in the summary layer

## Mgmt-bot controls
- `/sp-sync`
- `/sp-housekeep`
- `/sp-housekeep dry-run`
- `/sp-housekeep accounts`
- `/sp-housekeep opportunities`
- `/sp-housekeep entity:<Name>`
- `/sp-housekeep dry-run entity:<Name>`

## Email handling
- **Do not copy full email bodies into SharePoint**
- Maintain a timeline/log of email dates in `Current.md` or dated artifacts
- If a contact has moved from captured lead into active conversation, create a dated communication/timeline artifact promptly rather than waiting for the opportunity context to go stale
- Read both inbox and sent context when building the artifact/timeline; do not rely only on inbound messages
- Capture relevant substance from the thread: direction of conversation, commitments, asks, replies, momentum, next step, and anything material already known about the company/contact
- Emails live in inbox files (MICROSOFT_INBOX.md, etc) for reference
- Only capture key context, not full text
- **Entity-association rule:** before deciding an email/thread belongs to a new or different record, check whether the sender/recipient is one of the important associated people already tied to the account/opportunity in CRM or `Current.md`. If yes, log it back to the main entity history.
- **Associated-people maintenance rule:** when a new person becomes materially involved in an active account/opportunity, add them to the entity's important associated people list in `Current.md` so future routing stays coherent.
- **Stitching rule:** any strategically important outbound email to an account/opportunity should be capturable later as part of the relationship history, with enough context to answer "what did Tom send and why?" without re-reading the whole mailbox
- **Sent-item completeness rule:** if Tom asks to log/capture what was sent from Outlook/outbox, sweep the relevant sent items in scope before confirming completion. Do not log one obvious item and stop if another active account/opportunity/partnership send from the same live context still needs recording.

## Date verification rule (CRITICAL)
**When capturing dates in SharePoint artifacts or using CRM/SharePoint context to draft follow-ups/advice:**
1. **Verify dates against source material** — do not hallucinate or assume dates
2. If an email mentions "let's meet next Tuesday" but doesn't give an exact date → calculate it or note "TBC"
3. If a calendar invite was mentioned → check OUTLOOK_CALENDAR.md to verify the actual date
4. **Mark uncertain dates explicitly:** "proposed for ~[date] (TBC)" rather than stating as fact
5. When a meeting completes, create a NEW dated artifact with actual meeting date — don't leave old scheduling artifacts with wrong dates
6. **Weekday-label rule:** do not write conversational labels like "on Tuesday", "on Monday", "last Friday", or similar in a user-facing draft unless the weekday has been explicitly verified from the actual date. If only the date is verified, use the numeric date or a neutral phrase like "good to catch up last week".
7. **Current-year consistency rule:** when converting a verified date into a weekday, check it against the live session date/year before writing. Do not mentally reuse an old year/calendar pattern. If there is any mismatch between the remembered weekday and the verified date in the current year, the weekday label must be dropped.
8. **Fail-closed rule for uncertain-date follow-ups:** if Tom says he does not remember the exact dates, treat the output as high-integrity. Verify each entity separately from the source artifact before drafting, and if the weekday/day wording is not verified, omit it rather than guessing.
9. **Mechanism:** before any user-facing draft that references a recent meeting date, run this mini-check explicitly: (a) what is the exact date from source? (b) what year is that date in? (c) what weekday does that exact date fall on in that exact year? (d) does my wording match all three? If I have not checked all four, I must use date-only or no weekday at all.
10. **Tom's date-year gate:** always ask myself, in this order, **"What date is/was it? What year is/was it?"** before giving a day of the week. The weekday is not allowed to appear until both answers are known.

## File organization principles (corrected 9 April 2026)

**DO NOT leave files scattered. Consolidate and mark for deletion.**

### Workflow for organizing files:
1. **Read the file** — extract all important content
2. **Create properly organized artifact** with content in correct location/naming
3. **Tell Tom which files to delete** — "File X can be deleted - content now in Y"
4. **Don't create reference notes to scattered files** — that loses context
5. **Exception: Large binaries that can't be extracted** (audio/video) — document and ask Tom how to handle

### Known limitations (updated 13 April 2026):
- **Binary extraction now available** — `.docx`, `.pdf`, `.pptx`, `.msg` are automatically extracted to `.extracted.md` files in the cache
- **Audio files (.m4a, etc):** Cannot extract, need different approach
- **Large files (>5 MB binaries, >500 KB text):** Indexed but not extracted — check `SHAREPOINT_INDEX.md` for size/reason

### Artifact creation from source files:
- Extract key information into properly named/dated markdown
- Include context, outcomes, next steps
- Don't just point to originals — capture the substance
- Once extracted → mark original for deletion

### Tom will delete files
- You cannot delete
- You CAN tell Tom what to delete once you've processed it
- This keeps things organized, not scattered

## Deduplication rules (added 9 April 2026)
- **Check for duplicates within folders:** Same file in multiple places = create one reference note pointing to canonical location
- **Check between Opportunities and Accounts:** When entity migrates from Opportunity → Account, don't duplicate files — create reference notes in Accounts folder pointing to Opportunities folder originals if still relevant
- **File naming convention:** All files MUST have dates in the name: `YYYY-MM-DD - [Type] - [Description].ext`
- **Files without dates:** Add dates when you organize them (use file modified date or context to infer)
- **Loose files:** If file is at account root and should be in subfolder → copy to proper location with dated name, create reference note if original needs to stay

## Organization sweep checklist
When organizing a folder:
1. Check for files without dates → rename with dates
2. Check for duplicates → consolidate to one reference
3. Check for files in wrong location → copy to correct spot
4. Check for large binaries → create reference notes
5. Update Current.md if new material changes understanding
6. Check related folders (if Opportunity, check if Account exists; if Account, check if Opportunity has duplicates)

## Stage rules
- Website enquiry + real conversation → Opportunity folder in SharePoint
- Event/networking lead + real email conversation or warm follow-up thread → Opportunity folder in SharePoint
- Paid work booked/committed → migrate/create under Accounts in SharePoint
- Active opportunities/accounts must be excluded from generic campaigns

## Migration rule: Opportunity → Account
When paid work is booked or committed:

1. Change stage to `Active Engagement` or `Client`
2. Ensure an account folder exists under `Accounts/<Company>/`
3. Update/create `<Company> - Current.md` there
4. Preserve historical context by copying or recreating essential summary/history from the opportunity into the account current file
5. Continue all future notes in the Accounts folder
6. Update local CRM summary to point at the Accounts path, not the old opportunity path
7. Do not delete historical opportunity materials unless Tom explicitly asks

## Safety rules
- Read `SHAREPOINT_INDEX.md` before every write — never assume a path exists
- Confirm results in `SHAREPOINT_RESULT.md` before declaring success
- Never replace a placeholder path in local CRM with a SharePoint path until the path is verified live
- Never create a new entity folder without first checking the index for sensible existing variants
- `SHAREPOINT_INDEX.md` is at most 15 minutes old — if timing is critical, queue a `list` operation to get a fresh view
- You cannot delete or move files — only copy/rename/organize
- You cannot move files in SharePoint — you can only create copies with new names/locations
- **If a CRM row points to a SharePoint `Current.md` (or relevant dated artifacts) and Tom asks for advice, drafting, strategy, or next-step recommendations about that account/opportunity, do NOT answer from local CRM summary alone. Queue SharePoint reads first, wait for the results, and only then answer.**
- **While waiting on SharePoint reads, explicitly tell Tom what you are doing and that you are waiting for the richer account notes before advising.**
- **If the read results have not arrived yet, say that plainly and refuse to guess. Do not draft from partial context.**
- **Do not overwrite `sharepoint-queue.json` with a new job while waiting for context-critical reads unless you first confirm those reads have completed or failed.**

## Housekeeping triggers

### Trigger model (MANDATORY)
Own CRM + SharePoint with a two-layer trigger model:

1. **Event-driven targeted maintenance** — update one entity when a specific thing changes
2. **Scheduled coverage sweep** — run broader hygiene/current-truth review so drift does not accumulate silently

Do not rely on memory or vague intention. Every CRM/SharePoint action should be initiated by one of the explicit triggers below.

### Event-driven targeted maintenance triggers
These triggers initiate **entity-specific maintenance**:

- **Meeting completed**
  - Trigger: a calendar event relevant to a CRM entity has ended
  - Action: check whether the meeting created new truth (outcomes, next steps, changed momentum, follow-up commitments)
  - If yes: update `Current.md` and/or create a dated artifact for that entity

- **Meaningful email movement**
  - Trigger: a real inbound or outbound email materially changes status, momentum, next step, commercial direction, or understanding
  - Action: capture the change against the entity instead of leaving it only in inbox/sent history
  - Ignore trivial acknowledgements, newsletters, or non-substantive admin noise unless they change the operational state

- **Tom provides material new context**
  - Trigger: Tom mentions a meeting, call, decision, proposal movement, deliverable, concern, or anything that changes the entity story
  - Action: treat that as a CRM/SharePoint update signal, not just a conversational fact

- **New or loose SharePoint artifact detected**
  - Trigger: housekeeping/index review finds a new file, undated file, duplicate, root-level clutter, or active-looking source artifact for an entity
  - Action: classify it, organize it, and refresh current truth if the artifact changes understanding
  - **Mandatory latest-notes rule:** if the new file materially changes the entity story, update the entity's `Current.md` / latest notes layer as part of the same maintenance cycle. Do not leave the new file filed while `Current.md` stays stale.

- **Drift surfaced during any other workflow**
  - Trigger: while doing standup, inbox review, CRM review, account advice, or SharePoint work, you notice stale `Current.md`, stale CRM summary, missing post-meeting capture, or misleading active-looking old files
  - Action: immediately convert that observation into maintenance work for the entity

### Scheduled coverage sweep triggers
These triggers initiate **broader review / cleanup**:

- **Daily housekeeping sweep**
  - Trigger: scheduled recurring SharePoint/CRM housekeeping run
  - Scope: active Accounts first, then active Opportunities
  - Purpose: catch anything event-driven maintenance missed, refresh stale current truth, and reduce structural drift

- **Morning standup drift escalation**
  - Trigger: the morning standup detects CRM/SharePoint truth that is stale enough to mention
  - Action: do not merely report it; create same-day maintenance work automatically unless already fixed or concretely blocked

- **Manual explicit review request**
  - Trigger: Tom asks to check, organize, reconcile, or review CRM/SharePoint
  - Action: perform either entity-targeted or full-sweep maintenance depending on scope

### Live trigger routes (CURRENT IMPLEMENTATION)
These are the concrete firing paths that make the trigger model real:

- **Email movement route:** the recurring inbox-watch cron is an active trigger source. When it sees meaningful CRM/account/partnership thread movement, it must capture the communication into SharePoint and refresh current truth rather than just alerting Tom.
- **Meeting-completion route:** a dedicated recurring post-meeting CRM/SharePoint capture sweep is the active trigger source for recently ended CRM-relevant meetings.
- **Daily coverage route:** the recurring SharePoint housekeeping cron is the active full-sweep trigger.
- **Standup drift route:** the morning standup is an active detection route. If it surfaces stale CRM/SharePoint truth, it must either do the maintenance in-run if safe/small or create same-day agent-owned follow-up work rather than leaving a passive note.
- **Manual route:** Tom can always trigger targeted or broad maintenance directly in chat.

### Escalation rule: targeted vs full sweep
When a trigger fires, decide the scope explicitly:

- **Targeted maintenance** if the trigger is about one entity or one fresh change
- **Full sweep** if:
  - multiple active entities are stale,
  - drift appears systemic,
  - a scheduled housekeeping run is due,
  - standup surfaces stale truth across the pipeline,
  - or Tom asks for broad cleanup/check-in

### Action contract when a trigger fires
For every trigger, do exactly one of these:
1. **Fix now**
2. **Queue the maintenance action**
3. **Mark blocked with a concrete blocker**

Never stop at "needs attention" without one of those three outcomes.

### Trigger logging rule
When reporting CRM/SharePoint status back to Tom, make the initiator visible when useful:
- what triggered the maintenance
- whether it was targeted or full-sweep
- whether the result was fixed / queued / blocked

This keeps ownership grounded in actual mechanisms rather than vague promises.

### Existing trigger list
- **Daily:** Check active accounts/opportunities for new files (prioritize most active)
- **On demand:** When Tom says "organize X" or "check SharePoint"
- **Scheduled owner tasks:** If Tom tells you to organize a SharePoint folder at a future time, treat it as work you own. Schedule an agent task for yourself to do the organization at that time — not a reminder back to Tom.
- **After Tom adds context:** When Tom mentions a call/meeting/email, check if it needs to be captured as a dated artifact
- **After meeting completion:** When creating a new meeting artifact, check for stale prior artifacts referencing the same event (scheduling emails, tentative dates) and either update them or flag for deletion

## Self-improvement rule (added 9 April 2026)
**When you realize something needs to be tracked/organized differently:**
1. Update this skill file immediately
2. Don't wait — if you just learned it, write it down
3. Patterns that work = new rules
4. Mistakes that happened = guardrails to add

**This skill is living documentation of what works.**

## Task vs Backlog distinction (learned 9 April 2026)
**BACKLOG.md = coding/technical:**
- Python scripts, pollers, .py functions
- Replit work
- System improvements, features
- Anything that requires development

**TASKS.md = non-code actions:**
- Spending limits, API limits
- Admin tasks
- Tom's deliverables
- No coding required

**Both files:**
- Every item MUST have "Added: YYYY-MM-DD HH:MM" timestamp on creation
- Format: `**Added:** YYYY-MM-DD HH:MM` or `**Added:** YYYY-MM-DD (exact time unknown)`
- Timestamp is NOT optional - add it when you create the item, not retrospectively
- If unsure which file → ask Tom

**Never duplicate between files.**

**Friday review:** Both files reviewed with Tom weekly. Check SYSTEM_MAP.md for process.

## Completion discipline (learned 9 April 2026)
**When you hit a blocker during a task:**
1. Finish everything you CAN finish first
2. Complete all finishable parts
3. THEN present blockers as a separate clean list
4. Don't stop mid-task and ask for help
5. Give Tom ONE status message:
   - "Done: X, Y, Z"
   - "Need help: A, B, C"

**Never leave work half-done because one part is hard.**

## Iteration discipline (learned 9 April 2026)
**When you get corrective feedback 2+ times on the same piece of work:**
1. Stop iterating within your current approach
2. After the SECOND correction, ask: "What am I fundamentally misunderstanding?"
3. Don't assume you can fix it with another tweak
4. Your frame is probably wrong, not your execution

**When you say you've "learned" something:**
- Write it down in a skill file (concrete change)
- Not just: "I'll think harder next time" (platitude)
- Actual change = persistent behavior modification
