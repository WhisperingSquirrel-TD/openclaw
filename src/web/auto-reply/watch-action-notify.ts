import type { OpenClawConfig } from "../../config/config.js";
import { logInfo } from "../../logger.js";
import { logVerbose } from "../../globals.js";
import { sendMessageTelegram } from "../../telegram/send.js";
import type { TelegramInlineButtons } from "../../telegram/button-types.js";
import type { ClassifiedAction } from "./watch-action-classifier.js";
import { generateActionId, storeAction } from "./watch-action-store.js";

const ACTION_TYPE_EMOJI: Record<string, string> = {
  shopping: "\u{1F6D2}",
  calendar: "\u{1F4C5}",
  task: "\u{2705}",
  reminder: "\u{23F0}",
  urgent: "\u{1F6A8}",
  other: "\u{1F4CB}",
};

const ACTION_TYPE_LABEL: Record<string, string> = {
  shopping: "Shopping",
  calendar: "Calendar",
  task: "Task",
  reminder: "Reminder",
  urgent: "Urgent",
  other: "Action",
};

function buildActionButtons(actionId: string, actionType: string): TelegramInlineButtons {
  const buttons: TelegramInlineButtons = [];
  const row1: Array<{ text: string; callback_data: string }> = [];

  if (actionType === "shopping") {
    row1.push({ text: "Add to list", callback_data: `wa_act_add_${actionId}` });
  } else if (actionType === "calendar") {
    row1.push({ text: "Note it", callback_data: `wa_act_add_${actionId}` });
  } else if (actionType === "reminder") {
    row1.push({ text: "Remind me", callback_data: `wa_act_add_${actionId}` });
  } else {
    row1.push({ text: "Note it", callback_data: `wa_act_add_${actionId}` });
  }

  row1.push({ text: "Ignore", callback_data: `wa_act_ign_${actionId}` });
  buttons.push(row1);
  return buttons;
}

function buildActionMessage(action: ClassifiedAction): string {
  const emoji = ACTION_TYPE_EMOJI[action.actionType] ?? ACTION_TYPE_EMOJI.other;
  const label = ACTION_TYPE_LABEL[action.actionType] ?? "Action";
  const sender = action.senderName ?? "Unknown";
  const chat = action.chatName ? ` (${action.chatName})` : "";
  const time = new Date(action.timestamp).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });

  const truncatedMsg =
    action.originalMessage.length > 200
      ? action.originalMessage.slice(0, 197) + "..."
      : action.originalMessage;

  return [
    `${emoji} *${label} detected* from WhatsApp`,
    `From: ${sender}${chat} at ${time}`,
    "",
    `"${truncatedMsg}"`,
    "",
    `*Suggested:* ${action.summary}`,
  ].join("\n");
}

function resolveTelegramTarget(cfg: OpenClawConfig): string | null {
  const telegram = cfg.channels?.telegram;
  if (!telegram) return null;

  const allowFrom = telegram.allowFrom;
  if (Array.isArray(allowFrom) && allowFrom.length > 0) {
    return String(allowFrom[0]);
  }

  return null;
}

export async function notifyActions(
  cfg: OpenClawConfig,
  actions: ClassifiedAction[],
): Promise<void> {
  if (actions.length === 0) return;

  const target = resolveTelegramTarget(cfg);
  if (!target) {
    logInfo("watch-action-notify: no Telegram target found in config (channels.telegram.allowFrom)");
    return;
  }

  const telegramTo = `telegram:${target}`;

  for (const action of actions) {
    const actionId = generateActionId();

    storeAction({
      id: actionId,
      actionType: action.actionType,
      summary: action.summary,
      originalMessage: action.originalMessage,
      senderName: action.senderName,
      chatName: action.chatName,
      timestamp: action.timestamp,
      resolved: false,
    });

    const message = buildActionMessage(action);
    const buttons = buildActionButtons(actionId, action.actionType);

    try {
      await sendMessageTelegram(telegramTo, message, {
        buttons,
        textMode: "markdown",
      });
      logVerbose(`watch-action-notify: sent action card ${actionId} (${action.actionType})`);
    } catch (err) {
      logInfo(`watch-action-notify: failed to send Telegram card: ${String(err)}`);
    }
  }

  logInfo(`watch-action-notify: sent ${actions.length} action card(s) to Telegram`);
}
