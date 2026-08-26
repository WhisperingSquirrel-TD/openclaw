import { describe, expect, it, vi } from "vitest";
import { discoverSkilzVoltAuthorizationServer } from "./discovery.js";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("discoverSkilzVoltAuthorizationServer", () => {
  it("follows resource metadata to the authorization server and reads its endpoints", async () => {
    const fetchImpl = vi.fn(async (href: string) => {
      // RFC 9728: for a resource at .../mcp, the well-known segment is inserted before the
      // resource's own path, not requested at the bare origin root.
      if (href === "https://app.skilzvolt.com/.well-known/oauth-protected-resource/mcp") {
        return json({ authorization_servers: ["https://auth.skilzvolt.com"] });
      }
      if (href.endsWith("/.well-known/oauth-authorization-server")) {
        return json({
          issuer: "https://auth.skilzvolt.com",
          authorization_endpoint: "https://auth.skilzvolt.com/authorize",
          token_endpoint: "https://auth.skilzvolt.com/token",
          registration_endpoint: "https://auth.skilzvolt.com/register",
        });
      }
      throw new Error(`unexpected fetch: ${href}`);
    });

    const result = await discoverSkilzVoltAuthorizationServer({
      resourceUrl: "https://app.skilzvolt.com/mcp",
      fetchImpl: fetchImpl as typeof fetch,
    });

    expect(result).toEqual({
      issuer: "https://auth.skilzvolt.com",
      authorizationEndpoint: "https://auth.skilzvolt.com/authorize",
      tokenEndpoint: "https://auth.skilzvolt.com/token",
      registrationEndpoint: "https://auth.skilzvolt.com/register",
    });
  });

  it("falls back to openid-configuration when oauth-authorization-server is unavailable", async () => {
    const fetchImpl = vi.fn(async (href: string) => {
      if (href === "https://app.skilzvolt.com/.well-known/oauth-protected-resource/mcp") {
        return json({ authorization_servers: ["https://auth.skilzvolt.com"] });
      }
      if (href.endsWith("/.well-known/oauth-authorization-server")) {
        return json({ error: "not found" }, 404);
      }
      if (href.endsWith("/.well-known/openid-configuration")) {
        return json({
          authorization_endpoint: "https://auth.skilzvolt.com/authorize",
          token_endpoint: "https://auth.skilzvolt.com/token",
        });
      }
      throw new Error(`unexpected fetch: ${href}`);
    });

    const result = await discoverSkilzVoltAuthorizationServer({
      resourceUrl: "https://app.skilzvolt.com/mcp",
      fetchImpl: fetchImpl as typeof fetch,
    });
    expect(result.authorizationEndpoint).toBe("https://auth.skilzvolt.com/authorize");
    expect(result.registrationEndpoint).toBeUndefined();
  });

  it("throws a discovery error when required endpoints are missing", async () => {
    const fetchImpl = vi.fn(async (href: string) => {
      if (href.endsWith("/.well-known/oauth-protected-resource")) {
        return json({});
      }
      return json({});
    });

    await expect(
      discoverSkilzVoltAuthorizationServer({
        resourceUrl: "https://app.skilzvolt.com/mcp",
        fetchImpl: fetchImpl as typeof fetch,
      }),
    ).rejects.toMatchObject({ kind: "discovery" });
  });

  it("preserves a path-based authorization-server issuer per RFC 8414 (well-known inserted before the path)", async () => {
    const requested: string[] = [];
    const fetchImpl = vi.fn(async (href: string) => {
      requested.push(href);
      if (href.endsWith("/.well-known/oauth-protected-resource")) {
        return json({ authorization_servers: ["https://auth.skilzvolt.com/tenant-a"] });
      }
      if (href === "https://auth.skilzvolt.com/.well-known/oauth-authorization-server/tenant-a") {
        return json({
          authorization_endpoint: "https://auth.skilzvolt.com/tenant-a/authorize",
          token_endpoint: "https://auth.skilzvolt.com/tenant-a/token",
        });
      }
      throw new Error(`unexpected fetch: ${href}`);
    });

    const result = await discoverSkilzVoltAuthorizationServer({
      resourceUrl: "https://app.skilzvolt.com",
      fetchImpl: fetchImpl as typeof fetch,
    });
    expect(result.authorizationEndpoint).toBe("https://auth.skilzvolt.com/tenant-a/authorize");
    expect(requested).toContain(
      "https://auth.skilzvolt.com/.well-known/oauth-authorization-server/tenant-a",
    );
  });

  it("falls back to a path-based openid-configuration with the well-known suffix appended after the path", async () => {
    const fetchImpl = vi.fn(async (href: string) => {
      if (href.endsWith("/.well-known/oauth-protected-resource")) {
        return json({ authorization_servers: ["https://auth.skilzvolt.com/tenant-a"] });
      }
      if (href === "https://auth.skilzvolt.com/.well-known/oauth-authorization-server/tenant-a") {
        return json({ error: "not found" }, 404);
      }
      if (href === "https://auth.skilzvolt.com/tenant-a/.well-known/openid-configuration") {
        return json({
          authorization_endpoint: "https://auth.skilzvolt.com/tenant-a/authorize",
          token_endpoint: "https://auth.skilzvolt.com/tenant-a/token",
        });
      }
      throw new Error(`unexpected fetch: ${href}`);
    });

    const result = await discoverSkilzVoltAuthorizationServer({
      resourceUrl: "https://app.skilzvolt.com",
      fetchImpl: fetchImpl as typeof fetch,
    });
    expect(result.authorizationEndpoint).toBe("https://auth.skilzvolt.com/tenant-a/authorize");
  });

  it("inserts the well-known segment before a multi-segment resource path, per RFC 9728", async () => {
    const requested: string[] = [];
    const fetchImpl = vi.fn(async (href: string) => {
      requested.push(href);
      if (href === "https://app.skilzvolt.com/.well-known/oauth-protected-resource/api/mcp") {
        return json({ authorization_servers: ["https://auth.skilzvolt.com"] });
      }
      if (href.endsWith("/.well-known/oauth-authorization-server")) {
        return json({
          authorization_endpoint: "https://auth.skilzvolt.com/authorize",
          token_endpoint: "https://auth.skilzvolt.com/token",
        });
      }
      throw new Error(`unexpected fetch: ${href}`);
    });

    await discoverSkilzVoltAuthorizationServer({
      resourceUrl: "https://app.skilzvolt.com/api/mcp",
      fetchImpl: fetchImpl as typeof fetch,
    });
    expect(requested[0]).toBe(
      "https://app.skilzvolt.com/.well-known/oauth-protected-resource/api/mcp",
    );
  });
});
