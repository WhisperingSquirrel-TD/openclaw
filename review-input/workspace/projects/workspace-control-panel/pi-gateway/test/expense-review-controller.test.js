const assert = require('node:assert/strict');
const test = require('node:test');
const { createExpenseReviewController } = require('../src/expense-review');

test('expense review decision invokes only fixed Python control arguments and refreshes snapshot', async () => {
  const calls = [];
  let response;
  const controller = createExpenseReviewController({
    snapshotPath: '/fixed/snapshot.json', financeRoot: '/fixed/finance', databasePath: '/fixed/ledger.sqlite3',
    parseBody: async () => ({ expense_id: 'exp_1', decision: 'confirm', facts: { supplier: 'Acme' } }),
    run: async (binary, args, options) => {
      calls.push({ binary, args, options });
      return { stdout: args[0] === '-m' ? JSON.stringify({ expense: { expense_id: 'exp_1' } }) : '' };
    },
    sendJson: (_, status, body) => { response = { status, body }; return true; },
    success: (data) => ({ ok: true, data }), failure: (code, message) => ({ ok: false, error: { code, message } }),
    logger: { info() {}, warn() {} }
  });
  await controller.handle({ method: 'POST' }, {}, '/expenses/review/decision');
  assert.equal(response.status, 200);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].args.slice(0, 7), ['-m', 'seer_finance.ledger.expense_review_control', '--database', '/fixed/ledger.sqlite3', 'review', '--expense-id', 'exp_1']);
  assert.equal(calls[0].args.includes('--facts-json'), true);
  assert.equal(calls[1].args[0], '-c');
});

test('expense review decision rejects unsupported decisions before process invocation', async () => {
  let response; let called = false;
  const controller = createExpenseReviewController({
    parseBody: async () => ({ expense_id: 'exp_1', decision: 'post' }), run: async () => { called = true; },
    sendJson: (_, status, body) => { response = { status, body }; return true; },
    success: (data) => ({ ok: true, data }), failure: (code, message) => ({ ok: false, error: { code, message } })
  });
  await controller.handle({ method: 'POST' }, {}, '/expenses/review/decision');
  assert.equal(response.status, 400); assert.equal(response.body.error.code, 'EXPENSE_REVIEW_DECISION_INVALID'); assert.equal(called, false);
});
