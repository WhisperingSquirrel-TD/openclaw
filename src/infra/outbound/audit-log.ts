import fs from "node:fs";
import path from "node:path";
import { resolveStateDir } from "../../config/paths.js";
import { createSubsystemLogger } from "../../logging/subsystem.js";

const log = createSubsystemLogger("outbound/audit-log");

const AUDIT_DIRNAME = "audit";
const AUDIT_FILENAME = "outbound-audit.jsonl";
const MAX_CONTENT_LENGTH = 10_000;

export type AuditLogEntry = {
  timestamp: string;
  targetChannel: string;
  recipient: string;
  messageContent: string;
  blocked: boolean;
  blockReason: "watch_mode" | "deny_commands" | "rate_limit" | "trust_gate" | null;
  sessionId: string | null;
};

let auditFilePath: string | null = null;
let auditFd: number | null = null;

function resolveAuditLogPath(stateDir?: string): string {
  const base = stateDir ?? resolveStateDir();
  return path.join(base, AUDIT_DIRNAME, AUDIT_FILENAME);
}

function ensureAuditDir(filePath: string): void {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
}

function getAuditFd(): number | null {
  if (auditFd != null) {
    return auditFd;
  }
  try {
    const filePath = resolveAuditLogPath();
    ensureAuditDir(filePath);
    auditFd = fs.openSync(filePath, "a", 0o600);
    auditFilePath = filePath;
    return auditFd;
  } catch (err) {
    log.warn(`Failed to open audit log file: ${String(err)}`);
    return null;
  }
}

function truncateContent(content: string): string {
  if (content.length <= MAX_CONTENT_LENGTH) {
    return content;
  }
  return content.slice(0, MAX_CONTENT_LENGTH);
}

export function appendAuditEntry(entry: AuditLogEntry): void {
  const fd = getAuditFd();
  if (fd == null) {
    return;
  }
  try {
    const line = JSON.stringify({
      ...entry,
      messageContent: truncateContent(entry.messageContent),
    });
    fs.writeSync(fd, line + "\n");
  } catch (err) {
    log.warn(`Failed to write audit log entry: ${String(err)}`);
  }
}

export function logOutboundAudit(params: {
  channel: string;
  recipient: string;
  content: string;
  blocked: boolean;
  blockReason?: AuditLogEntry["blockReason"];
  sessionId?: string | null;
}): void {
  appendAuditEntry({
    timestamp: new Date().toISOString(),
    targetChannel: params.channel,
    recipient: params.recipient,
    messageContent: params.content,
    blocked: params.blocked,
    blockReason: params.blockReason ?? null,
    sessionId: params.sessionId ?? null,
  });
}

export function closeAuditLog(): void {
  if (auditFd != null) {
    try {
      fs.closeSync(auditFd);
    } catch {
      // Best-effort cleanup.
    }
    auditFd = null;
    auditFilePath = null;
  }
}
