import type { Command } from "commander";
import { isRemoteEnvironment } from "../commands/oauth-env.js";
import { openUrl } from "../commands/onboard-helpers.js";
import {
  getSkilzVoltStatus,
  loginSkilzVolt,
  logoutSkilzVolt,
} from "../integrations/skilzvolt/connection.js";
import { pollSkilzVoltUserCount } from "../integrations/skilzvolt/user-count.js";
import { defaultRuntime } from "../runtime.js";
import { createClackPrompter } from "../wizard/clack-prompter.js";
import { runCommandWithRuntime } from "./cli-utils.js";

const DEFAULT_CONNECTION_KEY_ENV = "SKILZVOLT_CONNECTION_KEY";

// SkilzVolt is a single owner-level connection, not scoped to whichever agent happens to invoke
// it. Every caller here (this CLI and the extension's token getter) intentionally omits
// `agentDir` so both resolve the exact same credential-store path via the shared
// `resolveOpenClawAgentDir()` default inside ensureAuthProfileStore/resolveAuthStorePath -
// a mismatch there would let login "succeed" while the extension reads a different, empty store.

export function registerSkilzVoltCli(program: Command) {
  const skilzvolt = program
    .command("skilzvolt")
    .description("Connect OpenClaw to SkilzVolt via OAuth");

  skilzvolt
    .command("login")
    .description("Connect SkilzVolt using a browser-based OAuth sign-in (no keys to paste)")
    .action(async () => {
      await runCommandWithRuntime(defaultRuntime, async () => {
        const prompter = createClackPrompter();
        await prompter.intro("SkilzVolt OAuth");
        const progress = prompter.progress("Discovering SkilzVolt's OAuth server…");
        try {
          await loginSkilzVolt({
            isRemote: isRemoteEnvironment(),
            openUrl,
            prompt: (message) => prompter.text({ message }),
            log: (message) => defaultRuntime.log(message),
            note: prompter.note,
            progress,
          });
          progress.stop("SkilzVolt connected.");
          await prompter.outro("Run `openclaw skilzvolt status` any time to check the connection.");
        } catch (error) {
          progress.stop("SkilzVolt connection failed.");
          throw error;
        }
      });
    });

  skilzvolt
    .command("status")
    .description("Show whether SkilzVolt is connected (never prints the credential itself)")
    .action(async () => {
      await runCommandWithRuntime(defaultRuntime, async () => {
        const status = getSkilzVoltStatus({
          connectionKeyEnv: DEFAULT_CONNECTION_KEY_ENV,
        });
        if (status.connected && status.mode === "oauth") {
          defaultRuntime.log(
            `SkilzVolt: connected via OAuth (token refreshes automatically; current token valid until ${new Date(status.expiresAt).toISOString()}).`,
          );
          return;
        }
        if (status.connected && status.mode === "env") {
          defaultRuntime.log(
            `SkilzVolt: connected via the ${DEFAULT_CONNECTION_KEY_ENV} fallback bearer key (not OAuth).`,
          );
          return;
        }
        defaultRuntime.log(`SkilzVolt: not connected — ${status.reason}`);
        defaultRuntime.log("Run `openclaw skilzvolt login` to connect.");
      });
    });

  skilzvolt
    .command("logout")
    .description("Remove the stored SkilzVolt OAuth session")
    .action(async () => {
      await runCommandWithRuntime(defaultRuntime, async () => {
        const cleared = logoutSkilzVolt();
        defaultRuntime.log(
          cleared ? "SkilzVolt OAuth session removed." : "No SkilzVolt OAuth session was stored.",
        );
      });
    });

  skilzvolt
    .command("user-count")
    .description("Poll and acknowledge aggregate SkilzVolt user counts")
    .option("--json", "Output machine-readable JSON", false)
    .action(async (options: { json?: boolean }) => {
      await runCommandWithRuntime(defaultRuntime, async () => {
        const result = await pollSkilzVoltUserCount();
        if (options.json) {
          defaultRuntime.log(JSON.stringify(result));
        } else if (result.ok) {
          defaultRuntime.log(
            [
              `SkilzVolt user count: ${result.total} total registered users`,
              `New signups since last acknowledged check: ${result.sinceLast}`,
              `Acknowledgement succeeded: yes`,
              `Check time (Europe/London): ${result.checkedAtEuropeLondon}`,
            ].join("\n"),
          );
        } else {
          defaultRuntime.error(`SkilzVolt user count unavailable: ${result.message}`);
        }
        if (!result.ok) {
          defaultRuntime.exit(1);
        }
      });
    });
}
