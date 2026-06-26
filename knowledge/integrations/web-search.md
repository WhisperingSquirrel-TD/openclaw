# Integration: Web Search (Tavily — native provider)

> Part of the OpenClaw knowledge base. Map: [`../../replit.md`](../../replit.md) · Knowledge index: [`../README.md`](../README.md).
> Related: [Troubleshooting](../troubleshooting.md) (gateway config crashes) · [Pi reference](../pi-reference.md)

Tavily is integrated as a **native `web_search` provider** in OpenClaw's built-in tool system. No exec or Python script needed — L1 calls `web_search` directly.

- Auto-detected from `TAVILY_API_KEY` in `~/.openclaw/.env`
- **Cannot** be forced via `tools.web.search.provider` — "tavily" is not a valid value (allowed: brave, perplexity, grok, gemini, kimi). Setting it crashes the gateway. Tavily only works via auto-detection.
- Auto-detection priority: Perplexity → Tavily → Brave → Gemini → Grok → Kimi
- `web_search` must be in `tools.alsoAllow` array in `openclaw.json` when using the `coding` profile, otherwise it is blocked regardless of key presence
- The Python script at `~/.openclaw/integrations/tavily/search.py` is a redundant fallback
