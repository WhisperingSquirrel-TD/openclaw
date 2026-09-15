---
name: linkedin-post
description: Draft LinkedIn posts for Tom Dean / Stackstone Consulting. Use when Tom asks for a LinkedIn post, content, or social copy.
metadata: { "openclaw": { "emoji": "💼" } }
last_edited: 2026-07-13 21:26
---

# LinkedIn Post Skill

## Policy Lineage
This process supports `SALES_POLICY.md`.

LinkedIn posts are not just content output — they are part of Stackstone's sales and positioning strategy, helping attract relevant conversations, establish credibility, and create opportunities.

## Process Role
This is a recurring opportunity-generation process via LinkedIn.

## Required source loading — before drafting or auditing copy
Read these in order, using the live files rather than memory:
1. `stackstone/linkedin-current-brief.md` — current positioning and commercial intent
2. `stackstone/linkedin-content-calendar.md` — canonical slot and sequence
3. `stackstone/linkedin-posts.md` — published/queued truth and anti-repeat check
4. `reference/TOM-VOICE-CALIBRATION.md` — canonical Tom voice bank
5. `memory/linkedin-ideas.md` — supporting source material when needed

The voice-calibration file is not optional when it exists. If it is missing or unreadable, do not claim the copy has passed the Tom-voice gate; report the coverage gap and use only clearly identified source material.

**Trigger:**
- Scheduled draft cron on Monday and Wednesday evenings
- Intended publishing window is the following morning (typically Tuesday/Thursday, or the next suitable morning if Tom wants to shift it)
- Also when Tom explicitly asks for a LinkedIn post

**Cross-skill planning rule (MANDATORY):**
If the previous scheduled draft window should have produced a LinkedIn post for the next morning and the relevant next publish slot is not yet clearly covered, the morning standup should proactively surface LinkedIn as a concrete task rather than assuming the content cron handled it.

**Scheduled preflight (cost control):**
- Before drafting on a cron run, read `stackstone/linkedin-current-brief.md` if present and use it as the live brief.
- Read `stackstone/linkedin-content-calendar.md` when present. It is the canonical sequencing layer: select the next eligible planned Tuesday/Thursday slot rather than inventing a generic distinct angle. Only deviate for a real, timely named event or explicit Tom direction; preserve any displaced slot in the calendar.
- Also check `memory/linkedin-ideas.md` for published markers.
- **Slot-specific cadence rule (MANDATORY):** Monday-evening draft is for the Tuesday slot. Wednesday-evening draft is for the Thursday slot. A Tuesday `[PUBLISHED ...]` marker must not suppress the Wednesday-evening draft.
- Only skip if the **next intended publish slot** is already clearly covered.
- **Same-day live-slot continuity rule (MANDATORY):** if Tom has already discussed, shaped, or approved a concrete angle/draft for the next intended LinkedIn slot in the current live conversation, treat that live conversation as the primary source of truth for the slot. Do **not** generate a fresh unrelated angle on the cron path. Either continue the same direction or explicitly skip with a note that the slot is already being worked live.
- **Published-skip response rule (MANDATORY):** when a cron run is skipped because the relevant next slot is already covered, return a one-line explicit skip summary naming the marker/date/slot. Do **not** use `NO_REPLY`, acknowledgements, or a blank/status-only response for this case.
- **Fail-closed completion rule for cron drafts:** never return `NO_REPLY`, an acknowledgement, or a status-only message while the drafting task is still incomplete. Either (a) deliver the full draft package, or (b) explicitly state the blocking missing source.
- **Partial-read recovery rule:** if one non-critical read fails (for example a wrong path, missing optional brief, or transient file error), retry with the correct path or continue from the remaining required sources. Do not abandon the cron task if `stackstone/linkedin-posts.md` and enough brief/context remain to draft safely.
- **Recent-explicit-direction override rule (MANDATORY):** if Tom has recently set a concrete content direction in chat (for example a named sequence, event-promo strategy, campaign angle, or "we need to talk about X" instruction), that direction outranks an older standing brief. Do not let the cron fall back to a generic distinct angle just because it passes anti-repeat checks.
- **Live-chat outranks cron-memory rule (MANDATORY):** when there is a conflict between a cron's independent drafting path and a same-day live user conversation about that exact post slot, the live conversation wins. The cron result must be reconciled to the live chat before delivery; do not forward an unrelated draft into the chat as if no work had already happened.
- **Cross-day continuity rule for LinkedIn (MANDATORY):** when Tom and L1 agree a multi-post sequence (e.g. "sell the talks + invite people + give snippets"), treat that as the current campaign spine until it is completed, replaced, or explicitly deprioritised. The next draft should continue the sequence, not rediscover a fresh angle.

**MANDATORY theme-deduplication check (BEFORE drafting):**

This check happens BEFORE you write any post. Do not draft first, then check.

1. Read `stackstone/linkedin-posts.md` completely
2. **List out the recent post themes explicitly** in your working context (topic column + notes, not just "I read it")
3. **State the proposed new angle explicitly** — write it down in one sentence
4. **Compare side-by-side:** Does the new angle overlap meaningfully with any recent theme?
   - Same core message? (e.g., "process before output" vs "process audit before AI strategy" = same)
   - Same framing? (e.g., "boring opportunities" vs "operational drag" = same)
   - Same CTA or question? (e.g., "Where is the drag?" used recently = reject)
5. **If yes → reject immediately.** Choose a genuinely different angle from `memory/linkedin-ideas.md`
6. **If no → proceed to draft**

**Test before drafting:** Can you explain why the new angle is distinct from recent posts in one sentence? If you can't, it's not distinct enough.

**Fail-closed rule:** If the recent-post comparison has not been done explicitly, do not draft. If the proposed angle overlaps meaningfully with a recent post, reject it immediately and choose a new angle before writing a single line.

**Pre-delivery anti-repeat gate (MANDATORY):**
Before any draft is shown to Tom, run a second explicit gate against `stackstone/linkedin-posts.md` and the current brief:
1. Name the draft's core hook in one sentence
2. Name the draft's concrete example / framing in one sentence
3. Check whether either is too close to recent fallback patterns or recent published posts
4. If the hook or framing is "same idea, different wording", discard the draft and rewrite from a genuinely different angle
5. **Sequence-integrity check:** if Tom recently set an active sequence/campaign direction, ask: "Does this draft obviously advance that exact sequence?" If no, reject it even if it is distinct from older posts.

**Known repeated fallback patterns to reject unless the brief explicitly demands them:**
- "AI work is boring"
- "operational drag / friction removal"
- tidy process-before-output / boring-but-valuable transformation framing
- generic "start with the problem, not the tool/model" positioning without a sharper Stackstone-specific edge
- broad operator/leadership-team bottleneck posts that could have been written by any competent AI consultant

If similarity is arguable rather than clearly distinct, treat that as a fail and rewrite before delivery.

**Generic-angle rejection rule (MANDATORY):**
If the post's core point is a broadly agreeable AI/business opinion that many consultants could post, reject it before delivery.

Fail examples:
- "don't start with tools, start with the problem"
- "AI value is in the workflow"
- "look for friction/bottlenecks"
- "most businesses talk about AI at headline level"
- generic independent-adviser / generic strategy-only takes that ignore Stackstone's live implementation-and-process-design positioning

Pass threshold:
- the post must contain a sharper Stackstone-specific stance, observation, live example, named sequence angle, or commercially useful point that is recognisably Tom rather than generic market commentary.

**Scheduled-draft specificity gate (MANDATORY):**
On Monday/Wednesday scheduled drafts, before writing the post, explicitly choose one of these anchors:
1. a live talk/event runway,
2. a specific client/prospect pattern Tom has genuinely observed,
3. a named Stackstone point of view that is not already in the recent fallback set,
4. a concrete operating-system / agent / workflow observation unique to Tom's current work.

If no such anchor is present, do not fall back to generic AI-ops commentary. Instead say the angle is not specific enough yet and choose a different one.

**DO NOT:**
- Skip this check and "trust your memory"
- Draft first, then check
- Rationalize similarity as "different enough"
- Let a scheduled cron post bypass the same anti-repeat check

**If Tom corrects you on theme overlap after you've already drafted, you failed this check.** Stop iterating and apply the check properly.

**Purpose in sales system:**
- stay visible to the right audience
- reinforce credibility and positioning
- create inbound conversations and future opportunities

## 360Brew — LinkedIn's AI Algorithm (2025/2026)

LinkedIn replaced its rule-based ranking with 360Brew — an LLM that reasons holistically about content, creator, and viewer together. Key implications for every post:

**What 360Brew rewards:**
- **Genuine expertise** — it reads all your recent posts to build a creator profile. Stay in your lane (AI strategy for mid-market businesses). Off-topic posts dilute your authority signal.
- **Comment depth, not like count** — a thoughtful comment that extends the conversation beats 50 likes. Always end posts with a genuine, open-ended question. Reply to every comment fast.
- **Consistency** — regular posting (2–3x/week) builds a "trusted creator" profile. Irregular bursts don't.
- **First-hour performance** — distribution is decided early. Engage immediately after posting. Have someone ready to comment within minutes if possible.
- **Niche relevance** — 360Brew matches posts to viewers semantically, not just by hashtag. Write for a specific audience (MDs, ops directors, CTOs at £2m–£50m businesses).

**What 360Brew penalises:**
- Links in post body (signals "leave LinkedIn" — kills dwell score). Links go in FIRST COMMENT only. ← already in rules, now double-important.
- Engagement bait ("comment yes if you agree", emoji polls, reaction requests) — actively suppressed.
- Generic/off-topic content — dilutes creator expertise profile.
- Posting without engaging — no comments back = weak conversation depth signal.

**Optimal posting times (UK B2B):** Tue–Thu, 07:00–09:00 or 12:00–14:00.

---

## Positioning anchor (MANDATORY)
Treat Stackstone’s current positioning as:
- **independent AI advisory + practical implementation**
- helping small and mid-market businesses **put AI to work inside the business**
- finding where AI genuinely adds value, **designing the process around it**, and **building practical systems teams can trust**
- staying vendor-independent while still being implementation-capable
- maintaining the judgment to say when the right answer is **not AI**, but structured automation / deterministic workflow instead

This means LinkedIn content should usually strengthen one or more of these ideas:
- AI inside real business processes
- process design / workflow design
- trust, auditability, approvals, and operational reality
- practical implementation over abstract hype
- the difference between genuine working systems and shallow AI theatre
- good judgment about when not to use AI

## Tom's Voice
- First person, direct, confident but not arrogant
- Practitioner tone — Tom has done this work, not just read about it
- Short sentences. No waffle. No corporate buzzwords.
- Occasional wit, never forced
- Oxfordshire-based, mid-market AI strategy focus
- Audience: business owners, MDs, ops directors, CTOs at £2m–£50m companies
- **Voice-anchor rule:** before drafting, ground yourself in Tom-written material, not just abstract style rules. Read recent successful posts in `stackstone/linkedin-posts.md` and use them as the cadence reference.
- **Voice-calibration file rule (MANDATORY):** before drafting or auditing LinkedIn copy, read `reference/TOM-VOICE-CALIBRATION.md` when it exists. Treat it as the canonical bank for "sounds like Tom / doesn't sound like Tom" patterns extracted from transcripts, posts, and real examples.
- **Tom-source-before-L1 wording rule (MANDATORY):** when Tom says previous LinkedIn copy sounded too AI-written or generic, drafting must start from Tom-origin language first: recent Tom-written posts, transcript excerpts, voice notes, or explicit phrases Tom used in chat. Do not start from a clean L1-written LinkedIn structure and then try to roughen it afterwards.
- **Voice-first execution gate (MANDATORY):** before writing any LinkedIn-shaped copy, complete a source-first pass in this order: (1) select one Tom-origin source passage, post, transcript excerpt, voice note, or explicit phrase that genuinely anchors the angle; (2) record at least two concrete cadence/wording characteristics from that source; (3) write a rough spoken version as if Tom were saying it aloud; (4) reject it if it does not sound sayable as Tom; and only then (5) lightly format that spoken version for LinkedIn. Merely reading `TOM-VOICE-CALIBRATION.md`, repeating its rules, or passing a post-draft checklist does not satisfy this gate.
- **Source-gap fail-closed rule:** if no Tom-origin source can support the proposed angle, do not invent generic buyer language or draft a substitute thought-leadership post. State that the voice source is insufficient and ask Tom for a real observation, conversation, phrase, or example before drafting.
- **Voice evidence requirement:** every draft package must retain an internal voice note containing the selected Tom-origin source, the two extracted cadence/wording observations, and the rough spoken version. Do not claim a voice gate passed without that evidence.
- **No-generic-authority-post rule (MANDATORY):** if a draft could plausibly be posted by a generic AI consultant, reject it before delivery even if the writing quality is good. Distinctiveness beats polish.
- **Anti-AI-writing rule:** do not write like a neat explanatory essay. Avoid over-balanced contrast structures, generic “the real issue is…” scaffolding, polished consultant cadence, and tidy insight-paragraph rhythm.
- **Podcast-snippet rule:** aim for the feel of a clipped spoken snippet from a good podcast: conversational, human, natural to say out loud, with one sharp point but without sounding rehearsed. It should feel like Tom talking, not Tom publishing an essay.
- **Anti-rhetorical-structure rule:** do not shape the post into a neat mini-essay. Avoid clean explanatory arcs, balanced contrasts, symmetrical paragraph patterns, or tidy “setup → explanation → conclusion” construction if they make the copy feel written rather than spoken.
- **Anti-compression rule:** do not compress the point so tightly that it turns into polished slogan-like beats. Let the thought breathe slightly. A sharp point is good; an over-distilled rhythm is not.
- **Answer-first brevity rule (MANDATORY):** decide the post's useful answer or reframe in one sentence before drafting. Put that answer in the opening lines. Do not make the reader work through a long problem description to reach it. Cut setup, context, and explanation unless each materially sharpens the answer. If the problem is explained for longer than the useful point is delivered, fail and rewrite.
- **Anti-tricolon rule:** do not default to writing in threes. Avoid neat three-beat lists, repeated three-line contrasts, or rhythmic "X. Y. Z." structures unless Tom's actual source material clearly uses them.
- **Structural anti-AI gate (MANDATORY):** before delivery, scan the draft for (a) three or more parallel questions/items, (b) stacked rhetorical questions, (c) a tidy hook → list → explanation → takeaway sequence, or (d) several short lines that each land a polished point. Any one of these is a fail unless the exact structure is clearly grounded in Tom's source language. Discard and restart from a rough spoken scene or real observation; do not merely re-punctuate or swap synonyms.
- **Spoken-cadence enforcement rule:** if Tom asks for "more punchy", "more spoken", or "more like a podcast excerpt", rewrite for looser spoken cadence: fewer stacked short lines, fewer slogan-like sentence fragments, fewer abstract summary lines, and more natural connective phrasing as if Tom is saying it mid-conversation.
- **Podcast-first drafting rule (MANDATORY):** if Tom asks for podcast style / spoken-word style / "like I'd say it", do NOT draft as a LinkedIn post first. First write a rough spoken version as if Tom is answering the point out loud in a podcast or voice note. Only after that may you lightly shape it into LinkedIn formatting. If the underlying spoken version does not sound real, discard it before any LinkedIn polishing.
- **Delivery test:** before showing a draft, read the first five lines as spoken dialogue in your head. If they sound like polished LinkedIn copy rather than something Tom could say into a mic, rewrite before sending.
- **AI-sounding copy rejection rule (MANDATORY):** reject any draft that reads like tidy social copy rather than Tom talking. Common fail signs include:
  - slogan-like line stacking
  - neat contrast beats like "Not X. Y."
  - over-compressed mini paragraphs that each land one polished point
  - generic explanatory cadence that feels written for LinkedIn rather than spoken by Tom
  - abstract lines that sound smart but don't feel like something Tom would naturally say out loud
- **Voice proof test (MANDATORY):** before delivery, ask: "Could Tom plausibly say this, almost verbatim, in a conversation, voice note, or podcast clip?" If not, reject and rewrite.
- **Calibration-bank check (MANDATORY):** before delivery, compare the draft against `reference/TOM-VOICE-CALIBRATION.md`. If the draft matches listed drift patterns or ignores the preserved strengths/themes, reject it and rewrite before showing Tom.
- **Concrete-example-first rule (MANDATORY):** if the draft's core point is abstract (for example continuity, trust, follow-through, process, orchestration), start from one real observed example before widening to the principle. Do not lead with a polished abstraction if Tom would naturally begin with what actually happened.
- **Natural-roughness preservation rule (MANDATORY):** do not over-smooth the copy into elegant LinkedIn prose. If a plainer, slightly rougher version sounds more like Tom, prefer it. Short blunt lines, lightly uneven rhythm, and simple phrasing are often a feature, not a flaw.
- **No over-explaining between punch lines rule:** when the point is already clear, do not add tidy connective/explanatory sentences just to make the post read more completely. If Tom would naturally jump from claim to examples to consequence, preserve that jump.
- **List-format allowance rule:** when Tom's natural phrasing is more forceful as simple bullets or broken-out examples, allow that structure. Do not automatically rewrite bullets into polished mini-paragraphs.
- **Specific drift check — reliability/heroics phrasing:** prefer grounded language like "someone reliable catches it" or "heroic individuals" over tidier consultant phrasing like "someone quietly keeping the wheels on" unless Tom explicitly uses the latter. Default to the more human, less polished version.
- **Draft-self-critique rule (MANDATORY):** before showing Tom a draft, explicitly test it against this checklist:
  1. Is this too neat?
  2. Is this too LinkedIn-aware / performatively polished?
  3. Does it sound like Tom walking someone through something real?
  4. Is there enough lived observation, not just a clean idea?
  5. Does it still read like good social copy more than Tom saying something true?
  6. Have I made it too neat by adding explanatory glue Tom would not say?
  7. Would a blunter, less elegant version sound more real?
  If any answer is unfavourable, discard and rewrite before delivery.
- **No-surface-fix rule:** do not just swap a few lines or roughen the punctuation on an already-AI-sounding draft. If the underlying thought still feels written rather than spoken, restart from a fresh spoken monologue instead of patching the old copy.
- Vary sentence length and rhythm on purpose.
- Prefer slightly rougher, more human phrasing if that sounds more like Tom.
- Use specific lived examples where possible. If the copy could have been written by any competent AI consultant on LinkedIn, rewrite it.
- **Read-aloud test:** if the post would sound odd, over-crafted, or too polished coming out of Tom's mouth, rewrite it.
- **Anti-polish rule:** do not optimize for "good LinkedIn writing" over Tom's actual cadence. Tom sounding like Tom is more important than tidy rhetorical structure.
- **Stance-first rule:** start from a real opinion, irritation, conviction, or lived observation Tom would actually say out loud. Do not start by shaping a tidy LinkedIn argument.
- **Spoken-first scene rule:** for scheduled posts built from a calendar angle, first write a rough spoken version rooted in one concrete scene, exchange, client observation, or local conversation. Do not turn the calendar’s supporting points into a stacked list of rhetorical questions or a polished explainer. Shape it for LinkedIn only after the spoken version sounds like Tom.
- **Sharp observation rule:** prefer one sharp, true observation over a neat explanatory arc. If the draft feels broadly agreeable, smoothed out, or generic, it probably is not Tom enough yet.
- **Anti-thought-leadership rule:** do not smooth the idea into generic thought-leadership. Write from Tom's actual stance first, then shape it lightly.
- **Behavioral proof rule:** when Tom flags a specific AI-writing pattern (for example: writing in threes, polished essay cadence, generic scaffolding), the next draft must be checked against that exact pattern before it is shown to him. If the pattern is still obviously present, the draft fails and should be rewritten before sending.
- **Tom-voice over elegance rule (MANDATORY):** if forced to choose, prefer slightly rougher, more human, more specific copy over cleaner, more elegant wording. Tom sounding real matters more than the post sounding well-crafted.
- **No fake pass rule:** do not claim a style/voice fix worked just because the rule was added. The proof is in the new copy, not the file edit.

## Post Structure
1. **Hook** — first line must stop the scroll. Bold claim, provocative question, or surprising stat.
2. **Body** — 3–5 short paragraphs or punchy bullets. Build the argument.
3. **Landing** — practical takeaway or call to reflection. What should the reader *do* or *think* differently?
4. **CTA** — always present but never desperate. Point to stackstoneconsulting.co.uk (in first comment, NOT in post body).
5. **Hashtags** — 3–5, relevant, at the end of the post body

## Critical Rules
- **NEVER put links in the post body** — LinkedIn penalises reach. Links go in the FIRST COMMENT only.
- Always remind Tom to drop stackstoneconsulting.co.uk as the first comment immediately after posting
- No emojis unless Tom specifically asks
- Keep posts under ~1,300 characters for best reach (LinkedIn truncates at ~210 chars before "see more")
- Hook must be the very first line — no preamble
- **Published-post recording rule (MANDATORY):** when Tom says a LinkedIn post has been sent, posted, published, or gone live, update the canonical published-post tracker in `stackstone/linkedin-posts.md` first. Do not treat `TASKS.md` as the publication record.
- **Posted-content continuity rule (MANDATORY):** `stackstone/linkedin-posts.md` is the canonical anti-repeat tracker for what Tom has actually posted or intentionally queued. Before drafting, compare the proposed angle against that file and fail closed if the file is stale or ambiguous. If the live LinkedIn surface is later checked manually, reconcile any mismatch back into `stackstone/linkedin-posts.md` rather than treating memory/chat as the source of truth.
- **Fail-closed publication rule:** if the exact published-post tracker entry cannot yet be identified or updated safely, say the publication record is not yet complete rather than claiming it was "marked" somewhere else.
- **Trigger phrases:** "I sent the LinkedIn post", "posted this on LinkedIn", "mark as published", "update the LinkedIn tracker", or equivalent.

## Draft package completion gate (MANDATORY)
Before delivering any LinkedIn draft, verify that the package contains every item below:

- selected Tom-origin source and internal voice evidence;
- rough spoken version written before the LinkedIn version;
- final LinkedIn post copy;
- first comment with the website link;
- image prompt;
- any relevant status note, such as prepared, queued, published, or blocked.

If any item is missing, do not deliver the package or claim the draft is complete. The image prompt must be derived from the post's actual core observation or scene, not added as a generic branding afterthought. Run this checklist immediately before the user-facing response, even if the draft has already passed the voice and anti-repeat gates.

## Image
Every post must include an image prompt using Stackstone brand:

**Brand:**
- Colours: cream/off-white background (#F5F0E8 approx), dark charcoal text (#2A2A2A approx), amber/gold accent (#C8922A approx)
- Logo: stacked cairn stones icon + STACKSTONE wordmark (horizontal or stacked)
- Style: clean, minimal, typographic — no clutter, no stock photo clichés
- URL visible in image: stackstoneconsulting.co.uk

**Brand Assets (hosted URLs):**

| Asset | SVG | PNG |
|-------|-----|-----|
| Logo Full (light bg) | https://stackstoneconsulting.co.uk/brand/stackstone-logo-full.svg | https://stackstoneconsulting.co.uk/brand/stackstone-logo-full-800.png |
| Logo Dark (dark bg) | https://stackstoneconsulting.co.uk/brand/stackstone-logo-dark.svg | https://stackstoneconsulting.co.uk/brand/stackstone-logo-dark-800.png |
| Logo Horizontal | https://stackstoneconsulting.co.uk/brand/stackstone-logo-horizontal.svg | https://stackstoneconsulting.co.uk/brand/stackstone-logo-horizontal-800.png |
| Logo Stacked | https://stackstoneconsulting.co.uk/brand/stackstone-logo-stacked.svg | https://stackstoneconsulting.co.uk/brand/stackstone-logo-stacked-600.png |
| Icon (light bg) | https://stackstoneconsulting.co.uk/brand/stackstone-icon.svg | https://stackstoneconsulting.co.uk/brand/stackstone-icon-400.png |
| Icon (dark bg) | https://stackstoneconsulting.co.uk/brand/stackstone-icon-dark.svg | https://stackstoneconsulting.co.uk/brand/stackstone-icon-dark-400.png |
| LinkedIn Banner | — | https://stackstoneconsulting.co.uk/brand/stackstone-linkedin-banner.png |

Use PNG versions for image generation prompts. Use SVG for references only.

**Important — ChatGPT image generation:**
- ChatGPT/DALL-E cannot fetch URLs directly during image generation — it will use the description to recreate the logo
- Always include the logo URL in the prompt text anyway (for context and for tools that do support URL references)
- If Tom is using GPT-4o canvas or any tool that accepts reference images, he should **attach the PNG URL directly** as a reference image alongside the prompt:
  - Light background posts: https://stackstoneconsulting.co.uk/brand/stackstone-logo-horizontal-800.png
  - Dark background posts: https://stackstoneconsulting.co.uk/brand/stackstone-logo-dark-800.png
- Always remind Tom to attach the reference image when sharing the prompt

**Scroll-stop image rule (MANDATORY):**
- The only hard test is: **will this stop the scroll sufficiently?** Treat every visual as a testable hypothesis, not as a rule-compliance exercise. Actual post data and Tom’s feedback outrank aesthetic theory.
- The image should create curiosity or recognition; the caption can do the explaining. Do not default to an information-heavy “AI consultant” graphic simply because it is easy to describe.
- Choose the visual form that best serves the specific hook. Viable routes include: a simple eye-catching text header; a provocative image; a real photograph or Tom-origin asset; or a restrained branded graphic. There is no fixed template and no blanket ban on visual forms.
- In an AI-gumph-heavy feed, avoid imagery that looks predictably generated or generic **unless it is clearly the deliberate strongest scroll-stop choice for that post**.
- Before delivery, state the visual hypothesis in one sentence: what should make someone pause? After publication, record any meaningful available signals (impressions, dwell/comments, profile views, relevant replies/DMs) in `stackstone/linkedin-posts.md` so future choices learn from data.

**Image prompt format:**
> Propose the strongest visual treatment for this specific LinkedIn hook. State the scroll-stop hypothesis first, then give a concise generation/design prompt. Keep Stackstone branding present but secondary. Do not turn the image into a caption screenshot or explanatory slide unless that is the deliberate hypothesis being tested.

**Image headline clarity rule:**
The headline text must be **independently understandable** — someone who hasn't read the post should immediately get the idea.

**Test:** Would this headline make sense on its own, without the post context?
- ✅ GOOD: "When I learn it, my agents know it" — clear, standalone, demonstrates differentiation
- ✅ GOOD: "Zero handoffs. Zero delay." — clear pain point solved
- ❌ BAD: "The diffusion delay is the moat" — insider language, requires context
- ❌ BAD: "Tools are table stakes" — abstract, needs explanation

**Avoid:**
- Insider/technical jargon
- Abstract concepts without concrete reference
- Clever wordplay that obscures meaning

**Prefer:**
- Direct statements of advantage
- Clear pain points being solved
- Concrete, human language

## Output Format
Always deliver:
1. **POST COPY** (ready to paste into LinkedIn)
2. **FIRST COMMENT** (URL to paste as first comment immediately after publishing)
3. **IMAGE PROMPT** (for DALL-E or manual creation)
4. **REMINDER** to Tom: drop the first comment the moment the post goes live

## Maintaining backlog
When adding a new LinkedIn post idea to `memory/linkedin-ideas.md`, always include:
- a **saved timestamp** (`YYYY-MM-DD HH:MM` if known; otherwise at least the date)
- an **Origin** line stating where the idea came from
- enough summary/framing that the idea is reusable later without needing the original chat

Possible origin types include:
- brothers podcast / uploaded transcript
- Tom chat note
- client conversation
- interview prep
- article / video / briefing source
- lived observation from Tom's own work

If the origin is unknown or too vague to file honestly, ask once rather than inventing provenance.

## Transcript / podcast mining (MANDATORY when relevant)
When Tom shares a transcript, podcast, workshop recording, or long conversation that may be useful for LinkedIn, do not only look for full post ideas.
Also scan for **short spoken clip candidates** Tom could cut as video.

### What to look for
Look for short runs of language Tom says that have:
- a clean, sayable point
- natural spoken cadence
- a strong hook or turn of phrase
- enough standalone meaning to work out of context
- preferably one sharp idea rather than a broad explanation

### Avoid
Do not select lines that are:
- too long
- too dependent on surrounding context
- messy half-thoughts unless they can be lightly cleaned while staying true to Tom's voice
- generic filler or setup without a payoff

### Output pattern for clip mining
When mining a transcript for LinkedIn use, try to produce three buckets where possible:
1. **Post ideas** — concept-level LinkedIn posts
2. **Clip candidates** — short spoken lines/paragraphs that could work as video snippets
3. **Hook phrases** — compact turns of phrase Tom could reuse in future spoken/video content

For clip candidates, include a short note on why the line works on video (e.g. strong hook, challenge, contrast, memorable phrasing, good opening line).

### Transcript integrity gate (MANDATORY)
If Tom asks for ideas/clips/themes from a specific transcript or uploaded document, inspect the source content first.
Do not claim transcript-derived themes, clip candidates, or hook phrases from a file you have not actually read/extracted.
If the source file cannot yet be read, say so plainly and distinguish that from broader contextual inference.

## Example Topics
- AI strategy for mid-market businesses
- The data moat / commoditisation of AI models
- Practical AI implementation lessons
- Oxfordshire / UK business angles
- Commentary on AI news (Diamandis, Anthropic, OpenAI etc.) through a practitioner lens

## LinkedIn idea capture / backlog rule (MANDATORY)
When Tom shares LinkedIn post ideas, social copy, content themes, or a sequence to "capture" / "save" / "use later":
1. Treat `linkedin-post` as the governing content skill, even if `resource-intake` is also needed for durable source retention.
2. Preserve the full source in an appropriate durable file when the material is long or reusable.
3. Also add a concise backlink entry to `memory/linkedin-ideas.md` so future LinkedIn drafting finds it through the active content backlog, not only through generic resource search.
4. The backlog entry should include origin, stored source path, theme summary, and the strongest reusable lines.
5. Do not rely on a subagent/resource capture alone unless the subagent is explicitly instructed to update `memory/linkedin-ideas.md` as well.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
