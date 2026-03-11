import fs from "node:fs";
import path from "node:path";
import { resolveOAuthDir } from "../../config/paths.js";
import { logVerbose } from "../../globals.js";

export type ActionType = "shopping" | "calendar" | "task" | "reminder" | "urgent" | "other";

export type DetectedAction = {
  id: string;
  actionType: ActionType;
  summary: string;
  originalMessage: string;
  senderName?: string;
  chatName?: string;
  timestamp: string;
  resolved: boolean;
  resolvedAt?: string;
  resolvedAction?: string;
};

function resolveActionStorePath(): string {
  const dir = path.join(resolveOAuthDir(), "whatsapp", "watch-actions");
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, "pending-actions.json");
}

function readActionStore(): Map<string, DetectedAction> {
  const storePath = resolveActionStorePath();
  try {
    const raw = fs.readFileSync(storePath, "utf-8");
    const entries: DetectedAction[] = JSON.parse(raw);
    const map = new Map<string, DetectedAction>();
    for (const entry of entries) {
      map.set(entry.id, entry);
    }
    return map;
  } catch {
    return new Map();
  }
}

function writeActionStore(store: Map<string, DetectedAction>): void {
  const storePath = resolveActionStorePath();
  try {
    const entries = Array.from(store.values());
    fs.writeFileSync(storePath, JSON.stringify(entries, null, 2), "utf-8");
  } catch (err) {
    logVerbose(`Watch action store write failed: ${String(err)}`);
  }
}

export function generateActionId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 6);
  return `wa_${ts}_${rand}`;
}

export function storeAction(action: DetectedAction): void {
  const store = readActionStore();
  store.set(action.id, action);
  writeActionStore(store);
}

export function getAction(id: string): DetectedAction | undefined {
  return readActionStore().get(id);
}

export function resolveAction(id: string, resolvedAction: string): DetectedAction | undefined {
  const store = readActionStore();
  const action = store.get(id);
  if (!action) return undefined;
  action.resolved = true;
  action.resolvedAt = new Date().toISOString();
  action.resolvedAction = resolvedAction;
  store.set(id, action);
  writeActionStore(store);
  return action;
}

export function getPendingActions(): DetectedAction[] {
  const store = readActionStore();
  return Array.from(store.values()).filter((a) => !a.resolved);
}

export function cleanupOldActions(maxAgeDays: number = 7): void {
  const store = readActionStore();
  const cutoff = Date.now() - maxAgeDays * 24 * 60 * 60 * 1000;
  for (const [id, action] of store) {
    const actionTime = new Date(action.timestamp).getTime();
    if (actionTime < cutoff && action.resolved) {
      store.delete(id);
    }
  }
  writeActionStore(store);
}
