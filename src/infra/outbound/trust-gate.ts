import type { OpenClawConfig } from "../../config/config.js";
import { createSubsystemLogger } from "../../logging/subsystem.js";
import {
  resolveExecApprovals,
  requestExecApprovalViaSocket,
  DEFAULT_EXEC_APPROVAL_TIMEOUT_MS,
} from "../exec-approvals.js";
import { logOutboundAudit } from "./audit-log.js";

const log = createSubsystemLogger("outbound/trust-gate");

const DEFAULT_REQUIRE_APPROVAL = ["message.send"];

export type TrustGateResult = {
  allowed: boolean;
  decision?: "allow-once" | "allow-always" | "deny" | null;
};

export function resolveTrustLevel(cfg: OpenClawConfig): number {
  return cfg.agents?.defaults?.trustLevel ?? 0;
}

export function resolveRequireApproval(cfg: OpenClawConfig): string[] {
  return cfg.agents?.defaults?.requireApproval ?? DEFAULT_REQUIRE_APPROVAL;
}

export function shouldInterceptAction(cfg: OpenClawConfig, action: string): boolean {
  const trustLevel = resolveTrustLevel(cfg);
  if (trustLevel < 1) {
    return false;
  }
  const requireApproval = resolveRequireApproval(cfg);
  return requireApproval.includes(action);
}

export async function requestMessageSendApproval(params: {
  cfg: OpenClawConfig;
  channel: string;
  recipient: string;
  content: string;
  sessionId?: string | null;
}): Promise<TrustGateResult> {
  const { cfg, channel, recipient, content, sessionId } = params;

  if (!shouldInterceptAction(cfg, "message.send")) {
    return { allowed: true };
  }

  log.info("Trust gate: holding outbound message for approval", {
    channel,
    recipient,
    contentLength: content.length,
  });

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
      log.info("Trust gate: message approved", { channel, recipient, decision });
      return { allowed: true, decision };
    }

    log.info("Trust gate: message denied or expired", { channel, recipient, decision });
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
    log.warn(`Trust gate: approval request failed: ${String(err)}`);
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
