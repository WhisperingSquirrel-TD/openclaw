# Continuation reconciliation

Date: 2026-08-22

## Method and boundary

The local `subrepl-yp2ra0tn` and `subrepl-dsmbnd6t` branches were compared
read-only against the current `main` worktree with direct `git diff HEAD
<branch>` comparisons. No merge, cherry-pick, branch deletion, mockup/design
import, finance edit, or Microsoft edit was performed.

This is a narrow reconciliation of durable agent-continuation recovery and
production-build TypeScript validation. It is not an approval to alter runtime
configuration or to deploy/restart a gateway.

## Decisions

| Branch work                                                                                                                                                                                           | Decision                                        | Evidence / reason                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `subrepl-yp2ra0tn`: `0f3632b4eca` plus `b0e6e273b51`, `fdae919b267`, and `4df39e31284` (continuation loop, leases, recovery, queue scheduling, runner lifecycle, and gateway startup/session control) | **Retained on `main`; no copy patch required.** | The direct comparison has no difference for the continuation implementation or its tests: `src/agents/continuation-loop.ts`, `src/agents/openclaw-tools.ts`, `src/agents/tools/agent-loop-tool.ts`, `src/agents/tools/subagents-tool.ts`, `src/auto-reply/reply/{agent-runner,abort,commands-session-abort,continuation-recovery,continuation-scheduler,followup-runner}.ts`, `src/auto-reply/reply/queue/{cleanup,enqueue,state,types}.ts`, `src/gateway/server-startup.ts`, and `src/gateway/server-methods/sessions.ts`. Current `main` already carries the corresponding continuation history (`829c3bfe731`, `a0cb14da276`) and preserves the branch's durable state, lease, stale-worker, cancellation, recovery, and bounded-turn behavior. Applying it again would be redundant and risk overwriting newer code. |
| `subrepl-dsmbnd6t`: `1550133e3e1` and `c56dda50f2a` (strict production type validation)                                                                                                               | **Retained on `main`; no copy patch required.** | `package.json` on `main` already runs `pnpm exec tsc --noEmit` as the first step of the production `build` script. The branch's strict-build behavior is therefore already present.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Both branches' remaining `package.json` difference                                                                                                                                                    | **Rejected.**                                   | Their only direct package difference is changing `youtube-transcript` from the exact `1.3.0` to the floating `^1.3.0` range. This is unrelated dependency-pin drift, does not strengthen typechecking, and weakens reproducibility.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `subrepl-yp2ra0tn` direct differences outside the assigned boundary                                                                                                                                   | **Rejected / left untouched.**                  | `src/agents/pi-tools.plugin-tool-conflicts.test.ts`; `src/agents/tools/task-system-tool.ts` and its deleted test; `src/agents/tools/youtube-transcript-tool.ts`; `src/auto-reply/reply/commands-core.ts`; `src/auto-reply/reply/commands-types.ts`; `src/auto-reply/reply/export-html/vendor/{highlight.min.js,marked.min.js}`; and `src/gateway/reconnect-gating.test.ts` are not continuation recovery or strict-build work.                                                                                                                                                                                                                                                                                                                                                                                           |
| `subrepl-dsmbnd6t` direct differences outside the assigned boundary                                                                                                                                   | **Rejected / left untouched.**                  | `src/agents/tools/task-system-tool.ts` and its deleted test are unrelated to durable continuation recovery and production-build typechecking.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |

## Verification

The retained implementation was exercised without running the application or
restarting a workflow:

```text
pnpm exec vitest run src/agents/continuation-loop.test.ts \
  src/agents/openclaw-tools.agent-loop.test.ts \
  src/agents/tools/agent-loop-tool.test.ts \
  src/auto-reply/reply/continuation-recovery.test.ts \
  src/auto-reply/reply/continuation-scheduler.test.ts
```

Result: 5 test files and 19 tests passed.

```text
pnpm exec tsc --noEmit
```

Result: passed with no diagnostics.

## Remaining unique work

There is no remaining unique durable-continuation or strict-typecheck code to
transfer from either named branch. The only remaining direct package change was
explicitly rejected above; all other direct differences are outside this
reconciliation's allowed ownership boundary and remain on their source
branches for separate review. No design/mockup/assets were imported, including
the Mockup Sandbox artifact.
