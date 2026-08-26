import { describe, expect, it, vi } from "vitest";
import { SkilzVoltCatalogue } from "./catalogue.js";
import { SkilzVoltClient } from "./client.js";

function rpc(id: number, result: unknown): Response {
  return new Response(JSON.stringify({ jsonrpc: "2.0", id, result }), {
    status: 200,
    headers: { "content-type": "application/json", "mcp-session-id": "session-1" },
  });
}

function makeClient(
  handleCatalogueCall: (args: Record<string, unknown>) => unknown,
): SkilzVoltClient {
  const fetchImpl = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)) as {
      id?: number;
      method: string;
      params?: { name?: string; arguments?: Record<string, unknown> };
    };
    if (body.method === "initialize") return rpc(body.id!, { protocolVersion: "2025-06-18" });
    if (body.method === "notifications/initialized") return new Response(null, { status: 202 });
    if (body.method === "tools/list") {
      return rpc(body.id!, {
        tools: [
          { name: "workspaces_list" },
          { name: "skills_search" },
          { name: "skills_get" },
          { name: "skills_catalogue" },
        ],
      });
    }
    if (body.method === "tools/call" && body.params?.name === "skills_catalogue") {
      const data = handleCatalogueCall(body.params.arguments ?? {});
      return rpc(body.id!, { content: [{ type: "text", text: JSON.stringify(data) }] });
    }
    return rpc(body.id!, { content: [] });
  });
  return new SkilzVoltClient({
    connectionKeyEnv: "TEST_SKILZVOLT_KEY",
    allowProposals: true,
    fetchImpl: fetchImpl as typeof fetch,
    getBearerToken: () => "svk_test_only",
  });
}

describe("SkilzVoltCatalogue", () => {
  it("bootstraps compact lines, keeps duplicate names across workspaces, and hides routing metadata", async () => {
    const client = makeClient(() => ({
      revision: "rev-1",
      skills: [
        {
          skill_id: "skill-a",
          workspace: { workspace_id: "ws-1", name: "Ops" },
          name: "deploy",
          description: "Deploy   the   app\nwith  extra   whitespace",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          skill_id: "skill-b",
          workspace: { workspace_id: "ws-2", name: "Sales" },
          name: "deploy",
          description: "A different deploy skill in another workspace",
        },
      ],
    }));
    const catalogue = new SkilzVoltCatalogue(client);
    const result = await catalogue.getLines();
    expect(result).toEqual({
      ok: true,
      lines: [
        "- deploy: Deploy the app with extra whitespace [SkilzVolt]",
        "- deploy: A different deploy skill in another workspace [SkilzVolt]",
      ],
    });
    // Routing metadata (skill_id, workspace) is retained internally but never in the lines above.
    expect(catalogue.findRouting("skill-a")).toMatchObject({ workspaceId: "ws-1" });
    expect(catalogue.findRouting("skill-b")).toMatchObject({ workspaceId: "ws-2" });
  });

  it("follows cursor-based pagination across multiple pages", async () => {
    let calls = 0;
    const client = makeClient((args) => {
      calls += 1;
      if (!args.cursor) {
        return {
          revision: "rev-1",
          skills: [
            {
              skill_id: "s1",
              workspace: { workspace_id: "ws-1" },
              name: "one",
              description: "First",
            },
          ],
          next_cursor: "page-2",
        };
      }
      return {
        revision: "rev-1",
        skills: [
          {
            skill_id: "s2",
            workspace: { workspace_id: "ws-1" },
            name: "two",
            description: "Second",
          },
        ],
      };
    });
    const catalogue = new SkilzVoltCatalogue(client);
    const result = await catalogue.getLines();
    expect(calls).toBe(2);
    expect(result).toEqual({
      ok: true,
      lines: ["- one: First [SkilzVolt]", "- two: Second [SkilzVolt]"],
    });
  });

  it("reports an explicit degraded state on malformed responses instead of guessing", async () => {
    const client = makeClient(() => ({ revision: "rev-1", skills: "not-an-array" }));
    const catalogue = new SkilzVoltCatalogue(client);
    const result = await catalogue.getLines();
    expect(result.ok).toBe(false);
    expect((result as { reason: string }).reason).toMatch(/skills array/);
  });

  it("reports degraded on a network failure and never serves stale data as current after failure", async () => {
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: vi.fn(async () => {
        throw new Error("network down");
      }),
      getBearerToken: () => "svk_test_only",
    });
    const catalogue = new SkilzVoltCatalogue(client);
    const result = await catalogue.getLines();
    expect(result.ok).toBe(false);
  });

  it("fails explicitly instead of serving a partial catalogue when pagination never terminates", async () => {
    let page = 0;
    const client = makeClient(() => {
      page += 1;
      // Every page reports a next_cursor, so pagination never naturally terminates; the
      // catalogue must refuse to report this bounded, partial fetch as the live catalogue.
      return {
        revision: "rev-1",
        skills: [
          {
            skill_id: `s${page}`,
            workspace: { workspace_id: "ws-1" },
            name: `n${page}`,
            description: "d",
          },
        ],
        next_cursor: `page-${page + 1}`,
      };
    });
    const catalogue = new SkilzVoltCatalogue(client);
    const result = await catalogue.getLines();
    expect(result.ok).toBe(false);
    expect((result as { reason: string }).reason).toMatch(/exceeded/);
  });

  it("treats an unchanged response as reusing the prior snapshot, and fails if none is cached", async () => {
    const client = makeClient(() => ({ revision: "rev-1", unchanged: true }));
    const catalogue = new SkilzVoltCatalogue(client);
    const result = await catalogue.getLines();
    expect(result.ok).toBe(false);
  });
});
