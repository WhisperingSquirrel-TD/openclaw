import { describe, expect, it } from "vitest";
import { ConnectErrorDetailCodes } from "./protocol/connect-error-details.js";
import { resolveGatewayErrorDetailCode } from "../../ui/src/ui/gateway.ts";

describe("gateway reconnect error details", () => {
  it("preserves structured authentication errors for reconnect handling", () => {
    expect(
      resolveGatewayErrorDetailCode({
        details: { code: ConnectErrorDetailCodes.AUTH_TOKEN_MISSING },
      }),
    ).toBe(ConnectErrorDetailCodes.AUTH_TOKEN_MISSING);
    expect(
      resolveGatewayErrorDetailCode({
        details: { code: ConnectErrorDetailCodes.AUTH_TOKEN_MISMATCH },
      }),
    ).toBe(ConnectErrorDetailCodes.AUTH_TOKEN_MISMATCH);
  });

  it("does not treat unstructured disconnect errors as authentication details", () => {
    expect(resolveGatewayErrorDetailCode(undefined)).toBeNull();
    expect(resolveGatewayErrorDetailCode({ details: { code: " " } })).toBeNull();
    expect(resolveGatewayErrorDetailCode({ details: "connection reset" })).toBeNull();
  });
});
