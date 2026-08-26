import { SkilzVoltOAuthError, type SkilzVoltOAuthErrorKind } from "./errors.js";

export type SkilzVoltAuthServerMetadata = {
  issuer: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  registrationEndpoint?: string;
};

export type FetchLike = typeof fetch;

const DEFAULT_TIMEOUT_MS = 10_000;

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

async function fetchJson(
  url: string,
  fetchImpl: FetchLike,
  timeoutMs: number,
  kind: SkilzVoltOAuthErrorKind,
): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    let response: Response;
    try {
      response = await fetchImpl(url, {
        headers: { accept: "application/json" },
        signal: controller.signal,
      });
    } catch (error) {
      if (controller.signal.aborted) {
        throw new SkilzVoltOAuthError(`Timed out fetching ${url}`, "timeout");
      }
      throw new SkilzVoltOAuthError(
        `Network error fetching ${url}: ${error instanceof Error ? error.message : String(error)}`,
        "network",
      );
    }
    if (!response.ok) {
      throw new SkilzVoltOAuthError(`${url} returned HTTP ${response.status}`, kind);
    }
    const data = await response.json().catch(() => null);
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new SkilzVoltOAuthError(`${url} returned a non-JSON-object response`, kind);
    }
    return data as Record<string, unknown>;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Discovers SkilzVolt's OAuth authorization server per RFC 8414 / RFC 9728:
 * resource metadata at the resource origin points to the authorization server(s),
 * whose own metadata document supplies the endpoints we need. This intentionally
 * never hardcodes SkilzVolt's authorization server so a future rotation on their
 * side does not require a code change here.
 */
export async function discoverSkilzVoltAuthorizationServer(params: {
  resourceUrl: string;
  fetchImpl?: FetchLike;
  timeoutMs?: number;
}): Promise<SkilzVoltAuthServerMetadata> {
  const fetchImpl = params.fetchImpl ?? fetch;
  const timeoutMs = params.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const resource = new URL(params.resourceUrl);
  const resourceOrigin = resource.origin;
  // RFC 9728 §3.1: for a resource with a non-root path, the well-known URI is formed by
  // inserting the well-known segment BEFORE that path (e.g. https://host/mcp ->
  // https://host/.well-known/oauth-protected-resource/mcp) - not at the bare origin root.
  const resourcePath = resource.pathname.replace(/\/+$/, "");
  const protectedResourceUrl = `${resourceOrigin}/.well-known/oauth-protected-resource${resourcePath}`;

  const resourceMetadata = await fetchJson(protectedResourceUrl, fetchImpl, timeoutMs, "discovery");
  const authServers = Array.isArray(resourceMetadata.authorization_servers)
    ? resourceMetadata.authorization_servers.filter(
        (entry): entry is string => typeof entry === "string" && entry.trim().length > 0,
      )
    : [];
  const authServerUrl = new URL(authServers[0] ?? resourceOrigin);
  const authServerOrigin = authServerUrl.origin;
  const authServerPath = authServerUrl.pathname.replace(/\/+$/, "");

  let asMetadata: Record<string, unknown>;
  try {
    // RFC 8414 §3.1: for an issuer with a path component, the well-known segment is inserted
    // BEFORE that path (like RFC 9728's protected-resource metadata), not appended after it.
    asMetadata = await fetchJson(
      `${authServerOrigin}/.well-known/oauth-authorization-server${authServerPath}`,
      fetchImpl,
      timeoutMs,
      "discovery",
    );
  } catch {
    // OpenID Connect Discovery 1.0 uses the opposite convention: the well-known suffix is
    // appended AFTER the issuer's path, not inserted before it.
    asMetadata = await fetchJson(
      `${authServerOrigin}${authServerPath}/.well-known/openid-configuration`,
      fetchImpl,
      timeoutMs,
      "discovery",
    );
  }

  const authorizationEndpoint = asString(asMetadata.authorization_endpoint);
  const tokenEndpoint = asString(asMetadata.token_endpoint);
  if (!authorizationEndpoint || !tokenEndpoint) {
    throw new SkilzVoltOAuthError(
      "SkilzVolt's authorization server metadata is missing authorization_endpoint or token_endpoint",
      "discovery",
    );
  }

  return {
    issuer: asString(asMetadata.issuer) ?? authServerOrigin,
    authorizationEndpoint,
    tokenEndpoint,
    registrationEndpoint: asString(asMetadata.registration_endpoint),
  };
}
