'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const provider = require('./email-composition-provider');

function packet(thread) { return { items: [{ source_id: 'emailSource1', source_ref: 'emailRef1', source_kind: 'email', source_role: 'dated_artifact', required_evidence: true, content: thread, composition_manifest: { included_message_count: 2 } }] }; }
const inbound = `From: Alice <alice@example.test>\nDate: 2026-08-06T10:00:00Z\nSubject: Re: Plan\n\nCan you send the agreed scope?`;
const outbound = `From: Alice <alice@example.test>\nDate: 2026-08-05T10:00:00Z\nSubject: Plan\n\nThanks.\n\n---\n\nFrom: Tom Dean <tom@stackstoneconsulting.co.uk>\nDate: 2026-08-06T10:00:00Z\nSubject: Re: Plan\n\nCould you confirm the next step?`;

test('bounded identity resolver supports latest inbound and latest outbound follow-up', () => {
  assert.equal(provider.resolveBoundedIdentity(packet(inbound), { mode: 'reply_inbound' }).recipient, 'alice@example.test');
  const follow = provider.resolveBoundedIdentity(packet(outbound), { mode: 'follow_up_outbound' });
  assert.equal(follow.recipient, 'alice@example.test');
  assert.equal(follow.strategy, 'new_draft_to_original_non_tom_recipient');
});

test('bounded identity resolver returns one focused clarification for ambiguity', () => {
  const result = provider.resolveBoundedIdentity({ items: [] }, { mode: 'reply_inbound', manual: true });
  assert.equal(result.ok, false); assert.match(result.clarification, /exact email thread/i);
});

test('anchorless reply uses only registered bounded context and exposes recipient state without a thread', () => {
  const contextPacket = { items: [{ source_id: 'crmCurrent1', source_ref: 'crmCurrent1', source_kind: 'crm', source_role: 'current', content_availability: 'full', freshness_status: 'fresh', content: 'Current account context.' }] };
  const unaddressed = provider.createRequest(contextPacket, { mode: 'reply_without_exact_anchor', subject: 'Proposal follow-up' });
  assert.equal(unaddressed.ok, true); assert.equal(unaddressed.request.identity.strategy, 'new_draft_unaddressed_recipient_unresolved');
  assert.equal(unaddressed.request.identity.recipient, 'RECIPIENT_UNRESOLVED');
  assert.equal(unaddressed.request.intent.exact_source_ref, 'crmCurrent1');
  const addressed = provider.createRequest(contextPacket, { mode: 'reply_without_exact_anchor', recipient_email: 'alex@example.com', subject: 'Proposal follow-up' });
  assert.equal(addressed.ok, true); assert.equal(addressed.request.identity.recipient, 'alex@example.com');
  assert.equal(addressed.request.identity.strategy, 'new_draft_to_verified_task_recipient');
});

test('quality-provider schema derives modes from the model-neutral contract', async () => {
  let sent;
  const quality = provider.createOpenAIQualityProvider({ apiKey: 'test-key', fetch: async (_url, options) => {
    sent = JSON.parse(options.body);
    return { ok: true, json: async () => ({ choices: [{ message: { content: JSON.stringify({ schema: provider.RESPONSE_SCHEMA, status: 'composed', mode: 'reply_without_exact_anchor', recipient: 'RECIPIENT_UNRESOLVED', send: false, draft: { body: 'Hi Alex,\n\nDraft copy.\n\nBest,', subject: 'Proposal follow-up' }, code: null, message: null }) } }] }) };
  } });
  const contextPacket = { items: [{ source_id: 'crmCurrent1', source_ref: 'crmCurrent1', source_kind: 'crm', source_role: 'current', content_availability: 'full', freshness_status: 'fresh', content: 'Current account context.' }] };
  const request = provider.createRequest(contextPacket, { mode: 'reply_without_exact_anchor', subject: 'Proposal follow-up' }).request;
  const response = await quality.compose(request);
  assert.equal(response.mode, 'reply_without_exact_anchor');
  assert.deepEqual(sent.response_format.json_schema.schema.properties.mode.enum, ['reply_inbound', 'follow_up_outbound', 'standalone_new_message', 'reply_without_exact_anchor']);
});

test('safe fallback is explicitly labelled, acknowledges visible non-ask content, and refuses empty evidence', async () => {
  const fallback = provider.createDeterministicSafeFallbackProvider();
  const request = provider.createRequest(packet(inbound.replace('Can you send the agreed scope?', 'Could you confirm receipt?')), { mode: 'reply_inbound' }).request;
  const result = await fallback.compose(request);
  assert.equal(result.status, 'composed'); assert.match(result.provider_note, /not a quality-model best draft/i);
  const noAsk = provider.createRequest(packet(inbound.replace('Can you send the agreed scope?', 'Noted.')), { mode: 'reply_inbound' }).request;
  assert.equal((await fallback.compose(noAsk)).status, 'composed');
  const empty = provider.createRequest(packet(inbound.replace('Can you send the agreed scope?', '')), { mode: 'reply_inbound' }).request;
  assert.equal((await fallback.compose(empty)).status, 'refused');
});

test('quality provider sends only the bounded request and returns a no-send structured response', async () => {
  let sent;
  const quality = provider.createOpenAIQualityProvider({ apiKey: 'test-key', model: 'test-model', fetch: async (_url, options) => {
    sent = JSON.parse(options.body);
    return { ok: true, json: async () => ({ choices: [{ message: { content: JSON.stringify({ schema: provider.RESPONSE_SCHEMA, status: 'composed', mode: 'reply_inbound', recipient: 'alice@example.test', send: false, draft: { body: 'Hi Alice,\n\nYes.\n\nBest,', subject: 'Re: Plan' }, code: null, message: null }) } }] }) };
  } });
  const request = provider.createRequest(packet(inbound), { mode: 'reply_inbound' }).request;
  const response = await quality.compose(request);
  assert.equal(response.send, false); assert.equal(response.recipient, 'alice@example.test');
  assert.equal(sent.model, 'test-model'); assert.match(sent.messages[0].content, /UNSENT/i);
  assert.equal(sent.messages[1].content, JSON.stringify(request));
});
