const assert = require('node:assert/strict');
const test = require('node:test');
const { createExpenseReviewController } = require('../src/expense-review');

function controller(body, calls, response) {
  return createExpenseReviewController({
    financeRoot: '/fixed/finance', databasePath: '/fixed/ledger.sqlite3', snapshotPath: '/fixed/snapshot.json',
    parseBody: async () => body,
    run: async (binary, args) => { calls.push({ binary, args }); return { stdout: args[0] === '-m' ? JSON.stringify({ outcome: 'posted', finance_ledger_ref: 'sqlite:tx1' }) : '' }; },
    sendJson: (_, status, payload) => { response.value = { status, payload }; return true; },
    success: (data) => ({ ok: true, data }), failure: (code, message) => ({ ok: false, error: { code, message } }), logger: { info() {}, warn() {} }
  });
}

test('finance post only invokes the fixed expense control module for an expense-direction payload', async () => {
  const calls = []; const response = {};
  const value = controller({ expense_id: 'exp_1', transaction: { txn_id: 'tx1', direction: 'expense', source_ref: 'source:1' } }, calls, response);
  await value.handle({ method: 'POST' }, {}, '/expenses/review/post');
  assert.equal(response.value.status, 200); assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].args.slice(0, 7), ['-m', 'seer_finance.ledger.expense_review_control', '--database', '/fixed/ledger.sqlite3', 'post', '--expense-id', 'exp_1']);
});

test('finance post rejects income before any process invocation', async () => {
  const calls = []; const response = {};
  const value = controller({ expense_id: 'income_1', transaction: { direction: 'income' } }, calls, response);
  await value.handle({ method: 'POST' }, {}, '/expenses/review/post');
  assert.equal(response.value.status, 400); assert.equal(response.value.payload.error.code, 'EXPENSE_FINANCE_POST_INVALID'); assert.equal(calls.length, 0);
});
