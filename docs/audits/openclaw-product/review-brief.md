# OpenClaw Product Review Brief

**Status:** evidence-backed audit deliverables prepared; no runtime code was edited or deleted. This is a review of a supplied snapshot, not a claim about live OpenClaw state.

## Product intent

The product intent is a single owner-only organiser that **Capture → Categorise → Allocate → Verify**:

1. **Capture** consequential or potentially important inbound evidence before it disappears or changes.
2. **Categorise** importance, domain, certainty, entity state, and the difference between fact, inference, and proposal.
3. **Allocate** each obligation to its owning destination; sibling routes remain independent.
4. **Verify** by reading back the actual destination and retaining a route-specific receipt. A mirror, proposal, queue, draft, poll, or local sidecar is not completion proof.

The organiser is owner-only. External messages, entity changes, authoritative CRM/SharePoint writes, financial mutations, posts, and other protected consequences remain owner-approved/TOTP-gated unless an explicitly approved deterministic route covers that exact action. There is no persistent mission: a skill's trigger wording is not a standing scheduler, and a configured-looking cron phrase is not runtime proof.

### Autonomous allowlist boundary

Only explicitly declared, least-privilege operations with a real route and destination proof may be autonomous: read-only inspection/retrieval, evidence preservation, categorisation, allocation, and the specifically documented routine intake/review/reconciliation paths. Everything outside that allowlist remains TOTP/owner approval. The inventory records this as a design boundary, not as proof that any route is live.

## Snapshot provenance and completeness

- Remote review provenance records exact commit **`faa717afeb66322a79e5eb20ebf8b27fec83042d`**, with the verified branch one commit ahead of main and exclusively review-input additions.
- The local checkout does not contain that commit object; the relation is preserved as supplied provenance, not re-presented as local live-state verification.
- `MANIFEST.json` contains **226 entries**. All 226 snapshot destinations were read and their byte sizes checked: **2,542,148 manifest bytes = 2,542,148 observed bytes; zero mismatches**.
- The companion download check has 112 content hash responses and 114 rate-limited responses. For every entry, this audit independently computes a Git blob SHA from the downloaded bytes; missing download-check SHA is not treated as a byte failure.
- Local counterpart search covers tracked repository files and `.local/intake-repair`; paths in the reports are relative. Exact content-hash matches: **36**. Same-relative-path candidates (path only, not content proof): **69**.

## What the deliverables contain

- `entry-inventory.json`: one record for each of the 226 manifest entries, including destination, bytes, Git blob SHA, remote commit provenance, local path/hash matches, purpose, consumer, dependency signals, deployment evidence, usage-confidence scope, and a conservative decision with rationale.
- `activation-matrix.md`: all 55 snapshot skills. It separates declared trigger instructions from proven scheduler/runtime evidence and marks live-state access blocked.
- `manifest-verification.json`: machine-readable byte/hash/count and provenance checks.

## Reading the decisions

- **keep:** 31
- **investigate:** 168
- **consolidate:** 13
- **retire:** 2
- **connect:** 12

These are audit dispositions, not implementation instructions. In particular, “retire” identifies generated/example candidates requiring owner confirmation and consumer checks; it does not delete anything. “Consolidate” requires choosing an authority and reconciling consumers first. “Investigate” means the snapshot is useful evidence but does not establish local ownership or deployment.

## Activation and proposed work guardrails

The activation matrix deliberately does not convert skill text into live scheduler claims. It also does not claim access to current cron records, gateway state, worker state, Telegram receipts, or scheduler delivery logs. Any next activation review must prove source event → router → state → worker → destination → receipt.

Existing proposed work remains proposed and is not implemented by this audit: Garmin full-recovery polling (Task #6), YouTube channel health polling (Task #8), Telegram transcript search (Task #9), and Telegram YouTube-poller removal (Task #10).

## Non-goals

No source content, personal records, email signatures, invoice bodies, tokens, or secrets were copied into these reports. No runtime code, deletion, deployment, scheduler change, or product claim was made. The report provides bounded evidence and explicit uncertainty for the owning review.
