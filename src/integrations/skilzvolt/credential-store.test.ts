import { describe, expect, it } from "vitest";
import {
  clearSkilzVoltCredential,
  readSkilzVoltCredential,
  saveSkilzVoltCredential,
} from "./credential-store.js";

describe("SkilzVolt credential store", () => {
  it("round-trips an OAuth credential through the shared auth-profile store", () => {
    expect(readSkilzVoltCredential()).toBeUndefined();

    saveSkilzVoltCredential({
      access: "access-1",
      refresh: "refresh-1",
      expires: Date.now() + 60_000,
      clientId: "client-1",
    });

    const credential = readSkilzVoltCredential();
    expect(credential).toMatchObject({
      type: "oauth",
      provider: "skilzvolt",
      access: "access-1",
      refresh: "refresh-1",
      clientId: "client-1",
    });

    expect(clearSkilzVoltCredential()).toBe(true);
    expect(readSkilzVoltCredential()).toBeUndefined();
    expect(clearSkilzVoltCredential()).toBe(false);
  });
});
