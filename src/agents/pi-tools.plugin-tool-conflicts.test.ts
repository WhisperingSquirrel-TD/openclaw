import { describe, expect, it, vi } from "vitest";

const { resolvePluginToolsMock } = vi.hoisted(() => ({
  resolvePluginToolsMock: vi.fn<(params: unknown) => unknown[]>(() => []),
}));

vi.mock("../plugins/tools.js", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../plugins/tools.js")>();
  return {
    ...mod,
    resolvePluginTools: resolvePluginToolsMock,
  };
});

import { createOpenClawCodingTools } from "./pi-tools.js";

describe("createOpenClawCodingTools plugin conflict protection", () => {
  it("passes existing core tool names into plugin resolution", () => {
    createOpenClawCodingTools({ senderIsOwner: true });

    expect(resolvePluginToolsMock).toHaveBeenCalledWith(
      expect.objectContaining({
        existingToolNames: expect.any(Set),
      }),
    );

    const call = resolvePluginToolsMock.mock.calls.at(-1)?.[0] as
      | { existingToolNames?: Set<string> }
      | undefined;

    expect(call?.existingToolNames?.has("read")).toBe(true);
    expect(call?.existingToolNames?.has("exec")).toBe(true);
    expect(call?.existingToolNames?.has("process")).toBe(true);
  });
});
