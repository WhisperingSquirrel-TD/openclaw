import { createHash, randomUUID } from "node:crypto";

export type SkilzVoltCatalogueEntry = {
  skillId: string;
  workspaceId: string;
  workspaceName?: string;
  name: string;
  description: string;
  updatedAt?: string;
  currentVersionId?: string;
};

export type SkillReceipt = {
  readonly receiptId: string;
  readonly skillId: string;
  readonly workspaceId: string;
  readonly versionId: string;
  readonly contentSha256: string;
  readonly readAt: number;
  readonly purpose: string;
  readonly skillName: string;
  readonly workflowSource?: "skill-body" | "resource";
  readonly resourceId?: string;
  readonly workflowSha256?: string;
};

export type WorkflowRequirement = {
  id: string;
  source?: string;
  action?: string;
};

export type WorkflowContract = {
  requirements: WorkflowRequirement[];
};

export type WorkflowProofStatus = "complete" | "blocked" | "not_applicable";

export type WorkflowProof = {
  requirementId: string;
  status: WorkflowProofStatus;
  evidence?: string;
};

export type PromptRoute =
  | { kind: "match"; entry: SkilzVoltCatalogueEntry; reason: string }
  | { kind: "none"; reason: string }
  | { kind: "ambiguous"; entries: SkilzVoltCatalogueEntry[]; reason: string };

type GovernedRun = {
  receipt: SkillReceipt;
  workflow: WorkflowContract;
  proofs: Map<string, WorkflowProof>;
};

const WORKFLOW_MARKER = /<!--\s*skilzvolt-workflow\s*([\s\S]*?)-->/i;
const LEARNING_INTENT =
  /\b(?:learn|learning|improve|correction|corrected|feedback|retrospective|retrospect)\b[\s\S]{0,80}\b(?:this|that|from|mistake|error|feedback|correction|lesson)\b/i;
const GOVERNED_MARKER = /^\s*\[skilzvolt-governed\s+skill=([^\]\r\n]+)\]\s*/i;
// Description routing runs against every ordinary prompt. These terms are too common to establish
// organisation-specific intent on their own, especially in incident reports and support requests.
const DESCRIPTION_ROUTING_STOPWORDS = new Set([
  "about",
  "agent",
  "assist",
  "assistant",
  "current",
  "error",
  "errors",
  "help",
  "issue",
  "issues",
  "problem",
  "problems",
  "reported",
  "request",
  "requests",
  "system",
  "systems",
  "thing",
  "things",
  "update",
  "updated",
  "work",
  "workflow",
]);

function normalize(value: string): string {
  return value.toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

function uniqueEntries(entries: SkilzVoltCatalogueEntry[]): SkilzVoltCatalogueEntry[] {
  return entries.filter(
    (entry, index) =>
      entries.findIndex((candidate) => candidate.skillId === entry.skillId) === index,
  );
}

function routingTerms(value: string): Set<string> {
  return new Set(
    normalize(value)
      .split(/[^a-z0-9]+/)
      .filter((term) => term.length >= 5 && !DESCRIPTION_ROUTING_STOPWORDS.has(term)),
  );
}

export function routePrompt(prompt: string, entries: SkilzVoltCatalogueEntry[]): PromptRoute {
  const normalized = normalize(prompt);
  const declared = prompt.match(GOVERNED_MARKER)?.[1]?.trim();
  if (declared) {
    const declaredMatches = uniqueEntries(
      entries.filter((entry) => normalize(entry.name) === normalize(declared)),
    );
    if (declaredMatches.length === 1) {
      return {
        kind: "match",
        entry: declaredMatches[0]!,
        reason: "declared-cron-skill",
      };
    }
    if (declaredMatches.length > 1) {
      return {
        kind: "ambiguous",
        entries: declaredMatches,
        reason: "multiple-live-declared-skill-names",
      };
    }
    return { kind: "none", reason: "declared-live-skill-not-found" };
  }
  const learningEntries = uniqueEntries(
    entries.filter((entry) => normalize(entry.name) === "learning"),
  );
  if (/\blearn from (?:this|that)\b/i.test(normalized) || LEARNING_INTENT.test(normalized)) {
    if (learningEntries.length === 1) {
      return {
        kind: "match",
        entry: learningEntries[0]!,
        reason: "explicit-learning-intent",
      };
    }
    if (learningEntries.length > 1) {
      return {
        kind: "ambiguous",
        entries: learningEntries,
        reason: "multiple-live-learning-skills",
      };
    }
    return { kind: "none", reason: "learning-skill-not-authorised" };
  }

  const exactNameMatches = uniqueEntries(
    entries.filter((entry) => {
      const name = normalize(entry.name);
      return (
        name.length > 1 &&
        new RegExp(`(?:^|\\s)${escapeRegExp(name)}(?:$|\\s)`, "i").test(normalized)
      );
    }),
  );
  if (exactNameMatches.length === 1) {
    return {
      kind: "match",
      entry: exactNameMatches[0]!,
      reason: "exact-live-skill-name",
    };
  }
  if (exactNameMatches.length > 1) {
    return {
      kind: "ambiguous",
      entries: exactNameMatches,
      reason: "multiple-exact-live-skill-names",
    };
  }

  const described = uniqueEntries(
    entries.filter((entry) => {
      const promptTerms = routingTerms(normalized);
      const descriptionTerms = routingTerms(entry.description);
      const matches = [...promptTerms].filter((term) => descriptionTerms.has(term));
      return matches.length >= 2;
    }),
  );
  if (described.length === 1) {
    return {
      kind: "match",
      entry: described[0]!,
      reason: "high-confidence-live-description",
    };
  }
  if (described.length > 1) {
    return {
      kind: "ambiguous",
      entries: described,
      reason: "multiple-live-description-matches",
    };
  }
  return { kind: "none", reason: "no-applicable-live-skill" };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function parseWorkflowContract(content: string): WorkflowContract {
  const match = WORKFLOW_MARKER.exec(content);
  let parsed: unknown;
  try {
    parsed = JSON.parse((match?.[1] ?? content).trim());
  } catch {
    if (!match?.[1]) {
      throw new Error(
        "Live SkilzVolt skill is missing an enforceable workflow contract (marker or resource)",
      );
    }
    throw new Error("Live SkilzVolt workflow contract is not valid JSON");
  }
  if (
    !parsed ||
    typeof parsed !== "object" ||
    !Array.isArray((parsed as Record<string, unknown>).requirements)
  ) {
    throw new Error("Live SkilzVolt workflow contract is missing requirements");
  }
  const requirements = (parsed as Record<string, unknown>).requirements as unknown[];
  const normalized = requirements.map((requirement) => {
    if (!requirement || typeof requirement !== "object") {
      throw new Error("Live SkilzVolt workflow requirement is invalid");
    }
    const record = requirement as Record<string, unknown>;
    if (typeof record.id !== "string" || !record.id.trim()) {
      throw new Error("Live SkilzVolt workflow requirement lacks an id");
    }
    return {
      id: record.id.trim(),
      ...(typeof record.source === "string" ? { source: record.source.trim() } : {}),
      ...(typeof record.action === "string" ? { action: record.action.trim() } : {}),
    };
  });
  if (normalized.length === 0) {
    throw new Error("Live SkilzVolt workflow contract has no requirements");
  }
  return { requirements: normalized };
}

export function createSkillReceipt(params: {
  entry: SkilzVoltCatalogueEntry;
  content: string;
  purpose: string;
  workflowSource?: "skill-body" | "resource";
  resourceId?: string;
  workflowSha256?: string;
  readAt?: number;
}): SkillReceipt {
  if (!params.entry.currentVersionId) {
    throw new Error(`Live SkilzVolt skill ${params.entry.name} has no current version`);
  }
  if (!params.content.trim()) {
    throw new Error(`Live SkilzVolt skill ${params.entry.name} has no content`);
  }
  return {
    receiptId: randomUUID(),
    skillId: params.entry.skillId,
    workspaceId: params.entry.workspaceId,
    versionId: params.entry.currentVersionId,
    contentSha256: createHash("sha256").update(params.content, "utf8").digest("hex"),
    readAt: params.readAt ?? Date.now(),
    purpose: params.purpose,
    skillName: params.entry.name,
    ...(params.workflowSource ? { workflowSource: params.workflowSource } : {}),
    ...(params.resourceId ? { resourceId: params.resourceId } : {}),
    ...(params.workflowSha256 ? { workflowSha256: params.workflowSha256 } : {}),
  };
}

export class SkillGovernanceLedger {
  private static readonly MAX_ENTRIES = 4096;
  private readonly runs = new Map<string, GovernedRun>();
  private readonly declarations = new Map<string, string>();

  private evictIfNeeded(map: Map<string, unknown>): void {
    while (map.size > SkillGovernanceLedger.MAX_ENTRIES) {
      const oldest = map.keys().next().value as string | undefined;
      if (oldest === undefined) break;
      map.delete(oldest);
    }
  }

  declare(runId: string, skillName: string): void {
    if (!runId.trim() || !skillName.trim()) {
      throw new Error("governed declaration requires a run ID and skill name");
    }
    this.declarations.delete(runId);
    this.declarations.set(runId, skillName.trim());
    this.evictIfNeeded(this.declarations);
  }

  hasDeclaration(runId: string): boolean {
    return this.declarations.has(runId);
  }

  begin(runId: string, params: { receipt: SkillReceipt; workflow: WorkflowContract }): void {
    if (!runId.trim()) {
      throw new Error("governed run requires a run ID");
    }
    const run = {
      ...params,
      proofs: new Map(),
    };
    this.runs.delete(runId);
    this.runs.set(runId, run);
    this.evictIfNeeded(this.runs);
  }

  hasReceipt(runId: string): boolean {
    return this.runs.has(runId);
  }

  recordProof(runId: string, proof: WorkflowProof): void {
    const run = this.runs.get(runId);
    if (!run) {
      throw new Error("no live skill receipt exists for this run");
    }
    if (!run.workflow.requirements.some((requirement) => requirement.id === proof.requirementId)) {
      throw new Error(`workflow proof is not required: ${proof.requirementId}`);
    }
    run.proofs.set(proof.requirementId, { ...proof });
    this.runs.delete(runId);
    this.runs.set(runId, run);
  }

  isDeliverable(runId: string): boolean {
    const run = this.runs.get(runId);
    if (!run) {
      return false;
    }
    this.runs.delete(runId);
    this.runs.set(runId, run);
    return run.workflow.requirements.every((requirement) => {
      const proof = run.proofs.get(requirement.id);
      return proof?.status === "complete" || proof?.status === "not_applicable";
    });
  }

  get(runId: string): GovernedRun | undefined {
    const run = this.runs.get(runId);
    if (!run) {
      return undefined;
    }
    this.runs.delete(runId);
    this.runs.set(runId, run);
    return { ...run, proofs: new Map(run.proofs) };
  }

  clear(runId: string): void {
    this.runs.delete(runId);
    this.declarations.delete(runId);
  }
}
