# Product repair status

This is a partial delivery, not completion of the whole-product review. No live deployment, permission expansion, schedule change, database migration or live skill edit was performed.

## Implemented, regression-tested repairs

| Area | Proven failure | Repair |
| --- | --- | --- |
| Expense recovery | Receipt transport fields were stripped before writing the recovery manifest, preventing later receipt delivery. | Preserve transport metadata in recovery records, not ledger facts. |
| Expense recovery integrity | Malformed JSON could be treated as an empty queue; malformed facts could become empty candidates. | Fail closed and preserve the original manifest/item rather than silently overwriting it. |
| Capture evidence | A `captured` outcome without an expense ID could produce a false canonical reference. | Require an expense ID before claiming persisted capture. |
| Concurrent recovery | Worker finalization could overwrite an item appended while the worker was processing. | Use the shared writer lock, reload current state, remove only exact successfully processed snapshots and retain concurrent appends/enrichment. |
| Task gateway connection | Node returns bracketed IPv6 hostnames, so the explicit `::1` loopback allowance never matched. | Normalize brackets before applying the existing local-only allowlist. |

Tests were introduced before these fixes. Finance/watcher coverage includes retry idempotency, evidence retention, malformed records and deterministic concurrent append/enrichment. Task bridge regression covers IPv6 loopback. These tests do not establish live receipt retention or task execution.

The workspace preview workflow starts and renders the control UI, but shows **Disconnected from gateway / Health Offline**. This is frontend-only verification, not an authenticated operational journey. No live gateway was configured or restarted.

No ledger schema, source-identity convention or review/approval state transition was changed. Capture remains `needs_review`, not confirmed finance posting.

## Source correspondence

The GitHub review branch resolves to `faa717afeb66322a79e5eb20ebf8b27fec83042d`; its comparison against remote main showed one additional commit, consisting only of `review-input/` additions. All 226 entries were retrieved and byte-checked.

Remote main was `9d783817ea19b6e518040055e135602863d71cfe` at inspection. Before changes, the three repaired implementation files matched the Git blobs on that remote main exactly:

- `pi-services/expense-intake-watcher/watcher.py`
- `pi-services/seer-finance/seer_finance/ledger/expense_capture_adapter.py`
- `src/agents/tools/task-system-tool.ts`

The workspace commit itself was unavailable to GitHub's compare endpoint (404), so whole-checkout equivalence is not established.

Other branch comparisons against remote main:

| Branch | Ahead / behind | Disposition |
| --- | --- | --- |
| `pi-live` | 2 / 53 | Diverged; three changed paths. Inspect separately, not a deployment authority. |
| `review/finance-watcher-integration` | 0 / 2 | Behind main; do not merge as new work. |
| `review/seer-finance-source` | 1 / 11 | Diverged; 44 paths in comparison, not proof all are absent from main. |
| `review/task-41-stale-actions` | 1 / 13 | Diverged; three paths require content reconciliation. |
| `reconcile-2026-06-03` | 0 / 175 | Behind main; retain history, no blanket merge. |

## Retained versus removed

No runtime component was removed. Legacy intake sidecars, alternative skill copies, deployment copies and recovery scripts have not passed consumer-migration/runtime-parity gates. Snapshot task-operator code already implements selection, leases, successor promotion and substantial regression coverage; missing code in an incomplete local view is not evidence that the product needs a replacement.

The inventory's retirement and consolidation labels are proposals only. Generated caches are not tracked cleanup targets. An old tracked SharePoint poller backup has no discovered static consumer, but this alone does not prove absence of dynamic or live consumers.

## Skill-update register — approval required

| Skill | Priority and evidence | User impact | Proposed change / dependency |
| --- | --- | --- | --- |
| expenses | High: live skill review found direct SQLite precedence alongside legacy Markdown workflow/checklist text. | Different sections can cause inconsistent destination choices. | Make direct source-linked SQLite `needs_review` capture the active procedure; move Markdown instructions to explicit migration/recovery context. Preserve original receipt/hash/SharePoint path/eTag/readback requirements. No live edit made. |
| task-operate | Verification gap, not confirmed stale guidance: snapshot includes bounded operator/lease logic, but no current delivery/scheduler proof was obtained. | A readiness change alone does not establish autonomous pickup. | First prove the human-transition → signal/delivery → operator-check path. Change wording only if it claims execution without delivered invocation. Do not rewrite the skill to match incomplete wiring. |
| email-send / send-email | Verification gap: gateway/tool inspection alone cannot prove the final executor's TOTP boundary. | Preparation might be mistaken for authorisation if evidence is conflated. | Trace and test the actual final send executor and signed-off draft contract before proposing any consolidation. Preserve TOTP; no permission expansion. |

## Remaining work and gates

1. **Live source map:** obtain bounded read-only service-unit, executable path, profile/state path, checkout and port evidence. Compare deployed source hashes before claiming workspace fixes apply to the live installation.
2. **Flagship direct journey:** prove approved email service → source-linked SQLite candidate → independent readback and receipt retention. The successful direct-capture path's attachment handoff remains unverified; recovery tests are not a substitute.
3. **Approval and continuation:** test real downstream expense posting from `needs_review` fails; prove actual human-review delivery invokes bounded operator pickup; trace final protected sends across alternate tools.
4. **Activation:** reconcile the full live catalogue with the 55 snapshot skill entries. Record actual invocation/cadence and destination evidence, not merely trigger wording.
5. **Consolidation/removal:** establish canonical ownership and installer/service wiring, test consumers and a full runtime schedule interval, explain each destructive batch, then remove only proven obsolete components.

Existing Garmin and YouTube proposals remain separate and unchanged. Do not mark the overall task complete from this bounded repair.

## Rollout boundary

Do not run a generic Pi deployment against an unidentified installation. After separate approval, source reconciliation and exact profile/state/checkout/service/port confirmation, use the canonical installer procedure described in `knowledge/pi-deployment.md`. The documented default commands are `cd ~/openclaw && git pull` followed by `bash ~/install-forked-openclaw.sh`; their suitability for the active installation is not yet verified. No deployment is requested by this report.