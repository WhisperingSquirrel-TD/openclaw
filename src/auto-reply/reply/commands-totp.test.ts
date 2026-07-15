import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  loadConfig: vi.fn(),
  loadTotpSecret: vi.fn(),
  verifyTotpCode: vi.fn(),
  isApprovalWindowActive: vi.fn(),
  getWindowStatus: vi.fn(),
  startApprovalWindow: vi.fn(),
  hasPendingApprovals: vi.fn(),
  rejectPendingApprovals: vi.fn(),
  closeApprovalWindow: vi.fn(),
}));

vi.mock("../../config/config.js", () => ({
  loadConfig: mocks.loadConfig,
}));
vi.mock("../../infra/totp/totp-setup.js", () => ({
  loadTotpSecret: mocks.loadTotpSecret,
  setupTotp: vi.fn(),
  isTotpConfigured: vi.fn(),
}));
vi.mock("../../infra/totp/totp.js", () => ({
  verifyTotpCode: mocks.verifyTotpCode,
}));
vi.mock("../../infra/totp/totp-session.js", () => ({
  startApprovalWindow: mocks.startApprovalWindow,
  getWindowStatus: mocks.getWindowStatus,
  closeApprovalWindow: mocks.closeApprovalWindow,
  rejectPendingApprovals: mocks.rejectPendingApprovals,
  hasPendingApprovals: mocks.hasPendingApprovals,
  isApprovalWindowActive: mocks.isApprovalWindowActive,
}));

import { handleTotpCodeInput, handleTotpPreGate } from "./commands-totp.js";
import type { HandleCommandsParams } from "./commands-types.js";

function buildParams(body: string): HandleCommandsParams {
  return {
    ctx: {
      Body: body,
      BodyForAgent: body,
      BodyStripped: body,
    },
    cfg: {},
    command: {
      surface: "telegram",
      channel: "telegram",
      ownerList: [],
      senderIsOwner: true,
      isAuthorizedSender: true,
      senderId: "owner",
      rawBodyNormalized: body,
      commandBodyNormalized: body,
    },
    directives: {},
    elevated: { enabled: false, allowed: false, failures: [] },
    sessionKey: "main",
    workspaceDir: "/tmp",
    defaultGroupActivation: () => "always" as const,
    resolvedVerboseLevel: "off",
    resolvedReasoningLevel: "off",
    resolveDefaultThinkingLevel: async () => undefined,
    provider: "openai-codex",
    model: "gpt-5.6-sol",
    contextTokens: 0,
    isGroup: false,
  } as unknown as HandleCommandsParams;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.loadConfig.mockReturnValue({
    agents: { defaults: { approvalMode: "totp", totpWindowMinutes: 10 } },
  });
  mocks.loadTotpSecret.mockResolvedValue("SECRET");
  mocks.isApprovalWindowActive.mockReturnValue(false);
  mocks.getWindowStatus.mockReturnValue(null);
  mocks.hasPendingApprovals.mockReturnValue(false);
  mocks.startApprovalWindow.mockReturnValue({ expiresAt: Date.now() + 600_000 });
});

describe("handleTotpCodeInput", () => {
  it("verifies a valid code and injects the gate-open note into BOTH BodyForAgent and BodyStripped", async () => {
    mocks.verifyTotpCode.mockReturnValue(true);
    const params = buildParams("123456");

    const result = await handleTotpCodeInput(params, true);

    expect(mocks.verifyTotpCode).toHaveBeenCalledWith("SECRET", "123456");
    expect(mocks.startApprovalWindow).toHaveBeenCalled();
    expect(result).toEqual({ shouldContinue: true });

    const ctx = params.ctx as Record<string, unknown>;
    // The agent prompt is built from BodyStripped (get-reply-run.ts), so the
    // note MUST land there — this is the regression that let the raw 6-digit
    // code reach the model instead of the verification result.
    expect(ctx.BodyStripped).toContain("TOTP GATE: ✅ Code verified");
    expect(ctx.BodyForAgent).toContain("TOTP GATE: ✅ Code verified");
    expect(ctx.BodyStripped).not.toContain("123456");
    expect(ctx.BodyForAgent).not.toContain("123456");
  });

  it("replies deterministically (no agent continuation) when a run was blocked at the gate", async () => {
    mocks.verifyTotpCode.mockReturnValue(true);
    mocks.hasPendingApprovals.mockReturnValue(true);
    const params = buildParams("123456");

    const result = await handleTotpCodeInput(params, true);

    expect(result?.shouldContinue).toBe(false);
    expect(result?.reply?.text).toContain("✅ Approved");
  });

  it("rejects an invalid code with a deterministic fail reply and never reaches the agent", async () => {
    mocks.verifyTotpCode.mockReturnValue(false);
    const params = buildParams("000000");

    const result = await handleTotpCodeInput(params, true);

    expect(result?.shouldContinue).toBe(false);
    expect(result?.reply?.text).toContain("❌ Invalid code");
    expect(mocks.startApprovalWindow).not.toHaveBeenCalled();
    // Body untouched — nothing continues to the agent anyway.
  });

  it("ignores non-6-digit messages", async () => {
    const params = buildParams("hello there");
    const result = await handleTotpCodeInput(params, true);
    expect(result).toBeNull();
    expect(mocks.verifyTotpCode).not.toHaveBeenCalled();
  });

  it("ignores codes when approvalMode is not totp", async () => {
    mocks.loadConfig.mockReturnValue({ agents: { defaults: { approvalMode: "socket" } } });
    const params = buildParams("123456");
    const result = await handleTotpCodeInput(params, true);
    expect(result).toBeNull();
    expect(mocks.verifyTotpCode).not.toHaveBeenCalled();
  });
});

describe("handleTotpPreGate", () => {
  it("does not pre-block or rewrite action messages when no approval window is active", async () => {
    const params = buildParams("send an email to John about the meeting");

    const result = await handleTotpPreGate(params, true);

    expect(result).toBeNull();
    const ctx = params.ctx as Record<string, unknown>;
    expect(ctx.BodyStripped).toBe("send an email to John about the meeting");
    expect(ctx.BodyForAgent).toBe("send an email to John about the meeting");
  });

  it("passes 6-digit codes through untouched so the code handler can verify them", async () => {
    const params = buildParams("123456");

    const result = await handleTotpPreGate(params, true);

    expect(result).toBeNull();
    const ctx = params.ctx as Record<string, unknown>;
    expect(ctx.BodyStripped).toBe("123456");
    expect(ctx.BodyForAgent).toBe("123456");
  });

  it("injects the PROCEED signal into BOTH fields when the window is already active", async () => {
    mocks.isApprovalWindowActive.mockReturnValue(true);
    mocks.getWindowStatus.mockReturnValue({
      remainingSeconds: 300,
      actions: ["message.send"],
    });
    const params = buildParams("send the report to Sarah");

    const result = await handleTotpPreGate(params, true);

    expect(result).toBeNull();
    const ctx = params.ctx as Record<string, unknown>;
    expect(ctx.BodyStripped).toContain("Approval window is ACTIVE");
    expect(ctx.BodyForAgent).toContain("Approval window is ACTIVE");
    expect(ctx.BodyStripped).toContain("send the report to Sarah");
  });
});
