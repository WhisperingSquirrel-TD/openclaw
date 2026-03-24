import { loadConfig } from "../../config/config.js";
import { logVerbose } from "../../globals.js";
import { loadTotpSecret, setupTotp, isTotpConfigured } from "../../infra/totp/totp-setup.js";
import { verifyTotpCode } from "../../infra/totp/totp.js";
import {
  startApprovalWindow,
  getWindowStatus,
  closeApprovalWindow,
  rejectPendingApprovals,
  hasPendingApprovals,
  isApprovalWindowActive,
} from "../../infra/totp/totp-session.js";
import type { CommandHandler } from "./commands-types.js";

const TOTP_SETUP_COMMAND = "/totp-setup";
const TOTP_STATUS_COMMAND = "/totp-status";
const TOTP_LOCK_COMMAND = "/totp-lock";

export const handleTotpSetupCommand: CommandHandler = async (params, allowTextCommands) => {
  if (!allowTextCommands) {
    return null;
  }
  const normalized = params.command.commandBodyNormalized;
  if (!normalized.toLowerCase().startsWith(TOTP_SETUP_COMMAND)) {
    return null;
  }
  if (!params.command.isAuthorizedSender) {
    logVerbose(
      `Ignoring /totp-setup from unauthorized sender: ${params.command.senderId || "<unknown>"}`,
    );
    return { shouldContinue: false };
  }

  const rest = normalized.slice(TOTP_SETUP_COMMAND.length).trim();
  const accountName = rest || "OpenClaw-L1";

  try {
    const result = await setupTotp(accountName);
    return {
      shouldContinue: false,
      reply: {
        text:
          `🔐 TOTP setup complete.\n\n` +
          `Scan this URI in your authenticator app (Google Authenticator, Authy, etc.):\n\n` +
          `\`${result.uri}\`\n\n` +
          `Or enter this secret manually: \`${result.secret}\`\n\n` +
          `⚠️ Save this secret — it cannot be shown again. ` +
          `Once set up, send a 6-digit code to approve gated actions.`,
      },
    };
  } catch (err) {
    return {
      shouldContinue: false,
      reply: { text: `❌ TOTP setup failed: ${String(err)}` },
    };
  }
};

export const handleTotpStatusCommand: CommandHandler = async (params, allowTextCommands) => {
  if (!allowTextCommands) {
    return null;
  }
  const normalized = params.command.commandBodyNormalized;
  if (!normalized.toLowerCase().startsWith(TOTP_STATUS_COMMAND)) {
    return null;
  }
  if (!params.command.isAuthorizedSender) {
    return { shouldContinue: false };
  }

  const configured = await isTotpConfigured();
  const status = getWindowStatus();

  if (!configured) {
    return {
      shouldContinue: false,
      reply: { text: "🔐 TOTP not configured. Run /totp-setup to get started." },
    };
  }

  if (!status) {
    return {
      shouldContinue: false,
      reply: { text: "🔐 TOTP configured. No active approval window. Send a 6-digit code to open one." },
    };
  }

  const mins = Math.floor(status.remainingSeconds / 60);
  const secs = status.remainingSeconds % 60;
  return {
    shouldContinue: false,
    reply: {
      text:
        `🔐 TOTP approval window active.\n` +
        `Remaining: ${mins}m ${secs}s\n` +
        `Approved actions: ${status.actions.join(", ")}`,
    },
  };
};

export const handleTotpLockCommand: CommandHandler = async (params, allowTextCommands) => {
  if (!allowTextCommands) {
    return null;
  }
  const normalized = params.command.commandBodyNormalized;
  if (!normalized.toLowerCase().startsWith(TOTP_LOCK_COMMAND)) {
    return null;
  }
  if (!params.command.isAuthorizedSender) {
    return { shouldContinue: false };
  }

  closeApprovalWindow();
  return {
    shouldContinue: false,
    reply: { text: "🔒 Approval window closed. All gated actions now require a fresh code." },
  };
};

/**
 * Pre-gate handler — fires as the very first step on any plain message from an
 * authorised sender when approvalMode is "totp" and no approval window is active.
 * Immediately prompts for a TOTP code and halts the message so L1 never starts
 * reasoning until the gate is open. The user sends their code, gets ✅ Approved,
 * then resends their original message — which passes straight through to L1.
 */
export const handleTotpPreGate: CommandHandler = async (params, allowTextCommands) => {
  if (!allowTextCommands) return null;
  if (!params.command.isAuthorizedSender) return null;

  const cfg = loadConfig();
  const approvalMode = cfg.agents?.defaults?.approvalMode;
  if (approvalMode !== "totp") return null;

  // Already open — nothing to do.
  if (isApprovalWindowActive()) return null;

  const normalized = params.command.commandBodyNormalized.trim();

  // Let TOTP codes and slash commands pass through to their own handlers.
  if (/^\d{6}$/.test(normalized)) return null;
  if (normalized.startsWith("/")) return null;

  // No active window and this is a real message — ask for TOTP immediately.
  logVerbose("TOTP pre-gate: no active window, prompting for code before dispatching to L1");
  return {
    shouldContinue: false,
    reply: {
      text:
        "🔐 Send your TOTP code to open the approval gate.\n" +
        "Once you see ✅ Approved, resend your message and I'll get straight to it.",
    },
  };
};

export const handleTotpCodeInput: CommandHandler = async (params, allowTextCommands) => {
  const normalized = params.command.commandBodyNormalized.trim();
  const looksLikeTotpCode = /^\d{6}$/.test(normalized);

  if (!allowTextCommands) {
    if (looksLikeTotpCode) {
      logVerbose(`TOTP code input skipped: text commands not allowed for this channel`);
    }
    return null;
  }

  if (!looksLikeTotpCode) {
    return null;
  }

  if (!params.command.isAuthorizedSender) {
    logVerbose(
      `Ignoring TOTP code from unauthorized sender: ${params.command.senderId || "<unknown>"}`,
    );
    return null;
  }

  const cfg = loadConfig();
  const approvalMode = cfg.agents?.defaults?.approvalMode;
  if (approvalMode !== "totp") {
    logVerbose(
      `TOTP code input ignored: approvalMode is "${approvalMode ?? "socket"}", not "totp"`,
    );
    return null;
  }

  const secret = await loadTotpSecret();
  if (!secret) {
    return {
      shouldContinue: false,
      reply: { text: "🔐 TOTP not configured. Run /totp-setup first." },
    };
  }

  const valid = verifyTotpCode(secret, normalized);
  if (!valid) {
    const hadPending = hasPendingApprovals();
    rejectPendingApprovals();
    return {
      shouldContinue: false,
      reply: {
        text: hadPending
          ? "❌ Invalid code — pending action cancelled."
          : "❌ Invalid code.",
      },
    };
  }

  const windowMinutes = cfg.agents?.defaults?.totpWindowMinutes ?? 5;
  const { expiresAt } = startApprovalWindow({
    durationMinutes: windowMinutes,
    channel: params.command.channel,
  });

  const expiresAtStr = new Date(expiresAt).toLocaleTimeString();
  return {
    shouldContinue: false,
    reply: {
      text:
        `✅ Approved. Window open for ${windowMinutes} minute${windowMinutes > 1 ? "s" : ""} (until ${expiresAtStr}).\n` +
        `All gated actions will proceed without further codes until the window expires.`,
    },
  };
};
