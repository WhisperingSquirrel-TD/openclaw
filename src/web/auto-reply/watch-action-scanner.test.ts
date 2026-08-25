import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../config/paths.js", () => ({
  resolveOAuthDir: () => testDir,
}));

import { commitCursor, scanWatchTranscript } from "./watch-action-scanner.js";

let testDir: string;

const entry = (body: string) =>
  JSON.stringify({
    channel: "whatsapp",
    chatType: "direct",
    timestamp: "2025-01-15T12:00:00.000Z",
    body,
    isFromMe: false,
  });

beforeEach(() => {
  testDir = fs.mkdtempSync(path.join(os.tmpdir(), "watch-action-scanner-"));
  const transcriptDir = path.join(testDir, "whatsapp", "watch-transcripts");
  fs.mkdirSync(transcriptDir, { recursive: true });
  fs.writeFileSync(
    path.join(transcriptDir, "whatsapp-watch-default.jsonl"),
    [entry("First"), entry("Second"), entry("Third")].join("\n") + "\n",
  );
});

afterEach(() => {
  fs.rmSync(testDir, { recursive: true, force: true });
});

describe("watch-action-scanner", () => {
  it("returns only messages after the cursor and retains preceding context", () => {
    commitCursor("default", 2);

    const result = scanWatchTranscript("default");

    expect(result.candidates.map((candidate) => candidate.body)).toEqual(["Third"]);
    expect(result.candidates[0]?.lineIndex).toBe(2);
    expect(result.contextMessages.map((message) => message.body)).toEqual(["First", "Second"]);
    expect(result.newCursorOffset).toBe(3);
  });
});