const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
process.env.HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-context-contract-home-'));
process.env.WORKSPACE_PI_GATEWAY_TOKEN = 'test-token';
const { createGatewayServer } = require('../src/server');
function config(root) { return { port: 0, workspaceRoot: root, snapshotRoot: path.join(root, '.snapshots'), archiveRoot: path.join(root, '.archive'), auditLogPath: path.join(root, '.audit.log'), approvedRoots: ['.'], browseRoots: ['.'], tierRules: [{ pattern: '**', tier: 1 }], auth: { envVar: 'WORKSPACE_PI_GATEWAY_TOKEN' } }; }
async function request(baseUrl, method, pathname, body) { const res = await fetch(`${baseUrl}${pathname}`, { method, headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); return { status: res.status, payload: await res.json() }; }

test('short client brief emits explicit mandatory SharePoint/current-file/cache source-packet contract', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-context-contract-workspace-'));
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(() => gateway.close());

  const captured = await request(baseUrl, 'POST', '/task-intake/capture', { text: 'Prepare the client deliverable for Acme', source_refs: ['brief-acme'] });
  assert.equal(captured.status, 200);
  const contract = captured.payload.entity.context_loading_contract;
  assert.equal(contract.schema, 'task-context-loading-contract-v1');
  assert.equal(contract.classification, 'client_or_deliverable');
  assert.deepEqual(contract.source_packet.lookup_order, ['sharepoint_current_file', 'current_file', 'sharepoint_cache']);
  assert.equal(contract.source_packet.fail_closed_if_missing, true);
  assert.equal(contract.source_packet.cache_policy, 'registered_cache_only_no_fallback_search');
  assert.ok(contract.source_packet.required_lookups.every((lookup) => lookup.required));

  const preview = await request(baseUrl, 'POST', '/task-intake/decompose', { text: 'Prepare the client deliverable for Acme' });
  assert.equal(preview.status, 200);
  assert.deepEqual(preview.payload.context_loading_contract.source_packet.lookup_order, contract.source_packet.lookup_order);
  assert.equal(preview.payload.preview.task.context_loading_contract.schema, 'task-context-loading-contract-v1');
  assert.equal(preview.payload.preview.subtasks[0].title, 'Load source packet: Prepare the client deliverable for Acme');
});
