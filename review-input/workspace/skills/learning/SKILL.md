---
name: learning
description: How to convert feedback into persistent behavioral change. Use when Tom says "learn from this", "core fix", or "what will you do differently?"
last_edited: 2026-06-10 08:34
---

# Learning

This skill defines HOW to learn, not WHAT was learned. Lessons go into the relevant skill files as concrete rules.

---

## When Tom corrects you

**Trigger:** Any correction from Tom — explicit ("learn from this") or implicit (pointing out a mistake, asking why something didn't happen, questioning a decision).

**Rule:** Treat every correction as a potential learning trigger, but do not assume every live discussion, refinement, or collaborative steering comment needs the full learning ceremony.

If Tom:
- Explicitly says "learn from this", "this is one to learn", "what will you do differently?", or equivalent
- Identifies a recurring/repeat failure or process-pattern problem that should persistently change behavior
- Explicitly challenges whether I used the learning skill properly

→ **Run this learning process.**

If Tom is:
- collaborating live on the shape of work
- refining a plan or design in conversation
- correcting a detail in normal back-and-forth
- steering scope or priority without asking for a durable behavioral change
- clarifying something he may not have articulated perfectly earlier
- adding nuance or better framing to help me understand the operating model

→ **Do the operational change directly without invoking the full learning ceremony**, unless it clearly rises into a repeat/process-level lesson.

**Explicit invocation rule:** If Tom explicitly says "learn from this" or "use the learning skill", do not compress this into a generic acknowledgement. Run the process in order and state steps 1-7 concisely before implementation/confirmation.

**Visible-skill-execution rule (MANDATORY):** When the learning skill is triggered, the reply itself must make it obvious that the skill is being used. Do not reply with a normal conversational answer, a generic apology, or a plain status update first. The response must explicitly walk through the learning steps (root cause, needed change, governing file, trigger, output type, sources/mechanism) before implementation.

**Direct-instruction obedience rule:** If Tom explicitly tells you to run a named skill/process, obey that instruction literally before improvising, summarising, or editing any task-specific file. Do not substitute your own shortcut for the requested process.

**No-prelude rule (MANDATORY):** If the triggered skill is `learning`, do not insert a prelude question, meta-comment, or ordinary reply in place of the skill unless the skill itself explicitly requires clarification first and that clarification is still genuinely unresolved. If Tom says the skill was not used, assume the clarification is resolved enough to execute it now.

**End-to-end skill invocation rule:** When a trigger indicates that a skill/process applies, run that skill fully as the governing workflow rather than partially borrowing from it or replacing it with an improvised conversational shortcut. The layered context is there so you can identify the correct skill at the correct moment; once triggered, the job is to execute the whole process end to end so nothing gets dropped.

**Skill-discovery-before-compression rule:** If you have not explicitly identified the governing skill/process yet, you are not allowed to shorten, relabel, paraphrase, or "just answer naturally" for an operational artifact. First find the skill that owns the job. Only after the governing skill is found and run may you decide whether any compression is allowed by that skill or by Tom's explicit request.

**Multi-part instruction rule:** If Tom gives a sequenced instruction like "learn from this too, then learn from the original issue", preserve the sequence and complete each requested learning pass separately. Do not collapse multiple requested learning runs into one blended summary.

**Return-to-original-learning rule (MANDATORY):** If a second-order failure happens while handling a learning step (for example: I mishandle the learning process itself), I must not stop after patching the learning process. After completing the meta-learning fix, I must explicitly return to the original learning and complete that pass too, unless Tom reprioritises.

### Process:
1. **Identify the root cause** - why did this actually fail?
2. **Identify what needs to change** - what specific behavior/process/rule would prevent this?
3. **Check `SYSTEM_MAP.md`** - every learning process must review the map before deciding where the fix belongs; do not guess
4. **Find the governing process/file** - use `SYSTEM_MAP.md` to identify the right governing skill/file
   - **Mandatory placement test:** decide which home the lesson belongs in before editing:
     1. **`AGENTS.md`** only if the fix must be always-on session governance/pre-reply behavior across all workstreams
     2. **`skills/learning/SKILL.md`** only if the failure is about how the learning process itself works (e.g. wrong lesson placement, wrong learning sequence, weak learning enforcement)
     3. **Domain skill/process file** if the failure is specific to one operating area (CRM, email, SharePoint, invoicing, app build, etc.)
     4. **`SYSTEM_MAP.md`** in addition, if the lesson changes routing, lookup expectations, or where future agents should look
     5. **Memory/backlog/task files are not governance homes** unless the lesson is purely factual tracking rather than a behavior/process change
   - Before editing, state to yourself: "Why does this lesson belong in this file rather than the other likely homes?"
   - **Home-validation gate (MANDATORY):** a plausible file location is not enough. Before editing, prove the selected home is on the live enforcement path: identify the file's owner, the exact trigger that reads/invokes it, the immediate upstream handoff, and the downstream state/output it controls. Run this counterfactual: "If the original failure happened again, would this file definitely be read at the moment the behavior needs to change?" If the answer is uncertain, do not edit; trace the runtime path further, choose the actual enforcement home, or mark placement unverified. For cross-layer workflows, test the handoff boundary explicitly rather than placing the rule in the nearest reporting or presentation layer.
5. **Define the trigger/initiator** - what exact event, condition, or review step should cause the new behavior to happen next time?
6. **Classify the output type** - is this:
   - **advisory / approximate** (some uncertainty acceptable), or
   - **high-integrity operational output** (lists, sends, routing/status claims, anything where partial correctness is not acceptable)
   If high-integrity, the fix must include a verification/fail-closed mechanism.
7. **Identify the source(s) of truth** - what records/files are definitive for this task right now? If there are multiple layers (e.g. CRM summary vs verified SharePoint vs sent register), name which one is primary and how discrepancies should be handled.
8. **Run the mechanism test (MANDATORY — blocks implementation):**
   
   Answer ALL three questions before proceeding:
   
   **a) What exact operational change will happen?**
   - What file will I read?
   - What check will I run?
   - What pattern will I match?
   - What trigger will fire it?
   
   If you can't answer in one concrete sentence, the mechanism doesn't exist yet.
   
   **b) Would this mechanism have caught the original failure?**
   - Walk through the failure scenario with the new mechanism
   - If the answer is "maybe" or "I think so", it's not strong enough
   
   **c) Is this mechanism sustainable?**
   - Can I afford to run this check every time the trigger fires?
   - Will I skip it because it's too expensive/slow/complex?
   - If yes to skipping, find a cheaper mechanism
   
   **If ANY answer is weak:** Go back to step 2 — the fix isn't concrete enough yet.
   
   Example GOOD mechanism: "Before forwarding cron inbox results, I'll read WHATSAPP_RECENT.md and verify the sender field matches the cron's attribution by searching for the quoted text."
   
   Example BAD mechanism: "I'll verify attributions better" or "I'll check the source" or "The rule says to verify"

9. **Propose the change** - "I'll add [this rule with THIS MECHANISM] to [that file] to prevent [the failure]"
10. **Implement immediately** - make the change unless Tom says not to
11. **Carry out the test after implementation** - actually execute the stated test/mechanism against the change you just made; do not merely say the test would pass
   - If immediate testing is possible and appropriate, do it before claiming pass
   - If immediate testing is not possible or not appropriate, do **not** claim pass; mark the change as **implemented, pending real-world test** and state what the next real trigger/test will be
12. **Update `SYSTEM_MAP.md` if needed** - if the learning changes routing, structure, important reference files, or where an agent should look next time, patch the map too
13. **Confirm** - tell Tom what changed and whether the post-change test passed, failed, or is pending real-world test

**Execution-order rule (mandatory):** When the learning skill is triggered, complete steps 1-8 explicitly before making any file edits. Do not jump straight from correction to implementation. The concrete mechanism must pass all three mechanism-test questions before step 9.

**Full-run checkpoint (MANDATORY):** Before editing any file, claiming that learning has been done, or sending the final response for a learning-triggered turn, check the actual draft/current reply against the process. If steps 1-8 are not visibly and explicitly covered, stop and complete them first. Reading this skill, summarising the issue, or making the operational fix does **not** count as running the learning skill. The learning pass is incomplete until the response itself shows root cause, needed change, SYSTEM_MAP check, governing file, trigger, output type, sources of truth, and the three-part mechanism test.

**Declared-route adherence gate (MANDATORY):** When a governing skill names a supported execution route (tool, queue, API, or file-first operation), use that route exactly. Do not substitute a familiar shell/exec path or claim a route is unavailable without first checking the named route.

**Route-discovery before fallback:** resolve the named route down to its real invocation contract before trying anything else: exact tool/queue/API identifier; required input keys; runtime consumer; and destination read-back proof. If a skill says `publish_skill`, for example, inspect the queue/processor contract and use its actual field names rather than guessing. A failed unrelated command, a document that merely mentions the route, or an unknown queue path is **not** a route test. Discovery remains incomplete until the exact route is attempted or its actual contract is proven missing.

Before any operational completion claim, state a compact skill receipt: exact skill read this turn; its designated route; resolved invocation contract; required checks/proof completed; and any remaining gap. If any field is absent, use only `prepared`, `partial`, `blocked`, or `coverage incomplete`—never `done`/equivalent. This is a soft fail-closed guard pending runtime enforcement.

**Skill-audit answer rule (MANDATORY):** If Tom asks whether I actually ran the learning skill or says I did not run it properly, I must answer that challenge with an explicit pass/fail statement first, then visibly run the learning steps in the same reply before claiming compliance. I must not imply the skill was properly run just because I made some related operational fixes.

**Overfire guardrail:** Before invoking the full learning ceremony, ask: "Is Tom asking for a durable behavioral/process change, or are we just working the problem together right now?" If it is ordinary collaborative steering, make the operational change directly and skip the ceremony.

**Clarification-vs-learning guardrail:** If Tom is mainly clarifying intent, adding nuance, or improving how he expressed something earlier, do **not** default to "this means I failed and need the learning skill." Treat clarification as collaborative guidance unless Tom is explicitly turning it into a durable lesson.

### CRITICAL RULES:

**Intent-before-implementation rule:**
- Before implementing Tom's request, identify whether he is asking for:
  1. a literal surface action, or
  2. a broader outcome/problem to be solved.
- If the broader intent is reasonably inferable, solve for that outcome rather than stopping at the surface instruction.
- If the intended outcome is not clear enough, ask a short clarifying question before building the wrong mechanism.
- Do not mistake "I updated the rule/file" for "I solved the user's actual problem."

**Generalize-the-lesson rule (MANDATORY):**
- Do not learn at the level of the anecdote if a broader repeatable failure explains it better.
- Prefer the most general behavior/process failure that would have prevented this class of mistake across other domains, not just the specific object involved.
- Before editing any file, state the candidate general lesson in one sentence.
- If that sentence still contains case-specific nouns (client/company/run/reminder/tool name) and the failure could happen elsewhere, keep abstracting.
- Only keep case-specific detail when the mechanism truly depends on that exact system/object.
- When choosing the "heart of the problem", prefer the user's intended outcome over the surface object involved. Example: if the visible object is a signature but the user actually wanted exact visual fidelity (formatting/font/colour/layout), the lesson must be framed at the fidelity/intent level, not the signature level.
- Ask explicitly: "What was the user trying to preserve or achieve here?" If the answer is broader than the named artifact, learn at that broader level.

**Whole-action completion rule (MANDATORY):**
- When Tom asks for an action, treat completion as the entirety of the requested outcome, not just the most visible sub-step.
- Convert the request into a completion checklist before acting.
- Ask: what would Tom reasonably assume is included if I say this is done?
- If any part of that implied bundle is unclear, play back the intended action briefly and get clarity before continuing.
- Do not leave background machinery (reminders, queued follow-ups, watches, side effects, or dependent runtime paths) running if stopping/closing them is part of the requested outcome.

**Root-cause depth rule:**
- Do not stop at the first plausible lesson.
- When Tom says "learn from this", ask yourself at least twice: "what sits underneath that?"
- Separate:
  1. the visible mistake,
  2. the process failure that allowed it,
  3. the deeper behavioural/governance failure underneath the process issue.
- Prefer the deepest correctable cause over the most obvious surface description.
- If Tom keeps having to refine the lesson for you, assume you are still describing symptoms rather than the heart of the problem.

**Useful-agent test (mandatory before claiming success):**
Ask yourself:
1. What problem is Tom actually trying to solve?
2. Am I only implementing the literal request?
3. What mechanism will make the desired outcome real in practice?
4. If Tom saw the result, would he say "yes, that solves it" or "you followed the words but missed the point"?
5. Am I describing the mistake, or the thing upstream that caused me to make that mistake repeatedly?
If you cannot answer those well, the work is incomplete.

**End-to-end fix rule:**
- When Tom asks you to "fix" something, assume he means the whole chain unless he explicitly narrows scope.
- Do not stop at patching one layer (for example: a skill file) if the live runtime path also depends on cron definitions, trigger wiring, delivery path, or a state file.
- Before claiming a fix is done, check the full chain:
  1. governing skill/process
  2. trigger/invocation path
  3. runtime/state layer
  4. delivery/output behaviour
- If any part is still unverified or unfixed, say exactly what remains instead of implying completion.

**Cross-day continuity rule:**
- When Tom identifies a concrete strategic route (for example a named campaign, offer, landing page, or outreach build) as the way to solve a bigger problem, do not let it dissolve back into generic wording on the next day.
- Convert it into a durable steering object in the system (weekly big thing, plan item, task, campaign name, or equivalent) so future standups can keep pointing at the same concrete route.
- Ask yourself: "If we restart tomorrow, what durable artifact will cause me to keep pushing the same real solution rather than rediscovering the problem from scratch?"

**Focus-preservation rule:**
- When Tom says he needs focus / pipeline / momentum / new business, prefer the most concrete already-defined path over inventing fresh optional work.
- Existing named machinery (e.g. Campaign C4) should outrank generic suggestions like "do some biz-dev" unless there is a stronger urgent override.

**Every lesson MUST:**
- Result in a useful change somewhere (file modification, new rule, process update)
- Amend something solid: a governing file, skill file, active process file, or `SYSTEM_MAP.md` when routing/structure is affected
- Define what will trigger the corrected behavior next time
- Pass the repeat-failure test: if the same thing would still plausibly happen, the lesson is incomplete
- Stop the behavior that happened from happening again
- Not be a log, not be documentation - be an active prevention
- Include the sentence: **"The heart of the problem was..."** so the lesson is forced to name the deepest cause, not just the symptom.
- **Learning-skill execution rule:** when Tom says a variation of "learn from this", "what will you do differently?", or explicitly challenges whether you used the learning skill, you must fully execute this skill's process. Do not merely answer in the style of a lesson; make the required governing-file/process change and say what changed.
- **Completion-integrity rule:** do not claim "done", "implemented", or equivalent full-completion language if any required mechanism is still only proposed, partially embedded, or not yet wired. In that case, explicitly separate:
  1. what is already changed,
  2. what is not yet mechanized,
  3. what would be needed for full completion.
- **Mechanism-before-claim rule:** before saying a fix is complete, state the concrete firing/enforcement mechanism to yourself. If you cannot point to the exact trigger/path that now makes the behavior happen, the work is not fully done.
- **Bundled-work return rule:** if Tom gives a bundled instruction and later corrects me while some requested items are still outstanding, I must not switch into explanation/progress-report mode and stop there. After the learning step, I must return to the original checklist, mark each item done/blocked/not started, and continue the unfinished work unless Tom explicitly pauses or reprioritises it.

**If you identify a process failure:**
- update the governing process/policy file immediately
- update `SYSTEM_MAP.md` too if the fix changes where agents should look or how the structure is understood
- not just acknowledge it in chat

**Test:** If this exact situation happens again, will this change prevent the same failure? If no, it's not the right change.

**When something is unclear:**
- Get clarity from Tom BEFORE running ahead
- Don't burn tokens iterating on a guess
- One clarifying question costs less than 5 wrong attempts
- **Special case — correction about the learning process itself:** if Tom says a learning step was run wrongly, do NOT immediately explain the root cause, propose a fix, or patch some other skill. First ask what I fundamentally misunderstood, then update `skills/learning/SKILL.md` itself once the failure is clear.

### Quality test (all must be YES):
- Can another agent read this rule and follow it?
- Does it change behavior, not just awareness?
- Is it specific enough to test whether I'm following it?
- Did it go into the right skill file, not a generic log?

---

## NOT acceptable:

❌ **Platitudes:**
- "I'll think harder next time"
- "I'll be more careful"
- "I'll pay more attention"
- "I'll consider X better"

❌ **Generic logs:**
- Creating LEARNING.md with lessons
- Adding to a "lessons learned" list
- Documenting without changing process

❌ **Vague commitments:**
- "I should X" without defining how
- "Next time I'll Y" without a trigger/rule
- Understanding the problem without changing behavior

---

## Acceptable:

✅ **Concrete rules in relevant files:**
- "After 2nd correction on same work, stop and ask what I'm misunderstanding" → crm-sharepoint/SKILL.md
- "When hit a blocker, finish all finishable parts first, then report blockers" → crm-sharepoint/SKILL.md
- "BACKLOG.md = code, TASKS.md = admin, always timestamp" → crm-sharepoint/SKILL.md

✅ **Process changes:**
- Update workflow section in skill file
- Add new safety rule
- Change trigger conditions
- Add quality checklist

---

## When Tom corrects you 2+ times on the same work:

**Stop iterating.** Your frame is probably wrong, not your execution.

**Ask:** "What am I fundamentally misunderstanding about what you need?"

**Don't:** Make another tweak and hope it's right this time.

**If the repeated correction is about HOW you are running the learning step:**
- Do not treat your own guess about the failure as established fact
- Do not patch the task-specific skill first
- Ask the misunderstanding question first
- Then patch `skills/learning/SKILL.md` with the concrete prevention rule

---

## Where lessons go:

| Type of lesson | Goes in |
|---------------|---------|
| CRM/SharePoint organization | `skills/crm-sharepoint/SKILL.md` |
| Email/inbox handling | `skills/email-check/SKILL.md` |
| Task/backlog management | relevant governing file/skill |
| General session behavior | relevant governing skill/process (do not dump into `AGENTS.md`) |
| Tool-specific | That tool's skill file |

**Never:** Create a separate lessons log. Lessons are active process changes, not historical records.

**If unsure where a lesson belongs:** check `SYSTEM_MAP.md` first, then patch the governing file it points to. `AGENTS.md` is for session bootstrap only, not a fallback home for stray lessons.

---

## Example (good):

**Tom:** "Learn from this - you keep repeating yourself"

**Bad response:** "I've learned to avoid repetition" → platitude, nothing changes

**Good response:**
1. Root cause: No rule about when to stop talking after confirming
2. What needs to change: Add a stop condition to communication rules
3. Proposed: "I'll add 'Once confirmed, stop - no second summary unless new info' to AGENTS.md § Formatting to prevent duplicate confirmations"
4. [Immediately update AGENTS.md]
5. Confirm: "Updated AGENTS.md - added stop-after-confirmation rule"

**Test:** Next time I confirm something, will this rule stop me from repeating? Yes → good change.

---

### Example abstraction test

**Bad lesson:** "If Tom says stop telling me about B&Q/Waitrose, delete that reminder cron."

**Better lesson:** "When Tom asks me to do/stop something, I must account for the whole action and shut down any dependent machinery that would otherwise keep producing the thing he asked to stop."

Why better:
- works beyond one company/run/reminder
- addresses the completion failure rather than the anecdote
- creates a reusable check across reminders, watchers, queued sends, sub-agents, and follow-up tasks

_This skill defines the learning process. Actual lessons live in their relevant skill files._

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
