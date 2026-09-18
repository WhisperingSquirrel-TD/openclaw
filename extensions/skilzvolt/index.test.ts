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

  it("keeps the expense boundary default-off even when SkilzVolt is enabled", async () => {
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

    expect(factories).toHaveLength(4);
    expect(factories.map((factory) => factory({ senderIsOwner: false }))).toEqual([
      null,
      null,
      null,
      null,
    ]);
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
      { name: "skilzvolt_workflow_proof", ownerOnly: true },
      { name: "skilzvolt_local_migration", ownerOnly: true },
      undefined,
    ]);

    const promptHook = hooks.find((hook) => hook.name === "before_prompt_build");
    const mainResult = (await promptHook?.handler(
      { prompt: "hello there" },
      { agentId: "main" },
    )) as { appendSystemContext: string; block?: boolean } | undefined;
    expect(mainResult).toMatchObject({
      appendSystemContext: expect.stringContaining("authoritative"),
    });
    // Catalogue fetch fails (network stubbed): reports an explicit degraded state, never stale
    // or guessed data.
    expect(mainResult?.appendSystemContext).toContain("unavailable");
    expect(mainResult?.block).toBeUndefined();
    const governedResult = (await promptHook?.handler(
      { prompt: "learn from this correction" },
      { agentId: "main" },
    )) as { block?: boolean } | undefined;
    expect(governedResult?.block).toBe(true);
    expect(await promptHook?.handler({}, { agentId: "other" })).toBeUndefined();
    expect(hooks.some((hook) => hook.name === "gateway_start")).toBe(true);
  });

  it("exposes the fixed expense boundary only for an owner after explicit opt-in", () => {
    const factories: OpenClawPluginToolFactory[] = [];
    const api = {
      pluginConfig: { agentIds: ["main"], expenseSharePointEnabled: true },
      registerTool: vi.fn((factory: OpenClawPluginToolFactory) => factories.push(factory)),
      on: vi.fn(),
      logger: { info: vi.fn(), warn: vi.fn() },
    } as unknown as OpenClawPluginApi;

    registerSkilzVolt(api);

    const expenseFactory = factories[3];
    expect(expenseFactory?.({ senderIsOwner: false })).toBeNull();
    expect(expenseFactory?.({ senderIsOwner: true })).toMatchObject({
      name: "expense_sharepoint",
      ownerOnly: true,
    });
  });
});
