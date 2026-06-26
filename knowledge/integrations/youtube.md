# Integration: YouTube Transcripts & Channel Poller

> Part of the OpenClaw knowledge base. Map: [`../../replit.md`](../../replit.md) · Knowledge index: [`../README.md`](../README.md).
> Related: [Integrations: AI briefing](./ai-briefing.md) (same two-phase batch model) · [Pi deployment: scheduling](../pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx) · [Pi reference](../pi-reference.md)

| File                                                         | Purpose                                                                           |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| `~/.openclaw/integrations/youtube/transcript.py`             | YouTube transcript extractor — no API key needed                                  |
| `~/.openclaw/integrations/youtube/channel_poller.py`         | Channel monitor — RSS polling, transcript fetch, AI summary, Markdown file writer |
| `~/.openclaw/integrations/youtube/channels.json`             | Channel list — edit directly or use `/yt-add` from mgmt-bot                       |
| `~/.openclaw/integrations/youtube/channel-poller-state.json` | Seen-video state (auto-managed, do not edit)                                      |
| `~/.openclaw/integrations/youtube/channel-poller.log`        | Poller log                                                                        |
| `~/.openclaw/workspace/reference/transcripts/`               | Output directory — YYYY-MM-DD - slug.md per video                                 |
| `~/.openclaw/skills/youtube-transcript/SKILL.md`             | L1 skill — usage patterns, URL formats, exit codes                                |

**transcript.py:** Accepts YouTube URLs or bare video IDs. Returns plain text transcript (manual or auto-generated captions). Use `--timestamps` for timestamped output, `--lang XX` for specific language, `--list-langs` to see available languages. Exit code 1 means no captions available.

**channel_poller.py:** Two-phase, two-mode design.

_Cron mode (default — every 30 min, skips 06:xx–07:xx per the [scheduling constraint](../pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx)):_

1. Phase 1 — checks `pending_batches` in state; for each completed Anthropic batch, retrieves results, writes Markdown files, sends Telegram notifications.
2. Phase 2 — polls RSS for new videos, fetches transcripts, submits all new videos as a **single Anthropic Message Batch** (50% cost saving). Videos are added to `pending_video_ids` immediately so they won't be re-fetched; files appear on the next run (~30 min). If batch submission fails, falls back to synchronous processing automatically. If only OpenAI is configured (no Anthropic key), also falls back to sync.

_Sync mode (`--sync` flag — used by `/yt-run` in mgmt-bot):_

- Each video is processed immediately: transcript → summary → file write → Telegram notification in one run. More expensive but gives instant feedback. The mgmt-bot passes `--sync` automatically.

_Single-video mode (`--video <url>` — always synchronous):_

- For interactive testing. Does not use batch API.

**State file fields:** `processed_ids` (fully done), `pending_video_ids` (claimed for a batch, not yet written), `pending_batches` (list of `{batch_id, submitted_at, videos[]}`). Batches older than 23h are dropped before Anthropic expires them at 24h.

**Adding channels:**

- From Telegram: `/yt-add https://www.youtube.com/@channelname Label` (mgmt-bot)
- Direct edit: `nano ~/.openclaw/integrations/youtube/channels.json`
- Accepted formats: channel URL (`@handle`, `/c/name`, `/user/name`), or bare channel ID (`UC...`)
- Trigger manually: `/yt-run` in mgmt-bot (sync mode, immediate result)
- Manual test run: `python3 ~/.openclaw/integrations/youtube/channel_poller.py --sync`
- Single-video test: `python3 ~/.openclaw/integrations/youtube/channel_poller.py --video <url>`

**AI summary:** Uses `ANTHROPIC_API_KEY` from `.env` (batch API in cron, sync in `/yt-run`), falls back to `OPENAI_API_KEY` (always sync — OpenAI has no batch API). If neither is present, raw transcript is saved without a summary. Model override: `OPENCLAW_AI_MODEL` env var. Transcript is truncated to 6000 chars for the prompt (cost control). Full raw transcript always saved.
