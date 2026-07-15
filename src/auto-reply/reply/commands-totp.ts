import { loadConfig } from "../../config/config.js";
import { logVerbose } from "../../globals.js";
import {
  startApprovalWindow,
  getWindowStatus,
  closeApprovalWindow,
  rejectPendingApprovals,
  hasPendingApprovals,
  isApprovalWindowActive,
} from "../../infra/totp/totp-session.js";
import { loadTotpSecret, setupTotp, isTotpConfigured } from "../../infra/totp/totp-setup.js";
import { verifyTotpCode } from "../../infra/totp/totp.js";
import type { CommandHandler } from "./commands-types.js";

/**
 * Replace the message body the agent will see. The agent prompt is built from
 * `BodyStripped` (see get-reply-run.ts: `sessionCtx.BodyStripped ?? sessionCtx.Body`),
 * so mutating `BodyForAgent` alone is NOT enough — the injected text must be
 * mirrored into `BodyStripped` or the model receives the original raw body.
 */
function setAgentBody(ctx: unknown, text: string): void {
  const mutable = ctx as Record<string, unknown>;
  mutable.BodyForAgent = text;
  mutable.BodyStripped = text;
}

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
      reply: {
        text: "🔐 TOTP configured. No active approval window. Send a 6-digit code to open one.",
      },
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
 * TOTP message handler.
 *
 * This no longer proactively blocks or rewrites ordinary user requests when no
 * approval window is active. Gating now happens at the actual protected action
 * layer (for example `exec.run` / `message.send`) so the assistant can still
 * plan, read, reason, update local files, and complete all ungated parts first.
 *
 * The only message-level injection retained here is the positive PROCEED signal
 * when a verified approval window is already active, plus pass-through for slash
 * commands and 6-digit codes so their own handlers can process them normally.
 */
export const handleTotpPreGate: CommandHandler = async (params, allowTextCommands) => {
  if (!allowTextCommands) {
    return null;
  }
  if (!params.command.isAuthorizedSender) {
    return null;
  }

  const cfg = loadConfig();
  const approvalMode = cfg.agents?.defaults?.approvalMode;
  if (approvalMode !== "totp") {
    return null;
  }

  // Window already open — inject a PROCEED signal so L1 doesn't ask for another code.
  if (isApprovalWindowActive()) {
    const status = getWindowStatus();
    const normalized = params.command.commandBodyNormalized.trim();
    const lower = normalized.toLowerCase();
    // Only inject for messages that look like they'll trigger a gated action.
    // Read-only requests don't need even a proceed signal.
    const READ_ONLY_FAST = [
      /^(check|read|show|list|what|how many|do i have|any |have i|is there|look at|find|search|get|fetch|pull up|display|view)\b/,
      /\b(check|read|show|list|look at|view)\b.*\b(email|inbox|mail|messages?|whatsapp)\b/,
    ];
    if (!READ_ONLY_FAST.some((re) => re.test(lower)) && status) {
      const expiresAtStr = new Date(
        Date.now() + status.remainingSeconds * 1000,
      ).toLocaleTimeString();
      logVerbose("TOTP pre-gate: window active — injecting PROCEED signal");
      const ctxRecord = params.ctx as Record<string, unknown> & typeof params.ctx;
      const original =
        (typeof ctxRecord.BodyStripped === "string" ? ctxRecord.BodyStripped : undefined) ??
        params.ctx.BodyForAgent ??
        params.ctx.Body ??
        normalized;
      setAgentBody(
        params.ctx,
        `[SYSTEM – TOTP GATE: ✅ Approval window is ACTIVE (expires ${expiresAtStr}). ` +
          `Execute the requested action IMMEDIATELY. ` +
          `Do NOT ask for a TOTP code — one has already been verified. ` +
          `Do NOT confirm, double-check, or pause. Just do it.]\n\n${original}`,
      );
    }
    return null;
  }

  const normalized = params.command.commandBodyNormalized.trim();

  // Let TOTP codes and slash commands pass through to their own handlers.
  if (/^\d{6}$/.test(normalized)) {
    return null;
  }
  if (normalized.startsWith("/")) {
    return null;
  }

  logVerbose("TOTP pre-gate: no active window — do not pre-block or rewrite the message");
  return null;
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
        text: hadPending ? "❌ Invalid code — pending action cancelled." : "❌ Invalid code.",
      },
    };
  }

  const windowMinutes = cfg.agents?.defaults?.totpWindowMinutes ?? 10;
  // Snapshot BEFORE opening the window: startApprovalWindow drains any resolvers
  // already blocked at the gate, so this tells us whether a run was waiting.
  const hadPendingApprovals = hasPendingApprovals();
  const { expiresAt } = startApprovalWindow({
    durationMinutes: windowMinutes,
    channel: params.command.channel,
  });
  const expiresAtStr = new Date(expiresAt).toLocaleTimeString();

  // A run was already blocked at the gate — opening the window just resumed it,
  // so it will produce its own output. Continuing this message into the agent
  // as well would double-trigger the task; reply deterministically instead.
  if (hadPendingApprovals) {
    return {
      shouldContinue: false,
      reply: {
        text:
          `✅ Approved. Window open for ${windowMinutes} minute${windowMinutes > 1 ? "s" : ""} (until ${expiresAtStr}).\n` +
          `The action that was waiting at the gate is resuming now.`,
      },
    };
  }

  // Nothing was blocked at the gate (typical pre-gate flow: L1 asked for the
  // code and ended its turn). Continue this message into the agent so L1 sees
  // the gate opened and resumes the pending task on its own — the user should
  // not have to say "the gate is open, continue". The raw 6-digit code is
  // replaced with a system note so it never reaches the model.
  setAgentBody(
    params.ctx,
    `[SYSTEM – TOTP GATE: ✅ Code verified. Approval window is now OPEN for ` +
      `${windowMinutes} minute${windowMinutes > 1 ? "s" : ""} (until ${expiresAtStr}). ` +
      `Continue normal conversation as usual. If a protected action is pending, execute it now ` +
      `without asking for the code again. Only stop at the exact gated tool/action boundary; ` +
      `do not treat the open window as a need to halt or distort ordinary conversation.]`,
  );
  return { shouldContinue: true };
};
