import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { SkilzVoltClient } from "./client.js";
import { SkilzVoltMigrationManager } from "./migration.js";

const content = "# App build\n\nUse the governed build workflow.\n";

async function setup() {
  const stateDir = await fs.mkdtemp(path.join(os.tmpdir(), "skilzvolt-"));
  const skillDir = path.join(stateDir, "skills", "app-build");
  await fs.mkdir(skillDir, { recursive: true });
  await fs.writeFile(path.join(skillDir, "SKILL.md"), content);
  return { stateDir, skillDir };
}

function fakeClient(params: { current: string; proposalStatus?: string }): SkilzVoltClient {
  return {
    listTools: async () => [
      {
        name: "skills_create",
        inputSchema: { properties: { content: { type: "string" } } },
      },
    ],
    callTool: async (name: string, args: Record<string, unknown>) => {
      if (name === "skills_create") {
        expect(args.content).toBe(content);
        return { proposal: { id: "proposal-1" } };
      }
      if (name === "skills_proposal_status") {
        return {
          proposal: {
            id: "proposal-1",
            status: params.proposalStatus ?? "approved",
            skillId: "skill-1",
          },
        };
      }
      return { skill: { id: "skill-1", content: params.current } };
    },
  } as unknown as SkilzVoltClient;
}

describe("SkilzVoltMigrationManager", () => {
  it("submits exact local content without deleting it", async () => {
    const { stateDir, skillDir } = await setup();
    const manager = new SkilzVoltMigrationManager(fakeClient({ current: content }), {
      stateDir,
      organisationSkillNames: ["app-build"],
    });

    const result = (await manager.submit({
      skillName: "app-build",
      createArguments: { workspace_id: "workspace-1", name: "app-build" },
      contentParameter: "content",
    })) as { deletedLocally: boolean; proposalId: string };
    expect(result.deletedLocally).toBe(false);
    expect(result.proposalId).toBe("proposal-1");
    await expect(fs.stat(path.join(skillDir, "SKILL.md"))).resolves.toBeTruthy();
  });

  it("does not retire a pending or mismatched vault copy", async () => {
    const { stateDir, skillDir } = await setup();
    const manager = new SkilzVoltMigrationManager(
      fakeClient({ current: "# different\n", proposalStatus: "pending" }),
      { stateDir, organisationSkillNames: ["app-build"] },
    );
    await manager.submit({
      skillName: "app-build",
      createArguments: { workspace_id: "workspace-1", name: "app-build" },
      contentParameter: "content",
    });
    const result = (await manager.verifyAndRetire({
      skillName: "app-build",
      proposalStatusArguments: { proposal_id: "proposal-1" },
      getArguments: { id: "skill-1" },
    })) as { verified: boolean; deletedLocally: boolean };
    expect(result).toEqual({
      verified: false,
      deletedLocally: false,
      skillName: "app-build",
      reason: expect.any(String),
    });
    await expect(fs.stat(path.join(skillDir, "SKILL.md"))).resolves.toBeTruthy();
  });

  it("retires only after an exact current-content readback and writes a marker", async () => {
    const { stateDir, skillDir } = await setup();
    const manager = new SkilzVoltMigrationManager(fakeClient({ current: content }), {
      stateDir,
      organisationSkillNames: ["app-build"],
    });
    await manager.submit({
      skillName: "app-build",
      createArguments: { workspace_id: "workspace-1", name: "app-build" },
      contentParameter: "content",
    });
    const result = (await manager.verifyAndRetire({
      skillName: "app-build",
      proposalStatusArguments: { proposal_id: "proposal-1" },
      getArguments: { id: "skill-1" },
    })) as { verified: boolean; deletedLocally: boolean };
    expect(result.verified).toBe(true);
    expect(result.deletedLocally).toBe(true);
    await expect(fs.stat(skillDir)).rejects.toMatchObject({ code: "ENOENT" });
    await expect(
      fs.readFile(
        path.join(stateDir, "skilzvolt", "retired-skills", "managed", "app-build"),
        "utf8",
      ),
    ).resolves.toMatch(/^[a-f0-9]{64}\n$/);
  });

  it("does not accept whitespace-normalized content as an exact vault match", async () => {
    const { stateDir, skillDir } = await setup();
    const manager = new SkilzVoltMigrationManager(fakeClient({ current: `${content}\n` }), {
      stateDir,
      organisationSkillNames: ["app-build"],
    });
    await manager.submit({
      skillName: "app-build",
      createArguments: { workspace_id: "workspace-1", name: "app-build" },
      contentParameter: "content",
    });
    const result = (await manager.verifyAndRetire({
      skillName: "app-build",
      proposalStatusArguments: { proposal_id: "proposal-1" },
      getArguments: { id: "skill-1" },
    })) as { verified: boolean };
    expect(result.verified).toBe(false);
    await expect(fs.stat(path.join(skillDir, "SKILL.md"))).resolves.toBeTruthy();
  });

  it("previews the full discovered inventory and only submits entries classified as new", async () => {
    const { stateDir, skillDir } = await setup();
    await fs.mkdir(path.join(skillDir, "resources"), { recursive: true });
    await fs.writeFile(path.join(skillDir, "resources", "runbook.txt"), "reference");
    const calls: Array<{ name: string; args: Record<string, unknown> }> = [];
    const client = {
      callTool: async (name: string, args: Record<string, unknown>) => {
        calls.push({ name, args });
        if (name === "skills_migration_preview") {
          return {
            structuredContent: {
              results: [{ client_ref: clientRef, classification: "new" }],
            },
          };
        }
        if (name === "skills_migration_submit") {
          return {
            structuredContent: {
              results: [
                {
                  client_ref: clientRef,
                  skill_name: "app-build",
                  proposal_id: "proposal-2",
                  status: "processing",
                },
              ],
            },
          };
        }
        return {};
      },
    } as unknown as SkilzVoltClient;
    const manager = new SkilzVoltMigrationManager(client, {
      stateDir,
      organisationSkillNames: [],
    });
    const clientRef = `managed:app-build:${createHash("sha256").update(content).digest("hex")}`;
    const inventory = (await manager.inventory()) as {
      scope: string;
      skills: Array<{ name: string; resourceCoverage: string; resources: unknown[] }>;
    };
    expect(inventory.scope).toBe("all-local-skill-roots");
    expect(inventory.skills[0]).toMatchObject({
      name: "app-build",
      resourceCoverage: "local-only-unverified",
    });
    expect(inventory.skills[0]?.resources).toHaveLength(1);

    await manager.submitAll({
      workspaceId: "workspace-1",
      migrationOperationId: "operation-1",
      items: [{ client_ref: clientRef, name: "app-build", content: "" }],
    });
    expect(calls.map((call) => call.name)).toEqual([
      "skills_migration_preview",
      "skills_migration_submit",
    ]);
    await expect(fs.stat(path.join(skillDir, "SKILL.md"))).resolves.toBeTruthy();
  });

  it("does not submit non-new preview results and recovers uncertain requests by stable identifiers", async () => {
    const { stateDir } = await setup();
    const clientRef = `managed:app-build:${createHash("sha256").update(content).digest("hex")}`;
    const calls: string[] = [];
    const client = {
      callTool: async (name: string) => {
        calls.push(name);
        if (name === "skills_migration_preview") {
          return {
            structuredContent: {
              results: [{ client_ref: clientRef, classification: "already current" }],
            },
          };
        }
        if (name === "skills_migration_recover") {
          return { structuredContent: { found: true, result: { proposal_id: "proposal-1" } } };
        }
        return {};
      },
    } as unknown as SkilzVoltClient;
    const manager = new SkilzVoltMigrationManager(client, {
      stateDir,
      organisationSkillNames: [],
    });
    const result = (await manager.submitAll({
      workspaceId: "workspace-1",
      migrationOperationId: "operation-1",
      items: [{ client_ref: clientRef, name: "app-build", content }],
    })) as { submitted: boolean };
    expect(result.submitted).toBe(false);
    expect(calls).toEqual(["skills_migration_preview"]);
    await expect(
      manager.recover({
        workspaceId: "workspace-1",
        migrationOperationId: "operation-1",
        clientRef,
      }),
    ).resolves.toMatchObject({ structuredContent: { found: true } });
  });

  it("uses the active workspace skill when a lower-precedence local copy has the same name", async () => {
    const { stateDir } = await setup();
    const workspaceDir = await fs.mkdtemp(path.join(os.tmpdir(), "skilzvolt-workspace-"));
    const workspaceSkillDir = path.join(workspaceDir, "skills", "app-build");
    const workspaceContent = "# Workspace build\n\nThis copy is active.\n";
    await fs.mkdir(workspaceSkillDir, { recursive: true });
    await fs.writeFile(path.join(workspaceSkillDir, "SKILL.md"), workspaceContent);
    const manager = new SkilzVoltMigrationManager({} as SkilzVoltClient, {
      stateDir,
      workspaceDir,
      organisationSkillNames: [],
    });

    const inventory = (await manager.inventory()) as {
      skills: Array<{ name: string; source: string; sha256: string }>;
    };
    expect(inventory.skills).toHaveLength(1);
    expect(inventory.skills[0]).toMatchObject({
      name: "app-build",
      source: "workspace",
      sha256: createHash("sha256").update(workspaceContent).digest("hex"),
    });
  });

  it("splits large migration previews into bounded requests", async () => {
    const { stateDir, skillDir } = await setup();
    const secondSkillDir = path.join(stateDir, "skills", "second-skill");
    await fs.mkdir(secondSkillDir, { recursive: true });
    const firstContent = `${"# first\n"}${"a".repeat(190_000)}`;
    const secondContent = `${"# second\n"}${"b".repeat(190_000)}`;
    await fs.writeFile(path.join(skillDir, "SKILL.md"), firstContent);
    await fs.writeFile(path.join(secondSkillDir, "SKILL.md"), secondContent);
    const previewBatchSizes: number[] = [];
    const client = {
      callTool: async (name: string, args: Record<string, unknown>) => {
        if (name === "skills_migration_preview") {
          previewBatchSizes.push((args.skills as unknown[]).length);
          return { structuredContent: { results: [] } };
        }
        return {};
      },
    } as unknown as SkilzVoltClient;
    const manager = new SkilzVoltMigrationManager(client, {
      stateDir,
      organisationSkillNames: [],
    });

    await manager.previewAll({ workspaceId: "workspace-1" });

    expect(previewBatchSizes).toEqual([1, 1]);
  });
});
