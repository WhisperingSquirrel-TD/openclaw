import { describe, expect, it, vi } from "vitest";
import { createCrmSharePointTool, resolveCrmBridgeScript } from "./crm-sharepoint-tool.js";

describe("CRM SharePoint bridge tool", () => {
  it("resolves the installed workspace handoff script without exposing a command argument", () => {
    expect(resolveCrmBridgeScript("/home/test/.openclaw/workspace")).toBe(
      "/home/test/.openclaw/workspace/scripts/crm-capture-handoff.py",
    );
  });

  it("only sends the bounded action to the fixed bridge", async () => {
    const run = vi.fn(async (request: { action: string }) => ({
      accepted: request.action === "run_pending",
      verified: false,
    }));
    const tool = createCrmSharePointTool({ run, workspaceDir: "/workspace" });

    await tool.execute("call-1", { action: "run_pending" });

    expect(run).toHaveBeenCalledWith({ action: "run_pending" }, undefined);
  });

  it("rejects unsupported actions before invoking the bridge", async () => {
    const run = vi.fn();
    const tool = createCrmSharePointTool({ run, workspaceDir: "/workspace" });

    await expect(tool.execute("call-1", { action: "shell" })).rejects.toThrow(
      /action must be one of/,
    );
    expect(run).not.toHaveBeenCalled();
  });
});