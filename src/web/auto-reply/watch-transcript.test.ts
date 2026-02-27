import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../config/paths.js", () => ({
  resolveOAuthDir: () => testDir,
}));

import { appendWatchTranscript, resolveTranscriptPath } from "./watch-transcript.js";

let testDir: string;

beforeEach(() => {
  testDir = fs.mkdtempSync(path.join(os.tmpdir(), "watch-transcript-"));
});

afterEach(() => {
  fs.rmSync(testDir, { recursive: true, force: true });
});

describe("watch-transcript", () => {
  it("resolves transcript path with safe account id", () => {
    const result = resolveTranscriptPath("default");
    expect(result).toContain("whatsapp-watch-default.jsonl");
    expect(result).toContain("watch-transcripts");
  });

  it("writes valid JSONL with all required fields", () => {
    appendWatchTranscript("default", {
      messageId: "msg001",
      channel: "whatsapp",
      chatType: "direct",
      chatName: "Alice",
      senderName: "Alice",
      senderNumber: "+15551234567",
      timestamp: "2025-01-15T12:00:00.000Z",
      body: "Hello there!",
      isFromMe: false,
    });

    const filePath = resolveTranscriptPath("default");
    const content = fs.readFileSync(filePath, "utf-8").trim();
    const parsed = JSON.parse(content);
    expect(parsed.messageId).toBe("msg001");
    expect(parsed.channel).toBe("whatsapp");
    expect(parsed.chatType).toBe("direct");
    expect(parsed.senderName).toBe("Alice");
    expect(parsed.senderNumber).toBe("+15551234567");
    expect(parsed.body).toBe("Hello there!");
    expect(parsed.isFromMe).toBe(false);
  });

  it("appends multiple entries as separate JSONL lines", () => {
    appendWatchTranscript("default", {
      channel: "whatsapp",
      chatType: "direct",
      timestamp: new Date().toISOString(),
      body: "First",
      isFromMe: false,
    });
    appendWatchTranscript("default", {
      channel: "whatsapp",
      chatType: "group",
      chatName: "Family",
      timestamp: new Date().toISOString(),
      body: "Second",
      isFromMe: true,
    });

    const filePath = resolveTranscriptPath("default");
    const lines = fs.readFileSync(filePath, "utf-8").trim().split("\n");
    expect(lines).toHaveLength(2);
    expect(JSON.parse(lines[0]).body).toBe("First");
    expect(JSON.parse(lines[1]).body).toBe("Second");
    expect(JSON.parse(lines[1]).isFromMe).toBe(true);
  });

  it("sanitizes control characters from body", () => {
    appendWatchTranscript("default", {
      channel: "whatsapp",
      chatType: "direct",
      timestamp: new Date().toISOString(),
      body: "Hello\x00World\x07!",
      isFromMe: false,
    });

    const filePath = resolveTranscriptPath("default");
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf-8").trim());
    expect(parsed.body).toBe("HelloWorld!");
  });

  it("includes optional fields when present", () => {
    appendWatchTranscript("default", {
      messageId: "msg002",
      channel: "whatsapp",
      chatType: "group",
      chatName: "Work Chat",
      senderName: "Bob",
      senderNumber: "+15559876543",
      timestamp: "2025-01-15T12:00:00.000Z",
      body: "Check this out",
      mediaType: "image/jpeg",
      quotedMessage: "What were you saying?",
      isFromMe: false,
    });

    const filePath = resolveTranscriptPath("default");
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf-8").trim());
    expect(parsed.mediaType).toBe("image/jpeg");
    expect(parsed.quotedMessage).toBe("What were you saying?");
    expect(parsed.chatName).toBe("Work Chat");
  });
});
