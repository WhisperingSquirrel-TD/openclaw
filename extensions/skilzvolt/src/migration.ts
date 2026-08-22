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
  proposal?: Record<string, string>;
};

type Journal = {
  version: 1;
  skills: Record<string, JournalEntry>;
};

export type MigrationConfig = {
  organisationSkillNames: string[];
  stateDir?: string;
};

function defaultStateDir(): string {
  return (
    process.env.OPENCLAW_STATE_DIR?.trim() ||
    path.join(os.homedir(), ".openclaw")
  );
}

function normalizedContent(value: string): string {
  return value.replace(/\r\n/g, "\n").trim();
}

function hashContent(value: string): string {
  return createHash("sha256").update(normalizedContent(value)).digest("hex");
}

function collectStrings(value: unknown, output: string[], depth = 0): void {
  if (depth > 12 || output.length > 5000) {
    return;
  }
  if (typeof value === "string") {
    output.push(value);
    if (
      (value.startsWith("{") || value.startsWith("[")) &&
      value.length <= MAX_SKILL_BYTES * 2
    ) {
      try {
        collectStrings(JSON.parse(value), output, depth + 1);
      } catch {
        // MCP text content is not necessarily JSON.
      }
    }
    return;
  }
  if (Array.isArray(value)) {
    for (const entry of value) {
      collectStrings(entry, output, depth + 1);
    }
    return;
  }
  if (value && typeof value === "object") {
    for (const entry of Object.values(value as Record<string, unknown>)) {
      collectStrings(entry, output, depth + 1);
    }
  }
}

function proposalSummary(value: unknown): Record<string, string> {
  const wanted = new Set([
    "proposalId",
    "proposal_id",
    "skillId",
    "skill_id",
    "status",
    "reviewStatus",
    "review_status",
  ]);
  const summary: Record<string, string> = {};
  const visit = (entry: unknown, depth = 0): void => {
    if (depth > 8 || !entry || typeof entry !== "object") {
      return;
    }
    if (Array.isArray(entry)) {
      for (const item of entry) {
        visit(item, depth + 1);
      }
      return;
    }
    for (const [key, child] of Object.entries(
      entry as Record<string, unknown>,
    )) {
      if (
        wanted.has(key) &&
        (typeof child === "string" || typeof child === "number")
      ) {
        summary[key] = String(child).slice(0, 200);
      } else {
        visit(child, depth + 1);
      }
    }
  };
  visit(value);
  return summary;
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

  private skillDir(name: string): string {
    this.assertAllowedName(name);
    return path.join(this.stateDir, "skills", name);
  }

  private markerPath(name: string): string {
    this.assertAllowedName(name);
    return path.join(this.migrationDir(), "retired-skills", name);
  }

  private assertAllowedName(name: string): void {
    if (!this.allowedNames.has(name)) {
      throw new Error(
        `Skill is not in the configured organisation migration set: ${name}`,
      );
    }
  }

  private async readJournal(): Promise<Journal> {
    try {
      const parsed = JSON.parse(
        await fs.readFile(this.journalPath(), "utf8"),
      ) as Journal;
      if (
        parsed?.version === 1 &&
        parsed.skills &&
        typeof parsed.skills === "object"
      ) {
        return parsed;
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
        throw new Error(
          "SkilzVolt migration journal is malformed or unreadable",
        );
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

  private async readSkill(
    name: string,
  ): Promise<{ content: string; hash: string; bytes: number }> {
    const skillPath = path.join(this.skillDir(name), "SKILL.md");
    const stat = await fs.stat(skillPath);
    if (!stat.isFile() || stat.size > MAX_SKILL_BYTES) {
      throw new Error(
        `Local skill is missing or exceeds ${MAX_SKILL_BYTES} bytes: ${name}`,
      );
    }
    const content = await fs.readFile(skillPath, "utf8");
    return {
      content,
      hash: hashContent(content),
      bytes: Buffer.byteLength(content),
    };
  }

  async inventory(): Promise<unknown> {
    const journal = await this.readJournal();
    const skills = [];
    for (const name of this.config.organisationSkillNames) {
      const marker = await fs
        .access(this.markerPath(name))
        .then(() => true)
        .catch(() => false);
      try {
        const local = await this.readSkill(name);
        skills.push({
          name,
          local: true,
          bytes: local.bytes,
          sha256: local.hash,
          status: marker
            ? "retired_marker_but_local_copy_present"
            : journal.skills[name]?.submittedAt
              ? "submitted"
              : "ready",
          proposal: journal.skills[name]?.proposal,
        });
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") {
          skills.push({
            name,
            local: false,
            status: marker ? "retired" : "missing_unverified",
            proposal: journal.skills[name]?.proposal,
          });
          continue;
        }
        throw error;
      }
    }
    return { mode: "dry-run", skills };
  }

  async submit(params: {
    skillName: string;
    createArguments: Record<string, unknown>;
    contentParameter: string;
    signal?: AbortSignal;
  }): Promise<unknown> {
    this.assertAllowedName(params.skillName);
    const local = await this.readSkill(params.skillName);
    const tools = await this.client.listTools(params.signal);
    const createTool = tools.find((tool) => tool.name === "skills_create");
    if (!createTool) {
      throw new Error("SkilzVolt did not advertise skills_create");
    }
    const properties =
      createTool.inputSchema?.properties &&
      typeof createTool.inputSchema.properties === "object"
        ? (createTool.inputSchema.properties as Record<string, unknown>)
        : undefined;
    if (!properties || !Object.hasOwn(properties, params.contentParameter)) {
      throw new Error(
        `contentParameter is not present in the live SkilzVolt skills_create schema: ${params.contentParameter}`,
      );
    }
    const createArguments = structuredClone(params.createArguments);
    createArguments[params.contentParameter] = local.content;
    const result = await this.client.callTool(
      "skills_create",
      createArguments,
      params.signal,
    );
    const journal = await this.readJournal();
    journal.skills[params.skillName] = {
      hash: local.hash,
      submittedAt: new Date().toISOString(),
      proposal: proposalSummary(result),
    };
    await this.writeJournal(journal);
    return {
      submitted: true,
      deletedLocally: false,
      skillName: params.skillName,
      sha256: local.hash,
      proposal: journal.skills[params.skillName].proposal,
      result,
      next: "Wait for approval/current publication, then run verify_and_retire with skills_get arguments.",
    };
  }

  async verifyAndRetire(params: {
    skillName: string;
    getArguments: Record<string, unknown>;
    signal?: AbortSignal;
  }): Promise<unknown> {
    this.assertAllowedName(params.skillName);
    const journal = await this.readJournal();
    const submitted = journal.skills[params.skillName];
    if (!submitted?.submittedAt) {
      throw new Error(
        "No recorded SkilzVolt submission exists for this local skill",
      );
    }
    const local = await this.readSkill(params.skillName);
    if (local.hash !== submitted.hash) {
      throw new Error(
        "Local skill changed after submission; submit the new content before retiring it",
      );
    }
    const current = await this.client.callTool(
      "skills_get",
      params.getArguments,
      params.signal,
    );
    const strings: string[] = [];
    collectStrings(current, strings);
    const matches = strings.some(
      (value) => normalizedContent(value) === normalizedContent(local.content),
    );
    if (!matches) {
      return {
        verified: false,
        deletedLocally: false,
        skillName: params.skillName,
        reason:
          "SkilzVolt current skill content does not exactly match the submitted local content.",
      };
    }

    const entries = await fs.readdir(this.skillDir(params.skillName));
    if (entries.some((entry) => entry !== "SKILL.md")) {
      throw new Error(
        "Local skill contains resources beyond SKILL.md; refusing retirement until every resource has a verified vault copy",
      );
    }
    await fs.rm(this.skillDir(params.skillName), {
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
