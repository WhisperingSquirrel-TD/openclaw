import { createDedupeCache } from "../../../infra/dedupe.js";
import { applyQueueDropPolicy, shouldSkipQueueItem } from "../../../utils/queue-helpers.js";
import { kickFollowupDrainIfIdle } from "./drain.js";
import { getExistingFollowupQueue, getFollowupQueue } from "./state.js";
import type { FollowupRun, QueueDedupeMode, QueueSettings } from "./types.js";

const RECENT_QUEUE_MESSAGE_IDS = createDedupeCache({
  ttlMs: 5 * 60 * 1000,
  maxSize: 10_000,
});

function buildRecentMessageIdKey(run: FollowupRun, queueKey: string): string | undefined {
  const messageId = run.messageId?.trim();
  if (!messageId) {
    return undefined;
  }
  // Use JSON tuple serialization to avoid delimiter-collision edge cases when
  // channel/to/account values contain "|" characters.
  return JSON.stringify([
    "queue",
    queueKey,
    run.originatingChannel ?? "",
    run.originatingTo ?? "",
    run.originatingAccountId ?? "",
    run.originatingThreadId == null ? "" : String(run.originatingThreadId),
    messageId,
  ]);
}

function isRunAlreadyQueued(
  run: FollowupRun,
  items: FollowupRun[],
  allowPromptFallback = false,
): boolean {
  const continuationKey = run.continuation?.idempotencyKey;
  if (continuationKey) {
    return items.some(
      (item) => item.continuation?.idempotencyKey === continuationKey,
    );
  }
  const hasSameRouting = (item: FollowupRun) =>
    item.originatingChannel === run.originatingChannel &&
    item.originatingTo === run.originatingTo &&
    item.originatingAccountId === run.originatingAccountId &&
    item.originatingThreadId === run.originatingThreadId;

  const messageId = run.messageId?.trim();
  if (messageId) {
    return items.some((item) => item.messageId?.trim() === messageId && hasSameRouting(item));
  }
  if (!allowPromptFallback) {
    return false;
  }
  return items.some((item) => item.prompt === run.prompt && hasSameRouting(item));
}

export function enqueueFollowupRun(
  key: string,
  run: FollowupRun,
  settings: QueueSettings,
  dedupeMode: QueueDedupeMode = "message-id",
  options?: {
    /** Do not let an internally scheduled continuation mutate user queue policy. */
    preserveExistingSettings?: boolean;
    /** The active continuation that is allowed to reserve its one successor slot. */
    activeContinuationIdempotencyKey?: string;
  },
): boolean {
  const queue =
    options?.preserveExistingSettings ? getExistingFollowupQueue(key) ?? getFollowupQueue(key, settings) : getFollowupQueue(key, settings);
  const recentMessageIdKey = dedupeMode !== "none" ? buildRecentMessageIdKey(run, key) : undefined;
  if (recentMessageIdKey && RECENT_QUEUE_MESSAGE_IDS.peek(recentMessageIdKey)) {
    return false;
  }

  const dedupe =
    run.continuation?.idempotencyKey || dedupeMode !== "none"
      ? (item: FollowupRun, items: FollowupRun[]) =>
          isRunAlreadyQueued(item, items, dedupeMode === "prompt")
      : undefined;

  // Deduplicate: skip if the same message is already queued.
  if (shouldSkipQueueItem({ item: run, items: queue.items, dedupe })) {
    return false;
  }

  queue.lastEnqueuedAt = Date.now();
  queue.lastRun = run.run;

  // A continuation schedules its successor while the drain still holds the
  // current item at index zero. Let that one successor reserve a slot rather
  // than treating the active item as queue pressure. Ordinary queue pressure
  // still follows the configured policy.
  const isSuccessorOfActiveContinuation =
    Boolean(run.continuation) &&
    queue.draining &&
    queue.items.length === queue.cap &&
    queue.items[0]?.continuation?.idempotencyKey === options?.activeContinuationIdempotencyKey;
  const shouldEnqueue =
    isSuccessorOfActiveContinuation ||
    applyQueueDropPolicy({
      queue,
      summarize: (item) => item.summaryLine?.trim() || item.prompt.trim(),
    });
  if (!shouldEnqueue) {
    return false;
  }

  queue.items.push(run);
  if (recentMessageIdKey) {
    RECENT_QUEUE_MESSAGE_IDS.check(recentMessageIdKey);
  }
  // If drain finished and deleted the queue before this item arrived, a new queue
  // object was created (draining: false) but nobody scheduled a drain for it.
  // Use the cached callback to restart the drain now.
  if (!queue.draining) {
    kickFollowupDrainIfIdle(key);
  }
  return true;
}

export function isContinuationAlreadyQueued(key: string, idempotencyKey: string): boolean {
  return getExistingFollowupQueue(key)?.items.some(
    (item) => item.continuation?.idempotencyKey === idempotencyKey,
  ) ?? false;
}

export function getFollowupQueueDepth(key: string): number {
  const queue = getExistingFollowupQueue(key);
  if (!queue) {
    return 0;
  }
  return queue.items.length;
}

export function resetRecentQueuedMessageIdDedupe(): void {
  RECENT_QUEUE_MESSAGE_IDS.clear();
}
