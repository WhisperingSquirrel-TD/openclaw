# Mail-reader reconciliation

## Scope

GitHub `main` at `9d783817ea19b6e518040055e135602863d71cfe` is one commit
ahead of the local known `origin/main` parent
`280de94aa9dbe1606e5d7feb90c34b06cb6527d8`. The commit changes only:

- `pi-services/external-email-reader/read_thread.py`
- `pi-services/trusted-email-reader/read_thread.py`

The files were compared through the GitHub connector API (`gh api`); no fetch,
merge, push, or remote code execution was used.

## Reconciled behavior

The useful remote changes are now present in both exact-thread readers:

- retain recipient and sent-time metadata, draft/sent/inbound status, and
  external raw-body plus deterministic authored-content projections;
- normalize Outlook HTML, entity escapes, reply separators, mobile separators,
  and horizontal-rule quote boundaries consistently;
- escape the Graph `conversationId` before using it in the exact bounded filter;
- reject returned messages outside the anchor conversation and enforce a
  separate 4 MiB raw-body resource ceiling;
- harden token handling for malformed `AccessToken` records and keep the
  external reader account fixed.

Local safety improvements were preserved rather than replaced:

- exact anchor lookup followed by one bounded conversation lookup, never
  mailbox-wide search;
- the approved-sender gate remains on the trusted anchor, while other
  participants are explicitly classified as untrusted;
- no write, draft creation, send, attachment download, link following, or
  token logging capability;
- the existing fail-closed 20-message and 64 KiB serialized broker-packet
  limits remain in force. The raw 4 MiB limit is an additional in-memory
  resource ceiling, not a replacement or truncation path.

## Verification

Dedicated tests cover the shared normalization contract, draft/sent
classification, authored-body extraction, and escaped exact-thread filters:

```text
python3 -m unittest \
  pi-services/trusted-email-reader/test_read_thread.py \
  pi-services/external-email-reader/test_read_thread.py
```
