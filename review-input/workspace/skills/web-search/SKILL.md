---
name: web-search
description: Check and use native OpenClaw web search availability. Use when Tom asks to search the web, read an article/page, or verify whether a first-class web search route exists without defaulting straight to exec.
---

# Web Search

## Goal
Handle web-search/web-read requests accurately.

## Rules
1. Do **not** assume "not available in this session" means the capability does not exist.
2. First check whether OpenClaw has a native web search route/provider for the environment.
3. Distinguish clearly between:
   - capability exists and is available now
   - capability exists in the platform but is not active because config/key is missing
   - capability truly does not exist in this environment
4. If native web search exists, prefer it over exec/browser scraping.
5. If native web search is unavailable right now, say whether that is because of:
   - missing provider key/config
   - policy/tool exposure
   - or true absence

## Specific note for this workspace
- Tavily-backed native web search may exist as an OpenClaw capability when `TAVILY_API_KEY` is configured in `~/.openclaw/.env`.
- Do not claim "no web search tool" without considering conditional activation/config.

## Output discipline
When Tom asks for web reading/search:
- say what route you checked
- say whether it is available now
- say what is blocking it if not
- then propose the cleanest next step

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
