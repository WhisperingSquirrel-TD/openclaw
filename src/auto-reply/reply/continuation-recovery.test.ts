import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  persistContinuationQueuedRun,
  prepareContinuationAdvance,
  startContinuation,
} from "../../agents/continuation-loop.js";

const scheduleFollowupDrainMock = vi.fn();
const runnerMock = vi.fn(async () => {});

vi.mock("./queue/drain.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./queue/drain.js")>()),
  scheduleFollowupDrain: (...args: unknown[]) => scheduleFollowupDrainMock(...args),
}));
vi.mock("./followup-runner.js", () => ({
  createFollowupRunner: () => runnerMock,
}));

import { recoverContinuationQueues } from "./continuation-recovery.js";

const directories: string[] = [];

afterEach(async () => {
  scheduleFollowupDrainMock.mockReset();
  runnerMock.mockClear();
  await Promise.all(directories.splice(0).map((directory) => fs.rm(directory, { recursive: true })));
});

describe("recoverContinuationQueues", () => {
  it("rehydrates persisted work and starts its drain without waiting for an inbound message", async () => {
    const agentDir = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-continuation-recovery-"));
    directories.push(agentDir);
    const sessionId = "recovery-session";
    const queueKey = "agent:main:telegram:owner";
    const queuedRun = {
      prompt: "continue work",
      enqueuedAt: Date.now(),
      continuation: { idempotencyKey: "placeholder", generation: 1, queueKey },
      run: {
        agentId: "main",
        agentDir,
        sessionId,
        sessionKey: queueKey,
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
    await startContinuation({ agentDir, sessionId, objective: "Recover from restart." });
    const advance = await prepareContinuationAdvance({ agentDir, sessionId });
    expect(advance.action).toBe("continue");
    if (advance.action !== "continue") {
      return;
    }
    queuedRun.continuation.idempotencyKey = advance.idempotencyKey;
    await persistContinuationQueuedRun({
      agentDir,
      sessionId,
      idempotencyKey: advance.idempotencyKey,
      queueKey,
      queuedRun,
    });

    await expect(recoverContinuationQueues({ agentDirs: [agentDir] })).resolves.toBe(1);
    expect(scheduleFollowupDrainMock).toHaveBeenCalledWith(queueKey, runnerMock);
  });
});