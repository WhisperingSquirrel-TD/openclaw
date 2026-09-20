import { once } from "node:events";
import { lstat } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { Type } from "@sinclair/typebox";
import type { AnyAgentTool } from "../../../src/agents/tools/common.js";
import { ToolInputError, jsonResult } from "../../../src/agents/tools/common.js";

const WRITE_OPERATIONS = ["create", "update", "append"] as const;
type WriteOperation = (typeof WRITE_OPERATIONS)[number];

type SharePointWriteRequest = {
  operation: WriteOperation;
  path: string;
  content: string;
  baseEtag?: string;
  expectedSourceSha256?: string;
};

type SharePointWriteRunner = (
  request: SharePointWriteRequest,
  signal?: AbortSignal,
) => Promise<Record<string, unknown>>;

const PYTHON_INTERPRETER = "/usr/bin/python3";
const MAX_CONTENT_BYTES = 1_000_000;
const MAX_OUTPUT_BYTES = 64 * 1024;

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ToolInputError("SharePoint write request must be an object");
  }
  return value as Record<string, unknown>;
}

function requiredString(params: Record<string, unknown>, name: string): string {
  const value = params[name];
  if (typeof value !== "string" || !value.trim()) {
    throw new ToolInputError(`${name} must be a non-empty string`);
  }
  return value;
}

function prepareRequest(rawParams: unknown): SharePointWriteRequest {
  const params = asObject(rawParams);
  const operation = requiredString(params, "operation");
  if (!WRITE_OPERATIONS.includes(operation as WriteOperation)) {
    throw new ToolInputError(`operation must be one of: ${WRITE_OPERATIONS.join(", ")}`);
  }
  const destination = requiredString(params, "path");
  const content = requiredString(params, "content");
  const cleanDestination = destination.startsWith("/") ? destination.slice(1) : destination;
  if (
    !cleanDestination ||
    cleanDestination.split("/").some((part) => part === "" || part === "..")
  ) {
    throw new ToolInputError("path must be a single safe SharePoint destination");
  }
  if (Buffer.byteLength(content, "utf8") > MAX_CONTENT_BYTES) {
    throw new ToolInputError(`content must be at most ${MAX_CONTENT_BYTES} bytes`);
  }
  const baseEtag = params.baseEtag;
  const expectedSourceSha256 = params.expectedSourceSha256;
  if (baseEtag !== undefined && (typeof baseEtag !== "string" || !baseEtag.trim())) {
    throw new ToolInputError("baseEtag must be a non-empty string when provided");
  }
  if (
    expectedSourceSha256 !== undefined &&
    (typeof expectedSourceSha256 !== "string" || !/^[a-f0-9]{64}$/i.test(expectedSourceSha256))
  ) {
    throw new ToolInputError("expectedSourceSha256 must be a SHA-256 hex digest");
  }
  return {
    operation: operation as WriteOperation,
    path: destination,
    content,
    ...(baseEtag === undefined ? {} : { baseEtag }),
    ...(expectedSourceSha256 === undefined ? {} : { expectedSourceSha256 }),
  };
}

export function resolveSharePointWriterScript(
  workspaceDir: string,
  environment: NodeJS.ProcessEnv = process.env,
): string {
  return path.resolve(
    environment.OPENCLAW_SHAREPOINT_WRITER_SCRIPT?.trim() ||
      path.join(workspaceDir, "scripts", "sharepoint-queue-writer.py"),
  );
}

async function assertScript(scriptPath: string): Promise<void> {
  const entry = await lstat(scriptPath);
  if (!entry.isFile() || entry.isSymbolicLink()) {
    throw new Error(`SharePoint writer deployment is not a regular file: ${scriptPath}`);
  }
}

export async function runSharePointWrite(
  request: SharePointWriteRequest,
  options: { workspaceDir: string; scriptPath?: string; signal?: AbortSignal },
): Promise<Record<string, unknown>> {
  const scriptPath = options.scriptPath ?? resolveSharePointWriterScript(options.workspaceDir);
  await assertScript(scriptPath);
  const child = spawn(PYTHON_INTERPRETER, [scriptPath], {
    cwd: options.workspaceDir,
    env: { ...process.env, PYTHONNOUSERSITE: "1" },
    stdio: ["pipe", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk: string) => {
    stdout += chunk;
    if (Buffer.byteLength(stdout) > MAX_OUTPUT_BYTES) child.kill("SIGKILL");
  });
  child.stderr.on("data", (chunk: string) => {
    stderr += chunk;
  });
  const abort = () => child.kill("SIGTERM");
  options.signal?.addEventListener("abort", abort, { once: true });
  child.stdin.end(JSON.stringify(request));
  const [code] = (await once(child, "close")) as [number | null];
  options.signal?.removeEventListener("abort", abort);
  if (code !== 0) {
    throw new Error(`SharePoint writer failed (${code ?? "terminated"}): ${stderr.trim().slice(0, 500)}`);
  }
  try {
    return JSON.parse(stdout);
  } catch {
    throw new Error("SharePoint writer returned malformed JSON");
  }
}

export function createSharePointWriteTool(
  options: { run?: SharePointWriteRunner; workspaceDir?: string } = {},
): AnyAgentTool {
  const workspaceDir = options.workspaceDir ?? process.env.OPENCLAW_WORKSPACE ?? process.cwd();
  const run =
    options.run ??
    ((request, signal) =>
      runSharePointWrite(request, {
        workspaceDir,
        signal,
      }));
  return {
    name: "sharepoint_write",
    label: "SharePoint Write",
    description:
      "Owner-only bounded SharePoint writer for the active skill. Pass the exact operation, SharePoint path, and complete Markdown content from the skill. No shell command, queue-file edit, arbitrary destination type, or TOTP approval is needed. A queued response is not confirmation; verify the processor result and cache/readback before reporting completion.",
    ownerOnly: true,
    parameters: Type.Object({
      operation: Type.Union(WRITE_OPERATIONS.map((value) => Type.Literal(value))),
      path: Type.String(),
      content: Type.String(),
      baseEtag: Type.Optional(Type.String()),
      expectedSourceSha256: Type.Optional(Type.String()),
    }),
    async execute(_toolCallId, rawParams, signal) {
      return jsonResult(await run(prepareRequest(rawParams), signal));
    },
  };
}