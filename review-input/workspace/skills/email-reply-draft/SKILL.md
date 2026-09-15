---
name: email-reply-draft
description: Prepare unsent, context-correct Outlook reply drafts using thread cadence, CRM truth, and commercial context; never send automatically.
---

# Email Reply Draft

## Purpose
Produce the right **unsent** reply draft, not merely plausible email prose.

Use alongside:
- `email-check` for detection/trust classification
- `email-send` for sender/signature/send rules if Tom later approves sending
- `crm-update` where a client/prospect/partner thread changes commercial truth
- `task-decompose` / `task-operate` for context-heavy reply preparation

Canonical system design: `reference/EMAIL-REPLY-DRAFT-SYSTEM.md`.

## Contact-alias and historical-message resolution (MANDATORY)
Before declaring a draft blocked because a named contact/message is absent from a short rolling feed or appears under a different surname, perform a bounded identity-and-source resolution pass: (1) search the current rolling mirror; (2) search the relevant retained conversation archive for the named contact and plausible aliases; (3) cross-check the resulting person against `contacts.md`, the owning CRM/account/opportunity record, and current account context; and (4) when evidence proves an alias, record the canonical-name/alias/email relationship in the contact and account truth before binding the task. A rolling-window miss is **not** proof that no usable message exists. Do not create or send a draft until one exact conversation source and one verified recipient identity resolve to the same person; once they do, proceed through the task-system draft route rather than asking Tom to repeat the context.

## No-friction drafting invariant (MANDATORY)
Tom expects regular email drafting to be easy. For every email-draft request, use the task-system/context-broker route to retrieve bounded message and relationship context and create an **unsent** Outlook draft. Neither step requires TOTP, `exec`, or a live full-mailbox read. TOTP is reserved for protected actions outside this flow—principally external sending, exceptional user-approved recovery, or protected configuration—not normal draft preparation. If task intake/binding is incomplete, repair the bounded task/entity/source binding in the task system; do not ask Tom for a code or make drafting contingent on it. Only a concrete broker `context_denied`/`coverage_incomplete` result may block the draft, and the task must retain that exact blocker for repair/retry.

## Process-first drafting rule (MANDATORY)
Any request from Tom to draft an email—whether he supplies wording, asks for a new email, or only wants a quick check-in—activates this skill **before** any chat copy or Outlook draft is produced. First select and record the route, assemble the required evidence, create the composition brief, and pass the pre-save editorial verification. For a live CRM client/prospect/partner, this means the context-heavy task-system route; it is never acceptable to draft first and retrofit the process afterwards. If the evidence or gate is missing, return `blocked` with the exact missing step rather than a plausible preliminary draft.

### Cross-skill hard stop (MANDATORY)
When a request is both CRM-relevant and an email-draft request, CRM/SharePoint maintenance does not satisfy the drafting obligation and must not be used as a reason to produce chat copy first. Invoke this skill's task-system route before presenting any client-facing wording. CRM/SharePoint capture may run in parallel, but the draft remains blocked until the task-system packet is `context_ready`; completion requires an unsent Outlook Draft ID/link and post-create verification unless Tom explicitly asks for text-only.

## Context-heavy client reply route (MANDATORY)
For a consequential client/prospect/partner reply whose quality depends on project history, commercial position, scope, prior commitments, or relationship cadence, use `task_system_context`; do not draft from the email thread and CRM summary alone.

### Commercial roadmap-context rule (MANDATORY)
For any CRM-relevant commercial draft or revision that mentions a phase, next stage, scope, opportunity, or proposed work, load the canonical source report or options/roadmap document before composing. The task packet must include that report as a required, fresh, full dated artifact alongside the current account record. Extract the explicit phase/work-item map and compare every proposed next-step claim against it. If the report is absent, stale, partial, or conflicts with Tom's latest direct update, mark the route `coverage_incomplete` or stop for reconciliation; do not replace the roadmap with generic “next refinements” language.

This check is separate from email-thread evidence: standalone messages do not need a historical email thread, but commercial phase claims still require the governing roadmap context.

### Existing-work preservation and artifact-reconciliation rule (MANDATORY)
For active CRM/account replies, do not treat the email thread as the whole context when the recipient asks about a deliverable, workbook, matrix, report, vendor evaluation, cost, scope, or decision already being prepared. Before composition, reconcile the ask against the registered SharePoint/CRM preparation sources.

The composition brief must explicitly classify each material point as one of:
- **already completed / already considered** — state where it is evidenced (for example, a named workbook tab or dated artifact);
- **open question** — do not imply it has been solved;
- **new work required** — name the owner and next step; or
- **unverified** — block or qualify rather than inventing.

Never convert evidence of completed preparation into future-tense filler such as “I’ll make sure we cover…”. If the source proves the work is already present, the draft must say so and point the recipient to the relevant comparison, tab, report, or attachment context. If the relevant preparation artifact is not registered or cannot be read, mark the draft `coverage_incomplete` and repair/register the bounded source; do not draft generic prose around the gap.

**Mechanism:** detect project-term cues in the full inbound/thread (`cost`, `price`, `matrix`, `scorecard`, `vendor`, `workbook`, `xlsx`, `requirements`, `scope`, `comparison`, `options`), require the `email_draft_v1` packet to include a fresh current record plus the matching registered dated artifact, then run a claim-to-source check immediately before saving. The draft fails editorial verification if it says Tom will do work that the artifact shows has already been done.

### Tom's task-system route preference (MANDATORY)
Tom's standing preference is that **every email draft, revision, or Outlook-draft save uses the task-system/context-broker route first**. Do not treat the direct trusted-reader + `draft.py` route as an acceptable fallback merely because it worked previously or because a Microsoft approval window is open.

Mechanism:
1. Create or load the task-system email-draft task.
2. Create the bounded context-loading subtask and load the registered entity/thread/profile packet.
3. Require the packet to contain the exact latest outbound, latest inbound or explicit absence, recipient identity, current CRM/SharePoint truth, cadence, and evidence gaps before composing.
4. If the required broker profile or source binding is missing/disabled, mark the task blocked and create the next task-system action to register/enable that bounded profile. Do not draft, update, or save an Outlook item through a direct route.
5. Only after `context_ready` may the draft subtask proceed to `draft.py`; preserve the explicit draft-only/no-send boundary and verify the resulting draft.

This rule is high-integrity and applies even when the requested change is a small wording revision to an existing draft. A prior successful direct route is evidence that the email operation works, not permission to bypass the governing task-system route.

### Email-reply admission boundary (MANDATORY)
An explicit user request to reply is sufficient to admit the work when it supplies a recipient and either an exact stored message/conversation reference or a trusted mirror item that can be deterministically bound to one. Do **not** reject or pause the request merely because `entity_id`, `entity_or_project`, CRM enrichment, or SharePoint current truth is not yet available. Derive a minimal contact/thread binding from the exact email source where the runtime supports it, and record richer commercial context as missing or pending review. These fields are context-quality inputs, not prerequisites for attempting the bounded exact-thread load.

Hard-block only when the exact thread cannot be deterministically bound/read, the recipient identity conflicts with the source, material context is unavailable for an honest draft, or the draft-only/no-send invariant cannot be enforced. The task-system route must return the real source/coverage blocker rather than an intake-schema blocker. Missing optional entity context must never be used to turn a direct “reply to this email” request into a user clarification question.

Mechanism: on `work_type=email_reply_draft`, validate recipient + exact source binding first; if present, derive or attach a minimal email-thread entity and continue to the bounded broker load. Treat absent entity enrichment as `context_incomplete` guidance unless the selected profile explicitly requires it for a material claim. The regression test must prove an exact-thread email brief without `entity_id` passes intake and then fails, if at all, only at the exact-thread/context-read boundary.

### Explicit-Tom flexibility override (MANDATORY)
When Tom directly instructs “draft/reply to this email” and supplies or identifies an exact message/thread plus the intended outcome, do not let a missing task-system entity, empty post-reset broker registry, or unregistered attachment turn that request into a clarification loop. Treat those as **backfill obligations**, not drafting blockers.

Mechanism: first load the exact message and only the named supporting artifact through the strongest authorised bounded source; verify recipient/thread/attachment identity; create and verify the unsent Outlook reply draft; then create or repair the task-system/CRM evidence record from the proven IDs and source references. This override never permits invented claims, mailbox-wide search, attachment substitution, or sending. It applies only to an explicit Tom instruction with deterministic exact message and artifact scope. If the exact source or named artifact cannot be read, report that concrete gap; otherwise continue.

Create an ordered task-system chain:
1. **Full-read and thread reconciliation** — obtain the complete current inbound, identify the actual ask, and prove whether a later Tom reply already exists.
2. **Rich entity-context load** — read the relevant SharePoint `Current.md` and dated account/opportunity artifacts; reconcile them with the CRM control row and recent sent/inbound thread. Attach: account state, agreed scope, commitments, active commercial question, relationship/cadence notes, and every evidence gap.
3. **Draft brief** — state the reply objective, recipient set, tone/cadence, claims that are supported, claims/figures that are not supported, and the one next move the reply should create.
4. **Draft-only preparation** — only when subtasks 1–3 are complete may the unsent-draft subtask become `execute_ready`.
5. **Tom review** — compare/review the draft before any external send; update CRM/SharePoint after the resulting external outcome, not merely because a draft exists.

If SharePoint/current truth is unavailable, stale, conflicting, or gated, record the exact blocker and request the required gate. Do not draft around the gap with generic prose.

### WhatsApp-originated standalone-email admission (MANDATORY)
When Tom asks for an email that follows up a WhatsApp message, treat it as a **standalone new-message** draft—not an email-reply task. Create the task-system draft task with the named contact and company as its bounded entity scope, then load the registered WhatsApp mirror and current entity sources through the task-context broker. Do not request TOTP for message/context retrieval, and do not substitute an `exec`/filesystem search for the broker route. If intake parsing drops an explicit entity scope, repair the task's entity/source binding through the task system and continue; report a blocker only when the broker itself returns a concrete bounded-coverage gap. Create and verify the unsent Outlook draft once the packet is context-ready; never send.

### Broker-first context rule (MANDATORY)
When a task has an exact entity binding and an approved read-only task-context-broker profile/source registry, retrieve the bounded context packet through that broker **before** requesting a Microsoft/exec TOTP. A normal broker packet retrieval is not an external action and must not be routed through the protected full-mailbox-read path.

- Use the broker packet for its authorised, entity-bound sources only; treat `context_incomplete`, `coverage_incomplete`, or `context_denied` as a drafting blocker rather than widening into mailbox/SharePoint search.
- Request TOTP only when the task genuinely needs an unregistered/full source that the broker cannot supply, or when performing separately protected configuration/permission/credential work. Do not request it merely because the reply is consequential or because an Outlook draft will later be saved.
- The trigger is any context-heavy draft task with a stored exact entity binding plus a broker profile/link. The check is: request the static packet, inspect its manifest for exact binding, freshness/coverage and conflicts, then either draft from `context_ready` or surface the broker result as the exact blocker.
- A broker that is not yet activated or lacks its required entity/source registry is an implementation gap, not a reason to reclassify the user request as a generic TOTP-gated email workflow. Record that gap and continue any safe broker activation/preparation work through the task-system/app-patch route.

**Model-routing boundary:** the local LLM path is not authorised to write or decide client-facing email copy. It may not be used as the drafting actor for this route; use the task system to assemble a bounded source packet for a capable reviewed drafting pass. This preserves the source package and independent review without treating a low-stakes/local first pass as external-copy authority.

## Monitor-triggered draft obligation (MANDATORY)
When a monitored Outlook pass finds a **fresh human inbound** from a live CRM client, opportunity, partner, named priority contact, or otherwise reply-worthy correspondent, do not stop at an alert if the message reasonably calls for a reply. This applies to trusted and non-safe-list/external senders alike.

**Safe-sender boundary:** safe-list/TOTP status controls protected mailbox reads, sender promotion, configuration, and sending. It must not suppress admission to unsent draft preparation. A non-safe-list message must enter the bounded draft-only route; if exact body/thread evidence cannot be read, retain a durable, retryable `coverage_incomplete` blocker and keep loading/repairing the bounded context path. Never silently classify it as `no_reply_needed`. Low-risk draft-only status removes the send risk; it does not remove the context-quality requirement.

For each candidate:
1. Match the inbound `Conversation ID` against later sent items in the same feed (and any stronger sent-thread source available).
2. If Tom has already replied later, suppress drafting and record/communicate only the reconciled state.
3. If no later reply exists, invoke this draft workflow in the same pass:
   - admit trusted and non-safe-list/external candidates to the unsent draft route; or
   - if material content is truncated/body-withheld, mark the task `coverage_incomplete` with the exact missing detail, retain it for retry, and surface the blocker. Continue bounded context retrieval/repair; do not compose generic prose around the gap. Do not ask for TOTP merely because the draft is unsent or the sender is not safe-listed.
4. Never downgrade this into a bare `reply needed` alert merely because the message also changes CRM truth. CRM capture and draft preparation are parallel obligations.
5. **Context-first drafting:** create the draft only after the task-system packet contains exact thread evidence and the relevant CRM/SharePoint context. Low-risk draft-only status changes the approval boundary for writing the draft; it does not authorise a context-free acknowledgement.

This trigger applies only to reply-worthy human correspondence, not newsletters, automated notices, calendar mechanics, or low-signal acknowledgements.

### Substantive negative-response rule (MANDATORY)
Do not suppress draft preparation solely because an inbound message contains a rejection, decline, pause, “not for us”, or says that a proposed route will not work. For a live CRM contact, client, opportunity, partner, or named priority contact, treat a substantive negative response as a **draft candidate** when a concise acknowledgement, relationship-preserving close, clarification, or future-door-open reply would be commercially or relationally sensible.

The monitor must:
1. create/load the task-system draft task;
2. load the exact inbound and current relationship context;
3. either prepare an unsent draft for Tom's review, or record an explicit evidence-backed reason why no reply is appropriate;
4. never turn “no direct question” or “no reply clearly required” into an unexamined suppression decision.

A short acknowledgement is still a client-facing draft and must use the mandatory task-system/context-broker route. If the full message or context is unavailable, mark the candidate `coverage_incomplete`/blocked rather than silently suppressing it.

## Workflow

### 1. Identify the reply route
For `tom@` inbound email, establish:
- trusted inbox path or external/body-withheld path
- an explicit task-system decision: `reply_needed`, `no_reply_needed`, or `blocked_to_decide`
- the evidence-backed reason for that decision
- whether a reply is actually required
- whether Tom has already replied later in the same thread

The task-system decision is the admission boundary. Do not create a reply-prep task or Outlook draft for `no_reply_needed`. For `blocked_to_decide`, create durable blocked work with the exact missing evidence. If the decision is absent or ambiguous, fail closed to `blocked_to_decide`; do not silently suppress the item.

Routes:
- `direct_trusted` — readable trusted email and simple enough to draft directly
- `task_system_context` — external/non-safe-list email that looks reply-worthy; admit it to the draft-only context route without TOTP. If the bounded reader cannot return the exact thread, preserve a durable `coverage_incomplete` blocker and retry/escalate visibly.
- `gated_full_read` — only for a genuinely protected full-mailbox read that is separately required; never use it as a reason to suppress unsent draft preparation.
- `task_system_context` — nuanced thread needing structured context assembly before drafting

Do not draft from external/body-withheld preview as though it were the complete email.

### 2. Assemble context
Before writing, load only the sources that matter:
1. latest readable email/thread and latest sent message
2. thread cadence: recent back-and-forth vs formal/reset interaction
3. CRM/partnership/account current truth for live commercial relationships
4. known tacit context needed for the actual decision

Determine:
- the immediate ask
- the real objective of Tom's reply
- whether pleasantries are appropriate or already exhausted
- whether reply should be brief, substantive, scheduling-focused, decision-focused, or a holding response

### 3. Use the task system when appropriate
Use a task-system reply-prep subtask when multiple sources or a meaningful commercial judgment are required.

The packet must state:
- mailbox, sender, message ID and conversation/thread ID
- trust/readability status and exact full-read blocker if applicable
- latest inbound ask, latest outbound context, and reply-already-sent reconciliation result
- thread cadence/tone mode, including whether pleasantries should be minimal, normal, or reset
- relevant CRM/current-truth/tacit notes and any evidence gap
- reply objective and reply mode (direct answer, scheduling, commercial next step, holding response)
- explicit draft-only/no-send boundary and Tom-review checkpoint
- success definition: an unsent, context-correct draft for Tom review, with Outlook Draft ID/link where saved

Do not create task-system work for simple trusted replies merely to add process.

### 4. Compose the email from an explicit brief
Before writing prose, make a compact composition brief (internally or in the task packet):
- **Recipient and relationship:** who they are, role, and the appropriate degree of warmth/formality
- **Their actual ask:** the question, decision, or action requiring a response
- **Tom’s intended outcome:** what this reply should achieve now—not merely what it should say
- **Position and evidence:** facts/commitments that can be stated confidently; facts that must be qualified; facts that are missing and therefore cannot be claimed
- **Practical next move:** owner, action, timing, and any choice Tom is asking the recipient to make
- **Constraints:** promises not to make, sensitive points, commercial boundaries, and whether a brief holding reply is safer

### Final copy QA (MANDATORY)
Before saving any draft, run a literal copy check against the source thread, task brief, calendar, and governed signature:
- **Apologies:** do not apologise for delay/non-response unless Tom explicitly wants that or the thread proves Tom owes an apology.
- **Names:** copy every participant name exactly from the authoritative source; never infer spelling (for example, do not change `Deon` to `Dion`).
- **Signature:** the body must not repeat Tom's name if the governed signature already supplies it. End with the closing only (for example, `Best,`) and let the signature provide the identity. The final task-system writer is the enforcement boundary: it must deterministically strip a trailing conventional closing-plus-`Tom`/`Tom Dean` before appending the governed signature, and reject/update drafts only through its exact task-owned no-send route. Upstream composition prompts are not sufficient protection.
- **Availability:** use calendar-backed dates, but offer the broadest useful window first. Use all-day/day-level availability when that gives the recipient more choice; specify a time only when Tom requested it, a real constraint requires it, or a narrower slot materially improves scheduling.
- **Claims and tone:** remove invented causes, unnecessary self-justification, or extra pleasantries that are not supported by the thread cadence.

The draft must fail editorial verification if any of these checks is unresolved; revise the copy before saving rather than relying on Tom to catch avoidable surface errors.

### Recipient-side opportunity framing check (MANDATORY for commercial follow-ups)
Before proposing, reviewing, or refining a commercial follow-up, create a brief **recipient-side decision frame** from the exact conversation evidence:
- what commercial outcome did the recipient explicitly say they would investigate or decide?
- what would make the opportunity valuable to *them* (for example client demand, delivery capability, margin, retention, or referral confidence)?
- which possible routes are Tom's hypotheses only, and therefore must not be presented as recipient demand?

**Rule:** Do not turn Tom's pre-call opportunity map into a menu of presumed needs. Lead with the recipient's stated reason to act, and introduce only the lightest relevant framing that helps them assess it. In particular, do not imply that the recipient needs Tom's direct internal services unless they have evidenced that need.

**Mechanism:** On every consequential commercial follow-up review, compare each proposed route/claim in the copy with the recipient-side decision frame. Remove or qualify anything that lacks direct conversational evidence. This is a high-integrity editorial check: if the frame cannot be established from the retained full thread/transcript, mark the review `coverage_incomplete` rather than confidently inventing commercial relevance.

### Commercial stage-transition check (MANDATORY for consequential commercial replies)
Before proposing or reviewing the next commercial move, explicitly record:
- **Buyer stage now:** the stage evidenced by the latest inbound (for example: exploring, evaluating, implementation/stitching, deciding, paused).
- **Latest buyer signal:** the exact new capability, problem, decision, timing or commitment the recipient has expressed.
- **What changed:** the material difference from the previous touch, including whether the buyer has moved forward, sideways or backward.
- **Recipient-stated outcome:** what the recipient said they want to achieve or decide next.
- **Proposed next move:** the one action the draft would create, with owner and timing.
- **Assumptions:** any route, offer, price, diagnostic, discovery step or internal service that is Tom’s hypothesis rather than recipient evidence.

**Stage-preservation rule:** the draft must meet the buyer at the latest evidenced stage. Do not regress an implementation/evaluation-stage conversation into a seller-led discovery or diagnostic offer unless the recipient explicitly asked for that route or the composition brief records a clear evidence-backed reason.

**Alignment mechanism:** compare every proposed commercial route in the draft against `latest_buyer_signal` and `recipient_stated_outcome`. If the proposed route is not directly supported, either remove it, qualify it as an option, or stop for Tom review with `commercial_stage_alignment: blocked`. A positive inbound followed by a newly introduced paid discovery/diagnostic is a mandatory review trigger, not an automatic recommendation.

**Required task-packet fields:** for task-system context drafts, persist `buyer_stage`, `latest_buyer_signal`, `stage_change_since_previous_touch`, `recipient_stated_outcome`, `proposed_next_step`, `assumptions_to_validate`, and `commercial_stage_alignment` (`aligned | qualified_option | blocked`).

### Internal-forwarding check (MANDATORY when recipients will brief or forward internally)
When the external recipients are expected to take the proposal to a partner, board, manager, or technical decision-maker, the email must also work as a compact standalone briefing if forwarded unchanged.

**Mechanism:** Before presenting the copy, remove the greeting and ask: “Could the internal decision-maker understand (1) what Tom does beyond a named product or licence sale, (2) why it could matter to their clients/business, (3) the commercial model, and (4) the immediate decision being requested?” If not, add a concise forwardable recap of the call and offer. Do not replace that recap with a bare product/service menu.

Then compose in this order, omitting elements only when the existing thread makes them redundant:
1. **Opening / acknowledgement** — acknowledge the specific point or answer already given. Do not add generic pleasantries in a fast back-and-forth, or repeat thanks/hope-you’re-well language that the thread has exhausted.
2. **Direct answer or position** — lead with Tom’s actual answer, decision, view, or availability. Do not bury it behind background explanation.
3. **Reasoning / useful detail** — give only the evidence or explanation needed for the recipient to understand the position. Separate known facts from estimates; do not turn uncertainty into certainty.
4. **Concrete next step** — make clear who does what next and, where useful, offer a bounded choice, proposed time, attachment, or decision request. Avoid vague endings such as “let me know your thoughts” when a sharper move is available.
5. **Close** — match the thread’s tone and sign-off convention. Preserve the configured sender/signature rules under `email-send`; do not manually imitate a signature unless the send workflow calls for it.

**Name-duplication rule:** when the governed signature block already displays Tom’s name, do not repeat his name in the authored sign-off. Use `Best,` / `Kind regards,` alone before the signature block (or omit the sign-off where the thread convention supports that). The rendered signature must carry the name once.

For a substantive commercial/client reply, also check whether the draft:
- protects Tom’s negotiating position and does not accidentally offer scope, price, delivery dates, or concessions not evidenced in current truth;
- distinguishes a recommendation from a commitment;
- keeps the recipient’s requested decision easy to make; and
- advances exactly one sensible next move rather than opening several unfocused threads.

### 5. Pre-save editorial verification
Before presenting or saving the draft, run this checklist:
- Every material inbound ask is answered, acknowledged, or intentionally deferred with a reason.
- The first substantive sentence contains the answer/position, not filler.
- Each factual assertion, attachment claim, date, price, scope statement, and commitment is supported by the assembled sources.
- Tone matches cadence: no duplicated pleasantries, false familiarity, abrupt reset, or unnecessary length.
- The next action has a named owner and usable timing/decision point where the situation requires one.
- No accidental send language, safe-sender promotion, or invented full-read/context claim is present.
- The result is explicitly **draft only** and ready for Tom’s review, not represented as an approved external message.

If any check fails because evidence is missing, return to the context/gated-read route and ask Tom for TOTP; never produce a holding draft or fill the gap with plausible prose.

### 6. Save, never send
For literal Outlook Drafts-folder creation, use:
`/home/tomdean88/.openclaw/integrations/microsoft-l1/draft.py`

**Thread-preservation invariant (MANDATORY):** when the requested action is a reply, call the script with `--reply-to-message-id <original Graph message id>`. Add `--reply-all` when replying to everyone. The script must use Graph `createReply`/`createReplyAll` and patch only the body/attachments, preserving Graph's conversation, subject and generated To/Cc recipient set. A standalone draft requires explicit `--new-message`; the tool must reject Reply All without an original message ID rather than silently creating a new email.

**Tom preference:** when Tom asks to draft an email, default to creating an unsent Outlook draft and returning its Outlook link, unless he explicitly asks for text-only. Do not silently substitute a chat-only draft because a current gate is unavailable: state that the Outlook-draft step is blocked and ask for the gate.

### Draft-delivery completion rule (MANDATORY)
For every Tom request phrased as “draft an email” (or equivalent), the completion checklist is: **(1)** source-backed copy, **(2)** `draft.py` creates the item in Outlook Drafts, **(3)** live post-create verification returns a stable draft ID/link, and **(4)** the reply reports that link and `not sent`. A chat-only draft counts as complete only when Tom explicitly requests text-only.

- When the approved Microsoft/exec gate is active, execute `draft.py` immediately after editorial verification; do not pause at chat copy, broker proof, task completion, or a progress report.
- If the gate is not active, report the draft as `prepared, Outlook save blocked` rather than calling it simply `prepared` or `drafted`.
- Before replying, match the user’s request against this checklist. If the Outlook draft ID/link is absent while the gate was active, continue execution instead of sending a completion message.

### Context-sufficiency hold point (MANDATORY)
A `context_ready` broker result is **not** by itself permission to write client-facing email. For a context-heavy commercial **reply/thread** draft, the composition packet must contain the full text (not a summary) of the latest material outbound message and any later material inbound/reply evidence that determines cadence, plus the verified recipient address, current entity record, and explicit current timing/next-action state. For a **standalone new message**, there is no prior thread to reconcile; require verified recipient identity, current entity record, relevant supporting evidence, buyer stage, and one proposed next move instead.

- Before composing a reply, inspect the packet manifest and source roles for `current_record`, `latest_outbound_full`, `latest_inbound_full_or_explicitly_absent`, and `recipient_identity`. A SharePoint communication recap, CRM summary, or prior-message paraphrase cannot satisfy a `*_full` requirement. For a standalone message, inspect instead for `recipient_identity`, `current_record`, relevant supporting evidence, buyer stage, and one proposed next move; do not require historical email evidence when no reply thread exists.
- If any required item is absent, mark the route `coverage_incomplete`, preserve the candidate, and repair/retry the bounded context path. Do not create chat copy or an Outlook draft until the exact thread and relevant context are loaded. Draft-only status means no TOTP/send approval is needed for the eventual write; it does not waive this evidence gate.
- The broker profile/source registry must distinguish standalone-new-message from reply/thread mode. Exact bounded email/thread evidence is mandatory for reply/thread mode only; it must not be used as a substitute for verified recipient identity in standalone mode.
- This check fires immediately before the composition brief and again immediately before `draft.py`. It is a required pass/fail checklist item, not stylistic judgment.

### No-gate local-mirror rule (MANDATORY)
The normal source for exact email/thread context is the canonical **local read-only mirror**, bound to the task/entity/profile through the broker — never a live Microsoft mailbox read. Before declaring exact message context unavailable, inspect the broker's registered local-mirror bindings and retained mirror artifacts for the exact message/thread IDs.

- A historical message that has aged out of a rolling mirror is a **retention/adapter gap**, not a TOTP-gate requirement. Record `coverage_incomplete`, preserve the draft block, and repair the governed mirror-retention/adapter path.
- Do not ask Tom for Microsoft/TOTP access merely to recover context that the mirror architecture is intended to retain. A gate can be relevant only to separately protected write operations or an explicit user-approved exceptional recovery — never the standard drafting-context path.
- Trigger: every context-heavy email draft that lacks an exact full-message artifact. Mechanism: check the task's registered mirror source/binding by opaque message/thread reference; if absent, return the exact coverage gap and open adapter/retention work rather than routing to Microsoft.

The script never calls a send endpoint. It requires a valid Microsoft grant with `Mail.ReadWrite`. Treat actual Drafts-folder appearance as unproven until a live post-create verification succeeds.

**Reply-linkage and idempotency verification (MANDATORY):** For every reply-mode draft, the writer must call Graph `createReplyAll` (or the explicitly recorded `createReply` exception) against the task-held original Graph message ID. Post-create verification must prove that the resulting draft has the original conversation ID and is a draft; a Drafts-folder ID/link alone is insufficient. Before creating a new item, the writer must look for an existing task-owned verified draft for that same original message and return it rather than create a duplicate. A saved draft is never evidence of a sent reply and must be excluded from source-thread composition and sent-reply suppression. If any linkage or state check is absent or conflicts, reject the result as `THREAD_CONTINUITY_UNVERIFIED` and preserve the task for repair.

**Reply-all, thread-continuity and signature defaults (MANDATORY):** Every reply draft must use the original Graph message ID and default to `createReplyAll` so the draft remains in the existing conversation and preserves the original recipient set. Every standalone draft and every reply draft must include the governed adaptive single-column Stackstone signature; a signature-less email is invalid. The writer must prepend the authored text and signature to Outlook Graph's generated quoted-history body; it must not replace that body with a fresh-looking standalone message. The only permitted exception is an explicit `reply_one` decision recorded in the task packet and passed as `--reply-one`; never omit the message ID or create a standalone draft for a reply.

### 7. Promotion candidate rule
If a consequential external sender repeatedly limits high-quality reply handling, flag them as an approved-sender promotion candidate. Never promote them automatically.

## Output format
Report compactly:
- `Reply needed:` yes/no
- `Route:` direct trusted / gated full-read / task-system context
- `Draft status:` prepared / saved to Outlook Drafts / blocked
- `Blocker:` only when relevant
- `Draft:` text or Outlook draft id/link

## Boundaries
- Never send automatically.
- Never change approved sender status automatically.
- If Tom explicitly approves a sender-status change, use only the fixed-path `manage_trusted_contacts.py` operator tool through the TOTP-gated exec route; never edit the registry or create a local substitute.
- Ask for TOTP only before a separately protected full-body mailbox read, sender-status change, configuration change, or external send. Ordinary unsent Outlook draft creation must use the bounded writer without TOTP.
- If full thread/context is unavailable, call the result blocked or incomplete rather than inventing a confident reply.
