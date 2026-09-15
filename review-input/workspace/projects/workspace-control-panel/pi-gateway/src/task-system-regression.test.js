'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs');
const test = require('node:test');

async function withGateway(run, controllerOptions = {}) {
  const previousHome = process.env.HOME;
  const testHome = fs.mkdtempSync(path.join(os.tmpdir(), 'task-system-regression-'));
  const modulePath = require.resolve('./task-system');
  delete require.cache[modulePath];
  process.env.HOME = testHome;
  const { createTaskSystemController } = require('./task-system');
  const controller = createTaskSystemController(controllerOptions);
  const server = http.createServer(async (req, res) => {
    const handled = await controller(req, res, new URL(req.url, 'http://localhost').pathname);
    if (!handled) { res.statusCode = 404; res.end(); }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = async (method, route, payload) => {
    const response = await fetch(`${base}${route}`, {
      method,
      headers: { 'content-type': 'application/json' },
      body: payload === undefined ? undefined : JSON.stringify({ payload }),
    });
    return { status: response.status, body: await response.json() };
  };
  try { await run(request); }
  finally {
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(testHome, { recursive: true, force: true });
    if (previousHome === undefined) delete process.env.HOME; else process.env.HOME = previousHome;
    delete require.cache[modulePath];
  }
}

async function createReadyPair(request, suffix) {
  const task = (await request('POST', '/tasks', {
    title: `Regression parent ${suffix}`,
    state: 'open',
  })).body.entity;
  const subtask = (await request('POST', '/subtasks', {
    parent_id: task.id,
    title: `Regression subtask ${suffix}`,
    next_action: 'Run bounded internal verification.',
    success_definition: 'The bounded verification has a recorded result.',
    owner: 'L1',
    risk: 'LOW',
    execution_mode: 'do_now',
    readiness_state: 'execute_ready',
    state: 'todo',
    primary_source_kind: 'test',
    primary_source_ref: 'task-system-regression-test',
    verified_summary: 'Test-only controlled record.',
  })).body.entity;
  return { task, subtask };
}

test('email_draft_v1 rejects summary-only context without exact email evidence', async () => {
  await withGateway(async (request) => {
    const { task, subtask } = await createReadyPair(request, 'email');
    const entityId = 'entRegressionEmail';
    const registered = await request('POST', '/task-system/context-broker/fixture/register', {
      entity_id: entityId,
      sources: [
        { source_id: 'srcRegressionCurrent', source_ref: 'refRegressionCurrent', source_kind: 'sharepoint', role: 'current', content: 'Current summary only.', content_availability: 'full', freshness_status: 'fresh', required_evidence: true },
        { source_id: 'srcRegressionRecap', source_ref: 'refRegressionRecap', source_kind: 'sharepoint', role: 'dated_artifact', content: 'Recap of an email, not its exact body.', content_availability: 'full', freshness_status: 'fresh', required_evidence: true },
      ],
    });
    assert.equal(registered.status, 200);
    await request('POST', '/task-system/context-broker/bindings/register', {
      task_id: task.id, subtask_id: subtask.id, entity_id: entityId, profile: 'email_draft_v1',
    });
    const loaded = await request('POST', '/task-system/context-broker/load', {
      task_id: task.id, subtask_id: subtask.id, entity_id: entityId, profile: 'email_draft_v1', purpose: 'Prepare a held draft only if exact email evidence is present.',
    });
    assert.equal(loaded.status, 200);
    assert.equal(loaded.body.outcome, 'context_incomplete');
    assert.ok(loaded.body.coverage_gaps.some((gap) => gap.code === 'EXACT_EMAIL_THREAD_EVIDENCE_MISSING'));
  });
});

test('operator releases a lease and preserves block rather than recovering blocked work', async () => {
  await withGateway(async (request) => {
    const { task, subtask } = await createReadyPair(request, 'lease');
    await request('PATCH', '/task-system/operator-state', { mode: 'auto_one', enabled: true, max_risk: 'MEDIUM', allow_medium_prepare: true });
    await request('POST', '/task-system/operator-signal', { parent_task_id: task.id, reason: 'regression test' });
    const claimed = await request('POST', '/task-system/operator-check', { parent_task_id: task.id });
    assert.equal(claimed.body.outcome, 'claimed', JSON.stringify(claimed.body));
    assert.equal(claimed.body.start_result.advanced, true);
    await request('PATCH', `/subtasks/${subtask.id}`, {
      state: 'todo', readiness_state: 'blocked', execution_mode: 'blocked',
      blockers_json: [{ type: 'coverage_incomplete', status: 'blocked', detail: 'Exact source absent.' }],
    });
    const reconciled = await request('POST', '/task-system/operator-check', { parent_task_id: task.id });
    assert.equal(reconciled.body.outcome, 'blocked');
    assert.equal(reconciled.body.reason, 'leased_subtask_blocked_or_not_ready');
    const state = await request('GET', '/task-system/operator-state');
    assert.equal(state.body.state.active_subtask_id, null);
    const reread = await request('GET', `/subtasks/${subtask.id}`);
    assert.equal(reread.body.entity.state, 'todo');
    assert.equal(reread.body.entity.readiness_state, 'blocked');
  });
});
