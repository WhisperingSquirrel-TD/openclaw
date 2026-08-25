import { describe, expect, it, vi } from "vitest";

const handler = vi.fn(async () => true);

vi.mock("./src/channel.js", () => ({ zaloPlugin: {}, zaloDock: {} }));
vi.mock("./src/monitor.js", () => ({ handleZaloWebhookRequest: handler }));
vi.mock("./src/runtime.js", () => ({ setZaloRuntime: vi.fn() }));
vi.mock("./src/accounts.js", () => ({
  listZaloAccountIds: () => ["default"],
  resolveZaloAccount: () => ({ config: { webhookPath: "/zalo-hook" } }),
}));

describe("Zalo plugin HTTP route", () => {
  it("registers and forwards its exact plugin-authenticated webhook route", async () => {
    const plugin = (await import("./index.js")).default;
    const registerHttpRoute = vi.fn();
    plugin.register({
      config: {},
      runtime: {},
      registerChannel: vi.fn(),
      registerHttpRoute,
    } as never);

    const route = registerHttpRoute.mock.calls[0]?.[0];
    expect(route).toMatchObject({ path: "/zalo-hook", auth: "plugin", match: "exact" });
    await route.handler({} as never, {} as never);
    expect(handler).toHaveBeenCalledOnce();
  });
});