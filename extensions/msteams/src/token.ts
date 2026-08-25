import { normalizeResolvedSecretInputString, type MSTeamsConfig } from "openclaw/plugin-sdk";

export type MSTeamsCredentials = {
  appId: string;
  appPassword: string;
  tenantId: string;
};

export function resolveMSTeamsCredentials(cfg?: MSTeamsConfig): MSTeamsCredentials | undefined {
  const appId =
    normalizeResolvedSecretInputString({ value: cfg?.appId, path: "channels.msteams.appId" }) ||
    process.env.MSTEAMS_APP_ID?.trim();
  const appPassword =
    normalizeResolvedSecretInputString({
      value: cfg?.appPassword,
      path: "channels.msteams.appPassword",
    }) || process.env.MSTEAMS_APP_PASSWORD?.trim();
  const tenantId =
    normalizeResolvedSecretInputString({
      value: cfg?.tenantId,
      path: "channels.msteams.tenantId",
    }) || process.env.MSTEAMS_TENANT_ID?.trim();

  if (!appId || !appPassword || !tenantId) {
    return undefined;
  }

  return { appId, appPassword, tenantId };
}
