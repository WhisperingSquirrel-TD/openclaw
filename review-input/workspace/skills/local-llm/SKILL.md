---
name: local-llm
description: Route small, private, low-stakes, waitable first-pass work to the local Ollama model when it is suitable and cheaper than cloud inference.
---

# Local LLM

## Goal
Use the Pi's local LLM path deliberately for work that is:
- internal
- private
- low-stakes
- waitable
- repetitive
- useful as a rough first pass

Treat the local model as:
- private
- cheap
- background
- first pass
- waitable

Do not treat it as:
- final authority
- external polish
- a high-trust decision-maker

## Current local route
Read `reference/LOCAL-LLM.md` for the current local model decision and endpoint.

At present the expected local route is:
- Ollama on Tom's Mac mini, reached from the Pi over the home network
- API at `http://192.168.86.46:11434`
- OpenAI-compatible API at `http://192.168.86.46:11434/v1`
- Preferred OpenClaw provider/model ref: `custom-mac-ollama/qwen3-coder-131k`
- Preferred model alias: `qwen-coder30b`
- Do not select `q3-coder-next`; it has been removed from the Mac mini route

Do **not** assume a Pi-local Ollama instance is still preferred.

## Failed route handling
Do not keep a failed or unproven local-model route as a "fallback" just because it still exists in config or documentation.
A local route may be called a fallback only if it has a current successful proof after the relevant config/gateway refresh.
If a replacement route is proven and the old route previously failed, remove the old route from active routing/config references or label it historical only.

## Session bootstrap / interactive operations — NEVER USE LOCAL
**MANDATORY exclusion:** Ollama is **never suitable** for:
- Session startup / bootstrap operations
- Interactive turn-by-turn conversation
- Any operation with <60 second latency requirement
- Daytime use when Pi is under normal operational load

**Why:**
- Model loading: 15-30 seconds for 2GB model
- Inference on 20-30K token context: additional 15-30+ seconds
- Total latency: 30-60+ seconds minimum, longer when Pi loaded
- Session bootstrap timeout: <30 seconds → **guaranteed failure**

**For these operations, use:**
- Primary cloud model (Anthropic Claude)
- Lightweight cloud fallback (e.g., Claude Haiku) if primary fails
- Fail fast with clear error if cloud unavailable

**Never configure Ollama as fallback for bootstrap/interactive paths.**

## When Ollama IS appropriate

**✅ Good fits:**
1. **Overnight background crons** (03:00-06:00 when Pi is quiet)
   - Email/inbox first-pass triage
   - WhatsApp message classification
   - Daily summary generation
   - Low-priority file organization
   
2. **Low-stakes internal work** (acceptable if 60-120s latency)
   - "Is this file still relevant?" checks
   - Simple categorization/tagging
   - First-pass contact research summaries
   - Internal note cleanup/structuring
   
3. **Controlled-context tasks only** (target route: 131072 tokens; safe fallback: 65536)
   - Single email analysis
   - One transcript chunk or bounded source packet
   - Short document summaries
   - Individual message classification
   - Larger task-system packets only when deliberately isolated and still within the selected route's proven window
   
4. **Draft-then-refine workflows**
   - Ollama generates rough structure/skeleton
   - Cloud model polishes to final quality
   - First pass at categorization, human/cloud reviews

**❌ Never use Ollama for:**
1. **Interactive/real-time operations** - too slow (30-60s minimum)
2. **Session bootstrap** - guaranteed timeout
3. **Uncontrolled main-session context** - even a 131k local route is not safe for bootstrap/interactive sessions with large injected context and compaction risk
4. **High-stakes decisions** - not reliable enough for source-of-truth work
5. **External-facing copy** - quality/polish matters
6. **When Pi is loaded** - becomes unusable (daytime operations)
7. **Client work** - wrong/rough output is not acceptable
8. **BCC lists** - operationally fragile
9. **Legal/financial wording** - risk too high
10. **Calendar/contact operations** - accuracy critical

## Decision checklist (ALL must be YES)

Before routing to Ollama, verify:
- [ ] Is it 03:00-06:00 OR truly low-priority background work?
- [ ] Is context bounded and comfortably within the selected local route (`131072` target, `65536` fallback)?
- [ ] Can I wait 60-120 seconds for response?
- [ ] Is wrong/rough output acceptable?
- [ ] Is this internal-only (not client-facing)?
- [ ] Is Pi quiet (load <1.0) or this is overnight?
- [ ] Would this still be useful as a rough first pass?
- [ ] Can the result be reviewed/refined later if needed?

If ANY answer is NO → use cloud model.

## Ollama routing pattern
When Ollama IS appropriate (checklist passes):
1. Explicitly specify model in cron/subagent spawn
2. Set generous timeout (120+ seconds minimum)
3. Verify Pi load before running (<1.0 preferred)
4. Keep context bounded and explicit; do not inherit main-session/bootstrap context
5. Have cloud refinement step if final output matters

## Behavioural checkpoint (MANDATORY)
Before defaulting to the main model, explicitly check whether the task is Ollama-appropriate.
Run the decision checklist:
1. Is it overnight (03:00-06:00) OR truly low-priority?
2. Is context <10K tokens?
3. Can I wait 60-120 seconds?
4. Is wrong/rough output acceptable?
5. Is this internal-only?
6. Is Pi quiet (or overnight)?
7. Still useful as rough first pass?
8. Can be reviewed/refined later?

**If ALL yes:** Consider Ollama (but still prefer cloud unless cost/load matters)  
**If ANY no:** Use cloud model

This is a behavioural rule: do the check before work, not after.

**Default assumption: use cloud model unless there's a specific reason to use Ollama.**

## Concrete examples of good Ollama use

**Overnight email triage cron (03:00):**
- Input: Last 24h emails (chunked, one at a time)
- Task: Flag likely-important vs routine
- Ollama output: rough triage list
- Cloud refinement: morning briefing synthesis

**Low-priority file organization:**
- Input: Single file metadata
- Task: "Is this still relevant?"
- Ollama output: keep/archive suggestion
- Review: human checks list before bulk action

**WhatsApp classification (overnight):**
- Input: Individual messages
- Task: Categorize as personal/admin/urgent/trivial
- Ollama output: rough classification
- Use: filter what appears in morning briefing

**Draft-then-refine:**
- Input: Research notes <10K tokens
- Task: Generate outline structure
- Ollama: rough skeleton
- Cloud: final polished document

**NOT good examples:**
- ❌ Session bootstrap (too slow)
- ❌ Client email drafts (quality matters)
- ❌ BCC list generation (operationally fragile)
- ❌ CRM updates during daytime (Pi loaded + accuracy matters)
- ❌ Calendar analysis (needs full context + accuracy)
- ❌ Interactive conversation (user expects <5s response)

## OpenClaw configuration integrity
When configuring OpenClaw to use Ollama / a local-network model provider:
- Treat a direct edit to `~/.openclaw/agents/<agentId>/agent/auth-profiles.json` as **non-durable unless verified after a gateway/auth refresh**. OpenClaw may rewrite the agent auth store from canonical config/auth state.
- The durable fix for a custom provider auth failure is the canonical config/profile layer (`~/.openclaw/openclaw.json` via `openclaw config set`, Control UI, or a direct config edit), not only the per-agent generated auth file.
- If `openclaw config set` or direct config write fails with `EPERM`, do **not** tell Tom that a plain `chattr -i` is enough. First determine whether root privileges are needed. For immutable/protected config files, the likely local command is `sudo chattr -i ~/.openclaw/openclaw.json` followed by the config edit and gateway restart.
- Do not claim the local model route is fixed until a real OpenClaw model invocation succeeds **after** any gateway restart/auth refresh, or clearly label it as only direct-endpoint validation.
- Minimum proof checklist before saying "done": endpoint reachable from Pi, model returns via Ollama API, provider auth exists in the durable config layer or survives refresh, and one OpenClaw session/subagent turn with that model completes.

## Output discipline
When recommending or using the local route, say plainly:
- why local is appropriate
- what trade-off is being accepted
- whether the result is only a first pass or safe to treat as final

## Important implementation note
Updating this skill improves routing judgement but does not enforce routing by itself.
For reliable local-first behaviour, ensure relevant operational skills explicitly inherit this policy and prefer a dedicated local execution path for recurring background work.

## Guardrails
- Do not route local just because work is cheap; it must also fit the local model's context limits and host resources.
- Treat "small enough" as one short excerpt, recent tail, single entity, or one file section at a time.
- Treat "too large" as whole transcripts, multiple long files, or tasks that need broad cross-document reasoning.
- Chunk only when each chunk can be understood independently and later merged safely.
- Do not chunk when the task depends on global judgement or preserving date/entity/context linkage across the whole input.
- Prefer cloud when the Pi is already busy, when other background jobs matter more, or when the local run would create noticeable contention.
- If local is suitable in principle but the runtime conditions are poor, fall back to cloud without drama.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".