import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { listGoogleChatAccountIds, resolveGoogleChatAccount } from "./src/accounts.js";
import { googlechatDock, googlechatPlugin } from "./src/channel.js";
import {
  handleGoogleChatWebhookRequest,
  resolveGoogleChatWebhookPath,
} from "./src/monitor.js";
import { setGoogleChatRuntime } from "./src/runtime.js";

const plugin = {
  id: "googlechat",
  name: "Google Chat",
  description: "OpenClaw Google Chat channel plugin",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setGoogleChatRuntime(api.runtime);
    api.registerChannel({ plugin: googlechatPlugin, dock: googlechatDock });
    // Google Chat request JWT verification is account-specific and performed by
    // the handler, so this route must bypass gateway authentication.
    const paths = new Set(
      listGoogleChatAccountIds(api.config).map((accountId) =>
        resolveGoogleChatWebhookPath({
          account: resolveGoogleChatAccount({ cfg: api.config, accountId }),
        }),
      ),
    );
    for (const path of paths) {
      api.registerHttpRoute({
        path,
        auth: "plugin",
        match: "exact",
        handler: handleGoogleChatWebhookRequest,
      });
    }
  },
};

export default plugin;
