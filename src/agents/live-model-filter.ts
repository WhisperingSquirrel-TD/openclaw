import {
  isRetainedAnthropicModelId,
  isRetainedOpenAICodexModelId,
} from "./model-affordability-policy.js";

export type ModelRef = {
  provider?: string | null;
  id?: string | null;
};

const OPENAI_MODELS = ["gpt-5.6", "gpt-5.5", "gpt-5.4", "gpt-5.2", "gpt-5.0"];
const GOOGLE_PREFIXES = ["gemini-3"];
const ZAI_PREFIXES = ["glm-5", "glm-4.7", "glm-4.7-flash", "glm-4.7-flashx"];
const MINIMAX_PREFIXES = ["minimax-m2.5", "minimax-m2.5"];
const XAI_PREFIXES = ["grok-4"];

function matchesPrefix(id: string, prefixes: string[]): boolean {
  return prefixes.some((prefix) => id.startsWith(prefix));
}

function matchesExactOrPrefix(id: string, values: string[]): boolean {
  return values.some((value) => id === value || id.startsWith(value));
}

export function isModernModelRef(ref: ModelRef): boolean {
  const provider = ref.provider?.trim().toLowerCase() ?? "";
  const id = ref.id?.trim().toLowerCase() ?? "";
  if (!provider || !id) {
    return false;
  }

  if (provider === "anthropic") {
    return isRetainedAnthropicModelId(id);
  }

  if (provider === "openai") {
    return matchesExactOrPrefix(id, OPENAI_MODELS);
  }

  if (provider === "openai-codex") {
    return isRetainedOpenAICodexModelId(id);
  }

  if (provider === "google" || provider === "google-gemini-cli") {
    return matchesPrefix(id, GOOGLE_PREFIXES);
  }

  if (provider === "zai") {
    return matchesPrefix(id, ZAI_PREFIXES);
  }

  if (provider === "minimax") {
    return matchesPrefix(id, MINIMAX_PREFIXES);
  }

  if (provider === "xai") {
    return matchesPrefix(id, XAI_PREFIXES);
  }

  if (provider === "opencode" && id.endsWith("-free")) {
    return false;
  }
  if (provider === "opencode" && id === "alpha-glm-4.7") {
    return false;
  }
  // Opencode MiniMax variants have been intermittently unstable in live runs;
  // prefer the rest of the modern catalog for deterministic smoke coverage.
  if (provider === "opencode" && matchesPrefix(id, MINIMAX_PREFIXES)) {
    return false;
  }

  if (provider === "openrouter" || provider === "opencode") {
    // OpenRouter/opencode are pass-through proxies; accept any model ID
    // rather than restricting to a static prefix list.
    return true;
  }

  return false;
}
