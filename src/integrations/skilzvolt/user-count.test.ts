import { describe, expect, it, vi } from "vitest";
import { SKILZVOLT_USER_COUNT_ACK_URL, SKILZVOLT_USER_COUNT_URL } from "./config.js";
import { pollSkilzVoltUserCount, type SkilzVoltUserCountState } from "./user-count.js";

const NOW = new Date("2026-08-28T12:00:00.000Z");

function countResponse(overrides: Record<string, unknown> = {}): Response {
  return new Response(
    JSON.stringify({
      since_last: 12,
      total: 438,
      delivery_ref: "opaque-delivery-reference",
      ...overrides,
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
}

describe("pollSkilzVoltUserCount", () => {
  it("records aggregate counts before acknowledging the delivery", async () => {
    const writes: SkilzVoltUserCountState[] = [];
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(countResponse())
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const result = await pollSkilzVoltUserCount({
      getBearerToken: () => "access-token",
      fetchImpl,
      now: () => NOW,
      writeState: async (state) => {
        writes.push({ ...state });
      },
    });

    expect(result).toMatchObject({
      ok: true,
      total: 438,
      sinceLast: 12,
      acknowledgementSucceeded: true,
      checkedAt: NOW.toISOString(),
      checkedAtEuropeLondon: expect.any(String),
    });
    expect(writes).toHaveLength(2);
    expect(writes[0]).toMatchObject({
      total: 438,
      sinceLast: 12,
      acknowledgementSucceeded: false,
    });
    expect(writes[1]).toMatchObject({
      total: 438,
      sinceLast: 12,
      acknowledgementSucceeded: true,
    });
    expect(fetchImpl).toHaveBeenNthCalledWith(
      1,
      SKILZVOLT_USER_COUNT_URL,
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          authorization: "Bearer access-token",
        }),
      }),
    );
    expect(fetchImpl).toHaveBeenNthCalledWith(
      2,
      SKILZVOLT_USER_COUNT_ACK_URL,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ delivery_ref: "opaque-delivery-reference" }),
      }),
    );
  });

  it("does not acknowledge when the aggregate result cannot be recorded", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(countResponse());
    const result = await pollSkilzVoltUserCount({
      getBearerToken: () => "access-token",
      fetchImpl,
      writeState: async () => {
        throw new Error("disk full");
      },
    });

    expect(result).toMatchObject({
      ok: false,
      kind: "record",
      acknowledgementSucceeded: false,
      recorded: false,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("leaves the snapshot pending when acknowledgement fails", async () => {
    const writes: SkilzVoltUserCountState[] = [];
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(countResponse())
      .mockResolvedValueOnce(new Response(null, { status: 503 }));
    const result = await pollSkilzVoltUserCount({
      getBearerToken: () => "access-token",
      fetchImpl,
      writeState: async (state) => {
        writes.push({ ...state });
      },
    });

    expect(result).toMatchObject({
      ok: false,
      kind: "ack",
      recorded: true,
      acknowledgementSucceeded: false,
      total: 438,
      sinceLast: 12,
    });
    expect(writes).toHaveLength(1);
    expect(writes[0].acknowledgementSucceeded).toBe(false);
  });

  it("retries the same snapshot on a later poll after a failed acknowledgement", async () => {
    const writes: SkilzVoltUserCountState[] = [];
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(countResponse())
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(countResponse())
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const first = await pollSkilzVoltUserCount({
      getBearerToken: () => "access-token",
      fetchImpl,
      now: () => NOW,
      writeState: async (state) => {
        writes.push({ ...state });
      },
    });
    const second = await pollSkilzVoltUserCount({
      getBearerToken: () => "access-token",
      fetchImpl,
      now: () => NOW,
      writeState: async (state) => {
        writes.push({ ...state });
      },
    });

    expect(first).toMatchObject({ ok: false, kind: "ack" });
    expect(second).toMatchObject({ ok: true, total: 438, sinceLast: 12 });
    expect(JSON.parse(fetchImpl.mock.calls[1][1].body as string)).toEqual({
      delivery_ref: "opaque-delivery-reference",
    });
    expect(JSON.parse(fetchImpl.mock.calls[3][1].body as string)).toEqual({
      delivery_ref: "opaque-delivery-reference",
    });
  });

  it.each([401, 403])("reports HTTP %s as an existing-connection failure", async (status) => {
    const result = await pollSkilzVoltUserCount({
      getBearerToken: () => "access-token",
      fetchImpl: vi.fn().mockResolvedValue(new Response(null, { status })),
    });

    expect(result).toMatchObject({
      ok: false,
      kind: status === 401 ? "auth" : "permission",
    });
    if (result.ok) {
      throw new Error("expected a failed result");
    }
    expect(result.message).toContain("existing SkilzVolt monitoring connection");
  });

  it("rejects user-level fields and does not persist them", async () => {
    const writeState = vi.fn();
    const result = await pollSkilzVoltUserCount({
      getBearerToken: () => "access-token",
      fetchImpl: vi.fn().mockResolvedValue(countResponse({ email: "user@example.com" })),
      writeState,
    });

    expect(result).toMatchObject({ ok: false, kind: "protocol" });
    expect(writeState).not.toHaveBeenCalled();
    expect(JSON.stringify(result)).not.toContain("user@example.com");
  });

  it("reports a timed-out count request without acknowledging anything", async () => {
    const fetchImpl = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
        }),
    );
    const result = await pollSkilzVoltUserCount({
      getBearerToken: () => "access-token",
      fetchImpl: fetchImpl as unknown as typeof fetch,
      timeoutMs: 1,
    });

    expect(result).toMatchObject({ ok: false, kind: "timeout" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
