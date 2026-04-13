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
~/.openclaw/workspace/sharepoint-cache/<SP-path>   ← LOCAL MIRROR (readable files)
~/.openclaw/workspace/SHAREPOINT_INDEX.md          ← document tree + sync status
~/.openclaw/workspace/sharepoint-cache/.manifest.json
       │
       │  You write a queue entry (direct file write — no exec, no TOTP)
       ▼
~/.openclaw/sharepoint-queue.json                  ← WRITE queue
       │
       │  sharepoint_queue_processor.py runs every 1 min via cron
       ▼
~/.openclaw/workspace/SHAREPOINT_RESULT.md         ← write results (check after ~1 min)
```

---

## Reading SharePoint files

**Reads need NO queue entry.** The cache poller mirrors `.md` and `.txt` files
locally every 15 minutes. Read them like any local file.

```
Local path = ~/.openclaw/workspace/sharepoint-cache/<SP-path>

Example:
  SharePoint path: /Stackstone CRM/Opportunities/Croyde Medical.md
  Local file:      ~/.openclaw/workspace/sharepoint-cache/Stackstone CRM/Opportunities/Croyde Medical.md
```

Each cached file starts with a sync-timestamp header so you always know how fresh it is:

```
<!-- openclaw-sp-cache synced: 2026-04-13T10:15:00Z -->
```

### What is and is not in the cache

| File type | Eligible for local mirror |
|-----------|--------------------------|
| `.md`     | ✅ Yes (if ≤ 500 KB)      |
| `.txt`    | ✅ Yes (if ≤ 500 KB)      |
| `.docx`, `.pdf`, `.xlsx`, etc. | ❌ No — use queue to request |

Files that are not cached are listed in `SHAREPOINT_INDEX.md` under a
"Skipped files" section explaining why (type, size, or path exclusion).

### Where to look first

1. **`SHAREPOINT_INDEX.md`** — scan the full document tree to find what exists
   and check which files are cached vs. skipped.
2. **`sharepoint-cache/<SP-path>`** — open the file directly to read content.
3. **`sharepoint-cache/.manifest.json`** — machine-readable per-file cache
   status (path, cached, reason_skipped, size, last_synced).

---

## Writing to SharePoint

Write a queue entry directly to `~/.openclaw/sharepoint-queue.json`.
This is a plain file write — no `exec`, no TOTP required.

The queue processor picks it up within 1 minute and writes the result to
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
- **`path`**: full SharePoint path from the drive root, must start with `/`
- **`operation`**:
  - `create` — creates a new file; fails if file already exists
  - `update` — overwrites the entire file; fails if file does not exist
  - `append` — appends content to the end of an existing file
- **`content`**: full text content for create/update; text to append for append
- **`requested_at`**: ISO 8601 UTC timestamp

If the queue file already has pending entries, append your entry to the array.
If the file does not exist yet, write a fresh JSON array with your entry.

### Checking write results

Open `~/.openclaw/workspace/SHAREPOINT_RESULT.md` about 1 minute after queuing.
It records success or error for each processed operation, keyed by `id`.

---

## Common patterns

### "Read the Harken Health opportunity note"

1. Check `SHAREPOINT_INDEX.md` to confirm path.
2. Read `sharepoint-cache/Stackstone CRM/Opportunities/Harken Health.md` directly.
3. Note the sync timestamp at the top — if stale (>15 min old), the live file
   in SharePoint may have newer edits.

### "Update the Harken Health note with call notes"

Write to `~/.openclaw/sharepoint-queue.json`:

```json
[
  {
    "id": "sp-harken-update-20260413",
    "operation": "update",
    "path": "/Stackstone CRM/Opportunities/Harken Health.md",
    "content": "# Harken Health\n\n...(full updated content)...",
    "requested_at": "2026-04-13T10:00:00Z"
  }
]
```

Wait ~1 min, then read `SHAREPOINT_RESULT.md` to confirm success.

### "Create a new opportunity note for Croyde Medical"

Use `operation: "create"` with the full intended content.
The file will be created at the path you specify in SharePoint.

### "I can't see a file in the cache"

- Check `SHAREPOINT_INDEX.md` — it may be listed as skipped (wrong type or too large).
- Check `.manifest.json` for the reason.
- For non-`.md`/`.txt` files, content is not mirrored; only the path is indexed.

---

## Cache freshness

- Poller runs every 15 minutes via cron.
- If you need a fresh read of a file you suspect has just changed, note the
  sync timestamp in the cached file and tell the user if the data may be up to
  15 minutes old.
- There is no manual cache-refresh trigger; the cron schedule is the only
  refresh mechanism.

---

## Error states

| Symptom | Likely cause |
|---------|-------------|
| `SHAREPOINT_INDEX.md` is empty or missing | Poller has not run yet, or `SHAREPOINT_HOST` is not set in `.env` |
| Write result shows auth error | SharePoint token expired — run `python3 ~/.openclaw/integrations/microsoft-l1/sharepoint.py reauth` |
| File visible in index but not in cache | File type or size is not eligible for local mirror |
| Queue entry stays pending | Queue processor may not be running — check cron with `crontab -l` |
