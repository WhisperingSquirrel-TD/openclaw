import { SKILZVOLT_OAUTH_REDIRECT_URI, SKILZVOLT_RESOURCE_URL } from "./config.js";
import {
  clearSkilzVoltCredential,
  readSkilzVoltCredential,
  saveSkilzVoltCredential,
} from "./credential-store.js";
import { discoverSkilzVoltAuthorizationServer, type FetchLike } from "./discovery.js";
import { registerSkilzVoltOAuthClient } from "./dynamic-registration.js";
import { SkilzVoltOAuthError } from "./errors.js";
import {
  refreshSkilzVoltAccessToken,
  runSkilzVoltOAuthLogin,
  type SkilzVoltOAuthLoginContext,
} from "./oauth-flow.js";

/** Refresh this long before actual expiry so an in-flight MCP call never races a stale token. */
const EXPIRY_SKEW_MS = 60_000;

export type SkilzVoltConnectionStatus =
  | { connected: true; mode: "oauth"; expiresAt: number }
  | { connected: true; mode: "env" }
  | { connected: false; reason: string };

export function getSkilzVoltStatus(params: {
  connectionKeyEnv: string;
  agentDir?: string;
}): SkilzVoltConnectionStatus {
  const credential = readSkilzVoltCredential(params.agentDir);
  if (credential) {
    return { connected: true, mode: "oauth", expiresAt: credential.expires };
  }
  if (process.env[params.connectionKeyEnv]?.trim()) {
    return { connected: true, mode: "env" };
  }
  return {
    connected: false,
    reason: `No SkilzVolt OAuth session, and ${params.connectionKeyEnv} is not set.`,
  };
}

async function resolveAuthServer(fetchImpl?: FetchLike) {
  return discoverSkilzVoltAuthorizationServer({ resourceUrl: SKILZVOLT_RESOURCE_URL, fetchImpl });
}

export async function loginSkilzVolt(
  ctx: SkilzVoltOAuthLoginContext & { agentDir?: string },
): Promise<void> {
  const authServer = await resolveAuthServer(ctx.fetchImpl);
  if (!authServer.registrationEndpoint) {
    // SkilzVolt's contract requires OAuth 2.1 + PKCE support; a missing dynamic client
    // registration endpoint means we cannot obtain a client id safely (no static client id is
    // published), so this is treated as a hard discovery failure rather than a silent guess.
    throw new SkilzVoltOAuthError(
      "SkilzVolt's authorization server did not advertise a dynamic client registration endpoint (RFC 7591). Cannot connect without a person pasting a client id.",
      "registration",
    );
  }
  const { clientId } = await registerSkilzVoltOAuthClient({
    registrationEndpoint: authServer.registrationEndpoint,
    redirectUri: SKILZVOLT_OAUTH_REDIRECT_URI,
    fetchImpl: ctx.fetchImpl,
  });
  const tokens = await runSkilzVoltOAuthLogin({ ...ctx, authServer, clientId });
  saveSkilzVoltCredential({ ...tokens, clientId }, ctx.agentDir);
}

export function logoutSkilzVolt(agentDir?: string): boolean {
  return clearSkilzVoltCredential(agentDir);
}

async function ensureFreshAccessToken(params: {
  agentDir?: string;
  fetchImpl?: FetchLike;
}): Promise<string | undefined> {
  const credential = readSkilzVoltCredential(params.agentDir);
  if (!credential) {
    return undefined;
  }
  if (Date.now() < credential.expires - EXPIRY_SKEW_MS) {
    return credential.access;
  }
  if (!credential.clientId) {
    throw new SkilzVoltOAuthError(
      "Stored SkilzVolt credential is missing its OAuth client id; run the SkilzVolt login command again.",
      "refresh",
    );
  }
  const authServer = await resolveAuthServer(params.fetchImpl);
  const refreshed = await refreshSkilzVoltAccessToken({
    tokenEndpoint: authServer.tokenEndpoint,
    clientId: credential.clientId,
    refreshToken: credential.refresh,
    fetchImpl: params.fetchImpl,
  });
  saveSkilzVoltCredential(
    {
      access: refreshed.access,
      refresh: refreshed.refresh || credential.refresh,
      expires: refreshed.expires,
      clientId: credential.clientId,
    },
    params.agentDir,
  );
  return refreshed.access;
}

/**
 * Builds the opaque bearer-token getter handed to the SkilzVolt MCP transport. It never exposes
 * the OAuth client id, refresh token, or discovery details to the caller — only a live access
 * token (or undefined if genuinely not connected), so a plugin extension can authenticate
 * without ever touching core credential storage. Falls back to the legacy static bearer-key
 * env var (the manifest's explicitly documented fallback) if there is no OAuth session, or if a
 * refresh attempt fails.
 */
export function createSkilzVoltAccessTokenGetter(params: {
  connectionKeyEnv: string;
  agentDir?: string;
  fetchImpl?: FetchLike;
  onRefreshError?: (error: unknown) => void;
}): () => Promise<string | undefined> {
  return async () => {
    try {
      const token = await ensureFreshAccessToken(params);
      if (token) {
        return token;
      }
    } catch (error) {
      params.onRefreshError?.(error);
    }
    return process.env[params.connectionKeyEnv]?.trim();
  };
}
