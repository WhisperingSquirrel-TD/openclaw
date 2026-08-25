import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

const STATE_VERSION = 1;
const DEFAULT_MAX_TURNS = 6;
const MAX_TURNS = 20;
const DEFAULT_MAX_WALL_CLOCK_SECONDS = 10 * 60;
const MAX_WALL_CLOCK_SECONDS = 30 * 60;
const MAX_CHECKPOINT_CHARS = 1_500;
const MAX_OBJECTIVE_CHARS = 2_000;

export type ContinuationStatus =
  | "active"
  | "completed"
  | "blocked"
  | "cancelled"
  | "limit_reached"
  | "expired";

export type ContinuationState = {
  version: number;
  sessionId: string;
  sessionKey?: string;
  objective: string;
  checkpoint?: string;
  status: ContinuationStatus;
  turnsCompleted: number;
  maxTurns: number;
  startedAt: number;
  deadlineAt: number;
  updatedAt: number;
  terminalReason?: string;
};

export type ContinuationAdvance =
  | { action: "none" }
  | { action: "continue"; state: ContinuationState; prompt: string }
  | { action: "terminal"; state: ContinuationState; notice: string };

function clampInteger(
  value: number | undefined,
  fallback: number,
  min: number,
  max: number,
): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.max(min, Math.min(max, Math.floor(value)));
}

function cleanText(value: string, maxChars: number): string {
  return value.split(String.fromCharCode(0)).join("").trim().slice(0, maxChars);
}

function stateDirectory(agentDir: string): string {
  return path.join(agentDir, "continuations");
}

function statePath(agentDir: string, sessionId: string): string {
  const stableId = createHash("sha256").update(sessionId).digest("hex");
  return path.join(stateDirectory(agentDir), `${stableId}.json`);
}

function isContinuationState(value: unknown): value is ContinuationState {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const state = value as Partial<ContinuationState>;
  return (
    state.version === STATE_VERSION &&
    typeof state.sessionId === "string" &&
    typeof state.objective === "string" &&
    typeof state.status === "string" &&
    typeof state.turnsCompleted === "number" &&
    typeof state.maxTurns === "number" &&
    typeof state.startedAt === "number" &&
    typeof state.deadlineAt === "number" &&
    typeof state.updatedAt === "number"
  );
}

async function writeState(
  agentDir: string,
  state: ContinuationState,
): Promise<void> {
  const directory = stateDirectory(agentDir);
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const target = statePath(agentDir, state.sessionId);
  const temporary = `${target}.tmp-${process.pid}`;
  await fs.writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, {
    mode: 0o600,
  });
  await fs.rename(temporary, target);
}

export async function readContinuationState(params: {
  agentDir: string;
  sessionId: string;
}): Promise<ContinuationState | undefined> {
  try {
    const parsed = JSON.parse(
      await fs.readFile(statePath(params.agentDir, params.sessionId), "utf8"),
    );
    return isContinuationState(parsed) ? parsed : undefined;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return undefined;
    }
    throw new Error(
      "Continuation state is unreadable; refusing to continue automatically.",
      {
        cause: error,
      },
    );
  }
}

export async function startContinuation(params: {
  agentDir: string;
  sessionId: string;
  sessionKey?: string;
  objective: string;
  checkpoint?: string;
  maxTurns?: number;
  maxWallClockSeconds?: number;
  now?: number;
}): Promise<ContinuationState> {
  const objective = cleanText(params.objective, MAX_OBJECTIVE_CHARS);
  if (!objective) {
    throw new Error("objective is required to start a continuation.");
  }
  const now = params.now ?? Date.now();
  const state: ContinuationState = {
    version: STATE_VERSION,
    sessionId: params.sessionId,
    sessionKey: params.sessionKey,
    objective,
    checkpoint: params.checkpoint
      ? cleanText(params.checkpoint, MAX_CHECKPOINT_CHARS)
      : undefined,
    status: "active",
    turnsCompleted: 0,
    maxTurns: clampInteger(params.maxTurns, DEFAULT_MAX_TURNS, 1, MAX_TURNS),
    startedAt: now,
    deadlineAt:
      now +
      clampInteger(
        params.maxWallClockSeconds,
        DEFAULT_MAX_WALL_CLOCK_SECONDS,
        30,
        MAX_WALL_CLOCK_SECONDS,
      ) *
        1_000,
    updatedAt: now,
  };
  await writeState(params.agentDir, state);
  return state;
}

export async function checkpointContinuation(params: {
  agentDir: string;
  sessionId: string;
  checkpoint: string;
  now?: number;
}): Promise<ContinuationState> {
  const state = await readContinuationState(params);
  if (!state) {
    throw new Error("No continuation is active for this session.");
  }
  if (state.status !== "active") {
    throw new Error(
      `Continuation is ${state.status}; start a new continuation instead.`,
    );
  }
  const checkpoint = cleanText(params.checkpoint, MAX_CHECKPOINT_CHARS);
  if (!checkpoint) {
    throw new Error("checkpoint is required.");
  }
  state.checkpoint = checkpoint;
  state.updatedAt = params.now ?? Date.now();
  await writeState(params.agentDir, state);
  return state;
}

export async function finishContinuation(params: {
  agentDir: string;
  sessionId: string;
  status: Extract<ContinuationStatus, "completed" | "blocked" | "cancelled">;
  reason?: string;
  now?: number;
}): Promise<ContinuationState> {
  const state = await readContinuationState(params);
  if (!state) {
    throw new Error("No continuation exists for this session.");
  }
  state.status = params.status;
  state.terminalReason = params.reason
    ? cleanText(params.reason, MAX_CHECKPOINT_CHARS)
    : undefined;
  state.updatedAt = params.now ?? Date.now();
  await writeState(params.agentDir, state);
  return state;
}

export async function resumeContinuation(params: {
  agentDir: string;
  sessionId: string;
  maxTurns?: number;
  maxWallClockSeconds?: number;
  now?: number;
}): Promise<ContinuationState> {
  const state = await readContinuationState(params);
  if (!state) {
    throw new Error(
      "No continuation exists for this session; start one instead.",
    );
  }
  if (state.status === "active") {
    throw new Error("Continuation is already active.");
  }
  const now = params.now ?? Date.now();
  state.status = "active";
  state.terminalReason = undefined;
  state.turnsCompleted = 0;
  state.maxTurns = clampInteger(params.maxTurns, state.maxTurns, 1, MAX_TURNS);
  state.deadlineAt =
    now +
    clampInteger(
      params.maxWallClockSeconds,
      DEFAULT_MAX_WALL_CLOCK_SECONDS,
      30,
      MAX_WALL_CLOCK_SECONDS,
    ) *
      1_000;
  state.updatedAt = now;
  await writeState(params.agentDir, state);
  return state;
}

function buildContinuationPrompt(state: ContinuationState): string {
  const checkpoint = state.checkpoint
    ? `Latest compact checkpoint: ${state.checkpoint}`
    : "No checkpoint has been recorded yet.";
  return [
    "[Continuation turn]",
    `Objective: ${state.objective}`,
    checkpoint,
    "Complete exactly one meaningful next step. Use subagents only for isolated work; give them a compact task and use their returned summary rather than copying this transcript.",
    "Do not ask the owner to send “Next?”. Before your final response, call agent_loop with action=checkpoint and a concise factual checkpoint. Call action=complete when the objective is done, or action=block when human input, approval, or a policy boundary is required.",
    "Do not start another continuation from this continuation turn.",
  ].join("\n");
}

function terminalNotice(state: ContinuationState): string {
  if (state.status === "expired") {
    return "Continuation paused: its wall-clock deadline was reached. Ask to resume when ready.";
  }
  return `Continuation paused: it reached the ${state.maxTurns}-turn safety limit. Ask to resume with a new bounded continuation.`;
}

export async function prepareContinuationAdvance(params: {
  agentDir: string;
  sessionId: string;
  now?: number;
}): Promise<ContinuationAdvance> {
  const state = await readContinuationState(params);
  if (!state || state.status !== "active") {
    return { action: "none" };
  }
  const now = params.now ?? Date.now();
  if (now >= state.deadlineAt) {
    state.status = "expired";
    state.terminalReason = "wall-clock deadline reached";
    state.updatedAt = now;
    await writeState(params.agentDir, state);
    return { action: "terminal", state, notice: terminalNotice(state) };
  }
  if (state.turnsCompleted >= state.maxTurns) {
    state.status = "limit_reached";
    state.terminalReason = "turn limit reached";
    state.updatedAt = now;
    await writeState(params.agentDir, state);
    return { action: "terminal", state, notice: terminalNotice(state) };
  }
  state.turnsCompleted += 1;
  state.updatedAt = now;
  await writeState(params.agentDir, state);
  return { action: "continue", state, prompt: buildContinuationPrompt(state) };
}
