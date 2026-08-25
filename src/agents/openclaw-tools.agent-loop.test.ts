import { describe, expect, it } from "vitest";
import { createOpenClawTools } from "./openclaw-tools.js";

describe("agent loop tool registration", () => {
  it("is available only to an owner parent session", () => {
    const ownerTools = createOpenClawTools({
      senderIsOwner: true,
      agentDir: "/tmp/openclaw-agent",
      sessionId: "parent-session",
      agentSessionKey: "agent:main:telegram:owner",
    });
    expect(ownerTools.some((tool) => tool.name === "agent_loop")).toBe(true);

    const nonOwnerTools = createOpenClawTools({
      senderIsOwner: false,
      agentDir: "/tmp/openclaw-agent",
      sessionId: "parent-session",
      agentSessionKey: "agent:main:telegram:guest",
    });
    expect(nonOwnerTools.some((tool) => tool.name === "agent_loop")).toBe(
      false,
    );
  });

  it("keeps the controller out of subagent tool lists", () => {
    const tools = createOpenClawTools({
      senderIsOwner: true,
      agentDir: "/tmp/openclaw-agent",
      sessionId: "subagent-session",
      agentSessionKey: "agent:main:subagent:worker",
    });
    expect(tools.some((tool) => tool.name === "agent_loop")).toBe(false);
  });
});
