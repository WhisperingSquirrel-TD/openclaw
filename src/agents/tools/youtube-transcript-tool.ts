import { Type } from "@sinclair/typebox";
import {
  YoutubeTranscript,
  YoutubeTranscriptDisabledError,
  YoutubeTranscriptError,
  YoutubeTranscriptNotAvailableError,
  YoutubeTranscriptNotAvailableLanguageError,
  YoutubeTranscriptTooManyRequestError,
  YoutubeTranscriptVideoUnavailableError,
  type TranscriptResponse,
} from "youtube-transcript";

import type { OpenClawConfig } from "../../config/config.js";
import type { AnyAgentTool } from "./common.js";
import { jsonResult, readStringParam } from "./common.js";
import {
  type CacheEntry,
  normalizeCacheKey,
  readCache,
  writeCache,
} from "./web-shared.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TRANSCRIPT_CACHE_TTL_MINUTES = 60 * 24; // 24 h — transcripts rarely change
const MAX_TRANSCRIPT_CHARS = 80_000;

const GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta";
const DEFAULT_GEMINI_MODEL = "gemini-2.5-flash";

// Gemini can take a while on long videos — allow up to 8 minutes
const GEMINI_TIMEOUT_MS = 8 * 60 * 1000;

// ---------------------------------------------------------------------------
// Cache
// ---------------------------------------------------------------------------

const TRANSCRIPT_CACHE = new Map<string, CacheEntry<string>>();

// ---------------------------------------------------------------------------
// Video ID extraction
// ---------------------------------------------------------------------------

const YT_ID_REGEX =
  /(?:youtube\.com\/(?:[^/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?/\s]{11})/i;

function extractVideoId(input: string): string | null {
  const trimmed = input.trim();
  if (/^[A-Za-z0-9_-]{11}$/.test(trimmed)) {
    return trimmed;
  }
  const match = trimmed.match(YT_ID_REGEX);
  return match?.[1] ?? null;
}

// ---------------------------------------------------------------------------
// Caption formatting helpers
// ---------------------------------------------------------------------------

function formatTimestamp(offsetMs: number): string {
  const totalSeconds = Math.floor(offsetMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function buildTranscriptText(
  segments: TranscriptResponse[],
  includeTimestamps: boolean,
): string {
  if (includeTimestamps) {
    return segments
      .map((s) => `[${formatTimestamp(s.offset)}] ${s.text}`)
      .join("\n");
  }
  return segments.map((s) => s.text).join(" ");
}

// ---------------------------------------------------------------------------
// Caption error classification
// ---------------------------------------------------------------------------

type CaptionFailureKind =
  | "no_captions"      // no captions at all — fallback to Gemini STT
  | "disabled"         // owner disabled captions — fallback to Gemini STT
  | "rate_limited"     // YouTube rate limit — do not fallback, surface to user
  | "unavailable"      // video private/deleted — do not fallback
  | "wrong_language"   // requested lang not found — surface available langs
  | "other";           // generic/unexpected

function classifyCaptionError(err: unknown): {
  kind: CaptionFailureKind;
  message: string;
} {
  if (err instanceof YoutubeTranscriptTooManyRequestError) {
    return {
      kind: "rate_limited",
      message:
        "YouTube is rate-limiting this server's IP — please try again in a few minutes.",
    };
  }
  if (err instanceof YoutubeTranscriptVideoUnavailableError) {
    return {
      kind: "unavailable",
      message: `Video unavailable or private: ${(err as Error).message}`,
    };
  }
  if (err instanceof YoutubeTranscriptDisabledError) {
    return {
      kind: "disabled",
      message: `Captions are disabled on this video — attempting AI transcription.`,
    };
  }
  if (err instanceof YoutubeTranscriptNotAvailableLanguageError) {
    return {
      kind: "wrong_language",
      message: (err as Error).message,
    };
  }
  if (err instanceof YoutubeTranscriptNotAvailableError) {
    return {
      kind: "no_captions",
      message: `No captions/transcript available — attempting AI transcription.`,
    };
  }
  if (err instanceof YoutubeTranscriptError) {
    return {
      kind: "other",
      message: `YouTube transcript error: ${(err as Error).message}`,
    };
  }
  return {
    kind: "other",
    message: `Unexpected error fetching transcript: ${String(err)}`,
  };
}

// ---------------------------------------------------------------------------
// Gemini AI transcription fallback
// ---------------------------------------------------------------------------

function resolveGeminiApiKey(config?: OpenClawConfig): string | undefined {
  // Config path: tools.web.search.gemini.apiKey
  const gemini = (config?.tools as Record<string, unknown>)?.web as
    | { search?: { gemini?: { apiKey?: string } } }
    | undefined;
  const fromConfig = gemini?.search?.gemini?.apiKey?.trim();
  if (fromConfig) return fromConfig;
  const fromEnv = process.env.GEMINI_API_KEY?.trim();
  return fromEnv || undefined;
}

function resolveGeminiModel(config?: OpenClawConfig): string {
  const gemini = (config?.tools as Record<string, unknown>)?.web as
    | { search?: { gemini?: { model?: string } } }
    | undefined;
  const fromConfig = gemini?.search?.gemini?.model?.trim();
  return fromConfig || DEFAULT_GEMINI_MODEL;
}

async function transcribeWithGemini(params: {
  videoId: string;
  lang: string | undefined;
  apiKey: string;
  model: string;
}): Promise<{ transcript: string; source: "gemini" }> {
  const { videoId, lang, apiKey, model } = params;
  const youtubeUrl = `https://www.youtube.com/watch?v=${videoId}`;

  const langInstruction = lang
    ? ` Provide the transcript in language code "${lang}" if the video is in that language, otherwise use the video's spoken language.`
    : "";

  const prompt =
    `Please provide a complete, verbatim transcript of all spoken words in this video. ` +
    `Include every word that is spoken. Do not summarise — output the raw transcript only.` +
    langInstruction;

  const body = {
    contents: [
      {
        parts: [
          {
            fileData: {
              mimeType: "video/*",
              fileUri: youtubeUrl,
            },
          },
          { text: prompt },
        ],
      },
    ],
    generationConfig: {
      maxOutputTokens: 65536,
    },
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GEMINI_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(
      `${GEMINI_API_BASE}/models/${model}:generateContent`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": apiKey,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      },
    );
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    const safe = detail.replace(/key=[^&\s]+/gi, "key=***");
    throw new Error(`Gemini API error (${res.status}): ${safe}`);
  }

  let data: {
    candidates?: Array<{
      content?: { parts?: Array<{ text?: string }> };
      finishReason?: string;
    }>;
    error?: { code?: number; message?: string; status?: string };
  };

  try {
    data = await res.json();
  } catch {
    throw new Error("Gemini API returned invalid JSON");
  }

  if (data.error) {
    const raw = data.error.message || data.error.status || "unknown";
    const safe = raw.replace(/key=[^&\s]+/gi, "key=***");
    throw new Error(`Gemini API error (${data.error.code}): ${safe}`);
  }

  const transcript =
    data.candidates
      ?.flatMap((c) => c.content?.parts ?? [])
      .map((p) => p.text ?? "")
      .join("")
      .trim() ?? "";

  if (!transcript) {
    throw new Error(
      "Gemini returned an empty transcript. " +
        "The video may have no speech, or it may be region-locked or unavailable.",
    );
  }

  return { transcript, source: "gemini" };
}

// ---------------------------------------------------------------------------
// Tool schema
// ---------------------------------------------------------------------------

const YoutubeTranscriptSchema = Type.Object({
  url: Type.String({
    description:
      "YouTube video URL (any format) or bare 11-character video ID.",
  }),
  lang: Type.Optional(
    Type.String({
      description:
        "ISO 639-1 language code for the preferred transcript language " +
        "(e.g. 'en', 'es', 'fr'). Defaults to the video's primary language.",
    }),
  ),
  includeTimestamps: Type.Optional(
    Type.Boolean({
      description:
        "If true, each line is prefixed with a [MM:SS] or [HH:MM:SS] timestamp. " +
        "Only applies when native captions are available. Defaults to false.",
      default: false,
    }),
  ),
});

// ---------------------------------------------------------------------------
// Tool factory
// ---------------------------------------------------------------------------

export function createYoutubeTranscriptTool(options?: {
  config?: OpenClawConfig;
}): AnyAgentTool {
  return {
    label: "YouTube Transcript",
    name: "youtube_transcript",
    description:
      "Fetch the transcript (captions/subtitles) of a YouTube video. " +
      "No API key required for videos with captions. " +
      "For videos without captions, automatically falls back to AI transcription via Gemini " +
      "(requires GEMINI_API_KEY — may take a few minutes for long videos). " +
      "Use this whenever the user shares a YouTube link and asks you to " +
      "summarise, analyse, quote, or reference the video content.",
    parameters: YoutubeTranscriptSchema,
    execute: async (_toolCallId, rawArgs) => {
      const args = rawArgs as Record<string, unknown>;
      const url = readStringParam(args, "url", { required: false })?.trim() ?? "";
      if (!url) {
        return jsonResult({ error: "url is required" });
      }

      const lang = readStringParam(args, "lang")?.trim() || undefined;
      const includeTimestamps = args.includeTimestamps === true;

      // ── Cache check ────────────────────────────────────────────────────────
      const cacheKey = normalizeCacheKey(
        `yt:${url}:${lang ?? "auto"}:${includeTimestamps}`,
      );
      const cached = readCache<string>(TRANSCRIPT_CACHE, cacheKey);
      if (cached) {
        return jsonResult({ transcript: cached.value, cached: true });
      }

      // ── Step 1: Try native YouTube captions ────────────────────────────────
      let captionErr: { kind: CaptionFailureKind; message: string } | null =
        null;

      try {
        const segments = await YoutubeTranscript.fetchTranscript(url, {
          ...(lang ? { lang } : {}),
        });

        if (!segments || segments.length === 0) {
          return jsonResult({
            error: `No transcript segments returned for: ${url}`,
          });
        }

        const detectedLang = segments[0]?.lang ?? lang ?? "unknown";
        let text = buildTranscriptText(segments, includeTimestamps);
        let truncated = false;

        if (text.length > MAX_TRANSCRIPT_CHARS) {
          text = text.slice(0, MAX_TRANSCRIPT_CHARS);
          truncated = true;
        }

        writeCache(
          TRANSCRIPT_CACHE,
          cacheKey,
          text,
          TRANSCRIPT_CACHE_TTL_MINUTES * 60_000,
        );

        return jsonResult({
          transcript: text,
          source: "captions",
          lang: detectedLang,
          segmentCount: segments.length,
          ...(truncated
            ? {
                truncated: true,
                note: `Transcript exceeded ${MAX_TRANSCRIPT_CHARS} chars and was trimmed.`,
              }
            : {}),
          cached: false,
        });
      } catch (err) {
        captionErr = classifyCaptionError(err);
      }

      // ── Non-recoverable caption errors — surface immediately ───────────────
      if (
        captionErr.kind === "rate_limited" ||
        captionErr.kind === "unavailable" ||
        captionErr.kind === "wrong_language" ||
        captionErr.kind === "other"
      ) {
        return jsonResult({ error: captionErr.message });
      }

      // ── Step 2: Gemini AI transcription fallback ───────────────────────────
      // Reached when: kind === "no_captions" | "disabled"

      const videoId = extractVideoId(url);
      if (!videoId) {
        return jsonResult({
          error: `Could not extract a valid YouTube video ID from: ${url}`,
        });
      }

      const geminiApiKey = resolveGeminiApiKey(options?.config);

      if (!geminiApiKey) {
        return jsonResult({
          error:
            `This video has no captions available. ` +
            `AI transcription via Gemini is available but requires GEMINI_API_KEY ` +
            `to be set in the gateway environment or config (tools.web.search.gemini.apiKey).`,
          captionError: captionErr.message,
        });
      }

      const geminiModel = resolveGeminiModel(options?.config);

      let geminiResult: { transcript: string; source: "gemini" };
      try {
        geminiResult = await transcribeWithGemini({
          videoId,
          lang,
          apiKey: geminiApiKey,
          model: geminiModel,
        });
      } catch (err) {
        return jsonResult({
          error:
            `Captions unavailable and AI transcription failed: ${String(err)}`,
          captionError: captionErr.message,
        });
      }

      let { transcript } = geminiResult;
      let truncated = false;
      if (transcript.length > MAX_TRANSCRIPT_CHARS) {
        transcript = transcript.slice(0, MAX_TRANSCRIPT_CHARS);
        truncated = true;
      }

      writeCache(
        TRANSCRIPT_CACHE,
        cacheKey,
        transcript,
        TRANSCRIPT_CACHE_TTL_MINUTES * 60_000,
      );

      return jsonResult({
        transcript,
        source: "gemini_ai",
        model: geminiModel,
        note: "No captions were available — this transcript was generated by Gemini AI and may not be 100% verbatim.",
        ...(truncated
          ? {
              truncated: true,
              truncatedNote: `Transcript exceeded ${MAX_TRANSCRIPT_CHARS} chars and was trimmed.`,
            }
          : {}),
        cached: false,
      });
    },
  };
}
