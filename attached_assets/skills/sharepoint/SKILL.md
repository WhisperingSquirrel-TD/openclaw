# SharePoint Skill

This skill describes how to read from, write to, and manage SharePoint documents
using the OpenClaw mirror + queue system on the Pi.

---

## Architecture overview

```
SharePoint (Microsoft 365)
       │
       │  Microsoft Graph API (every 15 min)
       ▼
~/.openclaw/workspace/sharepoint-cache/<SP-path>          ← .md / .txt files (verbatim)
~/.openclaw/workspace/sharepoint-cache/<SP-path>.extracted.md  ← .docx / .pdf / .pptx / .msg (text extracted)
~/.openclaw/workspace/SHAREPOINT_INDEX.md                 ← full document tree + sync status
~/.openclaw/workspace/sharepoint-cache/.manifest.json     ← per-file machine-readable status
       │
       │  You write a queue entry (direct file write — no exec, no TOTP)
       ▼
~/.openclaw/sharepoint-queue.json                         ← queue (writes + on-demand reads)
       │
       │  sharepoint_queue_processor.py runs every 1 min via cron
       ▼
~/.openclaw/workspace/SHAREPOINT_RESULT.md                ← operation results
```

---

## Reading SharePoint files

**No queue entry is needed for reads.** All supported file types are available
locally in the cache directory. Read them directly like any local file.

### Text files (.md, .txt)

```
Local path = ~/.openclaw/workspace/sharepoint-cache/<SP-path>

Example:
  SharePoint path: /Stackstone CRM/Opportunities/Croyde Medical.md
  Local file:      ~/.openclaw/workspace/sharepoint-cache/Stackstone CRM/Opportunities/Croyde Medical.md
```

Each file starts with a sync-timestamp header so you always know how fresh it is:
```
<!-- sharepoint-cache: /Stackstone CRM/Opportunities/Croyde Medical.md | synced: 2026-04-13T10:15:00Z -->
```

### Binary files (.docx, .pdf, .pptx, .msg)

Text (and images where available) are **automatically extracted** from these files
during each 15-minute sync. The extracted content lives at:

```
<original-path>.extracted.md

Example:
  SharePoint path: /Stackstone CRM/Proposals/Q2 Proposal.docx
  Extracted file:  ~/.openclaw/workspace/sharepoint-cache/Stackstone CRM/Proposals/Q2 Proposal.docx.extracted.md
```

The extracted file starts with a header:
```
<!-- sharepoint-binary-extract: /Stackstone CRM/Proposals/Q2 Proposal.docx | synced: 2026-04-13T10:15:00Z -->
```

If images were embedded in the document, they are saved alongside the extracted file in a
`<filename>.images/` folder and referenced in the markdown.

### What is and is not in the cache

| File type | How it's available |
|-----------|-------------------|
| `.md`, `.txt` | Direct text mirror (≤ 500 KB) |
| `.docx` | Text + tables extracted to `.docx.extracted.md` (≤ 5 MB) |
| `.pdf` | Text extracted to `.pdf.extracted.md` (≤ 5 MB) |
| `.pptx` | Slide text + notes extracted to `.pptx.extracted.md` (≤ 5 MB) |
| `.msg` | From/To/Subject/Body extracted to `.msg.extracted.md` (≤ 5 MB) |
| All other types | Indexed only — use `read_binary` queue entry if needed |

### Where to look first

1. **`SHAREPOINT_INDEX.md`** — scan the full document tree. It shows:
   - All SharePoint paths
   - Which files are cached / extracted / skipped and why
   - The exact local path for each available file
2. **`sharepoint-cache/<SP-path>`** — open a text file directly
3. **`sharepoint-cache/<SP-path>.extracted.md`** — open an extracted binary file directly
4. **`.manifest.json`** — machine-readable per-file status if you need to check programmatically

---

## On-demand binary read (mid-conversation)

If you need to read a binary file that hasn't been extracted yet, or you need
a fresh extraction NOW (not waiting for the next 15-min cron), queue a
`read_binary` entry. The processor picks it up within 1 minute.

```json
[
  {
    "id": "sp-read-20260413",
    "operation": "read_binary",
    "path": "/Stackstone CRM/Proposals/Q2 Proposal.docx",
    "requested_at": "2026-04-13T10:00:00Z"
  }
]
```

After ~1 minute, check `SHAREPOINT_RESULT.md` to confirm success, then
read the extracted file at `sharepoint-cache/Stackstone CRM/Proposals/Q2 Proposal.docx.extracted.md`.

---

## Writing to SharePoint

Write a queue entry directly to `~/.openclaw/sharepoint-queue.json`.
This is a plain file write — no `exec`, no TOTP required.

The queue processor picks it up within 1 minute and writes results to
`SHAREPOINT_RESULT.md`.

### Queue file format

```json
[
  {
    "id": "unique-id",
    "operation": "create" | "update" | "append",
    "path": "/Stackstone CRM/Opportunities/Harken Health.md",
    "content": "Markdown content to write",
    "requested_at": "2026-04-13T10:00:00Z"
  }
]
```

### Queue rules

- **`id`**: any unique string (e.g. `"sp-<timestamp>"`)
- **`path`**: full SharePoint path from drive root, starting with `/`
- **`operation`**:
  - `create` — creates a new file; fails if file already exists
  - `update` — overwrites the entire file; fails if file does not exist
  - `append` — appends content to end of an existing file
  - `read_binary` — on-demand extraction of a binary file (no `content` needed)
- **`content`**: required for create/update/append; omit for read_binary
- **`requested_at`**: ISO 8601 UTC timestamp

If the queue file already has pending entries, append your entry to the array.
If the file does not exist yet, write a fresh JSON array with your entry.

### Checking write results

Open `~/.openclaw/workspace/SHAREPOINT_RESULT.md` about 1 minute after queuing.
It records success or error for each processed operation, keyed by `id`.

---

## Common patterns

### "What's in folder X?"

1. Read `SHAREPOINT_INDEX.md` — the folder tree is shown visually.
2. Look for files under the folder in the Cached and Extracted sections.
3. All `.md`/`.txt` files and all `.docx`/`.pdf`/`.pptx`/`.msg` files (≤ 5 MB)
   are readable directly with no further action.

### "Read the Q2 Proposal Word doc"

1. Check `SHAREPOINT_INDEX.md` — find path and confirm it's extracted.
2. Read `sharepoint-cache/Stackstone CRM/Proposals/Q2 Proposal.docx.extracted.md` directly.
3. Note the sync timestamp — if the file changed recently, queue `read_binary` for a fresh pull.

### "Read a PDF that isn't in the cache yet"

Queue a `read_binary` entry:
```json
[{"id":"sp-read-now","operation":"read_binary","path":"/Reports/Annual Review.pdf","requested_at":"2026-04-13T10:00:00Z"}]
```
After ~1 min, read `sharepoint-cache/Reports/Annual Review.pdf.extracted.md`.

### "Update the Harken Health opportunity note"

```json
[
  {
    "id": "sp-harken-20260413",
    "operation": "update",
    "path": "/Stackstone CRM/Opportunities/Harken Health.md",
    "content": "# Harken Health\n\n...(full updated content)...",
    "requested_at": "2026-04-13T10:00:00Z"
  }
]
```

---

## Cache freshness

- Poller runs every **15 minutes** via cron.
- Each cached/extracted file has a sync timestamp in its header.
- For on-demand fresh extraction, use `read_binary` queue entry.

---

## Error states

| Symptom | Likely cause |
|---------|-------------|
| `SHAREPOINT_INDEX.md` is empty or missing | Poller hasn't run yet, or `SHAREPOINT_HOST` not set in `.env` |
| Binary file shows `extractor_unavailable` | `python-docx`/`pdfminer.six`/etc. not installed — run install script |
| Write/read_binary result shows auth error | Token expired — run `python3 ~/.openclaw/integrations/microsoft-l1/sharepoint.py reauth` |
| File visible in index but not extracted | File type or size not eligible (check `reason_detail` in manifest) |
| Queue entry stays pending | Queue processor may not be running — check cron with `crontab -l` |
