---
name: crm-update
description: Maintain CRM truth for contact, account, opportunity, and partnership activity, including Last Touch, dated Next Step, stage discipline, and required SharePoint coordination.
metadata: { "openclaw": { "emoji": "📊" } }
last_edited: 2026-06-10 11:44
---

# Stackstone CRM

## Scope Boundary
This skill owns:
- CRM table maintenance in `stackstone/crm.md`
- campaign status and hygiene
- bounce/unsub/reply tracking
- lead import/update discipline

This skill does **not** own:
- rich SharePoint file organization → use `crm-sharepoint`
- opportunity stage design / later-stage commercial handling → use `crm-opportunity`

## CRM activity capture rule (MANDATORY)

**This rule applies to ALL CRM-relevant activity Tom mentions, not just scheduled CRM update runs.**

**Before replying to ANY message from Tom that mentions:**
- emails/messages sent to opportunity/account contacts
- conversations/meetings with CRM entities
- project progress on active engagements
- WhatsApp screenshots involving known contacts
- Any communication with someone in the Opportunities or Accounts table

**STOP and complete these steps:**
1. Identify the entity (company + contact name)
2. **Immediately determine if this is CRM-summary-only OR CRM+SharePoint** (use rich-context escalation rule below)
3. Update local CRM `Last Touch` date to today
4. **Run the next-step maintenance check (MANDATORY):** after every meaningful CRM update, either set/refresh a concrete `Next Step` / next action, or explicitly record why there is no actionable next step yet. Do not leave a live entity with stale generic wording like `awaiting reply` if a more useful chase/nudge/follow-up action can be named.
   - **Required routing:** at the moment you choose or refresh the next action, read and apply `skills/crm-follow-up/SKILL.md` so the follow-up decision is context-aware, not just momentum-driven.
5. Update `Next Step` if the activity changed what happens next
6. If the contact was in Leads but is now having real conversations, promote to Opportunities
7. **If rich-context escalation triggered:** read `crm-sharepoint` skill and execute SharePoint coordination NOW, not later
8. **Only then** reply to Tom

**Fail-closed test before replying:** Can I answer "Was SharePoint updated?" with YES or EXPLICITLY-NOT-NEEDED? If the answer is "not yet" or "I'll do it later", the CRM work is incomplete and I must not reply yet.

### Rich-context escalation rule (MANDATORY)
If Tom provides **substantive detail** about a CRM entity — for example a call summary, meeting notes, project context, several factual bullets, operational pain points, stakeholder observations, commercial terms, dates/options, or wording that would be useful later even if the CRM row disappeared — you must treat the work as **CRM summary + SharePoint capture**, not CRM-only.

### Multi-context contact attribution rule (MANDATORY)
When an inbound item comes from a person who is linked to multiple CRM/partner contexts, do not assign the item to a specific company/opportunity/account unless the visible subject/body, authoritative source, or Tom explicitly confirms the context.

Required mechanism:
1. Check whether the contact appears in more than one CRM/opportunity/partnership context.
2. If the body/content is withheld or ambiguous, record the item as contact-level `coverage_incomplete` or ask/await Tom confirmation rather than choosing the most familiar row.
3. If Tom confirms the context, update only that confirmed row and undo any wrong-row attribution.
4. If the contact is primarily a strategic partner but the message is about one opportunity, update the opportunity row for the specific context and retain partner context only if it helps future routing.

Fail-closed test: if the same person could plausibly be talking about more than one active opportunity, and the content is not visible, do not pick a CRM row from sender identity alone.

### LinkedIn mirror reconciliation rule (MANDATORY)
When a LinkedIn mirror capture/route result, cron delivery, or mirror-derived summary surfaces one CRM-relevant contact/message:
1. Do not assume the delivered snippet is the only commercially relevant LinkedIn movement from that pass.
2. Read `memory/linkedin-crm-proposals.json` and `memory/linkedin-messages.json` for the same capture window before replying if Tom is being told what moved.
3. Cross-check the visible participant names against both `stackstone/crm.md` **and** `stackstone/partnerships.md`.
4. If a known opportunity/account/partnership contact appears in the same capture batch but was classified `not_needed` / omitted by the mirror router, fail closed: tell Tom the mirror classification looks incomplete and name the omitted contact(s) rather than forwarding a narrower summary as if exhaustive.
5. If the omitted contact is commercially live, update the relevant CRM/partnership next-step handling in the same pass or state exactly why not.

Mechanism: on any LinkedIn mirror result mentioning a CRM/partnership person, search `memory/linkedin-crm-proposals.json` for the current batch, scan `memory/linkedin-messages.json` thread participants/previews for other named contacts, then verify each against `stackstone/crm.md` and `stackstone/partnerships.md` before deciding what to surface.

Fail-closed test: if Tom could reasonably ask "what about Grant/Hamish/Tony/Cara from the same LinkedIn pass?" then the review was incomplete.

### Speaker-attribution rule (MANDATORY)
When capturing a raw transcript, chatty meeting notes, or voice-typed conversation involving a CRM entity:
1. Run a quick **speaker-identification pass** before summarising:
   - what is clearly Tom speaking?
   - what is clearly the contact speaking?
   - what is ambiguous?
2. Separate **Tom's own anecdotes/preferences/context** from the contact's facts where reasonably possible
3. If speaker ownership is ambiguous, do **not** treat the detail as settled contact metadata in `crm.md`; instead either:
   - keep it in the raw transcript only,
   - summarise it with explicit uncertainty, or
   - ask Tom if the attribution matters commercially
4. Before updating `crm.md`, ask: "Whose fact is this — Tom's, the contact's, or uncertain?"
5. Use a **materiality threshold**:
   - if wrong attribution would materially distort the CRM/account view, stop and clarify or omit it from the CRM summary
   - if it is low-stakes colour/rapport context, it can remain in the raw transcript without being promoted as a firm contact fact
6. Only summary-worthy contact facts should enter the CRM layer; Tom-origin context can stay in the raw artifact without being framed as contact metadata
7. **Conversation-participant checkpoint (MANDATORY):** before replying to Tom or updating CRM/SharePoint from a transcript, state the attribution frame explicitly to yourself in this shape:
   - `Conversation with: <named participant(s)>`
   - `Owning CRM entity: <company/account/opportunity>`
   - `Speaker-level certainty: clear / mixed / unclear`
   Do not rely on the owning account alone to imply who was actually in the conversation.
8. If Tom later clarifies the participants (for example `this was a conversation with Doug and Kev`), treat that clarification as authoritative and repair any looser wording in the CRM summary path on the next pass.

Required mechanism before replying:
1. Ask: "Is this just summary metadata, or is this durable account/opportunity knowledge?"
2. If it is durable knowledge, immediately invoke the `crm-sharepoint` path as mandatory, not optional
3. Queue/create the dated communication artifact and update Current state (or mark it pending SharePoint confirmation if queue-based)
4. Keep the local CRM row as the summary layer only
5. If SharePoint handling has not happened yet, fail closed: say the capture is only partially done rather than implying the account is fully updated

**Fail-closed test:** if Tom could reasonably say "this isn't just a CRM update, it's SharePoint too," then CRM-only handling is insufficient and must not be presented as complete.

### Outbound work-delivery detection rule (MANDATORY)
**Trigger:** Inbox watch cron or manual session reads sent items and finds an outbound email from Tom to a CRM entity contact (anyone in Opportunities/Accounts/Partnerships tables).

**When to fire:**
- Subject or body preview contains delivery-of-work signals: "first pass", "spec", "attached", "here's the", "following today's", "draft", "requirements", "document", "proposal"
- Or: the CRM Next Step explicitly describes sending/delivering something and this sent email matches that description

**What to do:**
1. Match sent email recipient(s) against CRM Opportunities/Accounts contacts
2. Read current CRM Next Step for that entity
3. If the sent email appears to complete or advance the work described in Next Step:
   - Update CRM Next Step to "Awaiting [recipient name(s)] feedback on [what was sent]" or similar forward-looking wording
   - If a related TASKS.md item exists for the same work, mark it `Cleared (sent YYYY-MM-DD)` or `Waiting feedback`
4. Update Last Touch date
5. If the sent email included substantive work (spec, analysis, proposal, requirements), queue SharePoint communication artifact via crm-sharepoint

**Fail-closed test:** If Tom sends Doug/Kev a requirements spec and the CRM still says "Immediate next step: produce requirements spec", the rule failed.

**Pattern examples that trigger this rule:**
- "I've sent follow-ups to Kyle, Diana, and John"
- "I'm speaking to Bekah Richens"
- "I've made a start on Andy's project"
- "Had a call with [known contact]"
- Any WhatsApp screenshot showing conversation with a CRM contact

**DO NOT:**
- Wait for Tom to say "update the CRM"
- Ask "shall I log this?"
- Reply first, update later
- Treat CRM maintenance as optional follow-up work

**Test before replying:** Can I list every entity that needs a CRM update from Tom's message? If no, stop and identify them first.

## Source of Truth
- **CSV files** (`~/prospects/YYYYMMDD/prospects_YYYYMMDD.csv`) — canonical source for new leads. Always use these.
- **Discord #prospects** — backup view only. Never import from Discord if a CSV exists for the same date. Check manually if asked.
- **sent-emails.md** — canonical source for who has been contacted. Always cross-reference before generating any BCC list.

## Files
```
~/.openclaw/workspace/stackstone/crm.md            # CRM summary — campaigns, opportunities, leads, blocked domains
~/.openclaw/workspace/stackstone/opportunities/    # Rich notes for later-stage opportunities
~/.openclaw/workspace/stackstone/accounts/         # Rich notes for active clients/accounts
~/.openclaw/workspace/reference/CRM-NEXT-ACTION-SYSTEM.md  # action-control model for Next Step / next-action-date / owner / state
~/prospector/pending_bounces.txt                   # Queue file — cron processes every 30min
~/prospector/pending_unsubs.txt                    # Queue file — cron processes every 30min
~/prospects/YYYYMMDD/                              # Dated prospector output folders with CSVs
~/prospects/data/store.json                        # Discovery store (read-only for L1)
```

## Next-action control model (MANDATORY)
Read `reference/CRM-NEXT-ACTION-SYSTEM.md` whenever you are updating a live Opportunity / Account / strategically live Partnership row.

Required rule:
- treat CRM as a control system, not just a notes table
- after any meaningful movement, maintain not just `Last Touch` but also the control concepts:
  - `Next Action Date`
  - `Next Best Action`
  - `Owner`
  - `Action State`
- until `stackstone/crm.md` has separate columns for all of these, encode them consistently inside the `Next Step` field using the compact control pattern from the reference file

Minimum acceptable `Next Step` shape for live rows:
`Next action date: YYYY-MM-DD | Owner: <Tom/L1/Waiting external> | State: <due/scheduled/waiting/done/blocked/watch> | Next best action: <clear action>`

Narrative detail can follow after that control line, but not replace it.

## Pipeline discipline
- `crm.md` is the summary layer
- Rich notes belong in SharePoint and should be managed via the `crm-sharepoint` skill

## Watch mode vs reconciliation mode (MANDATORY)
Before doing CRM maintenance triggered by inbox/sent/WhatsApp movement, classify the pass as one of:

### Watch mode
- routine recent activity handling
- goal: keep `stackstone/crm.md` fresh enough as the summary layer
- acceptable when the task is just to capture a clearly visible new touch/update

### Reconciliation mode
- Tom asks to verify thoroughly, investigate whether things were missed, or reconcile system state across inbox/sent/CRM/SharePoint
- used when CRM truth could be materially wrong if mirror-only evidence is used
- required for active-entity drift checks after meaningful recent sent/inbound movement
- if the available evidence is insufficient to prove CRM truth safely, classify the state as `coverage incomplete` rather than pretending the summary is current

## Closure-state expectation (MANDATORY)
For materially important CRM-triggering activity, there must be a durable proof path for what happened next. At minimum, the outcome should be provable via one or more of:
- `stackstone/crm.md`
- SharePoint current/artifact state via `crm-sharepoint`
- `memory/monitored-items-state.json`
- `ACTIONED.md` if the item was routed/surfaced and later explicitly handled
- `reference/OPERATIONAL_ACTIVITY_LOG.md`

If the CRM-relevant movement was seen but the summary/update chain is not yet provable, classify it as `pending SharePoint confirmation`, `blocked`, or `coverage incomplete` rather than complete.

## No-silent-partial-completion rule (MANDATORY)
Do not describe CRM/SharePoint work as complete when only the local CRM row moved.
For live entities, keep the state distinction explicit between:
- CRM summary updated
- SharePoint artifact retained/queued
- SharePoint `Current.md` updated
- proof/log layer updated
If one or more of those layers remain undone or unconfirmed, say so plainly.

## Operational activity logging rule (MANDATORY)
When this skill updates CRM state from email, sent mail, WhatsApp, meetings, or Tom-provided CRM context, ensure the meaningful action is also reflected in `reference/OPERATIONAL_ACTIVITY_LOG.md` in the same pass or via the delegated `crm-sharepoint` pass.

Required mechanism:
1. If the work is CRM-summary-only, write the log entry directly.
2. If the work escalates to `crm-sharepoint`, the final pass must still leave a reviewable log entry covering the CRM + SharePoint state.
3. Use the same state vocabulary: `Confirmed`, `Queued`, `Blocked`, `Coverage incomplete`.
4. Do not leave a meaningful CRM state transition visible only in `stackstone/crm.md` without a reviewable audit-log trace.
- If temporary local fallback notes exist before SharePoint write is live, use a per-entity folder under `stackstone/opportunities/<slug>/` or `stackstone/accounts/<slug>/`, never loose files in the parent directories
- **Pending-SharePoint summary rule:** if rich context has been queued to SharePoint but not yet confirmed, update `crm.md` immediately with a clearly marked pending note/state rather than waiting for SharePoint confirmation. The CRM summary must reflect that new information exists, while making the unconfirmed SharePoint state explicit.
- **Pending-state cleanup rule:** once later cache/index verification shows the SharePoint current file really does match the intended update, remove stale "queued / not yet confirmed" wording from `crm.md` in the same maintenance pass. Pending wording is temporary state only, not something to leave sitting after confirmation.
- **Reconciliation completion rule (MANDATORY):** if a sent/inbound thread materially changed account/opportunity truth, the CRM pass is not complete until the row is either:
  - updated locally,
  - explicitly marked `pending SharePoint confirmation`,
  - explicitly marked `blocked`, or
  - explicitly marked `coverage incomplete`.
  Do not leave meaningful movement as a mere inbox fact with no CRM state transition.
- **Save-review rule (MANDATORY):** after any direct edit to `stackstone/crm.md`, immediately re-read the affected section(s) of the file before replying. Review for markdown table integrity, section-order integrity, duplicated headings/rows, orphaned rows under the wrong heading, and any render break caused by blank lines or misplaced prose. Do not treat the edit as complete until the post-save review passes.
- **Fail-closed render rule:** if the edit touched a markdown table, the post-save review must verify that the header row, separator row, and subsequent data rows still form one continuous valid table. If unsure, say the file needs another repair pass rather than claiming it is fine.
- **Stage/section alignment rule (MANDATORY):** after any CRM edit or review affecting later-stage entities, verify that the row's physical section in `stackstone/crm.md` matches its commercial stage. Rows with stage `Account`, `Client`, or `Active Engagement` must live under **Accounts**; rows with stage `Opportunity` must live under **Opportunities**. Do not rely on the `Stage` cell alone if the row is sitting in the wrong section.
- If a contact/account moves beyond simple lead stage, do not leave them as a generic campaignable lead
- Before creating a new opportunity/account entity, search for an existing matching or near-matching folder/file and reuse it if it is clearly the same entity
- For stage >= Opportunity:
  - create/update the SharePoint structure
  - maintain `<Company> - Current.md` as latest truth
  - save meetings/emails/call notes as dated artifact files
  - set stage appropriately
  - **record next step + last touch**
  - record `sharepoint_path`
  - treat `sharepoint_path` as verified only once the exact live path exists in SharePoint/index/cache
  - mark campaign eligibility as `No`
  - maintain a practical **associated people** list for the entity when multiple contacts materially relate to the same account/opportunity
  - **Next step must be concrete and actionable:** e.g. "Follow up on SLT outcome (due 10 Apr)", "Send proposal (awaiting brief)", "Second follow-up (stalled 16 days)", NOT vague statements like "awaiting reply"
- **Next-step stewardship rule (MANDATORY):** CRM is an active control system, not a dead notes table. When Tom gives new context, sends a follow-up, has a meeting, gets a reply, or when L1 reviews campaign/opportunity state, ask: "What should happen next, by whom, and roughly when?" If the answer is non-trivial, maintain that as the CRM `Next Step` rather than leaving the row to decay.
- **Next-action-date rule (MANDATORY):** every live account/opportunity row should carry a dated review/chase point, not just a general suggestion. If the entity is still commercially live, maintain a `Next Action Date` either as an actual due date or a review date, encoded in the `Next Step` field if no dedicated column exists yet.
- **Control-field completeness rule (MANDATORY):** after every meaningful CRM update, verify that the row now implies all five control concepts from `reference/CRM-NEXT-ACTION-SYSTEM.md`: `Last Touch`, `Next Action Date`, `Next Best Action`, `Owner`, and `Action State`. If any are missing, the row is not yet daily-operable.
- **No-passive-waiting rule (MANDATORY):** weak passive phrases like `awaiting reply` are not sufficient on their own for warm/live entities. Convert them into a dated state such as `Next action date: 2026-07-10 | Owner: Tom | State: waiting | Next best action: Light follow-up if no reply by then`.
- **CRM-to-task closure reconciliation rule (MANDATORY):** after any CRM+SharePoint update, meeting transcript capture, meaningful sent follow-up, or confirmed next-step change for an opportunity/account, check open task surfaces for tasks referring to the same company/contact/topic before replying. Required mechanism: search `TASKS.md` and the task-system summary/list views for the entity/contact keywords, then for each matching open task decide `still active`, `complete`, `superseded/not required`, or `needs new next action` based on CRM/SharePoint/sent proof. If the original task objective has already happened (for example "prepare for meeting" after the meeting transcript and follow-up email exist), close or mark it superseded immediately rather than leaving it active. If uncertain, leave it active but update the next action to the new live CRM next step and state what evidence is missing. This is a high-integrity operational check: do not claim CRM/account maintenance is complete while related task-board items remain stale.
- **Named-contact continuity rule (MANDATORY):** if a person/company is strategically live enough that Tom would reasonably expect them to appear in standup guidance (for example Tim Ward, John Cropper, Brendan, Stuart Hobin, warm client threads, active opportunities), the CRM row must carry enough next-step clarity that standup/planning can surface it. Missing/weak next steps on strategically live rows are a CRM maintenance failure, not just a standup omission.
- **Stall wording rule:** when a thread is warm but waiting, prefer useful steerable wording such as `Chase after board meeting`, `Nudge for decision next week`, `Follow up on draft sent 4 days ago`, or `Hold until 1 July workshop, then send validated range` over passive wording like `awaiting reply` unless truly nothing sensible should be done.
- If Tom has done paid work for them, they should move into Accounts / Client handling, not remain in opportunities/leads
- If a website enquiry becomes a real commercial conversation, it should be promoted into Opportunities and excluded from generic campaigns
- If an event/networking lead (e.g. OBCN capture) turns into a real email conversation or warm follow-up thread, it must be reviewed for promotion into Opportunities rather than left as a generic lead
- Website-generated briefing packs / report packs should also be captured in CRM, even if they have not yet become live opportunities
- Website `briefing_pack` engagement/view events are meaningful movement too: when a website activity feed shows a `briefing_pack` event that can be confidently mapped to an existing CRM entity, update the CRM summary layer for that entity rather than leaving the signal only in the website feed.
- Do not infer that a pack was formally sent just because it was viewed/opened; treat it as engagement evidence only unless a send-state source proves more.
- Prefer recent dated artifacts and Current files over stale historical notes when building context

---

## 1. New Lead Import (run every /crm-update cycle)

Source: `~/prospects/` — find latest dated folder (YYYYMMDD format)
Read CSV files inside. Columns: company name, domain, ICP score, location, contact name, title, email.

### Website pack / report capture rule
If website-generated packs/reports are identified and the company/contact is not already represented correctly in CRM:
1. Capture them in CRM
2. Mark source in Notes (e.g. `Website pack generated`, `OBCN event captured`)
3. If only light intent is shown, keep as Lead / Qualified Lead
4. If there is clear active conversation, promote appropriately

### Event/networking follow-up promotion rule
If a person/company was first captured as an event/networking lead and Tom is now actively emailing them or discussing next steps:
1. Do not leave them sitting only in the Leads table
2. Review whether they should now be an Opportunity
3. If yes, update the Opportunities summary row in `stackstone/crm.md`
4. Trigger `crm-sharepoint` handling for a proper `Current.md` + dated communication/timeline artifacts
5. Record last touch and a concrete next step

### Exact-name verification rule (MANDATORY)
When capturing or updating a person/company from an event, badge, business card, LinkedIn screenshot, OCR output, or user-shared contact image:
1. Treat the visible source artifact as the primary source of truth for spelling
2. Preserve the exact displayed spelling of the person's name and company unless Tom explicitly corrects it
3. Do not silently normalise a name from memory, phonetics, or a near-match already in CRM/tasks
4. Before writing to `TASKS.md` or `stackstone/crm.md`, verify that the exact written name matches the source artifact character-for-character as far as legibility allows
5. If the image/text is ambiguous, fail closed: say the spelling is not yet verified and ask Tom rather than committing a guess
6. If Tom corrects a spelling from a source image, immediately update the relevant task/CRM entry to the corrected exact form

Steps:
1. List `~/prospects/` folders, pick most recent by date
2. Read CSV files in that folder
3. For each company: check if domain already exists in crm.md Leads table
4. If new: add one row per contact, Campaign blank, Status → "New"
5. If exists: skip (no duplicates)

## 2. Bounce Detection

**Campaign-hygiene rule (MANDATORY):** Treat bounce/unsub handling as always-on campaign hygiene, not a later reporting task.
- If any recent campaign email has matching undeliverable, unsubscribe, or forwarded bounce evidence in inbox/sent flow, stop and reconcile it before claiming campaign hygiene is up to date.
- For any question like "have we stayed on top of bounces/unsubs since the last campaign?" use a fail-closed check: verify current bounce/unsub evidence against `stackstone/crm.md` and `stackstone/sent-emails.md` before answering.
- If exact affected addresses cannot yet be verified, say the status is **not yet verified** rather than implying it is under control.
- When Tom asks for a thorough investigation / reconciliation and live mailbox access is available, do not rely only on the polled markdown mirrors; verify against the actual mailbox system as well before producing resend eligibility or "fully verified" campaign hygiene claims.

**Live-audit closure rule (MANDATORY):**
When a live mailbox review/backfill/reconciliation is run, do not stop after fixing only the first detected class (for example just unsubs). Before you call the CRM/system updated, run the closure checklist across the full campaign-response chain:
1. bounces found and reconciled?
2. unsubscribes found and reconciled?
3. real replies found and reconciled?
4. auto-replies reviewed for whether they imply left-company / temporary-only / no action?
5. affected CRM lead rows updated?
6. campaign counts updated?
7. queue files updated (`pending_unsubs.txt` / `pending_bounces.txt`) where required?
8. if a meaningful reply is warm enough, promotion check completed?

**Fail-closed mechanism:** if any item in that checklist is still unresolved, do not say the CRM/system is fully updated. State exactly which reconciliation steps are complete and which are still pending.

Source: TWO inboxes — check both every cycle:

Three accounts to check for bounces:
- `MICROSOFT_INBOX.md` / `MICROSOFT_EXTERNAL.md` — tom@stackstoneconsulting.co.uk
- `ASSISTANT_INBOX.md` / `ASSISTANT_EXTERNAL.md` — assistant@stackstoneconsulting.co.uk
- `GMAIL_INBOX.md` / `GMAIL_EXTERNAL.md` — tomdean1988@gmail.com

**A. MICROSOFT_EXTERNAL.md** (tom@ — external/unknown senders)
Trigger: subject contains "Undeliverable" | "Delivery Status Notification" | "Mail delivery failed" | "Returned mail" | "not delivered" OR sender is postmaster@ | mailer-daemon@
Limitation: body is hidden — can only infer bounced domain from postmaster sender address, not exact email.

**B. ASSISTANT_INBOX.md / ASSISTANT_EXTERNAL.md** (assistant@ — forwarded bounces)
Tom forwards bounce emails from tom@ to assistant@ so body is readable.
Trigger: email FROM tom@stackstoneconsulting.co.uk with bounce/undeliverable content in forwarded body.
Advantage: body is fully visible — extract the EXACT bounced email address from the body.
**Always prefer this source** — it gives precise recipient addresses.

**Incremental only:** Cross-reference `memory/last-seen-emails.md` last_scan_timestamp — only process bounces newer than that timestamp.

Also check "Automatic reply" emails — body may say "left the company" / "no longer with us". These count as bounces too; add note "Left company" in CRM Notes field.

**IMPORTANT — individual email level, not company level:**
A single bounce does NOT mark the whole company as bounced.
Only update the specific contact row that bounced. Other contacts at the same company remain active.
store.json handles company-level status automatically — it only marks a company bounced when ALL verified emails have bounced.

Steps:
1. Extract the bounced recipient email from the bounce message
2. Find the matching row in crm.md Leads table for that specific email address
3. Set that contact's Status → "Bounced", fill Bounce Date. If person left company, add "Left company" to Notes.
4. Do NOT change Status for other contacts at the same company — they remain active
5. If email not in CRM (e.g. C1 contacts), still complete steps 6-8
6. Append the bounced email to `~/prospector/pending_bounces.txt` (one per line)
7. Cron runs `manage.py bulk-bounce` every 30 mins — tracks individual bounces per company in store.json; only marks company bounced if ALL verified emails bounced
8. Update Campaign table bounce count (+1 per address)
9. Post to #bounces-unsubscribes Discord (channel ID: 1486023146908946544): "Bounce: [email] — [company]"

**Periodic full register sweep:**
When Tom asks to backfill or audit bounces, query Microsoft Graph API directly (30-day window) rather than relying only on MICROSOFT_INBOX.md (which may be stale or truncated). Use `poll.load_token()` + `poll.refresh_access_token()` pattern. Requires TOTP code from Tom.

**After any bulk bounce sweep:** post a complete register to #bounces-unsubscribes so the channel is the single source of truth for all bounced addresses.

**Discord-audit verification rule (MANDATORY):** after any bounce/unsub reconciliation, campaign hygiene pass, or answer about whether bounces/unsubs are being stayed on top of, verify the Discord audit trail as well as CRM state.
- Required check order:
  1. mailbox evidence
  2. `stackstone/crm.md`
  3. `stackstone/sent-emails.md` when campaign scope matters
  4. Discord `#bounces-unsubscribes` freshness / posting evidence
- **Fail closed:** if CRM has been updated but Discord posting has not been verified, do not imply the pipeline is healthy; say the local suppression state may be updated but the Discord audit trail is unverified or broken.
- If Discord posting is stale/broken, immediately add a technical item to `BACKLOG.md` before replying and treat it as a system issue, not just a campaign-detail omission.

## 3. Unsubscribe Detection

Source: `MICROSOFT_INBOX.md` / `MICROSOFT_EXTERNAL.md` **and** `ASSISTANT_INBOX.md` / `ASSISTANT_EXTERNAL.md`

**Tom-specific operating rule (MANDATORY):** Tom may forward unsubscribe emails from `tom@stackstoneconsulting.co.uk` to `assistant@stackstoneconsulting.co.uk` so the content is easier to read/process. Treat that forwarding pattern as part of the required unsubscribe workflow, not a nice-to-have extra.

Trigger: reply contains "unsubscribe" / "remove me" / "please remove" in body or subject, or Tom forwards the unsubscribe thread into `assistant@`.

**Required evidence chain (dual-source check):**
1. First attempt to identify the unsubscribe in `tom@` (`MICROSOFT_INBOX.md` / `MICROSOFT_EXTERNAL.md`).
2. Then attempt to identify/read the forwarded copy in `assistant@` (`ASSISTANT_INBOX.md` / `ASSISTANT_EXTERNAL.md`).
3. Prefer the forwarded `assistant@` copy for exact wording/body parsing when available.
4. Reconcile the two views before claiming the unsubscribe is handled.
5. **Fail closed:** if there is evidence that an unsubscribe exists in one mailbox but it has not yet been reconciled into CRM/blocked-domain state, say it is **not yet fully reconciled** rather than implying it is done.

Steps:
1. Extract sender email (prefer the forwarded readable copy if it provides cleaner evidence)
2. Find matching row in Leads table
3. Set Status → "Unsubscribed"
4. Append email to `~/prospector/pending_unsubs.txt` (one per line)
5. **Primary suppression mechanism:** suppress the exact email address in CRM/prospector flow
6. Add domain to Blocked Domains list in crm.md **only if** the unsubscribe is clearly domain-wide/company-wide or the campaign policy for that domain should stop entirely. Do **not** blindly block a whole domain because one contact unsubscribed.
7. Update Campaign table unsubs count (+1)
8. Post to #bounces Discord: "Unsubscribe: [email] — [company]"
9. If the original `tom@` message and forwarded `assistant@` copy disagree or only one is visible, stop and mark the unsubscribe as pending reconciliation rather than guessing

## 4. Reply Detection

Source: MICROSOFT_INBOX.md
Trigger: reply to outreach that is NOT bounce or unsubscribe

Steps:
1. Find matching row in Leads table
2. Set Status → "Replied", fill Reply Date
3. Add brief summary to Notes
4. Update Campaign table replies count (+1)
5. Post to #prospects Discord: "REPLY from [company]: [summary]"
6. Alert Tom via Telegram IMMEDIATELY — warm lead
7. **Promotion check:** if the replying person/company is still only in Leads but the thread now represents a real warm conversation, review immediately for Opportunity promotion rather than leaving it sitting in Leads
8. If promoted: update the Opportunities summary row and trigger `crm-sharepoint` handling for `Current.md` + dated communication/timeline artifacts

## 4a. Opportunity/Account Communication Capture (automated)

**Trigger:** When inbox watch detects email activity (reply, new message, sent item) involving a company/contact that exists in the CRM Opportunities or Accounts table, or involving a person already associated with one of those entities.

**Process:**
1. Check if sender/recipient company exists in Opportunities or Accounts table
2. Also check whether the sender/recipient is an important associated person already tied to an existing Opportunity or Account
3. If yes to either:
   - Read both inbox context AND sent items to get the full thread context
   - Queue SharePoint write: create `YYYY-MM-DD - Communication Update - <Brief Description>.md` in the appropriate folder
   - Artifact content should include:
     - Date, sender, recipient
     - Thread context (what was said, what was committed, what's next)
     - Material changes to understanding of the opportunity/account
   - Update `<Company> - Current.md` with:
     - Last touch date
     - Brief timeline entry
     - Updated next step if it changed
     - Important associated people list if a new materially involved person has emerged
   - Update CRM table row with new Last Touch date
3. If SharePoint write fails, log the failure but still update CRM Last Touch

**Do NOT:**
- Copy full email bodies verbatim
- Create artifacts for trivial/automated emails (out-of-office, calendar invites, marketing)
- Create duplicate artifacts if multiple emails in the same thread on the same day

**This automation ensures communication is captured promptly, not days/weeks later when context is stale.**

## 5. Campaign Creation

Trigger: Tom says "create campaign" or "send to [filter]"

**Offer-framing rule (MANDATORY):**
When drafting outreach or follow-up copy that references a real client build, pilot, or implemented example:
1. Identify the actual offer first:
   - a specific existing tool/product, or
   - the capability to design/build bespoke tools around each prospect's own workflow, bottleneck, or reporting/admin burden
2. If the referenced build was made for one client, treat it as **proof / case-study evidence** by default, **not** as the product being sold to the wider batch.
3. Do not imply that all recipients are being offered that exact same tool unless Tom explicitly says that is the offer.
4. For segmented outreach like SJP campaigns, prefer wording that sells the **concept and capability** (e.g. tailored tools, bespoke workflow automation, problem-specific builds) while using the existing client example only as evidence that this can be done in practice.
5. **Implementation-accuracy rule:** describe the example build according to what it actually is now, not what it may later become. Do not call it AI-powered, AI-supported, agentic, or automated unless the current implementation genuinely includes that. If the current build is conventional software solving an AI-relevant problem, say that plainly.
6. **Fail closed:** if it is unclear whether Tom wants to sell the specific tool or the broader bespoke-build concept, ask a short clarifying question before drafting.

Steps:
1. Add new row to Campaigns table (next ID: C3, C4, etc.)
2. Tom specifies which leads to include
3. L1 generates the BCC list (see §7) and hands it to Tom
4. **Tom sends the email himself** from tom@stackstoneconsulting.co.uk — L1 does NOT send it
5. Tom confirms send → L1 updates those leads: Campaign → [ID], Status → "Sent"
6. L1 appends all sent addresses to `sent-emails.md` under the campaign heading
7. Post summary to #campaign-log Discord

**L1 never sends outreach emails. L1 only generates the BCC list. Tom sends.**

## 6. Confirm Sent (Tom confirms after sending)

Trigger: Tom says "sent" / "done" after a campaign send

**BCC recipients are NEVER visible in Microsoft sent items — Graph API does not expose them.**
L1 cannot verify who was sent to by reading the inbox. The only source of truth is:
- The BCC list L1 generated (if L1 generated it)
- Tom explicitly confirming / pasting the recipient list

Steps:
1. Use the BCC list that was generated in §7 as the confirmed recipient list
2. If Tom pastes a different/amended list, use that instead
3. Update matching leads in CRM: Status → "Sent", Campaign → [ID]
4. Append all sent addresses to `sent-emails.md` under the campaign heading
5. Update Campaign table: Recipients count

## 7. BCC List Generation

Trigger: Tom asks for a BCC list

**CRITICAL: Always cross-reference `~/.openclaw/workspace/stackstone/sent-emails.md` first.**
The CRM Status field can be stale/incomplete. sent-emails.md is the definitive record of who has been emailed.
NEVER include any email in sent-emails.md unless Tom explicitly says to re-send.

**Active campaign:** There is always one active campaign running. New leads from the prospector are added to the CURRENT active campaign pool — not held for a future one. Only advance to a new campaign when Tom explicitly closes the current one.

Filters:
- "everyone not emailed yet" → not in sent-emails.md AND Status ≠ "Bounced"/"Unsubscribed"
- "same list as C[n]" → all emails under that campaign header in sent-emails.md
- "all new leads" → not in sent-emails.md AND Status ≠ "Bounced"/"Unsubscribed"
- "ICP 7+" → ICP ≥ 7 AND not in sent-emails.md AND Status ≠ "Bounced"/"Unsubscribed"

Rules:
- Always deduplicate
- Semicolon-separated output
- NEVER include Bounced or Unsubscribed contacts
- NEVER include domains on the Blocked Domains list
- ALWAYS check sent-emails.md — CRM status is secondary
- **Full-register verification rule:** Do not generate a BCC/send list from a partial visible slice, rough manual scan, or memory. Check the full `sent-emails.md` register and the full eligible CRM lead pool before outputting any list.
- **Fail-closed rule:** If you cannot verify against the full source-of-truth files, do not output the list. Say so plainly and ask for whatever access/tooling/state is needed to run the full check.

---

## Discord webhooks (LobsterFarm server)
- #prospects — verified emails, BCC lists, reply notifications
- #pipeline — qualified companies awaiting verification
- #bounces — bounce and unsubscribe notifications
- #campaign — campaign status updates

## Sync rule
store.json tracks discovery (read-only for L1). crm.md tracks outreach+engagement (L1 writes). Queue files bridge the two — cron syncs store.json via manage.py every 30min.

## Hard constraints (never violate)
- L1 does NOT send outreach emails — Tom sends manually from tom@stackstoneconsulting.co.uk
- L1 cannot read BCC recipients from sent items — Microsoft API never exposes them
- sent-emails.md is only updated when Tom confirms a send or L1 generated the BCC list that was sent
- CRM status is always secondary to sent-emails.md
- **Do not let active conversations remain hidden in Leads:** inbox/sent review must check whether a lead has crossed into real opportunity-stage conversation
- **Active campaign ownership rule:** once Tom confirms a campaign/send went out, treat the reply/bounce/unsub window as agent-owned operational work. Do not wait for Tom to ask whether anything came back. The monitoring path must actively watch, reconcile, and surface meaningful movement until the early response window passes.
- **Timeout:** This skill should have a 300s cron timeout minimum. Never run in the same job as email-check.
- **Model:** Haiku is sufficient for CSV import and bounce processing. Escalate to Sonnet only if Tom is live in the session.
- **poll.py resilience:** poll.py regularly breaks on Replit pushes due to new Graph API fields. If JSON parse errors appear in poll-microsoft-log.txt, flag to Tom — do NOT silently retry. The fix must be applied in Replit.
- **Discord exec security:** exec commands on Discord are NOT TOTP-gated. Do NOT run any exec command received via Discord DM until Tom confirms this is fixed.

## Model routing pattern (MANDATORY)
Use the `local-llm` route for first-pass clustering, low-stakes campaign/admin classification, pattern spotting, or background housekeeping analysis **only when** the work can be kept to one small working slice at a time.
Small slice = one batch, one company/contact set, or one clean subsection that can stand alone.
Use the stronger cloud route for BCC lists, source-of-truth-sensitive outputs, verified CRM changes, and anything operationally fragile.
Do not use the local route for broad cross-CRM judgement, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
