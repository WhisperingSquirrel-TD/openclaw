import { SKILZVOLT_ENDPOINT } from "./config.js";

export const SKILZVOLT_READ_TOOLS = [
  "search",
  "fetch",
  "workspaces_list",
  "skills_catalogue",
  "skills_search",
  "skills_get",
  "connection_diagnostic",
  "skills_get_resource",
  "skills_export_all",
  "skills_check_pending",
  "skills_proposal_status",
  "skills_get_proposal_diff",
] as const;

export const SKILZVOLT_PROPOSAL_TOOLS = [
  "skills_create",
  "skills_propose_change",
  "skills_submit_review",
] as const;

export const SKILZVOLT_MIGRATION_TOOLS = [
  "skills_migration_preview",
  "skills_migration_submit",
  "skills_migration_recover",
] as const;

export const SKILZVOLT_MAX_ARGUMENT_BYTES = 384_000;

export const SKILZVOLT_ALLOWED_TOOLS = [
  ...SKILZVOLT_READ_TOOLS,
  ...SKILZVOLT_PROPOSAL_TOOLS,
  ...SKILZVOLT_MIGRATION_TOOLS,
] as const;

export type SkilzVoltToolName = (typeof SKILZVOLT_ALLOWED_TOOLS)[number];

export type McpToolDescription = {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
};

export type SkilzVoltToolResult = {
  isError?: boolean;
  content?: unknown[];
  structuredContent?: Record<string, unknown>;
  /** Parsed structuredContent or the JSON encoded in a text content block. */
  data?: unknown;
  [key: string]: unknown;
};

type FetchLike = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

export type SkilzVoltClientOptions = {
  connectionKeyEnv: string;
  allowProposals: boolean;
  fetchImpl?: FetchLike;
  timeoutMs?: number;
  maxResponseBytes?: number;
  /**
   * Resolves the current bearer token. Async so the caller (core, not this extension) can
   * silently refresh an OAuth-issued access token before it is used. Falls back to reading
   * `connectionKeyEnv` directly when not supplied, for backwards compatibility.
   */
  getBearerToken?: () => string | undefined | Promise<string | undefined>;
  subscribeToNotifications?: boolean;
};

const REQUIRED_TOOLS = new Set(["workspaces_list", "skills_search", "skills_get"]);
const ALLOWED_TOOL_SET = new Set<string>(SKILZVOLT_ALLOWED_TOOLS);
const PROPOSAL_TOOL_SET = new Set<string>([...SKILZVOLT_PROPOSAL_TOOLS, "skills_migration_submit"]);

function redact(value: string, secret?: string): string {
  let redacted = value;
  if (secret) {
    redacted = redacted.split(secret).join("[REDACTED]");
    redacted = redacted.split(encodeURIComponent(secret)).join("[REDACTED]");
    redacted = redacted.split(JSON.stringify(secret).slice(1, -1)).join("[REDACTED]");
  }
  return redacted
    .replace(/\bsvk_[A-Za-z0-9._~-]+\b/g, "[REDACTED]")
    .replace(/\bBearer\s+[A-Za-z0-9._~+/-]+=*\b/gi, "Bearer [REDACTED]")
    .replace(/\b(token|key|authorization)\s*[:=]\s*["']?[^,}"'\s]+/gi, "$1=[REDACTED]")
    .slice(0, 500);
}

export class SkilzVoltError extends Error {
  constructor(
    message: string,
    readonly kind:
      | "auth"
      | "permission"
      | "protocol"
      | "network"
      | "timeout"
      | "response_too_large"
      | "contract_drift",
    secret?: string,
  ) {
    super(redact(message, secret));
    this.name = "SkilzVoltError";
  }
}

function parseSse(text: string): unknown[] {
  const messages: unknown[] = [];
  for (const frame of text.split(/\r?\n\r?\n/)) {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data || data === "[DONE]") {
      continue;
    }
    try {
      messages.push(JSON.parse(data));
    } catch {
      throw new SkilzVoltError("SkilzVolt returned malformed event-stream JSON", "protocol");
    }
  }
  return messages;
}

function parseResponsePayload(text: string, contentType: string | null): unknown[] {
  if (!text.trim()) {
    return [];
  }
  if (contentType?.toLowerCase().includes("text/event-stream")) {
    return parseSse(text);
  }
  try {
    const parsed = JSON.parse(text);
    return Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    throw new SkilzVoltError("SkilzVolt returned malformed JSON", "protocol");
  }
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function parseToolResult(value: unknown): SkilzVoltToolResult {
  const result = asRecord(value);
  if (!result) {
    throw new SkilzVoltError("SkilzVolt returned an invalid tool result", "protocol");
  }
  const structuredContent = asRecord(result.structuredContent);
  if (structuredContent) {
    return { ...result, structuredContent, data: structuredContent };
  }
  const text = Array.isArray(result.content)
    ? result.content
        .map(asRecord)
        .find((entry) => entry?.type === "text" && typeof entry.text === "string")?.text
    : undefined;
  if (typeof text === "string") {
    try {
      return { ...result, data: JSON.parse(text) };
    } catch {
      if (result.isError === true) {
        return { ...result, data: { message: text } };
      }
      throw new SkilzVoltError(
        "SkilzVolt returned non-JSON text content for a successful tool result",
        "protocol",
      );
    }
  }
  return result;
}

async function readBoundedBody(response: Response, maxBytes: number): Promise<string> {
  if (!response.body) {
    return "";
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
    if (size > maxBytes) {
      await reader.cancel();
      throw new SkilzVoltError(
        `SkilzVolt response exceeded the ${maxBytes}-byte safety limit`,
        "response_too_large",
      );
    }
    text += decoder.decode(chunk.value, { stream: true });
  }
  return text + decoder.decode();
}

export class SkilzVoltClient {
  private readonly fetchImpl: FetchLike;
  private readonly timeoutMs: number;
  private readonly maxResponseBytes: number;
  private readonly getBearerToken: () => string | undefined | Promise<string | undefined>;
  private sessionId?: string;
  private protocolVersion = "2025-06-18";
  private initialized = false;
  private requestId = 0;
  private tools?: McpToolDescription[];
  private notificationController?: AbortController;

  constructor(private readonly options: SkilzVoltClientOptions) {
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.timeoutMs = options.timeoutMs ?? 20_000;
    this.maxResponseBytes = options.maxResponseBytes ?? 512_000;
    this.getBearerToken =
      options.getBearerToken ?? (() => process.env[this.options.connectionKeyEnv]?.trim());
  }

  private async bearerToken(): Promise<string> {
    const token = await this.getBearerToken();
    if (!token) {
      throw new SkilzVoltError(
        `SkilzVolt is not connected. Connect it with the SkilzVolt OAuth login command, or set ${this.options.connectionKeyEnv} in the private OpenClaw environment, then restart the gateway.`,
        "auth",
      );
    }
    return token;
  }

  private async request(
    method: string,
    params?: Record<string, unknown>,
    notification = false,
    signal?: AbortSignal,
  ): Promise<unknown> {
    const id = notification ? undefined : ++this.requestId;
    const bearerToken = await this.bearerToken();
    const controller = new AbortController();
    const onAbort = () => controller.abort(signal?.reason);
    signal?.addEventListener("abort", onAbort, { once: true });
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      let response: Response;
      try {
        response = await this.fetchImpl(SKILZVOLT_ENDPOINT, {
          method: "POST",
          headers: {
            accept: "application/json, text/event-stream",
            authorization: `Bearer ${bearerToken}`,
            "content-type": "application/json",
            ...(this.sessionId ? { "mcp-session-id": this.sessionId } : {}),
            ...(this.initialized ? { "mcp-protocol-version": this.protocolVersion } : {}),
          },
          body: JSON.stringify({
            jsonrpc: "2.0",
            ...(id === undefined ? {} : { id }),
            method,
            ...(params ? { params } : {}),
          }),
          signal: controller.signal,
        });
      } catch (error) {
        if (controller.signal.aborted) {
          throw new SkilzVoltError(
            "SkilzVolt request timed out or was cancelled",
            "timeout",
            bearerToken,
          );
        }
        throw new SkilzVoltError(
          `SkilzVolt network request failed: ${error instanceof Error ? error.message : String(error)}`,
          "network",
          bearerToken,
        );
      }

      const sessionId = response.headers.get("mcp-session-id");
      if (sessionId) {
        this.sessionId = sessionId;
      }
      const text = await readBoundedBody(response, this.maxResponseBytes);
      if (response.status === 401) {
        this.reset();
        throw new SkilzVoltError(
          "SkilzVolt authentication was rejected or revoked. Update the private connection key and restart the gateway.",
          "auth",
        );
      }
      if (response.status === 403) {
        throw new SkilzVoltError("SkilzVolt denied this workspace operation", "permission");
      }
      if (!response.ok) {
        throw new SkilzVoltError(
          `SkilzVolt returned HTTP ${response.status}${text ? `: ${redact(text)}` : ""}`,
          "protocol",
          bearerToken,
        );
      }
      if (notification || response.status === 202 || response.status === 204) {
        return undefined;
      }

      const payloads = parseResponsePayload(text, response.headers.get("content-type"));
      if (
        payloads.some(
          (candidate) =>
            candidate &&
            typeof candidate === "object" &&
            (candidate as Record<string, unknown>).method === "notifications/tools/list_changed",
        )
      ) {
        this.tools = undefined;
      }
      const payload = payloads.find(
        (candidate) =>
          candidate &&
          typeof candidate === "object" &&
          (candidate as Record<string, unknown>).id === id,
      ) as Record<string, unknown> | undefined;
      if (!payload) {
        throw new SkilzVoltError(
          "SkilzVolt response did not include the matching request",
          "protocol",
        );
      }
      if (payload.error && typeof payload.error === "object") {
        const error = payload.error as Record<string, unknown>;
        const message = typeof error.message === "string" ? error.message : "Unknown MCP error";
        throw new SkilzVoltError(`SkilzVolt MCP error: ${message}`, "protocol", bearerToken);
      }
      return payload.result;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    }
  }

  private async initialize(signal?: AbortSignal): Promise<void> {
    if (this.initialized) {
      return;
    }
    const result = (await this.request(
      "initialize",
      {
        protocolVersion: this.protocolVersion,
        capabilities: {},
        clientInfo: { name: "openclaw-skilzvolt-adapter", version: "1.0.0" },
      },
      false,
      signal,
    )) as Record<string, unknown> | undefined;
    if (typeof result?.protocolVersion === "string") {
      this.protocolVersion = result.protocolVersion;
    }
    await this.request("notifications/initialized", undefined, true, signal);
    this.initialized = true;
    if (this.options.subscribeToNotifications) {
      void this.startNotificationStream();
    }
  }

  private async startNotificationStream(): Promise<void> {
    if (this.notificationController || !this.sessionId) return;
    const controller = new AbortController();
    this.notificationController = controller;
    try {
      const response = await this.fetchImpl(SKILZVOLT_ENDPOINT, {
        method: "GET",
        headers: {
          accept: "text/event-stream",
          authorization: `Bearer ${await this.bearerToken()}`,
          "mcp-session-id": this.sessionId,
          "mcp-protocol-version": this.protocolVersion,
        },
        signal: controller.signal,
      });
      if (!response.ok || !response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (!controller.signal.aborted) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        const frames = buffer.split(/\r?\n\r?\n/);
        buffer = frames.pop() ?? "";
        for (const payload of parseSse(frames.join("\n\n"))) {
          if (
            payload &&
            typeof payload === "object" &&
            (payload as Record<string, unknown>).method === "notifications/tools/list_changed"
          ) {
            this.tools = undefined;
          }
        }
      }
    } catch {
      // The POST transport remains fully functional if an optional inbound SSE stream closes.
    } finally {
      if (this.notificationController === controller) {
        this.notificationController = undefined;
      }
    }
  }

  reset(): void {
    this.notificationController?.abort();
    this.notificationController = undefined;
    this.sessionId = undefined;
    this.initialized = false;
    this.tools = undefined;
  }

  async listTools(signal?: AbortSignal): Promise<McpToolDescription[]> {
    await this.initialize(signal);
    if (this.options.subscribeToNotifications && !this.notificationController) {
      void this.startNotificationStream();
    }
    if (this.tools) {
      return this.tools;
    }
    const result = (await this.request("tools/list", undefined, false, signal)) as
      | Record<string, unknown>
      | undefined;
    const rawTools = Array.isArray(result?.tools) ? result.tools : [];
    const tools = rawTools
      .filter((entry): entry is Record<string, unknown> =>
        Boolean(entry && typeof entry === "object" && typeof entry.name === "string"),
      )
      .filter((entry) => ALLOWED_TOOL_SET.has(entry.name as string))
      .filter(
        (entry) => this.options.allowProposals || !PROPOSAL_TOOL_SET.has(entry.name as string),
      )
      .map((entry) => ({
        name: entry.name as string,
        ...(typeof entry.description === "string" ? { description: entry.description } : {}),
        ...(entry.inputSchema && typeof entry.inputSchema === "object"
          ? { inputSchema: entry.inputSchema as Record<string, unknown> }
          : {}),
      }));
    const names = new Set(tools.map((tool) => tool.name));
    const missing = [...REQUIRED_TOOLS].filter((name) => !names.has(name));
    if (missing.length > 0) {
      throw new SkilzVoltError(
        `SkilzVolt contract drift: required tools missing (${missing.join(", ")})`,
        "contract_drift",
      );
    }
    this.tools = tools;
    return tools;
  }

  async callTool(
    name: SkilzVoltToolName,
    args: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<unknown> {
    if (!ALLOWED_TOOL_SET.has(name)) {
      throw new SkilzVoltError(`SkilzVolt tool is not allowed: ${name}`, "permission");
    }
    if (PROPOSAL_TOOL_SET.has(name) && !this.options.allowProposals) {
      throw new SkilzVoltError("SkilzVolt proposal operations are disabled", "permission");
    }
    const size = Buffer.byteLength(JSON.stringify(args));
    if (size > SKILZVOLT_MAX_ARGUMENT_BYTES) {
      throw new SkilzVoltError("SkilzVolt tool arguments exceeded the safety limit", "protocol");
    }
    const tools = await this.listTools(signal);
    if (!tools.some((tool) => tool.name === name)) {
      throw new SkilzVoltError(
        `SkilzVolt did not advertise the requested tool: ${name}`,
        "contract_drift",
      );
    }
    return parseToolResult(
      await this.request("tools/call", { name, arguments: args }, false, signal),
    );
  }
}
