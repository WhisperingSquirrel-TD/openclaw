import { createHash } from "node:crypto";

const storedSoulHashes = new Map<string, string>();

export function computeSoulHash(content: string): string {
  return createHash("sha256").update(content, "utf-8").digest("hex");
}

function normalizeKey(workspaceDir?: string): string {
  return workspaceDir?.trim() || "__default__";
}

export function storeSoulHash(hash: string, workspaceDir?: string): void {
  storedSoulHashes.set(normalizeKey(workspaceDir), hash);
}

export function getStoredSoulHash(workspaceDir?: string): string | null {
  return storedSoulHashes.get(normalizeKey(workspaceDir)) ?? null;
}

export function clearStoredSoulHash(workspaceDir?: string): void {
  if (workspaceDir === undefined) {
    storedSoulHashes.clear();
  } else {
    storedSoulHashes.delete(normalizeKey(workspaceDir));
  }
}

export type SoulIntegrityResult =
  | { ok: true }
  | { ok: false; expected: string; actual: string };

export function verifySoulIntegrity(content: string, workspaceDir?: string): SoulIntegrityResult {
  const key = normalizeKey(workspaceDir);
  const stored = storedSoulHashes.get(key) ?? null;
  if (stored === null) {
    const hash = computeSoulHash(content);
    storedSoulHashes.set(key, hash);
    return { ok: true };
  }
  const currentHash = computeSoulHash(content);
  if (currentHash === stored) {
    return { ok: true };
  }
  return { ok: false, expected: stored, actual: currentHash };
}
