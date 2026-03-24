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
 *
 * Instead of blocking the message, it injects a system instruction into the
 * message body that L1 will read. L1 is instructed to ask for the TOTP code as
 * its very first reply — before planning, drafting, or using any tools. Once the
 * user sends the code and the window opens, L1 proceeds with the original task.
 *
 * Slash commands and 6-digit codes are passed through untouched so their own
 * handlers can process them normally.
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
  const lower = normalized.toLowerCase();

  // Let TOTP codes and slash commands pass through to their own handlers.
  if (/^\d{6}$/.test(normalized)) return null;
  if (normalized.startsWith("/")) return null;

  // Only inject the TOTP-first instruction when the message looks like it will
  // need a gated action (exec.run or message.send). Conversational messages,
  // questions, and advice requests pass through clean so L1 answers them directly.
  //
  // Heuristic: look for action-intent verbs that typically lead to gated tool calls.
  // False positives (gating a non-action) are harmless; false negatives (missing an
  // action) fall back to the existing trust gate prompt after L1 starts reasoning.
  const ACTION_PATTERNS = [
    /\bsend\b/,           // send email / send message
    /\breply\b/,          // reply to email / reply to WhatsApp
    /\brespond\b/,        // respond to
    /\bforward\b/,        // forward email
    /\bdraft\b/,          // draft a message/email
    /\bemail\b/,          // email John / email the team
    /\bwhatsapp\b/,       // whatsapp someone
    /\brun\b/,            // run a command / run this script
    /\bexecute\b/,        // execute
    /\bschedule\b/,       // schedule a meeting
    /\badd to\b/,         // add to contacts / add to calendar
    /\bcreate.*event\b/,  // create a calendar event
    /\bwrite to\b/,       // write to file
    /\bsave\b/,           // save this
    /\bdelete\b/,         // delete something
    /\bremove\b/,         // remove something
    /\bupdate.*contact\b/,// update a contact
    /\bcall\b/,           // call someone (future)
  ];

  const looksLikeAction = ACTION_PATTERNS.some((re) => re.test(lower));
  if (!looksLikeAction) {
    logVerbose("TOTP pre-gate: no action keywords detected, passing message through to L1 unmodified");
    return null;
  }

  // Looks like an action — inject a TOTP-first instruction so L1 asks for the
  // code immediately as its very first reply, before spending time planning or
  // calling any tools. No resend needed: L1 already has the full task context.
  logVerbose("TOTP pre-gate: action keywords detected, injecting TOTP-first instruction");
  const original = params.ctx.BodyForAgent ?? params.ctx.Body ?? normalized;
  params.ctx.BodyForAgent =
    `[SYSTEM – TOTP GATE: No approval window is currently active. ` +
    `Your FIRST and ONLY response right now must be: "🔐 Please send your TOTP code to open the gate." ` +
    `Do NOT plan, draft, analyse, or call any tools first. ` +
    `Once the user sends a code and you see ✅ Approved, proceed with the task below.]\n\n${original}`;

  return null; // shouldContinue — L1 gets the message with the injected instruction
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
