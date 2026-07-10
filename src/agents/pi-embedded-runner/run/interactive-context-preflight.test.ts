import { describe, expect, it } from "vitest";
import { evaluateInteractiveContextPreflight, isMainInteractiveSession } from "./attempt.js";

describe("interactive context preflight", () => {
  it("detects main interactive sessions", () => {
    expect(
      isMainInteractiveSession({
        sessionKey: "agent:main:telegram:direct:123",
        messageChannel: "telegram",
      }),
    ).toBe(true);
    expect(isMainInteractiveSession({ sessionKey: "agent:main:telegram:direct:123" })).toBe(false);
    expect(
      isMainInteractiveSession({
        sessionKey: "agent:main:subagent:abc",
        messageChannel: "telegram",
      }),
    ).toBe(false);
  });

  it("blocks fixed interactive context that already exceeds usable model window", () => {
    const result = evaluateInteractiveContextPreflight({
      sessionKey: "agent:main:telegram:direct:123",
      messageChannel: "telegram",
      prompt: "hello",
      systemPromptChars: 30_000,
      promptChars: 5,
      historyTextChars: 10_000,
      contextWindowTokens: 8_000,
    });

    expect(result).toMatchObject({
      kind: "interactive_baseline_exceeds_context",
      estimatedTokens: 10_002,
      contextWindowTokens: 8_000,
    });
  });

  it("does not block background/subagent jobs or reset commands", () => {
    const base = {
      prompt: "hello",
      systemPromptChars: 30_000,
      promptChars: 5,
      historyTextChars: 10_000,
      contextWindowTokens: 8_000,
    };

    expect(
      evaluateInteractiveContextPreflight({
        ...base,
        sessionKey: "agent:main:subagent:abc",
        messageChannel: "telegram",
      }),
    ).toBeUndefined();
    expect(
      evaluateInteractiveContextPreflight({
        ...base,
        sessionKey: "agent:main:telegram:direct:123",
        messageChannel: "telegram",
        prompt: "/reset",
      }),
    ).toBeUndefined();
  });
});
