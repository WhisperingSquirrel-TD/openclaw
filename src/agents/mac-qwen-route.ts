import type { ModelProviderConfig } from "../config/types.models.js";
import { OLLAMA_LOCAL_AUTH_MARKER } from "./model-auth-markers.js";

export const MAC_QWEN_PROVIDER = "custom-mac-ollama";
export const MAC_QWEN_MODEL_ID = "qwen3-coder-131k";
export const MAC_QWEN_MODEL_REF = `${MAC_QWEN_PROVIDER}/${MAC_QWEN_MODEL_ID}`;
export const MAC_QWEN_BASE_URL = "http://192.168.86.46:11434/v1";
export const MAC_QWEN_NATIVE_BASE_URL = "http://192.168.86.46:11434";
export const MAC_QWEN_TIMEOUT_SECONDS = 1800;
export const MAC_QWEN_CONTEXT_WINDOW = 16384;
export const MAC_QWEN_MAX_TOKENS = 2048;

export function isMacQwenProvider(provider: string | undefined): boolean {
  return provider?.trim().toLowerCase() === MAC_QWEN_PROVIDER;
}

export function isLocalOllamaProvider(provider: string | undefined): boolean {
  const normalized = provider?.trim().toLowerCase();
  return normalized === "ollama" || normalized === MAC_QWEN_PROVIDER;
}

export function buildMacQwenProviderConfig(): ModelProviderConfig {
  return {
    baseUrl: MAC_QWEN_BASE_URL,
    apiKey: OLLAMA_LOCAL_AUTH_MARKER,
    api: "openai-completions",
    timeoutSeconds: MAC_QWEN_TIMEOUT_SECONDS,
    models: [
      {
        id: MAC_QWEN_MODEL_ID,
        name: MAC_QWEN_MODEL_ID,
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: MAC_QWEN_CONTEXT_WINDOW,
        maxTokens: MAC_QWEN_MAX_TOKENS,
      },
    ],
  };
}

export function resolveMacQwenInstalledModel(modelNames: string[]): string {
  const exact = new Set([MAC_QWEN_MODEL_ID, `${MAC_QWEN_MODEL_ID}:latest`]);
  const match = modelNames.find((name) => exact.has(name.trim()));
  if (!match) {
    throw new Error(
      `Mac Qwen route requires exact model ${MAC_QWEN_MODEL_ID} or ${MAC_QWEN_MODEL_ID}:latest; refusing to select another model`,
    );
  }
  return match.trim();
}