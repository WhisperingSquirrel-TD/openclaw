import fs from "node:fs";
import path from "node:path";
import { resolveOAuthDir } from "../../config/paths.js";
import { logVerbose } from "../../globals.js";

export type WatchTranscriptEntry = {
  messageId?: string;
  channel: string;
  chatType: "direct" | "group";
  chatName?: string;
  senderName?: string;
  senderNumber?: string;
  timestamp: string;
  body: string;
  mediaType?: string;
  quotedMessage?: string;
  isFromMe: boolean;
};

const MAX_BODY_LENGTH = 100_000;
const CONTROL_CHAR_PATTERN = /[\x00-\x08\x0B\x0C\x0E-\x1F]/g;

function sanitize(value: string | undefined | null, maxLen = MAX_BODY_LENGTH): string {
  if (!value) {
    return "";
  }
  return value.slice(0, maxLen).replace(CONTROL_CHAR_PATTERN, "");
}

export function resolveTranscriptPath(accountId: string): string {
  const dir = path.join(resolveOAuthDir(), "whatsapp", "watch-transcripts");
  fs.mkdirSync(dir, { recursive: true });
  const safeAccountId = accountId.replace(/[^a-zA-Z0-9_-]/g, "_");
  return path.join(dir, `whatsapp-watch-${safeAccountId}.jsonl`);
}

export function appendWatchTranscript(
  accountId: string,
  entry: WatchTranscriptEntry,
): void {
  const filePath = resolveTranscriptPath(accountId);
  const sanitized: WatchTranscriptEntry = {
    messageId: entry.messageId,
    channel: "whatsapp",
    chatType: entry.chatType,
    chatName: sanitize(entry.chatName) || undefined,
    senderName: sanitize(entry.senderName) || undefined,
    senderNumber: entry.senderNumber,
    timestamp: entry.timestamp,
    body: sanitize(entry.body),
    mediaType: entry.mediaType,
    quotedMessage: sanitize(entry.quotedMessage) || undefined,
    isFromMe: entry.isFromMe,
  };
  const line = JSON.stringify(sanitized) + "\n";
  try {
    fs.appendFileSync(filePath, line, "utf-8");
  } catch (err) {
    logVerbose(`Watch transcript write failed: ${String(err)}`);
  }
}
