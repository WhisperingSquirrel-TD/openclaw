const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

process.env.HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-email-draft-home-'));
process.env.WORKSPACE_PI_GATEWAY_TOKEN = 'test-token';

const { createGatewayServer } = require('../src/server');
const { DB_PATH } = require('../src/task-system');

function resetDb() {
  for (const file of [DB_PATH, `${DB_PATH}-wal`, `${DB_PATH}-shm`]) fs.rmSync(file, { force: true });
}
function config(root) {
  return { port: 0, workspaceRoot: root, snapshotRoot: path.join(root, '.snapshots'), archiveRoot: path.join(root, '.archive'), auditLogPath: path.join(root, '.audit.log'), approvedRoots: ['.'], browseRoots: ['.'], tierRules: [{ pattern: '**', tier: 1 }], auth: { envVar: 'WORKSPACE_PI_GATEWAY_TOKEN' } };
}
async function request(base, body) {
  const response = await fetch(`${base}/task-system/email-draft/reply`, { method: 'POST', headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  return { status: response.status, payload: await response.json() };
}

test('email draft route is callable through the gateway without shell exec and never sends', async (t) => {
  resetDb();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-email-draft-workspace-'));
  let called = false;
  const gateway = createGatewayServer({
    config: config(root),
    authToken: 'test-token',
    emailDraftExecutor: async (_db, payload) => {
      called = true;
      assert.equal(payload.task_id, 'task_test');
      assert.equal(payload.subtask_id, 'sub_test');
      return { ok: true, outcome: 'draft_created_not_sent', draft_id: 'draft_test', verified: true, no_send_endpoint_called: true };
    },
  });
  const address = await gateway.start(0);
  t.after(() => gateway.close());
  const result = await request(`http://127.0.0.1:${address.port}`, { task_id: 'task_test', subtask_id: 'sub_test', body: 'Reply body' });
  assert.equal(result.status, 200);
  assert.equal(result.payload.draft_id, 'draft_test');
  assert.equal(result.payload.no_send_endpoint_called, true);
  assert.equal(called, true);
});

test('email draft route requires gateway bearer authentication', async () => {
  resetDb();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-email-draft-auth-'));
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token', emailDraftExecutor: async () => ({ ok: true }) });
  const address = await gateway.start(0);
  try {
    const response = await fetch(`http://127.0.0.1:${address.port}/task-system/email-draft/reply`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body: 'Reply' }) });
    assert.equal(response.status, 401);
  } finally {
    await gateway.close();
  }
});
