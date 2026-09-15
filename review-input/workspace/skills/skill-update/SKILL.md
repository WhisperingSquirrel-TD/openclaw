---
name: skill-update
description: Make a targeted update to an existing OpenClaw skill and sync the canonical SharePoint copy with verified in-place overwrite. Use for any edit to an existing skill.
---

# Skill Update

## Scope
Own small, targeted updates to an existing skill. For new, redesigned, split, or packageable skills, use `skill-creator` first; use this skill's SharePoint sync gate when that work is ready.

## Shared skill-store model (MANDATORY)
`/skills/openclaw-skill-estate/` is one shared canonical store, not an L1-only library. It is used and improved through two current writer surfaces:
1. **L1 / OpenClaw** — local working copies under the managed skill roots, published back to the canonical SharePoint folder through this workflow.
2. **Claude** — its managed SharePoint skill-store route.

Potential future agents may become additional consumers/writers, but they must be explicitly integrated into this same canonical store; do not create parallel per-agent libraries, alternate canonical folders, or unmanaged copies.

### Multi-writer invariants
- SharePoint is the sole shared source of truth; each skill has one canonical folder and SharePoint native version history is the only rollback history.
- Every writer must pull/read the current canonical skill and top-level manifest before editing, make a targeted change, then re-check the remote content immediately before overwrite.
- A remote hash/eTag or manifest change since the initial read is a **concurrent-change conflict**: do not overwrite, merge from memory, or create a fork. Re-read the canonical version and reconcile deliberately.
- Every writer must publish in place, verify the returned file hashes/eTags, and leave an auditable content receipt. Local copies are working copies, not authority.
- All agents must use the shared skill for its stated trigger and workflow. A local adaptation is not a substitute for updating the shared canonical skill first.

## Required inputs
- Exact local skill directory and intended change.
- Canonical SharePoint library root: `/skills/openclaw-skill-estate/`.
- The single library inventory: `/skills/openclaw-skill-estate/MANIFEST.json`.

## Guardrails
- SharePoint is the canonical shared current copy; local agent installs are working copies.
- Before any skill use, creation, or local skill edit, run the content-addressed SharePoint pull synchroniser. It may install only a new canonical skill or a hash-different canonical bundle; hash/content mismatches fail closed.
- Before editing, read the current SharePoint skill folder and top-level release manifest; record the canonical path, SHA-256 bundle/file hashes, and eTag metadata when available. SharePoint native version history is the sole release history: do not add or rely on any release number.
- Immediately before upload, re-check the remote skill folder. If it changed since the initial read, do not overwrite: mark **needs manual review — concurrent SharePoint change**.
- Overwrite existing files in the one canonical skill folder in place. Do not create a second skill folder, timestamped snapshot, per-skill manifest, or `versions/` copy. SharePoint native version history is the rollback mechanism.
- Never include credentials, tokens, `.env` files, or runtime secrets in a skill bundle.
- If publishing, manifest update, or verification fails, retain the local edit but label it **updated locally; SharePoint sync incomplete** and record the exact blocker.

## Pi/OpenClaw execution path (MANDATORY)

In this workspace, normal skill publishing is intentionally **not TOTP-gated**. The supported writer is the guarded SharePoint queue operation `publish_skill` using the allowlisted `skill_id` format `<source>:<top-level-skill-name>` (for example `workspace-skills:skill-update`).

- Use that queue route first for ordinary existing-skill updates; it performs the canonical baseline/manifest guard and returns its verified result through `SHAREPOINT_RESULT.md`.
- Do **not** misinterpret an exec/TOTP denial from a local helper script as a requirement to ask Tom for a code. That is the wrong path for normal publishing.
- For nested skill files, publish the allowlisted top-level canonical bundle that owns them (for example `workspace-skills:standup` for `skills/standup/morning-standup/SKILL.md`), not a fabricated nested `skill_id`.
- Read the queue result and require `verified: true`; then run the inbound synchroniser when exec is available and write the sync receipt. If the queue rejects an ID, inspect the top-level owning bundle and retry once with its valid ID; do not invent queue fields or report a publish as complete.
- Use the direct `publish_skill_release_to_sharepoint.py` executable only for diagnosis or where the queue route is unavailable and the relevant execution gate is already open.

## Pull synchronisation
Use `scripts/sync_skill_library_from_sharepoint.py` as the inbound synchroniser. It reads the schema-3 content-addressed canonical manifest and installs only a new skill or a hash-different canonical bundle. Hash mismatch, manifest defect and local/remote content divergence fail closed. Its durable receipt is `~/.openclaw/runtime/skill-library-sync/hash-ledger.json`; it records hashes and eTags only, never release numbers.

- Run `--dry-run` before activation and normally before every skill use or edit; a non-zero result means conflict/error and must be resolved before using the affected skill.
- Do not bypass the synchroniser with a manual overwrite.

## Workflow
1. Run the inbound synchroniser and resolve any conflict/error. Identify the exact skill directory and canonical SharePoint folder. Read the existing local `SKILL.md`, bundled files, current SharePoint folder, the top-level release manifest, and `SYSTEM_MAP.md` routing entry.
2. Record the pre-change comparison: local and SharePoint bundle/file hashes and eTags for every file in scope; do not create, infer or report a release number.
3. Make only the requested change. Keep `SKILL.md` focused; route detailed material to bundled references where appropriate.
4. Validate the local skill: check YAML frontmatter and name/path consistency; run applicable tests/validators; review changed files and any `SYSTEM_MAP.md` routing impact.
5. Publish only with `scripts/publish_skill_release_to_sharepoint.py <source-root>:<skill-name> --summary <summary>`. It immediately rechecks the full SharePoint content and manifest baseline; if unchanged, it overwrites the existing canonical files in place. Do not create new parallel locations.
6. The release script refreshes the single top-level `MANIFEST.json`, then re-reads every uploaded skill file and the manifest to verify hashes, bundle hash, path and SharePoint eTag.
7. Run the inbound synchroniser after a successful publish to record the verified content receipt in the local hash ledger, then write/overwrite one local sync record under `reference/skill-sync/<skill-name>.md` with paths, hashes/eTags and verification status. Do not suffix that record, the skill name, or any folder with `-vN`; SharePoint native version history is the only release history.
8. Report the change only with its verified canonical path, hashes/eTag and sync status—never a release version.

## Completion test
The update is complete only if local validation passed; the pre-upload concurrent-change check passed; the canonical SharePoint files were overwritten in place and hash/eTag-verified; the top-level manifest reflects the verified current hashes; and the local hash ledger records the verified receipt. SharePoint native version history provides rollback.

Otherwise state: **updated locally; SharePoint sync incomplete**.
