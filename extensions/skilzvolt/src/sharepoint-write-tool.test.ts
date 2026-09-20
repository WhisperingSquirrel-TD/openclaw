import { describe, expect, it, vi } from "vitest";
import {
  createSharePointWriteTool,
  resolveSharePointWriterScript,
} from "./sharepoint-write-tool.js";

describe("SharePoint write tool", () => {
  it("resolves the fixed workspace writer", () => {
    expect(resolveSharePointWriterScript("/home/test/.openclaw/workspace")).toBe(
      "/home/test/.openclaw/workspace/scripts/sharepoint-queue-writer.py",
    );
  });

  it("passes only the bounded write request to the service writer", async () => {
    const run = vi.fn(async (request: unknown) => ({ queued: true, request }));
    const tool = createSharePointWriteTool({ run, workspaceDir: "/workspace" });

    await tool.execute("call-1", {
      operation: "append",
      path: "/Accounts/Example/Example - Current.md",
      content: "Next action: follow up",
    });

    expect(run).toHaveBeenCalledWith(
      {
        operation: "append",
        path: "/Accounts/Example/Example - Current.md",
        content: "Next action: follow up",
      },
      undefined,
    );
  });

  it("rejects unsafe paths before invoking the writer", async () => {
    const run = vi.fn();
    const tool = createSharePointWriteTool({ run, workspaceDir: "/workspace" });

    await expect(
      tool.execute("call-1", {
        operation: "update",
        path: "/Accounts/../secrets.md",
        content: "bad",
      }),
    ).rejects.toThrow(/safe SharePoint destination/);
    expect(run).not.toHaveBeenCalled();
  });
});