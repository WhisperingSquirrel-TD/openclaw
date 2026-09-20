import { describe, expect, it } from "vitest";
import {
  MAC_QWEN_BASE_URL,
  MAC_QWEN_MODEL_ID,
  MAC_QWEN_MODEL_REF,
  MAC_QWEN_PROVIDER,
  buildMacQwenProviderConfig,
  resolveMacQwenInstalledModel,
} from "./mac-qwen-route.js";

describe("Mac Mini Qwen route", () => {
  it("serializes the exact OpenAI-compatible local provider contract", () => {
    expect(buildMacQwenProviderConfig()).toEqual({
      baseUrl: MAC_QWEN_BASE_URL,
      apiKey: "ollama-local",
      api: "openai-completions",
      timeoutSeconds: 1800,
      models: [
        {
          id: MAC_QWEN_MODEL_ID,
          name: MAC_QWEN_MODEL_ID,
          reasoning: false,
          input: ["text"],
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: 16384,
          maxTokens: 2048,
        },
      ],
    });
    expect(`${MAC_QWEN_PROVIDER}/${MAC_QWEN_MODEL_ID}`).toBe(MAC_QWEN_MODEL_REF);
  });

  it("accepts only the exact model or its explicit latest tag", () => {
    expect(resolveMacQwenInstalledModel(["other", `${MAC_QWEN_MODEL_ID}:latest`])).toBe(
      `${MAC_QWEN_MODEL_ID}:latest`,
    );
    expect(resolveMacQwenInstalledModel([MAC_QWEN_MODEL_ID, "other"])).toBe(MAC_QWEN_MODEL_ID);
  });

  it("fails closed for missing or forbidden models", () => {
    expect(() => resolveMacQwenInstalledModel([])).toThrow(/exact model/i);
    expect(() => resolveMacQwenInstalledModel(["qwen3-coder-next"])).toThrow(/exact model/i);
  });
});