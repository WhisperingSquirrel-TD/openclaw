# Source repair status

This is the remediation register for the [current audit](current-audit.md).
It does not certify the Pi deployment or complete the whole-product review.

## Implemented in this checkout

| Finding                                                       | Source repair                                                                                                                                                                                                                                                                      | Verification                                                                                                                                                                                                                    |
| ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Management-bot credentials in Git URLs and child environments | Scoped GitHub credential helper; reject noncanonical clone URLs before invoking Git; scrub legacy GitHub origins; redact output. Isolate authenticated network phases from checkout, local Git and npm execution with sanitized environments.                                      | Isolated tests include helper protocol execution with synthetic credentials, adversarial clone URLs and secret-inheritance checks. [Details and counts](credential-repair.md)                                                   |
| Google authentication contract mismatch                       | Explicit phone callback routes, strict callback/state validation, parser-compatible callback handling, explicit PKCE, atomic private refresh-capable token replacement, preserved tokens on failure, and fail-closed unattended operation. Installer/runbook instructions aligned. | Thirteen tests: twelve passed, one real-library integration test skipped because required libraries were unavailable. This is an outstanding verification gap, not a passing integration test. [Details](google-auth-repair.md) |
| WhatsApp 48/72-hour mismatch and stale empty evidence         | 48-hour source window; atomic output and coverage sidecar; missing/failed source is incomplete evidence rather than a verified empty feed.                                                                                                                                         | Runtime fixture and static contract tests included in the eight-test runtime suite. [Details](runtime-contract-repair.md)                                                                                                       |
| Expense legacy timer ambiguity                                | Units explicitly labelled legacy opt-in/rollback, portable home paths, and no installer activation/migration of those units. Guidance distinguishes canonical source policy from unknown live activation.                                                                          | Runtime/configuration suite and shell syntax checks. No live service changes. [Details](runtime-contract-repair.md)                                                                                                             |
| Executable regression coverage                                | Added YouTube, Whisper and Codex fixture coverage; checked existing SkilzVolt owner controls, task permits and receipt suites. Corrected one direct-exec test's ambient-PATH dependence without weakening the security policy.                                                     | Detailed suite results in [Executable coverage](executable-coverage-repair.md).                                                                                                                                                 |

Credential tests also fail against the prior source. That comparison was
retrospective; it is not represented as a test-first execution sequence.

## Governed skill corrections submitted, not active

Seven full-body, version-pinned proposals were submitted after checking for
existing pending proposals. All require human review; no active skill version
was replaced or self-approved.

| Skills                       | Correction                                                                                                                                                                              | Status/details                                                       |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Organisation `skill-creator` | Remove retired SharePoint-library authority requirements while retaining SkilzVolt governance and human review. The distinct generic bundled skill was not replaced.                    | Pending human review. [Proposal record](skill-governance-repair.md)  |
| `google-auth`                | Align helper availability, portable paths, callback ports, token preservation and fail-closed deployment checks with the source contract.                                               | Pending human review. [Proposal record](google-auth-repair.md)       |
| Five invoice skills          | Require verified executor availability and the actual command contract before use; retain draft/signoff, exact-row selection, ambiguity handling, ledger/PDF and readback requirements. | Pending human review. [Proposal records](invoice-contract-repair.md) |

## Not safely rectifiable from the current evidence

- **Invoice execution:** the authoritative named executor implementations,
  tracker adapter and approval binding were not recovered. No substitute
  business schema, fake completion, or alternate financial executor was built.
  Guarded skill proposals do not implement the missing runtime capability.
- **Schedule policy:** existing 06:55 health and Monday 06:00 briefing
  declarations conflict with the stated scheduling rule. They are not declared
  approved merely because they exist. No live schedule was moved; explicit
  owner/runtime reconciliation remains necessary.
- **Actual expense trigger ownership:** source ambiguity is clarified, but
  active timers/router units must still be inspected before migration/removal.
- **CRM and other procedural skills:** source absence of a dedicated worker
  was not a defect. Real attributed writes, approval paths and independent
  destination receipts remain unverified; no unnecessary worker was invented.
- **Deployment:** no Pi service, token, permission, schedule, ledger or
  production configuration was modified.

The SharePoint expense and finance XLSX authority is unchanged.
