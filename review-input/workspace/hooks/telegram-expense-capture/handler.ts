import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

const QUEUE = "/home/tomdean88/.openclaw/runtime/inbound-watch-router/expense-enrichment-queue.json";
// Bare discussion of an "expense system" is not transactional evidence. Preserve
// plausible financial messages, but require a money marker or transactional term.
const EXPENSE_SIGNAL = /(?:\b(?:invoice|receipt|paid|payment|charge|charged|cost|spent|spend|bought|purchase|ordered|renewal|subscription|reimburse(?:ment)?|bill(?:ing)?|taxi|mileage)\b|[£$€]\s*\d)/i;
const MAX_FUTURE_SKEW_MS = 5 * 60 * 1000;

type QueueItem = Record<string, unknown>;
type QueueDocument = { schema_version: number; items: QueueItem[]; updated_at?: string };

type SafeObservedAt = { observedAt: string; rawSourceTimestamp?: string; sourceTimestampStatus: "valid" | "missing" | "invalid" | "invalid_future" };

export function safeObservedAt(timestamp: unknown, nowMs = Date.now()): SafeObservedAt {
  const fallback = new Date(nowMs).toISOString();
  if (timestamp === undefined || timestamp === null || timestamp === "") {
    return { observedAt: fallback, sourceTimestampStatus: "missing" };
  }
  const rawSourceTimestamp = String(timestamp);
  const numeric = typeof timestamp === "number" && Number.isFinite(timestamp);
  // Telegram adapters may supply Unix seconds or milliseconds. Do not multiply
  // a millisecond epoch again: that creates years such as +058577.
  const epochMs = numeric ? (timestamp < 100_000_000_000 ? timestamp * 1000 : timestamp) : Date.parse(rawSourceTimestamp);
  if (!Number.isFinite(epochMs)) {
    return { observedAt: fallback, rawSourceTimestamp, sourceTimestampStatus: "invalid" };
  }
  if (epochMs > nowMs + MAX_FUTURE_SKEW_MS) {
    return { observedAt: fallback, rawSourceTimestamp, sourceTimestampStatus: "invalid_future" };
  }
  try {
    return { observedAt: new Date(epochMs).toISOString(), rawSourceTimestamp, sourceTimestampStatus: "valid" };
  } catch {
    return { observedAt: fallback, rawSourceTimestamp, sourceTimestampStatus: "invalid" };
  }
}

async function atomicWrite(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.${Date.now()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temporary, path);
}

async function loadQueue(): Promise<QueueDocument> {
  try {
    const parsed = JSON.parse(await readFile(QUEUE, "utf8"));
    if (parsed && Array.isArray(parsed.items)) return parsed as QueueDocument;
  } catch (error: unknown) {
    if (!(error instanceof Error) || !("code" in error) || error.code !== "ENOENT") throw error;
  }
  return { schema_version: 1, items: [] };
}

export default async function telegramExpenseCapture(event: any): Promise<void> {
  if (event?.type !== "message" || event?.action !== "received") return;
  const context = event.context ?? {};
  if (context.channelId !== "telegram") return;
  const content = String(context.content ?? "").trim();
  if (!content || !EXPENSE_SIGNAL.test(content)) return;
  const conversationId = String(context.conversationId ?? context.from ?? "unknown");
  const messageId = String(context.messageId ?? `${context.timestamp ?? Date.now()}`);
  const sourceId = `telegram:${conversationId}:${messageId}`;
  const queue = await loadQueue();
  if (queue.items.some((item) => item.source_id === sourceId)) return;
  const timestamp = safeObservedAt(context.timestamp);
  queue.items.push({
    source_id: sourceId,
    source_surface: "telegram_inbound",
    canonical_ref: `seer-expenses.md#pending:${sourceId}`,
    state: "needs_enrichment",
    required_facts: ["amount_pence", "category", "payment_settlement", "evidence_state"],
    blocker: "Telegram expense claim captured; requires evidence/enrichment before finance ledger entry",
    observed_at: timestamp.observedAt,
    raw_source_timestamp: timestamp.rawSourceTimestamp,
    source_timestamp_status: timestamp.sourceTimestampStatus,
    source_excerpt: content.slice(0, 500),
  });
  queue.updated_at = new Date().toISOString();
  await atomicWrite(QUEUE, queue);
}
