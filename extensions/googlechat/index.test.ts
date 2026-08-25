import { describe, expect, it, vi } from "vitest";

const handler = vi.fn(async () => true);

vi.mock("./src/channel.js", () => ({ googlechatPlugin: {}, googlechatDock: {} }));
vi.mock("./src/monitor.js", () => ({
  handleGoogleChatWebhookRequest: handler,
  resolveGoogleChatWebhookPath: () => "/googlechat",
}));
vi.mock("./src/runtime.js", () => ({ setGoogleChatRuntime: vi.fn() }));
vi.mock("./src/accounts.js", () => ({
  listGoogleChatAccountIds: () => ["default"],
  resolveGoogleChatAccount: () => ({}),
}));

describe("Google Chat plugin HTTP route", () => {
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
    expect(route).toMatchObject({ path: "/googlechat", auth: "plugin", match: "exact" });
    await route.handler({} as never, {} as never);
    expect(handler).toHaveBeenCalledOnce();
  });
});