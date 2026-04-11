# AI-INTEL-OPTIONS.md — AI Capability Options

## LLM providers (via OpenClaw gateway)

| Command | Provider | Model | Use when |
|---|---|---|---|
| `/codex` | OpenAI Codex OAuth | openai-codex/gpt-5.4 | Default. Cheapest. Good for most tasks. |
| `/openai` | OpenAI API | openai/gpt-5.4 | More capable. Higher cost. |
| `/anthropic` | Anthropic API | anthropic/claude-sonnet-4-5 | Best reasoning. Highest cost. |

**Daily reset**: Provider resets to openai-codex/gpt-5.4 at 04:00 daily.

## Subagents (OpenClaw-native)

Use for: research, analysis, audits, isolated coding tasks, anything multi-step or slow.

### How to trigger
Tell L1 in plain language:
> "Use a subagent to review BACKLOG.md and suggest the top 5 improvements"

Or use slash command directly in Telegram:
```
/subagents spawn l1 <task description>
```

### Subagent commands
```
/subagents list              — see running subagents
/subagents kill all          — stop all subagents
/subagents log 1             — see log from subagent #1
/subagents info 1            — metadata for subagent #1
```

### Good subagent tasks
- Audit these files and propose cleanup
- Review BACKLOG.md and suggest top priorities
- Refactor a specific integration
- Compare approaches and recommend one
- Research a topic and write a summary
- Draft multiple emails in parallel

### Poor subagent tasks (just ask L1 directly)
- Quick factual questions
- Simple one-line file edits
- Short summaries from a single file

### Cost note
Each subagent has its own token budget. For heavy tasks, L1 may use a cheaper model for subagents — configured via `agents.defaults.subagents.model`.

## ACP (external runtime — Codex, Claude Code)

ACP connects to external coding agent runtimes.

### When to use
- "Run this in Codex"
- "Use Claude Code for this"
- Complex coding tasks where a full coding agent is better than L1

### Note
ACP behavior depends on channel/runtime support. Persistent thread-bound ACP sessions may behave differently on Telegram than on other surfaces. Verify ACP is configured in openclaw.json before expecting it to work.

## Memory/search (qmd)

qmd is a local-first keyword search over workspace files.

```bash
# Check it works
which qmd
qmd --help

# Index workspace (if needed)
qmd collection add ~/.openclaw/workspace --name workspace

# L1 uses it automatically when available
```

If L1 reports "spawn qmd ENOENT": run `bash ~/openclaw/scripts/fix-qmd-path.sh`
