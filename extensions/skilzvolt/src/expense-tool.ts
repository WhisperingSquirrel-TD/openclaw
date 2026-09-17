import { spawn } from "node:child_process";
import { once } from "node:events";
import { lstat, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { Type } from "@sinclair/typebox";
import type { AnyAgentTool } from "../../../src/agents/tools/common.js";
import { ToolInputError, jsonResult } from "../../../src/agents/tools/common.js";
import { resolveStateDir } from "../../../src/config/paths.js";

const EXPENSE_ACTIONS = [
  "read_expense_workbook",
  "capture_expense",
  "upload_expense_receipt",
] as const;
const RECEIPT_FOLDERS = [
  "Anthropic",
  "ChatGPT",
  "Meals & Refreshments",
  "Not organised",
  "OpenAI API",
  "Receipts",
  "Replit",
  "SEER",
] as const;

type ExpenseAction = (typeof EXPENSE_ACTIONS)[number];
type ReceiptFolder = (typeof RECEIPT_FOLDERS)[number];
type ExpenseFacts = {
  source_timestamp?: string;
  observed_timestamp?: string;
  supplier?: string;
  amount_pence?: number;
  currency?: string;
  expense_date?: string;
  category?: string;
  evidence_ref?: string;
  evidence_state?: string;
  settlement_state?: string;
  finance_ledger_ref?: string;
  validation_result?: string;
};
type ExpenseBridgeRequest = {
  action: ExpenseAction;
  page?: number;
  page_size?: number;
  source_ref?: string;
  facts?: ExpenseFacts;
  receipt_media_path?: string;
  receipt_folder?: ReceiptFolder;
};

type ExpenseBridgeRunner = (
  request: ExpenseBridgeRequest,
  signal?: AbortSignal,
) => Promise<Record<string, unknown>>;

const financeRoot = "/opt/openclaw/expense-sharepoint";
const financeVendorRoot = path.join(financeRoot, "vendor");
const bridgePath = path.join(financeRoot, "seer_finance", "agent_expense_bridge.py");
const PYTHON_INTERPRETER = "/usr/bin/python3";
const MAX_BRIDGE_OUTPUT_BYTES = 90 * 1024 * 1024;
const MAX_READ_PAGE_SIZE = 50;
const FACT_FIELD_MAP = {
  sourceTimestamp: "source_timestamp",
  observedTimestamp: "observed_timestamp",
  supplier: "supplier",
  amountPence: "amount_pence",
  currency: "currency",
  expenseDate: "expense_date",
  category: "category",
  evidenceRef: "evidence_ref",
  evidenceState: "evidence_state",
  settlementState: "settlement_state",
  financeLedgerRef: "finance_ledger_ref",
  validationResult: "validation_result",
} as const;
const STRING_FACT_FIELDS = new Set(
  Object.entries(FACT_FIELD_MAP)
    .filter(([key]) => key !== "amountPence")
    .map(([key]) => key),
);

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ToolInputError("Expense request must be an object");
  }
  return value as Record<string, unknown>;
}

function requiredString(params: Record<string, unknown>, name: string): string {
  const value = params[name];
  if (typeof value !== "string" || !value.trim()) {
    throw new ToolInputError(`${name} required`);
  }
  return value;
}

function prepareFacts(value: unknown): ExpenseFacts {
  const facts = asObject(value);
  const unknown = Object.keys(facts).filter((key) => !(key in FACT_FIELD_MAP));
  if (unknown.length) {
    throw new ToolInputError(`unsupported expense fact(s): ${unknown.join(", ")}`);
  }
  const result: Record<string, string | number> = {};
  for (const [inputName, outputName] of Object.entries(FACT_FIELD_MAP)) {
    const fact = facts[inputName];
    if (fact === undefined) continue;
    if (STRING_FACT_FIELDS.has(inputName)) {
      if (typeof fact !== "string" || !fact.trim()) {
        throw new ToolInputError(`${inputName} must be a non-empty string`);
      }
      if (inputName === "currency" && !/^[A-Z]{3}$/.test(fact)) {
        throw new ToolInputError("currency must be a three-letter uppercase ISO code");
      }
      result[outputName] = fact;
      continue;
    }
    if (typeof fact !== "number" || !Number.isSafeInteger(fact) || fact < 0) {
      throw new ToolInputError("amountPence must be a non-negative integer");
    }
    result[outputName] = fact;
  }
  return result as ExpenseFacts;
}

function optionalInteger(
  params: Record<string, unknown>,
  name: string,
  { minimum, maximum }: { minimum: number; maximum: number },
): number | undefined {
  const value = params[name];
  if (value === undefined) return undefined;
  if (
    typeof value !== "number" ||
    !Number.isSafeInteger(value) ||
    value < minimum ||
    value > maximum
  ) {
    throw new ToolInputError(`${name} must be an integer between ${minimum} and ${maximum}`);
  }
  return value;
}

function prepareRequest(rawParams: unknown): ExpenseBridgeRequest {
  const params = asObject(rawParams);
  const action = params.action;
  if (typeof action !== "string" || !EXPENSE_ACTIONS.includes(action as ExpenseAction)) {
    throw new ToolInputError(`action must be one of: ${EXPENSE_ACTIONS.join(", ")}`);
  }
  const expenseAction = action as ExpenseAction;
  if (expenseAction === "read_expense_workbook") {
    const page = optionalInteger(params, "page", { minimum: 0, maximum: 10_000 });
    const pageSize = optionalInteger(params, "pageSize", {
      minimum: 1,
      maximum: MAX_READ_PAGE_SIZE,
    });
    return {
      action: expenseAction,
      ...(page === undefined ? {} : { page }),
      ...(pageSize === undefined ? {} : { page_size: pageSize }),
    };
  }
  if (expenseAction === "capture_expense") {
    return {
      action: expenseAction,
      source_ref: requiredString(params, "sourceRef"),
      facts: prepareFacts(params.facts),
    };
  }
  return {
    action: expenseAction,
    source_ref: requiredString(params, "sourceRef"),
    receipt_media_path: requiredString(params, "receiptMediaPath"),
    receipt_folder: requiredReceiptFolder(params),
  };
}

function requiredReceiptFolder(params: Record<string, unknown>): ReceiptFolder {
  const value = requiredString(params, "receiptFolder");
  if (!RECEIPT_FOLDERS.includes(value as ReceiptFolder)) {
    throw new ToolInputError(`receiptFolder must be one of: ${RECEIPT_FOLDERS.join(", ")}`);
  }
  return value as ReceiptFolder;
}

type ExpenseBridgeRuntimePaths = {
  home: string;
  stateDir: string;
  queuePath: string;
  resultsPath: string;
  cacheRoot: string;
  queueLockPath: string;
  journalPath: string;
  mediaRoot: string;
};

export function resolveExpenseBridgeRuntimePaths(
  environment: NodeJS.ProcessEnv = process.env,
): ExpenseBridgeRuntimePaths {
  const serviceHome = path.resolve(os.homedir());
  const configuredHome = environment.HOME?.trim();
  if (configuredHome && path.resolve(configuredHome) !== serviceHome) {
    throw new Error("unsupported_state_layout: HOME must match the OpenClaw service account home");
  }
  const configuredOpenClawHome = environment.OPENCLAW_HOME?.trim();
  if (configuredOpenClawHome && path.resolve(configuredOpenClawHome) !== serviceHome) {
    throw new Error(
      "unsupported_state_layout: OPENCLAW_HOME must match the OpenClaw service account home",
    );
  }
  const stateDir = path.resolve(resolveStateDir(environment));
  const defaultStateDir = path.join(serviceHome, ".openclaw");
  if (stateDir !== defaultStateDir) {
    throw new Error(
      `unsupported_state_layout: expense_sharepoint supports only ${defaultStateDir}`,
    );
  }
  return {
    home: serviceHome,
    stateDir,
    queuePath: path.join(stateDir, "sharepoint-queue.json"),
    resultsPath: path.join(stateDir, "sharepoint-queue-results.json"),
    cacheRoot: path.join(stateDir, "workspace", "sharepoint-cache"),
    queueLockPath: path.join(stateDir, "integrations", "microsoft", "sp-queue.lock"),
    journalPath: path.join(stateDir, "seer-finance-mutation-journal.json"),
    mediaRoot: path.join(stateDir, "media", "inbound"),
  };
}

export function createExpenseBridgeEnvironment(
  environment: NodeJS.ProcessEnv = process.env,
): NodeJS.ProcessEnv {
  const paths = resolveExpenseBridgeRuntimePaths(environment);
  return {
    HOME: paths.home,
    OPENCLAW_STATE_DIR: paths.stateDir,
    SEER_FINANCE_SHAREPOINT_QUEUE: paths.queuePath,
    SEER_FINANCE_SHAREPOINT_RESULTS: paths.resultsPath,
    SEER_FINANCE_SHAREPOINT_CACHE: paths.cacheRoot,
    SEER_FINANCE_SHAREPOINT_QUEUE_LOCK: paths.queueLockPath,
    SEER_FINANCE_SHAREPOINT_MUTATION_JOURNAL: paths.journalPath,
    SEER_FINANCE_EXPENSE_MEDIA_ROOT: paths.mediaRoot,
    PYTHONPATH: [financeVendorRoot, financeRoot].join(path.delimiter),
    PYTHONNOUSERSITE: "1",
    LANG: "C.UTF-8",
    LC_ALL: "C.UTF-8",
  };
}

function blockedStateLayout(error: unknown): Record<string, unknown> | undefined {
  const message = error instanceof Error ? error.message : String(error);
  if (!message.startsWith("unsupported_state_layout:")) {
    return undefined;
  }
  return {
    ok: false,
    result: {
      operation: "expense_sharepoint",
      accepted: false,
      verified: false,
      complete: false,
      error_code: "unsupported_state_layout",
      blocker: message,
    },
  };
}

async function assertServiceOwned(pathname: string, kind: "file" | "directory"): Promise<void> {
  const entry = await lstat(pathname);
  const mode = (entry.mode & 0o7777).toString(8).padStart(4, "0");
  const details = `uid=${entry.uid}, gid=${entry.gid ?? "unknown"}, mode=${mode}, symlink=${entry.isSymbolicLink()}`;
  if ((kind === "file" && !entry.isFile()) || (kind === "directory" && !entry.isDirectory())) {
    throw new Error(`Expense bridge deployment has an invalid ${kind}: ${pathname} (${details})`);
  }
  if (entry.isSymbolicLink() || (entry.mode & 0o022) !== 0) {
    throw new Error(
      `Expense bridge deployment is not safely permissioned: ${pathname} (${details})`,
    );
  }
  if (typeof process.getuid === "function" && entry.uid !== process.getuid()) {
    throw new Error(
      `Expense bridge deployment is not owned by the OpenClaw service user: ${pathname} (${details})`,
    );
  }
}

async function assertServiceFileOrProtectedParent(pathname: string): Promise<void> {
  try {
    await assertServiceOwned(pathname, "file");
  } catch (error) {
    if (!(error && typeof error === "object" && "code" in error && error.code === "ENOENT")) {
      throw error;
    }
    await assertServiceOwned(path.dirname(pathname), "directory");
  }
}

async function assertRootProtected(pathname: string, kind: "file" | "directory"): Promise<void> {
  const entry = await lstat(pathname);
  if ((kind === "file" && !entry.isFile()) || (kind === "directory" && !entry.isDirectory())) {
    throw new Error(`Expense bridge protected deployment has an invalid ${kind}: ${pathname}`);
  }
  if (entry.isSymbolicLink() || entry.uid !== 0 || (entry.mode & 0o022) !== 0) {
    throw new Error(
      `Expense bridge protected deployment is not root-owned and read-only: ${pathname}`,
    );
  }
}

async function assertBridgeDeployment(environment: NodeJS.ProcessEnv): Promise<void> {
  const root = await realpath(financeRoot);
  if (root !== financeRoot) {
    throw new Error("Expense bridge deployment root must not be a symlink");
  }
  const paths: Array<[string, "file" | "directory"]> = [
    [path.dirname(root), "directory"],
    [root, "directory"],
    [financeVendorRoot, "directory"],
    [path.join(financeRoot, "seer_finance"), "directory"],
    [path.join(financeRoot, "seer_finance", "ledger"), "directory"],
    [bridgePath, "file"],
  ];
  for (const [pathname, kind] of paths) {
    await assertRootProtected(pathname, kind);
  }
  if ((await realpath(bridgePath)) !== bridgePath) {
    throw new Error("Expense bridge must not be a symlink");
  }
  const interpreter = await realpath(PYTHON_INTERPRETER);
  if (!interpreter.startsWith("/usr/bin/")) {
    throw new Error("Expense bridge interpreter must resolve within /usr/bin");
  }
  const interpreterStat = await lstat(interpreter);
  if (
    !interpreterStat.isFile() ||
    interpreterStat.uid !== 0 ||
    (interpreterStat.mode & 0o022) !== 0
  ) {
    throw new Error("Expense bridge interpreter is not a root-owned protected system binary");
  }
  const runtime = resolveExpenseBridgeRuntimePaths(environment);
  for (const pathname of [runtime.home, runtime.stateDir, runtime.cacheRoot, runtime.mediaRoot]) {
    await assertServiceOwned(pathname, "directory");
  }
  // The queue is the one mutable transport file this tool may indirectly use;
  // it must be a protected service-owned regular file before a child starts.
  await assertServiceOwned(runtime.queuePath, "file");
  await assertServiceFileOrProtectedParent(runtime.resultsPath);
  await assertServiceFileOrProtectedParent(runtime.queueLockPath);
  await assertServiceFileOrProtectedParent(runtime.journalPath);
}

export async function runExpenseBridge(
  request: ExpenseBridgeRequest,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  let environment: NodeJS.ProcessEnv;
  try {
    environment = createExpenseBridgeEnvironment();
  } catch (error) {
    const blocked = blockedStateLayout(error);
    if (blocked) return blocked;
    throw error;
  }
  await assertBridgeDeployment(environment);
  const child = spawn(PYTHON_INTERPRETER, [bridgePath], {
    cwd: financeRoot,
    stdio: ["pipe", "pipe", "pipe"],
    // Do not pass the gateway process environment (including its secrets or
    // PATH) to a local child. The fixed bridge's documented defaults locate
    // its state under the deployment service account.
    env: environment,
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
  signal?.addEventListener("abort", abort, { once: true });
  child.stdin.end(JSON.stringify(request));
  const [code] = (await once(child, "close")) as [number | null];
  signal?.removeEventListener("abort", abort);
  if (code !== 0) {
    throw new Error(
      `Expense bridge failed (${code ?? "terminated"}): ${stderr.trim().slice(0, 500)}`,
    );
  }
  try {
    return JSON.parse(stdout) as Record<string, unknown>;
  } catch {
    throw new Error("Expense bridge returned malformed JSON");
  }
}

export function createExpenseSharePointTool(
  options: {
    run?: ExpenseBridgeRunner;
    workspaceDir?: string;
  } = {},
): AnyAgentTool {
  const run = options.run ?? runExpenseBridge;
  return {
    name: "expense_sharepoint",
    label: "Expense SharePoint Ledger",
    description:
      "Owner-only, no-TOTP expense route. It only reads or source-linked captures into the canonical /Expenses/Expense ledger.xlsx contract and uploads inbound receipt media to a content-addressed name in one approved existing /Expenses category folder. It cannot send messages, run commands, access arbitrary files, or choose SharePoint destinations. A queued operation is not complete until verified readback is returned.",
    ownerOnly: true,
    parameters: Type.Object(
      {
        action: Type.Union(EXPENSE_ACTIONS.map((value) => Type.Literal(value))),
        page: Type.Optional(Type.Integer({ minimum: 0, maximum: 10_000 })),
        pageSize: Type.Optional(Type.Integer({ minimum: 1, maximum: MAX_READ_PAGE_SIZE })),
        sourceRef: Type.Optional(Type.String()),
        facts: Type.Optional(
          Type.Object(
            {
              sourceTimestamp: Type.Optional(Type.String()),
              observedTimestamp: Type.Optional(Type.String()),
              supplier: Type.Optional(Type.String()),
              amountPence: Type.Optional(Type.Integer({ minimum: 0 })),
              currency: Type.Optional(Type.String({ pattern: "^[A-Z]{3}$" })),
              expenseDate: Type.Optional(Type.String()),
              category: Type.Optional(Type.String()),
              evidenceRef: Type.Optional(Type.String()),
              evidenceState: Type.Optional(Type.String()),
              settlementState: Type.Optional(Type.String()),
              financeLedgerRef: Type.Optional(Type.String()),
              validationResult: Type.Optional(Type.String()),
            },
            { additionalProperties: false },
          ),
        ),
        receiptMediaPath: Type.Optional(Type.String()),
        receiptFolder: Type.Optional(
          Type.Union(RECEIPT_FOLDERS.map((value) => Type.Literal(value))),
        ),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, rawParams, signal) {
      const response = await run(prepareRequest(rawParams), signal);
      return jsonResult(response);
    },
  };
}
