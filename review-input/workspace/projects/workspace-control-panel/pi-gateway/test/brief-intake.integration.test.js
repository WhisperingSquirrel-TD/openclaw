const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-intake-home-'));
process.env.HOME = tempHome;
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
    headers: { Authorization: 'Bearer test-token', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: res.status, payload: await res.json() };
}

test('generic brief intake creates a bounded, typed, reviewable chain and is idempotent', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-intake-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());

  const registered = await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: 'entityCroydeMedical',
    sources: [
      { source_id: 'src_croyde_current', source_kind: 'sharepoint', source_ref: 'croyde-current', role: 'current', content: 'Current Croyde vendor-selection requirements.', freshness_status: 'fresh', content_availability: 'full' },
      { source_id: 'src_croyde_vendor_email', source_kind: 'email', source_ref: 'croyde-vendor-email', role: 'dated_artifact', content: 'Linked vendor-selection evidence.', freshness_status: 'fresh', content_availability: 'full', required_evidence: true },
    ],
  });
  assert.equal(registered.status, 200);

  const first = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: "Write the vendor packs for Croyde's vendor-selection process.",
    entity: 'Croyde Medical',
    entity_id: 'entityCroydeMedical',
    source_refs: ['src_croyde_current', 'src_croyde_vendor_email'],
    idempotency_key: 'croyde-vendor-packs-v1',
  });
  assert.equal(first.status, 200);
  assert.equal(first.payload.ok, true);
  assert.equal(first.payload.status, 'ready');
  assert.equal(first.payload.interpretation.work_type, 'client_document');
  assert.equal(first.payload.context_loading_contract.context_result.outcome, 'context_ready');
  assert.equal(first.payload.operator_signal.reason, 'brief_intake_context_ready_first_l1_unit');
  assert.equal(first.payload.task.state, 'open');
  assert.equal(first.payload.strategy, null);
  assert.equal(first.payload.objective, null);
  assert.equal(first.payload.task.parent_id, null);
  assert.equal(first.payload.subtasks.length, 3);
  assert.equal(first.payload.subtasks[0].execute_ready, true);
  assert.equal(first.payload.subtasks[1].execution_mode, 'prepare_for_review');
  assert.equal(first.payload.subtasks[2].owner, 'Tom');
  assert.equal(first.payload.context_loading_contract.source_scope.no_execution_time_discovery_or_fallback_search, true);
  assert.equal(first.payload.context_loading_contract.source_scope.discovery.bounded, true);
  assert.equal(first.payload.context_loading_contract.output_contract.external_delivery, 'prohibited_pending_tom_approval');

  const executorList = await request(baseUrl, 'GET', '/task-intake/executors');
  assert.equal(executorList.status, 200);
  assert.deepEqual(executorList.payload.executors.map(item => item.work_type), ['client_document', 'email_reply_draft', 'email_new_draft', 'meeting_action_plan']);

  const output = await request(baseUrl, 'POST', '/task-intake/execute', {
    task_id: first.payload.task.id,
    subtask_id: first.payload.subtasks[0].id,
    idempotency_key: 'croyde-vendor-packs-output-v1',
    output: {
      sections: [{ title: 'Evaluation criteria', content: 'Compare shortlisted vendors against confirmed requirements.' }],
      source_refs: ['src_croyde_current', 'src_croyde_vendor_email'],
    },
  });
  assert.equal(output.status, 200);
  assert.equal(output.payload.status, 'prepared_for_review');
  assert.equal(output.payload.output_type, 'document_draft_package');
  assert.equal(output.payload.external_delivery, 'prohibited');

  const replayOutput = await request(baseUrl, 'POST', '/task-intake/execute', {
    task_id: first.payload.task.id,
    subtask_id: first.payload.subtasks[0].id,
    idempotency_key: 'croyde-vendor-packs-output-v1',
    output: { sections: [{ title: 'ignored', content: 'idempotent replay' }], source_refs: ['src_croyde_current'] },
  });
  assert.equal(replayOutput.payload.idempotent_replay, true);
  assert.equal(replayOutput.payload.output_id, output.payload.output_id);

  const replay = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: "Write the vendor packs for Croyde's vendor-selection process.",
    entity: 'entityCroydeMedical',
    idempotency_key: 'croyde-vendor-packs-v1',
  });
  assert.equal(replay.status, 200);
  assert.equal(replay.payload.idempotent_replay, true);
  assert.equal(replay.payload.task.id, first.payload.task.id);
});

test('executor generates a bounded reviewable package when no caller output is supplied', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-executor-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());

  const registered = await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: 'entityGeneratedDocument',
    sources: [
      { source_id: 'src_generated_current', source_kind: 'sharepoint', source_ref: 'generated-current', role: 'current', content: 'Confirmed current requirements.', freshness_status: 'fresh', content_availability: 'full' },
      { source_id: 'src_generated_evidence', source_kind: 'sharepoint', source_ref: 'generated-evidence', role: 'dated_artifact', content: 'Linked evidence paragraph.', freshness_status: 'fresh', content_availability: 'full', required_evidence: true },
    ],
  });
  assert.equal(registered.status, 200);
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Write the client document for the confirmed requirements.',
    entity: 'Generated Document',
    entity_id: 'entityGeneratedDocument',
    source_refs: ['src_generated_current', 'src_generated_evidence'],
    idempotency_key: 'generated-document-v1',
  });
  assert.equal(intake.payload.status, 'ready');

  const result = await request(baseUrl, 'POST', '/task-intake/execute', {
    task_id: intake.payload.task.id,
    subtask_id: intake.payload.subtasks[0].id,
    idempotency_key: 'generated-document-output-v1',
  });
  assert.equal(result.status, 200);
  assert.equal(result.payload.status, 'prepared_for_review');
  assert.equal(result.payload.provenance.generation, 'generated');
  assert.equal(result.payload.provenance.manifest_hash.startsWith('sha256:'), true);
  assert.equal(result.payload.link.status, 'prepared_for_review');
  assert.equal(result.payload.output.sections.length, 2);
  assert.equal(result.payload.output.sections[0].classification, 'verified_current_truth');
  assert.equal(result.payload.output.sections[1].classification, 'supporting_evidence');
  assert.equal(result.payload.output.coverage.broad_search_performed, false);
  assert.deepEqual(result.payload.output.coverage.missing_coverage, []);
  assert.equal(result.payload.output.review_checklist.length, 3);
});

test('executor rejects provenance outside the loaded bounded packet', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-provenance-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());

  await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: 'entityScopedDocument',
    sources: [{ source_id: 'src_scoped_current', source_kind: 'sharepoint', source_ref: 'scoped-current', role: 'current', content: 'Scoped truth.', freshness_status: 'fresh', content_availability: 'full' }],
  });
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Write the client document for scoped requirements.',
    entity: 'Scoped Document',
    entity_id: 'entityScopedDocument',
    idempotency_key: 'scoped-document-v1',
  });
  const result = await request(baseUrl, 'POST', '/task-intake/execute', {
    task_id: intake.payload.task.id,
    subtask_id: intake.payload.subtasks[0].id,
    output: { sections: [{ title: 'Unsupported', content: 'Do not accept this.' }], source_refs: ['unregistered-source'] },
  });
  assert.equal(result.status, 422);
  assert.equal(result.payload.error.code, 'OUTPUT_PROVENANCE_SCOPE_DENIED');
});

test('brief intake fails closed into clarification for unsupported or unscoped work', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-clarification-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());

  const result = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Please sort this out.',
    idempotency_key: 'ambiguous-v1',
  });
  assert.equal(result.status, 200);
  assert.equal(result.payload.status, 'needs_clarification');
  assert.equal(result.payload.interpretation.work_type, 'unknown');
  assert.notEqual(result.payload.subtasks[0].execute_ready, true);
  assert.deepEqual(result.payload.subtasks[0].blockers_json.map(item => item.code).sort(), ['ENTITY_OR_PROJECT_REQUIRED', 'WORK_TYPE_UNRESOLVED']);
});

test('email reply brief selects exact-thread pattern without authorising send', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-email-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());

  const result = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Draft a reply to this client email.',
    work_type: 'email_reply_draft',
    entity: 'entityCroydeMedical',
    source_refs: ['exact_registered_email_thread'],
  });
  assert.equal(result.status, 200);
  assert.equal(result.payload.status, 'ready');
  assert.equal(result.payload.interpretation.work_type, 'email_reply_draft');
  assert.equal(result.payload.context_loading_contract.reply_mode, 'reply_without_exact_anchor');
  assert.equal(result.payload.context_loading_contract.context_result.coverage_gaps.some((gap) => gap.code === 'NAMED_EMAIL_TARGET_UNRESOLVED_FALLBACK_UNLINKED'), true);
  assert.equal(result.payload.context_loading_contract.context_requirements[0].category, 'exact_email_thread');
  assert.equal(result.payload.context_loading_contract.output_contract.external_delivery, 'send_prohibited');
});

test('email reply intake preserves and auto-binds an exact raw thread anchor without a supplied entity id', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-email-autobind-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());

  const exactAnchor = 'microsoft_inbox:email:tony-thread:Abcdefghijklmnopqrstuvwx';
  const result = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Draft a reply using the exact inbound thread.',
    work_type: 'email_reply_draft',
    source_refs: [exactAnchor],
    idempotency_key: 'email-autobind-v1',
  });
  assert.equal(result.status, 200);
  assert.notEqual(result.payload.status, 'needs_clarification');
  assert.equal(result.payload.task.primary_source_kind, 'email');
  assert.equal(result.payload.task.primary_source_ref, exactAnchor);
  assert.equal(result.payload.subtasks[0].primary_source_ref, exactAnchor);
  assert.equal(result.payload.context_loading_contract.context_result.entity_id.startsWith('email_auto_'), true);
  assert.notEqual(result.payload.subtasks[0].blockers_json[0]?.code, 'ENTITY_BINDING_REQUIRED');
});

test('email follow-up intake accepts an exact sent-message anchor without an entity binding', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-email-sent-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());

  const exactAnchor = 'microsoft_sent:email:tom-sent-thread:Abcdefghijklmnopqrstuvwx';
  const result = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Follow up on my last sent email in this exact thread.',
    work_type: 'email_reply_draft', reply_mode: 'follow_up_outbound', source_refs: [exactAnchor], idempotency_key: 'email-sent-autobind-v1',
  });
  assert.equal(result.status, 200);
  assert.notEqual(result.payload.status, 'needs_clarification');
  assert.equal(result.payload.task.primary_source_ref, exactAnchor);
  assert.equal(result.payload.context_loading_contract.reply_mode, 'follow_up_outbound');
  assert.equal(result.payload.context_loading_contract.context_result.entity_id.startsWith('email_auto_'), true);
});

test('email reply executor automatically composes a conservative bounded reply package', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-email-quality-workspace-'));
  const writerCalls = [];
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token', emailDraftExecutor: async (_db, payload) => {
    writerCalls.push(payload);
    return { ok: true, verified: true, id: 'out_mock_email', draft_id: 'draft_mock_email', web_link: 'https://draft.example/mock', verification: { recipient_verified: true, subject: 'Re: mock', body_hash: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', body_length: 24, readback_body_length: 48, saved_at: '2026-08-27T08:00:00Z' } };
  } });
  const address = await gateway.start(0); const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', { entity_id: 'entityEmailQuality', sources: [{ source_id: 'src_exact_thread_quality', source_kind: 'email', source_ref: 'exact-thread-quality', role: 'dated_artifact', required_evidence: true, content: 'From: client@example.com\nDate: 2026-08-06T09:00:00Z\n\nDoes the proposed date still work?', freshness_status: 'fresh', content_availability: 'full' }] });
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', { brief_text: 'Draft a reply to the exact client email.', work_type: 'email_reply_draft', entity: 'Email Quality Test', entity_id: 'entityEmailQuality', source_refs: ['src_exact_thread_quality'], idempotency_key: 'email-quality-v1' });
  assert.equal(intake.payload.status, 'ready');
  assert.equal(intake.payload.interpretation.work_type, 'email_reply_draft');
  assert.equal(intake.payload.context_loading_contract.reply_mode, 'reply_inbound');
  assert.equal(intake.payload.context_loading_contract.context_requirements.some(item => item.category === 'exact_email_thread' && item.required === true), true);
  assert.equal(intake.payload.context_loading_contract.context_result.profile, 'email_draft_v1');
  const result = await request(baseUrl, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'email-quality-output-v1' });
  assert.equal(result.status, 200); assert.equal(result.payload.status, 'draft_created_verified'); assert.equal(result.payload.verified, true);
  assert.equal(result.payload.verification.body_length, 24);
  assert.equal(writerCalls.length, 1); assert.equal(writerCalls[0].composition_package.schema, 'email-composition-package-v1'); assert.equal(writerCalls[0].composition_package.mode, 'reply_inbound'); assert.equal(writerCalls[0].composition_package.recipient_proof.strategy, 'createReplyAll_exact_inbound'); assert.equal(writerCalls[0].composition_package.no_send_proof.send_endpoint_called, false);
});

test('email reply executor requires latest-message anchoring and contextual-flow proof', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-email-continuity-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: 'entityEmailContinuity',
    sources: [{
      source_id: 'src_exact_thread_continuity', source_kind: 'email', source_ref: 'exact-thread-continuity', role: 'dated_artifact', required_evidence: true,
      content: 'From: tony@crmoxford.co.uk\nDate: 2026-08-06T09:00:00Z\n\nPlease confirm the next step.', freshness_status: 'fresh', content_availability: 'full',
    }],
  });
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Draft a reply to Tony.', work_type: 'email_reply_draft', entity: 'Tony', entity_id: 'entityEmailContinuity', source_refs: ['src_exact_thread_continuity'], idempotency_key: 'email-continuity-v1',
  });
  const result = await request(baseUrl, 'POST', '/task-intake/execute', {
    task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'email-continuity-output-v1',
    output: {
      schema: 'unsent-email-draft-v2', mode: 'reply_inbound', anchor_proof: { source_ref: 'src_exact_thread_continuity' }, recipient_proof: { strategy: 'createReplyAll_exact_inbound', address: 'tony@crmoxford.co.uk' }, no_send_proof: { send_endpoint_called: false }, draft_text: 'Thanks, Tony — I can confirm the next step.',
      draft: { body: 'Thanks, Tony — I can confirm the next step.', source_refs: ['src_exact_thread_continuity'] },
      thread_evidence: [{ source_ref: 'src_exact_thread_continuity', classification: 'exact_thread_evidence', content: 'Please confirm the next step.' }],
      source_refs: ['src_exact_thread_continuity'], unresolved_questions: [], review_state: 'prepared_for_review', send: false, sent: false, external_delivery: 'send_prohibited',
      reply_to_source_ref: 'src_exact_thread_continuity', latest_message_evidence: { source_ref: 'src_exact_thread_continuity', evidence_excerpt: 'From: tony@crmoxford.co.uk\nDate: 2026-08-06T09:00:00Z\n\nPlease confirm the next step.' },
      thread_continuity_check: 'passed', contextual_flow_check: 'passed',
    },
  });
  assert.equal(result.status, 200);
  assert.equal(result.payload.status, 'prepared_for_review');
  assert.equal(result.payload.output.reply_to_source_ref, 'src_exact_thread_continuity');
});

test('meeting action plan keeps source evidence separate and marks owner, timing, and commitment uncertainty', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-meeting-quality-workspace-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());

  const registered = await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: 'entityMeetingQuality',
    sources: [{
      source_id: 'src_meeting_current_quality',
      source_kind: 'sharepoint',
      source_ref: 'meeting-current-quality',
      role: 'current',
      required_evidence: true,
      content_availability: 'full',
      freshness_status: 'fresh',
      content: 'Tom will circulate the shortlist by Friday.',
    }, {
      source_id: 'src_meeting_quality',
      source_kind: 'sharepoint',
      source_ref: 'meeting-record-quality',
      role: 'dated_artifact',
      required_evidence: true,
      content_availability: 'full',
      freshness_status: 'fresh',
      content: 'The team should compare the vendor demos.\nConfirm the final owner before booking.',
    }],
  });
  assert.equal(registered.status, 200);

  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Turn the meeting record into a reviewable action plan.',
    work_type: 'meeting_action_plan',
    entity: 'Meeting Quality Test',
    entity_id: 'entityMeetingQuality',
    source_refs: ['src_meeting_current_quality', 'src_meeting_quality'],
    idempotency_key: 'meeting-quality-v1',
  });
  assert.equal(intake.payload.status, 'ready');

  const result = await request(baseUrl, 'POST', '/task-intake/execute', {
    task_id: intake.payload.task.id,
    subtask_id: intake.payload.subtasks[0].id,
    idempotency_key: 'meeting-quality-output-v1',
  });
  assert.equal(result.status, 200);
  assert.equal(result.payload.output.schema, 'meeting-action-plan-v2');
  assert.equal(result.payload.output.meeting_evidence.length, 2);
  assert.equal(result.payload.output.meeting_evidence[0].classification, 'meeting_source_evidence');
  assert.equal(result.payload.output.actions.length, 3);
  assert.equal(result.payload.output.actions[0].owner, 'Tom');
  assert.equal(result.payload.output.actions[0].due, 'Friday');
  assert.equal(result.payload.output.actions[0].commitment_status, 'explicit_commitment');
  assert.equal(result.payload.output.actions[1].commitment_status, 'proposal');
  assert.equal(result.payload.output.actions[2].owner_confidence, 'unresolved');
  assert.ok(result.payload.output.unresolved_questions.includes('Confirm owners for actions without an explicit owner.'));
  assert.ok(result.payload.output.unresolved_questions.includes('Confirm dates or timing for actions without an explicit due point.'));
  assert.equal(result.payload.output.review_state, 'prepared_for_review');
  assert.equal(result.payload.output.review_gate, 'tom_or_owner_review_required');
  assert.equal(result.payload.output.external_delivery, 'not_applicable');
});

test('brief intake performs bounded decomposition-time discovery and records its source ladder', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-discovery-workspace-'));
  fs.mkdirSync(path.join(root, 'sharepoint-cache', 'Accounts', 'Acme'), { recursive: true });
  fs.writeFileSync(path.join(root, 'sharepoint-cache', 'Accounts', 'Acme', 'Options Report.md'), 'Acme roadmap options and Phase 2 work items.');
  fs.writeFileSync(path.join(root, 'stackstone-crm.md'), 'Acme current account truth.');
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  const registered = await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: 'entityAcmeDiscovery',
    sources: [
      { source_id: 'src_acme_current', source_kind: 'sharepoint', source_ref: 'acme-current', role: 'current', content: 'Acme current truth.', freshness_status: 'fresh', content_availability: 'full' },
      { source_id: 'src_acme_options', source_kind: 'sharepoint', source_ref: 'acme-options', role: 'dated_artifact', content: 'Acme options.', freshness_status: 'fresh', content_availability: 'full', required_evidence: true },
    ],
  });
  assert.equal(registered.status, 200);
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Prepare the Acme Phase 2 options report.',
    work_type: 'client_document', entity: 'Acme', entity_id: 'entityAcmeDiscovery',
    source_refs: ['src_acme_current', 'src_acme_options'], idempotency_key: 'acme-discovery-v1',
  });
  assert.equal(intake.status, 200);
  assert.equal(intake.payload.context_loading_contract.source_scope.discovery.status, 'complete');
  assert.equal(intake.payload.context_loading_contract.source_scope.discovery.bounded, true);
  assert.ok(intake.payload.context_loading_contract.source_scope.discovery.query_terms.includes('acme'));
  assert.ok(intake.payload.context_loading_contract.source_scope.discovery.results.some((item) => item.path.includes('Options Report.md')));
  assert.equal(intake.payload.context_loading_contract.source_scope.no_execution_time_discovery_or_fallback_search, true);
});

test('standalone LinkedIn-contact brief accepts task aliases and creates an unsent draft through the bounded route', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-brief-linkedin-standalone-'));
  const recipient = 'henry@lynchbrotherhomes.co.uk';
  const entityId = `standalone_${require('node:crypto').createHash('sha256').update(recipient).digest('hex').slice(0, 20)}`;
  const writerCalls = [];
  const gateway = createGatewayServer({
    config: makeConfig(root),
    authToken: 'test-token',
    compositionProvider: {
      id: 'test_bounded_composer', quality: 'test_only',
      async compose(request) {
        return {
          schema: 'email-composition-response-v1', status: 'composed', mode: request.mode,
          recipient: request.identity.recipient, send: false,
          draft: { subject: 'As agreed — business review for Lynch Brother Homes', body: 'Hi Henry,\n\nGood to meet you this morning. As agreed, I will carry out the business review for £900. Please send over a couple of dates for an initial session.\n\nBest,' },
          code: null, message: null,
        };
      },
    },
    emailDraftExecutor: async (_db, payload) => {
      writerCalls.push(payload);
      return { ok: true, verified: true, id: 'out_henry', draft_id: 'draft_henry', web_link: 'https://outlook.example/drafts/henry', verification: { recipient_verified: true, subject: 'As agreed — business review for Lynch Brother Homes', body_hash: 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', body_length: 80, readback_body_length: 120, saved_at: '2026-08-27T08:00:00Z' } };
    },
  });
  const address = await gateway.start(0);
  const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());

  const sourceRef = 'linkedin:5805e42d8621a585:7b68f96b5a8fdb9d';
  const registered = await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: entityId,
    sources: [{ source_id: 'src_henry_linkedin', source_kind: 'linkedin', source_ref: 'ref_henry_linkedin', role: 'dated_artifact', required_evidence: true, freshness_status: 'fresh', content_availability: 'full', content: 'Henry Lynch: Thanks Tom - henry@lynchbrotherhomes.co.uk' }],
  });
  assert.equal(registered.status, 200);

  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Prepare an unsent standalone email to Henry confirming the £900 business review agreed at OBCN and asking for dates for an initial session.',
    work_type: 'email_reply_draft', entity_or_project: 'Lynch Brother Homes', mode: 'standalone_new_message', recipient_email: recipient,
    source_refs: [sourceRef], idempotency_key: 'henry-linkedin-standalone-v1',
  });
  assert.equal(intake.status, 200);
  assert.equal(intake.payload.status, 'ready');
  assert.equal(intake.payload.context_loading_contract.reply_mode, 'standalone_new_message');
  assert.equal(intake.payload.context_loading_contract.interpretation.entity_id, entityId);
  assert.equal(intake.payload.context_loading_contract.context_result.outcome, 'context_ready');

  const result = await request(baseUrl, 'POST', '/task-intake/execute', {
    task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'henry-linkedin-standalone-output-v1',
  });
  assert.equal(result.status, 200);
  assert.equal(result.payload.status, 'draft_created_verified');
  assert.equal(writerCalls.length, 1);
  assert.equal(writerCalls[0].composition_package.mode, 'standalone_new_message');
  assert.equal(writerCalls[0].composition_package.recipient_proof.address, recipient);
});

test('fresh outbound email draft is distinct from reply drafting and needs only recipient plus bound current entity context', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-fresh-outbound-email-'));
  const writerCalls = [];
  const gateway = createGatewayServer({
    config: makeConfig(root), authToken: 'test-token',
    compositionProvider: { id: 'test-fresh-outbound-composer', quality: 'test_only', async compose(request) {
      assert.equal(request.mode, 'standalone_new_message');
      assert.equal(request.identity.recipient, 'cara@peaberryandleaf.com');
      return { schema: 'email-composition-response-v1', status: 'composed', mode: request.mode, recipient: request.identity.recipient, send: false,
        draft: { subject: 'Peaberry & Leaf — next steps', body: 'Hi Cara,\n\nFollowing our recent conversation, I wanted to share the next steps.\n\nBest,' }, code: null, message: null };
    } },
    emailDraftExecutor: async (_db, payload) => { writerCalls.push(payload); return { ok: true, verified: true, id: 'out_cara', draft_id: 'draft_cara', web_link: 'https://outlook.example/drafts/cara', verification: { recipient_verified: true, subject: 'Peaberry & Leaf — next steps', body_hash: 'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', body_length: 70, readback_body_length: 110, saved_at: '2026-08-27T08:00:00Z' } }; },
  });
  const address = await gateway.start(0); const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  await request(baseUrl, 'POST', '/task-system/context-broker/registry/contacts', { entity_id: 'entityPeaberryLeaf', contact_id: 'contactCaraBrandi', full_name: 'Cara Brandi', email: 'cara@peaberryandleaf.com', primary_contact: true, verification_source_kind: 'crm', verification_source_ref: 'crm_contact_cara_20260825', verified_at: '2026-08-25T09:00:00Z' });
  await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: 'entityPeaberryLeaf',
    sources: [{ source_id: 'src_peaberry_current', source_kind: 'crm', source_ref: 'ref_peaberry_current', role: 'current', required_evidence: true, freshness_status: 'fresh', content_availability: 'full', content: 'Peaberry & Leaf current CRM context. Cara Brandi: cara@peaberryandleaf.com. Agreed next step: share a concise outline.' }],
  });
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Draft a new email to Cara at Peaberry & Leaf about next steps.', work_type: 'email_new_draft',
    entity_or_project: 'Peaberry & Leaf', entity_id: 'entityPeaberryLeaf', recipient_contact_id: 'contactCaraBrandi', recipient_email: 'attacker@example.com', idempotency_key: 'cara-fresh-outbound-v1',
  });
  assert.equal(intake.status, 200); assert.equal(intake.payload.status, 'ready');
  assert.equal(intake.payload.interpretation.work_type, 'email_new_draft');
  assert.equal(intake.payload.context_loading_contract.classification, 'fresh_outbound_email_draft');
  assert.equal(intake.payload.context_loading_contract.reply_mode, 'standalone_new_message');
  assert.equal(intake.payload.context_loading_contract.context_requirements.some(item => item.category === 'exact_email_thread'), false);
  assert.equal(intake.payload.context_loading_contract.context_result.outcome, 'context_ready');
  const result = await request(baseUrl, 'POST', '/task-intake/execute', { task_id: intake.payload.task.id, subtask_id: intake.payload.subtasks[0].id, idempotency_key: 'cara-fresh-outbound-output-v1' });
  assert.equal(result.status, 200); assert.equal(result.payload.status, 'draft_created_verified');
  assert.equal(writerCalls.length, 1); assert.equal(writerCalls[0].work_type, 'email_new_draft');
  assert.equal(writerCalls[0].composition_package.mode, 'standalone_new_message');
  assert.equal(writerCalls[0].composition_package.recipient_proof.address, 'cara@peaberryandleaf.com');
  assert.equal(writerCalls[0].composition_package.anchor_proof.kind, 'entity_current_context');
  assert.equal('thread_evidence' in writerCalls[0].composition_package, false);
  assert.equal('reply_to_source_ref' in writerCalls[0].composition_package, false);
  assert.equal('latest_message_evidence' in writerCalls[0].composition_package, false);
});

test('chat-facing brief payload classifies a fresh standalone Outlook draft without reply-thread requirements', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-chat-fresh-outbound-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0); const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  // This is the exact field shape forwarded by task_system.brief_intake from chat.
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief: 'Create an unsent fresh Outlook draft for the prospect — a standalone new message, not a reply.',
    idempotency_key: 'chat-fresh-outlook-draft-v1',
  });
  assert.equal(intake.status, 200);
  assert.equal(intake.payload.interpretation.work_type, 'email_new_draft');
  assert.equal(intake.payload.context_loading_contract.classification, 'fresh_outbound_email_draft');
  assert.equal(intake.payload.context_loading_contract.reply_mode, 'standalone_new_message');
  assert.equal(intake.payload.context_loading_contract.context_requirements.some(item => item.category === 'exact_email_thread'), false);
  assert.equal(intake.payload.subtasks[0].blockers_json.some(item => item.code === 'ENTITY_BINDING_REQUIRED'), true);
  assert.equal(intake.payload.subtasks[0].blockers_json.some(item => item.code === 'RECIPIENT_UNRESOLVED_COPY_ONLY'), true);
});

test('explicit fresh_outbound composition mode selects the entity-bound route before reply classification', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-explicit-fresh-outbound-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0); const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  await request(baseUrl, 'POST', '/task-system/context-broker/registry/contacts', { entity_id: 'entityExplicitFresh', contact_id: 'contactExplicitCara', full_name: 'Cara Brandi', email: 'cara@peaberryandleaf.com', primary_contact: true, verification_source_kind: 'crm', verification_source_ref: 'crm_contact_cara_explicit', verified_at: '2026-08-25T09:00:00Z' });
  await request(baseUrl, 'POST', '/task-system/context-broker/fixture/register', {
    entity_id: 'entityExplicitFresh',
    sources: [{ source_id: 'src_explicit_fresh_current', source_kind: 'crm', source_ref: 'ref_explicit_fresh_current', role: 'current', required_evidence: true, freshness_status: 'fresh', content_availability: 'full', content: 'Current registered CRM context for the entity.' }],
  });
  const intake = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Draft an email to Cara about next steps.', composition_mode: 'fresh_outbound',
    entity_or_project: 'Peaberry & Leaf', entity_id: 'entityExplicitFresh', recipient_contact_id: 'contactExplicitCara', idempotency_key: 'explicit-fresh-outbound-v1',
  });
  assert.equal(intake.status, 200);
  assert.equal(intake.payload.status, 'ready');
  assert.equal(intake.payload.interpretation.work_type, 'email_new_draft');
  assert.equal(intake.payload.context_loading_contract.reply_mode, 'standalone_new_message');
  assert.equal(intake.payload.context_loading_contract.context_requirements.some(item => item.category === 'exact_email_thread'), false);
});

test('fresh outbound intake rejects mailbox or thread selectors rather than weakening reply safety', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-fresh-outbound-selector-denied-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0); const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  const result = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Draft a new email to Cara at Peaberry & Leaf.', work_type: 'email_new_draft',
    entity_or_project: 'Peaberry & Leaf', entity_id: 'entityPeaberryLeaf', recipient_email: 'cara@peaberryandleaf.com',
    mailbox: 'microsoft_inbox', conversation_id: 'not-permitted-for-fresh-outbound', idempotency_key: 'cara-fresh-outbound-selector-denied-v1',
  });
  assert.equal(result.status, 200); assert.equal(result.payload.status, 'needs_clarification');
  assert.equal(result.payload.interpretation.work_type, 'email_new_draft');
  assert.equal(result.payload.subtasks[0].blockers_json.some(item => item.code === 'FRESH_OUTBOUND_THREAD_SELECTOR_PROHIBITED'), true);
});

test('fresh outbound rejects an email source ref or thread-id alias even with entity and recipient supplied', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wcp-fresh-outbound-email-ref-denied-'));
  const gateway = createGatewayServer({ config: makeConfig(root), authToken: 'test-token' });
  const address = await gateway.start(0); const baseUrl = `http://127.0.0.1:${address.port}`;
  t.after(async () => gateway.close());
  const result = await request(baseUrl, 'POST', '/task-intake/brief', {
    brief_text: 'Prepare a fresh outbound email to Cara at Peaberry & Leaf.', composition_mode: 'fresh_outbound',
    entity_or_project: 'Peaberry & Leaf', entity_id: 'entityPeaberryLeaf', recipient_email: 'cara@peaberryandleaf.com',
    threadId: 'conversation-not-permitted', source_refs: ['microsoft_inbox:email:opaqueConversation:opaqueMessageIdentifierAtLeastTwentyChars'],
    idempotency_key: 'cara-fresh-outbound-email-ref-denied-v1',
  });
  assert.equal(result.status, 200); assert.equal(result.payload.status, 'needs_clarification');
  assert.equal(result.payload.interpretation.work_type, 'email_new_draft');
  assert.equal(result.payload.context_loading_contract.reply_mode, 'standalone_new_message');
  assert.equal(result.payload.subtasks[0].blockers_json.some(item => item.code === 'FRESH_OUTBOUND_THREAD_SELECTOR_PROHIBITED'), true);
});
