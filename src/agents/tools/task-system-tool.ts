import fs from "node:fs/promises";
import { Type } from "@sinclair/typebox";
import { stringEnum } from "../schema/typebox.js";
import {
  type AnyAgentTool,
  jsonResult,
  readStringOrNumberParam,
  readStringParam,
  ToolInputError,
} from "./common.js";

const DEFAULT_BASE_URL = "http://127.0.0.1:4312";
const DEFAULT_ENV_PATH = "/home/tomdean88/.config/workspace-pi-gateway/env";

const TASK_SYSTEM_ACTIONS = [
  "summary",
  "capture",
  "capture_batch",
  "decompose",
  "commit",
  "self_check",
  "subtask_start",
  "subtask_complete",
  "entity_context",
  "entity_timeline",
  "list",
  "get",
  "create",
  "patch",
  "view",
  "seed",
  "operator_state",
  "operator_state_patch",
  "operator_signal",
  "operator_check",
] as const;

const TASK_ENTITY_KINDS = ["strategy", "objective", "task", "subtask"] as const;
const TASK_SYSTEM_VIEWS = ["subtasks_by_owner_state", "tasks_by_objective_state"] as const;

const TaskSystemToolSchema = Type.Object(
  {
    action: stringEnum(TASK_SYSTEM_ACTIONS),
    kind: Type.Optional(stringEnum(TASK_ENTITY_KINDS)),
    id: Type.Optional(Type.String()),
    view: Type.Optional(stringEnum(TASK_SYSTEM_VIEWS)),
    parent_id: Type.Optional(Type.String()),
    state: Type.Optional(Type.String()),
    owner: Type.Optional(Type.String()),
    payload: Type.Optional(Type.Object({}, { additionalProperties: true })),
    baseUrl: Type.Optional(Type.String()),
    authToken: Type.Optional(Type.String()),
    envPath: Type.Optional(Type.String()),
    timeoutMs: Type.Optional(Type.Number()),
  },
  { additionalProperties: true },
);

type JsonRecord = Record<string, unknown>;

type TaskSystemToolOptions = {
  defaultBaseUrl?: string;
  defaultEnvPath?: string;
};

function normalizeBaseUrl(raw?: string) {
  const base = (raw ?? DEFAULT_BASE_URL).trim().replace(/\/$/, "");
  if (!base) {
    throw new ToolInputError("baseUrl required");
  }
  return base;
}

function normalizeTimeoutMs(raw: unknown) {
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return Math.max(1, Math.floor(raw));
  }
  return 30_000;
}

async function readGatewayBearerToken(envPath: string) {
  const raw = await fs.readFile(envPath, "utf8");
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const idx = trimmed.indexOf("=");
    if (idx <= 0) {
      continue;
    }
    const key = trimmed.slice(0, idx).trim();
    if (key !== "WORKSPACE_PI_GATEWAY_TOKEN") {
      continue;
    }
    const value = trimmed.slice(idx + 1).trim();
    if (value) {
      return value;
    }
  }
  throw new Error(`WORKSPACE_PI_GATEWAY_TOKEN not found in ${envPath}`);
}

function resolveEntityPath(kind: string) {
  switch (kind) {
    case "strategy":
      return "strategies";
    case "objective":
      return "objectives";
    case "task":
      return "tasks";
    case "subtask":
      return "subtasks";
    default:
      throw new ToolInputError(`Unsupported kind: ${kind}`);
  }
}

function resolveViewPath(view: string) {
  switch (view) {
    case "subtasks_by_owner_state":
      return "views/subtasks-by-owner-state";
    case "tasks_by_objective_state":
      return "views/tasks-by-objective-state";
    default:
      throw new ToolInputError(`Unsupported view: ${view}`);
  }
}

function inferParentKindForCreate(kind: string) {
  switch (kind) {
    case "objective":
      return "strategy";
    case "task":
      return "objective";
    case "subtask":
      return "task";
    default:
      return null;
  }
}

function appendViewFilters(path: string, params: Record<string, unknown>) {
  const query = new URLSearchParams();
  for (const key of ["parent_id", "state", "owner"]) {
    const value = readStringParam(params, key, { trim: true });
    if (value) {
      query.set(key, value);
    }
  }
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}

async function callTaskSystem(params: {
  method: "GET" | "POST" | "PATCH";
  path: string;
  baseUrl: string;
  token: string;
  timeoutMs: number;
  payload?: JsonRecord;
}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), params.timeoutMs);
  try {
    const res = await fetch(`${params.baseUrl}${params.path}`, {
      method: params.method,
      headers: {
        Authorization: `Bearer ${params.token}`,
        ...(params.payload ? { "Content-Type": "application/json" } : {}),
      },
      body: params.payload ? JSON.stringify(params.payload) : undefined,
      signal: controller.signal,
    });
    const text = await res.text();
    let parsed: unknown = text;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = text;
      }
    }
    if (!res.ok) {
      throw new Error(
        `Task system request failed (${res.status} ${res.statusText}): ${typeof parsed === "string" ? parsed : JSON.stringify(parsed)}`,
      );
    }
    return parsed;
  } finally {
    clearTimeout(timer);
  }
}

export function createTaskSystemTool(opts?: TaskSystemToolOptions): AnyAgentTool {
  return {
    label: "Task System",
    name: "task_system",
    ownerOnly: true,
    description:
      "Operate the Workspace Control Panel task system directly over its bearer-authenticated Pi gateway without shell exec. Supports fast capture/capture_batch, intake decompose/commit, entity context/timeline, CRUD, views, seed, and operator control actions.",
    parameters: TaskSystemToolSchema,
    execute: async (_toolCallId, args) => {
      const params = args as Record<string, unknown>;
      const action = readStringParam(params, "action", { required: true });
      const baseUrl = normalizeBaseUrl(
        readStringParam(params, "baseUrl", { trim: false }) ?? opts?.defaultBaseUrl,
      );
      const envPath =
        readStringParam(params, "envPath", { trim: false }) ??
        opts?.defaultEnvPath ??
        DEFAULT_ENV_PATH;
      const authToken =
        readStringParam(params, "authToken", { trim: false }) ??
        (await readGatewayBearerToken(envPath));
      const timeoutMs = normalizeTimeoutMs(params.timeoutMs);
      const payload =
        params.payload && typeof params.payload === "object" && !Array.isArray(params.payload)
          ? ({ ...(params.payload as JsonRecord) } as JsonRecord)
          : undefined;

      if (action === "summary") {
        const result = await callTaskSystem({
          method: "GET",
          path: "/task-board/summary",
          baseUrl,
          token: authToken,
          timeoutMs,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "capture") {
        const result = await callTaskSystem({
          method: "POST",
          path: "/task-intake/capture",
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "capture_batch") {
        const result = await callTaskSystem({
          method: "POST",
          path: "/task-intake/capture-batch",
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "decompose") {
        const result = await callTaskSystem({
          method: "POST",
          path: "/task-intake/decompose",
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "commit") {
        const result = await callTaskSystem({
          method: "POST",
          path: "/task-intake/commit",
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "seed") {
        const result = await callTaskSystem({
          method: "POST",
          path: "/task-system/seed",
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "self_check") {
        const result = await callTaskSystem({
          method: "POST",
          path: "/task-system/self-check",
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "view") {
        const view = readStringParam(params, "view", { required: true });
        const result = await callTaskSystem({
          method: "GET",
          path: `/${appendViewFilters(resolveViewPath(view), params)}`,
          baseUrl,
          token: authToken,
          timeoutMs,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "operator_state") {
        const result = await callTaskSystem({
          method: "GET",
          path: "/task-system/operator-state",
          baseUrl,
          token: authToken,
          timeoutMs,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "operator_state_patch") {
        const result = await callTaskSystem({
          method: "PATCH",
          path: "/task-system/operator-state",
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "operator_signal") {
        const result = await callTaskSystem({
          method: "POST",
          path: "/task-system/operator-signal",
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "operator_check") {
        const result = await callTaskSystem({
          method: "POST",
          path: "/task-system/operator-check",
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      const kind = readStringParam(params, "kind", { required: true });
      const entityPath = resolveEntityPath(kind);

      if (action === "list") {
        const result = await callTaskSystem({
          method: "GET",
          path: `/${entityPath}`,
          baseUrl,
          token: authToken,
          timeoutMs,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "create") {
        const createPayload: JsonRecord = { ...payload };
        const parentId = readStringParam(params, "parent_id", { trim: true });
        if (parentId) {
          createPayload.parent_id = parentId;
          if (!readStringParam(createPayload, "parent_kind", { trim: true })) {
            const inferredParentKind = inferParentKindForCreate(kind);
            if (inferredParentKind) {
              createPayload.parent_kind = inferredParentKind;
            }
          }
        }
        const result = await callTaskSystem({
          method: "POST",
          path: `/${entityPath}`,
          baseUrl,
          token: authToken,
          timeoutMs,
          payload: createPayload,
        });
        return jsonResult({ ok: true, result });
      }

      const id = readStringOrNumberParam(params, "id", { required: true });

      if (action === "subtask_start") {
        if (kind !== "subtask") {
          throw new ToolInputError("subtask_start requires kind=subtask");
        }
        const result = await callTaskSystem({
          method: "POST",
          path: `/${entityPath}/${encodeURIComponent(id)}/start`,
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "subtask_complete") {
        if (kind !== "subtask") {
          throw new ToolInputError("subtask_complete requires kind=subtask");
        }
        const result = await callTaskSystem({
          method: "POST",
          path: `/${entityPath}/${encodeURIComponent(id)}/complete`,
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "get") {
        const result = await callTaskSystem({
          method: "GET",
          path: `/${entityPath}/${encodeURIComponent(id)}`,
          baseUrl,
          token: authToken,
          timeoutMs,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "patch") {
        const result = await callTaskSystem({
          method: "PATCH",
          path: `/${entityPath}/${encodeURIComponent(id)}`,
          baseUrl,
          token: authToken,
          timeoutMs,
          payload,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "entity_context") {
        const result = await callTaskSystem({
          method: "GET",
          path: `/entities/${entityPath}/${encodeURIComponent(id)}/context`,
          baseUrl,
          token: authToken,
          timeoutMs,
        });
        return jsonResult({ ok: true, result });
      }

      if (action === "entity_timeline") {
        const result = await callTaskSystem({
          method: "GET",
          path: `/entities/${entityPath}/${encodeURIComponent(id)}/timeline`,
          baseUrl,
          token: authToken,
          timeoutMs,
        });
        return jsonResult({ ok: true, result });
      }

      throw new ToolInputError(`Unsupported action: ${action}`);
    },
  };
}
