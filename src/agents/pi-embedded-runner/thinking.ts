import type { AgentMessage } from "@mariozechner/pi-agent-core";

type AssistantContentBlock = Extract<AgentMessage, { role: "assistant" }>["content"][number];
type AssistantMessage = Extract<AgentMessage, { role: "assistant" }>;

export function isAssistantMessageWithContent(message: AgentMessage): message is AssistantMessage {
  return (
    !!message &&
    typeof message === "object" &&
    message.role === "assistant" &&
    Array.isArray(message.content)
  );
}

/**
 * Strip all `type: "thinking"` content blocks from assistant messages.
 *
 * If an assistant message becomes empty after stripping, it is replaced with
 * a synthetic `{ type: "text", text: "" }` block to preserve turn structure
 * (some providers require strict user/assistant alternation).
 *
 * Returns the original array reference when nothing was changed (callers can
 * use reference equality to skip downstream work).
 */
export function dropThinkingBlocks(messages: AgentMessage[]): AgentMessage[] {
  let touched = false;
  const out: AgentMessage[] = [];
  for (const msg of messages) {
    if (!isAssistantMessageWithContent(msg)) {
      out.push(msg);
      continue;
    }
    const nextContent: AssistantContentBlock[] = [];
    let changed = false;
    for (const block of msg.content) {
      if (block && typeof block === "object" && (block as { type?: unknown }).type === "thinking") {
        touched = true;
        changed = true;
        continue;
      }
      nextContent.push(block);
    }
    if (!changed) {
      out.push(msg);
      continue;
    }
    // Preserve the assistant turn even if all blocks were thinking-only.
    const content =
      nextContent.length > 0 ? nextContent : [{ type: "text", text: "" } as AssistantContentBlock];
    out.push({ ...msg, content });
  }
  return touched ? out : messages;
}

function isThinkingBlock(block: unknown): boolean {
  if (!block || typeof block !== "object") return false;
  const t = (block as { type?: unknown }).type;
  return t === "thinking" || t === "redacted_thinking";
}

/**
 * Strip thinking/redacted_thinking blocks from every assistant message EXCEPT
 * the last one. Anthropic requires that the most recent assistant turn's thinking
 * blocks are passed back verbatim; older thinking blocks are optional and can be
 * omitted cleanly to avoid modification errors from compaction/pruning.
 *
 * Returns the original array reference when nothing was changed.
 */
export function dropOlderThinkingBlocks(messages: AgentMessage[]): AgentMessage[] {
  // Find index of the last assistant message.
  let lastAssistantIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (isAssistantMessageWithContent(messages[i]!)) {
      lastAssistantIdx = i;
      break;
    }
  }

  let touched = false;
  const out: AgentMessage[] = [];
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i]!;
    // Preserve the latest assistant message completely — its thinking blocks must not be touched.
    if (i === lastAssistantIdx || !isAssistantMessageWithContent(msg)) {
      out.push(msg);
      continue;
    }
    const nextContent: AssistantContentBlock[] = [];
    let changed = false;
    for (const block of msg.content) {
      if (isThinkingBlock(block)) {
        touched = true;
        changed = true;
        continue;
      }
      nextContent.push(block);
    }
    if (!changed) {
      out.push(msg);
      continue;
    }
    const content =
      nextContent.length > 0 ? nextContent : [{ type: "text", text: "" } as AssistantContentBlock];
    out.push({ ...msg, content });
  }
  return touched ? out : messages;
}
