import fs from "node:fs";
import path from "node:path";
import { resolveOAuthDir } from "../../config/paths.js";
import { logInfo } from "../../logger.js";
import { logVerbose } from "../../globals.js";

const TASKS_SCOPE = "https://www.googleapis.com/auth/tasks";
const DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const TASKS_API_BASE = "https://tasks.googleapis.com/tasks/v1";

export type GoogleTasksStatus = "no-credentials" | "no-token" | "ready";

type GoogleCredentials = {
  clientId: string;
  clientSecret: string;
};

type GoogleToken = {
  access_token: string;
  refresh_token: string;
  expires_at: number;
};

type DeviceCodeResponse = {
  device_code: string;
  user_code: string;
  verification_url: string;
  expires_in: number;
  interval: number;
};

function resolveGoogleDir(): string {
  return path.join(resolveOAuthDir(), "google");
}

function resolveCredentialsPath(): string {
  return path.join(resolveGoogleDir(), "credentials.json");
}

function resolveTokenPath(): string {
  return path.join(resolveGoogleDir(), "tasks-token.json");
}

export function readGoogleCredentials(): GoogleCredentials | null {
  try {
    const credPath = resolveCredentialsPath();
    if (!fs.existsSync(credPath)) return null;
    const raw = JSON.parse(fs.readFileSync(credPath, "utf-8")) as Record<string, unknown>;
    const clientId = typeof raw.clientId === "string" ? raw.clientId.trim() : "";
    const clientSecret = typeof raw.clientSecret === "string" ? raw.clientSecret.trim() : "";
    if (!clientId || !clientSecret || clientId.startsWith("YOUR_")) return null;
    return { clientId, clientSecret };
  } catch {
    return null;
  }
}

function readToken(): GoogleToken | null {
  try {
    const tokenPath = resolveTokenPath();
    if (!fs.existsSync(tokenPath)) return null;
    return JSON.parse(fs.readFileSync(tokenPath, "utf-8")) as GoogleToken;
  } catch {
    return null;
  }
}

function writeToken(token: GoogleToken): void {
  const tokenPath = resolveTokenPath();
  fs.mkdirSync(path.dirname(tokenPath), { recursive: true });
  fs.writeFileSync(tokenPath, JSON.stringify(token, null, 2), "utf-8");
}

export function getGoogleTasksStatus(): GoogleTasksStatus {
  if (!readGoogleCredentials()) return "no-credentials";
  if (!readToken()) return "no-token";
  return "ready";
}

export function getCredentialsPath(): string {
  return resolveCredentialsPath();
}

async function refreshAccessToken(
  creds: GoogleCredentials,
  token: GoogleToken,
): Promise<GoogleToken> {
  const resp = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: creds.clientId,
      client_secret: creds.clientSecret,
      refresh_token: token.refresh_token,
      grant_type: "refresh_token",
    }),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Token refresh failed: ${resp.status} ${err}`);
  }
  const data = (await resp.json()) as { access_token: string; expires_in?: number };
  const newToken: GoogleToken = {
    access_token: data.access_token,
    refresh_token: token.refresh_token,
    expires_at: Date.now() + ((data.expires_in ?? 3600) - 60) * 1000,
  };
  writeToken(newToken);
  return newToken;
}

async function getValidAccessToken(creds: GoogleCredentials): Promise<string> {
  let token = readToken();
  if (!token) throw new Error("No Google token stored");
  if (Date.now() >= token.expires_at) {
    token = await refreshAccessToken(creds, token);
  }
  return token.access_token;
}

export async function startDeviceFlow(creds: GoogleCredentials): Promise<DeviceCodeResponse> {
  const resp = await fetch(DEVICE_CODE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: creds.clientId,
      scope: TASKS_SCOPE,
    }),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Device code request failed: ${resp.status} ${err}`);
  }
  return resp.json() as Promise<DeviceCodeResponse>;
}

/**
 * Polls Google until the user grants access (or times out / denies).
 * Returns the stored token on success, or null on denial/timeout.
 * Runs asynchronously — call without await to avoid blocking.
 */
export async function pollUntilAuthorized(
  creds: GoogleCredentials,
  deviceCode: string,
  intervalSeconds: number,
  expiresIn: number,
  onSuccess: (token: GoogleToken) => void,
  onFailure: (reason: "denied" | "expired") => void,
): Promise<void> {
  const pollMs = Math.max(intervalSeconds, 5) * 1000;
  const deadline = Date.now() + expiresIn * 1000;

  while (Date.now() < deadline) {
    await new Promise<void>((r) => setTimeout(r, pollMs));

    try {
      const resp = await fetch(TOKEN_URL, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          client_id: creds.clientId,
          client_secret: creds.clientSecret,
          device_code: deviceCode,
          grant_type: "urn:ietf:params:oauth:grant-type:device_code",
        }),
      });

      const data = (await resp.json()) as {
        access_token?: string;
        refresh_token?: string;
        expires_in?: number;
        error?: string;
      };

      if (data.access_token && data.refresh_token) {
        const token: GoogleToken = {
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          expires_at: Date.now() + ((data.expires_in ?? 3600) - 60) * 1000,
        };
        writeToken(token);
        logInfo("watch-action-google-tasks: device flow authorized, token stored");
        onSuccess(token);
        return;
      }

      if (data.error === "access_denied") {
        logInfo("watch-action-google-tasks: user denied Google access");
        onFailure("denied");
        return;
      }

      if (data.error === "slow_down") {
        await new Promise<void>((r) => setTimeout(r, 5000));
      }

      logVerbose(`watch-action-google-tasks: polling... error=${data.error ?? "authorization_pending"}`);
    } catch (err) {
      logVerbose(`watch-action-google-tasks: poll error: ${String(err)}`);
    }
  }

  logInfo("watch-action-google-tasks: device flow timed out");
  onFailure("expired");
}

async function findOrCreateShoppingList(accessToken: string): Promise<string> {
  const resp = await fetch(`${TASKS_API_BASE}/users/@me/lists`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!resp.ok) throw new Error(`Failed to list task lists: ${resp.status}`);

  const data = (await resp.json()) as {
    items?: Array<{ id: string; title: string }>;
  };
  const items = data.items ?? [];

  const existing = items.find((l) => l.title.toLowerCase() === "shopping");
  if (existing) return existing.id;

  const createResp = await fetch(`${TASKS_API_BASE}/users/@me/lists`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title: "Shopping" }),
  });
  if (!createResp.ok) throw new Error(`Failed to create Shopping list: ${createResp.status}`);

  const created = (await createResp.json()) as { id: string };
  logInfo("watch-action-google-tasks: created Shopping task list");
  return created.id;
}

async function addToGoogleTasksList(
  listId: string,
  accessToken: string,
  title: string,
  notes?: string,
): Promise<void> {
  const resp = await fetch(`${TASKS_API_BASE}/lists/${listId}/tasks`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title, notes: notes ?? "" }),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Failed to add task: ${resp.status} ${err}`);
  }
}

export async function addShoppingItem(summary: string, notes?: string): Promise<void> {
  const creds = readGoogleCredentials();
  if (!creds) throw new Error("No Google credentials configured");

  const accessToken = await getValidAccessToken(creds);
  const listId = await findOrCreateShoppingList(accessToken);
  await addToGoogleTasksList(listId, accessToken, summary, notes);
  logInfo(`watch-action-google-tasks: added "${summary}" to Shopping list`);
}

export async function addTaskItem(summary: string, notes?: string): Promise<void> {
  const creds = readGoogleCredentials();
  if (!creds) throw new Error("No Google credentials configured");

  const accessToken = await getValidAccessToken(creds);

  const listResp = await fetch(`${TASKS_API_BASE}/users/@me/lists`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!listResp.ok) throw new Error(`Failed to list task lists: ${listResp.status}`);

  const data = (await listResp.json()) as {
    items?: Array<{ id: string; title: string }>;
  };
  const defaultList = data.items?.[0];
  if (!defaultList) throw new Error("No task lists found");

  await addToGoogleTasksList(defaultList.id, accessToken, summary, notes);
  logInfo(`watch-action-google-tasks: added task "${summary}" to default list`);
}
