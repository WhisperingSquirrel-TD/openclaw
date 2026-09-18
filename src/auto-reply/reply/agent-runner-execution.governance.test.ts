import { describe, expect, it, vi } from "vitest";
import {
  clearGovernedRun,
  registerGovernedRun,
} from "../../agents/pi-embedded-runner/run/governance-registry.js";
import { emitToolLifecycleStatus } from "./agent-runner-execution.js";

describe("governed tool lifecycle status", () => {
  it("suppresses governed start/update status but preserves ordinary status", async () => {
    const signalToolStart = vi.fn(async () => {});
    const onToolStart = vi.fn(async () => {});
    registerGovernedRun("run-governed-status", "learning");
    await emitToolLifecycleStatus({
      runId: "run-governed-status",
      phase: "start",
      name: "message",
      signalToolStart,
      onToolStart,
    });
    await emitToolLifecycleStatus({
      runId: "run-governed-status",
      phase: "update",
      name: "message",
      signalToolStart,
      onToolStart,
    });
    expect(signalToolStart).not.toHaveBeenCalled();
    expect(onToolStart).not.toHaveBeenCalled();
    clearGovernedRun("run-governed-status");

    await emitToolLifecycleStatus({
      runId: "run-ordinary-status",
      phase: "start",
      name: "message",
      signalToolStart,
      onToolStart,
    });
    await emitToolLifecycleStatus({
      runId: "run-ordinary-status",
      phase: "update",
      name: "message",
      signalToolStart,
      onToolStart,
    });
    expect(signalToolStart).toHaveBeenCalledTimes(2);
    expect(onToolStart).toHaveBeenCalledTimes(2);
  });
});
