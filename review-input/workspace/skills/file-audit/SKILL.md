---
name: file-audit
description: Audit workspace files against the organization structure. Use when tidying the workspace, reviewing file sprawl, classifying files, or deciding what to keep, rename, merge, move, or delete.
---

# File Audit

This process exists to keep the workspace structurally sound, cheap to operate, and easy to navigate.

It supports:
- `ORGANIZATION.md`
- `SYSTEM_MAP.md`
- `FILES-TO-DELETE.md`
- cleanup work directed by Tom

---

## Why this process exists
A file can be functionally useful but still structurally wrong.

The purpose of this process is to ensure every file:
- has a clear classification
- has a clear purpose
- has a trigger
- has policy lineage
- has role linkage where relevant
- is either persistent, transient, or marked for deletion

---

## When to use
- Tom says "tidy up files"
- Tom says "audit the workspace"
- New structural confusion appears
- New files have been created and need placing
- There is duplication, drift, or uncertainty about lineage

---

## Audit method
For each file, answer:

1. **What is it?**
   - Policy
   - Process / Skill
   - Work Instruction
   - Tool

2. **What is its purpose?**
   - One sentence only

3. **When is it used?**
   - What triggers reading or using it?

4. **What policy justifies it?**
   - What is the "why"?

5. **What role uses it?**
   - Personal Assistant?
   - Non-Executive Director?
   - Security-conscious operator?
   - Or another role, if later defined

6. **What state is it in?**
   - Persistent
   - Transitional / transient
   - Legacy / obsolete

7. **What status is it in?**
   - Open
   - Resolved
   - Deferred

8. **What action is required?**
   - Keep
   - Rename
   - Reclassify
   - Map
   - Merge
   - Migrate
   - Delete
   - Defer

---

## Key distinctions

### Functionally useful vs structurally sound
Do not confuse usefulness with correct structure.
A file may be useful and still need reclassification, lineage, renaming, or cleanup.

### Transitional tools
Some tools are created temporarily during migration/cleanup.
These must be explicitly marked as:
- transient
- supporting a specific process
- having a cleanup trigger
- replaced by a canonical source of truth

### No orphan files
Nothing exists without a policy justification.
Not everything needs a process, but everything needs a why.

---

## Cleanup rule
Always use:

**Preserve → Relocate → Delete**

1. Preserve useful information
2. Relocate or rewrite it into the correct structure
3. Only then mark the old file for deletion

Never solve structure problems by deleting information.

---

## Naming rule
Check whether the file name is:
- literal
- specific
- single-purpose

If vague, either:
- rename it, or
- explicitly define its narrow purpose and keep it tightly scoped

---

## Outputs of this process
This process should produce one or more of:
- updated `FILE-AUDIT.md`
- updated `SYSTEM_MAP.md`
- updated governing policy/process files
- updated `FILES-TO-DELETE.md`
- renamed / merged / rewritten files

A good audit results in actual structural change, not just commentary.

---

## If uncertain
If a file cannot be confidently classified because the business meaning is unclear:
- do not bluff
- mark it as needing owner classification
- ask Tom

---

## Success condition
The process is complete when the file estate has:
- clear classifications
- clear lineage
- clear triggers
- minimal duplication
- no obvious dumping grounds
- a maintained delete queue for obsolete files

## Model routing pattern (MANDATORY)
Use the `local-llm` route for low-stakes first-pass grouping, classification suggestions, duplicate spotting, or rough organisation proposals **only when** the work can be kept to one small working slice at a time.
Small slice = one folder, one file batch, or one clean subsection that can stand alone.
Use the stronger cloud route for final rename/move/delete decisions and anything structurally sensitive.
Do not use the local route for broad cross-workspace judgement, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
