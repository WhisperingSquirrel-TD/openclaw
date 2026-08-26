import { describe, expect, it, vi } from "vitest";
import { createSkilzVoltAccessTokenGetter, getSkilzVoltStatus } from "./connection.js";
import { clearSkilzVoltCredential, saveSkilzVoltCredential } from "./credential-store.js";

const ENV_KEY = "TEST_SKILZVOLT_CONNECTION_KEY";

describe("getSkilzVoltStatus", () => {
  it("reports not connected when neither OAuth nor env fallback is present", () => {
    delete process.env[ENV_KEY];
    clearSkilzVoltCredential();
    expect(getSkilzVoltStatus({ connectionKeyEnv: ENV_KEY }).connected).toBe(false);
  });

  it("reports the env fallback mode when only the legacy key is set", () => {
    clearSkilzVoltCredential();
    process.env[ENV_KEY] = "legacy-key";
    try {
      expect(getSkilzVoltStatus({ connectionKeyEnv: ENV_KEY })).toEqual({
        connected: true,
        mode: "env",
      });
    } finally {
      delete process.env[ENV_KEY];
    }
  });

  it("reports OAuth mode when a credential is stored", () => {
    clearSkilzVoltCredential();
    const expires = Date.now() + 60_000;
    saveSkilzVoltCredential({ access: "a", refresh: "r", expires, clientId: "c" });
    try {
      expect(getSkilzVoltStatus({ connectionKeyEnv: ENV_KEY })).toEqual({
        connected: true,
        mode: "oauth",
        expiresAt: expires,
      });
    } finally {
      clearSkilzVoltCredential();
    }
  });
});

describe("createSkilzVoltAccessTokenGetter", () => {
  it("returns a live OAuth access token without refreshing when not near expiry", async () => {
    clearSkilzVoltCredential();
    saveSkilzVoltCredential({
      access: "fresh-access",
      refresh: "refresh-1",
      expires: Date.now() + 10 * 60_000,
      clientId: "client-1",
    });
    try {
      const getToken = createSkilzVoltAccessTokenGetter({ connectionKeyEnv: ENV_KEY });
      await expect(getToken()).resolves.toBe("fresh-access");
    } finally {
      clearSkilzVoltCredential();
    }
  });

  it("falls back to the legacy env var when there is no OAuth session", async () => {
    clearSkilzVoltCredential();
    process.env[ENV_KEY] = "legacy-fallback";
    try {
      const getToken = createSkilzVoltAccessTokenGetter({ connectionKeyEnv: ENV_KEY });
      await expect(getToken()).resolves.toBe("legacy-fallback");
    } finally {
      delete process.env[ENV_KEY];
    }
  });

  it("falls back to the env var and reports the error when refresh fails", async () => {
    clearSkilzVoltCredential();
    saveSkilzVoltCredential({
      access: "expired-access",
      refresh: "refresh-1",
      expires: Date.now() - 1000,
      clientId: "client-1",
    });
    process.env[ENV_KEY] = "legacy-fallback";
    const onRefreshError = vi.fn();
    try {
      const getToken = createSkilzVoltAccessTokenGetter({
        connectionKeyEnv: ENV_KEY,
        onRefreshError,
        fetchImpl: vi.fn(async () => {
          throw new Error("network down");
        }) as unknown as typeof fetch,
      });
      await expect(getToken()).resolves.toBe("legacy-fallback");
      expect(onRefreshError).toHaveBeenCalledTimes(1);
    } finally {
      delete process.env[ENV_KEY];
      clearSkilzVoltCredential();
    }
  });
});
