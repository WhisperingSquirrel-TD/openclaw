const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const baseConfig = require('../config.json');
const { createGatewayServer } = require('../src/server');

function quietLogger() {
  return { info() {}, warn() {}, error() {} };
}

async function withGateway(snapshotContent, run) {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'pi-gateway-expense-review-'));
  const snapshotPath = path.join(tempDir, 'expense-review-snapshot.json');
  if (snapshotContent !== undefined) await fs.writeFile(snapshotPath, snapshotContent, 'utf8');

  const config = JSON.parse(JSON.stringify(baseConfig));
  config.workspaceRoot = tempDir;
  config.snapshotRoot = path.join(tempDir, 'snapshots');
  config.archiveRoot = path.join(tempDir, 'archive');
  config.auditLogPath = path.join(tempDir, 'audit.jsonl');
  config.expenseReview.snapshotPath = snapshotPath;
  const gateway = createGatewayServer({ config, authToken: 'test-token', logger: quietLogger() });

  try {
    const address = await gateway.start(0);
    await run({
      snapshotPath,
      request: async (pathname, options = {}) => {
        const response = await fetch(`http://127.0.0.1:${address.port}${pathname}`, options);
        return { status: response.status, body: await response.json() };
      }
    });
  } finally {
    await gateway.close();
    await fs.rm(tempDir, { recursive: true, force: true });
  }
}

test('GET /expenses/review requires gateway bearer authentication', async () => {
  await withGateway('{"review_count":1}', async ({ request }) => {
    const response = await request('/expenses/review');
    assert.equal(response.status, 401);
    assert.deepEqual(response.body, {
      ok: false,
      error: { code: 'AUTH_FAILED', message: 'Authentication failed' }
    });
  });
});

test('GET /expenses/review returns the configured snapshot without modifying it', async () => {
  const content = '{"generated_at":"2026-08-10T18:00:00Z","items":[{"id":1}]}';
  await withGateway(content, async ({ request, snapshotPath }) => {
    const response = await request('/expenses/review', {
      headers: { authorization: 'Bearer test-token' }
    });
    assert.equal(response.status, 200);
    assert.deepEqual(response.body, {
      ok: true,
      data: { generated_at: '2026-08-10T18:00:00Z', items: [{ id: 1 }] }
    });
    assert.equal(await fs.readFile(snapshotPath, 'utf8'), content);
  });
});

test('GET /expenses/review reports an unavailable or malformed snapshot as 503', async (t) => {
  await t.test('missing snapshot', async () => {
    await withGateway(undefined, async ({ request }) => {
      const response = await request('/expenses/review', {
        headers: { authorization: 'Bearer test-token' }
      });
      assert.equal(response.status, 503);
      assert.deepEqual(response.body, {
        ok: false,
        error: {
          code: 'EXPENSE_REVIEW_SNAPSHOT_UNAVAILABLE',
          message: 'Expense review snapshot is not available'
        }
      });
    });
  });

  await t.test('malformed snapshot', async () => {
    await withGateway('{not json', async ({ request }) => {
      const response = await request('/expenses/review', {
        headers: { authorization: 'Bearer test-token' }
      });
      assert.equal(response.status, 503);
      assert.deepEqual(response.body, {
        ok: false,
        error: {
          code: 'EXPENSE_REVIEW_SNAPSHOT_MALFORMED',
          message: 'Expense review snapshot is malformed'
        }
      });
    });
  });
});
