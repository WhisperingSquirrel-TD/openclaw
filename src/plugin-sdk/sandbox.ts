// Fork note: upstream's plugin-sdk sandbox surface also re-exports the SSH /
// sandbox-backend-factory API (requireSandboxBackendFactory, runSshSandboxCommand,
// shellEscape, uploadDirectoryToSshTarget, SshSandboxSession types, etc.).
// Our src/agents/sandbox.ts predates that API, so those re-exports produced
// hundreds of MISSING_EXPORT build warnings on every install. Nothing in core
// or extensions/ consumes them, so they are trimmed here until an upstream
// sync brings the backend API into src/agents/sandbox — restore the full
// export list from upstream at that point.
export type { SandboxContext } from "../agents/sandbox.js";
export type { OpenClawConfig } from "../config/config.js";

export {
  runPluginCommandWithTimeout,
  type PluginCommandRunOptions,
  type PluginCommandRunResult,
} from "./run-command.js";
export { resolvePreferredOpenClawTmpDir } from "../infra/tmp-openclaw-dir.js";
