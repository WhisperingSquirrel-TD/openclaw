---
name: crm-partnership
description: Manage strategic partner records — investors, introducers, referrers, and collaboration partners — in local partnership summary files and SharePoint partnership folders.
---

# CRM Partnership

Use this skill when Tom mentions someone who is strategically important but is **not** simply a lead, opportunity, or client.

## Use this for
- investors
- potential investors
- introducers / warm connectors
- referrers
- collaboration partners
- ecosystem relationships
- people who may matter across multiple companies/opportunities

## Do NOT use this for
- standard sales opportunities → use CRM / SharePoint opportunity flow
- active clients/accounts → use accounts flow
- generic contacts with no strategic importance

## Local summary layer
- `stackstone/partnerships.md`

## SharePoint structure
- `Partnerships/<Person Name>/`
- `Partnerships/<Person Name>/<Person Name> - Current.md`
- `Partnerships/<Person Name>/YYYY-MM-DD - <Type> - <Description>.md`

## What to capture
- why this person matters
- relationship context (who introduced them / which company they connect to)
- what they care about commercially
- what Tom wants from the relationship
- what should **not** be pushed too early
- next step and timing
- ongoing communication trail (emails, LinkedIn notes, call notes, meeting setup, strategic framing changes)

## Filing rule
If Tom mentions:
- an investor around an opportunity
- someone who could become a channel / collaboration partner
- a person who sits behind multiple opportunities
- someone important enough to revisit later in a more strategic context

then create/update both:
1. `stackstone/partnerships.md`
2. SharePoint `Partnerships/<Person Name>/...`

## Communication capture rule
When Tom sends or receives something material involving a partner/investor/referrer:
- create a dated SharePoint artifact under `Partnerships/<Person Name>/`
- update `<Person Name> - Current.md`
- update `stackstone/partnerships.md` next step / last touch if materially changed
- if a new message/file movement changes the real next step (for example a document already arrived by WhatsApp after we drafted as if it still needed sending by email), update the records immediately before replying to Tom; do not leave the CRM/partnership layer describing an out-of-date state

## Blocked-write recovery rule
If a partnership SharePoint write fails because of access issues, stale system state, or other SharePoint blockage:
- do **not** treat "written to queue" as completion
- preserve the intended SharePoint paths/content as still-outstanding work
- once the SharePoint path is healthy again, re-queue the blocked partnership writes before considering the relationship record up to date
- do not let later unrelated queue writes silently replace the fact that this partner write still needs to happen

**Test:** If Tom asks later whether the partnership record was actually written to SharePoint, the answer must depend on verified SharePoint result state, not on whether it was once queued.

Examples:
- intro email sent
- reply received
- call booked
- strategic note about how to frame the relationship
- investor signal / concern / objection

## Stitching principle
The partner record must preserve enough context that later L1 can answer:
- what Tom sent
- why he sent it
- what stage the relationship was at
- what was deliberately held back for later

without relying on vague memory alone.

## Distinction rule
A partner record can coexist with an opportunity record.
Example:
- Harken = opportunity
- Tim Ward = strategic investor / partner contact around Harken

Do not force everything into the opportunity file if the person deserves their own long-lived relationship record.

## Mixed-topic meeting linkage rule (MANDATORY)
If one meeting/call/transcript covers multiple commercially meaningful threads at once (for example: an opportunity thread, a partnership thread, a project thread, or a referral/connector thread), do **not** collapse the whole thing into whichever record feels most obvious.

Required mechanism:
1. Before filing, run a **multi-thread linkage check**: which long-lived records did this meeting materially update?
2. If the answer includes more than one record type/home, update **each** relevant home.
3. In each home, add a short cross-reference so a later agent can see that the same meeting also mattered elsewhere.
4. Do not treat one home as the sole truth if the meeting genuinely moved multiple relationship threads.

Fail-closed test:
- If a later agent asked "where do I look to understand this meeting's impact?" the answer should be "check the linked records" rather than "hope the most obvious file captured everything."

## Joint-offer artifact rule (MANDATORY)
If a file/note/deck/report is primarily about a **shared proposition**, **joint go-to-market offer**, **referral/channel relationship**, or **how Tom and the other person work together**, treat that as strong evidence that the material belongs in a partnership record even if the person/company already has an Opportunity folder.

Required mechanism:
1. Ask: is this mainly about winning work from them, or mainly about collaborating with them to win/deliver work elsewhere?
2. If it is mainly collaboration, create/update `Partnerships/<Person Name>/` as the primary long-lived home.
3. If an Opportunity folder also exists and still matters, keep only the minimum cross-reference needed there rather than making the opportunity folder the sole canonical home.
4. If Tom explicitly asks to save it in the opportunity folder anyway, comply with the immediate filing request **but also surface that a partnership home likely fits better** and offer the follow-up move/copy.

Fail-closed test:
- If a later agent asked "where do I look first to understand the Tom + this-person strategic relationship?" the answer should not depend on rummaging through an unrelated sales-opportunity folder.

## Trigger examples
- "Tim Ward is an investor"
- "We should treat X as a partner"
- "This person could open doors later"
- "Create a partner folder for them"

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
