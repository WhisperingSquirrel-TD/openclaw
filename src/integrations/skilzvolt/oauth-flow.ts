import { createHash, randomBytes } from "node:crypto";
import { createServer } from "node:http";
import {
  SKILZVOLT_OAUTH_CALLBACK_HOST,
  SKILZVOLT_OAUTH_CALLBACK_PATH,
  SKILZVOLT_OAUTH_CALLBACK_PORT,
  SKILZVOLT_OAUTH_REDIRECT_URI,
  SKILZVOLT_RESOURCE_URL,
} from "./config.js";
import type { FetchLike } from "./discovery.js";
import type { SkilzVoltAuthServerMetadata } from "./discovery.js";
import { SkilzVoltOAuthError, type SkilzVoltOAuthErrorKind } from "./errors.js";

export type SkilzVoltOAuthTokens = { access: string; refresh: string; expires: number };

export type SkilzVoltOAuthLoginContext = {
  /** True when running headless/remote, where a local browser+callback loop is not possible. */
  isRemote: boolean;
  openUrl: (url: string) => Promise<unknown>;
  prompt: (message: string) => Promise<string>;
  log: (message: string) => void;
  note?: (message: string, title?: string) => Promise<void>;
  progress?: { update: (message: string) => void };
  fetchImpl?: FetchLike;
};

function generatePkce(): { verifier: string; challenge: string } {
  const verifier = randomBytes(32).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  return { verifier, challenge };
}

function generateState(): string {
  return randomBytes(16).toString("base64url");
}

export function buildSkilzVoltAuthorizationUrl(params: {
  authorizationEndpoint: string;
  clientId: string;
  challenge: string;
  state: string;
}): string {
  const url = new URL(params.authorizationEndpoint);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", params.clientId);
  url.searchParams.set("redirect_uri", SKILZVOLT_OAUTH_REDIRECT_URI);
  url.searchParams.set("code_challenge", params.challenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("state", params.state);
  // RFC 8707 resource indicator, required by the MCP authorization spec: binds the requested
  // token to the SkilzVolt MCP endpoint so the authorization server can scope/audience-restrict
  // it correctly, instead of issuing a token that is ambiguous about which resource it is for.
  url.searchParams.set("resource", SKILZVOLT_RESOURCE_URL);
  return url.toString();
}

function parseCallbackInput(
  input: string,
  expectedState: string,
): { code: string } | { error: string } {
  const trimmed = input.trim();
  if (!trimmed) {
    return { error: "No input provided" };
  }
  try {
    const url = new URL(trimmed);
    const error = url.searchParams.get("error");
    if (error) {
      return { error: `SkilzVolt denied the request: ${error}` };
    }
    const code = url.searchParams.get("code");
    const state = url.searchParams.get("state");
    if (!code) {
      return { error: "Missing 'code' parameter in the pasted URL" };
    }
    if (state !== expectedState) {
      return { error: "State mismatch - please restart the login" };
    }
    return { code };
  } catch {
    return { error: "Paste the full redirect URL, not just the code." };
  }
}

async function waitForLocalCallback(params: {
  expectedState: string;
  timeoutMs: number;
  onProgress?: (message: string) => void;
}): Promise<{ code: string }> {
  return new Promise<{ code: string }>((resolve, reject) => {
    let timeout: NodeJS.Timeout | null = null;
    const server = createServer((req, res) => {
      try {
        const requestUrl = new URL(
          req.url ?? "/",
          `http://${SKILZVOLT_OAUTH_CALLBACK_HOST}:${SKILZVOLT_OAUTH_CALLBACK_PORT}`,
        );
        if (requestUrl.pathname !== SKILZVOLT_OAUTH_CALLBACK_PATH) {
          res.statusCode = 404;
          res.end("Not found");
          return;
        }
        const error = requestUrl.searchParams.get("error");
        const code = requestUrl.searchParams.get("code")?.trim();
        const state = requestUrl.searchParams.get("state")?.trim();
        if (error) {
          res.statusCode = 400;
          res.end(`SkilzVolt denied the request: ${error}`);
          finish(new Error(`SkilzVolt OAuth error: ${error}`));
          return;
        }
        if (!code || !state) {
          res.statusCode = 400;
          res.end("Missing code or state");
          finish(new Error("Missing SkilzVolt OAuth code or state"));
          return;
        }
        if (state !== params.expectedState) {
          res.statusCode = 400;
          res.end("Invalid state");
          finish(new Error("SkilzVolt OAuth state mismatch"));
          return;
        }
        res.statusCode = 200;
        res.setHeader("Content-Type", "text/html; charset=utf-8");
        res.end(
          "<!doctype html><html><head><meta charset='utf-8'/></head>" +
            "<body><h2>SkilzVolt connected</h2>" +
            "<p>You can close this window and return to OpenClaw.</p></body></html>",
        );
        finish(undefined, { code });
      } catch (err) {
        finish(err instanceof Error ? err : new Error("SkilzVolt OAuth callback failed"));
      }
    });

    const finish = (err?: Error, result?: { code: string }) => {
      if (timeout) {
        clearTimeout(timeout);
      }
      try {
        server.close();
      } catch {
        // ignore close errors
      }
      if (err) {
        reject(err);
      } else if (result) {
        resolve(result);
      }
    };

    server.once("error", (err) => {
      finish(err instanceof Error ? err : new Error("SkilzVolt OAuth callback server error"));
    });

    server.listen(SKILZVOLT_OAUTH_CALLBACK_PORT, SKILZVOLT_OAUTH_CALLBACK_HOST, () => {
      params.onProgress?.(
        `Waiting for the SkilzVolt OAuth callback on ${SKILZVOLT_OAUTH_REDIRECT_URI}…`,
      );
    });

    timeout = setTimeout(() => {
      finish(new Error("SkilzVolt OAuth callback timeout"));
    }, params.timeoutMs);
  });
}

async function postForm(
  url: string,
  body: Record<string, string>,
  fetchImpl: FetchLike,
  kind: SkilzVoltOAuthErrorKind,
): Promise<Record<string, unknown>> {
  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" },
      body: new URLSearchParams(body).toString(),
    });
  } catch (error) {
    throw new SkilzVoltOAuthError(
      `SkilzVolt token request failed: ${error instanceof Error ? error.message : String(error)}`,
      "network",
    );
  }
  const text = await response.text();
  if (!response.ok) {
    throw new SkilzVoltOAuthError(
      `SkilzVolt token endpoint returned HTTP ${response.status}`,
      kind,
    );
  }
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    throw new SkilzVoltOAuthError("SkilzVolt token endpoint returned a non-JSON response", kind);
  }
}

function parseTokenResponse(
  data: Record<string, unknown>,
  kind: SkilzVoltOAuthErrorKind,
): SkilzVoltOAuthTokens {
  const access = typeof data.access_token === "string" ? data.access_token : undefined;
  const refresh = typeof data.refresh_token === "string" ? data.refresh_token : undefined;
  const expiresInRaw = data.expires_in;
  const expiresIn = typeof expiresInRaw === "number" ? expiresInRaw : Number(expiresInRaw);
  if (!access) {
    throw new SkilzVoltOAuthError("SkilzVolt token response did not include an access_token", kind);
  }
  const ttlMs = Number.isFinite(expiresIn) && expiresIn > 0 ? expiresIn * 1000 : 55 * 60 * 1000;
  return { access, refresh: refresh ?? "", expires: Date.now() + ttlMs };
}

export async function exchangeSkilzVoltAuthorizationCode(params: {
  tokenEndpoint: string;
  clientId: string;
  code: string;
  verifier: string;
  fetchImpl?: FetchLike;
}): Promise<SkilzVoltOAuthTokens> {
  const data = await postForm(
    params.tokenEndpoint,
    {
      grant_type: "authorization_code",
      client_id: params.clientId,
      code: params.code,
      redirect_uri: SKILZVOLT_OAUTH_REDIRECT_URI,
      code_verifier: params.verifier,
      // Carried through from the authorization request per RFC 8707 - the token request must
      // repeat the resource indicator so the issued token is bound to the SkilzVolt MCP endpoint.
      resource: SKILZVOLT_RESOURCE_URL,
    },
    params.fetchImpl ?? fetch,
    "token_exchange",
  );
  return parseTokenResponse(data, "token_exchange");
}

export async function refreshSkilzVoltAccessToken(params: {
  tokenEndpoint: string;
  clientId: string;
  refreshToken: string;
  fetchImpl?: FetchLike;
}): Promise<SkilzVoltOAuthTokens> {
  const data = await postForm(
    params.tokenEndpoint,
    {
      grant_type: "refresh_token",
      client_id: params.clientId,
      refresh_token: params.refreshToken,
      // Re-asserted per RFC 8707 so a refreshed token stays bound to the same resource as the
      // original grant, rather than silently widening (or losing) its audience.
      resource: SKILZVOLT_RESOURCE_URL,
    },
    params.fetchImpl ?? fetch,
    "refresh",
  );
  return parseTokenResponse(data, "refresh");
}

/**
 * Runs the interactive SkilzVolt OAuth 2.1 + PKCE login: opens the consent page in a local
 * browser and captures the redirect on a localhost callback server, or — for remote/headless
 * sessions — prints the URL and accepts the pasted redirect URL back (the same fallback pattern
 * already used by every other OAuth provider in this codebase). Never prompts for a connection
 * key, token, or secret.
 */
export async function runSkilzVoltOAuthLogin(
  ctx: SkilzVoltOAuthLoginContext & {
    authServer: SkilzVoltAuthServerMetadata;
    clientId: string;
  },
): Promise<SkilzVoltOAuthTokens> {
  const { verifier, challenge } = generatePkce();
  const state = generateState();
  const authUrl = buildSkilzVoltAuthorizationUrl({
    authorizationEndpoint: ctx.authServer.authorizationEndpoint,
    clientId: ctx.clientId,
    challenge,
    state,
  });

  const exchange = async (code: string): Promise<SkilzVoltOAuthTokens> => {
    const tokens = await exchangeSkilzVoltAuthorizationCode({
      tokenEndpoint: ctx.authServer.tokenEndpoint,
      clientId: ctx.clientId,
      code,
      verifier,
      fetchImpl: ctx.fetchImpl,
    });
    if (!tokens.refresh) {
      throw new SkilzVoltOAuthError(
        "SkilzVolt did not return a refresh token. Try again and approve offline/persistent access if prompted.",
        "token_exchange",
      );
    }
    return tokens;
  };

  const manualFallback = async (): Promise<SkilzVoltOAuthTokens> => {
    ctx.log(`\nOpen this URL in your browser to connect SkilzVolt:\n\n${authUrl}\n`);
    const input = await ctx.prompt("Paste the redirect URL here: ");
    const parsed = parseCallbackInput(input, state);
    if ("error" in parsed) {
      throw new SkilzVoltOAuthError(parsed.error, "authorization");
    }
    ctx.progress?.update("Exchanging authorization code for tokens…");
    return exchange(parsed.code);
  };

  if (ctx.isRemote) {
    await ctx.note?.(
      [
        "You are running in a remote environment.",
        "A URL will be shown for you to open in your LOCAL browser.",
        "After signing in, copy the redirect URL and paste it back here.",
      ].join("\n"),
      "SkilzVolt OAuth",
    );
    return manualFallback();
  }

  ctx.progress?.update("Complete sign-in in your browser…");
  try {
    await ctx.openUrl(authUrl);
  } catch {
    ctx.log(`\nOpen this URL in your browser:\n\n${authUrl}\n`);
  }

  try {
    const { code } = await waitForLocalCallback({
      expectedState: state,
      timeoutMs: 5 * 60 * 1000,
      onProgress: (msg) => ctx.progress?.update(msg),
    });
    ctx.progress?.update("Exchanging authorization code for tokens…");
    return await exchange(code);
  } catch {
    ctx.progress?.update("Local callback unavailable. Switching to manual entry…");
    return manualFallback();
  }
}
