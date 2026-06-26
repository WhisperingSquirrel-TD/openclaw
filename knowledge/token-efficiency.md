# Token Efficiency (Pi Config)

> Part of the OpenClaw knowledge base. Map: [`../replit.md`](../replit.md).
> Related: [Pi deployment](./pi-deployment.md) (install script applies these) · [Architecture](./architecture.md)

The install script applies these automatically via `setdefault` (all preserving any manual overrides). See [Pi deployment](./pi-deployment.md) for what the install script does.

| Setting                              | Value         | Effect                                                                                  |
| ------------------------------------ | ------------- | --------------------------------------------------------------------------------------- |
| `heartbeat.lightContext`             | `true`        | Heartbeat only sends `HEARTBEAT.md`, **not** SOUL.md/memory. ~70% cut in heartbeat cost |
| `heartbeat.every`                    | `60m`         | Once per hour (default 30m) — halves background API calls                               |
| `heartbeat.activeHours`              | `07:00–23:00` | Zero calls midnight–7am                                                                 |
| `heartbeat.ackMaxChars`              | `150`         | Heartbeat replies capped at 150 chars                                                   |
| `bootstrapMaxChars`                  | `10000`       | Each workspace file (SOUL.md etc.) capped at 10KB                                       |
| `contextPruning.mode`                | `cache-ttl`   | Prunes conversation history >2h old (Claude only)                                       |
| `providerTimeoutSeconds.ollama`      | `1800`        | Ollama session timeout = 30 min. Force-assigned (not setdefault) so re-running install always corrects lower values. A real session has 10k–20k input tokens; at Pi 4 prefill rates of 20–50 tok/s that's 200–1000 s before any output is generated. |
| `memory.qmd.update.embedActiveHoursStart` / `embedActiveHoursEnd` | `2` / `5` | Confines `qmd embed` (heavy CPU — observed at 343% on a 4-core Pi) to 02:00–05:00. Outside this window `shouldRunEmbed()` short-circuits, leaving CPU free for Ollama fallback. Force-assigned each install. Implemented in `src/memory/qmd-manager.ts` (`isWithinEmbedActiveHours`) with config in `src/config/types.memory.ts` / `zod-schema.ts` / `backend-config.ts`. |

**What still gets sent on every interactive message:** SOUL.md + memory files (up to 10KB each). Keep these files focused — every line costs tokens on every exchange.

**Skills vs inline context:** OpenClaw's skill system means tool descriptions are injected on-demand, not in the system prompt. No changes needed there.
