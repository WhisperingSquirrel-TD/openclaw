import { chmod, mkdir, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { SKILZVOLT_USER_COUNT_ACK_URL, SKILZVOLT_USER_COUNT_URL } from "./config.js";
import { createSkilzVoltAccessTokenGetter } from "./connection.js";

const DEFAULT_CONNECTION_KEY_ENV = "SKILZVOLT_CONNECTION_KEY";
const DEFAULT_STATE_PATH = path.join(
  process.env.OPENCLAW_STATE_DIR || path.join(process.env.HOME || ".", ".openclaw"),
  "integrations",
  "skilzvolt",
  "user-count-state.json",
);
const REQUEST_TIMEOUT_MS = 20_000;
const MAX_RESPONSE_BYTES = 32_768;
const EXPECTED_RESPONSE_KEYS = new Set(["since_last", "total", "delivery_ref"]);

export type SkilzVoltUserCountState = {
  total: number;
  sinceLast: number;
  acknowledgementSucceeded: boolean;
  checkedAt: string;
  checkedAtEuropeLondon: string;
};

export type SkilzVoltUserCountFailureKind =
  | "not_connected"
  | "auth"
  | "permission"
  | "network"
  | "timeout"
  | "protocol"
  | "record"
  | "ack";

export type SkilzVoltUserCountResult =
  | ({
      ok: true;
      acknowledgementSucceeded: true;
    } & SkilzVoltUserCountState)
  | {
      ok: false;
      kind: SkilzVoltUserCountFailureKind;
      message: string;
      acknowledgementSucceeded: boolean;
      recorded?: boolean;
      total?: number;
      sinceLast?: number;
      checkedAt?: string;
      checkedAtEuropeLondon?: string;
    };

type FetchLike = typeof fetch;
type StateWriter = (state: SkilzVoltUserCountState) => Promise<void>;

function formatLondonTime(date: Date): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "long",
    timeZone: "Europe/London",
  }).format(date);
}

function failure(
  kind: SkilzVoltUserCountFailureKind,
  message: string,
  state?: Partial<SkilzVoltUserCountState> & { recorded?: boolean },
): SkilzVoltUserCountResult {
  return {
    ok: false,
    kind,
    message,
    acknowledgementSucceeded: state?.acknowledgementSucceeded === true,
    ...(state?.recorded === undefined ? {} : { recorded: state.recorded }),
    ...(state?.total === undefined ? {} : { total: state.total }),
    ...(state?.sinceLast === undefined ? {} : { sinceLast: state.sinceLast }),
    ...(state?.checkedAt === undefined ? {} : { checkedAt: state.checkedAt }),
    ...(state?.checkedAtEuropeLondon === undefined
      ? {}
      : { checkedAtEuropeLondon: state.checkedAtEuropeLondon }),
  };
}

async function readBoundedBody(response: Response): Promise<string> {
  if (!response.body) {
    const text = await response.text();
    if (new TextEncoder().encode(text).byteLength > MAX_RESPONSE_BYTES) {
      throw new Error("response exceeded the safety limit");
    }
    return text;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let size = 0;
  let text = "";
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) {
      break;
    }
    size += chunk.value.byteLength;
    if (size > MAX_RESPONSE_BYTES) {
      await reader.cancel();
      throw new Error("response exceeded the safety limit");
    }
    text += decoder.decode(chunk.value, { stream: true });
  }
  return text + decoder.decode();
}

function assertCountPayload(value: unknown): {
  total: number;
  sinceLast: number;
  deliveryRef: string;
} {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("count endpoint returned a non-object response");
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record);
  if (
    keys.length !== EXPECTED_RESPONSE_KEYS.size ||
    keys.some((key) => !EXPECTED_RESPONSE_KEYS.has(key))
  ) {
    throw new Error("count endpoint returned an unexpected response shape");
  }
  if (
    !Number.isSafeInteger(record.total) ||
    (record.total as number) < 0 ||
    !Number.isSafeInteger(record.since_last) ||
    (record.since_last as number) < 0 ||
    typeof record.delivery_ref !== "string" ||
    record.delivery_ref.trim().length === 0
  ) {
    throw new Error("count endpoint returned invalid aggregate values");
  }
  return {
    total: record.total as number,
    sinceLast: record.since_last as number,
    deliveryRef: record.delivery_ref,
  };
}

async function request(
  fetchImpl: FetchLike,
  url: string,
  token: string,
  init: RequestInit,
  timeoutMs: number,
  readBody: boolean,
): Promise<{ response: Response; body?: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    let response: Response;
    try {
      const requestHeaders = Object.fromEntries(new Headers(init.headers).entries());
      response = await fetchImpl(url, {
        ...init,
        headers: {
          ...requestHeaders,
          accept: "application/json",
          authorization: `Bearer ${token}`,
        },
        signal: controller.signal,
      });
    } catch (error) {
      if (controller.signal.aborted) {
        throw Object.assign(new Error("SkilzVolt user-count request timed out"), {
          kind: "timeout" as const,
        });
      }
      throw Object.assign(new Error("SkilzVolt user-count request failed"), {
        kind: "network" as const,
        cause: error,
      });
    }
    if (!readBody || !response.ok) {
      return { response };
    }
    try {
      return { response, body: await readBoundedBody(response) };
    } catch (error) {
      if (controller.signal.aborted) {
        throw Object.assign(new Error("SkilzVolt user-count response timed out"), {
          kind: "timeout" as const,
        });
      }
      throw Object.assign(new Error("SkilzVolt user-count response was invalid"), {
        kind: "protocol" as const,
        cause: error,
      });
    }
  } finally {
    clearTimeout(timer);
  }
}

async function defaultWriteState(state: SkilzVoltUserCountState, statePath: string): Promise<void> {
  await mkdir(path.dirname(statePath), { recursive: true });
  const tempPath = `${statePath}.tmp-${process.pid}`;
  await writeFile(tempPath, `${JSON.stringify(state, null, 2)}\n`, "utf8");
  try {
    await chmod(tempPath, 0o600);
    await rename(tempPath, statePath);
  } catch (error) {
    await unlink(tempPath).catch(() => {});
    throw error;
  }
}

function stateFromCount(total: number, sinceLast: number, now: Date): SkilzVoltUserCountState {
  return {
    total,
    sinceLast,
    acknowledgementSucceeded: false,
    checkedAt: now.toISOString(),
    checkedAtEuropeLondon: formatLondonTime(now),
  };
}

export async function pollSkilzVoltUserCount(
  params: {
    connectionKeyEnv?: string;
    fetchImpl?: FetchLike;
    getBearerToken?: () => string | undefined | Promise<string | undefined>;
    statePath?: string;
    now?: () => Date;
    writeState?: StateWriter;
    timeoutMs?: number;
  } = {},
): Promise<SkilzVoltUserCountResult> {
  const fetchImpl = params.fetchImpl ?? fetch;
  const timeoutMs = params.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const getBearerToken =
    params.getBearerToken ??
    createSkilzVoltAccessTokenGetter({
      connectionKeyEnv: params.connectionKeyEnv ?? DEFAULT_CONNECTION_KEY_ENV,
    });
  const token = await getBearerToken();
  if (!token) {
    return failure(
      "not_connected",
      "The existing SkilzVolt monitoring connection is missing or not authorised.",
    );
  }

  let countRequest: { response: Response; body?: string };
  try {
    countRequest = await request(
      fetchImpl,
      SKILZVOLT_USER_COUNT_URL,
      token,
      { method: "GET" },
      timeoutMs,
      true,
    );
  } catch (error) {
    const kind = error && typeof error === "object" && "kind" in error ? error.kind : "network";
    return failure(
      kind === "timeout" ? "timeout" : kind === "protocol" ? "protocol" : "network",
      kind === "timeout"
        ? "SkilzVolt user-count request timed out."
        : kind === "protocol"
          ? "SkilzVolt user-count response invalid."
          : "SkilzVolt user-count request failed.",
    );
  }
  const countResponse = countRequest.response;

  if (countResponse.status === 401 || countResponse.status === 403) {
    return failure(
      countResponse.status === 401 ? "auth" : "permission",
      "The existing SkilzVolt monitoring connection is missing, expired, revoked, or not authorised.",
    );
  }
  if (!countResponse.ok) {
    return failure(
      "protocol",
      `SkilzVolt user-count endpoint returned HTTP ${countResponse.status}.`,
    );
  }

  let count: { total: number; sinceLast: number; deliveryRef: string };
  try {
    count = assertCountPayload(JSON.parse(countRequest.body ?? ""));
  } catch (error) {
    return failure(
      "protocol",
      error instanceof Error
        ? `SkilzVolt user-count response invalid: ${error.message}.`
        : "SkilzVolt user-count response invalid.",
    );
  }

  const now = (params.now ?? (() => new Date()))();
  const pendingState = stateFromCount(count.total, count.sinceLast, now);
  try {
    await (
      params.writeState ??
      ((state: SkilzVoltUserCountState) =>
        defaultWriteState(state, params.statePath ?? DEFAULT_STATE_PATH))
    )(pendingState);
  } catch {
    return failure(
      "record",
      "SkilzVolt user-count result could not be recorded; delivery was not acknowledged.",
      { ...pendingState, recorded: false },
    );
  }

  let ackRequest: { response: Response };
  try {
    ackRequest = await request(
      fetchImpl,
      SKILZVOLT_USER_COUNT_ACK_URL,
      token,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ delivery_ref: count.deliveryRef }),
      },
      timeoutMs,
      false,
    );
  } catch (error) {
    const kind = error && typeof error === "object" && "kind" in error ? error.kind : "network";
    return failure(
      kind === "timeout" ? "timeout" : "ack",
      kind === "timeout"
        ? "SkilzVolt user-count acknowledgement timed out; retrying the same snapshot later."
        : "SkilzVolt user-count acknowledgement failed; retrying the same snapshot later.",
      { ...pendingState, recorded: true },
    );
  }
  const ackResponse = ackRequest.response;

  if (ackResponse.status === 401 || ackResponse.status === 403) {
    return failure(
      ackResponse.status === 401 ? "auth" : "permission",
      "The existing SkilzVolt monitoring connection is missing, expired, revoked, or not authorised.",
      { ...pendingState, recorded: true },
    );
  }
  if (!ackResponse.ok) {
    return failure(
      "ack",
      `SkilzVolt user-count acknowledgement returned HTTP ${ackResponse.status}; retrying the same snapshot later.`,
      { ...pendingState, recorded: true },
    );
  }

  const acknowledgedState = {
    ...pendingState,
    acknowledgementSucceeded: true as const,
  };
  try {
    await (
      params.writeState ??
      ((state: SkilzVoltUserCountState) =>
        defaultWriteState(state, params.statePath ?? DEFAULT_STATE_PATH))
    )(acknowledgedState);
  } catch {
    return failure(
      "record",
      "SkilzVolt acknowledged the user-count snapshot, but acknowledgement status could not be recorded.",
      { ...acknowledgedState, recorded: false },
    );
  }

  return { ok: true, ...acknowledgedState };
}
