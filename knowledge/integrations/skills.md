# Skills Path Configuration

> Part of the OpenClaw knowledge base. Map: [`../../replit.md`](../../replit.md) · Knowledge index: [`../README.md`](../README.md).
> Related: [Pi reference](../pi-reference.md) · [Pi deployment](../pi-deployment.md)

- Workspace skills live at `~/.openclaw/workspace/skills/` (32 skills as of Apr 2026)
- Must be declared in `openclaw.json` under `skills.paths` or openclaw skips them with "resolves outside configured root" warnings
- Correct config: `"skills": {"paths": ["/home/tomdean88/.openclaw/workspace/skills"]}`
- System skills (10 core ones) live at `~/.openclaw/skills/` — auto-loaded, no config needed
