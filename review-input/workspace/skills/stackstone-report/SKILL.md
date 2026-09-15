---
name: stackstone-report
description: Produce client-facing Stackstone discovery, options, or proposal reports after discussing the problem, comparing trade-offs, and agreeing the consultative direction.
---

# Stackstone Consulting — Client Report Generation

## Critical: Process Before Output

**Never rush to produce a document.** The most important part of this skill is the conversation that happens before any writing. The report is the artefact of thinking, not a substitute for it.

The process follows this sequence every time:

1. **Load context** — Read all project files, transcripts, source documents. Understand the client's world thoroughly.
2. **Work the problem** — Discuss with Tom what the actual problem is. Not the technical description — the real problem the client is experiencing.
3. **Explore options** — Talk through the solution space, trade-offs, and how to present choices to the client.
4. **Agree structure** — Confirm what sections the report needs, what framing to use, how to handle unknowns.
5. **Draft** — Only now produce the document.
6. **Iterate** — Review with Tom, adjust tone, fix framing, correct estimates.

If you find yourself generating a document before step 4, stop and go back.

## Report Philosophy

Stackstone reports are designed to be acted on. Every section should either:
- Present a finding the client needs to know
- Present an option with enough detail to make a decision
- State clearly who does what
- Identify what can be done independently vs what needs external support

The tone is direct, honest, and consultative. We don't oversell. We don't hide uncertainty behind jargon. If we don't know something, we say so. If a solution might not work, we say that too.

## Standard Report Structure

Not every report uses every section. Use what fits. But the following is the proven structure from Stackstone engagements:

### Summary / Overview (always include)
One to two pages maximum. A busy client should be able to read this section alone and understand the full picture: the problem, the recommendation, and what happens next. Write this last even though it appears first.

### Context
Who the client is, what their situation is, what led to this engagement. Brief — the client knows their own context, this is for the record.

### The Problem
Frame the actual problem, not just the symptoms. This is the section where the client should think "yes, that's exactly it." Go beyond the technical description to the human impact — time lost, frustration, risk, opportunity cost.

### Current State
What we observed. How things work today. Data flows, tools, processes. Detailed enough to demonstrate we understood it, but not so detailed it reads like a technical audit. Avoid using specific client names, account numbers, or financial figures from their data — describe in general terms and themes.

### Vision (when applicable)
Where we believe this could go. Not what we're building tomorrow — where the trajectory leads if the client continues investing. This reframes the immediate work from a tactical fix to a strategic investment. Use "could" not "will" — the vision belongs to the client, not to us.

### Options / Solution Continuum
Present options as a continuum or spectrum where possible, not as isolated choices. Thread trade-off factors through so the client can see the implications of each position. Common factors to consider:
- Accuracy and trust
- Maintenance burden
- Security and hosting
- What happens when something changes
- Cost profile (one-off vs ongoing)
- Client's ability to run and maintain it
- What happens if Stackstone isn't available
- Scalability

Present this as a discussion point. Be honest about what we don't know and what the proof of concept will reveal.

### Work Items and Phasing
Use **MoSCoW by phase**. Every identified opportunity goes in the table — the client needs to see we heard everything. But MoSCoW classifications shift between phases:
- A COULD in Phase 1 might become a SHOULD in Phase 2 and a MUST in Phase 3
- Dependencies build naturally — e.g. AI-assisted drafting needs transcript integration first

Each phase must stand alone as a deliverable with its own value. The client can stop at any point. No lock-in.

### Return on Investment
Frame ROI in the currency the client used during the session. If they talked in hours, use hours. If they talked in money, use money. If they talked in headcount avoided, use that. Make it concrete and specific to their situation.

Where we need data from the client to complete this section, use red placeholder text (see below).

### Risks and Mitigations
Honest assessment. Include "unknown" as a likelihood where appropriate. The proof of concept should be positioned as the thing that answers key uncertainties rather than pretending we know everything upfront.

### Engagement Scope
What has been delivered (this report). What Phase 1 includes. How subsequent phases are scoped. Stackstone's range-based pricing model. Actions the client can take independently without external support.

### Next Steps
Table format. Action, owner, timing. Include responding to outstanding questions as an action.

## Estimating Effort

Stackstone always quotes a range:
- **Low end**: straight through, no issues hit
- **High end**: risk-based, accounts for unknowns

Factor in that vibe coding with AI tools makes many implementation tasks significantly faster than traditional development. The complex parts are typically integration, authentication, and dealing with third-party system constraints — not the coding itself.

Be explicit about what drives the range — e.g. "the low end assumes the PDF structure is consistent; the high end accounts for format variations we haven't seen yet."

## Outstanding Questions

When the report needs data from the client to be complete, use **bold red text in square brackets** at the point in the document where the answer would be used. The client sees exactly why we're asking.

Example: `[Andy — could you remind me how many client reports you produce per year?]`

These should be phrased warmly and specifically. Explain briefly why we need the answer at that point in the document. Also collect the questions into a follow-up email (see below).

## Follow-Up Email

After producing the report, draft a short email to the client asking the outstanding questions. The email should:
- Be warm and brief
- Reference the session positively
- List the questions with a one-line explanation of why each matters
- Not create urgency — "whenever you get a moment this week"

## Formatting and Branding

Use `~/.openclaw/workspace/skills/stackstone-branding/SKILL.md` as the exact Stackstone house style source of truth — colours, typography, cover page layout, header/footer format, table styling, and docx-js implementation patterns. The branding must match exactly.

The report is generated as a .docx using the `docx` npm package (docx-js). Use the branding skill's implementation patterns rather than ad hoc styling.

## Example: The Full Consultative Process

See the complete worked example in:
- `example-conversation-andy-barrett.md` (Part 1)
- `example-conversation-part2.md` (Part 2)

These two files form **one continuous example** showing the full arc from initial request through to final report delivery. They demonstrate:
- Deep dive before questions
- Resetting after premature output
- Working the problem collaboratively  
- Exploring solution continuum and trade-offs
- Vision emerging through dialogue
- MoSCoW phasing with independent ROI
- Realistic estimation with risk-based pricing

Read both parts together to see the complete consultative process.

## What To Read Before Starting

Before generating any report:
1. Read this SKILL.md (you're doing that now)
2. Read `~/.openclaw/workspace/skills/stackstone-branding/SKILL.md` for formatting specs
3. Read the docx skill at `/mnt/skills/public/docx/SKILL.md` for document generation mechanics (if available, otherwise use your knowledge of the docx library)
4. Read `example-conversation-andy-barrett.md` and `example-conversation-part2.md` to understand the full consultative process
5. Read ALL project files and transcripts provided by Tom
6. Then start the conversation — not the document

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
