import type { OpenClawConfig } from "../../config/config.js";
import { createSubsystemLogger } from "../../logging/subsystem.js";
import {
  resolveExecApprovals,
  requestExecApprovalViaSocket,
  DEFAULT_EXEC_APPROVAL_TIMEOUT_MS,
} from "../exec-approvals.js";
import { isActionApproved, waitForApprovalWindow } from "../totp/totp-session.js";
import { logOutboundAudit } from "./audit-log.js";

const log = createSubsystemLogger("outbound/trust-gate");

const DEFAULT_REQUIRE_APPROVAL = ["message.send"];
const DEFAULT_TOTP_WAIT_MS = 120_000;

type TotpPromptCallback = (message: string) => void;
let onTotpPromptCallback: TotpPromptCallback | null = null;

export function setTotpPromptCallback(cb: TotpPromptCallback | null): void {
  onTotpPromptCallback = cb;
}

function emitPromptBeforeWait(message: string): void {
  if (onTotpPromptCallback) {
    try {
      onTotpPromptCallback(message);
    } catch {
      log.warn("TOTP prompt callback failed");
    }
  }
}

export type TrustGateResult = {
  allowed: boolean;
  decision?: "allow-once" | "allow-always" | "deny" | null;
  pendingTotp?: boolean;
  promptMessage?: string;
};

export function resolveTrustLevel(cfg: OpenClawConfig): number {
  return cfg.agents?.defaults?.trustLevel ?? 0;
}

export function resolveRequireApproval(cfg: OpenClawConfig): string[] {
  return cfg.agents?.defaults?.requireApproval ?? DEFAULT_REQUIRE_APPROVAL;
}

export function resolveApprovalMode(cfg: OpenClawConfig): "socket" | "totp" {
  return cfg.agents?.defaults?.approvalMode ?? "socket";
}

export function resolveTotpWindowMinutes(cfg: OpenClawConfig): number {
  return cfg.agents?.defaults?.totpWindowMinutes ?? 5;
}

export function shouldInterceptAction(cfg: OpenClawConfig, action: string): boolean {
  const trustLevel = resolveTrustLevel(cfg);
  if (trustLevel < 1) {
    return false;
  }
  const requireApproval = resolveRequireApproval(cfg);
  return requireApproval.includes(action);
}

async function requestApprovalViaSocket(params: {
  cfg: OpenClawConfig;
  channel: string;
  recipient: string;
  content: string;
  sessionId?: string | null;
}): Promise<TrustGateResult> {
  const { channel, recipient, content, sessionId } = params;
  try {
    const resolved = resolveExecApprovals();
    const decision = await requestExecApprovalViaSocket({
      socketPath: resolved.socketPath,
      token: resolved.token,
      request: {
        command: `message.send → ${channel}:${recipient}`,
        commandArgv: ["message.send", channel, recipient],
        host: "gateway",
        security: "deny",
        ask: "always",
        agentId: null,
        sessionKey: sessionId ?? null,
      },
      timeoutMs: DEFAULT_EXEC_APPROVAL_TIMEOUT_MS,
    });

    if (decision === "allow-once" || decision === "allow-always") {
      log.info("Trust gate (socket): message approved", { channel, recipient, decision });
      return { allowed: true, decision };
    }

    log.info("Trust gate (socket): message denied or expired", { channel, recipient, decision });
    logOutboundAudit({
      channel,
      recipient,
      content,
      blocked: true,
      blockReason: "trust_gate",
      sessionId: sessionId ?? null,
    });
    return { allowed: false, decision };
  } catch (err) {
    log.warn(`Trust gate (socket): approval request failed: ${String(err)}`);
    logOutboundAudit({
      channel,
      recipient,
      content,
      blocked: true,
      blockReason: "trust_gate",
      sessionId: sessionId ?? null,
    });
    return { allowed: false, decision: null };
  }
}

async function requestApprovalViaTotp(params: {
  cfg: OpenClawConfig;
  channel: string;
  recipient: string;
  content: string;
  sessionId?: string | null;
}): Promise<TrustGateResult> {
  const { cfg, channel, recipient, content, sessionId } = params;
  const windowMinutes = resolveTotpWindowMinutes(cfg);

  if (isActionApproved("message.send")) {
    log.info("Trust gate (TOTP): active approval window — message allowed", {
      channel,
      recipient,
    });
    return { allowed: true, decision: "allow-once" };
  }

  log.info("Trust gate (TOTP): no active approval window — requesting code", {
    channel,
    recipient,
    contentLength: content.length,
  });

  const contentPreview =
    content.length > 100 ? content.slice(0, 100) + "…" : content;

  const promptMessage =
    `🔐 Action requires approval: send message to ${channel}:${recipient}\n` +
    `Preview: ${contentPreview}\n\n` +
    `Send your 6-digit authenticator code to approve (window: ${windowMinutes} min).`;

  const promptResult: TrustGateResult = {
    allowed: false,
    decision: null,
    pendingTotp: true,
    promptMessage,
  };

  void emitPromptBeforeWait(promptMessage);

  const approved = await waitForApprovalWindow("message.send", DEFAULT_TOTP_WAIT_MS);

  if (approved) {
    log.info("Trust gate (TOTP): message approved via code", { channel, recipient });
    return { allowed: true, decision: "allow-once" };
  }

  log.info("Trust gate (TOTP): approval timed out or denied", { channel, recipient });
  logOutboundAudit({
    channel,
    recipient,
    content,
    blocked: true,
    blockReason: "trust_gate",
    sessionId: sessionId ?? null,
  });
  return promptResult;
}

export async function requestMessageSendApproval(params: {
  cfg: OpenClawConfig;
  channel: string;
  recipient: string;
  content: string;
  sessionId?: string | null;
}): Promise<TrustGateResult> {
  if (!shouldInterceptAction(params.cfg, "message.send")) {
    return { allowed: true };
  }

  const mode = resolveApprovalMode(params.cfg);

  if (mode === "totp") {
    return requestApprovalViaTotp(params);
  }

  return requestApprovalViaSocket(params);
}
