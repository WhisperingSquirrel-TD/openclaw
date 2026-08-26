import { describe, expect, it, vi } from "vitest";
import { registerSkilzVoltOAuthClient } from "./dynamic-registration.js";

describe("registerSkilzVoltOAuthClient", () => {
  it("registers a public native-app client and returns its client_id", async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: { body?: string }) => {
      const body = JSON.parse(init?.body ?? "{}") as Record<string, unknown>;
      expect(body.token_endpoint_auth_method).toBe("none");
      expect(body.redirect_uris).toEqual(["http://127.0.0.1:51823/skilzvolt/oauth/callback"]);
      return new Response(JSON.stringify({ client_id: "client-123" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      });
    });

    const result = await registerSkilzVoltOAuthClient({
      registrationEndpoint: "https://auth.skilzvolt.com/register",
      redirectUri: "http://127.0.0.1:51823/skilzvolt/oauth/callback",
      fetchImpl: fetchImpl as typeof fetch,
    });
    expect(result).toEqual({ clientId: "client-123" });
  });

  it("fails clearly when the server does not return a client_id", async () => {
    const fetchImpl = vi.fn(
      async () =>
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    await expect(
      registerSkilzVoltOAuthClient({
        registrationEndpoint: "https://auth.skilzvolt.com/register",
        redirectUri: "http://127.0.0.1:51823/skilzvolt/oauth/callback",
        fetchImpl: fetchImpl as typeof fetch,
      }),
    ).rejects.toMatchObject({ kind: "registration" });
  });

  it("surfaces non-2xx responses as a registration error", async () => {
    const fetchImpl = vi.fn(async () => new Response("nope", { status: 400 }));
    await expect(
      registerSkilzVoltOAuthClient({
        registrationEndpoint: "https://auth.skilzvolt.com/register",
        redirectUri: "http://127.0.0.1:51823/skilzvolt/oauth/callback",
        fetchImpl: fetchImpl as typeof fetch,
      }),
    ).rejects.toMatchObject({ kind: "registration" });
  });
});
