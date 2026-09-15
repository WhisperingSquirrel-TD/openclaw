const fs = require('fs');
const path = require('path');

function safeId(value) {
  return String(value || '').trim();
}

function readJsonIfExists(filePath, fallback) {
  try {
    if (!filePath || !fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (_) {
    return fallback;
  }
}

function createAiBriefingsController(options) {
  const config = options.config || {};
  const sendJson = options.sendJson;
  const success = options.success;
  const failure = options.failure;
  const parseBody = options.parseBody;

  const aiConfig = config.aiBriefings || {};
  const baseUrl = String(aiConfig.baseUrl || 'http://127.0.0.1:8766').replace(/\/$/, '');
  const defaultMode = String(aiConfig.defaultMode || 'generate_only');
  const testTargetsPath = aiConfig.testTargetsPath ? path.resolve(aiConfig.testTargetsPath) : '';

  async function readBody(req) {
    return parseBody(req);
  }

  function testTargets() {
    const raw = readJsonIfExists(testTargetsPath, { targets: [] });
    const items = Array.isArray(raw.targets) ? raw.targets : [];
    return items
      .map((item) => ({
        id: safeId(item.id),
        crm_id: safeId(item.crm_id),
        company_name: String(item.company_name || '').trim(),
        website_url: String(item.website_url || '').trim(),
        contact_name: String(item.contact_name || '').trim(),
        contact_email: String(item.contact_email || '').trim(),
        campaign_segment: String(item.campaign_segment || '').trim() || null
      }))
      .filter((item) => item.id && item.crm_id && item.company_name && item.website_url && item.contact_email);
  }

  async function serviceFetch(routePath, init = {}) {
    const response = await fetch(`${baseUrl}${routePath}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init.headers || {})
      }
    });

    const text = await response.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch (_) {
      payload = { raw: text };
    }

    return { response, payload };
  }

  async function proxyJson(res, routePath, init = {}) {
    const { response, payload } = await serviceFetch(routePath, init);
    return sendJson(res, response.status, payload);
  }

  async function createRunWithTargets(body) {
    const availableTargets = testTargets();
    const selectedIds = Array.isArray(body.selectedIds) && body.selectedIds.length
      ? body.selectedIds.map((item) => safeId(item)).filter(Boolean)
      : availableTargets.map((item) => item.id);

    const selectedTargets = availableTargets.filter((item) => selectedIds.includes(item.id));
    if (!selectedTargets.length) {
      const err = new Error('No valid test targets selected');
      err.status = 400;
      err.code = 'NO_TEST_TARGETS_SELECTED';
      throw err;
    }

    const runCreate = await serviceFetch('/runs/create', {
      method: 'POST',
      body: JSON.stringify({
        name: body.name || `AI briefing test run - ${new Date().toISOString()}`,
        mode: body.mode || defaultMode,
        notes: body.notes || 'Created via workspace control bridge using registered AI briefing test targets.'
      })
    });

    if (!runCreate.response.ok || !runCreate.payload?.run?.id) {
      const err = new Error(runCreate.payload?.error || 'Failed to create briefing run');
      err.status = runCreate.response.status || 502;
      err.code = 'AI_BRIEFING_RUN_CREATE_FAILED';
      err.service = runCreate.payload;
      throw err;
    }

    const runId = Number(runCreate.payload.run.id);
    const addResults = [];
    for (const target of selectedTargets) {
      const addResult = await serviceFetch('/targets/add', {
        method: 'POST',
        body: JSON.stringify({
          crm_id: target.crm_id,
          company_name: target.company_name,
          website_url: target.website_url,
          contact_name: target.contact_name || null,
          contact_email: target.contact_email,
          campaign_segment: target.campaign_segment,
          force_regenerate: Boolean(body.forceRegenerate),
          run_id: runId,
          post_generation_action: body.post_generation_action || defaultMode
        })
      });

      addResults.push({
        target: target.id,
        ok: addResult.response.ok,
        status: addResult.response.status,
        payload: addResult.payload
      });

      if (!addResult.response.ok) {
        const err = new Error(addResult.payload?.error || `Failed to add target ${target.id}`);
        err.status = addResult.response.status || 502;
        err.code = 'AI_BRIEFING_TARGET_ADD_FAILED';
        err.service = addResult.payload;
        throw err;
      }
    }

    const summaryResult = await serviceFetch(`/runs/${runId}/summary`);
    if (!summaryResult.response.ok) {
      const err = new Error(summaryResult.payload?.error || 'Failed to fetch run summary');
      err.status = summaryResult.response.status || 502;
      err.code = 'AI_BRIEFING_RUN_SUMMARY_FAILED';
      err.service = summaryResult.payload;
      throw err;
    }

    return {
      run: runCreate.payload.run,
      selectedTargets,
      addResults,
      summary: summaryResult.payload.summary,
      summaryPayload: summaryResult.payload
    };
  }

  async function handle(req, res, pathname) {
    if (pathname === '/ai-briefings/health' && req.method === 'GET') {
      const { response, payload } = await serviceFetch('/health');
      return sendJson(res, response.status, success({
        gateway: 'workspace-pi-gateway',
        serviceBaseUrl: baseUrl,
        upstream: payload
      }));
    }

    if (pathname === '/ai-briefings/test-targets' && req.method === 'GET') {
      return sendJson(res, 200, success({ targets: testTargets() }));
    }

    if (pathname === '/ai-briefings/runs' && req.method === 'GET') {
      return proxyJson(res, '/runs');
    }

    if (pathname === '/ai-briefings/runs/create' && req.method === 'POST') {
      const body = await readBody(req);
      return proxyJson(res, '/runs/create', { method: 'POST', body: JSON.stringify(body) });
    }

    if (pathname === '/ai-briefings/runs/create-from-test-targets' && req.method === 'POST') {
      const body = await readBody(req);
      const payload = await createRunWithTargets(body);
      return sendJson(res, 201, success(payload));
    }

    const runSummaryMatch = pathname.match(/^\/ai-briefings\/runs\/(\d+)\/summary$/);
    if (runSummaryMatch && req.method === 'GET') {
      return proxyJson(res, `/runs/${runSummaryMatch[1]}/summary`);
    }

    const runWatchMatch = pathname.match(/^\/ai-briefings\/runs\/(\d+)\/watch$/);
    if (runWatchMatch && req.method === 'POST') {
      return proxyJson(res, '/runs/watch', { method: 'POST', body: JSON.stringify({ run_id: Number(runWatchMatch[1]) }) });
    }

    if (pathname === '/ai-briefings/targets/add' && req.method === 'POST') {
      const body = await readBody(req);
      return proxyJson(res, '/targets/add', { method: 'POST', body: JSON.stringify(body) });
    }

    if (pathname === '/ai-briefings/briefings' && req.method === 'GET') {
      const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
      const runId = url.searchParams.get('run_id');
      return proxyJson(res, runId ? `/briefings?run_id=${encodeURIComponent(runId)}` : '/briefings');
    }

    if (pathname === '/ai-briefings/briefings/submit' && req.method === 'POST') {
      const body = await readBody(req);
      const submitResult = await serviceFetch('/briefings/submit', { method: 'POST', body: JSON.stringify(body) });
      if (!submitResult.response.ok) {
        return sendJson(res, submitResult.response.status, submitResult.payload);
      }
      const runId = body && body.run_id ? Number(body.run_id) : null;
      const autoWatch = body && Object.prototype.hasOwnProperty.call(body, 'auto_watch')
        ? Boolean(body.auto_watch)
        : true;
      if (runId && autoWatch) {
        serviceFetch('/runs/watch', { method: 'POST', body: JSON.stringify({ run_id: runId }) }).catch(() => {});
      }
      return sendJson(res, 200, submitResult.payload);
    }

    if (pathname === '/ai-briefings/briefings/poll' && req.method === 'POST') {
      const body = await readBody(req);
      return proxyJson(res, '/briefings/poll', { method: 'POST', body: JSON.stringify(body) });
    }

    if (pathname === '/ai-briefings/send-packs' && req.method === 'GET') {
      const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
      const runId = url.searchParams.get('run_id');
      if (!runId) {
        return proxyJson(res, '/send-packs');
      }
      const { response, payload } = await serviceFetch(`/briefings?run_id=${encodeURIComponent(runId)}`);
      if (!response.ok) {
        return sendJson(res, response.status, payload);
      }
      const briefingItems = payload.items || [];
      const briefingIds = new Set(briefingItems.map((item) => Number(item.id)).filter(Number.isFinite));
      const sendPacks = (await serviceFetch('/send-packs')).payload.items || [];
      const filtered = sendPacks.filter((item) => briefingIds.has(Number(item.briefing_queue_id)));
      return sendJson(res, 200, success({ items: filtered }));
    }

    if (pathname === '/ai-briefings/send-packs/build' && req.method === 'POST') {
      const body = await readBody(req);
      return proxyJson(res, '/send-packs/build', { method: 'POST', body: JSON.stringify(body) });
    }

    if (pathname === '/ai-briefings/send-packs/approve' && req.method === 'POST') {
      const body = await readBody(req);
      return proxyJson(res, '/send-packs/approve', { method: 'POST', body: JSON.stringify(body) });
    }

    if (pathname === '/ai-briefings/send-packs/resend' && req.method === 'POST') {
      const body = await readBody(req);
      return proxyJson(res, '/send-packs/resend', { method: 'POST', body: JSON.stringify(body) });
    }

    if (pathname === '/ai-briefings/outbound' && req.method === 'GET') {
      return proxyJson(res, '/outbound');
    }

    if (pathname === '/ai-briefings/outbound/schedule' && req.method === 'POST') {
      const body = await readBody(req);
      return proxyJson(res, '/outbound/schedule', { method: 'POST', body: JSON.stringify(body) });
    }

    if (pathname === '/ai-briefings/outbound/run' && req.method === 'POST') {
      const body = await readBody(req);
      return proxyJson(res, '/outbound/run', { method: 'POST', body: JSON.stringify(body) });
    }

    return false;
  }

  return { handle };
}

module.exports = {
  createAiBriefingsController
};
