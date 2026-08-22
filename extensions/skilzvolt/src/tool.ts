import { Type } from "@sinclair/typebox";
import type { AnyAgentTool } from "../../../src/agents/tools/common.js";
import { jsonResult } from "../../../src/agents/tools/common.js";
import type { SkilzVoltClient, SkilzVoltToolName } from "./client.js";
import { SKILZVOLT_ALLOWED_TOOLS, SkilzVoltError } from "./client.js";
import type { SkilzVoltMigrationManager } from "./migration.js";

const stringEnum = <T extends readonly string[]>(
  values: T,
  description: string,
) =>
  Type.Unsafe<T[number]>({
    type: "string",
    enum: [...values],
    description,
  });

const ArgumentsSchema = Type.Record(Type.String(), Type.Unknown(), {
  description:
    "Arguments matching the live SkilzVolt tool schema returned by describe.",
});

type SkilzVoltParams = {
  action: "describe" | "call";
  toolName?: SkilzVoltToolName;
  arguments?: Record<string, unknown>;
};

type MigrationParams = {
  action: "inventory" | "submit" | "verify_and_retire";
  skillName?: string;
  arguments?: Record<string, unknown>;
  contentParameter?: string;
};

function publicError(error: unknown): ReturnType<typeof jsonResult> {
  if (error instanceof SkilzVoltError) {
    return jsonResult({ ok: false, error: error.message, kind: error.kind });
  }
  return jsonResult({
    ok: false,
    error:
      error instanceof Error
        ? error.message.slice(0, 500)
        : "Unknown SkilzVolt error",
  });
}

export function createSkilzVoltTool(client: SkilzVoltClient): AnyAgentTool {
  return {
    name: "skilzvolt",
    label: "SkilzVolt",
    description:
      "Read live organisation workspaces and governed skills from SkilzVolt, or submit governed skill proposals. Use describe first for the live schemas. This fixed adapter cannot call arbitrary MCP servers or unapproved tools.",
    ownerOnly: true,
    parameters: Type.Object(
      {
        action: stringEnum(
          ["describe", "call"] as const,
          "Describe allowed tools or call one.",
        ),
        toolName: Type.Optional(
          stringEnum(
            SKILZVOLT_ALLOWED_TOOLS,
            "Exact allowed SkilzVolt tool name.",
          ),
        ),
        arguments: Type.Optional(ArgumentsSchema),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, rawParams, signal) {
      const params = rawParams as SkilzVoltParams;
      try {
        if (params.action === "describe") {
          return jsonResult({
            ok: true,
            tools: await client.listTools(signal),
          });
        }
        if (!params.toolName) {
          throw new Error("toolName is required for action=call");
        }
        return jsonResult({
          ok: true,
          toolName: params.toolName,
          result: await client.callTool(
            params.toolName,
            params.arguments ?? {},
            signal,
          ),
        });
      } catch (error) {
        return publicError(error);
      }
    },
  };
}

export function createSkilzVoltMigrationTool(
  migration: SkilzVoltMigrationManager,
): AnyAgentTool {
  return {
    name: "skilzvolt_local_migration",
    label: "SkilzVolt Local Skill Migration",
    description:
      "Owner-only migration control. Inventory is dry-run. Submit injects the exact local SKILL.md into a governed proposal and never deletes it. verify_and_retire deletes only after skills_get returns an exact current content match.",
    ownerOnly: true,
    parameters: Type.Object(
      {
        action: stringEnum(
          ["inventory", "submit", "verify_and_retire"] as const,
          "Migration action.",
        ),
        skillName: Type.Optional(
          Type.String({ description: "Configured organisation skill name." }),
        ),
        arguments: Type.Optional(
          Type.Record(Type.String(), Type.Unknown(), {
            description:
              "Live skills_create or skills_get arguments. For submit, content is replaced with the local file.",
          }),
        ),
        contentParameter: Type.Optional(
          Type.String({
            description:
              "For submit, the exact live skills_create schema property that carries skill content.",
          }),
        ),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, rawParams, signal) {
      const params = rawParams as MigrationParams;
      try {
        if (params.action === "inventory") {
          return jsonResult({ ok: true, result: await migration.inventory() });
        }
        if (!params.skillName) {
          throw new Error("skillName is required for this migration action");
        }
        if (params.action === "submit") {
          if (!params.contentParameter) {
            throw new Error("contentParameter is required for action=submit");
          }
          return jsonResult({
            ok: true,
            result: await migration.submit({
              skillName: params.skillName,
              createArguments: params.arguments ?? {},
              contentParameter: params.contentParameter,
              signal,
            }),
          });
        }
        return jsonResult({
          ok: true,
          result: await migration.verifyAndRetire({
            skillName: params.skillName,
            getArguments: params.arguments ?? {},
            signal,
          }),
        });
      } catch (error) {
        return publicError(error);
      }
    },
  };
}
