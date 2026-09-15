const fs = require('fs/promises');
const { execFile: nativeExecFile } = require('child_process');
const { promisify } = require('util');

const execFile = promisify(nativeExecFile);
const DECISIONS = new Set(['confirm', 'not_business', 'duplicate']);

function createExpenseReviewController({ snapshotPath, financeRoot, databasePath, sendJson, success, failure, logger, parseBody, run = execFile }) {
  const fixedSnapshotPath = String(snapshotPath || '');
  const fixedFinanceRoot = String(financeRoot || '');
  const fixedDatabasePath = String(databasePath || '');

  async function snapshot(res) {
    let raw;
    try { raw = await fs.readFile(fixedSnapshotPath, 'utf8'); }
    catch (error) {
      if (error.code === 'ENOENT') return sendJson(res, 503, failure('EXPENSE_REVIEW_SNAPSHOT_UNAVAILABLE', 'Expense review snapshot is not available'));
      throw error;
    }
    try {
      const value = JSON.parse(raw);
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid_shape');
      return sendJson(res, 200, success(value));
    } catch (_) {
      logger?.warn('expense_review_snapshot_malformed', { reason: 'invalid_json' });
      return sendJson(res, 503, failure('EXPENSE_REVIEW_SNAPSHOT_MALFORMED', 'Expense review snapshot is malformed'));
    }
  }

  async function decision(req, res) {
    const body = await parseBody(req);
    if (!body || typeof body !== 'object' || Array.isArray(body) || typeof body.expense_id !== 'string' || !DECISIONS.has(body.decision)) {
      return sendJson(res, 400, failure('EXPENSE_REVIEW_DECISION_INVALID', 'expense_id and an allowed decision are required'));
    }
    const facts = body.facts === undefined ? {} : body.facts;
    if (!facts || typeof facts !== 'object' || Array.isArray(facts)) {
      return sendJson(res, 400, failure('EXPENSE_REVIEW_FACTS_INVALID', 'facts must be an object'));
    }
    // Fixed executable/module/database; user values are JSON arguments, never shell text.
    const args = ['-m', 'seer_finance.ledger.expense_review_control', '--database', fixedDatabasePath,
      'review', '--expense-id', body.expense_id, '--decision', body.decision, '--facts-json', JSON.stringify(facts)];
    try {
      const { stdout } = await run('/usr/bin/python3', args, { cwd: fixedFinanceRoot, env: { ...process.env, PYTHONPATH: fixedFinanceRoot }, maxBuffer: 128 * 1024 });
      const result = JSON.parse(stdout);
      await run('/usr/bin/python3', ['-c', "from seer_finance.ledger.database_review_snapshot import write_snapshot; write_snapshot('data/expense-ledger.sqlite3','data/expense-review-snapshot.json')"], { cwd: fixedFinanceRoot, env: { ...process.env, PYTHONPATH: fixedFinanceRoot }, maxBuffer: 128 * 1024 });
      logger?.info('expense_review_decision_applied', { expense_id: body.expense_id, decision: body.decision });
      return sendJson(res, 200, success(result));
    } catch (error) {
      logger?.warn('expense_review_decision_refused', { expense_id: body.expense_id, decision: body.decision, error: String(error.stderr || error.message || error) });
      return sendJson(res, 409, failure('EXPENSE_REVIEW_DECISION_REFUSED', 'The expense decision was refused; source evidence remains unchanged'));
    }
  }

  async function post(req, res) {
    const body = await parseBody(req);
    const transaction = body?.transaction;
    if (!body || typeof body.expense_id !== 'string' || !transaction || typeof transaction !== 'object' || Array.isArray(transaction) || transaction.direction !== 'expense') {
      return sendJson(res, 400, failure('EXPENSE_FINANCE_POST_INVALID', 'an existing expense_id and an expense-direction transaction are required'));
    }
    try {
      const { stdout } = await run('/usr/bin/python3', ['-m', 'seer_finance.ledger.expense_review_control', '--database', fixedDatabasePath,
        'post', '--expense-id', body.expense_id, '--transaction-json', JSON.stringify(transaction)],
        { cwd: fixedFinanceRoot, env: { ...process.env, PYTHONPATH: fixedFinanceRoot }, maxBuffer: 128 * 1024 });
      const result = JSON.parse(stdout);
      await run('/usr/bin/python3', ['-c', "from seer_finance.ledger.database_review_snapshot import write_snapshot; write_snapshot('data/expense-ledger.sqlite3','data/expense-review-snapshot.json')"], { cwd: fixedFinanceRoot, env: { ...process.env, PYTHONPATH: fixedFinanceRoot }, maxBuffer: 128 * 1024 });
      logger?.info('expense_finance_post_applied', { expense_id: body.expense_id });
      return sendJson(res, 200, success(result));
    } catch (error) {
      logger?.warn('expense_finance_post_refused', { expense_id: body?.expense_id, error: String(error.stderr || error.message || error) });
      return sendJson(res, 409, failure('EXPENSE_FINANCE_POST_REFUSED', 'The expense was not finance-posted; review state and source evidence were preserved'));
    }
  }

  async function handle(req, res, pathname) {
    if (pathname === '/expenses/review' && req.method === 'GET') return snapshot(res);
    if (pathname === '/expenses/review/decision' && req.method === 'POST') return decision(req, res);
    if (pathname === '/expenses/review/post' && req.method === 'POST') return post(req, res);
    return false;
  }
  return { handle };
}
module.exports = { createExpenseReviewController };
