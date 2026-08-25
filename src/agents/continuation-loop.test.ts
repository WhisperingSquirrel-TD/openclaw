import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  claimContinuationWork,
  cancelContinuationForSession,
  completeContinuationWork,
  checkpointContinuation,
  finishContinuation,
  prepareContinuationAdvance,
  nextContinuationRecoveryAt,
  readContinuationState,
  recoverContinuationWork,
  persistContinuationQueuedRun,
  resumeContinuation,
  startContinuation,
} from "./continuation-loop.js";

const directories: string[] = [];

async function setup() {
  const agentDir = await fs.mkdtemp(
    path.join(os.tmpdir(), "openclaw-continuation-"),
  );
  directories.push(agentDir);
  return { agentDir, sessionId: "session-1" };
}

afterEach(async () => {
  await Promise.all(
    directories
      .splice(0)
      .map((directory) => fs.rm(directory, { recursive: true })),
  );
});

describe("continuation loop state", () => {
  it("persists bounded progress and emits compact continuation prompts", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      sessionKey: "agent:main:telegram:owner",
      objective: "Finish the report and verify it.",
      checkpoint: "Outline created.",
      maxTurns: 2,
      maxWallClockSeconds: 60,
      now: 1_000,
    });

    const first = await prepareContinuationAdvance({
      agentDir,
      sessionId,
      now: 2_000,
    });
    expect(first).toMatchObject({
      action: "continue",
      state: { turnsCompleted: 1, maxTurns: 2, status: "active" },
    });
    if (first.action === "continue") {
      expect(first.prompt).toContain("Finish the report and verify it.");
      expect(first.prompt).toContain(
        "Latest compact checkpoint: Outline created.",
      );
      expect(first.prompt).toContain("Use subagents only for isolated work");
    }

    await checkpointContinuation({
      agentDir,
      sessionId,
      checkpoint: "Draft is complete; checking figures.",
      now: 3_000,
    });
    const second = await prepareContinuationAdvance({
      agentDir,
      sessionId,
      now: 4_000,
    });
    expect(second).toMatchObject({
      action: "continue",
      state: { turnsCompleted: 2 },
    });

    const limit = await prepareContinuationAdvance({
      agentDir,
      sessionId,
      now: 5_000,
    });
    expect(limit).toMatchObject({
      action: "terminal",
      state: { status: "limit_reached" },
    });
    expect(
      (await readContinuationState({ agentDir, sessionId }))?.checkpoint,
    ).toBe("Draft is complete; checking figures.");
  });

  it("stops at the wall-clock deadline without scheduling another turn", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Check the deployment.",
      maxWallClockSeconds: 30,
      now: 1_000,
    });

    const result = await prepareContinuationAdvance({
      agentDir,
      sessionId,
      now: 31_000,
    });
    expect(result).toMatchObject({
      action: "terminal",
      state: { status: "expired" },
    });
  });

  it("does not resume after a human or model records a terminal state", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Wait for approval.",
      now: 1_000,
    });
    await finishContinuation({
      agentDir,
      sessionId,
      status: "blocked",
      reason: "Approval is required.",
      now: 2_000,
    });

    await expect(
      prepareContinuationAdvance({ agentDir, sessionId, now: 3_000 }),
    ).resolves.toEqual({
      action: "none",
    });
  });

  it("resumes a terminal continuation with a fresh bounded budget", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Continue after review.",
      maxTurns: 2,
      now: 1_000,
    });
    await finishContinuation({
      agentDir,
      sessionId,
      status: "blocked",
      now: 2_000,
    });

    const resumed = await resumeContinuation({
      agentDir,
      sessionId,
      maxTurns: 3,
      maxWallClockSeconds: 60,
      now: 3_000,
    });
    expect(resumed).toMatchObject({
      status: "active",
      turnsCompleted: 0,
      maxTurns: 3,
    });
    await expect(
      prepareContinuationAdvance({ agentDir, sessionId, now: 4_000 }),
    ).resolves.toMatchObject({
      action: "continue",
      state: { turnsCompleted: 1 },
    });
  });

  it("supports more than two completed turns through the same persisted path", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Complete several safe steps.",
      maxTurns: 4,
      now: 1_000,
    });

    for (let turn = 1; turn <= 3; turn += 1) {
      const advance = await prepareContinuationAdvance({
        agentDir,
        sessionId,
        now: 1_000 + turn * 1_000,
      });
      expect(advance).toMatchObject({
        action: "continue",
        state: { turnsCompleted: turn },
      });
      await checkpointContinuation({
        agentDir,
        sessionId,
        checkpoint: `Completed step ${turn}.`,
        now: 1_500 + turn * 1_000,
      });
    }

    await expect(readContinuationState({ agentDir, sessionId })).resolves.toMatchObject({
      status: "active",
      turnsCompleted: 3,
      checkpoint: "Completed step 3.",
    });
  });

  it("recovers durable queued work after a crash between queue persistence and execution", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Recover after restart.",
      now: 1_000,
    });
    const advance = await prepareContinuationAdvance({ agentDir, sessionId, now: 2_000 });
    expect(advance.action).toBe("continue");
    if (advance.action !== "continue") {
      return;
    }
    await persistContinuationQueuedRun({
      agentDir,
      sessionId,
      idempotencyKey: advance.idempotencyKey,
      queueKey: "agent:main:telegram:owner",
      queuedRun: { prompt: advance.prompt, continuation: { idempotencyKey: advance.idempotencyKey } },
      now: 2_100,
    });

    const recovered = await recoverContinuationWork({ agentDir, now: 3_000 });
    expect(recovered).toHaveLength(1);
    expect(recovered[0]).toMatchObject({
      state: { status: "active", turnsCompleted: 1 },
      work: {
        idempotencyKey: advance.idempotencyKey,
        status: "pending",
        queueKey: "agent:main:telegram:owner",
      },
    });
  });

  it("leases work to exactly one concurrent runner and rejects stale completion", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Avoid duplicate work.",
      now: 1_000,
    });
    const advance = await prepareContinuationAdvance({ agentDir, sessionId, now: 2_000 });
    expect(advance.action).toBe("continue");
    if (advance.action !== "continue") {
      return;
    }

    const claims = await Promise.all(
      Array.from({ length: 4 }, () =>
        claimContinuationWork({
          agentDir,
          sessionId,
          idempotencyKey: advance.idempotencyKey,
          now: 3_000,
        }),
      ),
    );
    const winner = claims.find((claim) => claim.claimed);
    expect(claims.filter((claim) => claim.claimed)).toHaveLength(1);
    if (!winner || !winner.claimed) {
      return;
    }

    await expect(
      completeContinuationWork({
        agentDir,
        sessionId,
        idempotencyKey: advance.idempotencyKey,
        leaseId: "stale-lease",
        now: 4_000,
      }),
    ).resolves.toBeUndefined();
    await expect(
      completeContinuationWork({
        agentDir,
        sessionId,
        idempotencyKey: advance.idempotencyKey,
        leaseId: winner.lease.id,
        now: 4_000,
      }),
    ).resolves.toMatchObject({ status: "active", work: undefined });
  });

  it("keeps cancellation terminal when stale work tries to complete later", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Cancel safely.",
      now: 1_000,
    });
    await finishContinuation({
      agentDir,
      sessionId,
      status: "cancelled",
      reason: "Owner stopped the work.",
      now: 2_000,
    });
    await expect(
      finishContinuation({
        agentDir,
        sessionId,
        status: "completed",
        reason: "Stale worker finished.",
        now: 3_000,
      }),
    ).rejects.toThrow("refusing to overwrite");
    await expect(readContinuationState({ agentDir, sessionId })).resolves.toMatchObject({
      status: "cancelled",
      terminalReason: "Owner stopped the work.",
    });
  });

  it("reports running lease expiry so startup recovery can retry after a crash", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Retry safely after a crashed worker.",
      now: 1_000,
    });
    const advance = await prepareContinuationAdvance({ agentDir, sessionId, now: 2_000 });
    expect(advance.action).toBe("continue");
    if (advance.action !== "continue") {
      return;
    }
    const claim = await claimContinuationWork({
      agentDir,
      sessionId,
      idempotencyKey: advance.idempotencyKey,
      leaseMs: 10_000,
      now: 3_000,
    });
    expect(claim.claimed).toBe(true);
    await expect(nextContinuationRecoveryAt({ agentDir, now: 3_001 })).resolves.toBe(13_000);
  });

  it("atomically replaces completed work with a recoverable queued successor", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({
      agentDir,
      sessionId,
      objective: "Survive every handoff crash window.",
      now: 1_000,
    });
    const queueKey = "agent:main:telegram:owner";
    const first = await prepareContinuationAdvance({
      agentDir,
      sessionId,
      now: 2_000,
      queueKey,
      queuedRunFactory: (advance) => ({
        prompt: advance.prompt,
        continuation: { idempotencyKey: advance.idempotencyKey },
      }),
    });
    expect(first.action).toBe("continue");
    if (first.action !== "continue") {
      return;
    }
    const claim = await claimContinuationWork({
      agentDir,
      sessionId,
      idempotencyKey: first.idempotencyKey,
      now: 3_000,
    });
    expect(claim.claimed).toBe(true);
    if (!claim.claimed) {
      return;
    }

    // This returns only after the old work was replaced by a successor with
    // its routing envelope. A crash before the in-memory enqueue is now safe.
    const successor = await prepareContinuationAdvance({
      agentDir,
      sessionId,
      now: 4_000,
      completedWork: { idempotencyKey: first.idempotencyKey, leaseId: claim.lease.id },
      queueKey,
      queuedRunFactory: (advance) => ({
        prompt: advance.prompt,
        continuation: { idempotencyKey: advance.idempotencyKey },
      }),
    });
    expect(successor).toMatchObject({ action: "continue", state: { turnsCompleted: 2 } });
    const recovered = await recoverContinuationWork({ agentDir, now: 5_000 });
    expect(recovered).toHaveLength(1);
    expect(recovered[0]?.work).toMatchObject({
      idempotencyKey: successor.action === "continue" ? successor.idempotencyKey : undefined,
      status: "pending",
      queueKey,
      queuedRun: expect.any(Object),
    });
  });

  it("cancels a leased worker durably before restart recovery can reclaim it", async () => {
    const { agentDir, sessionId } = await setup();
    await startContinuation({ agentDir, sessionId, objective: "Stop during recovery wait.", now: 1_000 });
    const advance = await prepareContinuationAdvance({ agentDir, sessionId, now: 2_000 });
    expect(advance.action).toBe("continue");
    if (advance.action !== "continue") {
      return;
    }
    await claimContinuationWork({
      agentDir,
      sessionId,
      idempotencyKey: advance.idempotencyKey,
      leaseMs: 10_000,
      now: 3_000,
    });
    await expect(
      cancelContinuationForSession({
        agentDir,
        sessionId,
        reason: "Owner stopped the session before recovery.",
      }),
    ).resolves.toBe(true);
    await expect(recoverContinuationWork({ agentDir, now: 14_000 })).resolves.toEqual([]);
    await expect(readContinuationState({ agentDir, sessionId })).resolves.toMatchObject({
      status: "cancelled",
    });
  });
});
