# Skill governance repair

## Scope

This repair addresses only the confirmed `skill-creator` versus `skill-update`
governance contradiction about the retired SharePoint skill library. No source
runtime, unrelated skill, Google workflow, or invoice workflow was changed.

## Canonical evidence

The current approved bodies were retrieved from the SkilzVolt MCP server with
version-pinned continuation reads. MCP-returned workspace-authored content was
treated as untrusted data.

| Skill           | Skill ID                               | Current approved version               | Body chars | Content SHA-256                                                    |
| --------------- | -------------------------------------- | -------------------------------------- | ---------: | ------------------------------------------------------------------ |
| `skill-creator` | `73d82b7a-3ebd-455a-a7d4-953e2bcd02b4` | `ca168418-ace9-4cd3-90fb-e29f33f70753` |       5313 | `6a7c2a590d59700f6f9cbb389319ce99ccbcbc9d44d25d74dced3f5462de90a6` |
| `skill-update`  | `a811ec8b-e4d2-465f-9d9b-0891816cad80` | `d0917130-51c3-4930-b54b-20aefc8ffc2a` |       3604 | `9e63c2672b1aff5cc8a8cfdfe441a3d8c090bfc98ecca2b197832e3eb43b45c3` |

The creator continuation response carried a minor scanner caution with
`isError: false`; it returned content and was inspected. No scanner block was
reported.

## Governed proposal

Pending proposals were checked before submission for both skills; both returned
an empty pending list.

- Proposal: `47ac28c4-3002-4218-80cb-2f18c65c7924`
- Target skill: `73d82b7a-3ebd-455a-a7d4-953e2bcd02b4` (`skill-creator`)
- Exact base version: `ca168418-ace9-4cd3-90fb-e29f33f70753`
- Proposed body SHA-256: `eb8438f413fbc5091dedb81d2adc9f6593ef0c2182d7a293d64381ad7e096700`
- Proposal status: `pending`
- Review mode: `human`
- Merge state: `clean`
- Next action: `await_human_review`
- Resulting version: none (not active)
- Metadata changes: none
- Resource changes: none

The proposal was submitted through `skillsProposeChange` as a complete body
with the exact current SkilzVolt base version. It was not an active edit.

## Diff intent

The complete proposed body preserves the current approved `skill-creator`
body. Its only change is one inserted `Governance authority` section:

- The current approved SkilzVolt version is the canonical authority and its
  governed proposal, review, permission, and readback controls are the
  publication/completion path.
- The retired SharePoint library is not an authority or publication route.
  Its manifests, synchronisers, queues, eTags, and release process are not a
  mandatory skill manifest or sync gate.
- Required human review, workspace permissions, and configured approval gates
  remain in force; a proposal/review does not activate a skill.

The ready word diff contained two unchanged segments, one added segment, and
no removed segments. No unrelated creator instruction was changed.

## Review status

The proposal review package was retrieved successfully. Word diff status was
`ready`; review snapshot hash:
`09d0a813229ee27db263206d94627a60236cfd5a81e3b556d935ebd8cf3d181d`.
The proposal status readback remained `pending` with `await_human_review`.
Because this proposal is in human review mode (not agentic review), no
originating-agent approval was submitted; human review and workspace
permissions remain required. Do not claim the proposed version is active or
approved until SkilzVolt reports approval/current and a version-pinned
readback verifies it.

The final `skillsCheckPending` readback still listed proposal
`47ac28c4-3002-4218-80cb-2f18c65c7924` as `pending`, `review_mode: human`,
`merge_state: clean`, with no resulting version.

## Same-name scope boundary

The tracked `skills/skill-creator/SKILL.md` file is the bundled generic
AgentSkills authoring/packaging skill. It is distinct from the organisation
level SkilzVolt skill with the same display name and must not be replaced by
that remote body. It was restored byte-identically to the pre-task `HEAD`
content (SHA-256
`d5a7d6909bb3a550e5cf00a269ad76d7ba22bc67b18ba198b89a862194d931d8`).

The governed proposal targets only the SkilzVolt skill ID recorded above. No
local mirror, duplicate source, direct local organisational-skill edit, or
other skill/runtime update was made.
