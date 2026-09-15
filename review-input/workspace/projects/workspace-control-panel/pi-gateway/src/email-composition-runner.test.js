'use strict';
// End-to-end task runner proof: bounded broker -> mock quality provider -> mock
// Graph writer seam. No network, credential, or live Outlook dependency.
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const executors = require('./executors');
const { createMockProvider, createCodexCliProvider, createProductionCompositionProvider, RESPONSE_SCHEMA } = require('./email-composition-provider');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const emailDraft = require('./email-draft');

const inbound = `From: Alice <alice@example.test>\nDate: 2026-08-06T10:00:00Z\nSubject: Re: Scope\n\nCan you send the agreed scope?`;
const followUp = `From: Alice <alice@example.test>\nDate: 2026-08-05T10:00:00Z\nSubject: Scope\n\nThanks.\n\n---\n\nFrom: Tom Dean <tom@stackstoneconsulting.co.uk>\nDate: 2026-08-06T10:00:00Z\nSubject: Re: Scope\n\nCould you confirm the next step?`;
function packet(thread) { return { items: [{ source_id: 'emailSource1', source_ref: 'emailRef1', source_kind: 'email', source_role: 'dated_artifact', required_evidence: true, content: thread, composition_manifest: { included_message_count: 2, omitted_earlier_message_count: 0 } }, { source_id: 'crmCurrent1', source_ref: 'crmCurrent1', source_kind: 'crm', source_role: 'current', content_availability: 'full', freshness_status: 'fresh', content: 'Current account context: scope discussion is active.' }, { source_id: 'spArtifact1', source_ref: 'spArtifact1', source_kind: 'sharepoint', source_role: 'dated_artifact', content_availability: 'full', freshness_status: 'fresh', content: 'Agreed scope preparation artefact.' }] }; }
function qualityProvider(body) { return createMockProvider((request) => ({ schema: RESPONSE_SCHEMA, status: 'composed', mode: request.mode, recipient: request.identity.recipient, draft: { body, subject: 'RE: Scope' }, send: false })); }

test('production composition remains deterministic fallback unless quality composition is explicitly enabled', () => {
  const provider = createProductionCompositionProvider({ apiKey: 'present-but-not-consent', fetch: async () => { throw new Error('must not call cloud'); } });
  assert.equal(provider.id, 'deterministic_safe_fallback_v1');
});

test('production selection chooses the Codex worker only when explicitly enabled and selected', () => {
  const provider = createProductionCompositionProvider({ enableQualityProvider: true, provider: 'codex_cli', workspace: '/isolated/email-composer', spawn: () => { throw new Error('not invoked'); } });
  assert.equal(provider.id, 'codex_cli_bounded_email_v1');
});

function codexRequest() { return { schema: 'email-composition-request-v1', request_id: 'test-request', mode: 'reply_inbound', identity: { recipient: 'alice@example.test' }, no_send: true, bounded_packet: packet(inbound) }; }
function fakeCodexSpawn(handler) {
  return (bin, args) => {
    const child = new EventEmitter(); child.stdin = new PassThrough(); child.stderr = new PassThrough(); child.kill = () => {};
    handler({ bin, args, child });
    return child;
  };
}

test('Codex CLI provider uses the isolated read-only ephemeral worker and accepts valid JSON', async () => {
  let invocation;
  const provider = createCodexCliProvider({ workspace: '/isolated/email-composer', timeoutMs: 1000, spawn: fakeCodexSpawn(({ bin, args, child }) => {
    invocation = { bin, args }; const outputPath = args[args.indexOf('--output-last-message') + 1];
    child.stdin.on('finish', () => { fs.writeFileSync(outputPath, JSON.stringify({ schema: RESPONSE_SCHEMA, status: 'composed', mode: 'reply_inbound', recipient: 'alice@example.test', send: false, draft: { body: 'Hi Alice,\\n\\nYes.\\n\\nBest,', subject: null } })); child.emit('close', 0); });
  }) });
  const result = await provider.compose(codexRequest());
  assert.equal(result.status, 'composed'); assert.equal(invocation.bin, 'codex');
  assert.ok(invocation.args.includes('--ephemeral')); assert.ok(invocation.args.includes('read-only')); assert.ok(invocation.args.includes('--ignore-rules'));
  assert.equal(invocation.args[invocation.args.indexOf('-C') + 1], '/isolated/email-composer');
});

test('Codex CLI provider turns invalid JSON into a structured invalid-output refusal', async () => {
  const provider = createCodexCliProvider({ timeoutMs: 1000, spawn: fakeCodexSpawn(({ args, child }) => {
    const outputPath = args[args.indexOf('--output-last-message') + 1]; child.stdin.on('finish', () => { fs.writeFileSync(outputPath, 'not json'); child.emit('close', 0); });
  }) });
  const result = await provider.compose(codexRequest());
  assert.equal(result.status, 'refused'); assert.equal(result.code, 'COMPOSITION_PROVIDER_RESPONSE_INVALID');
});

test('Codex CLI provider makes a non-zero worker exit retryable/unavailable', async () => {
  const provider = createCodexCliProvider({ timeoutMs: 1000, spawn: fakeCodexSpawn(({ child }) => { child.stdin.on('finish', () => { child.stderr.write('bad worker'); child.emit('close', 2); }); }) });
  await assert.rejects(() => provider.compose(codexRequest()), error => error.code === 'COMPOSITION_PROVIDER_UNAVAILABLE');
});

test('Codex CLI provider terminates an overdue worker as a composition timeout', async () => {
  let killed = false;
  const provider = createCodexCliProvider({ timeoutMs: 10, spawn: () => { const child = new EventEmitter(); child.stdin = new PassThrough(); child.stderr = new PassThrough(); child.kill = () => { killed = true; }; return child; } });
  await assert.rejects(() => provider.compose(codexRequest()), error => error.code === 'COMPOSITION_PROVIDER_TIMEOUT');
  assert.equal(killed, true);
});

test('runner accepts a mock quality provider then hands only a valid no-send package to a mock Graph writer', async () => {
  const result = await executors.execute('email_reply_draft', packet(inbound), { context_loading_contract: { composition_intent: { mode: 'reply_inbound' } } }, {}, qualityProvider('Hi Alice,\n\nYes — I’ll send the agreed scope today.\n\nBest,'));
  assert.equal(result.ok, true); assert.equal(result.output.composition_provider.id, 'mock_composition_provider_v1');
  assert.equal(result.output.draft.to[0], 'alice@example.test'); assert.equal(result.output.send, false);
  // This is the exact writer admission check used before a Graph call; it is the mock-Graph seam.
  assert.equal(emailDraft.validateCompositionPackage(result.output).draft.body.includes('agreed scope'), true);
});

test('runner supports bounded latest-outbound follow-up without Reply All to Tom', async () => {
  const result = await executors.execute('email_reply_draft', packet(followUp), { context_loading_contract: { composition_intent: { mode: 'follow_up_outbound', manual: true } } }, {}, qualityProvider('Hi Alice,\n\nJust following up on the next step.\n\nBest,'));
  assert.equal(result.ok, true); assert.equal(result.output.mode, 'follow_up_outbound');
  assert.equal(result.output.recipient_proof.address, 'alice@example.test'); assert.equal(result.output.recipient_proof.strategy, 'new_draft_to_original_non_tom_recipient');
});

test('provider refusal, timeout, and invalid result are retryable runner blockers rather than fallback prose', async () => {
  const task = { context_loading_contract: { composition_intent: { mode: 'reply_inbound' } } };
  const refused = await executors.execute('email_reply_draft', packet(inbound), task, {}, createMockProvider({ schema: RESPONSE_SCHEMA, status: 'refused', code: 'NEEDS_HUMAN_JUDGEMENT', message: 'Substantive judgement required.' }));
  assert.equal(refused.ok, false); assert.equal(refused.code, 'NEEDS_HUMAN_JUDGEMENT');
  const timeout = await executors.execute('email_reply_draft', packet(inbound), task, {}, { id: 'timeout-test', async compose() { const err = new Error('timeout'); err.code = 'COMPOSITION_PROVIDER_TIMEOUT'; throw err; } });
  assert.equal(timeout.ok, false); assert.equal(timeout.code, 'COMPOSITION_PROVIDER_TIMEOUT');
  const invalid = await executors.execute('email_reply_draft', packet(inbound), task, {}, createMockProvider({ schema: RESPONSE_SCHEMA, status: 'composed', mode: 'reply_inbound', recipient: 'wrong@example.test', draft: { body: 'wrong' }, send: false }));
  assert.equal(invalid.ok, false); assert.equal(invalid.code, 'COMPOSITION_PROVIDER_RESULT_MISMATCH');
});
