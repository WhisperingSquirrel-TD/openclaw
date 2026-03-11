import fs from "node:fs";
import path from "node:path";
import { resolveOAuthDir } from "../../config/paths.js";
import { logVerbose } from "../../globals.js";
import type { WatchTranscriptEntry } from "./watch-transcript.js";

export type ActionCandidate = WatchTranscriptEntry & {
  lineIndex: number;
};

const CONTEXT_WINDOW_LINES = 30;

function resolveCursorPath(accountId: string): string {
  const safeAccountId = accountId.replace(/[^a-zA-Z0-9_-]/g, "_");
  const dir = path.join(resolveOAuthDir(), "whatsapp", "watch-transcripts");
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `whatsapp-watch-${safeAccountId}.cursor`);
}

function resolveTranscriptPath(accountId: string): string {
  const safeAccountId = accountId.replace(/[^a-zA-Z0-9_-]/g, "_");
  const dir = path.join(resolveOAuthDir(), "whatsapp", "watch-transcripts");
  return path.join(dir, `whatsapp-watch-${safeAccountId}.jsonl`);
}

function readCursor(accountId: string): number {
  const cursorPath = resolveCursorPath(accountId);
  try {
    const raw = fs.readFileSync(cursorPath, "utf-8").trim();
    const val = Number.parseInt(raw, 10);
    return Number.isNaN(val) ? 0 : val;
  } catch {
    return 0;
  }
}

function writeCursor(accountId: string, offset: number): void {
  const cursorPath = resolveCursorPath(accountId);
  try {
    fs.writeFileSync(cursorPath, String(offset), "utf-8");
  } catch (err) {
    logVerbose(`Watch action cursor write failed: ${String(err)}`);
  }
}

function parseLine(line: string): WatchTranscriptEntry | null {
  try {
    const entry: WatchTranscriptEntry = JSON.parse(line);
    if (!entry.body || entry.body.trim().length === 0) return null;
    return entry;
  } catch {
    return null;
  }
}

export function scanWatchTranscript(accountId: string): {
  candidates: ActionCandidate[];
  contextMessages: ActionCandidate[];
  newCursorOffset: number;
} {
  const transcriptPath = resolveTranscriptPath(accountId);
  if (!fs.existsSync(transcriptPath)) {
    return { candidates: [], contextMessages: [], newCursorOffset: 0 };
  }

  const cursorOffset = readCursor(accountId);
  const raw = fs.readFileSync(transcriptPath, "utf-8");
  const lines = raw.split("\n").filter(Boolean);

  if (lines.length <= cursorOffset) {
    return { candidates: [], contextMessages: [], newCursorOffset: cursorOffset };
  }

  const contextStart = Math.max(0, cursorOffset - CONTEXT_WINDOW_LINES);
  const contextLines = lines.slice(contextStart, cursorOffset);
  const contextMessages: ActionCandidate[] = [];
  for (let i = 0; i < contextLines.length; i++) {
    const entry = parseLine(contextLines[i]);
    if (entry) {
      contextMessages.push({ ...entry, lineIndex: contextStart + i });
    }
  }

  const newLines = lines.slice(cursorOffset);
  const candidates: ActionCandidate[] = [];
  for (let i = 0; i < newLines.length; i++) {
    const entry = parseLine(newLines[i]);
    if (entry) {
      candidates.push({ ...entry, lineIndex: cursorOffset + i });
    }
  }

  return { candidates, contextMessages, newCursorOffset: lines.length };
}

export function commitCursor(accountId: string, offset: number): void {
  writeCursor(accountId, offset);
}
