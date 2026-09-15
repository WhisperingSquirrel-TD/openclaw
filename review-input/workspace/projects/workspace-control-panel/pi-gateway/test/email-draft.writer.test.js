'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { createCompositionDraft, stripRedundantAuthoredName } = require('../src/email-draft');

const messageId = 'Abcdefghijklmnopqrstuvwx';
function fakeDb() { return { prepare() { return { get() { return null; }, run() { return {}; } }; } }; }
function entities() {
  const task = { id: 'task_writer', primary_source_ref: `microsoft_inbox:email:conversation:${messageId}` };
  // Brief-to-work composition children retain the intake reference; the exact inbound anchor lives on the parent task.
  const subtask = { id: 'sub_writer', parent_id: task.id, owner: 'L1', execution_mode: 'prepare_for_review', primary_source_ref: 'brief-intake:intake_writer' };
  return { task, subtask };
}
function packageFor(mode) {
  const follow = mode === 'follow_up_outbound';
  return {
    schema: 'email-composition-package-v1', mode,
    draft: { body: 'A bounded, review-only message.', subject: follow ? 'RE: Original topic' : 'Original topic' },
    subject: follow ? 'RE: Original topic' : undefined,
    anchor_proof: { source_ref: 'src_exact', content_hash: 'sha256:anchor' },
    recipient_proof: follow ? { strategy: 'new_draft_to_original_non_tom_recipient', address: 'client@example.com' } : { strategy: 'createReplyAll_exact_inbound', address: 'client@example.com' },
    no_send_proof: { send_endpoint_called: false }, unresolved_questions: ['Confirm tone before sending.'], review_state: 'prepared_for_review',
  };
}
function replyPayload(compositionPackage) {
  const payload = { task_id: 'task_writer', subtask_id: 'sub_writer', composition_package: compositionPackage };
  Object.defineProperty(payload, 'protected_reply_binding', { value: { schema: 'broker-proven-microsoft-message-locator-v1', task_id: 'task_writer', subtask_id: 'sub_writer', message_locator: messageId }, enumerable: false });
  return payload;
}
function depsFor(calls, responses) {
  const { task, subtask } = entities();
  return {
    getEntity(_db, kind) { return kind === 'task' ? task : subtask; }, addEvent() {},
    getAccessToken: async () => 'mock-token', getSignature: async () => '<div>signature</div>',
    graph: async (_token, method, endpoint, body) => { calls.push({ method, endpoint, body }); return responses(method, endpoint, body); },
  };
}

test('writer uses createReplyAll on the exact inbound anchor and verifies Drafts', async () => {
  const calls = [];
  const result = await createCompositionDraft(fakeDb(), replyPayload(packageFor('reply_inbound')), depsFor(calls, (method, endpoint) => {
    if (method === 'POST') return { id: 'draft-reply', body: { content: '<blockquote>thread</blockquote>' }, subject: 'Original topic' };
    if (method === 'PATCH') return { subject: 'RE: Original topic' };
    if (endpoint === '/me/mailFolders/drafts?$select=id') return { id: 'drafts-folder' };
    return { id: 'draft-reply', isDraft: true, parentFolderId: 'drafts-folder', subject: 'RE: Original topic', webLink: 'https://draft.example/reply', conversationId: 'conversation-1', body: { content: '<div>A bounded, review-only message.</div>' } };
  }));
  assert.equal(result.ok, true); assert.equal(result.verified, true);
  assert.equal(calls[0].endpoint, `/me/messages/${messageId}/createReplyAll`);
  assert.equal(calls.some(call => /\/send$/.test(call.endpoint)), false);
});

test('writer denies a reply package when a caller supplies only a task email locator', async () => {
  await assert.rejects(() => createCompositionDraft(fakeDb(), { task_id: 'task_writer', subtask_id: 'sub_writer', composition_package: packageFor('reply_inbound') }, depsFor([], () => ({}))), /broker-proven exact Microsoft email binding/);
});

test('writer rejects a reply draft that is in Drafts but belongs to a different conversation', async () => {
  const calls = [];
  await assert.rejects(() => createCompositionDraft(fakeDb(), replyPayload(packageFor('reply_inbound')), depsFor(calls, (method, endpoint) => {
    if (method === 'POST') return { id: 'draft-wrong-thread', body: { content: '<blockquote>thread</blockquote>' }, subject: 'Original topic' };
    if (method === 'PATCH') return { subject: 'RE: Original topic' };
    if (endpoint === '/me/mailFolders/drafts?$select=id') return { id: 'drafts-folder' };
    if (endpoint.includes(messageId)) return { id: messageId, conversationId: 'conversation-original' };
    return { id: 'draft-wrong-thread', isDraft: true, parentFolderId: 'drafts-folder', subject: 'RE: Original topic', webLink: 'https://draft.example/wrong-thread', conversationId: 'conversation-standalone' };
  })), /original conversation/);
  assert.equal(calls[0].endpoint, `/me/messages/${messageId}/createReplyAll`);
});

test('writer creates a new follow-up draft addressed only to verified original recipient', async () => {
  const calls = [];
  const result = await createCompositionDraft(fakeDb(), { task_id: 'task_writer', subtask_id: 'sub_writer', composition_package: packageFor('follow_up_outbound') }, depsFor(calls, (method, endpoint) => {
    if (method === 'POST') return { id: 'draft-follow', subject: 'RE: Original topic' };
    if (endpoint === '/me/mailFolders/drafts?$select=id') return { id: 'drafts-folder' };
    return { id: 'draft-follow', isDraft: true, parentFolderId: 'drafts-folder', subject: 'RE: Original topic', webLink: 'https://draft.example/follow', toRecipients: [{ emailAddress: { address: 'client@example.com' } }], body: { content: '<div>A bounded, review-only message.</div>' } };
  }));
  assert.equal(result.ok, true); assert.equal(calls[0].endpoint, '/me/messages');
  assert.deepEqual(calls[0].body.toRecipients, [{ emailAddress: { address: 'client@example.com' } }]);
  assert.equal(calls.some(call => call.endpoint.includes('createReplyAll')), false);
});

test('writer rejects a created message unless Graph proves it is in Drafts', async () => {
  const calls = [];
  await assert.rejects(() => createCompositionDraft(fakeDb(), replyPayload(packageFor('reply_inbound')), depsFor(calls, (method, endpoint) => {
    if (method === 'POST') return { id: 'draft-unverified', body: { content: '<blockquote>thread</blockquote>' } };
    if (method === 'PATCH') return {};
    if (endpoint === '/me/mailFolders/drafts?$select=id') return { id: 'drafts-folder' };
    return { id: 'draft-unverified', isDraft: false, parentFolderId: 'sent-folder', conversationId: 'conversation-1' };
  })), /Draft verification failed/);
});

test('writer creates and verifies an intentionally unaddressed anchorless draft without Reply All', async () => {
  const calls = [];
  const pkg = {
    schema: 'email-composition-package-v1', mode: 'reply_without_exact_anchor',
    draft: { body: 'A bounded, review-only message.', subject: 'Proposal follow-up' }, subject: 'Proposal follow-up',
    anchor_proof: { source_ref: 'crm_current', content_hash: 'sha256:anchor' },
    recipient_proof: { strategy: 'new_draft_unaddressed_recipient_unresolved', address: null },
    no_send_proof: { send_endpoint_called: false }, unresolved_questions: ['Add recipient before sending.'], review_state: 'prepared_for_review',
  };
  const result = await createCompositionDraft(fakeDb(), { task_id: 'task_writer', subtask_id: 'sub_writer', composition_package: pkg }, depsFor(calls, (method, endpoint) => {
    if (method === 'POST') return { id: 'draft-unaddressed', subject: 'Proposal follow-up' };
    if (endpoint === '/me/mailFolders/drafts?$select=id') return { id: 'drafts-folder' };
    return { id: 'draft-unaddressed', isDraft: true, parentFolderId: 'drafts-folder', subject: 'Proposal follow-up', webLink: 'https://draft.example/unaddressed', toRecipients: [], body: { content: '<div>A bounded, review-only message.</div>' } };
  }));
  assert.equal(result.ok, true); assert.equal(result.verification.recipient_verified, true);
  assert.equal(result.draft_route, 'fallback_unlinked');
  assert.equal(result.verification.linkage_status, 'fallback_unlinked');
  assert.equal(calls[0].endpoint, '/me/messages');
  assert.equal('toRecipients' in calls[0].body, false);
  assert.equal(calls.some(call => call.endpoint.includes('createReplyAll')), false);
  assert.equal(calls.some(call => /\/send$/.test(call.endpoint)), false);
});

test('writer creates an addressed anchorless draft as a new message, never Reply All', async () => {
  const calls = [];
  const pkg = {
    schema: 'email-composition-package-v1', mode: 'reply_without_exact_anchor',
    draft: { body: 'A bounded, review-only message.', subject: 'Proposal follow-up' }, subject: 'Proposal follow-up',
    anchor_proof: { source_ref: 'crm_current', content_hash: 'sha256:anchor' },
    recipient_proof: { strategy: 'new_draft_to_verified_task_recipient', address: 'alex@example.com' },
    no_send_proof: { send_endpoint_called: false }, unresolved_questions: ['Confirm tone before sending.'], review_state: 'prepared_for_review',
  };
  const result = await createCompositionDraft(fakeDb(), { task_id: 'task_writer', subtask_id: 'sub_writer', composition_package: pkg }, depsFor(calls, (method, endpoint) => {
    if (method === 'POST') return { id: 'draft-anchorless-addressed', subject: 'Proposal follow-up' };
    if (endpoint === '/me/mailFolders/drafts?$select=id') return { id: 'drafts-folder' };
    return { id: 'draft-anchorless-addressed', isDraft: true, parentFolderId: 'drafts-folder', subject: 'Proposal follow-up', webLink: 'https://draft.example/anchorless-addressed', toRecipients: [{ emailAddress: { address: 'alex@example.com' } }], body: { content: '<div>A bounded, review-only message.</div>' } };
  }));
  assert.equal(result.ok, true); assert.equal(calls[0].endpoint, '/me/messages');
  assert.deepEqual(calls[0].body.toRecipients, [{ emailAddress: { address: 'alex@example.com' } }]);
  assert.equal(calls.some(call => call.endpoint.includes('createReplyAll')), false);
  assert.equal(calls.some(call => /\/send$/.test(call.endpoint)), false);
});

test('writer strips a trailing authored Tom sign-off so governed signature remains the sole identity block', () => {
  assert.equal(stripRedundantAuthoredName('Hi Jess,\n\nBest,\nTom'), 'Hi Jess,\n\nBest,');
  assert.equal(stripRedundantAuthoredName('Hi Jess,\n\nKind regards,\nTom Dean'), 'Hi Jess,\n\nKind regards,');
  assert.equal(stripRedundantAuthoredName('Hi Jess,\n\nBest,'), 'Hi Jess,\n\nBest,');
});
