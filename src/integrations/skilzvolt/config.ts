/**
 * SkilzVolt is a single fixed third-party service (not a generic MCP server a user points
 * OpenClaw at), so these values are constants rather than user configuration. This file is the
 * single source of truth for the MCP endpoint and the OAuth callback OpenClaw listens on; the
 * extension re-exports the endpoint from here instead of duplicating the literal.
 */
export const SKILZVOLT_RESOURCE_URL = "https://app.skilzvolt.com/mcp";

export const SKILZVOLT_OAUTH_CALLBACK_HOST = "127.0.0.1";
export const SKILZVOLT_OAUTH_CALLBACK_PORT = 51823;
export const SKILZVOLT_OAUTH_CALLBACK_PATH = "/skilzvolt/oauth/callback";
export const SKILZVOLT_OAUTH_REDIRECT_URI = `http://${SKILZVOLT_OAUTH_CALLBACK_HOST}:${SKILZVOLT_OAUTH_CALLBACK_PORT}${SKILZVOLT_OAUTH_CALLBACK_PATH}`;
