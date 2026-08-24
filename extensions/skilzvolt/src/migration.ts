import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { SkilzVoltClient } from "./client.js";

const MAX_SKILL_BYTES = 256_000;

type JournalEntry = {
  hash: string;
  submittedAt?: string;
  retiredAt?: string;
  proposalId?: string;
  workspaceId?: string;
  operationId?: string;
  clientRef?: string;
};

type Journal = {
  version: 1;
  skills: Record<string, JournalEntry>;
};

export type MigrationConfig = {
  organisationSkillNames: string[];
  stateDir?: string;
};

type LocalSkill = {
  name: string;
  directory: string;
  content: string;
  hash: string;
  bytes: number;
};

function defaultStateDir(): string {
  return process.env.OPENCLAW_STATE_DIR?.trim() || path.join(os.homedir(), ".openclaw");
}

function hashContent(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function readTextResult(value: unknown): Record<string, unknown> {
  const direct = asRecord(value);
  if (!direct) {
    throw new Error("SkilzVolt returned an invalid structured response");
  }
  const structured = asRecord(direct.structuredContent);
  if (structured) {
    return structured;
  }
  const text = Array.isArray(direct.content)
    ? direct.content.find(
        (entry) => asRecord(entry)?.type === "text" && typeof asRecord(entry)?.text === "string",
      )
    : undefined;
  if (text) {
    try {
      const parsed = JSON.parse(asRecord(text)?.text as string);
      const parsedRecord = asRecord(parsed);
      if (parsedRecord) {
        return parsedRecord;
      }
    } catch {
      // A plain text response has no machine-verifiable migration identity.
    }
  }
  return direct;
}

function readNamedString(
  value: Record<string, unknown>,
  names: readonly string[],
): string | undefined {
  for (const name of names) {
    if (typeof value[name] === "string" && value[name]) {
      return value[name] as string;
    }
  }
  return undefined;
}

function extractProposal(
  value: unknown,
  requireStatus: boolean,
): {
  proposalId: string;
  status?: string;
  skillId?: string;
} {
  const body = readTextResult(value);
  const nestedProposal = asRecord(body.proposal);
  const proposal =
    nestedProposal ??
    (Object.hasOwn(body, "proposalId") || Object.hasOwn(body, "proposal_id") ? body : undefined);
  if (!proposal) {
    throw new Error("SkilzVolt response lacks the canonical proposal object");
  }
  const proposalId = readNamedString(proposal, ["proposalId", "proposal_id", "id"]);
  if (!proposalId) {
    throw new Error("SkilzVolt proposal response lacks its canonical proposal ID");
  }
  const status = readNamedString(proposal, ["status"]);
  if (requireStatus && !status) {
    throw new Error("SkilzVolt proposal response lacks its canonical status");
  }
  const nestedSkill = asRecord(proposal.skill);
  const skillId =
    readNamedString(proposal, ["skillId", "skill_id", "currentSkillId", "current_skill_id"]) ??
    readNamedString(nestedSkill ?? {}, ["id", "skillId", "skill_id"]);
  return { proposalId, status, skillId };
}

function extractCurrentSkill(value: unknown): {
  skillId: string;
  content: string;
} {
  const body = readTextResult(value);
  const nestedSkill = asRecord(body.skill);
  const skill =
    nestedSkill ??
    (Object.hasOwn(body, "content") || Object.hasOwn(body, "markdown") ? body : undefined);
  if (!skill) {
    throw new Error("SkilzVolt response lacks the canonical current skill object");
  }
  const skillId = readNamedString(skill, ["skillId", "skill_id", "id"]);
  const content = readNamedString(skill, ["content", "markdown"]);
  if (!skillId || content === undefined) {
    throw new Error("SkilzVolt current skill response lacks canonical ID or content");
  }
  return { skillId, content };
}

function bindIdentityArgument(
  argumentsInput: Record<string, unknown>,
  identity: string,
  allowedKeys: readonly string[],
  label: string,
): Record<string, unknown> {
  const keys = allowedKeys.filter((key) => Object.hasOwn(argumentsInput, key));
  if (keys.length !== 1) {
    throw new Error(
      `${label} arguments must include exactly one canonical identifier field: ${allowedKeys.join(", ")}`,
    );
  }
  return { ...argumentsInput, [keys[0]!]: identity };
}

export class SkilzVoltMigrationManager {
  private readonly stateDir: string;
  private readonly allowedNames: Set<string>;

  constructor(
    private readonly client: SkilzVoltClient,
    private readonly config: MigrationConfig,
  ) {
    this.stateDir = config.stateDir ?? defaultStateDir();
    this.allowedNames = new Set(config.organisationSkillNames);
  }

  private migrationDir(): string {
    return path.join(this.stateDir, "skilzvolt");
  }

  private journalPath(): string {
    return path.join(this.migrationDir(), "migration-journal.json");
  }

  private skillRoots(): string[] {
    return [
      path.join(this.stateDir, "skills"),
      path.join(this.stateDir, "workspace", "skills"),
      path.join(this.stateDir, "workspace", ".agents", "skills"),
    ];
  }

  private markerPath(name: string): string {
    this.assertSafeName(name);
    return path.join(this.migrationDir(), "retired-skills", name);
  }

  private assertSafeName(name: string): void {
    if (!name || name === "." || name === ".." || name.includes("/") || name.includes("\\")) {
      throw new Error(`Invalid local skill name: ${name}`);
    }
  }

  private async discoverLocalSkills(): Promise<LocalSkill[]> {
    const discovered = new Map<string, LocalSkill>();
    for (const root of this.skillRoots()) {
      let entries;
      try {
        entries = await fs.readdir(root, { withFileTypes: true });
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") continue;
        throw error;
      }
      for (const entry of entries) {
        if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
        const skillPath = path.join(root, entry.name, "SKILL.md");
        try {
          const stat = await fs.stat(skillPath);
          if (!stat.isFile() || stat.size > MAX_SKILL_BYTES) continue;
          const content = await fs.readFile(skillPath, "utf8");
          if (!discovered.has(entry.name)) {
            discovered.set(entry.name, {
              name: entry.name,
              directory: path.join(root, entry.name),
              content,
              hash: hashContent(content),
              bytes: Buffer.byteLength(content),
            });
          }
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
        }
      }
    }
    return [...discovered.values()].sort((a, b) => a.name.localeCompare(b.name));
  }

  private async findLocalSkill(name: string): Promise<LocalSkill> {
    this.assertSafeName(name);
    const skills = await this.discoverLocalSkills();
    const skill = skills.find((candidate) => candidate.name === name);
    if (!skill) {
      throw new Error(`Local skill is missing or exceeds ${MAX_SKILL_BYTES} bytes: ${name}`);
    }
    return skill;
  }

  private async readJournal(): Promise<Journal> {
    try {
      const parsed = JSON.parse(await fs.readFile(this.journalPath(), "utf8")) as Journal;
      if (parsed?.version === 1 && parsed.skills && typeof parsed.skills === "object") {
        return parsed;
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
        throw new Error("SkilzVolt migration journal is malformed or unreadable");
      }
    }
    return { version: 1, skills: {} };
  }

  private async writeJournal(journal: Journal): Promise<void> {
    await fs.mkdir(this.migrationDir(), { recursive: true, mode: 0o700 });
    const tempPath = `${this.journalPath()}.tmp-${process.pid}`;
    await fs.writeFile(tempPath, `${JSON.stringify(journal, null, 2)}\n`, {
      mode: 0o600,
    });
    await fs.rename(tempPath, this.journalPath());
  }

  private async readSkill(name: string): Promise<LocalSkill> {
    return this.findLocalSkill(name);
  }

  async inventory(): Promise<unknown> {
    const journal = await this.readJournal();
    const localSkills = await this.discoverLocalSkills();
    const discoveredNames = new Set(localSkills.map((skill) => skill.name));
    const skills = [];
    for (const local of localSkills) {
      const name = local.name;
      const marker = await fs
        .access(this.markerPath(name))
        .then(() => true)
        .catch(() => false);
      skills.push({
        name,
        local: true,
        directory: local.directory,
        bytes: local.bytes,
        sha256: local.hash,
        status: marker
          ? "retired_marker_but_local_copy_present"
          : journal.skills[name]?.submittedAt
            ? "submitted"
            : "ready",
        proposalId: journal.skills[name]?.proposalId,
      });
    }
    for (const name of this.config.organisationSkillNames) {
      if (discoveredNames.has(name)) continue;
      const marker = await fs
        .access(this.markerPath(name))
        .then(() => true)
        .catch(() => false);
      skills.push({
        name,
        local: false,
        status: marker ? "retired" : "missing_unverified",
        proposalId: journal.skills[name]?.proposalId,
      });
    }
    return {
      mode: "dry-run",
      scope: "all-local-skill-roots",
      roots: this.skillRoots(),
      skills,
    };
  }

  private async writableWorkspace(workspaceId?: string, signal?: AbortSignal): Promise<string> {
    if (workspaceId?.trim()) return workspaceId.trim();
    const result = (await this.client.callTool("workspaces_list", {}, signal)) as Record<
      string,
      unknown
    >;
    const workspaces = Array.isArray(result.workspaces) ? result.workspaces : [];
    const writable = workspaces.filter(
      (workspace): workspace is Record<string, unknown> =>
        Boolean(workspace && typeof workspace === "object" && !Array.isArray(workspace)) &&
        workspace.access === "read_write",
    );
    if (writable.length !== 1 || typeof writable[0]?.workspace_id !== "string") {
      throw new Error("Select exactly one writable SkilzVolt workspace before migrating skills");
    }
    return writable[0].workspace_id;
  }

  async previewAll(params: { workspaceId?: string; signal?: AbortSignal }): Promise<unknown> {
    const workspaceId = await this.writableWorkspace(params.workspaceId, params.signal);
    const skills = await this.discoverLocalSkills();
    const candidates = skills.map((skill) => ({
      client_ref: `${skill.name}:${skill.hash}`,
      name: skill.name,
      content: skill.content,
    }));
    return this.client.callTool(
      "skills_migration_preview",
      { workspace_id: workspaceId, skills: candidates },
      params.signal,
    );
  }

  async submitAll(params: {
    workspaceId?: string;
    migrationOperationId: string;
    items: Array<{
      client_ref: string;
      name: string;
      description?: string;
      content: string;
      suggested_purpose?: string;
      suggested_rules?: string;
      rationale?: string;
    }>;
    signal?: AbortSignal;
  }): Promise<unknown> {
    const workspaceId = await this.writableWorkspace(params.workspaceId, params.signal);
    if (!params.migrationOperationId.trim()) {
      throw new Error("migrationOperationId is required for idempotent migration");
    }
    const result = await this.client.callTool(
      "skills_migration_submit",
      {
        workspace_id: workspaceId,
        migration_operation_id: params.migrationOperationId,
        skills: params.items,
      },
      params.signal,
    );
    const body = readTextResult(result);
    const results = Array.isArray(body.results) ? body.results : [];
    const journal = await this.readJournal();
    for (const item of results) {
      const record = asRecord(item);
      const name = readNamedString(record ?? {}, ["skill_name", "name"]);
      const proposalId = readNamedString(record ?? {}, ["proposal_id", "proposalId"]);
      const clientRef = readNamedString(record ?? {}, ["client_ref", "clientRef"]);
      if (name && clientRef) {
        const local = await this.findLocalSkill(name);
        journal.skills[name] = {
          ...journal.skills[name],
          hash: local.hash,
          submittedAt: new Date().toISOString(),
          proposalId,
          workspaceId,
          operationId: params.migrationOperationId,
          clientRef,
        };
      }
    }
    await this.writeJournal(journal);
    return result;
  }

  async recover(params: {
    workspaceId: string;
    migrationOperationId: string;
    clientRef: string;
    signal?: AbortSignal;
  }): Promise<unknown> {
    return this.client.callTool(
      "skills_migration_recover",
      {
        workspace_id: params.workspaceId,
        migration_operation_id: params.migrationOperationId,
        client_ref: params.clientRef,
      },
      params.signal,
    );
  }

  async submit(params: {
    skillName: string;
    createArguments: Record<string, unknown>;
    contentParameter: string;
    signal?: AbortSignal;
  }): Promise<unknown> {
    const local = await this.readSkill(params.skillName);
    const tools = await this.client.listTools(params.signal);
    const createTool = tools.find((tool) => tool.name === "skills_create");
    if (!createTool) {
      throw new Error("SkilzVolt did not advertise skills_create");
    }
    const properties =
      createTool.inputSchema?.properties && typeof createTool.inputSchema.properties === "object"
        ? (createTool.inputSchema.properties as Record<string, unknown>)
        : undefined;
    if (!properties || !Object.hasOwn(properties, params.contentParameter)) {
      throw new Error(
        `contentParameter is not present in the live SkilzVolt skills_create schema: ${params.contentParameter}`,
      );
    }
    const createArguments = structuredClone(params.createArguments);
    createArguments[params.contentParameter] = local.content;
    const result = await this.client.callTool("skills_create", createArguments, params.signal);
    const proposalId = extractProposal(result, false).proposalId;
    const journal = await this.readJournal();
    journal.skills[params.skillName] = {
      hash: local.hash,
      submittedAt: new Date().toISOString(),
      proposalId,
    };
    await this.writeJournal(journal);
    return {
      submitted: true,
      deletedLocally: false,
      skillName: params.skillName,
      sha256: local.hash,
      proposalId,
      result,
      next: "Wait for explicit approval/current status, then run verify_and_retire with canonical proposal and skill identifiers.",
    };
  }

  async verifyAndRetire(params: {
    skillName: string;
    proposalStatusArguments: Record<string, unknown>;
    getArguments: Record<string, unknown>;
    signal?: AbortSignal;
  }): Promise<unknown> {
    this.assertAllowedName(params.skillName);
    const journal = await this.readJournal();
    const submitted = journal.skills[params.skillName];
    if (!submitted?.submittedAt || !submitted.proposalId) {
      throw new Error("No recorded SkilzVolt submission exists for this local skill");
    }
    const local = await this.readSkill(params.skillName);
    if (local.hash !== submitted.hash) {
      throw new Error(
        "Local skill changed after submission; submit the new content before retiring it",
      );
    }
    const proposal = await this.client.callTool(
      "skills_proposal_status",
      bindIdentityArgument(
        params.proposalStatusArguments,
        submitted.proposalId,
        ["proposal_id", "proposalId", "id"],
        "skills_proposal_status",
      ),
      params.signal,
    );
    const verifiedProposal = extractProposal(proposal, true);
    if (verifiedProposal.proposalId !== submitted.proposalId) {
      throw new Error("Live proposal identity does not match the recorded local-skill submission");
    }
    const proposalStatus = verifiedProposal.status!.toLowerCase();
    if (proposalStatus !== "approved" && proposalStatus !== "current") {
      return {
        verified: false,
        deletedLocally: false,
        skillName: params.skillName,
        reason: `SkilzVolt proposal is ${proposalStatus || "not approved"}; local content remains in place.`,
      };
    }
    const skillId = verifiedProposal.skillId;
    if (!skillId) {
      throw new Error("Approved SkilzVolt proposal lacks a canonical current skill ID");
    }
    const current = await this.client.callTool(
      "skills_get",
      bindIdentityArgument(
        params.getArguments,
        skillId,
        ["skillId", "skill_id", "id"],
        "skills_get",
      ),
      params.signal,
    );
    const verifiedSkill = extractCurrentSkill(current);
    if (verifiedSkill.skillId !== skillId) {
      throw new Error("Live current skill identity does not match the approved proposal");
    }
    if (verifiedSkill.content !== local.content) {
      return {
        verified: false,
        deletedLocally: false,
        skillName: params.skillName,
        reason:
          "SkilzVolt current skill content is not a byte-for-byte match for the submitted local content.",
      };
    }

    const entries = await fs.readdir(path.dirname(path.join((await this.findLocalSkill(params.skillName)).directory, "SKILL.md")));
    if (entries.some((entry) => entry !== "SKILL.md")) {
      throw new Error(
        "Local skill contains resources beyond SKILL.md; refusing retirement until every resource has a verified vault copy",
      );
    }
    await fs.rm((await this.findLocalSkill(params.skillName)).directory, {
      recursive: true,
      force: false,
    });
    await fs.mkdir(path.dirname(this.markerPath(params.skillName)), {
      recursive: true,
      mode: 0o700,
    });
    await fs.writeFile(this.markerPath(params.skillName), `${local.hash}\n`, {
      mode: 0o600,
    });
    journal.skills[params.skillName] = {
      ...submitted,
      retiredAt: new Date().toISOString(),
    };
    await this.writeJournal(journal);
    return {
      verified: true,
      deletedLocally: true,
      skillName: params.skillName,
      sha256: local.hash,
      next: "Restart the OpenClaw gateway and begin a new session so no old skill snapshot remains.",
    };
  }
}
