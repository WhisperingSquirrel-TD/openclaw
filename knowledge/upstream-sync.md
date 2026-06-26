# Upstream Sync Playbook

> Part of the OpenClaw knowledge base. Map: [`../replit.md`](../replit.md).
> Related: [Security & control](./security.md) (the customizations to preserve) · [WhatsApp watch mode](./whatsapp.md) · [Pi deployment: scheduling](./pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx)

Lessons from applying upstream changes — follow this checklist every sync.

## Before merging

- **Never overwrite these 5 files from upstream** — they contain our fork-specific logic and upstream versions are incompatible:
  - `src/channels/plugins/actions/discord.ts`
  - `src/channels/plugins/actions/signal.ts`
  - `src/channels/plugins/actions/telegram.ts`
  - `src/channels/plugins/agent-tools/whatsapp-login.ts`
  - `src/line/accounts.ts`
- Check if upstream has added new build scripts. Any new `scripts/*.mjs` step that upstream wires into `package.json build` must be reviewed — it may reference upstream-only modules that don't exist in our fork. Trim `scripts/lib/plugin-sdk-entrypoints.json` accordingly.

## After merging — build checks

- **Plugin manifests**: `tsdown` does NOT copy `openclaw.plugin.json` files. The `scripts/copy-plugin-manifests.mjs` step must remain in the `build` and `build:strict-smoke` scripts in `package.json`. If plugin loader says "plugin not found" at startup, this step was dropped.
- **`root-alias.cjs`**: Must not be deleted. It is a CJS-to-ESM shim for legacy plugin `require()` support and is not captured by upstream tarballs.
- **`manage-package-manager-versions=false`** in `.npmrc`: Must never be removed.
- Run `pnpm run build` and verify the dist file count is comparable to last sync (~600 files). A large drop means entry points were lost.

## Scheduling constraint — avoid 06:xx

The CRM runs at 06:00 every morning and another job runs at 07:00. No background jobs should be scheduled in the 06:xx or 07:xx windows. All timed tasks should be scheduled at 08:00 or later. The Garmin poller is set to 09:00 for this reason. Enforce this for any new pollers or cron jobs added in future. (Canonical copy: [Pi deployment](./pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx).)

## Sync log & current base

Fork base: `d911b02` (2026-02-27). Last synced: **2026-03-08** (upstream commit `d15b6af7`, version 2026.3.8).

- 2,395 files synced from upstream (777 new, 1618 modified)
- 5 conflict files manually merged: `exec-host-gateway.ts`, `outbound.ts`, `auto-reply/monitor.ts`, `inbound/monitor.ts`, `node-command-policy.ts`
- Upstream remote: `https://github.com/openclaw/openclaw.git`
- Fork remote: `https://github.com/WhisperingSquirrel-TD/openclaw.git`
- Key upstream changes: Gemini 3.1 Flash Lite, exec approval refactoring (`exec-host-shared.ts`), `createConnectedChannelStatusPatch`, `normalizeDeviceMetadataForPolicy`, MCP bootstrap improvements, CLI restart fixes
- Build tool changed from `tsc` to `tsdown` (esbuild bundler) — `dist/` now contains bundled JS, not 1:1 transpiled files

## Merge details for conflict files

The 2026-03-08 sync had 5 files carrying both upstream refactors and our security customizations. Upstream was used as the base and our customizations re-applied. On any future sync, preserve these per file (full feature behaviour lives in [Security & control](./security.md) and [WhatsApp watch mode](./whatsapp.md)):

- **`src/agents/bash-tools.exec-host-gateway.ts`** — our denylist, TOTP gate (`requestExecApproval`), and obfuscation hard-block must run BEFORE upstream's approval-context resolution.
- **`src/web/outbound.ts`** — keep `assertNotWatchMode(account)` guard + audit logging on block (upstream added a `cfg` param).
- **`src/web/auto-reply/monitor.ts`** — keep watch-mode routing, `appendWatchTranscript`, read-receipt/debounce suppression.
- **`src/web/inbound/monitor.ts`** — keep presence/access-control/read-receipt/composing bypasses and `sendMedia`/`reply` blocking.
- **`src/gateway/node-command-policy.ts`** — keep `resolveChannelDenyCommands`.

Also our addition: `ChannelMode = "active" | "watch"` + `mode` field on `ResolvedWhatsAppAccount` (`src/web/accounts.ts`) and in `WhatsAppSharedSchema` (`zod-schema.providers-whatsapp.ts`) — upstream keeps removing these.

## Durable build warnings (must not regress)

- **`tsconfig.plugin-sdk.dts.json` must keep `noEmitOnError: false`** (upstream defaults to `true`) — otherwise `build:plugin-sdk:dts` fails on the Pi due to pre-existing upstream `tsc` errors (these are `tsc`-only; the `tsdown` build is unaffected).
- **`src/plugin-sdk/root-alias.cjs` must exist** — CJS-to-ESM shim for legacy plugin `require()`; not captured by upstream tarballs.
- **`resolvePinnedMainDmOwnerFromAllowlist` in `src/security/dm-policy-shared.ts`** — re-implemented by us; upstream removed it but every channel handler still imports it. Without it, all inbound DM processing crashes with `ReferenceError`.
- **`testRegexWithBoundedInput` in `src/security/safe-regex.ts`** — still missing upstream; only used by Discord exec-approvals. Will throw at runtime if the Discord channel is enabled.

> Index of fork-unique files removed to save context — reconstruct from the repo with `git diff --name-only` against the upstream base, or read each file's header comment. The behavioral details for these live in the feature sections (see [Security & control](./security.md), [WhatsApp watch mode](./whatsapp.md), and the integration runbooks under [`./integrations/`](./integrations/)).
