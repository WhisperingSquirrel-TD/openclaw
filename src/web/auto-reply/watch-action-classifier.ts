import { streamSimple } from "@mariozechner/pi-ai";
import type { OpenClawConfig } from "../../config/config.js";
import { logVerbose } from "../../globals.js";
import { logInfo } from "../../logger.js";
import { resolveModel } from "../../agents/pi-embedded-runner/model.js";
import { resolveApiKeyForProvider } from "../../agents/model-auth.js";
import { normalizeProviderId } from "../../agents/model-selection.js";
import type { ActionCandidate } from "./watch-action-scanner.js";
import type { ActionType } from "./watch-action-store.js";

export type ClassifiedAction = {
  actionType: ActionType;
  summary: string;
  originalMessage: string;
  senderName?: string;
  chatName?: string;
  timestamp: string;
};

const CLASSIFICATION_SYSTEM_PROMPT = `You are a message analysis assistant. You review WhatsApp conversation threads and identify actionable items that need to be acted on.

You MUST consider the FULL conversation context. If a later message resolves or cancels an earlier request, do NOT flag it as actionable.

Examples of resolved actions:
- "Can you pick up milk?" followed by "Actually never mind, I got it" = NOT actionable
- "Can you pick up milk?" followed by recipient: "I've already got milk" = NOT actionable
- "Meeting at 3pm tomorrow" followed by "Meeting cancelled" = NOT actionable

Action types:
- shopping: Items to buy or pick up (e.g. "Get milk", "Buy coffee", "Pick up bread")
- calendar: Events, meetings, appointments, dates to remember
- task: Things to do, errands, requests for action
- reminder: Things to remember or not forget
- urgent: Time-sensitive items needing immediate attention

Respond with a JSON array. Each element must have:
- "actionType": one of "shopping", "calendar", "task", "reminder", "urgent"
- "summary": a concise description of what needs to be done (max 100 chars)
- "messageIndex": the index of the message that triggered this action (0-based from the input)

If NO messages require action, respond with an empty array: []

IMPORTANT RULES:
- Messages sent by "ME" (labeled with sender "ME") are self-sent reminders or notes to self. Treat these with HIGH confidence — if a self-sent message names an item, errand, or task, flag it. Short imperative phrases like "Get milk", "Call dentist", "Book flights" are definitely actionable.
- Casual conversation, greetings, jokes, status updates, and general chat are NOT actionable.
- Only skip flagging when a message is clearly not a request or reminder — e.g. pure small talk, reactions, or emoji-only messages.`;

function buildClassificationPrompt(
  candidates: ActionCandidate[],
  contextMessages: ActionCandidate[],
): string {
  const allMessages = [...contextMessages, ...candidates];
  const contextCount = contextMessages.length;

  const grouped = new Map<string, { msg: ActionCandidate; isNew: boolean; originalIdx: number }[]>();
  for (let i = 0; i < allMessages.length; i++) {
    const msg = allMessages[i];
    const key = msg.chatName ?? msg.senderName ?? "unknown";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push({
      msg,
      isNew: i >= contextCount,
      originalIdx: i < contextCount ? -1 : i - contextCount,
    });
  }

  let prompt = "Analyse the following WhatsApp messages and identify any actionable items.\n";
  prompt += "Messages marked [CONTEXT] are older messages shown for thread continuity — do NOT flag them as new actions, but DO use them to understand if newer messages resolve earlier requests.\n";
  prompt += "Only flag actions from [NEW] messages that are still unresolved.\n\n";

  for (const [chatKey, entries] of grouped) {
    prompt += `--- Conversation: ${chatKey} ---\n`;
    for (const entry of entries) {
      const label = entry.isNew ? "NEW" : "CONTEXT";
      const idx = entry.isNew ? `${entry.originalIdx}` : "-";
      const sender = entry.msg.isFromMe ? "ME" : (entry.msg.senderName ?? "Unknown");
      const time = entry.msg.timestamp
        ? new Date(entry.msg.timestamp).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
        : "??:??";
      prompt += `[${label}:${idx}] ${time} ${sender}: ${redactPii(entry.msg.body.slice(0, 500))}\n`;
    }
    prompt += "\n";
  }

  prompt += "Use messageIndex values from [NEW] messages only. Respond with ONLY a JSON array. No other text.";
  return prompt;
}

const PII_PATTERNS: Array<{ pattern: RegExp; replacement: string }> = [
  { pattern: /\b\d{10,15}\b/g, replacement: "[phone]" },
  { pattern: /\+\d{1,3}\s?\d{4,14}/g, replacement: "[phone]" },
  { pattern: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g, replacement: "[email]" },
  { pattern: /\b[A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2}\b/gi, replacement: "[postcode]" },
  { pattern: /\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b/g, replacement: "[card]" },
  { pattern: /\b\d{6,8}\b(?=\s*(sort|code))/gi, replacement: "[sortcode]" },
];

function redactPii(text: string): string {
  let result = text;
  for (const { pattern, replacement } of PII_PATTERNS) {
    result = result.replace(pattern, replacement);
  }
  return result;
}

const CHEAP_MODELS: Record<string, string> = {
  anthropic: "claude-haiku-4-20250414",
  openai: "gpt-4o-mini",
  google: "gemini-2.0-flash",
  gemini: "gemini-2.0-flash",
};

function resolveCheapModel(cfg: OpenClawConfig): { provider: string; modelId: string } | null {
  const configuredModel = cfg.channels?.whatsapp?.watchActions?.model;
  if (configuredModel) {
    const parts = configuredModel.split("/");
    if (parts.length === 2) {
      return { provider: parts[0], modelId: parts[1] };
    }
  }

  const defaults = cfg.agents?.defaults;
  const primaryModel =
    typeof defaults?.model === "object" ? defaults.model.primary : defaults?.model;
  if (primaryModel && typeof primaryModel === "string") {
    const parts = primaryModel.split("/");
    if (parts.length >= 2) {
      const provider = normalizeProviderId(parts[0]);
      const cheapModel = CHEAP_MODELS[provider];
      if (cheapModel) {
        return { provider, modelId: cheapModel };
      }
      return { provider, modelId: parts.slice(1).join("/") };
    }
  }

  return null;
}

function isActionType(value: unknown): value is ActionType {
  return (
    typeof value === "string" &&
    ["shopping", "calendar", "task", "reminder", "urgent", "other"].includes(value)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function parseClassificationResponse(value: unknown): Array<{
  actionType: ActionType;
  summary: string;
  messageIndex: number;
}> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!isRecord(item)) {
      return [];
    }
    const { actionType, summary, messageIndex } = item;
    if (!isActionType(actionType) || typeof summary !== "string" || typeof messageIndex !== "number") {
      return [];
    }
    return [{ actionType, summary, messageIndex }];
  });
}

export async function classifyActions(
  cfg: OpenClawConfig,
  candidates: ActionCandidate[],
  contextMessages: ActionCandidate[] = [],
): Promise<ClassifiedAction[]> {
  if (candidates.length === 0) return [];

  const modelChoice = resolveCheapModel(cfg);
  if (!modelChoice) {
    logInfo("watch-action-classifier: no model available for classification");
    return [];
  }

  const { provider, modelId } = modelChoice;
  logInfo(`watch-action-classifier: using ${provider}/${modelId} for ${candidates.length} messages`);

  const resolved = resolveModel(provider, modelId, undefined, cfg);
  if (!resolved.model) {
    logInfo(`watch-action-classifier: failed to resolve model ${provider}/${modelId}: ${resolved.error}`);
    return [];
  }

  let apiKey: string;
  try {
    const auth = await resolveApiKeyForProvider({ provider, cfg });
    if (!auth.apiKey) {
      logInfo(`watch-action-classifier: no API key for ${provider}`);
      return [];
    }
    apiKey = auth.apiKey;
  } catch (err) {
    logInfo(`watch-action-classifier: no API key for ${provider}: ${String(err)}`);
    return [];
  }

  const model = resolved.model;
  const prompt = buildClassificationPrompt(candidates, contextMessages);

  try {
    const context = {
      systemPrompt: CLASSIFICATION_SYSTEM_PROMPT,
      messages: [{ role: "user" as const, content: prompt, timestamp: Date.now() }],
    };

    let responseText = "";
    const stream = streamSimple(model, context, { apiKey, maxTokens: 1024 });
    for await (const event of stream) {
      if (event.type === "text_delta") {
        responseText += event.delta;
      }
    }

    responseText = responseText.trim();
    const jsonMatch = responseText.match(/\[[\s\S]*\]/);
    if (!jsonMatch) {
      logVerbose(`watch-action-classifier: no JSON array in response: ${responseText.slice(0, 200)}`);
      return [];
    }

    const parsed = parseClassificationResponse(JSON.parse(jsonMatch[0]));
    if (parsed.length === 0) return [];

    const results: ClassifiedAction[] = [];
    for (const item of parsed) {
      const idx = item.messageIndex;
      if (typeof idx !== "number" || idx < 0 || idx >= candidates.length) continue;
      const candidate = candidates[idx];
      results.push({
        actionType: item.actionType,
        summary: item.summary.slice(0, 200),
        originalMessage: redactPii(candidate.body.slice(0, 150)),
        senderName: candidate.senderName ? redactPii(candidate.senderName) : undefined,
        chatName: candidate.chatName ? redactPii(candidate.chatName) : undefined,
        timestamp: candidate.timestamp,
      });
    }

    logInfo(`watch-action-classifier: detected ${results.length} actions from ${candidates.length} messages`);
    return results;
  } catch (err) {
    logInfo(`watch-action-classifier: classification failed: ${String(err)}`);
    return [];
  }
}
