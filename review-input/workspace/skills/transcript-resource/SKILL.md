---
name: transcript-resource
last_edited: 2026-06-10 15:35
description: Store shared transcripts and meeting notes in the canonical resource location, summarize them, and update affected CRM and SharePoint truth when required.
---

# Transcript Resource

Store long transcripts as reusable reference material.

## Supported inputs
- Raw pasted transcript text
- Long notes dumps
- Meeting/workshop/interview transcripts
- YouTube URLs

## YouTube rule
- If Tom sends a YouTube URL, use the native YouTube transcript capability when available in-session
- Do **not** create or rely on old custom Tavily/YouTube wrapper scripts if native tooling exists
- Accept short and long YouTube URL formats (`youtu.be/`, `youtube.com/watch?v=`, `shorts/`, `live/`, `embed/`, or bare video id when supported)
- After extracting the transcript, save it using the same transcript resource format below
- If native transcript capability is unavailable in the current session, say so plainly and ask Tom either to paste the transcript or enable the route

### User-specified routing override (MANDATORY)
If Tom explicitly asks for a **batch**, **cheaper**, **async**, or otherwise specifically constrained transcript route:
1. That routing instruction overrides the default native-fast path
2. Do **not** silently substitute the immediate/native route just because it exists
3. If the requested route is available, use it
4. If the requested route is **not** available in the current session/tooling, say that plainly **before** extracting anything and ask whether Tom wants:
   - the default fast/native path anyway, or
   - to wait for the cheaper/batch route
5. Never imply the requested route was used if it was not

## Automatic YouTube channel pipeline
- A background Pi integration now captures transcripts from configured YouTube channels every 30 minutes and writes them directly to `reference/transcripts/`
- Management commands live on **mgmt-bot** (`/yt-add`, `/yt-list`, `/yt-run`) — not in this session
- Before re-fetching a YouTube transcript manually, check whether it already exists in `reference/transcripts/`
- The pipeline writes the same canonical file structure used by this skill, so treat those files as normal transcript resources

## Storage location
- Save files under `reference/transcripts/`
- Filename format: `YYYY-MM-DD - <short-slug>.md`
- Prefer descriptive slugs: `aerotek-feedback`, `event-conversation`, `podcast-notes`, `sales-call-transcript`
- If multiple transcript files arrive on the same day for the same topic, append `-2`, `-3`, etc.

## File format
Use this structure:

```md
# <Title>
- Received: YYYY-MM-DD HH:MM Europe/London
- Source: Tom paste | Tom image | Tom forwarded transcript | other stated source
- Topic: <short topic>
- Status: resource

## Useful Summary
- 5-10 bullets max
- Focus on decisions, claims, objections, useful facts, follow-ups, frameworks, names, dates
- Strip filler and repetition

## Key Takeaways
- What is reusable later?
- What might affect Stackstone, sales, product, positioning, health, operations, etc.?

## Raw Transcript
<preserve the original transcript verbatim where practical>
```

## Rules
- **No-TOTP local-retention rule (MANDATORY):** For a general transcript whose canonical home is `reference/transcripts/`, use the direct workspace `read`/`write` file route. Do not invoke shell/exec merely to copy or assemble the uploaded source, and do not ask for TOTP for this local retention step.
- **Full-transcript SharePoint queue rule (MANDATORY):** When classification confirms a live CRM/SharePoint entity, write one `create` queue item directly to `~/.openclaw/sharepoint-queue.json` with the entity artifact `path`, a unique `id`, `requested_at`, and `content` containing the complete Markdown artifact—including the source body verbatim under `## Raw Transcript`. Never create a summary-only queue item, never shell-copy the source, and never request TOTP. Verify `SHAREPOINT_RESULT.md` reports the same queue ID as `success: true` before calling the SharePoint filing complete.
- Keep the summary useful, not decorative
- Preserve the raw transcript below the summary unless Tom explicitly asks for summary-only
- Include dates/times exactly as stated in the source when available
- If the transcript contains action items for Tom, call them out explicitly in the summary
- If the transcript contains business strategy or positioning insight, say why it matters
- Do not overwrite an existing resource file unless Tom explicitly asks for replacement
- **Full-transcript retention rule (MANDATORY):** If Tom shares a transcript and wants it kept, preserve the **full original transcript verbatim** in the canonical stored artifact. Do not replace it with compressed notes.
- **Summary-is-secondary rule:** summaries, extracted notes, CRM updates, and SharePoint Current updates are helpful secondary layers, but they never count as transcript retention on their own.
- **Tom-next-actions rule (MANDATORY):** when Tom shares a transcript/resource for retention or use, return an explicit short `Tom next actions` list based on the source. Do not stop at storage/summary alone if the transcript implies concrete follow-up work.
- **Task-curation rule (MANDATORY):** treat `Tom next actions` as proposed actions, not automatically accepted tracked tasks. If the transcript/resource suggests concrete follow-up work, ask Tom whether he wants any/all of those actions added to `TASKS.md` or the task system before writing them into tracked-task machinery.
- **Fail-closed task-capture rule:** do not add transcript-derived actions to `TASKS.md`, task trackers, or future task-system records unless Tom explicitly approves that capture, either generally for that transcript or item-by-item.
- **CRM / opportunity rule:** If the transcript is specific to a live account/opportunity (client call, prospect meeting, investor context, sales discussion), default to storing it against the CRM / SharePoint entity instead of generic `reference/transcripts/`, unless Tom explicitly wants it as a general reusable reference
- **Upload-preservation rule (MANDATORY):** When Tom uploads or shares a transcript/resource and it is being retained, do not collapse it into only a summary layer or CRM note. Preserve the full original transcript/body in the stored artifact, then add the summary above it.
- **SharePoint transcript rule (MANDATORY):** If the transcript/resource belongs to a live CRM account, opportunity, partnership, or other business entity with a SharePoint home, the retention target is the entity's SharePoint context first. A local CRM summary may point to it, but does not replace storing the full transcript/resource in the entity artifact set.
- **Raw-first SharePoint rule (MANDATORY):** When Tom shares a transcript that is being retained to a SharePoint-backed business entity, save the **full raw transcript verbatim** into the SharePoint artifact itself. Do not save only a partial excerpt, teaser section, cleaned fragment, or summary-plus-note placeholder.
- **No-placeholder completion rule (MANDATORY):** A SharePoint transcript artifact does not count as complete if it says the transcript continues elsewhere, says the rest can be regenerated later, or substitutes commentary for omitted sections. Completion requires the full original transcript body in SharePoint unless Tom explicitly asks for a summary-only or redacted artifact.
- **Fail-closed rule for retained transcripts:** Do not imply a transcript has been properly stored if only the summary/CRM layer was updated. If the full transcript has not yet been preserved in its retention home, say that plainly.
- **SharePoint write-surface rule (MANDATORY):** For a transcript owned by a live CRM entity, use the standard SharePoint queue write surface (`~/.openclaw/sharepoint-queue.json`) directly to create the complete verbatim artifact and update `Current.md`. This is the same asynchronous, no-TOTP write path used for SharePoint filing and housekeeping. Do not misclassify a separate local-command or protected-route limitation as a SharePoint-queue blocker; queue the complete artifact, then verify `SHAREPOINT_RESULT.md`/cache before claiming completion.
- **No-clearing-pending rule (MANDATORY):** Once a complete transcript write is queued, preserve it until the SharePoint processor has returned a verified success or failure. Never clear a pending queue entry merely because a separate local tool is gated. If the full artifact cannot be assembled safely, do not queue a placeholder; retain the source and state the exact assembly blocker.

## Enforcement trigger
Before replying after any user-uploaded transcript, pasted transcript, forwarded meeting notes, or long structured resource:
1. Decide whether this is being retained
2. If yes, decide whether it belongs in general transcripts or a CRM/SharePoint entity
3. Confirm the artifact will contain the full original content, not just a summary
4. Only then describe it as saved/stored

## Explicit transcript-request precedence rule (MANDATORY)
If Tom explicitly calls something a transcript, says to use the transcript skill, or asks for transcript processing/storage/review, this skill becomes the governing workflow first even if CRM, SharePoint, or other downstream systems are also implicated.

Required order:
1. Run transcript classification/retention first
2. Preserve the full transcript artifact in its correct home
3. Then update CRM / SharePoint current truth or other downstream systems
4. Do not substitute a CRM-summary-only pass for transcript handling

Fail-closed rule:
- If the full transcript artifact has not been retained yet, do not say the transcript was properly processed
- You may say CRM/SharePoint summary capture is partial, but not that transcript handling is complete
## Classification gate (MANDATORY before filing)
Before storing any pasted transcript/notes, explicitly determine:
1. **Who is this about?** (person + company)
2. **What date is it from?**
3. **Is this tied to a live account/opportunity, or is it a general reusable reference?**
4. **What existing folder/file should this attach to?**

**Filename/date clue rule (MANDATORY):**
- Treat the incoming filename as a useful clue, especially for the likely date/time of the transcript
- But do **not** trust the filename alone when deciding the canonical date, entity, or storage home
- Check the transcript content, adjacent metadata, or surrounding context to confirm when it happened and who/what it belongs to
- **Calendar corroboration rule (MANDATORY):** before filing any meeting transcript, read the relevant calendar source and look for a matching event using the filename date/time, named people/company, and meeting topic. Treat a matching calendar event as corroboration for the date, entity and meeting type—not as a substitute for the transcript’s own evidence.
- If the filename, calendar, and transcript conflict or the calendar has no credible match, do not guess. File only to the level supported by the transcript and explicitly mark the calendar linkage `coverage incomplete` (or ask Tom if the canonical date/entity remains material to filing).

**If any of those are uncertain, stop and ask Tom before filing.**

**Batch-review exception (MANDATORY):**
- If Tom explicitly asks for a review/organise pass across transcripts and says uncertain cases should be surfaced later, do not guess the filing
- File only the transcripts whose owner/date/home are materially clear after checking both filename clues and transcript content
- Collect the ambiguous items into a concise follow-up list for Tom's next review window (for example, the morning standup/check-in) with the specific uncertainty called out
- In that mode, uncertainty should be flagged for Tom rather than silently misfiled

**Do NOT classify by theme similarity alone.**
- "This sounds like another AI conversation" is not enough
- Similar topics across different people/companies must stay separated

**Rule of precedence:**
- Confirmed named entity + confirmed/most-supported date > filename hint alone > thematic similarity
- Existing CRM/SharePoint entity context > generic reference filing

## Owning-system completion rule (MANDATORY)
If the transcript/resource materially changes the truth of a live business/client/project system, do not stop at storage + summary.
Complete the owning-system update in the same pass when evidence and access are sufficient.

**CRM + SharePoint Current rule (MANDATORY):**
- If the transcript belongs to a live account, opportunity, partnership, client, prospect, or project with business-system state, update both layers as part of the same workflow unless Tom explicitly says not to:
  1. the local CRM truth layer / account summary / pipeline state
  2. the entity's SharePoint `Current.md` (or equivalent current-truth file)
- Treat transcript retention, CRM update, and SharePoint `Current.md` maintenance as one connected completion chain, not optional extras
- If the transcript changes understanding but not stage, still update `Current.md` with the new facts, meeting outcome, risks, commitments, or next step
- If one downstream layer cannot yet be updated, say exactly which layer is still outstanding; do not describe the whole transcript workflow as complete

Examples:
- client/prospect meeting transcript -> store the full artifact in the correct entity home, then update CRM and SharePoint `Current.md` if the transcript materially changes status, next step, or understanding
- operational transcript -> create/update the relevant task/plan/reference state if concrete actions are implied
- general reusable transcript -> retain it durably with full original content and summary/proof path

## Proof rule (MANDATORY)
If this skill performs meaningful transcript/resource retention or downstream truth maintenance, leave a reviewable proof path via one or more of:
- stored artifact path
- CRM update target/path
- SharePoint `Current.md` update target/path
- confirmation source/result when the write path is queued or async
- `reference/OPERATIONAL_ACTIVITY_LOG.md`
- `memory/monitored-items-state.json` when the source came from a monitored inbound surface

## Morning exceptions rule (MANDATORY for deferred batch review)
If Tom has asked for a review/organise batch where uncertain transcript filing should be deferred rather than blocking the pass:
1. maintain a concise exceptions list of ambiguous transcripts/items
2. for each item, record the likely entity/date/home plus the exact uncertainty
3. include downstream truth gaps too when discovered during filing, for example:
   - transcript retained but CRM not yet updated
   - CRM updated but SharePoint `Current.md` not yet updated
   - entity has artifacts but no usable `Current.md`
4. surface that list at the next agreed review window rather than silently leaving the ambiguity buried

## Ambiguity / ask-Tom rule (MANDATORY)
If you are not materially certain who the transcript is about, what entity owns it, whether it is reusable vs entity-specific, or what downstream system should be updated, ask Tom a short clarification question instead of guessing.

## Optional extra steps
When helpful:
- Add a brief pointer into a relevant business file (`TASKS.md`, `stackstone/crm.md`, SharePoint note, etc.)
- Mention the new file path in chat
- If the transcript changes an ongoing process, update the governing skill/file

## Model routing pattern (MANDATORY)
Use the `local-llm` route for rough internal summarisation, first-pass extraction, topic detection, or draft structuring **only when** the work can be kept to one small working slice at a time.
Small slice = one short excerpt, one section, or one clean chunk that can stand alone.
Use the stronger cloud route for final summaries, filing/classification decisions, and anything entity/date-sensitive, accuracy-sensitive, or dependent on the whole transcript.
Do not use the local route for whole transcripts, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Trigger examples
- "Save this transcript"
- "Store this as a resource file"
- "Here's a workshop transcript"
- "Take notes from this and keep it for later"
- "You'll be getting more of these — create a summary and save them"

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
