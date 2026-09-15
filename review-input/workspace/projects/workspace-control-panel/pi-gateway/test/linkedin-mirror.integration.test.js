const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

process.env.WORKSPACE_PI_GATEWAY_TOKEN = 'test-token';

const { createGatewayServer } = require('../src/server');

function makeConfig(root) {
  return {
    port: 0,
    workspaceRoot: root,
    snapshotRoot: path.join(root, '.snapshots'),
    archiveRoot: path.join(root, '.archive'),
    auditLogPath: path.join(root, '.audit.log'),
    approvedRoots: ['.'],
    browseRoots: ['.'],
    tierRules: [{ pattern: '**', tier: 1 }],
    auth: { envVar: 'WORKSPACE_PI_GATEWAY_TOKEN' },
  };
}

async function request(baseUrl, method, pathname, body) {
  const res = await fetch(`${baseUrl}${pathname}`, {
    method,
    headers: {
      Authorization: 'Bearer test-token',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await res.json();
  return { status: res.status, payload };
}

test('linkedin mirror status route is mounted and exposes fixed non-exec contract', async (t) => {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-linkedin-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(workspaceRoot), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => {
    await gateway.close();
  });

  const status = await request(baseUrl, 'GET', '/linkedin-mirror/status');
  assert.equal(status.status, 200);
  assert.equal(status.payload.ok, true);
  assert.equal(status.payload.data.helper, 'projects/linkedin-message-mirror/scripts/capture_linkedin_messages.py');
  assert.equal(status.payload.data.route_helper, 'projects/linkedin-message-mirror/scripts/route_linkedin_messages.py');
  assert.equal(status.payload.data.arbitrary_exec, false);
  assert.deepEqual(status.payload.data.outputs, {
    json: 'memory/linkedin-messages.json',
    markdown: 'LINKEDIN_MESSAGES.md',
    events: 'memory/linkedin-mirror-events.json',
    state: 'memory/linkedin-mirror-state.json',
    proposals: 'memory/linkedin-crm-proposals.json',
    proposals_markdown: 'LINKEDIN_CRM_PROPOSALS.md',
  });
});

test('authored-post status route is mounted with bounded read-only outputs', async (t) => {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-linkedin-posts-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(workspaceRoot), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => { await gateway.close(); });
  const status = await request(baseUrl, 'GET', '/linkedin-mirror/posts/status');
  assert.equal(status.status, 200);
  assert.equal(status.payload.data.helper, 'projects/linkedin-message-mirror/scripts/capture_linkedin_posts.py');
  assert.equal(status.payload.data.arbitrary_exec, false);
  assert.deepEqual(status.payload.data.outputs, {
    raw: 'memory/linkedin-posts-raw.json', state: 'memory/linkedin-posts-capture-state.json',
    markdown: 'LINKEDIN_POSTS.md', tracker: 'stackstone/linkedin-posts.md',
  });
});

test('authored-post capture refuses safely when fixed helper/venv is missing', async (t) => {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-linkedin-posts-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(workspaceRoot), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => { await gateway.close(); });
  const result = await request(baseUrl, 'POST', '/linkedin-mirror/posts/capture', { headed: false });
  assert.equal(result.status, 503);
  assert.equal(result.payload.ok, false);
  assert.equal(result.payload.error.code, 'LINKEDIN_POSTS_HELPER_MISSING');
});

test('linkedin mirror capture refuses safely when fixed helper/venv is missing', async (t) => {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-linkedin-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(workspaceRoot), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => {
    await gateway.close();
  });

  const result = await request(baseUrl, 'POST', '/linkedin-mirror/capture', { headed: false, limit_threads: 99 });
  assert.equal(result.status, 503);
  assert.equal(result.payload.ok, false);
  assert.equal(result.payload.error.code, 'LINKEDIN_MIRROR_VENV_MISSING');
});

test('linkedin mirror route refuses safely when fixed helper/venv is missing', async (t) => {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-linkedin-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(workspaceRoot), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => {
    await gateway.close();
  });

  const result = await request(baseUrl, 'POST', '/linkedin-mirror/route', { mode: 'baseline' });
  assert.equal(result.status, 503);
  assert.equal(result.payload.ok, false);
  assert.equal(result.payload.error.code, 'LINKEDIN_MIRROR_VENV_MISSING');
});
