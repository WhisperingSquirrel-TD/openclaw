---
name: crm-opportunity
description: Promote leads into later pipeline stages (Qualified Lead, Opportunity, Proposal, Active Engagement, Client, Dormant, Lost), create/update detailed account files, and ensure they are excluded from generic campaigns when appropriate.
---

# CRM Opportunity Management

Use this skill when a lead moves beyond simple lead stage.

## Scope Boundary
This skill owns:
- stage transitions beyond simple lead stage
- commercial progression logic
- opportunity / proposal / active engagement / client handling
- defining concrete next steps for later-stage records

This skill does **not** own:
- general CRM campaign maintenance → use `crm-update`
- SharePoint file/folder organization itself → use `crm-sharepoint`

## Goals
- Keep CRM concise
- Keep rich account context in dedicated files
- Stop active opportunities from being swept into unrelated campaigns

## Stage rules
- `Lead` = early / unqualified
- `Qualified Lead` = plausible fit, worth active follow-up
- `Opportunity` = live commercial conversation
- `Proposal` = scoped offer or clear commercial next step
- `Active Engagement` = paid work in progress
- `Client` = established client relationship
- `Dormant Opportunity` = warm but inactive
- `Lost` = closed / no longer live

## Required actions when stage >= Opportunity
1. Create or update the rich note structure in SharePoint using the `crm-sharepoint` skill
2. Mark `campaign_eligible` as `No`
3. Add/update local CRM summary fields:
   - stage
   - **next_step** — must be concrete and actionable with timeline/trigger
   - last_touch
   - sharepoint_path
4. Keep meeting/call notes in SharePoint, not in the CRM summary row
5. Ensure the SharePoint entity follows the structure:
   - `<Company> - Current.md`
   - dated artifact files for meetings/calls/emails/updates
6. If temporary local fallback notes are needed, they must live in a per-entity folder (e.g. `stackstone/opportunities/<slug>/`), never as loose files in the parent folder
7. Before creating a new folder (local or SharePoint), search for sensible existing variants and reuse the existing entity if clearly the same

## Next step guidance
The `next_step` field should drive Tom's action list, not just record status.

**Good:**
- "Follow up on SLT discussion outcome (due 10 Apr)"
- "Send revised proposal after Tom reviews brief"
- "Second gentle check-in (stalled 16 days since last contact)"
- "Await reply to 8 Apr email; mark inactive if no response by 15 Apr"

**Bad:**
- "Awaiting reply"
- "Follow up"
- "Next steps TBC"
- "Ongoing"

## Migration rule: paid work
If Tom has done paid work for the company, it is no longer just an opportunity.
- Migrate/create the entity under `sites/StackstoneConsulting/Shared Documents/Accounts/<Company>/`
- Set stage to `Active Engagement` or `Client` as appropriate
- Ensure the account folder contains:
  - `<Company> - Current.md`
  - dated artifact files for future history
- Preserve enough historical context from the opportunity stage in the account current file
- Keep it excluded from generic campaigns
- Treat it as an account management relationship, not a lead/opportunity nurture item

## CRM field guidance
Each meaningful row should support:
- company
- primary_contact
- stage
- status
- last_touch
- next_step
- campaign_eligible
- detail_file

## Rule
Do not leave an active opportunity sitting as a campaignable lead.

## Website / inbound rule
If a new website enquiry arrives and it is commercially real, create or update an Opportunity entry and detail file promptly. Website enquiries are not just anonymous leads once a real conversation has started.

## Paid work rule
If paid work is booked or committed, promote immediately into Accounts / Active Engagement or Client. Do not leave paid business sitting in Opportunities.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
