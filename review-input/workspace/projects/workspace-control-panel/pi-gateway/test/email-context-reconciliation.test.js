'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const executors = require('../src/executors');

function packet(items) { return { items }; }
function item(source_kind, source_role, source_id, content, extra = {}) {
  return { source_kind, source_role, source_id, source_ref: source_id, content, freshness_status: 'fresh', ...extra };
}

test('commercial email reconciliation preserves completed preparation with provenance', () => {
  const context = packet([
    item('email', 'dated_artifact', 'email_stuart', 'From: Stuart\nCan you confirm the vendor price and suitability matrix?'),
    item('sharepoint', 'current', 'croyde-current', 'Croyde vendor selection current project record'),
    item('sharepoint', 'dated_artifact', 'vendor-scorecard', 'Vendor scorecard and cost comparison: licence, setup and integration costs at four-to-six-user scale; Must/Should requirements and offline capability.', { extraction: { format: 'xlsx', sheet: 'Cost comparison', range: 'A1:H18', cell_references: ['A4', 'B4'] } }),
  ]);
  const reconciliation = executors.reconcileExistingWork(context);
  assert.equal(reconciliation.status, 'reconciled');
  assert.equal(reconciliation.classifications[0].classification, 'already_considered');
  assert.deepEqual(reconciliation.classifications[0].provenance.extraction, { format: 'xlsx', sheet: 'Cost comparison', range: 'A1:H18', cell_references: ['A4', 'B4'] });
  const output = { draft_text: 'Cost was already considered in the vendor scorecard and cost comparison.', existing_work_reconciliation: reconciliation };
  assert.equal(executors.validateAgainstPacket('email_reply_draft', output, context).ok, true);
});

test('commercial email rejects generic future-tense regeneration', () => {
  const context = packet([
    item('email', 'dated_artifact', 'email_stuart', 'From: Stuart\nPlease confirm vendor price and comparison.'),
    item('sharepoint', 'dated_artifact', 'scorecard', 'Vendor scorecard includes cost comparison and licence/setup costs.'),
  ]);
  const result = executors.validateAgainstPacket('email_reply_draft', { draft_text: "I'll make sure we cover the cost comparison." }, context);
  assert.equal(result.ok, false);
  assert.equal(result.code, 'COMPLETED_WORK_RECAST_AS_FUTURE');
});

test('commercial acknowledgement may quote a customer future-work question without becoming a Tom promise', () => {
  const context = packet([
    item('email', 'dated_artifact', 'email_waqas', 'From: Waqas\nCan you confirm the integration pricing and whether you will compare the options?'),
  ]);
  const result = executors.validateAgainstPacket('email_reply_draft', { draft_text: 'Hi,\n\nThanks for your email. I’ve received your question: “Can you confirm the integration pricing and whether you will compare the options?”\n\nBest,' }, context);
  assert.equal(result.ok, true);
  assert.equal(result.reconciliation.status, 'coverage_incomplete');
});

test('later Tom outbound suppresses duplicate reply drafting', () => {
  const context = packet([item('email', 'dated_artifact', 'email_stuart', 'From: Stuart\nOriginal request\n\n---\n\nFrom: tom@stackstoneconsulting.co.uk\nSent: later\nAlready replied.')]);
  const result = executors.detectLaterTomOutbound(context);
  assert.equal(result.source_ref, 'email_stuart');
});
