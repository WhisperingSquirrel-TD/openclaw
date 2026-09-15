const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const { execFile } = require('child_process');

function createLinkedinMirrorController(options = {}) {
  const workspaceRoot = path.resolve(options.workspaceRoot);
  const logger = options.logger;
  const sendJson = options.sendJson;
  const success = options.success;
  const failure = options.failure;
  const parseBody = options.parseBody;

  const projectRoot = path.join(workspaceRoot, 'projects', 'linkedin-message-mirror');
  const venvPython = path.join(projectRoot, '.venv', 'bin', 'python');
  const captureScript = path.join(projectRoot, 'scripts', 'capture_linkedin_messages.py');
  const routeScript = path.join(projectRoot, 'scripts', 'route_linkedin_messages.py');
  const postsScript = path.join(projectRoot, 'scripts', 'capture_linkedin_posts.py');
  const jsonOut = path.join(workspaceRoot, 'memory', 'linkedin-messages.json');
  const mdOut = path.join(workspaceRoot, 'LINKEDIN_MESSAGES.md');
  const eventsOut = path.join(workspaceRoot, 'memory', 'linkedin-mirror-events.json');
  const routeState = path.join(workspaceRoot, 'memory', 'linkedin-mirror-state.json');
  const proposalsOut = path.join(workspaceRoot, 'memory', 'linkedin-crm-proposals.json');
  const proposalsMd = path.join(workspaceRoot, 'LINKEDIN_CRM_PROPOSALS.md');
  const profileDir = path.join(path.dirname(workspaceRoot), 'linkedin-browser-profile');
  const postsRawOut = path.join(workspaceRoot, 'memory', 'linkedin-posts-raw.json');
  const postsStateOut = path.join(workspaceRoot, 'memory', 'linkedin-posts-capture-state.json');
  const postsMdOut = path.join(workspaceRoot, 'LINKEDIN_POSTS.md');
  const postsTracker = path.join(workspaceRoot, 'stackstone', 'linkedin-posts.md');

  function safeLimit(value) {
    const n = Number(value || 1);
    if (!Number.isFinite(n)) return 1;
    return Math.max(1, Math.min(3, Math.floor(n)));
  }

  function safeLoginWait(value) {
    const n = Number(value || 240);
    if (!Number.isFinite(n)) return 240;
    return Math.max(0, Math.min(600, Math.floor(n)));
  }

  function commandAvailable(filePath) {
    try {
      fs.accessSync(filePath, fs.constants.X_OK);
      return true;
    } catch (_) {
      return false;
    }
  }

  function runFixedPython(script, args, { timeoutMs = 120000 } = {}) {
    return new Promise((resolve) => {
      const startedAt = Date.now();
      const child = execFile(venvPython, [script, ...args], {
        cwd: workspaceRoot,
        timeout: timeoutMs,
        maxBuffer: 768 * 1024,
        env: {
          ...process.env,
          HOME: process.env.HOME || '/home/tomdean88',
          OPENCLAW_WORKSPACE: workspaceRoot,
          LINKEDIN_CAPTURE_PROFILE: profileDir,
        },
      }, (error, stdout, stderr) => {
        resolve({
          ok: !error,
          exit_code: error?.code ?? 0,
          signal: error?.signal || null,
          duration_ms: Date.now() - startedAt,
          stdout: String(stdout || '').slice(-12000),
          stderr: String(stderr || '').slice(-12000),
          error: error ? error.message : null,
        });
      });
      child.stdin?.end();
    });
  }

  function runCapture({ headed = true, limitThreads = 1, loginWaitSeconds = 240 } = {}) {
    const args = [
      '--limit-threads', String(safeLimit(limitThreads)),
      '--write',
      '--json-out', jsonOut,
      '--md-out', mdOut,
      '--profile-dir', profileDir,
      '--login-wait-seconds', String(safeLoginWait(loginWaitSeconds)),
    ];
    if (headed) args.push('--headed');

    return new Promise((resolve) => {
      runFixedPython(captureScript, args, { timeoutMs: Math.max(45000, (safeLoginWait(loginWaitSeconds) + 90) * 1000) }).then(async (processResult) => {
        let snapshot = null;
        try {
          snapshot = JSON.parse(await fsp.readFile(jsonOut, 'utf8'));
        } catch (_) {}
        const coverage = snapshot?.coverage_state || (processResult.ok ? 'unknown' : 'blocked');
        const status = coverage === 'complete'
          ? 'captured'
          : coverage === 'login_required'
            ? 'login_required'
            : coverage === 'coverage_incomplete'
              ? 'coverage_incomplete'
              : 'blocked';
        const payload = {
          ok: processResult.ok || Boolean(snapshot),
          status,
          coverage_state: coverage,
          thread_count: snapshot?.thread_count ?? 0,
          message_count: snapshot?.message_count ?? 0,
          blocker: snapshot?.blocker || processResult.error,
          generated_at: snapshot?.generated_at || null,
          outputs: {
            json: 'memory/linkedin-messages.json',
            markdown: 'LINKEDIN_MESSAGES.md',
          },
          command: {
            fixed_helper: 'projects/linkedin-message-mirror/scripts/capture_linkedin_messages.py',
            arbitrary_exec: false,
            headed: Boolean(headed),
            limit_threads: safeLimit(limitThreads),
            login_wait_seconds: safeLoginWait(loginWaitSeconds),
          },
          process: processResult,
        };
        logger?.info?.('linkedin_capture_finished', {
          outcome: status,
          coverage_state: coverage,
          thread_count: payload.thread_count,
          message_count: payload.message_count,
          duration_ms: payload.process.duration_ms,
        });
        resolve(payload);
      });
    });
  }

  async function runPostsCapture({ headed = false } = {}) {
    const args = ['--write', '--reconcile', '--raw-out', postsRawOut, '--state-out', postsStateOut, '--md-out', postsMdOut, '--tracker', postsTracker];
    if (headed) args.push('--headed');
    const processResult = await runFixedPython(postsScript, args, { timeoutMs: 120000 });
    let state = null;
    try { state = JSON.parse(await fsp.readFile(postsStateOut, 'utf8')); } catch (_) {}
    const coverage = state?.last_coverage_state || (processResult.ok ? 'unknown' : 'blocked');
    const payload = { ok: processResult.ok, status: coverage === 'complete' ? 'captured' : coverage, coverage_state: coverage,
      post_count: state?.post_count ?? 0, new_post_count: state?.new_post_count ?? 0, updated_engagement_count: state?.updated_engagement_count ?? 0,
      last_successful_visible_capture: state?.last_successful_visible_capture || null, blocker: state?.last_blocker || processResult.error,
      outputs: { raw: 'memory/linkedin-posts-raw.json', state: 'memory/linkedin-posts-capture-state.json', markdown: 'LINKEDIN_POSTS.md', tracker: 'stackstone/linkedin-posts.md' },
      command: { fixed_helper: 'projects/linkedin-message-mirror/scripts/capture_linkedin_posts.py', arbitrary_exec: false, headed: Boolean(headed) }, process: processResult };
    logger?.info?.('linkedin_posts_capture_finished', { outcome: coverage, post_count: payload.post_count, new_post_count: payload.new_post_count, duration_ms: processResult.duration_ms });
    return payload;
  }

  async function runRoute({ mode = 'only_new' } = {}) {
    const args = [
      '--snapshot', jsonOut,
      '--events-out', eventsOut,
      '--state', routeState,
      '--proposals-out', proposalsOut,
      '--proposals-md', proposalsMd,
      '--write',
    ];
    if (mode === 'baseline') args.push('--baseline');
    else if (mode === 'only_new') args.push('--only-new');

    const processResult = await runFixedPython(routeScript, args, { timeoutMs: 120000 });
    let proposals = null;
    try {
      proposals = JSON.parse(await fsp.readFile(proposalsOut, 'utf8'));
    } catch (_) {}
    const payload = {
      ok: processResult.ok && Boolean(proposals),
      status: processResult.ok ? 'routed' : 'blocked',
      mode,
      coverage_state: proposals?.coverage_state || null,
      event_count: proposals?.event_count ?? 0,
      new_event_count: proposals?.new_event_count ?? 0,
      proposal_count: Array.isArray(proposals?.proposals) ? proposals.proposals.length : 0,
      outputs: {
        events: 'memory/linkedin-mirror-events.json',
        state: 'memory/linkedin-mirror-state.json',
        proposals: 'memory/linkedin-crm-proposals.json',
        proposals_markdown: 'LINKEDIN_CRM_PROPOSALS.md',
      },
      command: {
        fixed_helper: 'projects/linkedin-message-mirror/scripts/route_linkedin_messages.py',
        arbitrary_exec: false,
        mode,
      },
      process: processResult,
    };
    logger?.info?.('linkedin_route_finished', {
      outcome: payload.status,
      mode,
      coverage_state: payload.coverage_state,
      event_count: payload.event_count,
      new_event_count: payload.new_event_count,
      proposal_count: payload.proposal_count,
      duration_ms: payload.process.duration_ms,
    });
    return payload;
  }

  async function handle(req, res, pathname) {
    if (pathname === '/linkedin-mirror/posts/status' && req.method === 'GET') {
      let state = null; let raw = null;
      try { state = JSON.parse(await fsp.readFile(postsStateOut, 'utf8')); } catch (_) {}
      try { raw = JSON.parse(await fsp.readFile(postsRawOut, 'utf8')); } catch (_) {}
      return sendJson(res, 200, success({ available: commandAvailable(venvPython) && fs.existsSync(postsScript), helper: 'projects/linkedin-message-mirror/scripts/capture_linkedin_posts.py', arbitrary_exec: false,
        outputs: { raw: 'memory/linkedin-posts-raw.json', state: 'memory/linkedin-posts-capture-state.json', markdown: 'LINKEDIN_POSTS.md', tracker: 'stackstone/linkedin-posts.md' }, last_state: state, last_snapshot: raw ? { generated_at: raw.generated_at, coverage_state: raw.coverage_state, post_count: raw.post_count } : null }));
    }
    if (pathname === '/linkedin-mirror/posts/capture' && req.method === 'POST') {
      if (!commandAvailable(venvPython) || !fs.existsSync(postsScript)) return sendJson(res, 503, failure('LINKEDIN_POSTS_HELPER_MISSING', 'Authored-post capture helper or project venv is missing'));
      const body = await parseBody(req); const result = await runPostsCapture({ headed: body.headed === true });
      return sendJson(res, result.ok ? 200 : 500, success(result));
    }

    if (pathname === '/linkedin-mirror/status' && req.method === 'GET') {
      let snapshot = null;
      let proposals = null;
      try {
        snapshot = JSON.parse(await fsp.readFile(jsonOut, 'utf8'));
      } catch (_) {}
      try {
        proposals = JSON.parse(await fsp.readFile(proposalsOut, 'utf8'));
      } catch (_) {}
      return sendJson(res, 200, success({
        available: commandAvailable(venvPython) && fs.existsSync(captureScript) && fs.existsSync(routeScript),
        helper: 'projects/linkedin-message-mirror/scripts/capture_linkedin_messages.py',
        route_helper: 'projects/linkedin-message-mirror/scripts/route_linkedin_messages.py',
        arbitrary_exec: false,
        profile_dir: profileDir,
        outputs: {
          json: 'memory/linkedin-messages.json',
          markdown: 'LINKEDIN_MESSAGES.md',
          events: 'memory/linkedin-mirror-events.json',
          state: 'memory/linkedin-mirror-state.json',
          proposals: 'memory/linkedin-crm-proposals.json',
          proposals_markdown: 'LINKEDIN_CRM_PROPOSALS.md',
        },
        last_snapshot: snapshot ? {
          generated_at: snapshot.generated_at,
          coverage_state: snapshot.coverage_state,
          blocker: snapshot.blocker || null,
          thread_count: snapshot.thread_count || 0,
          message_count: snapshot.message_count || 0,
        } : null,
        last_proposals: proposals ? {
          generated_at: proposals.generated_at,
          mode: proposals.mode,
          coverage_state: proposals.coverage_state,
          event_count: proposals.event_count || 0,
          new_event_count: proposals.new_event_count || 0,
          proposal_count: Array.isArray(proposals.proposals) ? proposals.proposals.length : 0,
        } : null,
      }));
    }

    if (pathname === '/linkedin-mirror/capture' && req.method === 'POST') {
      if (!commandAvailable(venvPython)) return sendJson(res, 503, failure('LINKEDIN_MIRROR_VENV_MISSING', 'Project venv/python is not available'));
      if (!fs.existsSync(captureScript)) return sendJson(res, 503, failure('LINKEDIN_MIRROR_HELPER_MISSING', 'Capture helper script is missing'));
      const body = await parseBody(req);
      const result = await runCapture({
        headed: body.headed !== false,
        limitThreads: body.limit_threads || body.limitThreads || 1,
        loginWaitSeconds: body.login_wait_seconds || body.loginWaitSeconds || 240,
      });
      return sendJson(res, result.ok ? 200 : 500, success(result));
    }

    if (pathname === '/linkedin-mirror/route' && req.method === 'POST') {
      if (!commandAvailable(venvPython)) return sendJson(res, 503, failure('LINKEDIN_MIRROR_VENV_MISSING', 'Project venv/python is not available'));
      if (!fs.existsSync(routeScript)) return sendJson(res, 503, failure('LINKEDIN_MIRROR_ROUTE_HELPER_MISSING', 'Route helper script is missing'));
      const body = await parseBody(req);
      const mode = body.mode === 'baseline' ? 'baseline' : body.mode === 'assess_all' ? 'assess_all' : 'only_new';
      const result = await runRoute({ mode });
      return sendJson(res, result.ok ? 200 : 500, success(result));
    }

    return false;
  }

  return { handle };
}

module.exports = { createLinkedinMirrorController };
