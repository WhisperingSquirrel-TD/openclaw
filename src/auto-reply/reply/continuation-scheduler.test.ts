import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  claimContinuationWork,
  readContinuationState,
  startContinuation,
} from "../../agents/continuation-loop.js";
import { enqueueFollowupRun } from "./queue/enqueue.js";
import { FOLLOWUP_QUEUES } from "./queue/state.js";
import type { FollowupRun } from "./queue/types.js";
import { scheduleContinuationTurn } from "./continuation-scheduler.js";

const directories: string[] = [];

async function setup() {
  const agentDir = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-continuation-scheduler-"));
  directories.push(agentDir);
  return { agentDir, sessionId: "scheduler-session", queueKey: `continuation-${Date.now()}` };
}

function createRun(agentDir: string, sessionId: string): FollowupRun {
  return {
    prompt: "owner request",
    enqueuedAt: Date.now(),
    run: {
      agentId: "main",
      agentDir,
      sessionId,
      sessionKey: "agent:main:telegram:owner",
      sessionFile: "/tmp/session.jsonl",
      workspaceDir: "/tmp",
      config: {},
      provider: "test",
      model: "test-model",
      timeoutMs: 1_000,
      blockReplyBreak: "message_end",
      senderIsOwner: true,
    },
  };
}

afterEach(async () => {
  await Promise.all(directories.splice(0).map((directory) => fs.rm(directory, { recursive: true })));
  FOLLOWUP_QUEUES.clear();
});

describe("continuation scheduler", () => {
  it("uses one shared completion path for three consecutive continuation turns", async () => {
    const { agentDir, sessionId, queueKey } = await setup();
    const run = createRun(agentDir, sessionId);
    await startContinuation({
      agentDir,
      sessionId,
      sessionKey: run.run.sessionKey,
      objective: "Finish a three-step task.",
      maxTurns: 4,
    });

    const first = await scheduleContinuationTurn({ queueKey, followupRun: run });
    expect(first).toMatchObject({ scheduled: true });

    const queue = FOLLOWUP_QUEUES.get(queueKey);
    expect(queue?.items).toHaveLength(1);
    if (!queue) {
      return;
    }
    // This is what the drain does while the active callback executes.
    queue.draining = true;

    for (let turn = 1; turn <= 3; turn += 1) {
      const active = queue.items[0];
      const key = active?.continuation?.idempotencyKey;
      expect(key).toBeTruthy();
      if (!active || !key) {
        return;
      }
      const claim = await claimContinuationWork({
        agentDir,
        sessionId,
        idempotencyKey: key,
      });
      expect(claim.claimed).toBe(true);
      if (!claim.claimed) {
        return;
      }
      const scheduled = await scheduleContinuationTurn({
        queueKey,
        followupRun: active,
        completedWork: { idempotencyKey: key, leaseId: claim.lease.id },
      });
      expect(scheduled.scheduled).toBe(true);
      // The active item is removed only after its callback returns.
      queue.items.shift();
    }

    await expect(readContinuationState({ agentDir, sessionId })).resolves.toMatchObject({
      status: "active",
      turnsCompleted: 4,
      work: { status: "pending", turn: 4 },
    });
  });

  it("blocks continuation work when an idle queue has no safe capacity", async () => {
    const { agentDir, sessionId, queueKey } = await setup();
    const run = createRun(agentDir, sessionId);
    enqueueFollowupRun(
      queueKey,
      { ...run, prompt: "ordinary queued message" },
      { mode: "followup", debounceMs: 0, cap: 1, dropPolicy: "new" },
    );
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Do not displace a user message.",
    });

    await expect(scheduleContinuationTurn({ queueKey, followupRun: run })).resolves.toMatchObject({
      scheduled: false,
      notice: expect.stringContaining("queue pressure"),
    });
    await expect(readContinuationState({ agentDir, sessionId })).resolves.toMatchObject({
      status: "blocked",
    });
  });

  it("treats a recovered duplicate envelope as already scheduled instead of blocking it", async () => {
    const { agentDir, sessionId, queueKey } = await setup();
    const run = createRun(agentDir, sessionId);
    await startContinuation({ agentDir, sessionId, objective: "Recover idempotently." });

    await expect(scheduleContinuationTurn({ queueKey, followupRun: run })).resolves.toMatchObject({
      scheduled: true,
    });
    await expect(scheduleContinuationTurn({ queueKey, followupRun: run })).resolves.toMatchObject({
      scheduled: true,
    });
    await expect(readContinuationState({ agentDir, sessionId })).resolves.toMatchObject({
      status: "active",
      work: { status: "pending" },
    });
  });

  it("does not override an existing non-followup queue policy", async () => {
    const { agentDir, sessionId, queueKey } = await setup();
    const run = createRun(agentDir, sessionId);
    enqueueFollowupRun(
      queueKey,
      { ...run, prompt: "ordinary collected message" },
      { mode: "collect", debounceMs: 5_000, cap: 3, dropPolicy: "old" },
    );
    await startContinuation({ agentDir, sessionId, objective: "Respect queue policy." });

    await expect(scheduleContinuationTurn({ queueKey, followupRun: run })).resolves.toMatchObject({
      scheduled: false,
      notice: expect.stringContaining("queue policy"),
    });
    expect(FOLLOWUP_QUEUES.get(queueKey)).toMatchObject({
      mode: "collect",
      debounceMs: 5_000,
      cap: 3,
      dropPolicy: "old",
    });
  });
});