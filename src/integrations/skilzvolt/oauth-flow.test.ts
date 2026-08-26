import { describe, expect, it, vi } from "vitest";
import { SKILZVOLT_OAUTH_REDIRECT_URI, SKILZVOLT_RESOURCE_URL } from "./config.js";
import {
  buildSkilzVoltAuthorizationUrl,
  exchangeSkilzVoltAuthorizationCode,
  refreshSkilzVoltAccessToken,
  runSkilzVoltOAuthLogin,
} from "./oauth-flow.js";

const authServer = {
  issuer: "https://auth.skilzvolt.com",
  authorizationEndpoint: "https://auth.skilzvolt.com/authorize",
  tokenEndpoint: "https://auth.skilzvolt.com/token",
};

describe("buildSkilzVoltAuthorizationUrl", () => {
  it("includes PKCE, state, and the fixed redirect URI", () => {
    const url = new URL(
      buildSkilzVoltAuthorizationUrl({
        authorizationEndpoint: authServer.authorizationEndpoint,
        clientId: "client-1",
        challenge: "challenge-1",
        state: "state-1",
      }),
    );
    expect(url.searchParams.get("client_id")).toBe("client-1");
    expect(url.searchParams.get("code_challenge")).toBe("challenge-1");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("state")).toBe("state-1");
    expect(url.searchParams.get("redirect_uri")).toBe(SKILZVOLT_OAUTH_REDIRECT_URI);
    // RFC 8707 resource indicator, required by the MCP authorization spec, binding the token to
    // the SkilzVolt MCP endpoint rather than leaving its audience ambiguous.
    expect(url.searchParams.get("resource")).toBe(SKILZVOLT_RESOURCE_URL);
  });
});

describe("exchangeSkilzVoltAuthorizationCode / refreshSkilzVoltAccessToken", () => {
  it("exchanges a code for tokens and normalizes expiry", async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: { body?: string }) => {
      const body = new URLSearchParams(init?.body ?? "");
      expect(body.get("grant_type")).toBe("authorization_code");
      expect(body.get("code_verifier")).toBe("verifier-1");
      expect(body.get("resource")).toBe(SKILZVOLT_RESOURCE_URL);
      return new Response(
        JSON.stringify({ access_token: "access-1", refresh_token: "refresh-1", expires_in: 3600 }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    });
    const before = Date.now();
    const tokens = await exchangeSkilzVoltAuthorizationCode({
      tokenEndpoint: authServer.tokenEndpoint,
      clientId: "client-1",
      code: "code-1",
      verifier: "verifier-1",
      fetchImpl: fetchImpl as typeof fetch,
    });
    expect(tokens.access).toBe("access-1");
    expect(tokens.refresh).toBe("refresh-1");
    expect(tokens.expires).toBeGreaterThan(before);
  });

  it("throws a token_exchange error when access_token is missing", async () => {
    const fetchImpl = vi.fn(
      async () =>
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    await expect(
      exchangeSkilzVoltAuthorizationCode({
        tokenEndpoint: authServer.tokenEndpoint,
        clientId: "client-1",
        code: "code-1",
        verifier: "verifier-1",
        fetchImpl: fetchImpl as typeof fetch,
      }),
    ).rejects.toMatchObject({ kind: "token_exchange" });
  });

  it("refreshes an access token using the refresh grant", async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: { body?: string }) => {
      const body = new URLSearchParams(init?.body ?? "");
      expect(body.get("grant_type")).toBe("refresh_token");
      expect(body.get("refresh_token")).toBe("refresh-1");
      expect(body.get("resource")).toBe(SKILZVOLT_RESOURCE_URL);
      return new Response(JSON.stringify({ access_token: "access-2", expires_in: 1800 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const tokens = await refreshSkilzVoltAccessToken({
      tokenEndpoint: authServer.tokenEndpoint,
      clientId: "client-1",
      refreshToken: "refresh-1",
      fetchImpl: fetchImpl as typeof fetch,
    });
    expect(tokens.access).toBe("access-2");
  });

  it("surfaces a non-2xx refresh response as a refresh error", async () => {
    const fetchImpl = vi.fn(async () => new Response("denied", { status: 400 }));
    await expect(
      refreshSkilzVoltAccessToken({
        tokenEndpoint: authServer.tokenEndpoint,
        clientId: "client-1",
        refreshToken: "refresh-1",
        fetchImpl: fetchImpl as typeof fetch,
      }),
    ).rejects.toMatchObject({ kind: "refresh" });
  });
});

describe("runSkilzVoltOAuthLogin", () => {
  it("uses the manual paste-URL fallback in a remote environment and never prompts for a key", async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: { body?: string }) => {
      const body = new URLSearchParams(init?.body ?? "");
      expect(body.get("grant_type")).toBe("authorization_code");
      return new Response(
        JSON.stringify({ access_token: "access-1", refresh_token: "refresh-1", expires_in: 3600 }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    });
    let capturedState = "";
    const openUrl = vi.fn(async () => true);
    const prompt = vi.fn(async () => {
      const state = capturedState;
      return `${SKILZVOLT_OAUTH_REDIRECT_URI}?code=code-1&state=${state}`;
    });
    const log = vi.fn((message: string) => {
      const match = message.match(/[?&]state=([^&\s]+)/);
      if (match) {
        capturedState = match[1]!;
      }
    });

    const tokens = await runSkilzVoltOAuthLogin({
      isRemote: true,
      openUrl,
      prompt,
      log,
      note: vi.fn(async () => {}),
      progress: { update: vi.fn() },
      fetchImpl: fetchImpl as typeof fetch,
      authServer,
      clientId: "client-1",
    });

    expect(openUrl).not.toHaveBeenCalled();
    expect(tokens).toEqual({
      access: "access-1",
      refresh: "refresh-1",
      expires: expect.any(Number),
    });
  });

  it("rejects a mismatched state in the manual fallback", async () => {
    const openUrl = vi.fn(async () => true);
    const log = vi.fn();
    const prompt = vi.fn(
      async () => `${SKILZVOLT_OAUTH_REDIRECT_URI}?code=code-1&state=wrong-state`,
    );
    await expect(
      runSkilzVoltOAuthLogin({
        isRemote: true,
        openUrl,
        prompt,
        log,
        fetchImpl: vi.fn() as unknown as typeof fetch,
        authServer,
        clientId: "client-1",
      }),
    ).rejects.toMatchObject({ kind: "authorization" });
  });
});
