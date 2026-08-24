import { Type } from "@sinclair/typebox";
import type { AnyAgentTool } from "../../../src/agents/tools/common.js";
import { jsonResult } from "../../../src/agents/tools/common.js";
import type { SkilzVoltClient, SkilzVoltToolName } from "./client.js";
import { SKILZVOLT_ALLOWED_TOOLS, SkilzVoltError } from "./client.js";
import type { SkilzVoltMigrationManager } from "./migration.js";

const stringEnum = <T extends readonly string[]>(values: T, description: string) =>
  Type.Unsafe<T[number]>({
    type: "string",
    enum: [...values],
    description,
  });

const ArgumentsSchema = Type.Record(Type.String(), Type.Unknown(), {
  description: "Arguments matching the live SkilzVolt tool schema returned by describe.",
});

type SkilzVoltParams = {
  action: "describe" | "call";
  toolName?: SkilzVoltToolName;
  arguments?: Record<string, unknown>;
};

type MigrationParams = {
  action: "inventory" | "preview" | "submit" | "submit_all" | "recover" | "verify_and_retire";
  skillName?: string;
  workspaceId?: string;
  migrationOperationId?: string;
  clientRef?: string;
  items?: Array<{
    client_ref: string;
    name: string;
    description?: string;
    content: string;
    suggested_purpose?: string;
    suggested_rules?: string;
    rationale?: string;
  }>;
  arguments?: Record<string, unknown>;
  contentParameter?: string;
  proposalStatusArguments?: Record<string, unknown>;
};

function publicError(error: unknown): ReturnType<typeof jsonResult> {
  if (error instanceof SkilzVoltError) {
    return jsonResult({ ok: false, error: error.message, kind: error.kind });
  }
  return jsonResult({
    ok: false,
    error: error instanceof Error ? error.message.slice(0, 500) : "Unknown SkilzVolt error",
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
        action: stringEnum(["describe", "call"] as const, "Describe allowed tools or call one."),
        toolName: Type.Optional(
          stringEnum(SKILZVOLT_ALLOWED_TOOLS, "Exact allowed SkilzVolt tool name."),
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
          result: await client.callTool(params.toolName, params.arguments ?? {}, signal),
        });
      } catch (error) {
        return publicError(error);
      }
    },
  };
}

export function createSkilzVoltMigrationTool(migration: SkilzVoltMigrationManager): AnyAgentTool {
  return {
    name: "skilzvolt_local_migration",
    label: "SkilzVolt Local Skill Migration",
    description:
      "Owner-only migration control. Inventory and preview are read-only. Preview the complete local skill inventory, submit only preview-approved new items with stable migration_operation_id/client_ref values, and use recover after uncertain requests. No action deletes a local skill; verify_and_retire requires approved/current status plus byte-for-byte readback.",
    ownerOnly: true,
    parameters: Type.Object(
      {
        action: stringEnum(
          ["inventory", "preview", "submit", "submit_all", "recover", "verify_and_retire"] as const,
          "Migration action. Use preview before submit_all.",
        ),
        skillName: Type.Optional(
          Type.String({ description: "Configured organisation skill name." }),
        ),
        workspaceId: Type.Optional(
          Type.String({ description: "Target writable SkilzVolt workspace ID." }),
        ),
        migrationOperationId: Type.Optional(
          Type.String({ description: "Stable idempotency key reused across retries." }),
        ),
        clientRef: Type.Optional(
          Type.String({ description: "Stable item reference used by preview and recovery." }),
        ),
        items: Type.Optional(
          Type.Array(
            Type.Object({
              client_ref: Type.String(),
              name: Type.String(),
              description: Type.Optional(Type.String()),
              content: Type.Optional(
                Type.String({
                  description:
                    "Optional integrity check. The bridge loads the exact active local SKILL.md itself.",
                }),
              ),
              suggested_purpose: Type.Optional(Type.String()),
              suggested_rules: Type.Optional(Type.String()),
              rationale: Type.Optional(Type.String()),
            }),
          ),
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
        proposalStatusArguments: Type.Optional(
          Type.Record(Type.String(), Type.Unknown(), {
              description: "Live skills_proposal_status arguments for the recorded proposal.",
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
        if (params.action === "preview") {
          return jsonResult({
            ok: true,
            result: await migration.previewAll({ workspaceId: params.workspaceId, signal }),
          });
        }
        if (params.action === "submit_all") {
          if (!params.migrationOperationId || !params.items) {
            throw new Error("migrationOperationId and items are required for action=submit_all");
          }
          return jsonResult({
            ok: true,
            result: await migration.submitAll({
              workspaceId: params.workspaceId,
              migrationOperationId: params.migrationOperationId,
              items: params.items,
              signal,
            }),
          });
        }
        if (params.action === "recover") {
          if (!params.workspaceId || !params.migrationOperationId || !params.clientRef) {
            throw new Error(
              "workspaceId, migrationOperationId, and clientRef are required for action=recover",
            );
          }
          return jsonResult({
            ok: true,
            result: await migration.recover({
              workspaceId: params.workspaceId,
              migrationOperationId: params.migrationOperationId,
              clientRef: params.clientRef,
              signal,
            }),
          });
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
            proposalStatusArguments: params.proposalStatusArguments ?? {},
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
