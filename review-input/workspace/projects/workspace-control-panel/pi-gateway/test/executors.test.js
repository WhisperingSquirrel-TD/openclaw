'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const executors = require('../src/executors');

function exactThread(messages) {
  return {
    items: [{
      source_id: 'src_thread', source_ref: 'src_thread', source_kind: 'email', source_role: 'dated_artifact', required_evidence: true,
      content: messages.join('\n\n---\n\n'),
    }],
  };
}

test('duplicate suppression ignores an Outlook draft but retains verified sent outbound evidence', () => {
  const inbound = 'From: waqas@example.com\nDate: 2026-08-07T15:59:00Z\nSubject: Joblogic\nIsDraft: false\n\nPlease send the technical response.';
  const draft = 'From: tom@stackstoneconsulting.co.uk\nDate: 2026-08-08T10:42:47Z\nSubject: RE: Joblogic\nIsDraft: true\n\nDraft body.';
  const sent = 'From: tom@stackstoneconsulting.co.uk\nDate: 2026-08-08T10:42:47Z\nSubject: RE: Joblogic\nIsDraft: false\n\nSent body.';
  assert.equal(executors.detectLaterTomOutbound(exactThread([inbound, draft])), null);
  assert.ok(executors.detectLaterTomOutbound(exactThread([inbound, sent])));
});

test('an exact commercial inbound can produce a held acknowledgement without a dated preparation artefact', () => {
  const sourceRef = 'src_exact_waqas';
  const packet = {
    items: [{
      source_id: sourceRef,
      source_ref: sourceRef,
      source_kind: 'email',
      source_role: 'dated_artifact',
      required_evidence: true,
      content: [
        'From: Waqas Qureshi <waqas@example.com>',
        'To: Tom Dean <tom@stackstoneconsulting.co.uk>',
        'Date: 2026-08-07T15:59:00Z',
        'Subject: Joblogic Demonstration Session',
        '',
        'Please confirm the proposed demonstration session time and the pricing approach.',
      ].join('\n'),
    }],
  };
  const output = {
    schema: 'email-composition-package-v1',
    mode: 'reply_inbound',
    draft_text: 'Hi Waqas,\n\nThanks for your email. I have received your request.\n\nBest,',
    draft: { body: 'Hi Waqas,\n\nThanks for your email. I have received your request.\n\nBest,' },
    recipient_proof: { address: 'waqas@example.com' },
    reply_to_source_ref: sourceRef,
    latest_message_evidence: { source_ref: sourceRef, evidence_excerpt: 'From: Waqas Qureshi\nDate: 2026-08-07T15:59:00Z' },
    thread_continuity_check: 'passed',
    contextual_flow_check: 'passed',
    source_refs: [sourceRef],
  };

  const result = executors.validateAgainstPacket('email_reply_draft', output, packet);
  assert.equal(result.ok, true);
  assert.equal(result.reconciliation.status, 'coverage_incomplete');
});
