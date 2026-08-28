import { Command } from "commander";
import { describe, expect, it, vi } from "vitest";

// Regression guard: `openclaw skilzvolt login` writes credentials into a store resolved with no
// explicit agentDir, and the extension's token getter (createSkilzVoltAccessTokenGetter) reads
// back with no explicit agentDir either. If either side started passing a config-derived
// per-agent directory while the other kept the bare default, login would "succeed" while the
// extension kept reading an empty store. This test locks the CLI side to the bare-default
// contract regardless of what a "non-main" default agent config would otherwise resolve to.
const loginSkilzVolt = vi.fn(async (_ctx: Record<string, unknown>) => {});
const logoutSkilzVolt = vi.fn(() => true);
const getSkilzVoltStatus = vi.fn(() => ({ connected: false, reason: "not connected" }) as const);
const pollSkilzVoltUserCount = vi.fn(async () => ({
  ok: true as const,
  total: 438,
  sinceLast: 12,
  acknowledgementSucceeded: true as const,
  checkedAt: "2026-08-28T12:00:00.000Z",
  checkedAtEuropeLondon: "28 Aug 2026, 13:00:00 BST",
}));

vi.mock("../integrations/skilzvolt/connection.js", () => ({
  loginSkilzVolt,
  logoutSkilzVolt,
  getSkilzVoltStatus,
}));

vi.mock("../integrations/skilzvolt/user-count.js", () => ({
  pollSkilzVoltUserCount,
}));

vi.mock("../commands/onboard-helpers.js", () => ({
  openUrl: vi.fn(async () => true),
}));

vi.mock("../commands/oauth-env.js", () => ({
  isRemoteEnvironment: () => true,
}));

vi.mock("../wizard/clack-prompter.js", () => ({
  createClackPrompter: () => ({
    intro: vi.fn(async () => {}),
    outro: vi.fn(async () => {}),
    note: vi.fn(async () => {}),
    text: vi.fn(async () => "unused"),
    progress: () => ({ update: vi.fn(), stop: vi.fn() }),
  }),
}));

vi.mock("../runtime.js", () => ({
  defaultRuntime: {
    log: vi.fn(),
    error: vi.fn(),
    exit: (code: number) => {
      throw new Error(`__exit__:${code}`);
    },
  },
}));

const { registerSkilzVoltCli } = await import("./skilzvolt-cli.js");

function buildProgram(): Command {
  const program = new Command();
  program.exitOverride();
  registerSkilzVoltCli(program);
  return program;
}

describe("registerSkilzVoltCli", () => {
  it("logs in without passing an agentDir override", async () => {
    const program = buildProgram();
    await program.parseAsync(["node", "openclaw", "skilzvolt", "login"]);
    expect(loginSkilzVolt).toHaveBeenCalledTimes(1);
    const ctx = loginSkilzVolt.mock.calls[0][0];
    expect(ctx).not.toHaveProperty("agentDir");
  });

  it("checks status without passing an agentDir override", async () => {
    const program = buildProgram();
    await program.parseAsync(["node", "openclaw", "skilzvolt", "status"]);
    expect(getSkilzVoltStatus).toHaveBeenCalledWith(
      expect.not.objectContaining({ agentDir: expect.anything() }),
    );
  });

  it("logs out without passing an agentDir override", async () => {
    const program = buildProgram();
    await program.parseAsync(["node", "openclaw", "skilzvolt", "logout"]);
    expect(logoutSkilzVolt).toHaveBeenCalledWith();
  });

  it("supports machine-readable aggregate user-count polling", async () => {
    const program = buildProgram();
    await program.parseAsync(["node", "openclaw", "skilzvolt", "user-count", "--json"]);
    expect(pollSkilzVoltUserCount).toHaveBeenCalledTimes(1);
  });
});
