# Task-System Email Dispatch

## Purpose

Task-system email delivery is allowed without a fresh TOTP prompt only after the owner has approved the prerequisite work and explicitly signed off the final draft. The task system, not the assistant client, is the authorization authority.

## Required server behaviour

1. Persist a canonical draft containing the sender, To/CC/BCC recipients, subject, body type and body, reply target, and immutable attachment identifiers or hashes.
2. Prevent generic task create/patch APIs from setting email approval, sign-off, permit, dispatch, or sent fields.
3. Present the canonical draft to the owner for final sign-off. Any draft change must invalidate approval.
4. When the owner signs off, issue a permit with `version: 1`, `audience: "openclaw.microsoft.email.send"`, `task_id`, `draft_id`, a random `jti`, integer `expires_at`, and `email_digest`.
5. Sign the permit (excluding `signature`) with HMAC-SHA256 using `TASK_SYSTEM_EMAIL_DISPATCH_KEY`. The sender and task system must receive the same secret through their service environment; it must never be exposed to the agent, tool inputs, logs, workspace files, or chat.
6. Expose only a dispatch request that accepts a draft identifier. The server reloads the canonical draft and either dispatches it with its own permit or rejects the request. It must never accept content, recipient, task-state, approval, or permit data from the assistant.
7. Consume the permit atomically before sending, retain the result for duplicate requests, and audit the task ID, draft ID, permit ID, decision, and provider correlation ID without storing email bodies or recipients in the audit log.

## Permit binding

The permit's `email_digest` is the SHA-256 hash of canonical JSON containing:

- normalized To, CC, and BCC recipients
- sender display name, subject, body type, and rendered body
- reply target and reply-all flag
- every attachment's file name, byte size, and SHA-256 hash. The sender reads attachment bytes once, then uses that same in-memory snapshot for both this fingerprint and the Graph upload, so a file swap after approval cannot alter the sent message.

The Microsoft sender rejects a missing, forged, expired, overly long-lived, altered, or previously used permit before calling Microsoft Graph.

## Direct email

Direct L1 email remains an `exec.run` operation and requires the normal TOTP approval window. Do not implement a command-line flag or task ID that claims an email is approved; only a verified permit grants task-system delivery.