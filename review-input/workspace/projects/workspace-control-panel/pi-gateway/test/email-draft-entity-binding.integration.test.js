'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const childProcess = require('node:child_process');

process.env.HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-email-draft-home-'));
process.env.WORKSPACE_PI_GATEWAY_TOKEN = 'test-token';

const { createGatewayServer } = require('../src/server');
const { DB_PATH } = require('../src/task-system');
const { createMockProvider, RESPONSE_SCHEMA } = require('../src/email-composition-provider');

function resetDb() {
  for (const file of [DB_PATH, `${DB_PATH}-wal`, `${DB_PATH}-shm`]) fs.rmSync(file, { force: true });
}
function config(root) {
  return { port: 0, workspaceRoot: root, snapshotRoot: path.join(root, '.snapshots'), archiveRoot: path.join(root, '.archive'), auditLogPath: path.join(root, '.audit.log'), approvedRoots: ['.'], browseRoots: ['.'], tierRules: [{ pattern: '**', tier: 1 }], auth: { envVar: 'WORKSPACE_PI_GATEWAY_TOKEN' }, taskContextBroker: { sharepointCache: { enabled: true, root: path.join(root, 'sharepoint-cache'), maxAgeMs: 24 * 60 * 60 * 1000, maxBytes: 64 * 1024 } } };
}
async function request(baseUrl, method, pathname, body) {
  const response = await fetch(`${baseUrl}${pathname}`, { method, headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  return { status: response.status, payload: await response.json() };
}

async function setupAnchoredReply(t, messageId) {
  resetDb();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-email-draft-binding-'));
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  t.after(() => gateway.close());
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const task = await request(baseUrl, 'POST', '/tasks', { title: 'Reply from exact inbound email', state: 'active', primary_source_kind: 'email', primary_source_ref: `microsoft_inbox:email:conversationId:${messageId}` });
  const subtask = await request(baseUrl, 'POST', '/subtasks', { title: 'Draft reply', parent_id: task.payload.entity.id, owner: 'L1', risk: 'MEDIUM', execution_mode: 'prepare_for_review', readiness_state: 'execute_ready', state: 'todo', next_action: 'Load exact email', success_definition: 'Draft context is bounded' });
  return { baseUrl, task: task.payload.entity, subtask: subtask.payload.entity };
}

function installExactThreadReader(t, messageId, sender, messages = null) {
  const original = childProcess.spawnSync;
  childProcess.spawnSync = (_command, args) => ({ status: 0, stdout: JSON.stringify({ success: true, messages: messages || [
    { message_id: 'EarlierThreadMessageIdentifier000', sender: 'Earlier Sender <earlier@example.com>', received: '2026-08-29T10:00:00Z', subject: 'Earlier', is_draft: false, body: 'Earlier message.' },
    { message_id: messageId, sender, received: '2026-08-30T10:00:00Z', subject: 'Exact inbound', is_draft: false, body: 'Please send a reply.' },
  ] }) });
  t.after(() => { childProcess.spawnSync = original; });
}
async function registerContact(baseUrl, contactId, entityId, email, fullName = 'Verified Contact') {
  const result = await request(baseUrl, 'POST', '/task-system/context-broker/registry/contacts', { contact_id: contactId, entity_id: entityId, full_name: fullName, email, primary_contact: true, verification_source_ref: 'crm-contact-record', verification_source_kind: 'crm' });
  assert.equal(result.status, 200);
}
async function load(baseUrl, task, subtask) {
  return request(baseUrl, 'POST', '/task-system/context-broker/load', { task_id: task.id, subtask_id: subtask.id, profile: 'email_draft_v1', purpose: 'Prepare a bounded reply from the exact inbound message.' });
}

test('binds a single active verified CRM entity using the normalized sender of the exact inbound anchor before bounded load', async (t) => {
  const messageId = 'AnchoredInboundMessageIdentifier0001';
  installExactThreadReader(t, messageId, 'Verified Contact <CONTACT@Example.com>');
  const { baseUrl, task, subtask } = await setupAnchoredReply(t, messageId);
  await registerContact(baseUrl, 'contact_verified', 'entity_verified', 'contact@example.com');

  const result = await load(baseUrl, task, subtask);
  assert.equal(result.status, 200);
  assert.equal(result.payload.outcome, 'context_ready');
  assert.equal(result.payload.manifest.entity_id, 'entity_verified');
  assert.equal(result.payload.packet.items[0].entity_id, 'entity_verified');
});

test('retains the task-local email_auto entity when exact inbound sender has no verified CRM contact', async (t) => {
  const messageId = 'AnchoredInboundMessageIdentifier0002';
  installExactThreadReader(t, messageId, 'Unverified <unknown@example.com>');
  const { baseUrl, task, subtask } = await setupAnchoredReply(t, messageId);

  const result = await load(baseUrl, task, subtask);
  assert.equal(result.status, 200);
  assert.equal(result.payload.outcome, 'context_ready');
  assert.match(result.payload.manifest.entity_id, /^email_auto_/);
});

test('retains email_auto rather than guessing when normalized inbound sender maps to multiple active verified contacts', async (t) => {
  const messageId = 'AnchoredInboundMessageIdentifier0003';
  installExactThreadReader(t, messageId, 'Duplicate <duplicate@example.com>');
  const { baseUrl, task, subtask } = await setupAnchoredReply(t, messageId);
  await registerContact(baseUrl, 'contact_duplicate_one', 'entity_duplicate_one', 'duplicate@example.com');
  await registerContact(baseUrl, 'contact_duplicate_two', 'entity_duplicate_two', 'DUPLICATE@example.com');

  const result = await load(baseUrl, task, subtask);
  assert.equal(result.status, 200);
  assert.equal(result.payload.outcome, 'context_ready');
  assert.match(result.payload.manifest.entity_id, /^email_auto_/);
});

test('does not infer a CRM entity from an outbound/sent anchor', async (t) => {
  const messageId = 'AnchoredInboundMessageIdentifier0004';
  installExactThreadReader(t, messageId, 'Verified Contact <contact@example.com>');
  const { baseUrl, task, subtask } = await setupAnchoredReply(t, messageId);
  await registerContact(baseUrl, 'contact_sent', 'entity_sent', 'contact@example.com');
  // Replace only the stored anchor with a sent surface; exact sender evidence is not inbound.
  await request(baseUrl, 'PATCH', `/tasks/${task.id}`, { primary_source_ref: `microsoft_sent:email:conversationId:${messageId}` });

  const result = await load(baseUrl, task, subtask);
  assert.equal(result.status, 200);
  assert.equal(result.payload.outcome, 'context_ready');
  assert.match(result.payload.manifest.entity_id, /^email_auto_/);
});

async function registerCurrent(baseUrl, entityId, sourceId, options = {}) {
  const result = await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: entityId,
    sources: [{ source_id: sourceId, source_kind: options.source_kind || 'crm', source_ref: `ref_${sourceId}`, role: 'current', required_evidence: true, content_availability: options.content_availability || 'full', freshness_status: options.freshness_status || 'fresh', claim_key: options.claim_key, claim_value: options.claim_value, content: options.content || 'Registered current context.' }],
  });
  assert.equal(result.status, 200);
}

// Regression: CiCo is a named/verified entity, but absence of registered current
// CRM/SharePoint truth must remain a visible gap—not a reason to lose the exact
// bounded thread or to falsely report complete context.
test('CiCo named entity with no current context retains exact thread and reports provenance coverage gap', async (t) => {
  const messageId = 'CiCoInboundMessageIdentifier00001';
  installExactThreadReader(t, messageId, 'Cristian I Olteanu <cristian@cico.example>');
  const { baseUrl, task, subtask } = await setupAnchoredReply(t, messageId);
  await registerContact(baseUrl, 'contact_cico', 'entity_cico', 'cristian@cico.example');

  const result = await load(baseUrl, task, subtask);
  assert.equal(result.status, 200);
  assert.equal(result.payload.outcome, 'context_ready');
  assert.equal(result.payload.manifest.entity_id, 'entity_cico');
  assert.equal(result.payload.manifest.coverage_status, 'incomplete');
  assert.equal(result.payload.manifest.current_truth_status, 'coverage_incomplete_or_stale');
  assert.deepEqual(result.payload.manifest.coverage_gaps.map((gap) => gap.code), ['EMAIL_DRAFT_CURRENT_TRUTH_UNAVAILABLE']);
  assert.equal(result.payload.packet.items.filter((item) => item.source_kind === 'email').length, 1);
  assert.equal(result.payload.packet.items[0].source_ref.startsWith('email_ref_'), true);
});

test('fresh registered current context yields complete bounded provenance for named email entity', async (t) => {
  const messageId = 'CurrentContextInboundMessageIdentifier1';
  installExactThreadReader(t, messageId, 'Current Contact <current@example.com>');
  const { baseUrl, task, subtask } = await setupAnchoredReply(t, messageId);
  await registerContact(baseUrl, 'contact_current', 'entity_current', 'current@example.com');
  await registerCurrent(baseUrl, 'entity_current', 'src_current_fresh');

  const result = await load(baseUrl, task, subtask);
  assert.equal(result.status, 200);
  assert.equal(result.payload.outcome, 'context_ready');
  assert.equal(result.payload.manifest.entity_id, 'entity_current');
  assert.equal(result.payload.manifest.coverage_status, 'complete');
  assert.deepEqual(result.payload.manifest.coverage_gaps, []);
  assert.equal(result.payload.packet.items.some((item) => item.source_id === 'src_current_fresh' && item.source_kind === 'crm' && item.source_role === 'current' && item.freshness_status === 'fresh'), true);
});

test('stale, missing, and ambiguous registered current context remain explicit coverage gaps', async (t) => {
  const messageId = 'CoverageGapInboundMessageIdentifier01';
  installExactThreadReader(t, messageId, 'Gap Contact <gaps@example.com>');
  const { baseUrl, task, subtask } = await setupAnchoredReply(t, messageId);
  await registerContact(baseUrl, 'contact_gaps', 'entity_gaps', 'gaps@example.com');
  await registerCurrent(baseUrl, 'entity_gaps', 'src_current_stale', { freshness_status: 'stale', claim_key: 'next_action', claim_value: 'wait' });
  await registerCurrent(baseUrl, 'entity_gaps', 'src_current_conflict_one', { claim_key: 'next_action', claim_value: 'send' });
  await registerCurrent(baseUrl, 'entity_gaps', 'src_current_conflict_two', { claim_key: 'next_action', claim_value: 'hold' });

  const result = await load(baseUrl, task, subtask);
  assert.equal(result.status, 200);
  assert.equal(result.payload.outcome, 'context_ready');
  assert.equal(result.payload.manifest.coverage_status, 'incomplete');
  const codes = result.payload.manifest.coverage_gaps.map((gap) => gap.code);
  assert.equal(codes.includes('EMAIL_DRAFT_CURRENT_TRUTH_STALE_OR_INCOMPLETE'), true);
  // The stale source does not contribute a claim; the conflicting fresh pair
  // must independently remain visible rather than being auto-resolved.
  assert.equal(codes.includes('UNRESOLVED_SOURCE_CONFLICT'), true);
  assert.equal(result.payload.manifest.required_curated_refresh, true);
});


test('exact thread adapter failure admits only a visibly fallback-unlinked bounded task packet', async (t) => {
  const messageId = 'UnavailableInboundMessageIdentifier1';
  const original = childProcess.spawnSync;
  childProcess.spawnSync = () => ({ status: 2, stdout: '', stderr: '{"error":"Exact conversation exceeds the bounded 65536-byte limit"}' });
  t.after(() => { childProcess.spawnSync = original; });
  const { baseUrl, task, subtask } = await setupAnchoredReply(t, messageId);

  const result = await load(baseUrl, task, subtask);
  assert.equal(result.status, 200);
  assert.equal(result.payload.outcome, 'context_ready');
  assert.equal(result.payload.manifest.draft_mode, 'reply_without_exact_anchor');
  assert.equal(result.payload.manifest.draft_route, 'fallback_unlinked');
  assert.equal(result.payload.manifest.coverage_status, 'incomplete');
  assert.equal(result.payload.manifest.coverage_gaps[0].code, 'EXACT_EMAIL_THREAD_UNAVAILABLE_FALLBACK_UNLINKED');
  assert.match(result.payload.manifest.coverage_gaps[0].message, /Exact conversation exceeds the bounded 65536-byte limit/);
  assert.equal(result.payload.packet.items.length, 1);
  assert.equal(result.payload.packet.items[0].source_kind, 'system_metadata');
  assert.match(result.payload.packet.items[0].content, /standalone, unlinked, UNSENT draft/i);
});

test('named email intake binds one exact registered thread for one exact verified contact without mailbox search', async (t) => {
  const messageId = 'NamedRegisteredThreadMessageIdentifier1';
  installExactThreadReader(t, messageId, 'Named Contact <named@example.com>');
  resetDb();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-named-email-intake-'));
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token' });
  const address = await gateway.start(0); t.after(() => gateway.close());
  const baseUrl = `http://127.0.0.1:${address.port}`;
  await registerContact(baseUrl, 'contact_named', 'entity_named', 'named@example.com', 'Named Contact');
  const registration = await request(baseUrl, 'POST', '/task-system/context-broker/registry/sources', { entity_id: 'entity_named', sources: [{ source_id: 'source_named_thread', source_kind: 'email', source_ref: 'registered_named_thread_1', role: 'dated_artifact', adapter_kind: 'trusted_email_thread_v1', adapter_locator: messageId, enabled: true, content_availability: 'full', freshness_status: 'fresh', required_evidence: true, sender_trust: 'trusted', read_only: true }] });
  assert.equal(registration.status, 200);

  const intake = await request(baseUrl, 'POST', '/task-intake/brief', { brief_text: 'Draft a reply to Named Contact about their email.', work_type: 'email_reply_draft', entity: 'Named Contact', idempotency_key: 'named-email-registered-thread-v1' });
  assert.equal(intake.status, 200);
  assert.equal(intake.payload.status, 'ready');
  assert.equal(intake.payload.context_loading_contract.context_result.entity_id, 'entity_named');
  assert.equal(intake.payload.context_loading_contract.context_result.coverage_gaps.some((gap) => gap.code === 'EXACT_EMAIL_THREAD_EVIDENCE_MISSING'), false);
  const loadResult = intake.payload.context_loading_contract.context_result;
  assert.equal(loadResult.source_count, 1);
});

test('named email intake with no unique registered target stays ready only for an unaddressed unlinked UNSENT draft', async (t) => {
  resetDb();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-named-email-fallback-'));
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token' });
  const address = await gateway.start(0); t.after(() => gateway.close());
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', { brief_text: 'Draft a reply to Unknown Named Contact.', work_type: 'email_reply_draft', entity: 'Unknown Named Contact', idempotency_key: 'named-email-fallback-v1' });
  assert.equal(intake.status, 200);
  assert.equal(intake.payload.status, 'ready');
  const context = intake.payload.context_loading_contract.context_result;
  assert.equal(context.outcome, 'context_ready');
  assert.equal(context.coverage_gaps.some((gap) => gap.code === 'NAMED_EMAIL_TARGET_UNRESOLVED_FALLBACK_UNLINKED'), true);
  assert.equal(intake.payload.task.context_loading_contract.composition_intent.mode, 'reply_without_exact_anchor');
  assert.equal(intake.payload.task.context_loading_contract.composition_intent.recipient_email, null);
  const loaded = await load(baseUrl, intake.payload.task, intake.payload.subtasks[0]);
  assert.equal(loaded.payload.outcome, 'context_ready');
  assert.equal(loaded.payload.manifest.draft_mode, 'reply_without_exact_anchor');
  assert.equal(loaded.payload.manifest.draft_route, 'fallback_unlinked');
  assert.equal(loaded.payload.manifest.coverage_status, 'incomplete');
  assert.equal(loaded.payload.packet.items.length, 1);
  assert.equal(loaded.payload.packet.items[0].source_kind, 'system_metadata');
  assert.match(loaded.payload.packet.items[0].content, /unaddressed, standalone, unlinked, UNSENT draft/i);
});

test('fallback-unlinked exact reply fails closed before the Outlook writer and records no draft link', async (t) => {
  resetDb();
  const original = childProcess.spawnSync;
  childProcess.spawnSync = () => ({ status: 2, stdout: '' });
  t.after(() => { childProcess.spawnSync = original; });
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-email-fallback-route-'));
  const writerCalls = [];
  const gateway = createGatewayServer({
    config: config(root), authToken: 'test-token',
    compositionProvider: createMockProvider((request) => ({
      schema: RESPONSE_SCHEMA, status: 'composed', mode: request.mode, recipient: request.identity.recipient, send: false,
      draft: { subject: '[UNLINKED — REVIEW REQUIRED] Draft email', body: 'Hi,\n\nThis is an unlinked draft for review.\n\nBest,' }, code: null, message: null,
    })),
    emailDraftExecutor: async (_db, payload) => {
      writerCalls.push(payload);
      return { ok: true, verified: true, id: 'out_fallback', draft_id: 'draft_fallback', web_link: 'https://draft.example/fallback', draft_route: 'fallback_unlinked', verification: { linkage_status: 'fallback_unlinked', recipient_verified: true, subject: '[UNLINKED — REVIEW REQUIRED] Draft email', body_hash: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', body_length: 32, readback_body_length: 48, saved_at: '2026-08-30T21:00:00Z' } };
    },
  });
  const address = await gateway.start(0); t.after(() => gateway.close());
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const anchor = 'microsoft_inbox:email:fallback-conversation:UnavailableInboundMessageIdentifier2';
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', { brief_text: 'Draft a reply to this client email.', work_type: 'email_reply_draft', source_refs: [anchor], idempotency_key: 'fallback-unlinked-route-v1' });
  assert.equal(intake.payload.status, 'ready');
  assert.equal(intake.payload.context_loading_contract.context_result.coverage_gaps[0].code, 'EXACT_EMAIL_THREAD_UNAVAILABLE_FALLBACK_UNLINKED');
  const execution = await request(baseUrl, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'fallback-unlinked-route-output-v1' });
  assert.equal(execution.status, 409);
  assert.equal(execution.payload.status, 'blocked');
  assert.equal(execution.payload.error.code, 'EXACT_EMAIL_THREAD_UNAVAILABLE_FALLBACK_UNLINKED');
  assert.equal(writerCalls.length, 0);
  const task = await request(baseUrl, 'GET', `/tasks/${intake.payload.task.id}`);
  const subtask = await request(baseUrl, 'GET', `/subtasks/${intake.payload.subtasks[0].id}`);
  assert.equal(task.payload.entity.links_json.some((link) => link.type === 'outlook_draft'), false);
  assert.equal(subtask.payload.entity.links_json.some((link) => link.type === 'outlook_draft'), false);
  assert.equal(subtask.payload.entity.blockers_json.some((blocker) => blocker.code === 'EXACT_EMAIL_THREAD_UNAVAILABLE_FALLBACK_UNLINKED'), true);
});

test('named intake resolves the latest admitted inbound anchor in one conversation without a CRM contact', async (t) => {
  const olderMessageId = 'AdmittedDeonOlderMessageIdentifier01';
  const latestMessageId = 'AdmittedDeonLatestMessageIdentifier2';
  const conversationId = 'AdmittedDeonConversationIdentifier1';
  installExactThreadReader(t, latestMessageId, 'Deon Dreyer <deon.dreyer.343@gmail.com>');
  resetDb();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-named-admitted-inbound-'));
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token' });
  const address = await gateway.start(0); t.after(() => gateway.close());
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const old = await request(baseUrl, 'POST', '/tasks', {
    title: 'Reply prep — Deon Dreyer <deon.dreyer.343@gmail.com>: Earlier message', state: 'active',
    primary_source_kind: 'email', primary_source_ref: `microsoft_external:email:${conversationId}:${olderMessageId}`,
  });
  assert.equal(old.status, 200);
  const latest = await request(baseUrl, 'POST', '/tasks', {
    title: 'Reply prep — Deon Dreyer <deon.dreyer.343@gmail.com>: Re: Current request', state: 'active',
    primary_source_kind: 'email', primary_source_ref: `microsoft_external:email:${conversationId}:${latestMessageId}`,
  });
  assert.equal(latest.status, 200);

  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Draft a reply to Deon Dreyer.', work_type: 'email_reply_draft', entity: 'Deon Dreyer',
    idempotency_key: 'named-admitted-inbound-anchor-v1',
  });
  assert.equal(intake.status, 200);
  assert.equal(intake.payload.status, 'ready');
  assert.equal(intake.payload.task.primary_source_ref, `microsoft_external:email:${conversationId}:${latestMessageId}`);
  assert.equal(intake.payload.context_loading_contract.reply_thread_binding.schema, 'registered-exact-email-reply-binding-v1');
  assert.equal(intake.payload.context_loading_contract.context_result.outcome, 'context_ready');
  assert.match(intake.payload.context_loading_contract.context_result.entity_id, /^email_auto_/);
  assert.equal(intake.payload.context_loading_contract.context_result.coverage_gaps.some((gap) => gap.code === 'NAMED_EMAIL_TARGET_UNRESOLVED_FALLBACK_UNLINKED'), false);
});

test('named intake fails closed when admitted inbound anchors span multiple conversations', async (t) => {
  resetDb();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-named-admitted-ambiguous-'));
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token' });
  const address = await gateway.start(0); t.after(() => gateway.close());
  const baseUrl = `http://127.0.0.1:${address.port}`;
  for (const [conversationId, messageId] of [['AmbiguousConversationIdentifier1', 'AmbiguousInboundMessageIdentifier01'], ['AmbiguousConversationIdentifier2', 'AmbiguousInboundMessageIdentifier02']]) {
    const admitted = await request(baseUrl, 'POST', '/tasks', {
      title: 'Reply prep — Deon Dreyer <deon.dreyer.343@gmail.com>: Re: Different thread', state: 'active',
      primary_source_kind: 'email', primary_source_ref: `microsoft_external:email:${conversationId}:${messageId}`,
    });
    assert.equal(admitted.status, 200);
  }
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Draft a reply to Deon Dreyer.', work_type: 'email_reply_draft', entity: 'Deon Dreyer',
    idempotency_key: 'named-admitted-inbound-ambiguous-v1',
  });
  assert.equal(intake.status, 200);
  assert.equal(intake.payload.status, 'ready');
  assert.equal(intake.payload.task.primary_source_kind, 'brief_intake');
  assert.equal(intake.payload.task.context_loading_contract.composition_intent.mode, 'reply_without_exact_anchor');
  assert.equal(intake.payload.context_loading_contract.context_result.coverage_gaps.some((gap) => gap.code === 'NAMED_EMAIL_TARGET_UNRESOLVED_FALLBACK_UNLINKED'), true);
});

test('named registered Deon route passes only the broker-proven exact locator to a drafts-only Reply All writer', { concurrency: false }, async (t) => {
  const messageId = 'DeonRegisteredMessageLocator00001';
  installExactThreadReader(t, messageId, 'Deon Dreyer <deon.dreyer.343@gmail.com>');
  resetDb();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-deon-registered-route-'));
  const writerCalls = [];
  const gateway = createGatewayServer({
    config: config(root), authToken: 'test-token',
    compositionProvider: createMockProvider((request) => ({ schema: RESPONSE_SCHEMA, status: 'composed', mode: request.mode, recipient: request.identity.recipient, send: false, draft: { subject: 'Re: Stackstone x Deon x Grant', body: 'Hi Deon,\n\nThanks — I will review this.\n\nBest,' } })),
    emailDraftExecutor: async (_db, payload) => {
      writerCalls.push(payload);
      return { ok: true, verified: true, id: 'out_deon', draft_id: 'draft_deon', web_link: 'https://draft.example/deon', verification: { recipient_verified: true, subject: 'Re: Stackstone x Deon x Grant', body_hash: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', body_length: 44, readback_body_length: 44, saved_at: '2026-08-31T13:30:00.000Z' } };
    },
  });
  const address = await gateway.start(0); const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  await registerContact(baseUrl, 'contact_deon', 'entity_deon', 'deon.dreyer.343@gmail.com', 'Deon Dreyer');
  const registered = await request(baseUrl, 'POST', '/task-system/context-broker/registry/sources', { entity_id: 'entity_deon', sources: [{ source_id: 'src_deon_registered_thread', source_kind: 'email', source_ref: 'email_ref_deon_registered', role: 'dated_artifact', adapter_kind: 'trusted_email_thread_v1', adapter_locator: messageId, enabled: true, content_availability: 'full', freshness_status: 'fresh', required_evidence: true, sender_trust: 'trusted', read_only: true }] });
  assert.equal(registered.status, 200);
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', { brief_text: 'Create an unsent Outlook reply draft to Deon Dreyer.', work_type: 'email_reply_draft', entity: 'Deon Dreyer', idempotency_key: 'deon-registered-reply-v1' });
  assert.equal(intake.payload.status, 'ready', JSON.stringify(intake.payload));
  assert.deepEqual(intake.payload.context_loading_contract.reply_thread_binding, { schema: 'registered-email-reply-binding-v1', entity_id: 'entity_deon', contact_id: 'contact_deon', source_id: 'src_deon_registered_thread' });
  const execution = await request(baseUrl, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'deon-registered-execute-v1' });
  assert.equal(execution.status, 200, JSON.stringify(execution.payload));
  assert.equal(execution.payload.status, 'draft_created_verified');
  assert.equal(writerCalls.length, 1);
  assert.equal(writerCalls[0].composition_package.mode, 'reply_inbound');
  assert.equal(writerCalls[0].composition_package.no_send_proof.send_endpoint_called, false);
  assert.equal(Object.prototype.propertyIsEnumerable.call(writerCalls[0], 'protected_reply_binding'), false);
  assert.equal(writerCalls[0].protected_reply_binding.message_locator, messageId);
});


test('chat-facing explicitly labelled Microsoft IDs in brief text are registered and capability-bound before any named fallback or draft writer call', { concurrency: false }, async (t) => {
  const messageId = 'SuppliedExactInboundMessageLocator001';
  installExactThreadReader(t, messageId, 'Deon Dreyer <deon.dreyer.343@gmail.com>');
  resetDb();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-supplied-exact-intake-'));
  const writerCalls = [];
  const gateway = createGatewayServer({
    config: config(root), authToken: 'test-token',
    compositionProvider: createMockProvider((request) => ({ schema: RESPONSE_SCHEMA, status: 'composed', mode: request.mode, recipient: request.identity.recipient, send: false, draft: { subject: 'Re: Exact thread', body: 'Hi Deon,\n\nThanks — I will review this.\n\nBest,' } })),
    emailDraftExecutor: async (_db, payload) => { writerCalls.push(payload); return { ok: true, verified: true, id: 'out_exact', draft_id: 'draft_exact', web_link: 'https://draft.example/exact', verification: { recipient_verified: true, subject: 'Re: Exact thread', body_hash: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', body_length: 44, readback_body_length: 44, saved_at: '2026-08-31T13:30:00.000Z' } }; },
  });
  const address = await gateway.start(0); const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    // This is the legacy chat tool shape: only `brief` is forwarded. The IDs
    // remain explicitly labelled opaque values, not inferred from prose.
    brief: `Create an unsent Outlook reply draft to Deon Dreyer. Entity/project: Deon Dreyer. Work type: email_reply_draft. Mailbox: assistant@example.com. Exact Microsoft message ID: ${messageId}. Exact Microsoft conversation ID: SuppliedExactConversationIdentifier01. Never send.`,
    idempotency_key: 'supplied-exact-deon-reply-v1',
  });
  assert.equal(intake.status, 200, JSON.stringify(intake.payload));
  assert.equal(intake.payload.status, 'ready', JSON.stringify(intake.payload));
  const binding = intake.payload.context_loading_contract.reply_thread_binding;
  assert.equal(binding.schema, 'registered-exact-email-reply-binding-v1');
  assert.match(binding.source_id, /^email_source_/);
  assert.match(intake.payload.task.primary_source_ref, /^microsoft_external:email:/);
  assert.match(intake.payload.context_loading_contract.source_scope.explicit_source_refs[0], /^email_ref_/);
  assert.equal(intake.payload.context_loading_contract.context_result.outcome, 'context_ready');
  assert.equal(intake.payload.context_loading_contract.context_result.coverage_gaps.some((gap) => /NAMED_EMAIL_TARGET_UNRESOLVED/.test(gap.code)), false);
  const execution = await request(baseUrl, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'supplied-exact-deon-execute-v1' });
  assert.equal(execution.status, 200, JSON.stringify(execution.payload));
  assert.equal(execution.payload.status, 'draft_created_verified');
  assert.equal(writerCalls.length, 1);
  assert.equal(writerCalls[0].composition_package.mode, 'reply_inbound');
  assert.equal(Object.prototype.propertyIsEnumerable.call(writerCalls[0], 'protected_reply_binding'), false);
  assert.equal(writerCalls[0].protected_reply_binding.message_locator, messageId);
  assert.equal(writerCalls[0].protected_reply_binding.source_id, binding.source_id);
  assert.equal(Object.keys(writerCalls[0]).includes('message_id'), false);
});


test('Deon-shaped raw thread above 65536 bytes is reduced only by deterministic repeated-quotation removal and reaches Reply All as a complete representation', { concurrency: false }, async (t) => {
  const messageId = 'DeonLongQuotedMessageLocator00001';
  const authored = 'Could you confirm whether the grant discussion is still active?';
  const rawQuote = `<div>${authored}</div><div id="divRplyFwdMsg">${'Repeated Outlook quotation. '.repeat(4000)}</div>`;
  assert.ok(Buffer.byteLength(rawQuote, 'utf8') > 65536);
  installExactThreadReader(t, messageId, 'Deon Dreyer <deon.dreyer.343@gmail.com>', [
    { message_id: 'DeonEarlierMessageLocator000001', sender: 'tom@stackstoneconsulting.co.uk', to: ['deon.dreyer.343@gmail.com'], cc: [], received: '2026-08-29T10:00:00Z', sent: '2026-08-29T10:00:00Z', subject: 'Stackstone x Deon x Grant', is_draft: false, status: 'sent', raw_body: '<div>Earlier context.</div>', authored_content: 'Earlier context.' },
    { message_id: messageId, sender: 'Deon Dreyer <deon.dreyer.343@gmail.com>', to: ['tom@stackstoneconsulting.co.uk'], cc: ['grant@example.com'], received: '2026-08-30T10:00:00Z', subject: 'Stackstone x Deon x Grant', is_draft: false, status: 'inbound', raw_body: rawQuote, authored_content: authored },
  ]);
  resetDb(); const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-deon-long-representation-')); const writerCalls = []; const providerCalls = [];
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token', compositionProvider: createMockProvider((request) => { providerCalls.push(request); return { schema: RESPONSE_SCHEMA, status: 'composed', mode: request.mode, recipient: request.identity.recipient, send: false, draft: { subject: 'Re: Stackstone x Deon x Grant', body: 'Hi Deon,\n\nThanks — I have received your question.\n\nBest,' } }; }), emailDraftExecutor: async (_db, payload) => { writerCalls.push(payload); return { ok: true, verified: true, id: 'out_deon_long', draft_id: 'draft_deon_long', web_link: 'https://draft.example/deon-long', verification: { recipient_verified: true, subject: 'Re: Stackstone x Deon x Grant', body_hash: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', body_length: 50, readback_body_length: 50, saved_at: '2026-08-31T14:00:00.000Z' } }; } });
  const address = await gateway.start(0); t.after(() => gateway.close()); const baseUrl = `http://127.0.0.1:${address.port}`;
  await registerContact(baseUrl, 'contact_deon_long', 'entity_deon_long', 'deon.dreyer.343@gmail.com', 'Deon Dreyer');
  await request(baseUrl, 'POST', '/task-system/context-broker/registry/sources', { entity_id: 'entity_deon_long', sources: [{ source_id: 'src_deon_long_thread', source_kind: 'email', source_ref: 'email_ref_deon_long', role: 'dated_artifact', adapter_kind: 'trusted_email_thread_v1', adapter_locator: messageId, enabled: true, content_availability: 'full', freshness_status: 'fresh', required_evidence: true, sender_trust: 'trusted', read_only: true }] });
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', { brief_text: 'Create an unsent Outlook reply draft to Deon Dreyer.', work_type: 'email_reply_draft', entity: 'Deon Dreyer', idempotency_key: 'deon-long-representation-intake-v1' });
  const execution = await request(baseUrl, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'deon-long-representation-execute-v1' });
  assert.equal(execution.payload.status, 'draft_created_verified', JSON.stringify(execution.payload)); assert.equal(writerCalls.length, 1); assert.equal(writerCalls[0].composition_package.no_send_proof.send_endpoint_called, false);
  const represented = providerCalls[0].bounded_packet.items.find((item) => item.source_kind === 'email');
  assert.equal(represented.composition_manifest.schema, 'email-drafting-representation-v1'); assert.equal(represented.composition_manifest.all_messages_represented, true); assert.equal(represented.composition_manifest.thread_message_count, 2); assert.equal(represented.composition_manifest.representation_message_count, 2); assert.equal(represented.composition_manifest.explicit_coverage[1].raw_content_bytes, Buffer.byteLength(rawQuote)); assert.equal(represented.composition_manifest.explicit_coverage[1].represented_content_bytes, Buffer.byteLength(authored)); assert.doesNotMatch(represented.content, /Repeated Outlook quotation/);
});

test('oversized Deon authored message fails closed before composition or Reply All writer invocation', { concurrency: false }, async (t) => {
  const messageId = 'DeonOversizedAuthoredLocator0001'; const oversized = 'x'.repeat(13 * 1024);
  installExactThreadReader(t, messageId, 'Deon Dreyer <deon.dreyer.343@gmail.com>', [{ message_id: messageId, sender: 'Deon Dreyer <deon.dreyer.343@gmail.com>', to: ['tom@stackstoneconsulting.co.uk'], cc: [], received: '2026-08-30T10:00:00Z', subject: 'Stackstone x Deon x Grant', is_draft: false, status: 'inbound', raw_body: oversized, authored_content: oversized }]);
  resetDb(); const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-deon-oversized-authored-')); const writerCalls = []; const providerCalls = [];
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token', compositionProvider: createMockProvider((request) => { providerCalls.push(request); throw new Error('must not compose'); }), emailDraftExecutor: async (_db, payload) => { writerCalls.push(payload); throw new Error('must not write'); } }); const address = await gateway.start(0); t.after(() => gateway.close()); const baseUrl = `http://127.0.0.1:${address.port}`;
  await registerContact(baseUrl, 'contact_deon_large', 'entity_deon_large', 'deon.dreyer.343@gmail.com', 'Deon Dreyer'); await request(baseUrl, 'POST', '/task-system/context-broker/registry/sources', { entity_id: 'entity_deon_large', sources: [{ source_id: 'src_deon_oversized_thread', source_kind: 'email', source_ref: 'email_ref_deon_oversized', role: 'dated_artifact', adapter_kind: 'trusted_email_thread_v1', adapter_locator: messageId, enabled: true, content_availability: 'full', freshness_status: 'fresh', required_evidence: true, sender_trust: 'trusted', read_only: true }] });
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', { brief_text: 'Create an unsent Outlook reply draft to Deon Dreyer.', work_type: 'email_reply_draft', entity: 'Deon Dreyer', idempotency_key: 'deon-oversized-authored-intake-v1' }); const execution = await request(baseUrl, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'deon-oversized-authored-execute-v1' });
  assert.equal(execution.status, 409); assert.equal(execution.payload.error.code, 'EXECUTION_CONTEXT_NOT_READY'); assert.equal(execution.payload.error.coverage_gaps[0].code, 'EMAIL_REPRESENTATION_AUTHORED_MESSAGE_TOO_LARGE'); assert.equal(providerCalls.length, 0); assert.equal(writerCalls.length, 0);
});


test('commercial Deon exact reply auto-admits only exact-term SharePoint current and supporting provenance before the Reply All draft gate', { concurrency: false }, async (t) => {
  const messageId = 'DeonCommercialAutoAdmissionLocator01';
  installExactThreadReader(t, messageId, 'Deon Dreyer <deon@example.com>', [
    { message_id: 'DeonCommercialEarlierLocator0001', sender: 'tom@stackstoneconsulting.co.uk', to: ['deon@example.com'], cc: ['grant@example.com'], received: '2026-08-29T10:00:00Z', subject: 'Stackstone x Deon x Grant', is_draft: false, status: 'sent', body: 'Earlier commercial context.' },
    { message_id: messageId, sender: 'Deon Dreyer <deon@example.com>', to: ['tom@stackstoneconsulting.co.uk'], cc: ['grant@example.com'], received: '2026-08-30T10:00:00Z', subject: 'Stackstone x Deon x Grant', is_draft: false, status: 'inbound', body: 'Could you confirm the pricing and options before we proceed?' },
  ]);
  resetDb(); const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-deon-commercial-auto-admission-'));
  const cache = path.join(root, 'sharepoint-cache', 'Partnerships', 'Grant Fagan'); fs.mkdirSync(cache, { recursive: true });
  fs.writeFileSync(path.join(cache, 'Grant Fagan - Current.md'), '# Stackstone x Deon x Grant\n\nCurrent commercial next action is recorded.');
  fs.writeFileSync(path.join(cache, '2026-08-26 - Meeting Summary - Stackstone x Deon x Grant.md'), '# Stackstone x Deon x Grant\n\nCommercial pricing and options meeting evidence.');
  const writerCalls = []; const providerCalls = [];
  const gateway = createGatewayServer({ config: config(root), authToken: 'test-token',
    compositionProvider: createMockProvider((request) => { providerCalls.push(request); return ({ schema: RESPONSE_SCHEMA, status: 'composed', mode: request.mode, recipient: request.identity.recipient, send: false, draft: { subject: 'Re: Stackstone x Deon x Grant', body: 'Hi Deon,\n\nThanks — I will come back on the pricing and options.\n\nBest,' } }); }),
    emailDraftExecutor: async (_db, payload) => { writerCalls.push(payload); return { ok: true, verified: true, id: 'out_deon_commercial', draft_id: 'draft_deon_commercial', web_link: 'https://draft.example/deon-commercial', verification: { recipient_verified: true, subject: 'Re: Stackstone x Deon x Grant', body_hash: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', body_length: 70, readback_body_length: 70, saved_at: '2026-08-31T16:00:00.000Z', folder: 'Drafts', is_draft: true, conversation_continuity: true } }; },
  });
  const address = await gateway.start(0); t.after(() => gateway.close()); const baseUrl = `http://127.0.0.1:${address.port}`;
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', { brief_text: 'Create an unsent Outlook reply to the commercial pricing email.', work_type: 'email_reply_draft', entity: 'Stackstone x Deon x Grant', mailbox: 'microsoft_inbox', conversation_id: 'DeonCommercialConversation01', message_id: messageId, idempotency_key: 'deon-commercial-auto-admission-v1' });
  assert.equal(intake.status, 200, JSON.stringify(intake.payload));
  assert.equal(intake.payload.context_loading_contract.commercial_context_required, true);
  assert.equal(intake.payload.context_loading_contract.commercial_context_admission.status, 'admitted');
  assert.deepEqual(intake.payload.context_loading_contract.commercial_context_admission.sources.map((source) => [source.source_kind, source.role]).sort(), [['sharepoint', 'current'], ['sharepoint', 'dated_artifact']]);
  assert.equal(intake.payload.context_loading_contract.context_result.coverage_gaps.length, 0);
  assert.equal(intake.payload.context_loading_contract.context_result.source_count, 3);
  const execution = await request(baseUrl, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'deon-commercial-auto-admission-execute-v1' });
  assert.equal(execution.status, 200, JSON.stringify(execution.payload)); assert.equal(execution.payload.status, 'draft_created_verified'); assert.equal(writerCalls.length, 1);
  assert.equal(writerCalls[0].composition_package.no_send_proof.send_endpoint_called, false);
  assert.equal(writerCalls[0].protected_reply_binding.message_locator, messageId);
  assert.equal(providerCalls[0].bounded_packet.items.some((item) => item.source_kind === 'sharepoint' && item.source_role === 'current' && item.freshness_status === 'fresh'), true);
  assert.equal(providerCalls[0].bounded_packet.items.some((item) => item.source_kind === 'sharepoint' && item.source_role === 'dated_artifact' && item.freshness_status === 'fresh'), true);
});

test('complete commercial exact thread with no SharePoint sources creates an unsent low-confidence draft and records Grant’s existing CRM binding', { concurrency: false }, async (t) => {
  const messageId = 'DeonCommercialNoSharepoint001'; installExactThreadReader(t, messageId, 'Deon Dreyer <deon@example.com>', [{ message_id: 'DeonCommercialNoSharepointEarlier', sender: 'Tom Dean <tom@stackstoneconsulting.co.uk>', to: ['deon@example.com'], cc: ['Grant Fagan <grant@example.com>'], received: '2026-08-29T10:00:00Z', subject: 'Stackstone x Deon x Grant', is_draft: false, status: 'sent', body: 'Earlier context.' }, { message_id: messageId, sender: 'Deon Dreyer <deon@example.com>', to: ['tom@stackstoneconsulting.co.uk'], cc: ['Grant Fagan <grant@example.com>'], received: '2026-08-30T10:00:00Z', subject: 'Stackstone x Deon x Grant', is_draft: false, status: 'inbound', body: 'Please confirm the pricing.' }]);
  resetDb(); const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-deon-commercial-no-sharepoint-'));
  const writerCalls = []; const providerCalls = []; const gateway = createGatewayServer({ config: config(root), authToken: 'test-token', compositionProvider: createMockProvider((request) => { providerCalls.push(request); return { schema: RESPONSE_SCHEMA, status: 'composed', mode: request.mode, recipient: request.identity.recipient, send: false, draft: { subject: 'Re: Stackstone x Deon x Grant', body: 'Hi Deon,\n\nThanks — I have your pricing question.\n\nBest,' } }; }), emailDraftExecutor: async (_db, payload) => { writerCalls.push(payload); return { ok: true, verified: true, id: 'out_deon_no_sharepoint', draft_id: 'draft_deon_no_sharepoint', web_link: 'https://draft.example/deon-no-sharepoint', verification: { recipient_verified: true, subject: 'Re: Stackstone x Deon x Grant', body_hash: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', body_length: 55, readback_body_length: 55, saved_at: '2026-09-01T10:00:00.000Z', folder: 'Drafts', is_draft: true, conversation_continuity: true } }; } });
  const address = await gateway.start(0); t.after(() => gateway.close()); const baseUrl = `http://127.0.0.1:${address.port}`;
  await registerContact(baseUrl, 'contact_grant', 'entity_grant', 'grant@example.com', 'Grant Fagan');
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', { brief_text: 'Create an unsent Outlook reply to the commercial pricing email.', work_type: 'email_reply_draft', entity: 'Stackstone x Deon x Grant', mailbox: 'microsoft_inbox', conversation_id: 'DeonCommercialNoSharepointConversation1', message_id: messageId, idempotency_key: 'deon-commercial-no-sharepoint-v1' });
  assert.equal(intake.payload.context_loading_contract.commercial_context_admission.status, 'coverage_incomplete');
  const execution = await request(baseUrl, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'deon-commercial-no-sharepoint-execute-v1' });
  assert.equal(execution.status, 200, JSON.stringify(execution.payload)); assert.equal(execution.payload.status, 'draft_created_verified'); assert.equal(providerCalls.length, 1); assert.equal(writerCalls.length, 1);
  assert.equal(writerCalls[0].composition_package.no_send_proof.send_endpoint_called, false);
  assert.equal(writerCalls[0].composition_package.context_coverage.status, 'incomplete'); assert.equal(writerCalls[0].composition_package.context_coverage.confidence, 'low');
  const grant = writerCalls[0].composition_package.context_coverage.participant_resolution.find((participant) => participant.address === 'grant@example.com');
  assert.deepEqual(grant && { resolution: grant.resolution, admitted: grant.admitted, bindings: grant.bindings.map((binding) => binding.entity_id) }, { resolution: 'linked_unique', admitted: true, bindings: ['entity_grant'] });
});
