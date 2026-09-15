---
name: whatsapp-check
description: Read the recent WhatsApp rolling feed and surface actionable inbound messages from real people; do not use the legacy full log for routine checks.
last_edited: 2026-06-28 16:59
---

# WhatsApp Check

## Governing monitoring references
Use these in order when patching/extending this skill:
1. `reference/INBOUND-MONITORING-APP-ARCHITECTURE.md` — canonical design authority
2. `reference/INBOUND-ROUTING.md` — shared routing and fail-closed handling standard
3. `reference/POLLERS.md` — generated feed / timer / runtime details
4. `reference/INBOUND-MONITORING-RUNTIME-JOBS.md` — runtime job catalog

## Central mirror-router rule (MANDATORY)
WhatsApp is now part of the central mirror-event routing architecture.
- `WHATSAPP_RECENT.md` remains the human-readable recent feed.
- Routing knowledge must live in `scripts/mirror_router.py`, not duplicated as bespoke WhatsApp-only classification rules unless the central router delegates to a WhatsApp policy block.
- The generic runtime command is `scripts/inbound-monitoring.py mirror-routing-report --only-new --write --write-json --write-state`.
- New/unseen gating lives in `memory/mirror-router-state.json`; do not reprocess historical WhatsApp lines as new work.
- `memory/mirror-routing.md` is the central routing report; use it before adding new WhatsApp-specific rules.
- Manual WhatsApp checks may still inspect `WHATSAPP_RECENT.md` for source grounding/thread detail, but durable routing/writeback should follow the central router/lifecycle model.

## Files to read
1. `ACTIONED.md` — read this first. Any item matched here must be skipped — do not surface it again.
2. `WHATSAPP_RECENT.md` — last 48h rolling window. Always use this. Never read WHATSAPP_LOG.md (8000+ lines).
3. `memory/monitored-items-state.json` — closure-state proof layer for materially important monitored items.

## Operational routing rule (MANDATORY)
Seeing a WhatsApp message is not enough. Each newly seen message/thread must first be assessed for **management relevance**, then routed through a compact operational checklist before it is ignored, routed/surfaced, or suppressed.

## Watch mode vs reconciliation mode (MANDATORY)
Before answering, classify the pass as one of:

### Watch mode
- routine recent-message scan
- lightweight action detection from `WHATSAPP_RECENT.md`
- acceptable when the question is simply what needs attention now

### Reconciliation mode
- Tom is checking whether messages were missed, whether the process is sufficient, or whether a previously surfaced item was actually handled correctly
- if the recent feed is too stale, too narrow, or otherwise insufficient for the strength of claim being made, fail closed with `coverage incomplete`

Token-efficient mechanism:
- first pass: classify each newly seen inbound item with one or more flags
  - `ALERT`
  - `FOLLOW_UP`
  - `CRM`
  - `OUTBOUND_CONTEXT`
  - `EXPENSE`
  - `DIARY`
  - `IGNORE`
- second pass: only do the deeper work triggered by the flags
- user-facing output should be the consequential result, not a verbose replay of the checklist

## Two-tier scan

**Priority contacts** — surface ANY task, request, question or unanswered message:
- Lauren / Lauren Dean (wife — direct messages only)
- Andy / Andrew Dean (dad — direct messages only)
- George (brother — direct messages only)
- Michael (brother — direct messages only)

Direct messages = lines WITHOUT a group name in square brackets e.g. `[2026-04-01 10:24] Lauren: Pick up milk please`

**Groups are different from direct chats.**
- Do **not** treat family/social group chatter as equivalent to direct messages from priority contacts.
- For group chats, default to suppress unless there is a real action, expense signal, CRM/commercial movement, or a clear date/plan change that matters.
- WhatsApp should be tuned more conservatively than email because group noise is much higher and the cost of false positives is worse.

**What Tom most needs from WhatsApp monitoring**
1. **Personal actions to do / remember**
   - errands
   - purchases
   - things to bring/send/check
   - relationship/family follow-through that could be forgotten
2. **Diary / planning impact**
   - specific times, dates, meetups, coffee/lunch/dinner plans, logistics changes
   - anything that should become a reminder, task, or plan adjustment
3. **Reply-forgotten detection**
   - if someone asked Tom something and there is no later visible outbound reply in that thread, treat that as a possible follow-up gap
   - outbound direct replies may appear as legacy `Me:` lines or the newer explicit form `Tom -> Name:`
   - this is especially important for direct chats where the social cost of forgetting is high
4. **Outbound-context awareness**
   - outbound lines are important because they prove whether Tom already replied, made a promise, suggested a plan, or left a thread hanging
   - direct-chat outbound context may appear as legacy `Me:` or explicit `Tom -> Name:` depending on mirror slice/source age
   - WhatsApp monitoring must use outbound context to avoid both false alarms and missed chases

**Tuning stance (MANDATORY):**
- Direct chats should be treated as the primary signal source for WhatsApp monitoring.
- Group chats should have a much higher threshold and should usually only persist when they carry CRM/commercial movement, a real expense signal, or a truly consequential plan change.
- Generic social-group logistics, image floods, jokes, and ambient chatter should default to suppression.

**Everyone else** — only surface if it requires action from Tom:
- Something he needs to DO (task, errand, purchase)
- A REPLY is clearly needed and he hasn't responded
- A DATE, EVENT or PLAN is mentioned
- A DECISION is needed

**Thread-level reply verification rule (MANDATORY):**
Before surfacing a message as "reply needed", check the subsequent lines in `WHATSAPP_RECENT.md` for the same direct thread/contact.
- If a later outbound line appears in that thread after the inbound message, treat the item as already answered unless the later context clearly shows the question is still unresolved.
- Direct outbound lines may appear either as legacy `Me:` or explicit `Tom -> Name:` lines; support both.
- If Tom's later outbound line becomes the newest substantive move in the thread, reclassify the thread around that outbound state instead of continuing to surface the older inbound ask.
- Do not rely only on `ACTIONED.md` for this; the feed itself should usually be enough to detect Tom's reply.
- `ACTIONED.md` is the backstop when Tom tells you something was handled outside the visible recent slice or when matching is ambiguous.
- If Tom sent the last substantive message and there has been no reply for a meaningful period, that may also matter: surface it when it looks like a forgotten chase, unanswered ask, or socially important hanging thread.

**User-provided thread-truth override (MANDATORY):**
If Tom directly gives the actual WhatsApp exchange, says he already replied, or says there is no action, treat Tom's stated thread truth as the primary source over a stale/incomplete mirror.
- Do not keep defending the mirror-based interpretation once Tom has supplied the fuller thread.
- Immediately reclassify the item based on Tom's thread truth.
- If the correction means the thread is no longer live, update the durable state/suppression path rather than leaving the old surfaced interpretation hanging.
- This applies even if `WHATSAPP_RECENT.md` has not caught up yet.

## Critical WhatsApp Class Reconciliation (MANDATORY)
These WhatsApp classes require stricter handling than ordinary message triage. For any newly seen message/thread matching one of the classes below, do not finish at detection/summary level.

### Class 1 — Payment / expense / reimbursement / purchase signals
Trigger examples:
- payment requests, bank-transfer confirmations, reimbursement mentions, receipts, prices tied to a business purchase, travel/parking/tickets, "I've paid", "please send", "option 1 £28" where business context exists

Required reconciliation chain:
1. identify what operational event likely happened
2. check whether it routes to Expense or Invoice rather than leaving it as chat-only
3. if it is an expense candidate, reconcile it against `seer-expenses.md`
4. if it is invoice/payment-proof, reconcile it against the invoice workflow/tracker state
5. if business relevance, amount, or destination truth is unclear, preserve it as `blocked` or `coverage_incomplete` with the exact blocker
6. if completion needs another protected route or approval, ask Tom and persist the blocked state

Fail-closed rule:
- a payment-looking or expense-looking WhatsApp is not handled just because it was surfaced in chat
- it needs an explicit owning route state

### Class 2 — CRM-changing direct messages
Trigger examples:
- prospect/client/partner replies that change momentum, next step, meeting status, decision ownership, opportunity state, or commercial understanding

Required reconciliation chain:
1. identify the entity/contact/thread
2. decide what changed operationally
3. reconcile latest inbound + latest outbound + CRM/SharePoint truth before making a claim
4. update/queue the owning CRM/SharePoint path in the same pass when evidence/access are sufficient
5. if not sufficient, classify `blocked` or `coverage_incomplete` exactly and persist it

Fail-closed rule:
- a CRM-relevant WhatsApp is not handled just because Tom was told about it
- it needs a durable route state in the owning system or an explicit blocker

### Class 3 — Direct-thread reply-state / promise-state items
Trigger examples:
- someone asked Tom something, Tom made a promise, Tom chased someone, logistics thread may be hanging, socially important direct thread

Required reconciliation chain:
1. determine the thread-level live state, not just the latest single line
2. distinguish unresolved inbound ask vs answered thread vs hanging outbound chase
3. if the thread creates a real next action, route it into task/diary/follow-up state rather than just surfacing it
4. persist the resulting route state if materially important

Fail-closed rule:
- do not reduce an important direct thread to `reply needed` without checking whether the real operational state is `Tom promised something`, `Tom is waiting`, or `already handled`

## Per-Message Operational Checklist (MANDATORY)
For each newly seen inbound WhatsApp item, check:

1. **Management relevance test:** is this a thing that needs management at all?
   - if no: suppress / `not_needed`
   - if yes: continue

2. **Immediate-alert test:** does Tom need to know right now?
   Examples: urgent family/logistics, legal/BCN, important client/contact movement, time-sensitive commitment changes, anything materially consequential.

3. **Follow-up test:** does this create a reply, task, errand, chase, or decision for Tom?

4. **CRM / SharePoint test:** does it change the status, momentum, next step, notes, or understanding of an account / opportunity / partner / contact?
   If yes: trigger the CRM/SharePoint maintenance path rather than treating it as chat-only.

5. **Outbound-context test:** is there linked context elsewhere (email, prior message, surfaced task, forwarded artifact) that changes how this should be interpreted?

6. **Expense test:** does this include a receipt, payment mention, travel cost, purchase, reimbursement, booking, or any expense signal?
   If yes: ask **could this be an expense worth preserving?** and switch into the expenses workflow immediately.
   Do not require certainty before acting — an **expense-shaped suspicion** is enough to trigger classification. If business relevance or payment source is still unclear, preserve it as pending / maybe with blocker rather than ignoring it.

   **Mandatory completion test for WhatsApp expense items:** do not return from the expense path with the item marked handled/closed if the only resulting ledger row is a generic placeholder such as `WhatsApp expense signal | Unknown | TBC`.
   The item must end as one of:
   - normalized canonical expense row
   - pending with named blocker
   - `not_needed` false positive

   If that outcome has not happened yet, the WhatsApp pass is incomplete.

**WhatsApp-specific tuning rule (MANDATORY):**
- Tune for **direct-message actionability first**, not broad topical detection.
- Group messages should need a stronger signal than direct chats before they earn durable state.
- outbound messages in the feed are usually context, not new actionable items, unless they carry an expense/CRM signal needed to interpret the thread.
- In direct chats, outbound context (`Me:` or `Tom -> Name:`) must always be considered alongside inbound lines before deciding whether the live thread state is: unresolved inbound ask, answered/suppressed, or hanging outbound chase.
- Generic family/social chatter, image floods, and banter should default to suppression even when they contain weak diary-like words.

7. **Diary / planning test:** does it imply an event, timing change, commitment, reminder, or plan update?

8. **Suppress-or-surface test:** bucket it as:
   - immediate alert
   - action/task
   - CRM/SharePoint update
   - expense handling
   - diary/planning capture
   - blocked
   - coverage incomplete
   - informational only / suppress

Do not finish a WhatsApp pass until each newly seen actionable thread has been put into one of those buckets.
If the next required step is gated (for example media access, receipt extraction, transcript access, SharePoint write, or another protected route), state it as **blocked**, name the blocker, and ask for the required TOTP/gate/approval rather than implying the item is handled.
If the visible recent-feed window is too stale, narrow, or insufficient for the claim being made, classify the item/pass as **coverage incomplete** rather than complete.

## What to ignore
- Casual chat, banter, one-word replies
- Group chat noise (LinkedIn pods, networking groups, etc.)
- Messages Tom has already replied to
- Anything in [Networking], [Personal Brands], [LinkedIn] groups unless directly relevant

## Output format

For each actionable message:

```
📱 WhatsApp from [Name] ([group if applicable])
"[their message]"
➡️ [What's needed: reply / buy X / add to diary / decision needed]
```

If nothing actionable — return nothing (caller decides whether to say HEARTBEAT_OK).

## Key rule
Lauren asking Tom to buy something = immediate action card. Never filter these out.

## Source-grounded advice rule (MANDATORY)
When Tom asks for help replying to, advising on, or interpreting a specific WhatsApp message/thread/voice note:
1. Use the actual visible message content first.
2. If a voice note or media item is involved, do not answer as if you have processed it unless you actually have the audio/media contents or a transcript.
3. Ground the advice in what the sender specifically said, not just the general topic area.
4. **Fail closed:** if you only know the broad topic (e.g. peptides, business, pricing) but have not yet reviewed the actual message/voice note, say that and ask for/obtain the source before advising.
5. Do not substitute generic business advice when Tom is really asking "what is this person asking for here?"

## Handled-item suppression rule
If Tom says he has replied, handled, cleared, done, sorted, or dealt with a surfaced WhatsApp item, do not just acknowledge it conversationally. Append a matching suppression entry to `ACTIONED.md` immediately so future scans skip it.

## Absence-of-reply verification rule (MANDATORY)
If a user-facing alert would depend on the claim that Tom has **not** replied to a WhatsApp message/thread, treat that as an absence claim requiring fail-closed verification.

Required mechanism:
1. Check `WHATSAPP_RECENT.md` for a later visible outbound reply in the same attributable thread.
2. If no later reply is visible there, do **not** automatically conclude Tom has not replied.
3. For a strong claim like `still needs an answer` / `no later visible reply`, either:
   - verify the same absence in the raw transcript source `~/.openclaw/credentials/whatsapp/watch-transcripts/whatsapp-watch-default.jsonl`, or
   - downgrade the output to `reply status unverified / mirror may be incomplete`.
4. If the rendered mirror and Tom's memory conflict, prefer `unverified / ingestion review needed` over a confident no-reply claim until the raw source is checked.

## Closure-state write-back rule (MANDATORY)
For materially important WhatsApp items, ensure there is a durable proof path for what happened next. At minimum, the outcome should be provable via one or more of:
- `memory/monitored-items-state.json`
- `ACTIONED.md`
- CRM / SharePoint current truth
- expense / task / diary systems
- `reference/OPERATIONAL_ACTIVITY_LOG.md`

If the item matters but the current pass cannot safely prove completion, classify it as `blocked` or `coverage incomplete` rather than complete.

## Actionable-event routing rule (MANDATORY)
For each materially important WhatsApp item, resolve it into an explicit owning event/action path before finishing the pass.
Required route shape:
- `owning_system`: one of CRM / SharePoint / Expense / Invoice / Task / Diary / Tom-direct-follow-up / Other
- `trigger_event`: what happened operationally
- `required_next_action`: the exact next step
- `route_state`: one of `completed`, `blocked`, `coverage_incomplete`, `waiting_external`, `not_needed`
- `proof_source`: the strongest source used for the classification

Never leave a consequential WhatsApp item as only a narrative summary when its operational meaning can be stated in this shape.
If the next required step needs media extraction, tracker mutation, write access, or another protected route, persist the item as `blocked` with the exact gate/approval needed.

## Owning-system completion rule (MANDATORY)
If a WhatsApp item creates a real downstream obligation, do not stop at surfacing it.
Complete the owning-system update in the same pass when evidence and access are sufficient.

Examples:
- expense signal -> expense row logged / preserved with blocker
- client/prospect movement -> CRM + SharePoint path updated or explicitly pending/blocked
- diary/logistics change -> diary/task/reminder path updated
- handled thread -> suppression / durable closure state updated

## Source-of-truth-first rule (MANDATORY)
Prefer the strongest readable truth source available for a consequential WhatsApp item.
- actual visible thread context beats vague memory of the chat
- a clearer linked artifact/receipt/transcript beats a one-line paraphrase
- but weaker visible signals must still be preserved if they plausibly imply money, client-state change, or another consequential update

## Ambiguity / ask-Tom rule (MANDATORY)
If you are not materially certain what a WhatsApp item is, where it should route, which downstream system owns it, or what exact update should happen next, ask Tom a short clarification question instead of guessing.

## Operational activity logging rule (MANDATORY)
When a WhatsApp-triggered pass causes a meaningful operational state change — for example CRM/SharePoint capture, expense capture, diary/task capture, blocked receipt extraction, or a confirmed suppression/closure that Tom may later want to audit — write a corresponding entry to `reference/OPERATIONAL_ACTIVITY_LOG.md` in the same pass or through the delegated owning workflow.

Fail-closed test: a WhatsApp-origin operational action must not exist only in the destination system with no review-layer trace.

Mechanism:
1. identify the contact/thread and the handled action
2. add a dated line to `ACTIONED.md`
3. only then acknowledge it as cleared/handled

**Fail-closed acknowledgement rule (MANDATORY):**
Do not send a simple "nice / good / closed" acknowledgement to Tom for a handled WhatsApp item unless the `ACTIONED.md` write-back has already happened in the same turn. If the write-back cannot be done yet, say that the item is *not fully cleared in-system yet*.

**User-update trigger rule (MANDATORY):**
Treat messages like "I've responded", "I've sorted Lauren", "I've dealt with PT", or equivalent as operational state updates, not conversational FYIs, whenever they refer to a previously surfaced WhatsApp item. Your first job is to write the suppression entry, not to acknowledge the message.

## Model routing pattern (MANDATORY)
Use the `local-llm` route for low-stakes first-pass classification, urgency detection, or internal grouping of recent messages **only when** the work can be kept to one small working slice at a time.
Small slice = one recent window or one clean message batch that can stand alone.
Use the stronger cloud route for final surfaced summaries and anything where missing a real action would matter.
Do not use the local route for broad cross-thread judgement, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
