import { describe, expect, it, vi } from "vitest";
import {
  createSkillReceipt,
  parseWorkflowContract,
  routePrompt,
  SkillGovernanceLedger,
  type SkilzVoltCatalogueEntry,
} from "./governance.js";

const learning: SkilzVoltCatalogueEntry = {
  skillId: "skill-learning",
  workspaceId: "workspace-1",
  name: "learning",
  description: "Learn from corrections and improve future work",
  currentVersionId: "version-7",
};

describe("SkilzVolt governance", () => {
  it("routes explicit learning prompts to the canonical live skill", () => {
    expect(routePrompt("Please learn from this correction", [learning])).toEqual({
      kind: "match",
      entry: learning,
      reason: "explicit-learning-intent",
    });
  });

  it("resolves governed cron markers by exact normalized name before generic matching", () => {
    const entry = { ...learning, name: "Daily Briefing" };
    expect(
      routePrompt("[skilzvolt-governed skill=daily briefing]\nRun now", [entry]),
    ).toMatchObject({
      kind: "match",
      entry,
      reason: "declared-cron-skill",
    });
    expect(routePrompt("[skilzvolt-governed skill=missing]\nRun now", [entry])).toMatchObject({
      kind: "none",
      reason: "declared-live-skill-not-found",
    });
  });

  it("does not guess between equally plausible catalogue entries", () => {
    const candidates = [
      { ...learning, name: "review", description: "Review the inbox and recommend action" },
      {
        ...learning,
        skillId: "skill-review",
        name: "review",
        description: "Review expense records",
      },
    ];
    expect(routePrompt("please review this", candidates)).toMatchObject({ kind: "ambiguous" });
  });

  it("requires a machine-readable workflow contract in the live body", () => {
    const body = [
      "# Learning",
      "<!-- skilzvolt-workflow",
      '{"requirements":[{"id":"capture","source":"input","action":"record"}]}',
      "-->",
    ].join("\n");
    expect(parseWorkflowContract(body)).toEqual({
      requirements: [{ id: "capture", source: "input", action: "record" }],
    });
    expect(() => parseWorkflowContract("# No contract")).toThrow(/workflow contract/i);
  });

  it("issues an opaque receipt and requires runtime proof", () => {
    const ledger = new SkillGovernanceLedger();
    const receipt = createSkillReceipt({
      entry: learning,
      content: "live skill body",
      purpose: "learning",
    });
    ledger.begin("run-1", { receipt, workflow: { requirements: [{ id: "capture" }] } });
    expect(ledger.hasReceipt("run-1")).toBe(true);
    expect(ledger.isDeliverable("run-1")).toBe(false);
    ledger.recordProof("run-1", { requirementId: "capture", status: "complete" });
    expect(ledger.isDeliverable("run-1")).toBe(true);
    expect(receipt).toMatchObject({
      skillId: learning.skillId,
      versionId: learning.currentVersionId,
      workspaceId: learning.workspaceId,
      contentSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
    });
    expect(receipt.receiptId).not.toBe("run-1");
  });

  it("isolates receipts and proof between concurrent runs", () => {
    const ledger = new SkillGovernanceLedger();
    const receipt = createSkillReceipt({ entry: learning, content: "same", purpose: "learning" });
    ledger.begin("run-a", { receipt, workflow: { requirements: [{ id: "a" }] } });
    ledger.begin("run-b", { receipt, workflow: { requirements: [{ id: "b" }] } });
    ledger.recordProof("run-a", { requirementId: "a", status: "complete" });
    expect(ledger.isDeliverable("run-a")).toBe(true);
    expect(ledger.isDeliverable("run-b")).toBe(false);
  });

  it("tracks a declared run separately so missing receipts can fail closed", () => {
    const ledger = new SkillGovernanceLedger();
    ledger.declare("run-cron", "learning");
    expect(ledger.hasDeclaration("run-cron")).toBe(true);
    expect(ledger.hasReceipt("run-cron")).toBe(false);
  });

  it("keeps a proven run available through delivery ordering regardless of elapsed time", () => {
    vi.useFakeTimers();
    try {
      const ledger = new SkillGovernanceLedger();
      const receipt = createSkillReceipt({ entry: learning, content: "same", purpose: "reply" });
      ledger.declare("run-reply", learning.name);
      ledger.begin("run-reply", { receipt, workflow: { requirements: [{ id: "send" }] } });
      ledger.recordProof("run-reply", { requirementId: "send", status: "complete" });
      // The agent completion hook may happen before route-reply; no eager cleanup is performed.
      expect(ledger.isDeliverable("run-reply")).toBe(true);
      expect(ledger.isDeliverable("later-run")).toBe(false);
      vi.advanceTimersByTime(11 * 60 * 1000);
      expect(ledger.hasReceipt("run-reply")).toBe(true);
      ledger.clear("run-reply");
      expect(ledger.hasReceipt("run-reply")).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it("bounds retained run state by evicting only the oldest entries", () => {
    const ledger = new SkillGovernanceLedger();
    const receipt = createSkillReceipt({ entry: learning, content: "same", purpose: "capacity" });
    for (let i = 0; i < 4097; i++) {
      ledger.begin(`run-${i}`, { receipt, workflow: { requirements: [] } });
    }
    expect(ledger.hasReceipt("run-0")).toBe(false);
    expect(ledger.hasReceipt("run-4096")).toBe(true);
  });
});
