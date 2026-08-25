import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

const STATE_VERSION = 2;
const DEFAULT_MAX_TURNS = 6;
const MAX_TURNS = 20;
const DEFAULT_MAX_WALL_CLOCK_SECONDS = 10 * 60;
const MAX_WALL_CLOCK_SECONDS = 30 * 60;
const MAX_CHECKPOINT_CHARS = 1_500;
const MAX_OBJECTIVE_CHARS = 2_000;
const DEFAULT_LEASE_MS = 2 * 60 * 1_000;
const LOCK_RETRY_MS = 10;
const LOCK_TIMEOUT_MS = 5_000;
const STALE_LOCK_MS = 2 * 60 * 1_000;

export type ContinuationStatus =
  | "active"
  | "completed"
  | "blocked"
  | "cancelled"
  | "limit_reached"
  | "expired";

export type ContinuationWorkStatus = "pending" | "running";

export type ContinuationLease = {
  id: string;
  acquiredAt: number;
  expiresAt: number;
};

export type ContinuationWork = {
  idempotencyKey: string;
  prompt: string;
  generation: number;
  turn: number;
  status: ContinuationWorkStatus;
  enqueuedAt: number;
  queueKey?: string;
  /**
   * The fully resolved FollowupRun is JSON-safe configuration and routing
   * metadata. Keeping it alongside the work item lets a later process
   * reconcile a crash between state persistence and queue insertion.
   */
  queuedRun?: unknown;
  lease?: ContinuationLease;
  recoveredAt?: number;
};

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
  /** Monotonic restart generation. A stale worker can never cross it. */
  generation: number;
  /** Monotonic compare-and-set revision for every durable transition. */
  revision: number;
  work?: ContinuationWork;
};

export type ContinuationAdvance =
  | { action: "none"; state?: ContinuationState }
  | {
      action: "continue";
      state: ContinuationState;
      prompt: string;
      idempotencyKey: string;
      recovered?: boolean;
    }
  | { action: "terminal"; state: ContinuationState; notice: string };

export type ContinuationWorkClaim =
  | { claimed: false; state?: ContinuationState; reason: string }
  | { claimed: true; state: ContinuationState; lease: ContinuationLease };

export type RecoverableContinuationWork = {
  state: ContinuationState;
  work: ContinuationWork;
};

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

function workId(sessionId: string, generation: number, turn: number): string {
  return createHash("sha256")
    .update(JSON.stringify(["continuation", sessionId, generation, turn]))
    .digest("hex");
}

function isStatus(value: unknown): value is ContinuationStatus {
  return (
    value === "active" ||
    value === "completed" ||
    value === "blocked" ||
    value === "cancelled" ||
    value === "limit_reached" ||
    value === "expired"
  );
}

function normalizeState(value: unknown): ContinuationState | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  const state = value as Partial<ContinuationState>;
  if (
    (state.version !== 1 && state.version !== STATE_VERSION) ||
    typeof state.sessionId !== "string" ||
    typeof state.objective !== "string" ||
    !isStatus(state.status) ||
    typeof state.turnsCompleted !== "number" ||
    typeof state.maxTurns !== "number" ||
    typeof state.startedAt !== "number" ||
    typeof state.deadlineAt !== "number" ||
    typeof state.updatedAt !== "number"
  ) {
    return undefined;
  }
  const work =
    state.work &&
    typeof state.work === "object" &&
    typeof state.work.idempotencyKey === "string" &&
    typeof state.work.prompt === "string" &&
    typeof state.work.generation === "number" &&
    typeof state.work.turn === "number" &&
    (state.work.status === "pending" || state.work.status === "running") &&
    typeof state.work.enqueuedAt === "number"
      ? state.work
      : undefined;
  return {
    ...state,
    version: STATE_VERSION,
    generation:
      typeof state.generation === "number" && state.generation > 0
        ? Math.floor(state.generation)
        : 1,
    revision:
      typeof state.revision === "number" && state.revision >= 0
        ? Math.floor(state.revision)
        : 0,
    ...(work ? { work } : {}),
  } as ContinuationState;
}

async function readStateAt(target: string): Promise<ContinuationState | undefined> {
  try {
    const parsed = JSON.parse(await fs.readFile(target, "utf8"));
    return normalizeState(parsed);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return undefined;
    }
    throw new Error("Continuation state is unreadable; refusing to continue automatically.", {
      cause: error,
    });
  }
}

async function writeStateAt(target: string, state: ContinuationState): Promise<void> {
  await fs.mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
  const temporary = `${target}.tmp-${process.pid}-${randomUUID()}`;
  await fs.writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, {
    mode: 0o600,
  });
  await fs.rename(temporary, target);
}

async function withStateLock<T>(target: string, fn: () => Promise<T>): Promise<T> {
  const lockPath = `${target}.lock`;
  await fs.mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
  const startedAt = Date.now();
  while (true) {
    try {
      await fs.mkdir(lockPath, { mode: 0o700 });
      break;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") {
        throw error;
      }
      try {
        const stat = await fs.stat(lockPath);
        if (Date.now() - stat.mtimeMs > STALE_LOCK_MS) {
          await fs.rm(lockPath, { recursive: true, force: true });
          continue;
        }
      } catch {
        continue;
      }
      if (Date.now() - startedAt >= LOCK_TIMEOUT_MS) {
        throw new Error("Continuation state is busy; retry the owner command.", {
          cause: error,
        });
      }
      await new Promise((resolve) => setTimeout(resolve, LOCK_RETRY_MS));
    }
  }
  try {
    return await fn();
  } finally {
    await fs.rm(lockPath, { recursive: true, force: true });
  }
}

async function mutateState<T>(
  params: { agentDir: string; sessionId: string },
  fn: (state: ContinuationState | undefined) => Promise<{ state?: ContinuationState; value: T }>,
): Promise<T> {
  const target = statePath(params.agentDir, params.sessionId);
  return await withStateLock(target, async () => {
    const current = await readStateAt(target);
    const next = await fn(current);
    if (next.state) {
      await writeStateAt(target, next.state);
    }
    return next.value;
  });
}

function touch(state: ContinuationState, now: number): ContinuationState {
  state.revision += 1;
  state.updatedAt = now;
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

function terminalize(
  state: ContinuationState,
  status: Extract<ContinuationStatus, "expired" | "limit_reached">,
  reason: string,
  now: number,
): ContinuationState {
  state.status = status;
  state.terminalReason = reason;
  state.work = undefined;
  return touch(state, now);
}

export async function readContinuationState(params: {
  agentDir: string;
  sessionId: string;
}): Promise<ContinuationState | undefined> {
  return await readStateAt(statePath(params.agentDir, params.sessionId));
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
  return await mutateState(params, async (existing) => {
    if (existing?.status === "active") {
      throw new Error("Continuation is already active; checkpoint, complete, or cancel it first.");
    }
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
      generation: (existing?.generation ?? 0) + 1,
      revision: (existing?.revision ?? -1) + 1,
    };
    return { state, value: state };
  });
}

export async function checkpointContinuation(params: {
  agentDir: string;
  sessionId: string;
  checkpoint: string;
  now?: number;
}): Promise<ContinuationState> {
  const checkpoint = cleanText(params.checkpoint, MAX_CHECKPOINT_CHARS);
  if (!checkpoint) {
    throw new Error("checkpoint is required.");
  }
  const now = params.now ?? Date.now();
  return await mutateState(params, async (state) => {
    if (!state) {
      throw new Error("No continuation is active for this session.");
    }
    if (state.status !== "active") {
      throw new Error(`Continuation is ${state.status}; start a new continuation instead.`);
    }
    state.checkpoint = checkpoint;
    // A checkpoint is the completion signal for the current continuation turn.
    // A persisted queue envelope is always attached before real work is
    // dispatched; this branch also preserves the public state API for callers
    // that advance/checkpoint without a queue runner.
    if (state.work?.status === "pending" && !state.work.queuedRun) {
      state.work = undefined;
    }
    touch(state, now);
    return { state, value: state };
  });
}

export async function finishContinuation(params: {
  agentDir: string;
  sessionId: string;
  status: Extract<ContinuationStatus, "completed" | "blocked" | "cancelled">;
  reason?: string;
  now?: number;
}): Promise<ContinuationState> {
  const now = params.now ?? Date.now();
  return await mutateState(params, async (state) => {
    if (!state) {
      throw new Error("No continuation exists for this session.");
    }
    if (state.status !== "active") {
      if (state.status === params.status) {
        return { value: state };
      }
      throw new Error(
        `Continuation is already ${state.status}; refusing to overwrite its terminal state.`,
      );
    }
    state.status = params.status;
    state.terminalReason = params.reason
      ? cleanText(params.reason, MAX_CHECKPOINT_CHARS)
      : undefined;
    state.work = undefined;
    touch(state, now);
    return { state, value: state };
  });
}

/** Terminalizes an active continuation even when no in-memory queue item remains. */
export async function cancelContinuationForSession(params: {
  agentDir: string;
  sessionId: string | undefined;
  reason: string;
}): Promise<boolean> {
  const sessionId = params.sessionId?.trim();
  if (!sessionId) {
    return false;
  }
  const state = await readContinuationState({ agentDir: params.agentDir, sessionId });
  if (!state || state.status !== "active") {
    return false;
  }
  await finishContinuation({
    agentDir: params.agentDir,
    sessionId,
    status: "cancelled",
    reason: params.reason,
  });
  return true;
}

export async function resumeContinuation(params: {
  agentDir: string;
  sessionId: string;
  maxTurns?: number;
  maxWallClockSeconds?: number;
  now?: number;
}): Promise<ContinuationState> {
  const now = params.now ?? Date.now();
  return await mutateState(params, async (state) => {
    if (!state) {
      throw new Error("No continuation exists for this session; start one instead.");
    }
    if (state.status === "active") {
      throw new Error("Continuation is already active.");
    }
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
    state.generation += 1;
    state.work = undefined;
    touch(state, now);
    return { state, value: state };
  });
}

export async function prepareContinuationAdvance(params: {
  agentDir: string;
  sessionId: string;
  now?: number;
  /**
   * When supplied by the scheduler, the next queue envelope is written in the
   * same locked transition as the work record. This prevents a crash from
   * leaving an otherwise active continuation without recoverable routing.
   */
  queueKey?: string;
  queuedRunFactory?: (advance: {
    state: ContinuationState;
    prompt: string;
    idempotencyKey: string;
  }) => unknown;
  completedWork?: { idempotencyKey: string; leaseId: string };
}): Promise<ContinuationAdvance> {
  const now = params.now ?? Date.now();
  return await mutateState<ContinuationAdvance>(params, async (state) => {
    if (!state || state.status !== "active") {
      return { value: { action: "none" } };
    }
    if (params.completedWork) {
      if (
        !state.work ||
        state.work.idempotencyKey !== params.completedWork.idempotencyKey ||
        state.work.lease?.id !== params.completedWork.leaseId
      ) {
        return { value: { action: "none", state } };
      }
      state.work = undefined;
    }
    if (now >= state.deadlineAt) {
      terminalize(state, "expired", "wall-clock deadline reached", now);
      return { state, value: { action: "terminal", state, notice: terminalNotice(state) } };
    }
    if (
      state.work?.status === "pending" &&
      !state.work.queuedRun &&
      state.turnsCompleted >= state.maxTurns
    ) {
      terminalize(state, "limit_reached", "turn limit reached", now);
      return { state, value: { action: "terminal", state, notice: terminalNotice(state) } };
    }
    if (state.work) {
      if (
        state.work.status === "running" &&
        (state.work.lease?.expiresAt ?? 0) > now
      ) {
        return { value: { action: "none", state } };
      }
      const recovered = state.work.status === "running";
      state.work.status = "pending";
      state.work.lease = undefined;
      state.work.recoveredAt = recovered ? now : state.work.recoveredAt;
      if (recovered) {
        touch(state, now);
      }
      const value: ContinuationAdvance = {
        action: "continue",
        state,
        prompt: state.work.prompt,
        idempotencyKey: state.work.idempotencyKey,
        ...(recovered ? { recovered: true } : {}),
      };
      if (params.queueKey && params.queuedRunFactory && !state.work.queuedRun) {
        state.work.queueKey = params.queueKey;
        state.work.queuedRun = params.queuedRunFactory(value);
        touch(state, now);
      }
      return {
        state: recovered || Boolean(params.queueKey && params.queuedRunFactory) ? state : undefined,
        value,
      };
    }
    if (state.turnsCompleted >= state.maxTurns) {
      terminalize(state, "limit_reached", "turn limit reached", now);
      return { state, value: { action: "terminal", state, notice: terminalNotice(state) } };
    }
    const turn = state.turnsCompleted + 1;
    const prompt = buildContinuationPrompt(state);
    state.turnsCompleted = turn;
    state.work = {
      idempotencyKey: workId(state.sessionId, state.generation, turn),
      prompt,
      generation: state.generation,
      turn,
      status: "pending",
      enqueuedAt: now,
    };
    touch(state, now);
    const value: ContinuationAdvance = {
      action: "continue",
      state,
      prompt,
      idempotencyKey: state.work.idempotencyKey,
    };
    if (params.queueKey && params.queuedRunFactory) {
      state.work.queueKey = params.queueKey;
      state.work.queuedRun = params.queuedRunFactory(value);
    }
    return { state, value };
  });
}

export async function persistContinuationQueuedRun(params: {
  agentDir: string;
  sessionId: string;
  idempotencyKey: string;
  queueKey: string;
  queuedRun: unknown;
  now?: number;
}): Promise<ContinuationState> {
  const now = params.now ?? Date.now();
  return await mutateState(params, async (state) => {
    if (
      !state ||
      state.status !== "active" ||
      !state.work ||
      state.work.idempotencyKey !== params.idempotencyKey ||
      state.work.status !== "pending"
    ) {
      throw new Error("Continuation work is no longer pending; refusing to queue stale work.");
    }
    state.work.queueKey = params.queueKey;
    state.work.queuedRun = params.queuedRun;
    touch(state, now);
    return { state, value: state };
  });
}

export async function claimContinuationWork(params: {
  agentDir: string;
  sessionId: string;
  idempotencyKey: string;
  leaseMs?: number;
  now?: number;
}): Promise<ContinuationWorkClaim> {
  const now = params.now ?? Date.now();
  return await mutateState<ContinuationWorkClaim>(params, async (state) => {
    if (!state || state.status !== "active" || !state.work) {
      return { value: { claimed: false, state, reason: "continuation is not active" } };
    }
    if (state.work.idempotencyKey !== params.idempotencyKey) {
      return { value: { claimed: false, state, reason: "stale continuation work" } };
    }
    if (now >= state.deadlineAt) {
      terminalize(state, "expired", "wall-clock deadline reached", now);
      return {
        state,
        value: { claimed: false, state, reason: "continuation deadline reached" },
      };
    }
    if (
      state.work.status === "running" &&
      (state.work.lease?.expiresAt ?? 0) > now
    ) {
      return { value: { claimed: false, state, reason: "continuation work is leased" } };
    }
    const lease: ContinuationLease = {
      id: randomUUID(),
      acquiredAt: now,
      expiresAt: Math.min(
        state.deadlineAt,
        now + Math.max(1_000, params.leaseMs ?? DEFAULT_LEASE_MS),
      ),
    };
    state.work.status = "running";
    state.work.lease = lease;
    touch(state, now);
    return { state, value: { claimed: true, state, lease } };
  });
}

export async function completeContinuationWork(params: {
  agentDir: string;
  sessionId: string;
  idempotencyKey: string;
  leaseId: string;
  now?: number;
}): Promise<ContinuationState | undefined> {
  const now = params.now ?? Date.now();
  return await mutateState(params, async (state) => {
    if (
      !state ||
      state.status !== "active" ||
      !state.work ||
      state.work.idempotencyKey !== params.idempotencyKey ||
      state.work.lease?.id !== params.leaseId
    ) {
      return { value: undefined };
    }
    state.work = undefined;
    touch(state, now);
    return { state, value: state };
  });
}

export async function failContinuationWork(params: {
  agentDir: string;
  sessionId: string;
  idempotencyKey: string;
  leaseId: string;
  reason: string;
  now?: number;
}): Promise<ContinuationState | undefined> {
  const now = params.now ?? Date.now();
  return await mutateState(params, async (state) => {
    if (
      !state ||
      state.status !== "active" ||
      !state.work ||
      state.work.idempotencyKey !== params.idempotencyKey ||
      state.work.lease?.id !== params.leaseId
    ) {
      return { value: undefined };
    }
    state.status = "blocked";
    state.terminalReason = cleanText(params.reason, MAX_CHECKPOINT_CHARS);
    state.work = undefined;
    touch(state, now);
    return { state, value: state };
  });
}

export async function recoverContinuationWork(params: {
  agentDir: string;
  now?: number;
}): Promise<RecoverableContinuationWork[]> {
  const now = params.now ?? Date.now();
  let files: string[];
  try {
    files = (await fs.readdir(stateDirectory(params.agentDir)))
      .filter((entry) => entry.endsWith(".json"))
      .map((entry) => path.join(stateDirectory(params.agentDir), entry));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }
    throw error;
  }
  const recovered: RecoverableContinuationWork[] = [];
  for (const target of files) {
    await withStateLock(target, async () => {
      const state = await readStateAt(target);
      if (!state || state.status !== "active" || !state.work) {
        return;
      }
      if (now >= state.deadlineAt) {
        terminalize(state, "expired", "wall-clock deadline reached", now);
        await writeStateAt(target, state);
        return;
      }
      if (
        state.work.status === "running" &&
        (state.work.lease?.expiresAt ?? 0) > now
      ) {
        return;
      }
      if (state.work.status === "running") {
        state.work.status = "pending";
        state.work.lease = undefined;
        state.work.recoveredAt = now;
        touch(state, now);
        await writeStateAt(target, state);
      }
      if (state.work.queuedRun && state.work.queueKey) {
        recovered.push({ state, work: state.work });
      }
    });
  }
  return recovered;
}

/**
 * Returns the earliest still-valid running lease. Startup recovery leaves
 * these alone until their owner can no longer be alive, then retries the scan.
 */
export async function nextContinuationRecoveryAt(params: {
  agentDir: string;
  now?: number;
}): Promise<number | undefined> {
  const now = params.now ?? Date.now();
  let entries: string[];
  try {
    entries = await fs.readdir(stateDirectory(params.agentDir));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return undefined;
    }
    throw error;
  }
  let next: number | undefined;
  for (const entry of entries) {
    if (!entry.endsWith(".json")) {
      continue;
    }
    const state = await readStateAt(path.join(stateDirectory(params.agentDir), entry));
    const expiresAt = state?.work?.status === "running" ? state.work.lease?.expiresAt : undefined;
    if (expiresAt != null && expiresAt > now && (next == null || expiresAt < next)) {
      next = expiresAt;
    }
  }
  return next;
}