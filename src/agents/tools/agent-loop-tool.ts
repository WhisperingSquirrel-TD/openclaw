import { Type } from "@sinclair/typebox";
import {
  checkpointContinuation,
  finishContinuation,
  readContinuationState,
  resumeContinuation,
  startContinuation,
} from "../continuation-loop.js";
import type { AnyAgentTool } from "./common.js";
import { jsonResult } from "./common.js";

type AgentLoopParams = {
  action:
    | "start"
    | "resume"
    | "checkpoint"
    | "complete"
    | "block"
    | "cancel"
    | "stop"
    | "status";
  objective?: string;
  checkpoint?: string;
  reason?: string;
  maxTurns?: number;
  maxWallClockSeconds?: number;
};

export function createAgentLoopTool(params: {
  agentDir: string;
  sessionId: string;
  sessionKey?: string;
  /** Must be set by the trusted ingress that exposes this controller. */
  trustedOwner: true;
}): AnyAgentTool {
  return {
    name: "agent_loop",
    label: "Agent Continuation Loop",
    description:
      "Owner-only bounded continuation controller. Use only when the owner explicitly asks to keep working without repeated prompts. Start with a concrete objective, checkpoint each completed step with a compact factual summary, and complete or block the loop at its natural end. Never use it for open-ended monitoring or infinite work.",
    ownerOnly: true,
    parameters: Type.Object(
      {
        action: Type.Union(
          [
            Type.Literal("start"),
            Type.Literal("resume"),
            Type.Literal("checkpoint"),
            Type.Literal("complete"),
            Type.Literal("block"),
            Type.Literal("cancel"),
            Type.Literal("stop"),
            Type.Literal("status"),
          ],
          { description: "Continuation lifecycle action." },
        ),
        objective: Type.Optional(
          Type.String({ description: "Concrete owner-approved objective." }),
        ),
        checkpoint: Type.Optional(
          Type.String({
            description: "Compact factual progress summary, not a transcript.",
          }),
        ),
        reason: Type.Optional(
          Type.String({
            description: "Completion, block, or cancellation reason.",
          }),
        ),
        maxTurns: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })),
        maxWallClockSeconds: Type.Optional(
          Type.Integer({ minimum: 30, maximum: 1800 }),
        ),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, rawParams) {
      const input = rawParams as AgentLoopParams;
      try {
        if (input.action === "status") {
          return jsonResult({
            ok: true,
            state: await readContinuationState(params),
          });
        }
        if (input.action === "start") {
          return jsonResult({
            ok: true,
            state: await startContinuation({
              ...params,
              objective: input.objective ?? "",
              checkpoint: input.checkpoint,
              maxTurns: input.maxTurns,
              maxWallClockSeconds: input.maxWallClockSeconds,
            }),
          });
        }
        if (input.action === "resume") {
          return jsonResult({
            ok: true,
            state: await resumeContinuation({
              ...params,
              maxTurns: input.maxTurns,
              maxWallClockSeconds: input.maxWallClockSeconds,
            }),
          });
        }
        if (input.action === "checkpoint") {
          return jsonResult({
            ok: true,
            state: await checkpointContinuation({
              ...params,
              checkpoint: input.checkpoint ?? "",
            }),
          });
        }
        if (
          input.action === "complete" ||
          input.action === "block" ||
          input.action === "cancel" ||
          input.action === "stop"
        ) {
          return jsonResult({
            ok: true,
            state: await finishContinuation({
              ...params,
              status:
                input.action === "complete"
                  ? "completed"
                  : input.action === "block"
                    ? "blocked"
                    : "cancelled",
              reason: input.reason,
            }),
          });
        }
        return jsonResult({ ok: false, error: "Unknown continuation action." });
      } catch (error) {
        return jsonResult({
          ok: false,
          error:
            error instanceof Error
              ? error.message
              : "Continuation action failed.",
        });
      }
    },
  };
}
