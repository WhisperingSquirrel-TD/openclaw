import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  checkpointContinuation,
  finishContinuation,
  prepareContinuationAdvance,
  readContinuationState,
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
});
