# MEMORY.md — Persistent Learnings

_Durable facts and learnings across sessions. Written when something important is discovered._
_Trim oldest entries when file grows beyond ~20KB._

## System & integrations
- SOUL.md is encrypted at rest. Never create plaintext SOUL.md in workspace.
- SOUL_PENDING.md is a staging area — never auto-promote to SOUL.
- Garmin auth uses ~/.garth token store. Do not retry login when rate-limited (429). Run poller interactively to refresh session.
- OpenAI gateway supports: openai/gpt-5.4, openai-codex/gpt-5.4, anthropic/claude-sonnet-4-5
- qmd search requires PATH to include ~/.npm-packages/bin in the gateway systemd service.
- Gateway service unit: ~/.config/systemd/user/openclaw-gateway.service

## Tom's preferences
- Direct responses, no filler
- Revenue-critical items (enquiries, leads) surfaced immediately
- TOTP approval required for outbound actions
- Morning briefing at 07:00

## Process learnings
_(add learnings here as they are discovered)_
