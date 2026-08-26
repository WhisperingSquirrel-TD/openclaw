import {
  ensureAuthProfileStore,
  saveAuthProfileStore,
  upsertAuthProfile,
} from "../../agents/auth-profiles.js";
import type { OAuthCredential } from "../../agents/auth-profiles/types.js";

/**
 * SkilzVolt is not an LLM model provider, but it reuses OpenClaw's existing encrypted-at-rest,
 * lock-safe auth-profile store rather than inventing a second credential file. The extension
 * never touches this module directly; only core (src/integrations/skilzvolt) reads or writes it.
 */
export const SKILZVOLT_PROVIDER_ID = "skilzvolt";
export const SKILZVOLT_PROFILE_ID = "skilzvolt:default";

export function readSkilzVoltCredential(agentDir?: string): OAuthCredential | undefined {
  const store = ensureAuthProfileStore(agentDir);
  const credential = store.profiles[SKILZVOLT_PROFILE_ID];
  if (!credential || credential.type !== "oauth" || credential.provider !== SKILZVOLT_PROVIDER_ID) {
    return undefined;
  }
  return credential;
}

export function saveSkilzVoltCredential(
  tokens: { access: string; refresh: string; expires: number; clientId: string },
  agentDir?: string,
): void {
  upsertAuthProfile({
    profileId: SKILZVOLT_PROFILE_ID,
    agentDir,
    credential: {
      type: "oauth",
      provider: SKILZVOLT_PROVIDER_ID,
      access: tokens.access,
      refresh: tokens.refresh,
      expires: tokens.expires,
      clientId: tokens.clientId,
    },
  });
}

export function clearSkilzVoltCredential(agentDir?: string): boolean {
  const store = ensureAuthProfileStore(agentDir);
  if (!store.profiles[SKILZVOLT_PROFILE_ID]) {
    return false;
  }
  delete store.profiles[SKILZVOLT_PROFILE_ID];
  saveAuthProfileStore(store, agentDir);
  return true;
}
