import type { FetchLike } from "./discovery.js";
import { SkilzVoltOAuthError } from "./errors.js";

/**
 * Registers a public (no client secret) native-app OAuth client with SkilzVolt's authorization
 * server per RFC 7591, so OpenClaw never ships or asks a person for a pre-shared client id.
 */
export async function registerSkilzVoltOAuthClient(params: {
  registrationEndpoint: string;
  redirectUri: string;
  fetchImpl?: FetchLike;
  timeoutMs?: number;
}): Promise<{ clientId: string }> {
  const fetchImpl = params.fetchImpl ?? fetch;
  const timeoutMs = params.timeoutMs ?? 10_000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    try {
      response = await fetchImpl(params.registrationEndpoint, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json" },
        body: JSON.stringify({
          client_name: "OpenClaw",
          redirect_uris: [params.redirectUri],
          grant_types: ["authorization_code", "refresh_token"],
          response_types: ["code"],
          token_endpoint_auth_method: "none",
          application_type: "native",
        }),
        signal: controller.signal,
      });
    } catch (error) {
      if (controller.signal.aborted) {
        throw new SkilzVoltOAuthError(
          "Timed out registering an OAuth client with SkilzVolt",
          "timeout",
        );
      }
      throw new SkilzVoltOAuthError(
        `Network error registering an OAuth client with SkilzVolt: ${error instanceof Error ? error.message : String(error)}`,
        "network",
      );
    }
  } finally {
    clearTimeout(timer);
  }

  const text = await response.text();
  if (!response.ok) {
    throw new SkilzVoltOAuthError(
      `SkilzVolt dynamic client registration returned HTTP ${response.status}`,
      "registration",
    );
  }
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(text) as Record<string, unknown>;
  } catch {
    throw new SkilzVoltOAuthError(
      "SkilzVolt dynamic client registration returned a non-JSON response",
      "registration",
    );
  }
  const clientId = typeof data.client_id === "string" ? data.client_id.trim() : "";
  if (!clientId) {
    throw new SkilzVoltOAuthError(
      "SkilzVolt dynamic client registration did not return a client_id",
      "registration",
    );
  }
  return { clientId };
}
