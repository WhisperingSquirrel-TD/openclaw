import { describe, expect, it } from "vitest";
import { capSubagentCompletionResult } from "./subagent-announce.js";

describe("capSubagentCompletionResult", () => {
  it("preserves ordinary compact child results", () => {
    expect(capSubagentCompletionResult("bounded finding")).toBe("bounded finding");
  });

  it("caps an oversized completion before it can enter requester context", () => {
    const source = "x".repeat(20_000);
    const result = capSubagentCompletionResult(source);

    expect(result).toContain("[Child result truncated: 20000 characters total.");
    expect(result.length).toBeLessThan(12_200);
    expect(result.startsWith("x".repeat(100))).toBe(true);
  });
});
