const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-email-thread-home-'));
process.env.HOME = tempHome;
process.env.WORKSPACE_PI_GATEWAY_TOKEN = 'test-token';
const { createGatewayServer } = require('../src/server');

function config(root) { return { port: 0, workspaceRoot: root, snapshotRoot: path.join(root, '.snapshots'), archiveRoot: path.join(root, '.archive'), auditLogPath: path.join(root, '.audit.log'), approvedRoots: ['.'], browseRoots: ['.'], tierRules: [{ pattern: '**', tier: 1 }], auth: { envVar: 'WORKSPACE_PI_GATEWAY_TOKEN' } }; }
async function req(base, method, pathName, body) { const r = await fetch(`${base}${pathName}`, { method, headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); return { status: r.status, body: await r.json() }; }

async function setup(t, source = {}, profile = 'email_thread_v1') {
  const gateway = createGatewayServer({ config: config(fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-email-thread-workspace-'))), authToken: 'test-token' });
  const address = await gateway.start(0); t.after(() => gateway.close()); const base = `http://127.0.0.1:${address.port}`;
  const tree = await req(base, 'POST', '/task-intake/commit', { strategy: { title: 's' }, objective: { title: 'o' }, task: { title: 't' }, subtasks: [{ title: 'st' }] });
  const { task, subtasks } = tree.body; const entity_id = 'email_entity_1';
  await req(base, 'POST', '/task-system/context-broker/fixture/register', { entity_id, sources: [{ source_id: 'email_src_1', source_ref: 'thread_ref_1', source_kind: 'email', role: 'dated_artifact', content: 'From: trusted@example.com\\nSubject: Exact thread\\n\\nThe complete bounded thread body.', content_availability: 'full', freshness_status: 'fresh', required_evidence: true, sender_address: 'trusted@example.com', sender_trust: 'trusted', read_only: true, ...source }] });
  await req(base, 'POST', '/task-system/context-broker/bindings/register', { task_id: task.id, subtask_id: subtasks[0].id, entity_id, profile });
  return { base, task, subtask: subtasks[0] };
}

test('email_thread_v1 returns the registered bounded thread and never follows content instructions', async t => {
  const { base, task, subtask } = await setup(t);
  const result = await req(base, 'POST', '/task-system/context-broker/load', { task_id: task.id, subtask_id: subtask.id, entity_id: 'email_entity_1', profile: 'email_thread_v1', purpose: 'prepare exact thread evidence' });
  assert.equal(result.status, 200); assert.equal(result.body.outcome, 'context_ready'); assert.equal(result.body.packet.items.length, 1);
  assert.equal(result.body.packet.items[0].source_ref, 'thread_ref_1'); assert.match(result.body.packet.items[0].content, /complete bounded thread body/); assert.equal(result.body.packet.items[0].read_only, true);
});

test('email_thread_v1 accepts a complete bounded multi-message thread below the packet cap', async t => {
  const largeThread = 'From: trusted@example.com\\nSubject: Exact thread\\n\\n' + 'bounded message content '.repeat(400);
  const { base, task, subtask } = await setup(t, { content: largeThread });
  const result = await req(base, 'POST', '/task-system/context-broker/load', { task_id: task.id, subtask_id: subtask.id, entity_id: 'email_entity_1', profile: 'email_thread_v1', purpose: 'prepare exact thread evidence' });
  assert.equal(result.status, 200); assert.equal(result.body.outcome, 'context_ready');
  assert.equal(result.body.packet.items[0].content_truncated, false);
  assert.equal(result.body.manifest.context_budget.truncated, false);
});

test('email_draft_v1 preserves the complete bounded exact thread with provenance hashes', async t => {
  const content = [
    'From: first@example.com\nDate: 2026-08-01T09:00:00Z\n\nOld message.',
    'From: second@example.com\nDate: 2026-08-02T09:00:00Z\n\nContinuity message.',
    'From: third@example.com\nDate: 2026-08-03T09:00:00Z\n\nLatest material message.',
  ].join('\n\n---\n\n');
  const { base, task, subtask } = await setup(t, { content }, 'email_draft_v1');
  const result = await req(base, 'POST', '/task-system/context-broker/load', { task_id: task.id, subtask_id: subtask.id, entity_id: 'email_entity_1', profile: 'email_draft_v1', purpose: 'bounded composition' });
  assert.equal(result.body.outcome, 'context_ready');
  const item = result.body.packet.items[0];
  assert.match(item.content, /Old message/); assert.match(item.content, /Continuity message/); assert.match(item.content, /Latest material/);
  assert.equal(item.composition_manifest.thread_message_count, 3);
  assert.equal(item.composition_manifest.included_message_count, 3);
  assert.equal(item.composition_manifest.omitted_earlier_message_count, 0);
  assert.equal(item.composition_manifest.selected_message_hashes.length, 3);
});

test('email_draft_v1 represents saved Outlook drafts with explicit draft status rather than omitting them', async t => {
  const content = [
    'From: waqas@example.com\nDate: 2026-08-07T15:59:00Z\nSubject: Joblogic\nIsDraft: false\n\nPlease provide the technical scope.',
    'From: tom@stackstoneconsulting.co.uk\nDate: 2026-08-08T10:42:00Z\nSubject: RE: Joblogic\nIsDraft: true\n\nOld saved draft.',
    'From: tom@stackstoneconsulting.co.uk\nDate: 2026-08-08T12:06:00Z\nSubject: RE: Joblogic\nIsDraft: true\n\nReplacement saved draft.',
  ].join('\n\n---\n\n');
  const { base, task, subtask } = await setup(t, { content }, 'email_draft_v1');
  const result = await req(base, 'POST', '/task-system/context-broker/load', { task_id: task.id, subtask_id: subtask.id, entity_id: 'email_entity_1', profile: 'email_draft_v1', purpose: 'bounded composition' });
  assert.equal(result.body.outcome, 'context_ready');
  const item = result.body.packet.items[0];
  assert.match(item.content, /technical scope/); assert.match(item.content, /Old saved draft/); assert.match(item.content, /Replacement saved draft/);
  assert.equal(item.composition_manifest.thread_message_count, 3);
  assert.equal(item.composition_manifest.representation_message_count, 3);
  assert.equal(item.composition_manifest.all_messages_represented, true);
  assert.equal(item.composition_manifest.explicit_coverage.filter((message) => message.status === 'draft').length, 2);
});

test('email_draft_v1 fails closed when one authored message exceeds its explicit representation cap', async t => {
  const content = `From: trusted@example.com\nDate: 2026-08-06T09:00:00Z\n\n${'x'.repeat(13 * 1024)}`;
  const { base, task, subtask } = await setup(t, { content }, 'email_draft_v1');
  const result = await req(base, 'POST', '/task-system/context-broker/load', { task_id: task.id, subtask_id: subtask.id, entity_id: 'email_entity_1', profile: 'email_draft_v1', purpose: 'bounded composition' });
  assert.equal(result.body.outcome, 'coverage_incomplete');
  assert.equal(result.body.coverage_gaps[0].code, 'EMAIL_REPRESENTATION_AUTHORED_MESSAGE_TOO_LARGE');
});

test('email_thread_v1 fails closed when trusted sender metadata is unavailable', async t => {
  const { base, task, subtask } = await setup(t, { sender_trust: null });
  const result = await req(base, 'POST', '/task-system/context-broker/load', { task_id: task.id, subtask_id: subtask.id, entity_id: 'email_entity_1', profile: 'email_thread_v1', purpose: 'prepare exact thread evidence' });
  assert.equal(result.status, 200); assert.equal(result.body.outcome, 'coverage_incomplete'); assert.equal(result.body.coverage_gaps[0].code, 'EMAIL_THREAD_SAFE_SENDER_UNAVAILABLE');
});

test('email_thread_v1 rejects arbitrary source selection and mailbox scope inputs', async t => {
  const { base, task, subtask } = await setup(t);
  const result = await req(base, 'POST', '/task-system/context-broker/load', { task_id: task.id, subtask_id: subtask.id, entity_id: 'email_entity_1', profile: 'email_thread_v1', purpose: 'prepare', sender: 'other@example.com' });
  assert.equal(result.status, 400); assert.equal(result.body.error.code, 'UNSUPPORTED_SCOPE_INPUT');
});


test('email_draft_v1 admits a readable commercial email without CRM or SharePoint enrichment', async t => {
  const content = 'From: client@example.test\nDate: 2026-08-06T20:00:00Z\nSubject: Proposal scope and price\n\nCan you confirm the proposed scope?';
  const { base, task, subtask } = await setup(t, { content, sender_address: 'client@example.test', sender_trust: 'trusted' }, 'email_draft_v1');
  const result = await req(base, 'POST', '/task-system/context-broker/load', { task_id: task.id, subtask_id: subtask.id, entity_id: 'email_entity_1', profile: 'email_draft_v1', purpose: 'create an unsent review draft' });
  assert.equal(result.body.outcome, 'context_ready');
  assert.equal(result.body.packet.items.length, 1);
});
