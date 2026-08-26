import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OpenClawPluginApi, OpenClawPluginToolFactory } from "../../src/plugins/types.js";
import registerSkilzVolt from "./index.js";

describe("SkilzVolt plugin registration", () => {
  beforeEach(() => {
    // The catalogue bootstrap call happens inside before_prompt_build; stub fetch so tests never
    // hit the real network and instead exercise the explicit degraded-mode reporting path.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network disabled in test");
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not expose either native tool to non-owner senders", async () => {
    const factories: OpenClawPluginToolFactory[] = [];
    const hooks: Array<{
      name: string;
      handler: (...args: unknown[]) => unknown;
    }> = [];
    const api = {
      pluginConfig: { agentIds: ["main"] },
      registerTool: vi.fn((factory: OpenClawPluginToolFactory) => factories.push(factory)),
      on: vi.fn((name: string, handler: (...args: unknown[]) => unknown) =>
        hooks.push({ name, handler }),
      ),
      logger: { info: vi.fn() },
    } as unknown as OpenClawPluginApi;

    registerSkilzVolt(api);

    expect(factories).toHaveLength(2);
    expect(factories.map((factory) => factory({ senderIsOwner: false }))).toEqual([null, null]);
    expect(
      factories
        .map((factory) => factory({ senderIsOwner: true }))
        .map((tool) => {
          if (!tool || Array.isArray(tool)) {
            return undefined;
          }
          return { name: tool.name, ownerOnly: tool.ownerOnly };
        }),
    ).toEqual([
      { name: "skilzvolt", ownerOnly: true },
      { name: "skilzvolt_local_migration", ownerOnly: true },
    ]);

    const promptHook = hooks.find((hook) => hook.name === "before_prompt_build");
    const mainResult = (await promptHook?.handler({}, { agentId: "main" })) as
      | { appendSystemContext: string }
      | undefined;
    expect(mainResult).toMatchObject({
      appendSystemContext: expect.stringContaining("authoritative"),
    });
    // Catalogue fetch fails (network stubbed): reports an explicit degraded state, never stale
    // or guessed data.
    expect(mainResult?.appendSystemContext).toContain("unavailable");
    expect(await promptHook?.handler({}, { agentId: "other" })).toBeUndefined();
  });
});
