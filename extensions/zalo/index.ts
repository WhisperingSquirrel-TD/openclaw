import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { listZaloAccountIds, resolveZaloAccount } from "./src/accounts.js";
import { zaloDock, zaloPlugin } from "./src/channel.js";
import { handleZaloWebhookRequest } from "./src/monitor.js";
import { setZaloRuntime } from "./src/runtime.js";

const plugin = {
  id: "zalo",
  name: "Zalo",
  description: "Zalo channel plugin (Bot API)",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setZaloRuntime(api.runtime);
    api.registerChannel({ plugin: zaloPlugin, dock: zaloDock });
    // Zalo signs webhook requests with each account's webhook secret; keep
    // gateway auth disabled and dispatch the configured exact paths to it.
    const paths = new Set(
      listZaloAccountIds(api.config)
        .map((accountId) => resolveZaloAccount({ cfg: api.config, accountId }).config)
        .map((account) => {
          const explicit = account.webhookPath?.trim();
          if (explicit) {
            return explicit.startsWith("/") ? explicit : `/${explicit}`;
          }
          const webhookUrl = account.webhookUrl?.trim();
          if (!webhookUrl) {
            return null;
          }
          try {
            return new URL(webhookUrl).pathname || "/";
          } catch {
            return null;
          }
        })
        .filter((path): path is string => path !== null),
    );
    for (const path of paths) {
      api.registerHttpRoute({
        path,
        auth: "plugin",
        match: "exact",
        handler: handleZaloWebhookRequest,
      });
    }
  },
};

export default plugin;
