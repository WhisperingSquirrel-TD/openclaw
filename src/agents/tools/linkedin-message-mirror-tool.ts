import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { Type } from "@sinclair/typebox";
import { stringEnum } from "../schema/typebox.js";
import {
  type AnyAgentTool,
  jsonResult,
  readNumberParam,
  readStringParam,
  ToolInputError,
} from "./common.js";

const execFileAsync = promisify(execFile);

const WORKSPACE = "/home/tomdean88/.openclaw/workspace";
const PROJECT_DIR = path.join(WORKSPACE, "projects/linkedin-message-mirror");
const CAPTURE_SCRIPT = path.join(PROJECT_DIR, "scripts/capture_linkedin_messages.py");
const ROUTE_SCRIPT = path.join(PROJECT_DIR, "scripts/route_linkedin_messages.py");
const PYTHON = path.join(PROJECT_DIR, ".venv/bin/python");

const SNAPSHOT_PATH = path.join(WORKSPACE, "memory/linkedin-messages.json");
const SUMMARY_PATH = path.join(WORKSPACE, "LINKEDIN_MESSAGES.md");
const EVENTS_PATH = path.join(WORKSPACE, "memory/linkedin-mirror-events.json");
const PROPOSALS_PATH = path.join(WORKSPACE, "memory/linkedin-crm-proposals.json");
const PROPOSALS_MD_PATH = path.join(WORKSPACE, "LINKEDIN_CRM_PROPOSALS.md");
const MIRROR_STATE_PATH = path.join(WORKSPACE, "memory/linkedin-mirror-state.json");
const CAPTURE_STATE_PATH = path.join(WORKSPACE, "memory/linkedin-capture-state.json");

const ACTIONS = ["status", "capture", "route", "capture_and_route"] as const;
const ROUTE_MODES = ["baseline", "only_new", "assess_all"] as const;

const LinkedInMessageMirrorToolSchema = Type.Object(
  {
    action: stringEnum(ACTIONS),
    routeMode: Type.Optional(stringEnum(ROUTE_MODES)),
    limitThreads: Type.Optional(Type.Number({ minimum: 1, maximum: 10 })),
    headed: Type.Optional(Type.Boolean()),
    diagnostic: Type.Optional(Type.Boolean()),
    timeoutMs: Type.Optional(Type.Number({ minimum: 1000, maximum: 240000 })),
  },
  { additionalProperties: false },
);

type JsonRecord = Record<string, unknown>;

function normalizeLimitThreads(raw: unknown) {
  const value = typeof raw === "number" && Number.isFinite(raw) ? Math.trunc(raw) : undefined;
  if (value === undefined) {
    return 3;
  }
  if (value < 1 || value > 10) {
    throw new ToolInputError("limitThreads must be between 1 and 10");
  }
  return value;
}

function normalizeTimeoutMs(raw: unknown) {
  const value = typeof raw === "number" && Number.isFinite(raw) ? Math.trunc(raw) : undefined;
  if (value === undefined) {
    return 90_000;
  }
  if (value < 1_000 || value > 240_000) {
    throw new ToolInputError("timeoutMs must be between 1000 and 240000");
  }
  return value;
}

async function readJsonIfExists(filePath: string): Promise<unknown> {
  try {
    const raw = await fs.readFile(filePath, "utf8");
    return JSON.parse(raw);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return null;
    }
    throw err;
  }
}

async function readTextPreview(filePath: string, maxChars = 4000) {
  try {
    const raw = await fs.readFile(filePath, "utf8");
    return raw.length > maxChars ? `${raw.slice(0, maxChars)}…` : raw;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return null;
    }
    throw err;
  }
}

async function scriptExists(filePath: string) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function resolvePython() {
  return (await scriptExists(PYTHON)) ? PYTHON : "python3";
}

async function runFixedScript(params: { script: string; args: string[]; timeoutMs: number }) {
  if (!(await scriptExists(params.script))) {
    throw new Error(`LinkedIn mirror script missing: ${params.script}`);
  }
  const python = await resolvePython();
  const { stdout, stderr } = await execFileAsync(python, [params.script, ...params.args], {
    cwd: PROJECT_DIR,
    timeout: params.timeoutMs,
    maxBuffer: 2 * 1024 * 1024,
    env: {
      ...process.env,
      OPENCLAW_WORKSPACE: WORKSPACE,
    },
  });
  return { stdout, stderr };
}

async function runCapture(params: {
  limitThreads: number;
  headed: boolean;
  diagnostic: boolean;
  timeoutMs: number;
}) {
  const scriptTimeoutMs = Math.max(1_000, Math.min(params.timeoutMs - 5_000, 180_000));
  const args = [
    "--write",
    "--limit-threads",
    String(params.limitThreads),
    "--timeout-ms",
    String(scriptTimeoutMs),
  ];
  if (params.headed) {
    args.push("--headed");
  }
  if (params.diagnostic) {
    args.push("--diagnostic");
  }
  const result = await runFixedScript({
    script: CAPTURE_SCRIPT,
    args,
    timeoutMs: params.timeoutMs,
  });
  return {
    command: "capture_linkedin_messages.py",
    stdout: result.stdout.trim(),
    stderr: result.stderr.trim(),
    snapshot: await readJsonIfExists(SNAPSHOT_PATH),
    summaryPreview: await readTextPreview(SUMMARY_PATH),
    captureState: await readJsonIfExists(CAPTURE_STATE_PATH),
  };
}

async function runRoute(params: { routeMode: string; timeoutMs: number }) {
  const args = ["--write"];
  if (params.routeMode === "baseline") {
    args.push("--baseline");
  }
  if (params.routeMode === "only_new") {
    args.push("--only-new");
  }
  const result = await runFixedScript({ script: ROUTE_SCRIPT, args, timeoutMs: params.timeoutMs });
  let parsed: unknown = null;
  const trimmed = result.stdout.trim();
  if (trimmed) {
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      parsed = trimmed;
    }
  }
  return {
    command: "route_linkedin_messages.py",
    stdout: parsed,
    stderr: result.stderr.trim(),
    events: await readJsonIfExists(EVENTS_PATH),
    proposals: await readJsonIfExists(PROPOSALS_PATH),
    proposalsPreview: await readTextPreview(PROPOSALS_MD_PATH),
    mirrorState: await readJsonIfExists(MIRROR_STATE_PATH),
  };
}

async function statusPayload() {
  return {
    ok: true,
    projectDir: PROJECT_DIR,
    scripts: {
      capture: await scriptExists(CAPTURE_SCRIPT),
      route: await scriptExists(ROUTE_SCRIPT),
      pythonVenv: await scriptExists(PYTHON),
    },
    snapshot: await readJsonIfExists(SNAPSHOT_PATH),
    captureSummaryPreview: await readTextPreview(SUMMARY_PATH),
    captureState: await readJsonIfExists(CAPTURE_STATE_PATH),
    proposals: await readJsonIfExists(PROPOSALS_PATH),
    proposalsPreview: await readTextPreview(PROPOSALS_MD_PATH),
    mirrorState: await readJsonIfExists(MIRROR_STATE_PATH),
  };
}

export function createLinkedInMessageMirrorTool(): AnyAgentTool {
  return {
    label: "LinkedIn Message Mirror",
    name: "linkedin_message_mirror",
    ownerOnly: true,
    description:
      "Operate the local read-only LinkedIn message mirror without shell exec. Supports status, capture, route, and capture_and_route with bounded allowlisted actions only; never sends LinkedIn messages or writes CRM/SharePoint directly.",
    parameters: LinkedInMessageMirrorToolSchema,
    execute: async (_toolCallId, args) => {
      const params = args as JsonRecord;
      const action = readStringParam(params, "action", { required: true });
      const routeMode = readStringParam(params, "routeMode") ?? "only_new";
      if (!ROUTE_MODES.includes(routeMode as (typeof ROUTE_MODES)[number])) {
        throw new ToolInputError(`Unsupported routeMode: ${routeMode}`);
      }
      const limitThreads = normalizeLimitThreads(readNumberParam(params, "limitThreads"));
      const timeoutMs = normalizeTimeoutMs(readNumberParam(params, "timeoutMs"));
      const headed = params.headed === true;
      const diagnostic = params.diagnostic === true;

      if (action === "status") {
        return jsonResult(await statusPayload());
      }
      if (action === "capture") {
        return jsonResult({
          ok: true,
          action,
          result: await runCapture({ limitThreads, headed, diagnostic, timeoutMs }),
        });
      }
      if (action === "route") {
        return jsonResult({
          ok: true,
          action,
          routeMode,
          result: await runRoute({ routeMode, timeoutMs }),
        });
      }
      if (action === "capture_and_route") {
        const capture = await runCapture({ limitThreads, headed, diagnostic, timeoutMs });
        const route = await runRoute({ routeMode, timeoutMs });
        return jsonResult({ ok: true, action, routeMode, capture, route });
      }
      throw new ToolInputError(`Unsupported action: ${action}`);
    },
  };
}
