import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { listBlueBubblesAccountIds, resolveBlueBubblesAccount } from "./src/accounts.js";
import { bluebubblesPlugin } from "./src/channel.js";
import { handleBlueBubblesWebhookRequest } from "./src/monitor.js";
import { resolveWebhookPathFromConfig } from "./src/monitor-shared.js";
import { setBlueBubblesRuntime } from "./src/runtime.js";

const plugin = {
  id: "bluebubbles",
  name: "BlueBubbles",
  description: "BlueBubbles channel plugin (macOS app)",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setBlueBubblesRuntime(api.runtime);
    api.registerChannel({ plugin: bluebubblesPlugin });
    // BlueBubbles validates its per-account GUID/password in the handler.
    // Register every configured exact path so custom account paths remain reachable.
    const paths = new Set(
      listBlueBubblesAccountIds(api.config).map((accountId) =>
        resolveWebhookPathFromConfig(resolveBlueBubblesAccount({ cfg: api.config, accountId }).config),
      ),
    );
    for (const path of paths) {
      api.registerHttpRoute({
        path,
        auth: "plugin",
        match: "exact",
        handler: handleBlueBubblesWebhookRequest,
      });
    }
  },
};

export default plugin;
