---
name: email-send
description: Send outbound email only after approved TOTP authorization, with confirmed recipient, subject, body, account, and post-send verification.
last_edited: 2026-06-09 15:17
---

# Email Send

Use this skill whenever Tom wants an email **drafted or sent**.

## Default sender
- Default to **assistant@stackstoneconsulting.co.uk** for outbound email
- Only use **tom@stackstoneconsulting.co.uk** / Tom's personal Microsoft account if Tom explicitly asks

## Signature handling (UPDATED 15 Jun 2026)
**CURRENT STATE: do not rely on server-side signatures.**

Live evidence shows that a plain text/manual fallback is not enough when Tom explicitly wants the real branded signature styling preserved.

**Default rule:**
- Do **not** assume the server will append the signature correctly.
- Do **not** treat the text mirror of a sent email as sufficient if Tom wants the real visual signature.
- If Tom asks for "my signature", "the same signature", "same format/font/colour/layout", or equivalent, the source of truth is the **actual formatted HTML signature block from a real sent email** for that account.

**Mandatory fidelity rule:**
- For `tom@` or `assistant@`, if visual fidelity matters, extract/reuse the live formatted signature artifact from an actual sent email for that account.
- Canonical stored artifact for `tom@`: embedded in this skill and may also be mirrored to `reference/email-signatures/tom-signature.html` for operational reuse
- Canonical stored artifact for `assistant@`: embedded in this skill and may also be mirrored to `reference/email-signatures/assistant-signature.html` for operational reuse
- Do not substitute a text-only approximation when the request is clearly about formatting/branding.
- **Background-safety + brand rule:** branded HTML signatures must render legibly on both light-mode and dark-mode email clients while staying in Stackstone house style. Do not use transparent signature backgrounds with near-white text, or any text colour that depends on the app/background colour behind it. The canonical signature must carry its own explicit brand-safe card/background and use Stackstone brand constants: Arial, CHARCOAL `#2D2D2D`, SLATE `#4A5568`, AMBER `#D97706`, LIGHT_BG `#F7F5F2`, WHITE `#FFFFFF`, and BORDER_COL `#CBD5E0`. Amber is for accents/links/dividers, not body text.
- **Pre-send static check:** before calling a branded HTML signature ready, reject the body if the signature block contains `background:transparent`, `color:rgb(244,244,244)`, `color:#f4f4f4`, or equivalent near-white text outside an explicitly dark filled panel. If that check fails, the email is **not signature-safe** and must be fixed before TOTP/send.
- If live HTML extraction is gated, say that the draft is **not yet signature-complete** and request the gate/TOTP path rather than pretending the text version is enough.

**Fallback only when visual fidelity is not required:**

**assistant@ fallback block:**
```

Kind regards

PA to Tom Dean
Stackstone Consulting
assistant@stackstoneconsulting.co.uk
stackstoneconsulting.co.uk
```

When branded fidelity is needed for `assistant@`, use the embedded canonical signature block in this skill (and any mirrored operational copy) instead of the fallback block.

## Canonical branded signature artifacts

### `tom@` HTML signature
```html
<div id="Signature" class="elementToProof" style="margin-top:18px; max-width:620px; background:#F7F5F2; color:#4A5568; border:1px solid #CBD5E0; border-radius:8px; padding:14px 16px; font-family:Arial,sans-serif; line-height:1.4;"><table cellspacing="0" cellpadding="0" border="0" role="presentation" style="width:100%; background:#F7F5F2; color:#4A5568; border-collapse:collapse; text-align:left; line-height:1.4; font-family:Arial,sans-serif;"><tbody><tr><td style="border-right:2px solid #D97706; padding-right:18px; vertical-align:top; width:42%;"><div style="font-size:18px; color:#2D2D2D; font-weight:700; letter-spacing:-0.3px;">Tom Dean</div><div style="font-size:13px; color:#D97706; font-weight:700; padding-top:3px; padding-bottom:12px;">Founder &amp; AI Consultant</div><div style="font-size:16px;"><span style="color:#2D2D2D; font-weight:700; letter-spacing:-0.2px;">Stackstone</span><span style="color:#4A5568; letter-spacing:-0.2px;">&nbsp;Consulting</span></div></td><td style="padding-left:18px; vertical-align:top;"><div style="font-size:13px; padding-bottom:4px;"><a href="mailto:tom@stackstoneconsulting.co.uk" style="color:#4A5568; text-decoration:none;">tom@stackstoneconsulting.co.uk</a></div><div style="font-size:13px; padding-bottom:4px;"><a href="https://stackstoneconsulting.co.uk/" style="color:#D97706; text-decoration:none; font-weight:700;">stackstoneconsulting.co.uk</a></div><div style="font-size:13px; color:#4A5568; padding-bottom:4px;"><a href="https://linkedin.com/in/tomadean" style="color:#4A5568; text-decoration:none;">LinkedIn</a>&nbsp;- 07894 241 276</div><div style="font-size:11px; color:#4A5568; padding-top:6px;">AI Strategy &amp; Implementation for Mid-Market Businesses</div></td></tr></tbody></table></div><div style="font-family:Arial,sans-serif; font-size:12pt; color:#2D2D2D;"><br></div>
```

### `assistant@` HTML signature
```html
<div id="Signature" class="elementToProof" style="margin-top:18px; max-width:620px; background:#F7F5F2; color:#4A5568; border:1px solid #CBD5E0; border-radius:8px; padding:14px 16px; font-family:Arial,sans-serif; line-height:1.4;"><table cellspacing="0" cellpadding="0" border="0" role="presentation" style="width:100%; background:#F7F5F2; color:#4A5568; border-collapse:collapse; text-align:left; line-height:1.4; font-family:Arial,sans-serif;"><tbody><tr><td style="border-right:2px solid #D97706; padding-right:18px; vertical-align:top; width:42%;"><div style="font-size:18px; color:#2D2D2D; font-weight:700; letter-spacing:-0.3px;">PA to Tom Dean</div><div style="font-size:13px; color:#D97706; font-weight:700; padding-top:3px; padding-bottom:12px;">Founder &amp; AI Consultant</div><div style="font-size:16px;"><span style="color:#2D2D2D; font-weight:700; letter-spacing:-0.2px;">Stackstone</span><span style="color:#4A5568; letter-spacing:-0.2px;">&nbsp;Consulting</span></div></td><td style="padding-left:18px; vertical-align:top;"><div style="font-size:13px; padding-bottom:4px;"><a href="mailto:assistant@stackstoneconsulting.co.uk" style="color:#4A5568; text-decoration:none;">assistant@stackstoneconsulting.co.uk</a></div><div style="font-size:13px; padding-bottom:4px;"><a href="https://stackstoneconsulting.co.uk/" style="color:#D97706; text-decoration:none; font-weight:700;">stackstoneconsulting.co.uk</a></div><div style="font-size:13px; color:#4A5568; padding-bottom:4px;">Tom's AI Agent</div><div style="font-size:11px; color:#4A5568; padding-top:6px;">AI Strategy &amp; Implementation for Mid-Market Businesses</div></td></tr></tbody></table></div><div style="font-family:Arial,sans-serif; font-size:12pt; color:#2D2D2D;"><br></div>
```

**tom@ fallback block:**
```

Kind regards

Tom Dean
Stackstone Consulting
tom@stackstoneconsulting.co.uk
+44 7894 241 276
stackstoneconsulting.co.uk
```

**When server-side signatures are fixed again:**
- Tom will confirm they work
- Then revert to the lighter "Kind regards only" approach
- But do not assume that state until confirmed working

## Invoice and document send rule (MANDATORY)
When sending invoices or client deliverables via email:
1. **Always attach the actual file** - use `--attachment` flag with the PDF path (typically `/tmp/INV-XXX.pdf`)
2. **Never include SharePoint links to external clients** - SharePoint is Tom's internal system; clients cannot access it
3. Verify the attachment is prepared in the send command before calling the draft ready
4. Test: "Can the recipient open this without any Tom/L1 system access?" If no, fix it.

## Internal brief/document delivery rule (MANDATORY)
When Tom asks to "email me this", "send me the brief", "send me the document", or equivalent after I have created a brief, plan, report, or governed document:
1. Treat the **actual artifact content** as the deliverable unless Tom explicitly asks for just a summary, link, or heads-up
2. Default to sending the full content **inline in the email body** or as an attachment if that is clearly better
3. Do **not** send only a summary plus a workspace file path unless Tom explicitly wants that
4. Before send, run this test: **"If Tom opened this email away from the workspace, would he have the actual thing he asked for?"** If no, the send package is incomplete

## Rules
- **Draft-stage routing rule (MANDATORY):** if Tom asks to draft, write, prepare, introduce, or send an email, enter this skill immediately even if no send has been requested yet. Do not treat email drafting as generic writing work outside the governed email workflow.
- **Draft-not-send monitoring rule (MANDATORY):** when a draft originates from inbox monitoring for `tom@`, default behavior is `draft only, never auto-send`. If the monitored thread is on the external/body-withheld path, the full mailbox read gate/TOTP must be obtained before claiming the draft is context-complete.
- **Task-system context rule (MANDATORY):** if the right reply depends on richer thread cadence, CRM/current-truth, tacit commercial context, or a multi-message back-and-forth, treat the job as a context-assembly task first and drafting second. In those cases, prefer a task-system style prep flow over one-shot prose generation.
- **Literal Outlook-draft rule (MANDATORY):** if Tom specifically wants a saved item visible in Outlook Drafts, use the governed `email-reply-draft` workflow and `~/.openclaw/integrations/microsoft-l1/draft.py`, not `send.py`. `draft.py` must never be substituted with the send route. Do not claim Outlook visibility until a live create-and-verify test has passed for the account/token in use.
- NEVER send without a valid 6-digit TOTP code pasted in chat
- State full draft + recipient BEFORE sending
- "Go", "Send", or "window open" alone is not enough unless an approved gate/window actually permits the command path
- If a code was already pasted recently in chat, use it immediately instead of re-challenging Tom
- For assistant@ emails, use the exact assistant signoff block above
- For Tom's account, sign off as Tom, not as PA
- **Signature-presence rule (MANDATORY):** for every outbound email, explicitly decide whether the body will contain (a) the canonical HTML signature, or (b) the fallback text signature block. Never assume a signature will appear unless it is already present in the prepared body or deliberately injected by a verified send path.
- Log every send to `memory/email_log.md`
- **Operational activity logging rule (MANDATORY):** if the email send creates or closes a trust-relevant operational state change (for example invoice sent, client deliverable sent, chase sent, payment/next-step thread materially moved, or a `blocked` state), also write the outcome to `reference/OPERATIONAL_ACTIVITY_LOG.md` in the same pass or via the owning workflow.

## Draft-preparation mechanics (MANDATORY)
Before showing a draft as ready-to-send:
1. prepare the send inputs file-first
   - `/tmp/oc-email-recipients.txt` for visible To recipients, even if it only contains Tom/assistant as the visible To line
   - `/tmp/oc-email-bcc.txt` for BCC recipients; write it fresh for every email and leave it empty only when BCC is genuinely not being used
   - `/tmp/oc-email-subject.txt`
   - `/tmp/oc-email-body.txt`
   - attachment path list if needed
2. if BCC is being used, show Tom the **full BCC list after prep and before requesting TOTP**; do not ask for/open the TOTP gate until the BCC list is final and visible for review
3. inspect the prepared body and verify the chosen signature mode is actually present:
   - canonical HTML signature embedded in body, **or**
   - fallback text signature block embedded in body
4. if neither is present, the email is **not** ready and must be fixed before draft approval/send
5. state the exact send command/path that would be executed once the gate opens, including `--bcc-file /tmp/oc-email-bcc.txt` when BCC is in use
6. run this test: **"Can I execute within 5 seconds of gate opening?"**
7. if the answer is no, preparation is incomplete and the draft is not yet ready

## Invoice-send completion mechanics (MANDATORY)
If the email being sent includes an invoice PDF attachment:
1. treat the send and tracker update as one operational unit
2. prepare the tracker-update path before or alongside the send
3. after successful send, immediately update the tracker in the same gate/window
4. extract/confirm the invoice number from the subject/filename and ensure the tracker can answer definitively that the invoice was sent
5. do not split invoice send and tracker update into separate later steps unless Tom explicitly reprioritises

## Sender decision rule (FIRST)
Before drafting, decide explicitly:
1. **Is this being sent as L1 / assistant@?**
2. **Or is this being drafted for Tom / sent from Tom's account?**
3. **Is this a true reply / reply-all to an existing inbound email, or a fresh new email?**

This decision must happen **before** tone, structure, and wording are chosen.

Why it matters:
- assistant@ emails can sound like an assistant
- Tom emails must sound like Tom
- the wrong sender decision early will corrupt the whole draft

## Tom voice rule
If the email is being drafted **for Tom to send** or sent **from Tom's account**, it must sound like **Tom**, not like AI.

That means:
- direct
- natural
- human
- commercially intelligent
- grammatically correct
- clean sentence structure

Avoid obvious AI giveaways:
- over-balanced sentence rhythm
- generic consultancy phrasing
- over-explaining
- sterile polish
- abstract filler that sounds plausible but says little
- sounding like a pitch deck instead of a person
- softening active reality into vague "thinking about" language when the thing is already being done
- fake-disarming phrases that deny the obvious purpose of the email (e.g. pretending a pitch / ask / outreach isn't one)
- lines like "no big pitch", "not trying to sell you", or similar throat-clearing if they make the email sound more salesy or less like Tom

**Test:** If Tom read this aloud, would it sound like something he would actually say? If not, rewrite it.

**Closing-style rule:** In Tom-voice emails, prefer the shortest natural closing that still does the job. Do not automatically round off the ending with extra polish if a simpler line (e.g. "Let me know if you have time for a short call.") sounds more like Tom.

**Name-duplication rule:** when the governed signature block already displays Tom’s name, do not add `Tom` / `Tom Dean` again in the authored sign-off. Use `Best,` / `Kind regards,` alone before the signature, or omit the sign-off where appropriate. The signature should display Tom’s name once.

This rule matters less when the email is explicitly from L1 / assistant@ and meant to sound like an assistant.

## Quoted-thread parsing rule (MANDATORY)
When Tom pastes an email thread and then adds his own draft/comments above or below it:
1. Separate **Tom's proposed reply text** from the quoted thread/history before critiquing
2. Do not treat quoted earlier outreach, signatures, disclaimers, or forwarded content as part of the new draft unless Tom explicitly says it is
3. When giving feedback, reference the exact lines from Tom's proposed reply that you are critiquing
4. **Fail-closed:** if it's unclear what is Tom's new draft vs historical thread text, ask before critiquing

## Direct-source-first rule for live-thread drafting (MANDATORY)
When drafting a reply or follow-up to a real person in a live relationship thread — especially a CRM opportunity, account, partner, investor, or warm prospect:
1. Do **not** draft from CRM summary alone
2. First review the **latest direct source** of truth for the thread:
   - the actual latest inbound/outbound email if available, or
   - the latest dated SharePoint communication artifact / current file if inbox access is unavailable
3. Use CRM only as supporting summary context, not as the primary drafting source
4. If the latest direct source has **not** been reviewed, do **not** produce a confident draft that claims to fit the thread
5. **Fail closed:** say the draft is not yet grounded in the live thread and ask for/pull the latest message first

**Trigger:** Any ask like "draft a message to him/her", "reply to X", "follow up with X", or "send Brendan/Wasim/John a note" where prior live thread context exists.

**Test before drafting:** Have I seen the latest actual message, or the best available direct artifact representing it? If not, stop.

## Context assembly rule (CRITICAL)
Before drafting any important email, build the context first.

### Relationship-context sweep rule (MANDATORY)
For any meaningful email where prior relationship/thread context may matter:
1. Do a context sweep across the best available sources **before** drafting, in this order of preference:
   - **Email / live thread** — check for the latest actual inbound/outbound context if it exists
   - **CRM / partnerships summary** — check local summary layer for status, last touch, and next-step framing
   - **SharePoint** — check the latest current file / dated communication artifact for fuller recent context
   - **Internet** — only if identity, role, company, or public positioning is still unclear after internal sources, or if this is a new/lightly-known person where public context would materially improve the email
2. In the draft working note to yourself, answer in one sentence:
   - who they are
   - why Tom is writing now
   - how the relationship/thread has progressed to this point
   - what they likely care about next
   - what the next-step ask should be
3. If strong internal context already exists, do **not** do a performative web search just to satisfy the rule
4. If context is still thin or ambiguous, **do not** write a confident context-heavy email pretending the relationship is better grounded than it is
5. Instead either:
   - ask Tom for the missing context, or
   - do your own public search if that is the sensible next source, or
   - write a deliberately light-touch holding draft that makes no claims beyond what is actually known
6. When the person is new/lightly-known and Tom's own description may be incomplete, prefer **independent source-finding** over letting Tom unknowingly supply all the framing. Use Tom's notes as a lead, not as the whole model of who the person is.
7. **Fail-closed:** if I have not checked the relevant internal relationship record(s) for a known contact, or if I cannot name the source that gave me the hook for the email, I must not act as though the email is properly contextualised

**Trigger:** any follow-up, reply, reactivation, intro, investor/partner note, or other email where the naturalness of the message depends on understanding the actual state of the relationship/thread.

**Mechanism test:** before showing the draft, ask: "Which sources told me where this conversation currently is, and which source gave me the hook for this email?" If I cannot answer that concretely, the context sweep was not done.

### Required context questions
1. **Who is this person?**
   - role
   - relationship to Tom
   - company / entity
   - if another person is the bridge/introduction, will the recipient know exactly who that is?
2. **Why are we writing now?**
   - trigger event
   - what happened just before this email
3. **What do they care about?**
   - commercial lens
   - personality / style if known
   - likely objections / interests
4. **What is the goal of this email?**
   - intro
   - progress
   - close
   - ask for call
   - send deliverable
5. **What should be held back?**
   - things not to pitch yet
   - things for the next conversation, not this email

### Human-email test
A human doesn't write from generic positioning first.
A human pulls back the relationship context and wraps the message around the moment.

**Test before drafting:**
- Does this email sound like it knows who the recipient is?
- Does it sound like it was triggered by a real moment, not written from a generic template?
- Does it say the right amount for *this stage* of the relationship?

If not, gather more context before drafting.

## Recipient-model rule (CRITICAL for relationship-shaping emails)
For emails where ambiguity would be costly — especially:
- first outreach
- warm intros
- investor notes
- senior stakeholder emails
- relationship-shaping follow-ups

explicitly model the reader before finalising:
1. **Persona** — how do they tend to think / speak / decide?
2. **Agenda** — what are they likely trying to optimise for?
3. **Tolerance** — how much fluff / abstraction / polish will they tolerate?
4. **Hook** — what is most likely to make *this specific person* lean in?

Then critique the draft **as them**:
- If I were them, what would feel vague?
- What would feel generic?
- What would feel over-pitched?
- What would actually make me reply?
- Are the people and companies referenced clear?
- Do the statements made actually feel grounded, or are they only clear from our side?

This is a **risk-based review**, not a rigid process for every trivial email.
Use it when the cost of ambiguity is high.

### Reader-fit test
Before sending, ask:
- Does this sound like it was written *to this person*, not just *for a type of person*?
- Is the sharpest relevant hook early enough?
- Have we said too much for email one?
- Have we held back what should be held back?
- Have we made any key person references too casually? (e.g. "Jess" instead of "Jess Harrold at Harken")
- Have we done a final plain-English grammar pass for obvious slips / awkward phrasing?
- Are we pretending this is less commercial / less intentional than it really is?

If not, rewrite.

## Context stitching rule (CRITICAL)
If the email relates to a live:
- account
- opportunity
- partnership / investor / referrer

then the send must be treated as part of the relationship record, not a standalone action.

That means the system should preserve enough context for later retrieval by:
- capturing the sent thread in the relevant summary layer
- creating/updating the relevant SharePoint note trail
- keeping next step / last touch current

**Test:** If Tom asks later "what did I send them and why?" the system should be able to answer from the record, not just from vague memory or inbox archaeology.

## Reply / threading rule (CRITICAL)
When Tom is responding to an inbound email or says things like "reply to X", "respond to this", or "send that back to them":
1. Default to a **true reply** to the original message, not a fresh email
2. Use **reply-all** if the original context or Tom's instruction implies the wider thread should be preserved
3. Only use a fresh new email if:
   - there is no usable message/thread id, or
   - Tom explicitly wants a new thread
4. If you cannot preserve the thread, say that explicitly before sending; do not silently downgrade to a fresh email
5. In the prepared send package, make the mode visible: `reply`, `reply-all`, or `new email`

## Preparation rule (CRITICAL)
**When drafting an email that will need TOTP approval:**
1. **Prepare the send command WHILE drafting** — don't wait until gate opens
2. **Preflight all prerequisites before calling the draft ready** — recipient email(s), sender account, subject, final body, exact send mode (`reply` / `reply-all` / `new email`), and message id if replying must all already be known
3. If any required send input is missing, ask for it **before** gate-open and explicitly say the email is **not yet send-ready**
4. Write body to `/tmp/oc-email-body.txt` immediately after showing draft
5. Have the exact send command ready
6. Treat TOTP windows as short-lived: do all possible ungated prep before asking for the code
7. When Tom opens gate → **execute only**, no prep steps and no fresh fact-finding

## Recipient integrity rule (MANDATORY)
Before **every** send:
1. Rebuild the recipients file for **this specific email**; do not assume an old `/tmp/oc-email-recipients.txt` is still correct
2. Rebuild `/tmp/oc-email-bcc.txt` for **this specific email** whenever BCC is possible; do not reuse an old BCC list
3. Treat all prior `/tmp` send artifacts (recipients/BCC/subject/body/attachments) as unsafe until rewritten or explicitly verified for the current send
4. State the intended To recipients and BCC recipients for the current send to yourself before executing
5. If the current ask changes the recipient set in any way (for example: "send to Tom instead", "CC Adam too", "not them, me", "add/remove these BCCs"), regenerate the send files before executing
6. **Fail-closed:** if you are not certain the recipients file and BCC file belong to the current send, do not send

**BCC pre-gate rule (MANDATORY):**
- For any email using BCC, the draft is not send-ready until `/tmp/oc-email-bcc.txt` exists, has been freshly populated, and the full BCC list has been shown to Tom before the TOTP request.
- Do not hide BCC behind “recipient list prepared”; list every BCC address or provide the exact reviewed source artifact if the list is very long and Tom has explicitly accepted that review form.
- The send command must include `--bcc-file /tmp/oc-email-bcc.txt`; otherwise the BCC field will not be populated.

**Concrete execution test before send:**
- Does the current To recipients file match the latest user instruction exactly?
- Does the current BCC file match the latest reviewed BCC list exactly?
- Were both freshly written for this email?
- Am I relying on any stale `/tmp` state from a previous send?
If there is any doubt, regenerate the files first.

**Test:** Can you send within 5 seconds of gate opening? If no, you didn't prepare properly.

**Pattern:**
- Tom asks for email draft
- Build context first
- Resolve all missing recipient/identity details first
- Show draft only once it is genuinely send-ready, or explicitly mark what is missing
- IMMEDIATELY: write body to /tmp, prepare command
- Tom approves / opens gate
- Execute (no reading skills, no file writing, just send)

## Commands
**Script:** `python3 ~/.openclaw/integrations/microsoft/send.py`

**Always default to assistant@ unless the user explicitly asks to send as Tom.**

### Send as assistant@stackstoneconsulting.co.uk (default)
For short/simple emails:
```bash
python3 ~/.openclaw/integrations/microsoft/send.py \
  --account assistant \
  <recipient_email> "PA to Tom Dean" \
  "<subject>" "<body>"
```

For multiple visible To recipients on ONE shared email:
1. Write recipients to `/tmp/oc-email-recipients.txt` (one per line or comma-separated)
2. Run:
```bash
python3 ~/.openclaw/integrations/microsoft/send.py \
  --account assistant \
  --recipients-file /tmp/oc-email-recipients.txt \
  --subject-file /tmp/oc-email-subject.txt \
  --body-file /tmp/oc-email-body.txt \
  <recipient_email_or_placeholder> "PA to Tom Dean"
```

For BCC sends:
1. Write visible To recipient(s) to `/tmp/oc-email-recipients.txt`
2. Write every BCC recipient to `/tmp/oc-email-bcc.txt`
3. Show Tom the full BCC list before requesting TOTP
4. Run:
```bash
python3 ~/.openclaw/integrations/microsoft/send.py \
  --account assistant \
  --recipients-file /tmp/oc-email-recipients.txt \
  --bcc-file /tmp/oc-email-bcc.txt \
  --subject-file /tmp/oc-email-subject.txt \
  --body-file /tmp/oc-email-body.txt \
  <recipient_email_or_placeholder> "PA to Tom Dean"
```

**Important parser note:** even when using `--recipients-file`, `--subject-file`, and `--body-file`, the script still requires the positional `from_name` argument and behaves most safely if a dummy/real `to` positional is also supplied. Do not omit these trailing positionals when using file-based inputs.

For longer emails, use `--body-file` (preferred to avoid security denylist matches in shell args):
1. Write body to `/tmp/body.txt` (or `/tmp/oc-email-body.txt`)
2. Run:
```bash
python3 ~/.openclaw/integrations/microsoft/send.py \
  --account assistant \
  <recipient_email> "PA to Tom Dean" \
  "<subject>" \
  --body-file /tmp/body.txt
```

**Important:** Replace `<recipient_email>` with the actual address from context. The from-name for assistant@ is **"PA to Tom Dean"**, not "Stackstone Assistant".

### Send as tom@stackstoneconsulting.co.uk (only if user explicitly requests it)
For short/simple emails:
```bash
python3 ~/.openclaw/integrations/microsoft/send.py \
  --account microsoft \
  <recipient_email> "Tom Dean" \
  "<subject>" "<body>"
```

For multiple recipients on ONE shared email, use the same `--recipients-file` pattern with `--account microsoft`, and still include the trailing positional `to` placeholder plus `"Tom Dean"` as `from_name` because the script parser requires them even when subject/body/recipients are file-backed.

For BCC sends from Tom's account, use the same `--bcc-file /tmp/oc-email-bcc.txt` pattern with `--account microsoft` and the full BCC pre-gate review above.

For longer emails, use the same `--body-file` pattern.

### Threading as a reply
To thread as a reply, add the Microsoft message ID as the final positional argument:
```bash
python3 ~/.openclaw/integrations/microsoft/send.py \
  --account assistant \
  <recipient_email> "PA to Tom Dean" \
  "<subject>" "<body>" \
  <message_id>
```

Use `\n` in the body for line breaks when passing inline.

### Multi-recipient integrity rule (CRITICAL)
**If Tom intends one shared email, do not turn it into multiple separate emails.**

This applies to:
- introductions ("put you both in touch")
- joint updates
- one-message-to-multiple-people requests
- reply-all situations

When Tom intends one shared email:
1. Treat the deliverable as **one message object** with multiple recipients
2. Present the full joint recipient list before send
3. Prepare one send path that preserves the shared recipient context
4. If the available command path cannot safely send one shared email, **say so before sending** — do not fake it with separate sends

**Never do this:**
- Send separate new emails to each recipient and pretend that equals one introduction
- Preserve wording but break the social object of the message
- Assume matching subject lines create a shared thread

**Test:** Will every intended recipient appear on the same email together? If no, it is not the right send.

## Workflow
1. Confirm recipient, subject, full body, and sender account
2. Default sender to assistant@ unless Tom explicitly requested Tom's account
3. Before calling any draft ready, verify that all required recipient email addresses are already known; if not, stop and ask before progressing
4. For any joint intro / shared email, verify that the final send plan is **one email with all intended recipients together**; if not, stop and fix the send plan before gate-open
5. If this is **draft-only for now**, still complete the sender/context/drafting steps in this skill and explicitly say whether the email is **send-ready** or what exact prerequisite is still missing
6. Obtain valid 6-digit TOTP code from chat, or use an already-open approved window
7. If Tom says the approval window/gate is open, trust that statement and attempt the action immediately rather than re-challenging for approval
8. If the email is long, first use `write` to create `/tmp/oc-email-subject.txt` and `/tmp/oc-email-body.txt`
9. If using `--recipients-file` and/or `--subject-file` / `--body-file`, still include the required positional `to` placeholder and `from_name` in the command because `send.py` parser requires them
10. Run the exact documented `send.py` command via exec — do NOT improvise alternative commands, wrappers, heredocs, filenames, or helper paths
10. If using an already-open approval window, do not force a fresh approval by setting exec ask mode to `always`; use the normal/open-window path instead
11. Confirm success/failure to Tom
12. Append a log line to `memory/email_log.md`

## Completion-not-detection rule (MANDATORY)
This skill is not complete when a draft merely exists or when the send command is merely prepared.
Completion means the intended email was actually sent through the correct route, or the pass failed closed with the exact blocker.

If the email also creates a downstream operational obligation, completion includes the owning-system update too.
Examples:
- invoice email -> relevant invoice tracker fields/rows updated
- chase email -> chase-driving tracker fields updated
- client deliverable / important relationship email -> operational log / CRM / SharePoint state updated where materially required

## Ambiguity / ask-Tom rule (MANDATORY)
If you are not materially certain about sender account, recipients, reply-vs-new-email mode, attachment set, or which downstream system should update after send, ask Tom a short clarification question instead of guessing.

## Failure rule
- If sending fails, treat it first as a command/path awareness or shell-argument scanning problem before assuming TOTP failed
- If Tom explicitly said the approval window is open, do not second-guess that by repeatedly asking for fresh approval unless the normal open-window execution path has actually been tried
- Never invent a substitute email-send route
- Never use heredoc execution for email sending — security scanner may flag it before exec runs
- If the exact command is unavailable or blocked, tell Tom which exact command was attempted

## Notes
- This does NOT require a separate send tool beyond exec after TOTP approval
- Keep quoting safe when constructing the command
- If replying into an existing Microsoft thread, use the optional 5th argument

## Drafting rule for post-call follow-ups
When drafting a follow-up after a meeting/call:
1. Start from what was actually said on the call, not from a generic consultant summary
2. Mirror the natural structure that emerged in the conversation (e.g. "three strands")
3. Prefer concrete next steps and real language over polished abstraction
4. Preserve the recipient's framing and priorities where possible
5. Ask: "Does this sound like a real continuation of the conversation?" If not, rewrite

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
