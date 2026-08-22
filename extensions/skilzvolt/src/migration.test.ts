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
      if (name === "skill_proposals_get") {
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
      fs.readFile(path.join(stateDir, "skilzvolt", "retired-skills", "app-build"), "utf8"),
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
});
