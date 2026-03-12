import fs from "node:fs";
import path from "node:path";
import { resolveOAuthDir, resolveStateDir } from "../../config/paths.js";
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

function resolveMarkdownLogPath(): string {
  const workspaceDir = path.join(resolveStateDir(), "workspace");
  fs.mkdirSync(workspaceDir, { recursive: true });
  return path.join(workspaceDir, "WHATSAPP_LOG.md");
}

function formatMarkdownLogLine(entry: WatchTranscriptEntry): string {
  const ts = new Date(entry.timestamp);
  const datePart = ts.toISOString().slice(0, 10);
  const timePart = ts.toTimeString().slice(0, 5);
  const prefix = entry.isFromMe ? "Me" : (entry.senderName || entry.senderNumber || "Unknown");
  const chat = entry.chatType === "group" && entry.chatName ? ` [${sanitize(entry.chatName, 40)}]` : "";
  const body = sanitize(entry.body, 500);
  return `[${datePart} ${timePart}]${chat} ${prefix}: ${body}\n`;
}

function appendMarkdownLog(entry: WatchTranscriptEntry): void {
  try {
    const logPath = resolveMarkdownLogPath();
    const line = formatMarkdownLogLine(entry);
    fs.appendFileSync(logPath, line, "utf-8");
  } catch (err) {
    logVerbose(`Watch markdown log write failed: ${String(err)}`);
  }
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
  appendMarkdownLog(entry);
}
