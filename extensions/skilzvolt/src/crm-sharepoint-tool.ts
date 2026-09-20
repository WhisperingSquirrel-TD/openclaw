import { once } from "node:events";
import { lstat } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { Type } from "@sinclair/typebox";
import type { AnyAgentTool } from "../../../src/agents/tools/common.js";
import { ToolInputError, jsonResult } from "../../../src/agents/tools/common.js";

const CRM_ACTIONS = ["preview", "run_pending"] as const;
type CrmAction = (typeof CRM_ACTIONS)[number];

type CrmBridgeRequest = {
  action: CrmAction;
};

type CrmBridgeRunner = (
  request: CrmBridgeRequest,
  signal?: AbortSignal,
) => Promise<Record<string, unknown>>;

const PYTHON_INTERPRETER = "/usr/bin/python3";
const MAX_BRIDGE_OUTPUT_BYTES = 256 * 1024;

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ToolInputError("CRM SharePoint request must be an object");
  }
  return value as Record<string, unknown>;
}

function prepareRequest(rawParams: unknown): CrmBridgeRequest {
  const params = asObject(rawParams);
  const action = params.action;
  if (typeof action !== "string" || !CRM_ACTIONS.includes(action as CrmAction)) {
    throw new ToolInputError(`action must be one of: ${CRM_ACTIONS.join(", ")}`);
  }
  return { action: action as CrmAction };
}

async function assertBridgeScript(scriptPath: string): Promise<void> {
  const entry = await lstat(scriptPath);
  if (!entry.isFile() || entry.isSymbolicLink()) {
    throw new Error(`CRM handoff deployment is not a regular file: ${scriptPath}`);
  }
}

export function resolveCrmBridgeScript(
  workspaceDir: string,
  environment: NodeJS.ProcessEnv = process.env,
): string {
  const configured = environment.OPENCLAW_CRM_HANDOFF_SCRIPT?.trim();
  if (configured) {
    return path.resolve(configured);
  }
  return path.resolve(workspaceDir, "scripts", "crm-capture-handoff.py");
}

export async function runCrmSharePointBridge(
  request: CrmBridgeRequest,
  options: {
    workspaceDir: string;
    scriptPath?: string;
    signal?: AbortSignal;
  },
): Promise<Record<string, unknown>> {
  const scriptPath =
    options.scriptPath ?? resolveCrmBridgeScript(options.workspaceDir);
  await assertBridgeScript(scriptPath);

  const args = [scriptPath];
  if (request.action === "run_pending") args.push("--execute");
  const child = spawn(PYTHON_INTERPRETER, args, {
    cwd: options.workspaceDir,
    env: {
      ...process.env,
      PYTHONNOUSERSITE: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk: string) => {
    stdout += chunk;
    if (Buffer.byteLength(stdout) > MAX_BRIDGE_OUTPUT_BYTES) child.kill("SIGKILL");
  });
  child.stderr.on("data", (chunk: string) => {
    stderr += chunk;
  });
  const abort = () => child.kill("SIGTERM");
  options.signal?.addEventListener("abort", abort, { once: true });
  const [code] = (await once(child, "close")) as [number | null];
  options.signal?.removeEventListener("abort", abort);
  if (code !== 0) {
    throw new Error(
      `CRM SharePoint bridge failed (${code ?? "terminated"}): ${stderr.trim().slice(0, 500)}`,
    );
  }
  try {
    return {
      ok: true,
      bridge: "crm_sharepoint",
      action: request.action,
      result: JSON.parse(stdout),
    };
  } catch {
    throw new Error("CRM SharePoint bridge returned malformed JSON");
  }
}

export function createCrmSharePointTool(
  options: {
    run?: CrmBridgeRunner;
    workspaceDir?: string;
  } = {},
): AnyAgentTool {
  const workspaceDir = options.workspaceDir ?? process.env.OPENCLAW_WORKSPACE ?? process.cwd();
  const run =
    options.run ??
    ((request, signal) =>
      runCrmSharePointBridge(request, {
        workspaceDir,
        signal,
      }));
  return {
    name: "crm_sharepoint",
    label: "CRM SharePoint Handoff",
    description:
      "Owner-only, no-TOTP CRM/SharePoint route. Preview or run the bounded pending CRM handoff through the service-owned SharePoint queue producer. It has no arbitrary command, path, entity, or message capability. A queued operation is not complete until the processor result and destination-native readback prove both the dated artifact and Current.md update.",
    ownerOnly: true,
    parameters: Type.Object(
      {
        action: Type.Union(CRM_ACTIONS.map((value) => Type.Literal(value))),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, rawParams, signal) {
      return jsonResult(await run(prepareRequest(rawParams), signal));
    },
  };
}