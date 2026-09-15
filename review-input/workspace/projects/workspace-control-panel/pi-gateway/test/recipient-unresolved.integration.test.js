'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-copy-only-home-'));
process.env.HOME = tempHome;
process.env.WORKSPACE_PI_GATEWAY_TOKEN = 'test-token';
const { createGatewayServer } = require('../src/server');
function config(root) { return { port: 0, workspaceRoot: root, snapshotRoot: path.join(root, '.snapshots'), archiveRoot: path.join(root, '.archive'), auditLogPath: path.join(root, '.audit.log'), approvedRoots: ['.'], browseRoots: ['.'], tierRules: [{ pattern: '**', tier: 1 }], auth: { envVar: 'WORKSPACE_PI_GATEWAY_TOKEN' } }; }
async function request(base, method, pathname, body) { const response = await fetch(`${base}${pathname}`, { method, headers: { Authorization: 'Bearer test-token', ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined }); return { status: response.status, payload: await response.json() }; }

test('new email with unresolved recipient produces an unaddressed verified Outlook draft and never sends', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-copy-only-workspace-'));
  let writerCalled = false;
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token', compositionProvider: { id: 'unaddressed-test-provider', quality: 'test_only', async compose(request) { assert.equal(request.identity.strategy, 'new_draft_unaddressed_recipient_unresolved'); assert.equal(request.identity.recipient, 'RECIPIENT_UNRESOLVED'); return { schema: 'email-composition-response-v1', status: 'composed', mode: request.mode, recipient: 'RECIPIENT_UNRESOLVED', send: false, draft: { subject: 'Project next steps', body: 'Hello,\n\nBased on the agreed project context, here is the proposed next step.\n\nBest,' }, code: null, message: null }; } }, emailDraftExecutor: async (_db, payload) => { writerCalled = true; assert.equal(payload.composition_package.recipient_proof.strategy, 'new_draft_unaddressed_recipient_unresolved'); return { ok: true, verified: true, id: 'draft_unaddressed_mock', draft_id: 'draft_unaddressed_mock', web_link: 'https://draft.example/unaddressed', verification: { recipient_verified: true, subject: 'Project next steps', body_hash: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', body_length: 80, readback_body_length: 80, saved_at: '2026-08-30T14:00:00.000Z' } }; } });
  const address = await gateway.start(0); const base = `http://127.0.0.1:${address.port}`; t.after(async () => gateway.close());
  await request(base, 'POST', '/task-system/context-broker/fixture/register', { entity_id: 'entityCopyOnly', sources: [{ source_id: 'src_copy_current', source_kind: 'crm', source_ref: 'ref_copy_current', role: 'current', required_evidence: true, freshness_status: 'fresh', content_availability: 'full', content: 'Current project context: agreed next step is to review the proposal.' }] });
  const intake = await request(base, 'POST', '/task-intake/brief', { brief_text: 'Draft a new email about the agreed project next step.', work_type: 'email_new_draft', entity: 'Copy Only Client', entity_id: 'entityCopyOnly', idempotency_key: 'copy-only-v1' });
  assert.equal(intake.payload.status, 'ready');
  const result = await request(base, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'copy-only-output-v1' });
  assert.equal(result.status, 200); assert.equal(result.payload.status, 'draft_created_verified'); assert.equal(writerCalled, true); assert.equal(result.payload.external_delivery, 'send_prohibited');
});
