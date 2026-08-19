const RETAINED_ANTHROPIC_MODEL_IDS = new Set(["claude-sonnet-5"]);
const RETAINED_OPENAI_CODEX_MODEL_IDS = new Set(["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]);

function normalizedModelId(modelId: string): string {
  return modelId.trim().toLowerCase();
}

export function isRetainedAnthropicModelId(modelId: string): boolean {
  return RETAINED_ANTHROPIC_MODEL_IDS.has(normalizedModelId(modelId));
}

export function isRetainedOpenAICodexModelId(modelId: string): boolean {
  return RETAINED_OPENAI_CODEX_MODEL_IDS.has(normalizedModelId(modelId));
}
