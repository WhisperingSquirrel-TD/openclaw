import {
  finishContinuation,
  prepareContinuationAdvance,
  recoverContinuationWork,
} from "../../agents/continuation-loop.js";
import {
  enqueueFollowupRun,
  isContinuationAlreadyQueued,
} from "./queue/enqueue.js";
import { getExistingFollowupQueue } from "./queue/state.js";
import type { FollowupRun } from "./queue/types.js";

const CONTINUATION_QUEUE_SETTINGS = {
  mode: "followup" as const,
  debounceMs: 0,
  cap: 1,
  dropPolicy: "new" as const,
};

export type ContinuationScheduleResult = {
  notice?: string;
  scheduled: boolean;
  recovered?: boolean;
};

/**
 * The only place that turns durable continuation state into queue work.
 * Persisting the full queue envelope before enqueueing closes the crash window
 * between an agent turn finishing and the next turn becoming runnable.
 */
export async function scheduleContinuationTurn(params: {
  queueKey: string;
  followupRun: FollowupRun;
  completedWork?: { idempotencyKey: string; leaseId: string };
}): Promise<ContinuationScheduleResult> {
  const agentDir = params.followupRun.run.agentDir?.trim();
  const sessionId = params.followupRun.run.sessionId;
  if (!agentDir || !sessionId) {
    return { scheduled: false };
  }

  const activeQueue = getExistingFollowupQueue(params.queueKey);
  if (activeQueue && activeQueue.mode !== "followup") {
    await finishContinuation({
      agentDir,
      sessionId,
      status: "blocked",
      reason: `Continuation cannot safely enter an active ${activeQueue.mode} queue.`,
    });
    return {
      scheduled: false,
      notice:
        "Continuation paused because the current queue policy collects messages. Resume it after the queue is idle.",
    };
  }
  const advance = await prepareContinuationAdvance({
    agentDir,
    sessionId,
    completedWork: params.completedWork,
    queueKey: params.queueKey,
    queuedRunFactory: (next) => ({
      ...params.followupRun,
      prompt: next.prompt,
      messageId: undefined,
      summaryLine: `[Continuation ${next.state.turnsCompleted}/${next.state.maxTurns}]`,
      enqueuedAt: Date.now(),
      continuation: {
        idempotencyKey: next.idempotencyKey,
        generation: next.state.generation,
        queueKey: params.queueKey,
      },
    }),
  });
  if (advance.action === "none") {
    return { scheduled: false };
  }
  if (advance.action === "terminal") {
    return { scheduled: false, notice: advance.notice };
  }
  const nextRun = advance.state.work?.queuedRun as FollowupRun | undefined;
  if (!nextRun) {
    throw new Error("Continuation queue envelope was not persisted.");
  }
  const queued = enqueueFollowupRun(
    params.queueKey,
    nextRun,
    CONTINUATION_QUEUE_SETTINGS,
    "none",
    {
      preserveExistingSettings: true,
      activeContinuationIdempotencyKey: params.completedWork?.idempotencyKey,
    },
  );
  if (queued || isContinuationAlreadyQueued(params.queueKey, advance.idempotencyKey)) {
    return { scheduled: true, recovered: advance.recovered };
  }

  await finishContinuation({
    agentDir,
    sessionId,
    status: "blocked",
    reason: "Unable to reserve queue capacity for the next continuation turn.",
  });
  return {
    scheduled: false,
    notice:
      "Continuation paused: queue pressure prevented the next turn from being reserved. Resume it when ready.",
  };
}

/**
 * Rehydrates work that was fully persisted before a restart but never reached
 * the in-memory queue. The caller supplies the active queue key so a recovered
 * turn can only resume in its original conversation and routing context.
 */
export async function enqueueRecoveredContinuationTurns(params: {
  agentDir: string;
  queueKey: string;
}): Promise<number> {
  const recovered = await recoverContinuationWork({ agentDir: params.agentDir });
  let enqueued = 0;
  for (const entry of recovered) {
    if (entry.work.queueKey !== params.queueKey) {
      continue;
    }
    const queuedRun = entry.work.queuedRun as FollowupRun | undefined;
    if (!queuedRun?.continuation?.idempotencyKey) {
      continue;
    }
    if (
      enqueueFollowupRun(
        params.queueKey,
        queuedRun,
        CONTINUATION_QUEUE_SETTINGS,
        "none",
        { preserveExistingSettings: true },
      )
    ) {
      enqueued += 1;
    }
  }
  return enqueued;
}