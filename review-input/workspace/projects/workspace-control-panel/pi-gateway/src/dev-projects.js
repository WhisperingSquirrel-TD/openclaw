const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

function nowIso() {
  return new Date().toISOString();
}

function ensureArrayCommand(value, fieldName) {
  if (!Array.isArray(value) || value.length === 0 || value.some((item) => typeof item !== 'string' || !item.trim())) {
    const err = new Error(`${fieldName} must be a non-empty array of strings`);
    err.code = 'INVALID_DEV_PROJECT_CONFIG';
    throw err;
  }
  return value;
}

function safeId(value) {
  return String(value || '').trim();
}

function pidIsRunning(pid) {
  if (!pid || Number.isNaN(Number(pid))) return false;
  try {
    process.kill(Number(pid), 0);
    return true;
  } catch (_) {
    return false;
  }
}

function tailLines(text, maxLines) {
  const lines = String(text || '').split(/\r?\n/);
  return lines.slice(-maxLines).join('\n').trim();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readJsonIfExists(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (_) {
    return fallback;
  }
}

function writeJsonAtomic(filePath, data) {
  const tmp = `${filePath}.tmp`;
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
  fs.renameSync(tmp, filePath);
}

function resolveMaybeRelative(baseDir, candidate) {
  if (!candidate) return null;
  if (String(candidate).startsWith('~/')) {
    const home = process.env.HOME || '/home/tomdean88';
    return path.join(home, String(candidate).slice(2));
  }
  return path.isAbsolute(candidate) ? candidate : path.resolve(baseDir, candidate);
}

function loadEnvFile(envFilePath) {
  const env = {};
  if (!envFilePath || !fs.existsSync(envFilePath)) return env;
  try {
    const lines = fs.readFileSync(envFilePath, 'utf8').split(/\r?\n/);
    for (const raw of lines) {
      let line = raw.trim();
      if (!line || line.startsWith('#') || !line.includes('=')) continue;
      if (line.startsWith('export ')) line = line.slice(7);
      const idx = line.indexOf('=');
      const key = line.slice(0, idx).trim();
      const value = line.slice(idx + 1).trim().replace(/^['"]|['"]$/g, '');
      if (key) env[key] = value;
    }
  } catch (_) {}
  return env;
}

function normaliseProject(project) {
  const id = safeId(project.id);
  const name = String(project.name || '').trim();
  const projectPath = String(project.path || '').trim();
  if (!id || !name || !projectPath) {
    const err = new Error('Each dev project needs id, name, and path');
    err.code = 'INVALID_DEV_PROJECT_CONFIG';
    throw err;
  }

  const resolvedPath = path.resolve(projectPath);
  const preview = project.preview || {};
  const test = project.test || {};

  return {
    id,
    name,
    description: String(project.description || '').trim(),
    framework: String(project.framework || '').trim(),
    repo: String(project.repo || '').trim(),
    path: resolvedPath,
    preview: preview.startCommand ? {
      startCommand: ensureArrayCommand(preview.startCommand, `preview.startCommand (${id})`),
      cwd: path.resolve(preview.cwd ? resolveMaybeRelative(resolvedPath, preview.cwd) : resolvedPath),
      env: preview.env && typeof preview.env === 'object' ? preview.env : {},
      envFile: preview.envFile ? String(preview.envFile) : '',
      url: preview.url ? String(preview.url) : '',
      urlFile: preview.urlFile ? String(preview.urlFile) : '',
      healthUrl: preview.healthUrl ? String(preview.healthUrl) : '',
      startupTimeoutSeconds: Number(preview.startupTimeoutSeconds || 45),
      logFile: preview.logFile ? String(preview.logFile) : '',
      urlCommand: preview.urlCommand ? ensureArrayCommand(preview.urlCommand, `preview.urlCommand (${id})`) : null,
      urlCommandCwd: path.resolve(preview.urlCommandCwd ? resolveMaybeRelative(resolvedPath, preview.urlCommandCwd) : (preview.cwd ? resolveMaybeRelative(resolvedPath, preview.cwd) : resolvedPath)),
      urlPattern: preview.urlPattern ? String(preview.urlPattern) : ''
    } : null,
    test: test.command ? {
      command: ensureArrayCommand(test.command, `test.command (${id})`),
      cwd: path.resolve(test.cwd ? resolveMaybeRelative(resolvedPath, test.cwd) : resolvedPath),
      env: test.env && typeof test.env === 'object' ? test.env : {},
      envFile: test.envFile ? String(test.envFile) : '',
      timeoutSeconds: Number(test.timeoutSeconds || 900),
      logFile: test.logFile ? String(test.logFile) : ''
    } : null
  };
}

function createDevProjectsController(options) {
  const config = options.config || {};
  const projectRoot = options.projectRoot;
  const sendJson = options.sendJson;
  const success = options.success;
  const failure = options.failure;
  const parseBody = options.parseBody;

  const devConfig = config.devProjects || {};
  const registryPath = path.resolve(devConfig.registryPath || path.join(projectRoot, 'dev-projects.json'));
  const runtimeRoot = path.resolve(devConfig.runtimeRoot || path.join(projectRoot, '.runtime', 'dev-projects'));
  const eventsLogPath = path.resolve(devConfig.eventsLogPath || path.join(runtimeRoot, 'events.jsonl'));

  function appendEvent(event) {
    fs.mkdirSync(path.dirname(eventsLogPath), { recursive: true });
    fs.appendFileSync(eventsLogPath, `${JSON.stringify({ time: nowIso(), ...event })}\n`);
  }

  function getRegistry() {
    const raw = readJsonIfExists(registryPath, { projects: [] });
    const projects = Array.isArray(raw.projects) ? raw.projects.map(normaliseProject) : [];
    return { projects };
  }

  function getProjectOrThrow(projectId) {
    const registry = getRegistry();
    const project = registry.projects.find((item) => item.id === projectId);
    if (!project) {
      const err = new Error(`Unknown dev project: ${projectId}`);
      err.code = 'DEV_PROJECT_NOT_FOUND';
      err.status = 404;
      throw err;
    }
    return project;
  }

  function runtimeDirFor(projectId) {
    return path.join(runtimeRoot, projectId);
  }

  function statePathFor(projectId) {
    return path.join(runtimeDirFor(projectId), 'state.json');
  }

  function ensureRuntimeDir(projectId) {
    const dir = runtimeDirFor(projectId);
    fs.mkdirSync(dir, { recursive: true });
    return dir;
  }

  function readState(projectId) {
    return readJsonIfExists(statePathFor(projectId), {
      projectId,
      preview: {
        status: 'idle',
        pid: null,
        startedAt: null,
        stoppedAt: null,
        exitCode: null,
        signal: null,
        previewUrl: ''
      },
      test: {
        status: 'idle',
        pid: null,
        startedAt: null,
        completedAt: null,
        exitCode: null,
        signal: null
      }
    });
  }

  function writeState(projectId, state) {
    writeJsonAtomic(statePathFor(projectId), state);
  }

  function extractUrl(text, pattern) {
    const source = String(text || '');
    if (!source.trim()) return '';
    if (pattern) {
      try {
        const re = new RegExp(pattern, 'g');
        const matches = Array.from(source.matchAll(re));
        if (matches.length) {
          const last = matches[matches.length - 1];
          return String(last[1] || last[0] || '').trim();
        }
      } catch (_) {}
    }
    const generic = source.match(/https:\/\/[^\s"'`]+/g);
    return generic && generic.length ? generic[generic.length - 1].trim() : '';
  }

  function resolvePreviewUrl(project) {
    if (!project.preview) return '';
    if (project.preview.urlFile) {
      const urlFile = resolveMaybeRelative(project.path, project.preview.urlFile);
      try {
        const fromFile = fs.readFileSync(urlFile, 'utf8').trim();
        if (fromFile) return fromFile;
      } catch (_) {}
    }
    const logPath = previewLogPath(project);
    if (logPath && fs.existsSync(logPath)) {
      try {
        const fromLogs = extractUrl(fs.readFileSync(logPath, 'utf8'), project.preview.urlPattern);
        if (fromLogs) return fromLogs;
      } catch (_) {}
    }
    if (project.preview.urlCommand) {
      try {
        const [command, ...args] = project.preview.urlCommand;
        const result = spawnSync(command, args, {
          cwd: project.preview.urlCommandCwd,
          env: previewEnv(project),
          encoding: 'utf8',
          timeout: 15000
        });
        const combined = `${result.stdout || ''}\n${result.stderr || ''}`;
        const fromCommand = extractUrl(combined, project.preview.urlPattern);
        if (fromCommand) return fromCommand;
      } catch (_) {}
    }
    if (project.preview.url && !/127\.0\.0\.1|localhost/.test(project.preview.url)) return project.preview.url;
    return project.preview.url || '';
  }

  function previewEnv(project) {
    const fileEnv = loadEnvFile(resolveMaybeRelative(project.path, project.preview?.envFile || ''));
    return { ...process.env, ...fileEnv, ...(project.preview?.env || {}) };
  }

  function inferPreviewStatus(project, state) {
    const current = state?.preview?.status || 'idle';
    const logPath = state?.preview?.logPath || previewLogPath(project);
    if (!logPath || !fs.existsSync(logPath)) return current;
    try {
      const tail = tailLines(fs.readFileSync(logPath, 'utf8'), 80).toLowerCase();
      if (/git push|enumerating objects|writing objects|to https:\/\/github|to github\.com/.test(tail)) return 'pushing';
      if (/vercel|deployment|inspect|queued|building in|ready preview/.test(tail)) return 'deploying';
      if (/npm run build|next build|creating an optimized production build|typecheck|tsc --noemit/.test(tail)) return 'building';
    } catch (_) {}
    return current;
  }

  function testEnv(project) {
    const fileEnv = loadEnvFile(resolveMaybeRelative(project.path, project.test?.envFile || ''));
    return { ...process.env, ...fileEnv, ...(project.test?.env || {}) };
  }

  function previewLogPath(project) {
    if (!project.preview) return '';
    return resolveMaybeRelative(project.path, project.preview.logFile) || path.join(runtimeDirFor(project.id), 'preview.log');
  }

  function testLogPath(project) {
    if (!project.test) return '';
    return resolveMaybeRelative(project.path, project.test.logFile) || path.join(runtimeDirFor(project.id), 'test.log');
  }

  function refreshStateFromReality(project, state) {
    const next = JSON.parse(JSON.stringify(state));
    if (project.preview) {
      next.preview.logPath = previewLogPath(project);
      next.preview.healthUrl = project.preview.healthUrl || '';
      next.preview.previewUrl = resolvePreviewUrl(project) || next.preview.previewUrl || '';
    }
    if (next.preview && next.preview.pid) {
      if (pidIsRunning(next.preview.pid)) {
        next.preview.status = inferPreviewStatus(project, next);
      } else {
        next.preview.pid = null;
        if (['running', 'building', 'pushing', 'deploying'].includes(next.preview.status)) {
          next.preview.status = next.preview.exitCode === 0 ? (next.preview.previewUrl ? 'stopped' : 'deploying') : 'stopped';
          next.preview.stoppedAt = next.preview.stoppedAt || nowIso();
        }
      }
    }
    if (next.preview && next.preview.status === 'deploying' && !next.preview.pid && next.preview.previewUrl) {
      next.preview.status = 'stopped';
      next.preview.exitCode = next.preview.exitCode == null ? 0 : next.preview.exitCode;
      next.preview.completedAt = next.preview.completedAt || nowIso();
      next.preview.stoppedAt = next.preview.stoppedAt || next.preview.completedAt;
    }
    if (next.test && next.test.pid && !pidIsRunning(next.test.pid) && next.test.status === 'running') {
      next.test.status = next.test.completedAt ? 'completed' : 'stopped';
      next.test.completedAt = next.test.completedAt || nowIso();
    }
    if (project.test) {
      next.test.logPath = testLogPath(project);
    }
    return next;
  }

  function projectSummary(project) {
    const state = refreshStateFromReality(project, readState(project.id));
    writeState(project.id, state);
    return {
      id: project.id,
      name: project.name,
      description: project.description,
      framework: project.framework,
      repo: project.repo,
      path: project.path,
      capabilities: {
        preview: Boolean(project.preview),
        test: Boolean(project.test),
        remotePreviewStop: false
      },
      preview: state.preview,
      test: state.test
    };
  }

  async function startPreview(project) {
    if (!project.preview) {
      const err = new Error(`Project ${project.id} does not define a preview action`);
      err.code = 'DEV_PREVIEW_NOT_CONFIGURED';
      err.status = 400;
      throw err;
    }

    const state = refreshStateFromReality(project, readState(project.id));
    if (state.preview.status === 'running' && pidIsRunning(state.preview.pid)) {
      return { alreadyRunning: true, project: projectSummary(project) };
    }

    ensureRuntimeDir(project.id);
    const logPath = previewLogPath(project);
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    const logStream = fs.createWriteStream(logPath, { flags: 'a' });
    const [command, ...args] = project.preview.startCommand;
    const child = spawn(command, args, {
      cwd: project.preview.cwd,
      env: previewEnv(project),
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    child.stdout.pipe(logStream);
    child.stderr.pipe(logStream);
    child.unref();

    const nextState = refreshStateFromReality(project, state);
    nextState.preview = {
      ...nextState.preview,
      status: 'building',
      pid: child.pid,
      startedAt: nowIso(),
      stoppedAt: null,
      exitCode: null,
      signal: null,
      logPath,
      previewUrl: resolvePreviewUrl(project) || nextState.preview.previewUrl || '',
      healthUrl: project.preview.healthUrl || ''
    };
    writeState(project.id, nextState);
    appendEvent({ kind: 'preview-start', projectId: project.id, pid: child.pid, command: project.preview.startCommand });

    child.on('exit', (code, signal) => {
      const latest = refreshStateFromReality(project, readState(project.id));
      const finishedAt = nowIso();
      latest.preview = {
        ...latest.preview,
        status: code === 0 ? 'deploying' : 'stopped',
        pid: null,
        completedAt: finishedAt,
        stoppedAt: finishedAt,
        exitCode: code,
        signal: signal || null,
        previewUrl: resolvePreviewUrl(project) || latest.preview.previewUrl || ''
      };
      writeState(project.id, latest);
      appendEvent({ kind: 'preview-exit', projectId: project.id, code, signal: signal || null });
    });

    const waitUntil = Date.now() + Math.max(20, Number(project.preview.startupTimeoutSeconds || 45)) * 1000;
    while (Date.now() < waitUntil) {
      await sleep(1500);
      const latest = refreshStateFromReality(project, readState(project.id));
      writeState(project.id, latest);
      if (latest.preview.previewUrl) break;
    }

    return { started: true, project: projectSummary(project) };
  }

  async function stopPreview(project) {
    if (!project.preview) {
      const err = new Error(`Project ${project.id} does not define a preview action`);
      err.code = 'DEV_PREVIEW_NOT_CONFIGURED';
      err.status = 400;
      throw err;
    }
    const state = refreshStateFromReality(project, readState(project.id));
    if (!state.preview.pid || !pidIsRunning(state.preview.pid)) {
      if (state.preview.previewUrl) {
        state.preview.status = 'stopped';
        state.preview.pid = null;
        state.preview.completedAt = state.preview.completedAt || nowIso();
        state.preview.stoppedAt = state.preview.stoppedAt || state.preview.completedAt;
        state.preview.exitCode = state.preview.exitCode == null ? 0 : state.preview.exitCode;
        writeState(project.id, state);
        return {
          unsupported: true,
          message: 'Hosted preview already exists remotely; no local process is running to terminate. Close/teardown must be handled by the hosted provider route when implemented.',
          project: projectSummary(project)
        };
      }
      state.preview.status = 'idle';
      state.preview.pid = null;
      state.preview.stoppedAt = nowIso();
      writeState(project.id, state);
      return { alreadyStopped: true, project: projectSummary(project) };
    }
    process.kill(Number(state.preview.pid), 'SIGTERM');
    state.preview.status = 'stopping';
    state.preview.stoppedAt = nowIso();
    writeState(project.id, state);
    appendEvent({ kind: 'preview-stop', projectId: project.id, pid: state.preview.pid });
    return { stopping: true, project: projectSummary(project) };
  }

  async function startTest(project) {
    if (!project.test) {
      const err = new Error(`Project ${project.id} does not define a test action`);
      err.code = 'DEV_TEST_NOT_CONFIGURED';
      err.status = 400;
      throw err;
    }

    const state = refreshStateFromReality(project, readState(project.id));
    if (state.test.status === 'running' && pidIsRunning(state.test.pid)) {
      return { alreadyRunning: true, project: projectSummary(project) };
    }

    ensureRuntimeDir(project.id);
    const logPath = testLogPath(project);
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.writeFileSync(logPath, '');
    const logStream = fs.createWriteStream(logPath, { flags: 'a' });
    const [command, ...args] = project.test.command;
    const child = spawn(command, args, {
      cwd: project.test.cwd,
      env: testEnv(project),
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    child.stdout.pipe(logStream);
    child.stderr.pipe(logStream);
    child.unref();

    const nextState = refreshStateFromReality(project, state);
    nextState.test = {
      ...nextState.test,
      status: 'running',
      pid: child.pid,
      startedAt: nowIso(),
      completedAt: null,
      exitCode: null,
      signal: null,
      logPath
    };
    writeState(project.id, nextState);
    appendEvent({ kind: 'test-start', projectId: project.id, pid: child.pid, command: project.test.command });

    const timeoutMs = Math.max(30, Number(project.test.timeoutSeconds || 900)) * 1000;
    const timer = setTimeout(() => {
      try {
        process.kill(Number(child.pid), 'SIGTERM');
      } catch (_) {}
    }, timeoutMs);

    child.on('exit', (code, signal) => {
      clearTimeout(timer);
      const latest = refreshStateFromReality(project, readState(project.id));
      latest.test = {
        ...latest.test,
        status: signal === 'SIGTERM' && code === null ? 'timed_out' : 'completed',
        pid: null,
        completedAt: nowIso(),
        exitCode: code,
        signal: signal || null,
        logPath
      };
      writeState(project.id, latest);
      appendEvent({ kind: 'test-exit', projectId: project.id, code, signal: signal || null });
    });

    return { started: true, project: projectSummary(project) };
  }

  async function readLogs(project, streamName, lines) {
    const state = refreshStateFromReality(project, readState(project.id));
    writeState(project.id, state);
    const maxLines = Math.max(20, Math.min(400, Number(lines || 120)));
    const logPath = streamName === 'test' ? state.test.logPath : state.preview.logPath;
    if (!logPath || !fs.existsSync(logPath)) {
      return {
        stream: streamName,
        logPath: logPath || '',
        tail: ''
      };
    }
    const content = await fsp.readFile(logPath, 'utf8');
    return {
      stream: streamName,
      logPath,
      tail: tailLines(content, maxLines)
    };
  }

  async function handle(req, res, pathname) {
    if (pathname === '/dev/projects' && req.method === 'GET') {
      const registry = getRegistry();
      return sendJson(res, 200, success({ projects: registry.projects.map(projectSummary) }));
    }

    const match = pathname.match(/^\/dev\/projects\/([^/]+)(?:\/(status|logs|test|start-preview|stop-preview|restart-preview))?$/);
    if (!match) return false;

    const projectId = decodeURIComponent(match[1]);
    const action = match[2] || '';
    const project = getProjectOrThrow(projectId);

    if (!action && req.method === 'GET') {
      return sendJson(res, 200, success({ project: projectSummary(project) }));
    }

    if (action === 'status' && req.method === 'GET') {
      return sendJson(res, 200, success({ project: projectSummary(project) }));
    }

    if (action === 'logs' && req.method === 'GET') {
      const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
      const streamName = String(url.searchParams.get('stream') || 'preview');
      const lines = Number(url.searchParams.get('lines') || 120);
      return sendJson(res, 200, success(await readLogs(project, streamName, lines)));
    }

    if (action === 'test' && req.method === 'POST') {
      await parseBody(req);
      return sendJson(res, 202, success(await startTest(project)));
    }

    if (action === 'start-preview' && req.method === 'POST') {
      await parseBody(req);
      return sendJson(res, 202, success(await startPreview(project)));
    }

    if (action === 'stop-preview' && req.method === 'POST') {
      await parseBody(req);
      return sendJson(res, 202, success(await stopPreview(project)));
    }

    if (action === 'restart-preview' && req.method === 'POST') {
      await parseBody(req);
      await stopPreview(project);
      return sendJson(res, 202, success(await startPreview(project)));
    }

    return sendJson(res, 404, failure('NOT_FOUND', 'Route not found'));
  }

  return { handle };
}

module.exports = {
  createDevProjectsController
};
