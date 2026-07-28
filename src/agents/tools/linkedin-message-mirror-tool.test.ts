import { describe, expect, it } from "vitest";
import { createLinkedInMessageMirrorTool } from "./linkedin-message-mirror-tool.js";

function detailsOf(result: unknown) {
  return (result as { details?: unknown }).details as Record<string, unknown>;
}

describe("linkedin_message_mirror tool", () => {
  it("exposes only the fixed read-only LinkedIn mirror actions", () => {
    const tool = createLinkedInMessageMirrorTool();
    expect(tool.name).toBe("linkedin_message_mirror");
    expect(tool.ownerOnly).toBe(true);
    expect(tool.description).toContain("read-only");
    expect(tool.description).toContain("never sends LinkedIn messages");

    const parameters = tool.parameters as {
      properties?: { action?: { anyOf?: Array<{ const?: string }>; enum?: string[] } };
      additionalProperties?: boolean;
    };
    const action = parameters.properties?.action;
    const values = new Set<string>();
    for (const variant of action?.anyOf ?? []) {
      if (typeof variant.const === "string") {
        values.add(variant.const);
      }
    }
    for (const value of action?.enum ?? []) {
      values.add(value);
    }

    expect(values).toEqual(
      new Set(["status", "capture", "route", "capture_and_route", "posts_status", "capture_posts"]),
    );
    expect(parameters.additionalProperties).toBe(false);
  });

  it("can report status without shell exec or external writes", async () => {
    const tool = createLinkedInMessageMirrorTool();
    const result = await tool.execute?.("test-call", { action: "status" });
    const details = detailsOf(result);

    expect(details.ok).toBe(true);
    expect(details.projectDir).toBe(
      "/home/tomdean88/.openclaw/workspace/projects/linkedin-message-mirror",
    );
    expect(details.scripts).toMatchObject({
      capture: true,
      route: true,
    });
  });

  it("exposes a bounded authored-post status action", async () => {
    const tool = createLinkedInMessageMirrorTool();
    const result = await tool.execute?.("test-posts-status", { action: "posts_status" });
    const details = detailsOf(result);
    expect(details.ok).toBe(true);
    expect(details.arbitraryExec).toBe(false);
    expect(details.script).toBe(true);
  });
});
