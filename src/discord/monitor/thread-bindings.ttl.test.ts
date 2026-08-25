import { describe, expect, it } from "vitest";
import {
  resolveThreadBindingInactivityExpiresAt,
  resolveThreadBindingIntroText,
  resolveThreadBindingMaxAgeExpiresAt,
} from "./thread-bindings.js";

describe("thread binding lifecycle windows", () => {
  it("describes idle expiry and optional maximum age", () => {
    const intro = resolveThreadBindingIntroText({
      agentId: "main",
      idleTimeoutMs: 24 * 60 * 60 * 1000,
      maxAgeMs: 48 * 60 * 60 * 1000,
    });

    expect(intro).toContain("idle auto-unfocus after 24h inactivity");
    expect(intro).toContain("max age 48h");
  });

  it("expires an idle window from the most recent activity", () => {
    expect(
      resolveThreadBindingInactivityExpiresAt({
        record: { lastActivityAt: 1_000, idleTimeoutMs: 60_000 },
        defaultIdleTimeoutMs: 0,
      }),
    ).toBe(61_000);
    expect(
      resolveThreadBindingInactivityExpiresAt({
        record: { lastActivityAt: 1_000, idleTimeoutMs: 0 },
        defaultIdleTimeoutMs: 60_000,
      }),
    ).toBeUndefined();
  });

  it("enforces maximum age from the original bind time", () => {
    expect(
      resolveThreadBindingMaxAgeExpiresAt({
        record: { boundAt: 1_000, maxAgeMs: 60_000 },
        defaultMaxAgeMs: 0,
      }),
    ).toBe(61_000);
    expect(
      resolveThreadBindingMaxAgeExpiresAt({
        record: { boundAt: 1_000, maxAgeMs: 0 },
        defaultMaxAgeMs: 60_000,
      }),
    ).toBeUndefined();
  });
});