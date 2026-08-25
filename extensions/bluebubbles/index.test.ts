import { describe, expect, it, vi } from "vitest";

const handler = vi.fn(async () => true);

vi.mock("./src/channel.js", () => ({ bluebubblesPlugin: {} }));
vi.mock("./src/monitor.js", () => ({ handleBlueBubblesWebhookRequest: handler }));
vi.mock("./src/runtime.js", () => ({ setBlueBubblesRuntime: vi.fn() }));
vi.mock("./src/accounts.js", () => ({
  listBlueBubblesAccountIds: () => ["default"],
  resolveBlueBubblesAccount: () => ({ config: {} }),
}));
vi.mock("./src/monitor-shared.js", () => ({
  resolveWebhookPathFromConfig: () => "/bluebubbles-webhook",
}));

describe("BlueBubbles plugin HTTP route", () => {
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
    expect(route).toMatchObject({
      path: "/bluebubbles-webhook",
      auth: "plugin",
      match: "exact",
    });
    await route.handler({} as never, {} as never);
    expect(handler).toHaveBeenCalledOnce();
  });
});