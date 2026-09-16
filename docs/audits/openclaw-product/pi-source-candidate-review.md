# Pi source-candidate review

## Decision

Independent review passed the follow-up source fixes to the audited repair
baseline. The candidate is suitable for a controlled Pi source update, not
certified as deployed or verified against live data.

## Review findings resolved

- **Authenticated Git executable provenance:** validated absolute system Git
  and HTTPS helper paths, trusted network PATH and GIT_EXEC_PATH, and fail-closed
  handling prevent a home-directory executable planted by package code from
  receiving the network credential. A real offline planted-executable test
  uses synthetic credentials. This is not a same-user filesystem sandbox.
- **WhatsApp coverage:** retention caps and malformed/unrenderable records
  now mark coverage incomplete. The Markdown feed itself displays warnings,
  including when valid messages remain. Direct, group, total-cap and mixed
  valid/malformed fixtures exercise this behavior.
- **Supported development runtime:** the workspace now uses Node 22, matching
  the application's Node >=22.12 requirement rather than testing only on
  unsupported Node 20.

The independent reviewer reran the Git and runtime suites (23 tests) and
reported no remaining blocking regression in these fixes. Debian/Pi trusted
Git helper resolution was also exercised offline.

## Validation

Validation used Node 22.22.0, pnpm 10.26.1 and Python 3.11.14.

| Check                                            | Result               |
| ------------------------------------------------ | -------------------- |
| Full `pnpm build`                                | Passed               |
| `pnpm exec tsc --noEmit`                         | Passed               |
| YouTube, SkilzVolt and direct-exec Vitest suites | 67 passed            |
| Management-bot Git credential suite              | 11 passed            |
| Runtime/WhatsApp contract suite                  | 12 passed            |
| Google OAuth suite                               | 12 passed, 1 skipped |
| Codex profile-shape suite                        | 2 passed             |
| Whisper offline shell fixtures                   | Passed               |
| Installer and modified shell syntax              | Passed               |

The full build ran in a disposable copy of HEAD plus the working-tree source
fixes, using existing installed dependencies and the existing prebuilt A2UI
bundle/hash. It completed plugin manifest, SDK declaration and metadata
staging. This is not evidence of a fresh dependency install or a fresh A2UI
source build. The main workspace build outputs were not replaced.

The preview renders after the runtime update, but remains disconnected from
the Pi gateway; this is not authenticated live UI verification.

## Explicit limits

- The real OAuth-library integration test remains skipped because the optional
  libraries are unavailable. Stub-based tests do not prove provider exchange.
- `pnpm release:check` fails its extension-version alignment gate (root
  2026.3.8 versus 32 extension packages at 2026.2.26). Inspection found no such
  version gate in the Pi source installer, build or runtime. This candidate is
  **not an npm publication release**; extension metadata was not broadly changed.
- Seven skill corrections still require human review. Invoice executor
  recovery and live CRM/finance readback are not delivered by these source fixes.
- Existing schedules stay unchanged. The user accepted this after clarification
  that a rule about new jobs does not establish a violation by existing jobs.

## Pi handoff

Before updating, verify the actual instance profile, state directory, checkout,
branch, service source and port. Check for live-only source changes and preserve
them deliberately; do not assume a clean GitHub branch proves the Pi matches.
Then use the canonical installer/full build, not an ad-hoc partial build or a
build whose failure is ignored. See the existing
[Pi deployment guidance](../../../knowledge/pi-deployment.md).

Only live post-update checks can establish gateway/channel operation, poller
freshness, approval behavior and independent CRM/finance destination receipts.
No Pi deployment, live credential read, schedule change or ledger mutation was
performed in this review.
