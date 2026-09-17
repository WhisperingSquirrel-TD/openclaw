import { EventEmitter } from "node:events";
import os from "node:os";
import path from "node:path";
import { PassThrough } from "node:stream";
import { describe, expect, it, vi } from "vitest";

const { spawnMock } = vi.hoisted(() => ({ spawnMock: vi.fn() }));

vi.mock("node:child_process", async (importOriginal) => ({
  ...(await importOriginal<typeof import("node:child_process")>()),
  spawn: spawnMock,
}));
vi.mock("node:fs/promises", () => ({
  lstat: vi.fn(async (pathname: string) => {
    const isFile =
      pathname === "/usr/bin/python3" ||
      pathname.endsWith(".py") ||
      pathname.endsWith(".json") ||
      pathname.endsWith(".lock");
    return {
      isFile: () => isFile,
      isDirectory: () => !isFile,
      isSymbolicLink: () => false,
      uid:
        pathname === "/usr/bin/python3" ||
        pathname === "/opt/openclaw" ||
        pathname.startsWith("/opt/openclaw/")
          ? 0
          : (process.getuid?.() ?? 0),
      gid: process.getgid?.() ?? 0,
      mode: 0o755,
    };
  }),
  realpath: vi.fn(async (pathname: string) => pathname),
}));

import {
  createExpenseBridgeEnvironment,
  createExpenseSharePointTool,
  runExpenseBridge,
} from "./expense-tool.js";

function resultText(result: { content: Array<{ type: string; text?: string }> }) {
  return result.content
    .filter((item): item is { type: string; text: string } => typeof item.text === "string")
    .map((item) => item.text)
    .join("\n");
}

describe("expense_sharepoint", () => {
  it("passes the verified default Pi state through the actual fixed child runner", async () => {
    spawnMock.mockClear();
    const homedirSpy = vi.spyOn(os, "homedir").mockReturnValue("/home/tomdean88");
    const originalHome = process.env.HOME;
    const originalState = process.env.OPENCLAW_STATE_DIR;
    const originalOpenClawHome = process.env.OPENCLAW_HOME;
    const originalSecret = process.env.EXPENSE_RUNNER_TEST_SECRET;
    const home = os.homedir();
    const stateDir = path.join(home, ".openclaw");
    process.env.HOME = home;
    process.env.OPENCLAW_STATE_DIR = stateDir;
    delete process.env.OPENCLAW_HOME;
    process.env.EXPENSE_RUNNER_TEST_SECRET = "must-not-reach-child";
    const child = Object.assign(new EventEmitter(), {
      stdin: new PassThrough(),
      stdout: new PassThrough(),
      stderr: new PassThrough(),
      kill: vi.fn(),
    });
    spawnMock.mockImplementationOnce(() => {
      queueMicrotask(() => {
        child.stdout.end('{"ok":true}');
        child.emit("close", 0);
      });
      return child;
    });
    try {
      await expect(runExpenseBridge({ action: "read_expense_workbook" })).resolves.toEqual({
        ok: true,
      });
    } finally {
      if (originalHome === undefined) delete process.env.HOME;
      else process.env.HOME = originalHome;
      if (originalState === undefined) delete process.env.OPENCLAW_STATE_DIR;
      else process.env.OPENCLAW_STATE_DIR = originalState;
      if (originalOpenClawHome === undefined) delete process.env.OPENCLAW_HOME;
      else process.env.OPENCLAW_HOME = originalOpenClawHome;
      if (originalSecret === undefined) delete process.env.EXPENSE_RUNNER_TEST_SECRET;
      else process.env.EXPENSE_RUNNER_TEST_SECRET = originalSecret;
      homedirSpy.mockRestore();
    }

    expect(spawnMock).toHaveBeenCalledWith(
      "/usr/bin/python3",
      ["/opt/openclaw/expense-sharepoint/seer_finance/agent_expense_bridge.py"],
      expect.objectContaining({
        cwd: "/opt/openclaw/expense-sharepoint",
        env: expect.objectContaining({
          HOME: home,
          OPENCLAW_STATE_DIR: stateDir,
          SEER_FINANCE_SHAREPOINT_QUEUE: path.join(stateDir, "sharepoint-queue.json"),
          SEER_FINANCE_SHAREPOINT_RESULTS: path.join(stateDir, "sharepoint-queue-results.json"),
          SEER_FINANCE_SHAREPOINT_CACHE: path.join(stateDir, "workspace", "sharepoint-cache"),
          SEER_FINANCE_SHAREPOINT_QUEUE_LOCK: path.join(
            stateDir,
            "integrations",
            "microsoft",
            "sp-queue.lock",
          ),
          SEER_FINANCE_SHAREPOINT_MUTATION_JOURNAL: path.join(
            stateDir,
            "seer-finance-mutation-journal.json",
          ),
          SEER_FINANCE_EXPENSE_MEDIA_ROOT: path.join(stateDir, "media", "inbound"),
          PYTHONPATH: "/opt/openclaw/expense-sharepoint/vendor:/opt/openclaw/expense-sharepoint",
          PYTHONNOUSERSITE: "1",
        }),
      }),
    );
    expect(
      (spawnMock.mock.calls[0]?.[2] as { env: Record<string, string> }).env,
    ).not.toHaveProperty("PATH");
    expect(
      (spawnMock.mock.calls[0]?.[2] as { env: Record<string, string> }).env,
    ).not.toHaveProperty("EXPENSE_RUNNER_TEST_SECRET");
  });

  it("fails closed for an unsupported custom profile before a child can spawn", async () => {
    spawnMock.mockClear();
    const originalHome = process.env.HOME;
    const originalState = process.env.OPENCLAW_STATE_DIR;
    const originalOpenClawHome = process.env.OPENCLAW_HOME;
    process.env.HOME = os.homedir();
    process.env.OPENCLAW_STATE_DIR = "/var/lib/openclaw/custom-profile";
    delete process.env.OPENCLAW_HOME;
    try {
      await expect(runExpenseBridge({ action: "read_expense_workbook" })).resolves.toMatchObject({
        ok: false,
        result: {
          accepted: false,
          complete: false,
          error_code: "unsupported_state_layout",
          blocker: expect.stringContaining("unsupported_state_layout"),
        },
      });
    } finally {
      if (originalHome === undefined) delete process.env.HOME;
      else process.env.HOME = originalHome;
      if (originalState === undefined) delete process.env.OPENCLAW_STATE_DIR;
      else process.env.OPENCLAW_STATE_DIR = originalState;
      if (originalOpenClawHome === undefined) delete process.env.OPENCLAW_HOME;
      else process.env.OPENCLAW_HOME = originalOpenClawHome;
    }
    expect(spawnMock).not.toHaveBeenCalled();
    expect(() =>
      createExpenseBridgeEnvironment({
        HOME: os.homedir(),
        OPENCLAW_HOME: "/another-service-user",
        OPENCLAW_STATE_DIR: path.join(os.homedir(), ".openclaw"),
      }),
    ).toThrow(/unsupported_state_layout/);
  });

  it("builds a minimal child environment for only the default service profile", () => {
    const home = os.homedir();
    const stateDir = path.join(home, ".openclaw");
    const environment = createExpenseBridgeEnvironment({
      HOME: home,
      OPENCLAW_STATE_DIR: stateDir,
      PATH: "/attacker/bin",
      PYTHONPATH: "/attacker/python",
      SECRET_TOKEN: "must-not-leak",
    });

    expect(environment).toEqual({
      HOME: home,
      OPENCLAW_STATE_DIR: stateDir,
      SEER_FINANCE_SHAREPOINT_QUEUE: path.join(stateDir, "sharepoint-queue.json"),
      SEER_FINANCE_SHAREPOINT_RESULTS: path.join(stateDir, "sharepoint-queue-results.json"),
      SEER_FINANCE_SHAREPOINT_CACHE: path.join(stateDir, "workspace", "sharepoint-cache"),
      SEER_FINANCE_SHAREPOINT_QUEUE_LOCK: path.join(
        stateDir,
        "integrations",
        "microsoft",
        "sp-queue.lock",
      ),
      SEER_FINANCE_SHAREPOINT_MUTATION_JOURNAL: path.join(
        stateDir,
        "seer-finance-mutation-journal.json",
      ),
      SEER_FINANCE_EXPENSE_MEDIA_ROOT: path.join(stateDir, "media", "inbound"),
      PYTHONPATH: "/opt/openclaw/expense-sharepoint/vendor:/opt/openclaw/expense-sharepoint",
      PYTHONNOUSERSITE: "1",
      LANG: "C.UTF-8",
      LC_ALL: "C.UTF-8",
    });
    expect(environment).not.toHaveProperty("PATH");
    expect(environment).not.toHaveProperty("SECRET_TOKEN");
  });

  it("exposes only the owner-authorized, fixed expense operations without a TOTP parameter", () => {
    const run = vi.fn();
    const tool = createExpenseSharePointTool({ run, workspaceDir: "/workspace" });

    expect(tool.ownerOnly).toBe(true);
    expect(tool.name).toBe("expense_sharepoint");
    expect(JSON.stringify(tool.parameters)).not.toContain("totp");
    expect(JSON.stringify(tool.parameters)).not.toContain("command");
    expect(JSON.stringify(tool.parameters)).not.toContain("sharepointPath");
  });

  it("passes canonical workbook reads through the fixed bridge", async () => {
    const run = vi.fn().mockResolvedValue({ ok: true, snapshot: { etag: '"etag-1"' } });
    const tool = createExpenseSharePointTool({ run, workspaceDir: "/workspace" });

    const result = await tool.execute("call", { action: "read_expense_workbook" });

    expect(run).toHaveBeenCalledWith({ action: "read_expense_workbook" }, undefined);
    expect(resultText(result)).toContain('"etag"');
  });

  it("allows source-linked expense capture while fixing source and workbook ownership", async () => {
    const run = vi.fn().mockResolvedValue({
      ok: true,
      result: { operation: "capture_expense", accepted: true, verified: false, complete: false },
    });
    const tool = createExpenseSharePointTool({ run, workspaceDir: "/workspace" });

    await tool.execute("call", {
      action: "capture_expense",
      sourceRef: "whatsapp:lidl-2026-09-16",
      facts: {
        supplier: "Lidl",
        amountPence: 4218,
        currency: "EUR",
        observedTimestamp: "2026-09-16T10:00:00Z",
        financeLedgerRef: "ledger-1",
        settlementState: "company_card",
      },
    });

    expect(run).toHaveBeenCalledWith(
      {
        action: "capture_expense",
        source_ref: "whatsapp:lidl-2026-09-16",
        facts: {
          supplier: "Lidl",
          amount_pence: 4218,
          currency: "EUR",
          observed_timestamp: "2026-09-16T10:00:00Z",
          finance_ledger_ref: "ledger-1",
          settlement_state: "company_card",
        },
      },
      undefined,
    );
  });

  it("reports an accepted-but-pending receipt as incomplete rather than claiming success", async () => {
    const run = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        operation: "upload_binary",
        accepted: true,
        verified: false,
        complete: false,
        path: "/Expenses/Meals & Refreshments/lidl.jpg",
        blocker: "receipt readback pending",
      },
    });
    const tool = createExpenseSharePointTool({ run, workspaceDir: "/workspace" });

    const result = await tool.execute("call", {
      action: "upload_expense_receipt",
      sourceRef: "whatsapp:lidl-2026-09-16",
      receiptMediaPath: "/home/tom/.openclaw/media/inbound/lidl.jpg",
      receiptFolder: "Meals & Refreshments",
    });

    expect(run).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "upload_expense_receipt",
        source_ref: "whatsapp:lidl-2026-09-16",
        receipt_media_path: "/home/tom/.openclaw/media/inbound/lidl.jpg",
        receipt_folder: "Meals & Refreshments",
      }),
      undefined,
    );
    expect(resultText(result)).toContain('"complete": false');
  });

  it("allows only the existing Expenses receipt folder enum", async () => {
    const run = vi.fn().mockResolvedValue({ ok: true });
    const tool = createExpenseSharePointTool({ run, workspaceDir: "/workspace" });
    const approvedFolders = [
      "Anthropic",
      "ChatGPT",
      "Meals & Refreshments",
      "Not organised",
      "OpenAI API",
      "Receipts",
      "Replit",
      "SEER",
    ];
    for (const receiptFolder of approvedFolders) {
      await tool.execute("call", {
        action: "upload_expense_receipt",
        sourceRef: "receipt-1",
        receiptMediaPath: "/home/tom/.openclaw/media/inbound/receipt.jpg",
        receiptFolder,
      });
    }
    expect(run).toHaveBeenCalledTimes(approvedFolders.length);
    for (const receiptFolder of approvedFolders) {
      expect(run).toHaveBeenCalledWith(
        expect.objectContaining({ receipt_folder: receiptFolder }),
        undefined,
      );
    }
    for (const receiptFolder of [
      "../Receipts",
      "Receipts/2026",
      "Receipts%2F2026",
      "Meals & Refreshments/..",
    ]) {
      await expect(
        tool.execute("call", {
          action: "upload_expense_receipt",
          sourceRef: "receipt-1",
          receiptMediaPath: "/home/tom/.openclaw/media/inbound/receipt.jpg",
          receiptFolder,
        }),
      ).rejects.toThrow(/receiptFolder must be one of/);
    }
  });

  it("refuses raw workbook replacement, unsupported actions, and unsupported fact keys", async () => {
    const run = vi.fn();
    const tool = createExpenseSharePointTool({ run, workspaceDir: "/workspace" });

    await expect(
      tool.execute("call", {
        action: "upload_expense_receipt",
        sourceRef: "receipt-1",
        receiptMediaPath: "/etc/shadow",
        receiptFolder: "Receipts",
      }),
    ).resolves.toBeTruthy();
    await expect(
      tool.execute("call", {
        action: "capture_expense",
        sourceRef: "receipt-1",
        facts: { supplier: "Lidl", lineItems: ["not supported"] },
      }),
    ).rejects.toThrow(/unsupported expense fact/);
    await expect(
      tool.execute("call", { action: "write_expense_workbook", contentBase64: "replacement" }),
    ).rejects.toThrow(/action/);
    expect(run).toHaveBeenCalledTimes(1);
    expect(run).toHaveBeenCalledWith(
      {
        action: "upload_expense_receipt",
        source_ref: "receipt-1",
        receipt_media_path: "/etc/shadow",
        receipt_folder: "Receipts",
      },
      undefined,
    );
  });

  it("does not expose mail, messaging, shell, or arbitrary file actions", () => {
    const tool = createExpenseSharePointTool({ run: vi.fn(), workspaceDir: "/workspace" });
    const schema = JSON.stringify(tool.parameters);

    for (const forbidden of [
      "send_email",
      "send_message",
      "exec",
      "shell",
      "read_file",
      "delete",
      "write_expense_workbook",
      "contentSha256",
      "contentBase64",
      "receiptName",
      "mimeType",
    ]) {
      expect(schema).not.toContain(forbidden);
    }
    expect(schema).toContain("receiptMediaPath");
    expect(schema).toContain("receiptFolder");
    expect(schema).not.toContain("destinationPath");
    expect(schema).toContain("observedTimestamp");
    expect(schema).toContain("financeLedgerRef");
  });

  it("documents that Telegram photos use the inbound media path directly", () => {
    const tool = createExpenseSharePointTool({ run: vi.fn(), workspaceDir: "/workspace" });
    const schema = JSON.stringify(tool.parameters);

    expect(schema).toContain("Telegram photo");
    expect(schema).toContain("[media attached:");
    expect(schema).toContain("receiptMediaPath");
  });
});
