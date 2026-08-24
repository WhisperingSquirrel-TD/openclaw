import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { SkilzVoltClient } from "./client.js";

const MAX_SKILL_BYTES = 256_000;
const MAX_RESOURCE_BYTES = 256_000;
const MAX_RESOURCE_COUNT = 50;

type JournalEntry = {
  hash: string;
  source?: string;
  directory?: string;
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
  workspaceDir?: string;
  extraSkillDirs?: string[];
  pluginSkillDirs?: string[];
};

type LocalSkill = {
  name: string;
  source: string;
  directory: string;
  content: string;
  hash: string;
  bytes: number;
  resources: Array<{ path: string; bytes: number; sha256: string }>;
};

type LocalSkillRoot = {
  source: string;
  directory: string;
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
  if (direct.isError === true) {
    const text = Array.isArray(direct.content)
      ? direct.content
          .map(asRecord)
          .find((entry) => entry?.type === "text" && typeof entry.text === "string")?.text
      : undefined;
    throw new Error(
      `SkilzVolt reported an MCP tool error${typeof text === "string" ? `: ${text.slice(0, 500)}` : ""}`,
    );
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
  constructor(
    private readonly client: SkilzVoltClient,
    private readonly config: MigrationConfig,
  ) {
    this.stateDir = config.stateDir ?? defaultStateDir();
  }

  private migrationDir(): string {
    return path.join(this.stateDir, "skilzvolt");
  }

  private journalPath(): string {
    return path.join(this.migrationDir(), "migration-journal.json");
  }

  private skillRoots(): string[] {
    return this.localSkillRoots().map((root) => root.directory);
  }

  private localSkillRoots(): LocalSkillRoot[] {
    const workspaceDir = this.config.workspaceDir ?? path.join(this.stateDir, "workspace");
    const extraDirs = (this.config.extraSkillDirs ?? [])
      .map((directory) => directory.trim())
      .filter(Boolean)
      .map((directory, index) => ({
        source: `extra-${index}`,
        directory: path.resolve(directory.replace(/^~(?=\/|$)/, os.homedir())),
      }));
    const pluginDirs = (this.config.pluginSkillDirs ?? [])
      .map((directory) => directory.trim())
      .filter(Boolean)
      .map((directory, index) => ({
        source: `plugin-${index}`,
        directory: path.resolve(directory),
      }));
    // Keep the active OpenClaw precedence: extra < managed < personal < project < workspace.
    // Bundled skills are intentionally excluded: they are product-provided, not local authored skills.
    return [
      ...extraDirs,
      ...pluginDirs,
      { source: "managed", directory: path.join(this.stateDir, "skills") },
      { source: "agents-personal", directory: path.join(os.homedir(), ".agents", "skills") },
      { source: "agents-project", directory: path.join(workspaceDir, ".agents", "skills") },
      { source: "workspace", directory: path.join(workspaceDir, "skills") },
    ];
  }

  private journalKey(skill: Pick<LocalSkill, "name" | "source">): string {
    return `${skill.source}:${skill.name}`;
  }

  private markerPath(skill: Pick<LocalSkill, "name" | "source">): string {
    this.assertSafeName(skill.name);
    if (!/^[a-z0-9-]+$/i.test(skill.source)) {
      throw new Error(`Invalid local skill source: ${skill.source}`);
    }
    return path.join(this.migrationDir(), "retired-skills", skill.source, skill.name);
  }

  private assertSafeName(name: string): void {
    if (!name || name === "." || name === ".." || name.includes("/") || name.includes("\\")) {
      throw new Error(`Invalid local skill name: ${name}`);
    }
  }

  private async discoverLocalSkills(): Promise<LocalSkill[]> {
    const discovered = new Map<string, LocalSkill>();
    for (const root of this.localSkillRoots()) {
      let entries;
      try {
        entries = await fs.readdir(root.directory, { withFileTypes: true });
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") continue;
        throw error;
      }
      const rootRealPath = await fs.realpath(root.directory).catch(() => undefined);
      if (!rootRealPath) continue;
      for (const entry of entries) {
        if ((!entry.isDirectory() && !entry.isSymbolicLink()) || entry.name.startsWith(".")) {
          continue;
        }
        const skillPath = path.join(root.directory, entry.name, "SKILL.md");
        try {
          const skillRealPath = await fs.realpath(skillPath);
          const relative = path.relative(rootRealPath, skillRealPath);
          if (relative.startsWith("..") || path.isAbsolute(relative)) continue;
          const stat = await fs.stat(skillPath);
          if (!stat.isFile() || stat.size > MAX_SKILL_BYTES) continue;
          const content = await fs.readFile(skillPath, "utf8");
          const resources = await this.readResources(path.join(root.directory, entry.name));
          // Later roots win, matching the active OpenClaw skill loader.
          discovered.set(entry.name, {
            name: entry.name,
            source: root.source,
            directory: path.join(root.directory, entry.name),
            content,
            hash: hashContent(content),
            bytes: Buffer.byteLength(content),
            resources,
          });
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
        }
      }
    }
    return [...discovered.values()].sort((a, b) => a.name.localeCompare(b.name));
  }

  private async readResources(
    directory: string,
    relativeDirectory = "",
  ): Promise<Array<{ path: string; bytes: number; sha256: string }>> {
    const resources: Array<{ path: string; bytes: number; sha256: string }> = [];
    const visit = async (current: string, relative: string): Promise<void> => {
      const entries = await fs.readdir(current, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.name.startsWith(".")) continue;
        const entryPath = path.join(current, entry.name);
        const entryRelative = path.join(relative, entry.name);
        if (entry.isDirectory()) {
          await visit(entryPath, entryRelative);
          continue;
        }
        if (!entry.isFile() || entryRelative === "SKILL.md") continue;
        if (resources.length >= MAX_RESOURCE_COUNT) {
          throw new Error(`Local skill has more than ${MAX_RESOURCE_COUNT} resources`);
        }
        const stat = await fs.stat(entryPath);
        if (stat.size > MAX_RESOURCE_BYTES) {
          throw new Error(`Local skill resource exceeds ${MAX_RESOURCE_BYTES} bytes: ${entryRelative}`);
        }
        const content = await fs.readFile(entryPath);
        resources.push({
          path: entryRelative,
          bytes: stat.size,
          sha256: createHash("sha256").update(content).digest("hex"),
        });
      }
    };
    await visit(directory, relativeDirectory);
    return resources.sort((a, b) => a.path.localeCompare(b.path));
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
        .access(this.markerPath(local))
        .then(() => true)
        .catch(() => false);
      skills.push({
        name,
        local: true,
        directory: local.directory,
        bytes: local.bytes,
        sha256: local.hash,
        resources: local.resources,
        resourceCoverage: local.resources.length === 0 ? "none" : "local-only-unverified",
        status: marker
          ? "retired_marker_but_local_copy_present"
          : journal.skills[this.journalKey(local)]?.submittedAt
            ? "submitted"
            : "ready",
        source: local.source,
        proposalId: journal.skills[this.journalKey(local)]?.proposalId,
      });
    }
    for (const name of this.config.organisationSkillNames) {
      if (discoveredNames.has(name)) continue;
      const marker = await fs
        .access(this.markerPath({ name, source: "configured" }))
        .then(() => true)
        .catch(() => false);
      skills.push({
        name,
        local: false,
        status: marker ? "retired" : "missing_unverified",
        proposalId: journal.skills[`configured:${name}`]?.proposalId,
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
    const result = readTextResult(await this.client.callTool("workspaces_list", {}, signal));
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
      client_ref: `${skill.source}:${skill.name}:${skill.hash}`,
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
    if (params.items.length === 0) {
      throw new Error("At least one preview candidate is required for migration submission");
    }
    const seenRefs = new Set<string>();
    for (const item of params.items) {
      if (!item.client_ref || seenRefs.has(item.client_ref)) {
        throw new Error("Each migration item must have a unique non-empty client_ref");
      }
      seenRefs.add(item.client_ref);
      const local = await this.findLocalSkill(item.name);
      const expectedRef = `${local.source}:${local.name}:${local.hash}`;
      if (item.content !== local.content || item.client_ref !== expectedRef) {
        throw new Error(
          `Migration item ${item.name} no longer matches the discovered local skill or stable client_ref`,
        );
      }
    }
    const preview = await this.client.callTool(
      "skills_migration_preview",
      { workspace_id: workspaceId, skills: params.items },
      params.signal,
    );
    const previewBody = readTextResult(preview);
    const previewResults = Array.isArray(previewBody.results) ? previewBody.results : [];
    const newRefs = new Set(
      previewResults
        .map(asRecord)
        .filter((item): item is Record<string, unknown> => Boolean(item))
        .filter((item) => item.classification === "new")
        .map((item) => readNamedString(item, ["client_ref", "clientRef"]))
        .filter((ref): ref is string => Boolean(ref)),
    );
    const approvedItems = params.items.filter((item) => newRefs.has(item.client_ref));
    if (approvedItems.length === 0) {
      return {
        submitted: false,
        migrationOperationId: params.migrationOperationId,
        workspaceId,
        preview,
        outcomes: params.items.map((item) => ({
          client_ref: item.client_ref,
          skill_name: item.name,
          status: "not_submitted_not_new",
        })),
      };
    }
    const result = await this.client.callTool(
      "skills_migration_submit",
      {
        workspace_id: workspaceId,
        migration_operation_id: params.migrationOperationId,
        skills: approvedItems,
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
        const journalKey = this.journalKey(local);
        journal.skills[journalKey] = {
          ...journal.skills[journalKey],
          hash: local.hash,
          source: local.source,
          directory: local.directory,
          submittedAt: new Date().toISOString(),
          proposalId,
          workspaceId,
          operationId: params.migrationOperationId,
          clientRef,
        };
      }
    }
    await this.writeJournal(journal);
    return {
      submitted: true,
      workspaceId,
      migrationOperationId: params.migrationOperationId,
      preview,
      result,
      skipped: params.items
        .filter((item) => !newRefs.has(item.client_ref))
        .map((item) => ({ client_ref: item.client_ref, skill_name: item.name })),
    };
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
    journal.skills[`configured:${params.skillName}`] = {
      hash: local.hash,
      source: local.source,
      directory: local.directory,
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
    this.assertSafeName(params.skillName);
    const journal = await this.readJournal();
    const local = await this.readSkill(params.skillName);
    const submitted =
      journal.skills[this.journalKey(local)] ??
      journal.skills[`configured:${params.skillName}`];
    if (!submitted?.submittedAt || !submitted.proposalId) {
      throw new Error("No recorded SkilzVolt submission exists for this local skill");
    }
    if (
      submitted.source &&
      (submitted.source !== local.source || submitted.directory !== local.directory)
    ) {
      throw new Error(
        "The recorded migration source no longer matches the active local skill; refusing retirement",
      );
    }
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
    await fs.mkdir(path.dirname(this.markerPath(local)), {
      recursive: true,
      mode: 0o700,
    });
    await fs.writeFile(this.markerPath(local), `${local.hash}\n`, {
      mode: 0o600,
    });
    journal.skills[this.journalKey(local)] = {
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
