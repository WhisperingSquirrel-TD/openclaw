---
name: reminder-delivery
description: Create, update or audit Tom-facing reminders with delivery proof, one retry, and a daily failure audit. Use for any new reminder or when a reminder is missed.
---

# Reminder Delivery

Read `reference/REMINDER-DELIVERY-SYSTEM.md` and `reference/reminder-delivery-registry.json` first.

## Required workflow
1. Give the reminder a stable ID and add its due time, message, priority, primary and verifier job IDs to the registry.
2. Create the primary as an isolated `agentTurn` job with Telegram `announce` delivery. Its only user-facing output is the reminder.
3. Create a verifier for five minutes later. It reads the primary job run and sends the same message once only if `status=ok` and `deliveryStatus=delivered` are not both proven.
4. Verify both jobs are live with `cron list` before confirming.
5. For critical reminders, ask Tom whether acknowledgement is required; do not assume Telegram delivery proves it was read.

## Rules
- Never use a main-session `systemEvent` as the sole delivery route for a Tom-facing reminder.
- A tracker entry or a cron creation response is not delivery proof.
- Never silently suppress or abandon a reminder in quiet hours; schedule the agreed deferred time explicitly if it should wait.
- The audit reports only primary-and-retry failures, never clean routine reminders.

## Completion
State the due time, retry time, and live primary/verifier IDs. If either delivery route is missing, call the reminder incomplete.
