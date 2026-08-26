import { describe, expect, it, vi } from "vitest";
import { SKILZVOLT_ALLOWED_TOOLS, SkilzVoltClient } from "./client.js";
import { SKILZVOLT_ENDPOINT } from "./config.js";

function rpc(id: number, result: unknown): Response {
  return new Response(JSON.stringify({ jsonrpc: "2.0", id, result }), {
    status: 200,
    headers: {
      "content-type": "application/json",
      "mcp-session-id": "session-1",
    },
  });
}

const liveTools = [
  "workspaces_list",
  "skills_search",
  "skills_get",
  "skills_create",
  "evil_arbitrary_tool",
].map((name) => ({
  name,
  description: `${name} description`,
  inputSchema: { type: "object", properties: {} },
}));

describe("SkilzVoltClient", () => {
  it("allowlists every published contract tool and no arbitrary tool", async () => {
    expect(SKILZVOLT_ALLOWED_TOOLS).toHaveLength(18);
    const tools = SKILZVOLT_ALLOWED_TOOLS.map((name) => ({
      name,
      inputSchema: { type: "object", properties: {} },
    }));
    const fetchImpl = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { id?: number; method: string };
      if (body.method === "initialize") return rpc(body.id!, { protocolVersion: "2025-06-18" });
      if (body.method === "notifications/initialized") return new Response(null, { status: 202 });
      if (body.method === "tools/list")
        return rpc(body.id!, { tools: [...tools, { name: "nope" }] });
      return rpc(body.id!, { structuredContent: { page: 1 }, content: [] });
    });
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: fetchImpl as typeof fetch,
      getBearerToken: () => "svk_test_only",
    });

    expect((await client.listTools()).map((tool) => tool.name)).toEqual(SKILZVOLT_ALLOWED_TOOLS);
    await expect(
      client.callTool("skills_export_all", { cursor: "opaque", limit: 1 }),
    ).resolves.toEqual({
      content: [],
      structuredContent: { page: 1 },
      data: { page: 1 },
    });
  });

  it("uses only the fixed endpoint and filters the live tool list", async () => {
    const urls: string[] = [];
    const calls: string[] = [];
    const fetchImpl = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      urls.push(typeof url === "string" ? url : url instanceof URL ? url.href : url.url);
      const body = JSON.parse(String(init?.body)) as {
        id?: number;
        method: string;
      };
      calls.push(body.method);
      if (body.method === "initialize") {
        return rpc(body.id!, { protocolVersion: "2025-06-18" });
      }
      if (body.method === "notifications/initialized") {
        return new Response(null, { status: 202 });
      }
      if (body.method === "tools/list") {
        return rpc(body.id!, { tools: liveTools });
      }
      return rpc(body.id!, { content: [{ type: "text", text: "{}" }] });
    });
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: fetchImpl as typeof fetch,
      getBearerToken: () => "svk_test_only",
    });

    const tools = await client.listTools();
    expect(urls.every((url) => url === SKILZVOLT_ENDPOINT)).toBe(true);
    expect(tools.map((tool) => tool.name)).toEqual([
      "workspaces_list",
      "skills_search",
      "skills_get",
      "skills_create",
    ]);
    expect(fetchImpl.mock.calls[0]?.[1]?.headers).toMatchObject({
      authorization: "Bearer svk_test_only",
    });

    await client.callTool("skills_search", { query: "deployment" });
    expect(calls).toEqual(["initialize", "notifications/initialized", "tools/list", "tools/call"]);
  });

  it("redacts auth failures and rejects oversized responses", async () => {
    const unauthorized = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: vi.fn(
        async () =>
          new Response(JSON.stringify({ error: "token=svk_secret_should_not_escape" }), {
            status: 401,
            headers: { "content-type": "application/json" },
          }),
      ),
      getBearerToken: () => "svk_secret_should_not_escape",
    });
    await expect(unauthorized.listTools()).rejects.toMatchObject({
      kind: "auth",
    });
    await expect(unauthorized.listTools()).rejects.toThrow(/not connected|rejected|revoked/);
    try {
      await unauthorized.listTools();
    } catch (error) {
      expect(String(error)).not.toContain("svk_secret_should_not_escape");
    }

    const oversized = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      maxResponseBytes: 8,
      fetchImpl: vi.fn(
        async () =>
          new Response("0123456789", {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
      ),
      getBearerToken: () => "svk_test_only",
    });
    await expect(oversized.listTools()).rejects.toMatchObject({
      kind: "response_too_large",
    });
  });

  it("redacts the configured bearer value even when it has no svk_ prefix", async () => {
    const secret = "private-connection-key-without-prefix";
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: vi.fn(
        async () =>
          new Response(JSON.stringify({ message: `token=${secret}` }), {
            status: 500,
            headers: { "content-type": "application/json" },
          }),
      ),
      getBearerToken: () => secret,
    });
    await expect(client.listTools()).rejects.toThrow("[REDACTED]");
    try {
      await client.listTools();
    } catch (error) {
      expect(String(error)).not.toContain(secret);
    }
  });

  it("redacts the configured bearer value from JSON-RPC errors", async () => {
    const secret = "private-rpc-key-without-prefix";
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              jsonrpc: "2.0",
              id: 1,
              error: { code: -32000, message: `unexpected ${secret} echo` },
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
      ),
      getBearerToken: () => secret,
    });
    try {
      await client.listTools();
    } catch (error) {
      expect(String(error)).toContain("[REDACTED]");
      expect(String(error)).not.toContain(secret);
    }
  });

  it("requires the live contract before allowing calls", async () => {
    const fetchImpl = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as {
        id?: number;
        method: string;
      };
      if (body.method === "initialize") {
        return rpc(body.id!, { protocolVersion: "2025-06-18" });
      }
      if (body.method === "notifications/initialized") {
        return new Response(null, { status: 202 });
      }
      return rpc(body.id!, { tools: [{ name: "skills_search" }] });
    });
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: fetchImpl as typeof fetch,
      getBearerToken: () => "svk_test_only",
    });
    await expect(client.callTool("skills_search", {})).rejects.toMatchObject({
      kind: "contract_drift",
    });
  });

  it("refreshes its catalogue after a tool-list-changed notification and preserves MCP errors", async () => {
    let toolListCalls = 0;
    const fetchImpl = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { id?: number; method: string };
      if (body.method === "initialize") return rpc(body.id!, { protocolVersion: "2025-06-18" });
      if (body.method === "notifications/initialized") return new Response(null, { status: 202 });
      if (body.method === "tools/list") {
        toolListCalls += 1;
        return rpc(body.id!, {
          tools: [
            { name: "workspaces_list" },
            { name: "skills_search" },
            { name: "skills_get" },
            ...(toolListCalls > 1 ? [{ name: "connection_diagnostic" }] : []),
          ],
        });
      }
      return new Response(
        [
          'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed"}',
          "",
          `data: {"jsonrpc":"2.0","id":${body.id},"result":{"isError":true,"content":[{"type":"text","text":"denied"}]}}`,
          "",
        ].join("\n"),
        { status: 200, headers: { "content-type": "text/event-stream" } },
      );
    });
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: fetchImpl as typeof fetch,
      getBearerToken: () => "svk_test_only",
    });

    await client.listTools();
    await expect(client.callTool("skills_search", { query: "test" })).resolves.toEqual({
      isError: true,
      content: [{ type: "text", text: "denied" }],
      data: { message: "denied" },
    });
    expect((await client.listTools()).map((tool) => tool.name)).toContain("connection_diagnostic");
    expect(toolListCalls).toBe(2);
  });

  it("awaits an async getBearerToken and fails clearly when it resolves to nothing", async () => {
    const fetchImpl = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { id?: number; method: string };
      if (body.method === "initialize") return rpc(body.id!, { protocolVersion: "2025-06-18" });
      if (body.method === "notifications/initialized") return new Response(null, { status: 202 });
      return rpc(body.id!, {
        tools: [{ name: "workspaces_list" }, { name: "skills_search" }, { name: "skills_get" }],
      });
    });
    const resolvedToken = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: fetchImpl as typeof fetch,
      getBearerToken: () => Promise.resolve("svk_async_token"),
    });
    await resolvedToken.listTools();
    expect(fetchImpl.mock.calls[0]?.[1]?.headers).toMatchObject({
      authorization: "Bearer svk_async_token",
    });

    const missingToken = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: fetchImpl as typeof fetch,
      getBearerToken: () => Promise.resolve(undefined),
    });
    await expect(missingToken.listTools()).rejects.toMatchObject({ kind: "auth" });
  });
});
