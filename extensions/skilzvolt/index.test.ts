import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OpenClawPluginApi, OpenClawPluginToolFactory } from "../../src/plugins/types.js";
import registerSkilzVolt from "./index.js";
import { SkilzVoltCatalogue } from "./src/catalogue.js";

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
    vi.restoreAllMocks();
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

    expect(factories).toHaveLength(5);
    expect(factories.map((factory) => factory({ senderIsOwner: false }))).toEqual([
      null,
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

  it("exposes the fixed CRM SharePoint boundary only for an owner after explicit opt-in", () => {
    const factories: OpenClawPluginToolFactory[] = [];
    const api = {
      pluginConfig: { agentIds: ["main"], crmSharePointEnabled: true },
      registerTool: vi.fn((factory: OpenClawPluginToolFactory) => factories.push(factory)),
      on: vi.fn(),
      logger: { info: vi.fn(), warn: vi.fn() },
    } as unknown as OpenClawPluginApi;

    registerSkilzVolt(api);

    const crmFactory = factories[4];
    expect(crmFactory?.({ senderIsOwner: false })).toBeNull();
    expect(crmFactory?.({ senderIsOwner: true })).toMatchObject({
      name: "crm_sharepoint",
      ownerOnly: true,
    });
  });

  it("lets the model resolve ambiguous intent instead of blocking before reply", async () => {
    const entries = [
      {
        skillId: "skill-estimate",
        workspaceId: "workspace-1",
        name: "estimation-breakdown",
        description: "Prepare a detailed estimate breakdown for a client",
        currentVersionId: "version-1",
      },
      {
        skillId: "skill-vendor",
        workspaceId: "workspace-1",
        name: "vendor-brief",
        description: "Prepare a vendor estimate breakdown for a client",
        currentVersionId: "version-1",
      },
    ];
    vi.spyOn(SkilzVoltCatalogue.prototype, "getLines").mockResolvedValue({
      ok: true,
      lines: entries.map((entry) => `- ${entry.name}: ${entry.description} [SkilzVolt]`),
    });
    vi.spyOn(SkilzVoltCatalogue.prototype, "getEntries").mockReturnValue(entries);
    const readCurrentSkill = vi.spyOn(SkilzVoltCatalogue.prototype, "readCurrentSkill");
    const hooks: Array<{
      name: string;
      handler: (...args: unknown[]) => unknown;
    }> = [];
    const api = {
      pluginConfig: { agentIds: ["main"] },
      registerTool: vi.fn(),
      on: vi.fn((name: string, handler: (...args: unknown[]) => unknown) =>
        hooks.push({ name, handler }),
      ),
      logger: { info: vi.fn(), warn: vi.fn() },
    } as unknown as OpenClawPluginApi;

    registerSkilzVolt(api);
    const promptHook = hooks.find((hook) => hook.name === "before_prompt_build");
    const result = (await promptHook?.handler(
      { prompt: "Prepare the client estimate breakdown" },
      { agentId: "main", runId: "run-1" },
    )) as { appendSystemContext?: string; block?: boolean } | undefined;

    expect(result?.block).toBeUndefined();
    expect(result?.appendSystemContext).toContain("Intent candidates only");
    expect(result?.appendSystemContext).toContain("Do not block");
    expect(readCurrentSkill).not.toHaveBeenCalled();
  });

  it("automatically loads the live CRM skill before allowing the typed side-effect tool", async () => {
    const entry = {
      skillId: "skill-crm-sharepoint",
      workspaceId: "workspace-1",
      name: "crm-sharepoint",
      description: "Governed CRM and SharePoint handoff",
      currentVersionId: "version-1",
    };
    const live = {
      entry,
      content: "CRM workflow",
      receipt: {
        receiptId: "receipt-1",
        skillId: entry.skillId,
        workspaceId: entry.workspaceId,
        versionId: entry.currentVersionId,
        contentSha256: "a".repeat(64),
        readAt: 1,
        purpose: "typed CRM SharePoint side-effect boundary",
        skillName: entry.name,
      },
      workflow: { requirements: [{ id: "processor-readback" }] },
    };
    vi.spyOn(SkilzVoltCatalogue.prototype, "getLines").mockResolvedValue({
      ok: true,
      lines: ["- crm-sharepoint: Governed CRM and SharePoint handoff [SkilzVolt]"],
    });
    vi.spyOn(SkilzVoltCatalogue.prototype, "getEntries").mockReturnValue([entry]);
    const readCurrentSkill = vi
      .spyOn(SkilzVoltCatalogue.prototype, "readCurrentSkill")
      .mockResolvedValue(live);
    const hooks: Array<{
      name: string;
      handler: (...args: unknown[]) => unknown;
    }> = [];
    const api = {
      pluginConfig: { agentIds: ["main"], crmSharePointEnabled: true },
      registerTool: vi.fn(),
      on: vi.fn((name: string, handler: (...args: unknown[]) => unknown) =>
        hooks.push({ name, handler }),
      ),
      logger: { info: vi.fn(), warn: vi.fn() },
    } as unknown as OpenClawPluginApi;

    registerSkilzVolt(api);
    const toolHook = hooks.find((hook) => hook.name === "before_tool_call");
    const result = await toolHook?.handler(
      { toolName: "crm_sharepoint", params: { action: "run_pending" } },
      { runId: "run-crm-1" },
    );

    expect(result).toMatchObject({ governanceAuthorized: true });
    expect(readCurrentSkill).toHaveBeenCalledTimes(1);
  });
});
