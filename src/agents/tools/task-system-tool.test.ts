import { createServer } from "node:http";
import { afterEach, describe, expect, it } from "vitest";
import { createTaskSystemTool } from "./task-system-tool.js";

const servers: Array<ReturnType<typeof createServer>> = [];

afterEach(async () => {
  await Promise.all(
    servers
      .splice(0)
      .map(
        (server) =>
          new Promise<void>((resolve, reject) =>
            server.close((error) => (error ? reject(error) : resolve())),
          ),
      ),
  );
});

describe("task_system brief_intake bridge", () => {
  it("forwards the chat fresh-Outlook brief unchanged to the bounded intake route", async () => {
    const expectedPayload = {
      brief: "Create an unsent fresh Outlook draft... standalone new message, not a reply...",
      idempotency_key: "bridge-fresh-outlook-regression-v1",
    };
    let observed: { method?: string; path?: string; authorization?: string; payload?: unknown } =
      {};
    const server = createServer(async (req, res) => {
      const chunks: Buffer[] = [];
      for await (const chunk of req) {
        chunks.push(Buffer.from(chunk));
      }
      observed = {
        method: req.method,
        path: req.url,
        authorization: req.headers.authorization,
        payload: JSON.parse(Buffer.concat(chunks).toString("utf8")),
      };
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          interpretation: { work_type: "email_new_draft" },
          context_loading_contract: {
            reply_mode: "standalone_new_message",
            context_requirements: [{ category: "verified_recipient_identity", required: true }],
          },
        }),
      );
    });
    servers.push(server);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    if (!address || typeof address === "string") {
      throw new Error("test server address unavailable");
    }

    const tool = createTaskSystemTool({
      defaultBaseUrl: `http://127.0.0.1:${address.port}`,
      defaultAuthToken: "test-token",
    });
    const result = await tool.execute("test-call", {
      action: "brief_intake",
      payload: expectedPayload,
    });

    expect(observed).toEqual({
      method: "POST",
      path: "/task-intake/brief",
      authorization: "Bearer test-token",
      payload: expectedPayload,
    });
    expect(JSON.stringify(result)).toContain("email_new_draft");
    expect(JSON.stringify(result)).toContain("standalone_new_message");
  });

  it("requests dispatch by draft ID only, leaving approval and email contents to the task system", async () => {
    let observed: { method?: string; path?: string; authorization?: string; payload?: unknown } =
      {};
    const server = createServer(async (req, res) => {
      const chunks: Buffer[] = [];
      for await (const chunk of req) {
        chunks.push(Buffer.from(chunk));
      }
      observed = {
        method: req.method,
        path: req.url,
        authorization: req.headers.authorization,
        payload: JSON.parse(Buffer.concat(chunks).toString("utf8")),
      };
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "sent", draft_id: "draft-42" }));
    });
    servers.push(server);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    if (!address || typeof address === "string") {
      throw new Error("test server address unavailable");
    }

    const tool = createTaskSystemTool({
      defaultBaseUrl: `http://127.0.0.1:${address.port}`,
      defaultAuthToken: "test-token",
    });
    const result = await tool.execute("test-call", {
      action: "email_dispatch",
      payload: { draft_id: "draft-42" },
    });

    expect(observed).toEqual({
      method: "POST",
      path: "/task-system/email-dispatch/request",
      authorization: "Bearer test-token",
      payload: { draft_id: "draft-42" },
    });
    expect(JSON.stringify(result)).toContain("sent");
  });

  it("rejects assistant-supplied email content or approval fields on dispatch", async () => {
    const tool = createTaskSystemTool({ defaultAuthToken: "test-token" });

    await expect(
      tool.execute("test-call", {
        action: "email_dispatch",
        payload: { draft_id: "draft-42", subject: "changed by assistant" },
      }),
    ).rejects.toThrow("accepts only payload.draft_id");

    await expect(
      tool.execute("test-call", {
        action: "patch",
        kind: "task",
        id: "task-1",
        payload: { operations: [{ email: { signed_off: true } }] },
      }),
    ).rejects.toThrow("controlled by the task system");

    await expect(
      tool.execute("test-call", {
        action: "create",
        kind: "task",
        payload: { email_approval: "approved" },
      }),
    ).rejects.toThrow("controlled by the task system");
  });
});
