export const SKILZVOLT_ENDPOINT = "https://app.skilzvolt.com/mcp";

export const DEFAULT_ORGANISATION_SKILLS = [
  "app-plan",
  "app-init",
  "app-build",
  "app-test",
  "app-deploy",
  "app-patch",
  "app-resume",
  "mgmt-bot",
  "sharepoint",
  "youtube-transcript",
] as const;

export type SkilzVoltConfig = {
  connectionKeyEnv: string;
  allowProposals: boolean;
  agentIds: string[];
  organisationSkillNames: string[];
};

function readStringArray(
  value: unknown,
  fallback: readonly string[],
): string[] {
  if (!Array.isArray(value)) {
    return [...fallback];
  }
  const values = value
    .filter((entry): entry is string => typeof entry === "string")
    .map((entry) => entry.trim())
    .filter(Boolean);
  return [...new Set(values)];
}

export function resolveSkilzVoltConfig(raw: unknown): SkilzVoltConfig {
  const value =
    raw && typeof raw === "object" && !Array.isArray(raw)
      ? (raw as Record<string, unknown>)
      : {};
  const connectionKeyEnv =
    typeof value.connectionKeyEnv === "string" && value.connectionKeyEnv.trim()
      ? value.connectionKeyEnv.trim()
      : "SKILZVOLT_CONNECTION_KEY";
  if (!/^[A-Z_][A-Z0-9_]*$/.test(connectionKeyEnv)) {
    throw new Error(
      "SkilzVolt connectionKeyEnv must be an uppercase environment variable name",
    );
  }
  return {
    connectionKeyEnv,
    allowProposals: value.allowProposals !== false,
    agentIds: readStringArray(value.agentIds, ["main"]),
    organisationSkillNames: readStringArray(
      value.organisationSkillNames,
      DEFAULT_ORGANISATION_SKILLS,
    ),
  };
}
