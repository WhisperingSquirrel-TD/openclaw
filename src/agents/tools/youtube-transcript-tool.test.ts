import { afterEach, describe, expect, it, vi } from "vitest";
import {
  YoutubeTranscript,
  YoutubeTranscriptNotAvailableError,
  YoutubeTranscriptTooManyRequestError,
} from "youtube-transcript/dist/youtube-transcript.esm.js";
import type { OpenClawConfig } from "../../config/config.js";
import { createYoutubeTranscriptTool } from "./youtube-transcript-tool.js";

type ToolDetails = Record<string, unknown>;

function details(result: unknown): ToolDetails {
  return (result as { details: ToolDetails }).details;
}

function createGeminiConfig(): OpenClawConfig {
  return {
    tools: {
      web: {
        search: {
          gemini: {
            apiKey: "gemini-test-key",
            model: "gemini-test-model",
          },
        },
      },
    },
  } as OpenClawConfig;
}

function installGeminiResponse(transcript: string) {
  const fetch = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
      new Response(
        JSON.stringify({
          candidates: [{ content: { parts: [{ text: transcript }] } }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("youtube_transcript", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("extracts the supported URL forms before calling the caption client", async () => {
    const fetchTranscript = vi
      .spyOn(YoutubeTranscript, "fetchTranscript")
      .mockResolvedValue([{ text: "caption", duration: 1, offset: 0, lang: "en" }]);
    const tool = createYoutubeTranscriptTool();
    const cases = [
      ["AbCdEfGhI_1", "AbCdEfGhI_1"],
      ["https://www.youtube.com/watch?v=AbCdEfGhI_2&t=42", "AbCdEfGhI_2"],
      ["https://youtu.be/AbCdEfGhI_3?si=test", "AbCdEfGhI_3"],
      ["https://youtube.com/shorts/AbCdEfGhI_4", "AbCdEfGhI_4"],
      ["https://youtube.com/live/AbCdEfGhI_5#now", "AbCdEfGhI_5"],
      ["https://youtube.com/embed/AbCdEfGhI_6", "AbCdEfGhI_6"],
      ["https://youtube.com/e/AbCdEfGhI_7", "AbCdEfGhI_7"],
      ["https://youtube.com/v/AbCdEfGhI_8", "AbCdEfGhI_8"],
    ] as const;

    for (const [url, videoId] of cases) {
      await tool.execute("url-form", { url });
      expect(fetchTranscript).toHaveBeenLastCalledWith(videoId, {});
    }
    expect(fetchTranscript).toHaveBeenCalledTimes(cases.length);
  });

  it("rejects malformed IDs without attempting captions or Gemini", async () => {
    const fetchTranscript = vi.spyOn(YoutubeTranscript, "fetchTranscript");
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const tool = createYoutubeTranscriptTool({ config: createGeminiConfig() });

    const result = await tool.execute("invalid-url", {
      url: "https://youtube.com/watch?v=too-short",
    });

    expect(details(result)).toMatchObject({
      error: expect.stringContaining("Could not extract a YouTube video ID"),
    });
    expect(fetchTranscript).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shares a cache entry across URL forms while preserving the first result", async () => {
    const fetchTranscript = vi
      .spyOn(YoutubeTranscript, "fetchTranscript")
      .mockResolvedValue([{ text: "cached caption", duration: 1, offset: 0, lang: "en" }]);
    const tool = createYoutubeTranscriptTool();

    const first = await tool.execute("cache-first", {
      url: "https://www.youtube.com/watch?v=CacheId_001",
    });
    const second = await tool.execute("cache-second", {
      url: "https://youtu.be/CacheId_001?feature=shared",
    });

    expect(details(first)).toMatchObject({
      transcript: "cached caption",
      source: "captions",
      cached: false,
    });
    expect(details(second)).toEqual({ transcript: "cached caption", cached: true });
    expect(fetchTranscript).toHaveBeenCalledTimes(1);
  });

  it("formats timestamps and caps an oversized native transcript", async () => {
    const longCaption = "x".repeat(80_001);
    vi.spyOn(YoutubeTranscript, "fetchTranscript").mockResolvedValue([
      { text: longCaption, duration: 1, offset: 0, lang: "en" },
      { text: "later", duration: 1, offset: 3_661_000, lang: "en" },
    ]);
    const tool = createYoutubeTranscriptTool();

    const result = await tool.execute("caption-truncation", {
      url: "AbCdEfGhJ_1",
      includeTimestamps: true,
    });
    const value = details(result);

    expect(value.source).toBe("captions");
    expect(value.truncated).toBe(true);
    expect(value.transcript).toBe(`[00:00] ${longCaption}`.slice(0, 80_000));
    expect(value.transcript).not.toContain("later");
    expect(value.note).toContain("80000 chars");
  });

  it("falls back to the configured Gemini endpoint for missing captions", async () => {
    const videoId = "Fallback_01";
    vi.spyOn(YoutubeTranscript, "fetchTranscript").mockRejectedValue(
      new YoutubeTranscriptNotAvailableError(videoId),
    );
    const fetch = installGeminiResponse("AI transcript");
    const tool = createYoutubeTranscriptTool({ config: createGeminiConfig() });

    const result = await tool.execute("gemini-fallback", {
      url: `https://www.youtube.com/watch?v=${videoId}`,
      lang: "en",
    });
    const value = details(result);
    const [endpoint, init] = fetch.mock.calls[0] ?? [];
    if (typeof init?.body !== "string") {
      throw new Error("Expected a JSON string request body");
    }
    const body = JSON.parse(init.body) as {
      contents?: Array<{ parts?: Array<{ fileData?: { fileUri?: string }; text?: string }> }>;
    };

    expect(value).toMatchObject({
      transcript: "AI transcript",
      source: "gemini_ai",
      model: "gemini-test-model",
      cached: false,
    });
    expect(endpoint).toBe(
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-test-model:generateContent",
    );
    expect(new Headers(init?.headers).get("x-goog-api-key")).toBe("gemini-test-key");
    expect(body.contents?.[0]?.parts).toEqual(
      expect.arrayContaining([
        {
          fileData: { mimeType: "video/*", fileUri: `https://www.youtube.com/watch?v=${videoId}` },
        },
        expect.objectContaining({ text: expect.stringContaining("complete, verbatim transcript") }),
      ]),
    );
  });

  it("does not call Gemini for a caption rate limit", async () => {
    vi.spyOn(YoutubeTranscript, "fetchTranscript").mockRejectedValue(
      new YoutubeTranscriptTooManyRequestError(),
    );
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const tool = createYoutubeTranscriptTool({ config: createGeminiConfig() });

    const result = await tool.execute("rate-limited", { url: "AbCdEfGhJ_2" });

    expect(details(result).error).toContain("rate-limiting");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("reports missing Gemini credentials without making an endpoint request", async () => {
    vi.spyOn(YoutubeTranscript, "fetchTranscript").mockRejectedValue(
      new YoutubeTranscriptNotAvailableError("NoKeyId_001"),
    );
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const tool = createYoutubeTranscriptTool();

    const result = await tool.execute("no-gemini-key", { url: "NoKeyId_001" });

    expect(details(result).error).toContain("requires GEMINI_API_KEY");
    expect(fetch).not.toHaveBeenCalled();
  });
});
