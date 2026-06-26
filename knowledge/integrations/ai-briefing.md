# Integration: AI Briefing Pipeline

> Part of the OpenClaw knowledge base. Map: [`../../replit.md`](../../replit.md) · Knowledge index: [`../README.md`](../README.md).
> Related: [Integrations: YouTube](./youtube.md) · [Pi deployment: scheduling](../pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx) · [Pi reference](../pi-reference.md)

Weekly automated briefing: RSS collection → heuristic ranking → Claude synthesis → `AI_BRIEFING_CURRENT.md`.

| File | Purpose |
| ---- | ------- |
| `~/.openclaw/integrations/ai-briefing/collect.py` | Fetch + deduplicate items from ~16 RSS/Atom feeds |
| `~/.openclaw/integrations/ai-briefing/rank.py` | Heuristic pre-filter, title-word clustering, Haiku scoring; fallback to heuristics if API fails |
| `~/.openclaw/integrations/ai-briefing/synthesize.py` | Tavily enrichment (top 4 items, 3000-char cap), Sonnet synthesis, writes `AI_BRIEFING_CURRENT.md`; fallback to structured plain-text |
| `~/.openclaw/integrations/ai-briefing/run.py` | Orchestrator: runs collect→rank→synthesize, updates `state.json`, exit codes 0/1/2 |
| `~/.openclaw/ai-briefing/AI_BRIEFING_CURRENT.md` | Latest briefing handoff file for L1 to read |
| `~/.openclaw/ai-briefing/state.json` | Pipeline state (last run, per-stage summaries, error) |
| `~/.openclaw/ai-briefing/seen-items.json` | URL-hash dedup across runs (prevents repeats) |
| `~/.openclaw/ai-briefing/included-items.json` | "New since last briefing" tracking |
| `~/.openclaw/ai-briefing/raw/` | Raw collected JSON per run |
| `~/.openclaw/ai-briefing/ranked/` | Ranked JSON per run |
| `~/.openclaw/ai-briefing/briefings/` | Archived briefing Markdown files |
| `~/.openclaw/integrations/ai-briefing/pipeline.log` | Cron log |
| `reference/AI-BRIEFING-POLICY.md` | Scoring policy, inclusion/exclusion rules, format contract |
| `reference/ai-briefing-sources.yaml` | Machine-readable source list with weights |

**Scoring:** 4 dimensions (Relevance, Novelty, Actionability, Credibility) × 1–5 pts each = max 20. Shortlist ≥10; Tavily enrichment ≥14; quiet-week threshold: <2 items ≥10.

**Cron:** every Monday at 06:00 → `run.py`. (This is the 06:00 job referenced by the [scheduling constraint](../pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx).) On-demand via `/ai-briefing run` in mgmt-bot or `python3 ~/.openclaw/integrations/ai-briefing/run.py` directly.

**mgmt-bot commands:**
- `/ai-briefing` — show pipeline status from `state.json`
- `/ai-briefing run` — run the full pipeline now (2–5 min)
- `/ai-briefing read` — preview first 3000 chars of `AI_BRIEFING_CURRENT.md`

**Resilience:** partial source failure is tolerated (per-feed try/except); Haiku failures fall back to heuristic ranking; Sonnet failures fall back to structured plain-text briefing; pipeline always writes an output file unless zero items are collected.
