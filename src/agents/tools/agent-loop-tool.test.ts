import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { readContinuationState } from "../continuation-loop.js";
import { createAgentLoopTool } from "./agent-loop-tool.js";

const directories: string[] = [];

async function setup() {
  const agentDir = await fs.mkdtemp(
    path.join(os.tmpdir(), "openclaw-loop-tool-"),
  );
  directories.push(agentDir);
  return { agentDir, sessionId: "loop-tool-session" };
}

afterEach(async () => {
  await Promise.all(
    directories
      .splice(0)
      .map((directory) => fs.rm(directory, { recursive: true })),
  );
});

describe("agent_loop tool", () => {
  it("starts, checkpoints, and completes a bounded continuation", async () => {
    const { agentDir, sessionId } = await setup();
    const tool = createAgentLoopTool({
      agentDir,
      sessionId,
      sessionKey: "agent:main:telegram:owner",
      trustedOwner: true,
    });

    await tool.execute("start", {
      action: "start",
      objective: "Complete the bounded task.",
      maxTurns: 3,
      maxWallClockSeconds: 60,
    });
    await tool.execute("checkpoint", {
      action: "checkpoint",
      checkpoint: "First safe step completed.",
    });
    await tool.execute("complete", {
      action: "complete",
      reason: "Verified complete.",
    });

    await expect(
      readContinuationState({ agentDir, sessionId }),
    ).resolves.toMatchObject({
      objective: "Complete the bounded task.",
      checkpoint: "First safe step completed.",
      status: "completed",
      terminalReason: "Verified complete.",
    });
  });
});
