import { createHash } from "node:crypto";
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
  it("reads every current-version chunk with the live skills_get contract and validates hash", async () => {
    const content = '<!-- skilzvolt-workflow {"requirements":[{"id":"capture😀"}]} -->';
    const codePoints = Array.from(content);
    const split = Math.floor(codePoints.length / 2);
    const firstChunk = codePoints.slice(0, split).join("");
    const secondChunk = codePoints.slice(split).join("");
    const hash = createHash("sha256").update(content, "utf8").digest("hex");
    const calls: Record<string, unknown>[] = [];
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
          tools: [{ name: "workspaces_list" }, { name: "skills_search" }, { name: "skills_get" }],
        });
      }
      if (body.method === "tools/call" && body.params?.name === "skills_get") {
        const args = body.params.arguments ?? {};
        calls.push(args);
        const first = args.start_char === undefined;
        return rpc(body.id!, {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                first
                  ? {
                      skill_id: "skill-1",
                      version_id: "v2",
                      version_is_current: true,
                      content: firstChunk,
                      content_hash: hash,
                      total_content_chars: codePoints.length,
                      total_content_bytes: Buffer.byteLength(content),
                      chunk: {
                        start_char: 0,
                        end_char: split,
                        complete: false,
                        next_start_char: split,
                        content_utf8_bytes: Buffer.byteLength(firstChunk),
                        content_serialized_bytes: Buffer.byteLength(firstChunk),
                      },
                      content_metadata: { origin: "vault", is_untrusted: false },
                      resources: [],
                    }
                  : {
                      skill_id: "skill-1",
                      version_id: "v2",
                      version_is_current: true,
                      content: secondChunk,
                      chunk: {
                        start_char: split,
                        end_char: codePoints.length,
                        complete: true,
                        content_utf8_bytes: Buffer.byteLength(secondChunk),
                        content_serialized_bytes: Buffer.byteLength(secondChunk),
                      },
                    },
              ),
            },
          ],
        });
      }
      return rpc(body.id!, { content: [] });
    });
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: fetchImpl as typeof fetch,
      getBearerToken: () => "svk_test_only",
    });
    const catalogue = new SkilzVoltCatalogue(client);
    const entry = {
      skillId: "skill-1",
      workspaceId: "workspace-1",
      name: "learning",
      description: "Learn",
      currentVersionId: "v2",
    };
    const live = await catalogue.readCurrentSkill(entry, "test");
    expect(live.content).toBe(content);
    expect(calls).toEqual([
      {
        skill_id: "skill-1",
        version_id: "v2",
        max_chars: 12000,
        include_metadata: true,
        include_resources: true,
      },
      {
        skill_id: "skill-1",
        max_chars: 12000,
        include_metadata: true,
        include_resources: true,
        version_id: "v2",
        start_char: split,
      },
    ]);
    expect(calls[0]).not.toHaveProperty("workspace_id");
    expect(calls[0]).not.toHaveProperty("skillId");
  });

  it("rejects stale versions and content hash mismatches", async () => {
    const fetchImpl = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as {
        id?: number;
        method: string;
        params?: { name?: string };
      };
      if (body.method === "initialize") return rpc(body.id!, { protocolVersion: "2025-06-18" });
      if (body.method === "notifications/initialized") return new Response(null, { status: 202 });
      if (body.method === "tools/list") {
        return rpc(body.id!, {
          tools: [{ name: "workspaces_list" }, { name: "skills_search" }, { name: "skills_get" }],
        });
      }
      return rpc(body.id!, {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              skill_id: "skill-1",
              version_id: "v1",
              version_is_current: false,
              content: "stale",
              content_hash: "00".repeat(32),
              total_content_chars: 5,
              total_content_bytes: 5,
              complete: true,
            }),
          },
        ],
      });
    });
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: fetchImpl as typeof fetch,
      getBearerToken: () => "svk_test_only",
    });
    const catalogue = new SkilzVoltCatalogue(client);
    await expect(
      catalogue.readCurrentSkill(
        {
          skillId: "skill-1",
          workspaceId: "workspace-1",
          name: "learning",
          description: "",
          currentVersionId: "v2",
        },
        "test",
      ),
    ).rejects.toThrow(/current|current-version|version/i);
  });

  it("fetches referenced workflow resources and fails closed when the resource read fails", async () => {
    const content = "plain skill";
    const hash = createHash("sha256").update(content).digest("hex");
    let resourceCalls = 0;
    let failResource = false;
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
            { name: "skills_get_resource" },
          ],
        });
      }
      if (body.params?.name === "skills_get_resource") {
        resourceCalls += 1;
        if (failResource) {
          return rpc(body.id!, {
            isError: true,
            content: [{ type: "text", text: "resource unavailable" }],
          });
        }
        const resourceText = JSON.stringify({ requirements: [{ id: "capture" }] });
        return rpc(body.id!, {
          resource_id: "workflow-1",
          skill_id: "skill-1",
          version_id: "v2",
          content_sha256: createHash("sha256").update(resourceText).digest("hex"),
          content_length: Buffer.byteLength(resourceText),
          content: resourceText,
        });
      }
      return rpc(body.id!, {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              skill_id: "skill-1",
              version_id: "v2",
              version_is_current: true,
              content,
              content_hash: hash,
              total_content_chars: Array.from(content).length,
              total_content_bytes: Buffer.byteLength(content),
              chunk: { start_char: 0, end_char: content.length, complete: true },
              resources: [
                {
                  resource_id: "workflow-1",
                  content_sha256: createHash("sha256")
                    .update(JSON.stringify({ requirements: [{ id: "capture" }] }))
                    .digest("hex"),
                  content_length: Buffer.byteLength(
                    JSON.stringify({ requirements: [{ id: "capture" }] }),
                  ),
                },
              ],
            }),
          },
        ],
      });
    });
    const client = new SkilzVoltClient({
      connectionKeyEnv: "TEST_SKILZVOLT_KEY",
      allowProposals: true,
      fetchImpl: fetchImpl as typeof fetch,
      getBearerToken: () => "svk_test_only",
    });
    const live = await new SkilzVoltCatalogue(client).readCurrentSkill(
      {
        skillId: "skill-1",
        workspaceId: "workspace-1",
        name: "learning",
        description: "",
        currentVersionId: "v2",
      },
      "test",
    );
    expect(live.workflow.requirements[0]?.id).toBe("capture");
    expect(resourceCalls).toBe(1);
    failResource = true;
    await expect(
      new SkilzVoltCatalogue(client).readCurrentSkill(
        {
          skillId: "skill-1",
          workspaceId: "workspace-1",
          name: "learning",
          description: "",
          currentVersionId: "v2",
        },
        "test",
      ),
    ).rejects.toThrow();
  });

  it("bootstraps compact lines, keeps duplicate names across workspaces, and hides routing metadata", async () => {
    const client = makeClient(() => ({
      revision: "rev-1",
      skills: [
        {
          skill_id: "skill-a",
          home_workspace_id: "ws-1",
          home_workspace_name: "Ops",
          name: "deploy",
          description: "Deploy   the   app\nwith  extra   whitespace",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          skill_id: "skill-b",
          home_workspace_id: "ws-2",
          home_workspace_name: "Sales",
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

  it("accepts the confirmed live SkilzVolt contract verbatim (flat home_workspace_* fields, no nested workspace object, null next_cursor)", async () => {
    const client = makeClient(() => ({
      catalogue_revision: "rev-live-1",
      skills: [
        {
          skill_id: "skill-live-1",
          name: "triage-inbox",
          description: "Triage the shared inbox",
          current_version_id: "v3",
          updated_at: "2026-08-20T09:00:00Z",
          home_workspace_id: "1bf7c86f-cea1-4dac-bf08-e9d82728c1fb",
          home_workspace_name: "Tom Dean's workspace",
          home_workspace_slug: "tom",
        },
      ],
      next_cursor: null,
    }));
    const catalogue = new SkilzVoltCatalogue(client);
    const result = await catalogue.getLines();
    expect(result).toEqual({
      ok: true,
      lines: ["- triage-inbox: Triage the shared inbox [SkilzVolt]"],
    });
    expect(catalogue.findRouting("skill-live-1")).toMatchObject({
      workspaceId: "1bf7c86f-cea1-4dac-bf08-e9d82728c1fb",
      workspaceName: "Tom Dean's workspace",
    });
  });

  it("falls back to a nested workspace object when present (older/mocked shape) without weakening validation", async () => {
    const client = makeClient(() => ({
      revision: "rev-1",
      skills: [
        {
          skill_id: "skill-nested",
          workspace: { workspace_id: "ws-nested", name: "Legacy" },
          name: "legacy-skill",
          description: "Uses the pre-2026-08-26 nested shape",
        },
      ],
    }));
    const catalogue = new SkilzVoltCatalogue(client);
    const result = await catalogue.getLines();
    expect(result.ok).toBe(true);
    expect(catalogue.findRouting("skill-nested")).toMatchObject({ workspaceId: "ws-nested" });
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
              home_workspace_id: "ws-1",
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
            home_workspace_id: "ws-1",
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

  it("treats a past snapshot_expires_at as immediately stale, overriding the default cache window", async () => {
    let calls = 0;
    const client = makeClient(() => {
      calls += 1;
      return {
        revision: "rev-1",
        // Already expired by the time this response is read, even though the fixed 5-minute
        // fallback TTL would normally still consider it fresh.
        snapshot_expires_at: new Date(Date.now() - 1000).toISOString(),
        skills: [{ skill_id: "s1", home_workspace_id: "ws-1", name: "one", description: "First" }],
      };
    });
    const catalogue = new SkilzVoltCatalogue(client);
    await catalogue.getLines();
    await catalogue.getLines();
    expect(calls).toBe(2);
  });

  it("honors a snapshot_expires_at further out than the default cache window", async () => {
    vi.useFakeTimers();
    try {
      let calls = 0;
      const client = makeClient(() => {
        calls += 1;
        return {
          revision: "rev-1",
          snapshot_expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
          skills: [
            { skill_id: "s1", home_workspace_id: "ws-1", name: "one", description: "First" },
          ],
        };
      });
      const catalogue = new SkilzVoltCatalogue(client);
      await catalogue.getLines();
      // Past the default 5-minute TTL, but still inside the server-declared 10-minute window.
      vi.advanceTimersByTime(6 * 60 * 1000);
      await catalogue.getLines();
      expect(calls).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("falls back to the default cache window when snapshot_expires_at is absent", async () => {
    vi.useFakeTimers();
    try {
      let calls = 0;
      const client = makeClient(() => {
        calls += 1;
        return {
          revision: "rev-1",
          skills: [
            { skill_id: "s1", home_workspace_id: "ws-1", name: "one", description: "First" },
          ],
        };
      });
      const catalogue = new SkilzVoltCatalogue(client);
      await catalogue.getLines();
      vi.advanceTimersByTime(6 * 60 * 1000);
      await catalogue.getLines();
      expect(calls).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });
});
