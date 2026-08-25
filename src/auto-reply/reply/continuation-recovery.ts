import {
  nextContinuationRecoveryAt,
  recoverContinuationWork,
} from "../../agents/continuation-loop.js";
import { createFollowupRunner } from "./followup-runner.js";
import { enqueueFollowupRun } from "./queue/enqueue.js";
import { scheduleFollowupDrain } from "./queue/drain.js";
import type { FollowupRun } from "./queue/types.js";
import type { TypingController } from "./typing.js";

const RECOVERY_QUEUE_SETTINGS = {
  mode: "followup" as const,
  debounceMs: 0,
  cap: 1,
  dropPolicy: "new" as const,
};

const RECOVERY_TYPING: TypingController = {
  onReplyStart: async () => {},
  startTypingLoop: async () => {},
  startTypingOnText: async () => {},
  refreshTypingTtl: () => {},
  isActive: () => false,
  markRunComplete: () => {},
  markDispatchIdle: () => {},
  cleanup: () => {},
};

const recoveryRetryTimers = new Map<string, NodeJS.Timeout>();

/**
 * Rebuilds the in-memory drain from persisted continuation envelopes. This is
 * intentionally independent of inbound traffic: after a gateway restart,
 * approved work resumes through its original routing metadata rather than
 * waiting for the owner to send another message.
 */
export async function recoverContinuationQueues(params: {
  agentDirs: Iterable<string>;
  onError?: (message: string) => void;
}): Promise<number> {
  let enqueued = 0;
  const agentDirs = [...new Set([...params.agentDirs].map((agentDir) => agentDir.trim()).filter(Boolean))];
  const retryKey = agentDirs.toSorted().join("\n");
  const existingRetry = recoveryRetryTimers.get(retryKey);
  if (existingRetry) {
    clearTimeout(existingRetry);
    recoveryRetryTimers.delete(retryKey);
  }
  let earliestLeaseExpiry: number | undefined;
  for (const agentDir of agentDirs) {
    let recovered;
    try {
      recovered = await recoverContinuationWork({ agentDir });
    } catch (error) {
      params.onError?.(`continuation recovery scan failed for ${agentDir}: ${String(error)}`);
      continue;
    }
    for (const entry of recovered) {
      const queued = entry.work.queuedRun as FollowupRun | undefined;
      const queueKey = entry.work.queueKey;
      if (!queued || !queueKey || !queued.continuation?.idempotencyKey) {
        continue;
      }
      const runner = createFollowupRunner({
        typing: RECOVERY_TYPING,
        typingMode: "never",
        defaultModel: queued.run.model,
      });
      const queuedNow = enqueueFollowupRun(
        queueKey,
        queued,
        RECOVERY_QUEUE_SETTINGS,
        "none",
        { preserveExistingSettings: true },
      );
      if (!queuedNow) {
        continue;
      }
      enqueued += 1;
      scheduleFollowupDrain(queueKey, runner);
    }
    const nextRetry = await nextContinuationRecoveryAt({ agentDir });
    if (nextRetry != null && (earliestLeaseExpiry == null || nextRetry < earliestLeaseExpiry)) {
      earliestLeaseExpiry = nextRetry;
    }
  }
  if (earliestLeaseExpiry != null) {
    const delayMs = Math.max(1_000, earliestLeaseExpiry - Date.now() + 50);
    const retry = setTimeout(() => {
      recoveryRetryTimers.delete(retryKey);
      void recoverContinuationQueues(params);
    }, delayMs);
    retry.unref?.();
    recoveryRetryTimers.set(retryKey, retry);
  }
  return enqueued;
}