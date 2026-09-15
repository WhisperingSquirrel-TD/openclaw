'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-draft-failure-home-'));
process.env.HOME = tempHome;
process.env.WORKSPACE_PI_GATEWAY_TOKEN = 'test-token';
const { createGatewayServer } = require('../src/server');
const { createMockProvider, RESPONSE_SCHEMA } = require('../src/email-composition-provider');
function config(root) { return { port: 0, workspaceRoot: root, snapshotRoot: path.join(root, '.snapshots'), archiveRoot: path.join(root, '.archive'), auditLogPath: path.join(root, '.audit.log'), approvedRoots: ['.'], browseRoots: ['.'], tierRules: [{ pattern: '**', tier: 1 }], auth: { envVar: 'WORKSPACE_PI_GATEWAY_TOKEN' } }; }
async function request(base, method, pathname, body) { const response = await fetch(`${base}${pathname}`, { method, headers: { Authorization: 'Bearer test-token', ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined }); return { status: response.status, payload: await response.json() }; }

test('generated email writer failure leaves retryable blocked state and never reports a draft', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-draft-failure-workspace-'));
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token', compositionProvider: createMockProvider((request) => ({ schema: RESPONSE_SCHEMA, status: 'composed', mode: request.mode, recipient: request.identity.recipient, send: false, draft: { body: 'Hi,\n\nYes.\n\nBest,', subject: null } })), emailDraftExecutor: async () => { const error = new Error('mock Graph unavailable'); error.code = 'GRAPH_UNAVAILABLE'; throw error; } });
  const address = await gateway.start(0); const base = `http://127.0.0.1:${address.port}`; t.after(async () => gateway.close());
  await request(base, 'POST', '/task-system/context-broker/fixture/register', { entity_id: 'entityDraftFailure', sources: [{ source_id: 'src_exact_failure', source_kind: 'email', source_ref: 'exact-failure', role: 'dated_artifact', required_evidence: true, freshness_status: 'fresh', content_availability: 'full', content: 'From: client@example.com\nDate: 2026-08-06T09:00:00Z\n\nCan you confirm the proposed date?' }] });
  const intake = await request(base, 'POST', '/task-intake/brief', { brief_text: 'Draft a reply to this email.', work_type: 'email_reply_draft', entity: 'Draft Failure', entity_id: 'entityDraftFailure' });
  const execution = await request(base, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id });
  assert.equal(execution.status, 409); assert.equal(execution.payload.status, 'draft_unverified'); assert.equal(execution.payload.retryable, true); assert.equal(execution.payload.error.code, 'GRAPH_UNAVAILABLE');
  const subtask = await request(base, 'GET', `/subtasks/${intake.payload.subtasks[0].id}`);
  assert.equal(subtask.payload.entity.state, 'blocked'); assert.equal(subtask.payload.entity.blockers_json[0].retryable, true);
  assert.equal(JSON.stringify(execution.payload).includes('draft_created_not_sent'), false);
});
