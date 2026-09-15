const http = require('http');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const crypto = require('crypto');
const { execFile } = require('child_process');
const { URL } = require('url');

const config = require('../config.json');
const { createDevProjectsController } = require('./dev-projects');
const { createAiBriefingsController } = require('./ai-briefings');
const { createTaskSystemController } = require('./task-system');
const emailDraft = require('./email-draft');
const { createProductionCompositionProvider } = require('./email-composition-provider');
const { createLinkedinMirrorController } = require('./linkedin-mirror');
const { createExpenseReviewController } = require('./expense-review');
const { createLogger } = require('./logger');

const SEARCH_INDEX_REFRESH_MS = 5 * 60 * 1000;
const DEFAULT_SEARCH_ROOTS = ['projects', 'reference', 'stackstone/reference', 'stackstone/crm.md', 'stackstone/partnerships.md'];
const SEARCH_SKIP_DIR_NAMES = new Set(['.git', 'node_modules', '.next', 'dist', 'build', 'coverage', 'tmp', 'sharepoint-cache', 'cargo', '__MACOSX']);

function createGatewayServer(options = {}) {
  const resolvedConfig = options.config || config;
  const logger = options.logger || createLogger({ subsystem: 'workspace-pi-gateway' });
  const workspaceRoot = path.resolve(resolvedConfig.workspaceRoot);
  const snapshotRoot = path.resolve(resolvedConfig.snapshotRoot);
  const archiveRoot = path.resolve(resolvedConfig.archiveRoot);
  const auditLogPath = path.resolve(resolvedConfig.auditLogPath);
  const authToken = options.authToken !== undefined ? options.authToken : (process.env[resolvedConfig.auth.envVar] || '');

  const searchIndexState = {
    entries: [],
    builtAt: null,
    buildPromise: null,
    lastError: null
  };

  const tierLabels = { 1: 'safe', 2: 'guarded', 3: 'protected' };

  function sendJson(res, status, payload) {
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(payload, null, 2));
  }

  function success(data) {
    return { ok: true, data };
  }

  function failure(code, message, extra = {}) {
    return { ok: false, error: { code, message, ...extra } };
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderMarkdownLite(content) {
    const lines = String(content).split(/\r?\n/);
    const html = [];
    let inList = false;
    let inTable = false;

    function closeList() {
      if (inList) {
        html.push('</ul>');
        inList = false;
      }
    }

    function closeTable() {
      if (inTable) {
        html.push('</tbody></table>');
        inTable = false;
      }
    }

    function isTableLine(line) {
      return /^\|.+\|$/.test(line.trim());
    }

    function isTableSeparator(line) {
      return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line.trim());
    }

    function splitTableCells(line) {
      return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => escapeHtml(cell.trim()));
    }

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const nextLine = lines[index + 1] || '';

      if (isTableLine(line) && isTableSeparator(nextLine)) {
        closeList();
        closeTable();
        const headers = splitTableCells(line);
        html.push('<div class="table-wrap"><table><thead><tr>');
        headers.forEach((cell) => html.push(`<th>${cell}</th>`));
        html.push('</tr></thead><tbody>');
        inTable = true;
        index += 1;
        continue;
      }

      if (inTable && isTableLine(line) && !isTableSeparator(line)) {
        const cells = splitTableCells(line);
        html.push('<tr>');
        cells.forEach((cell) => html.push(`<td>${cell}</td>`));
        html.push('</tr>');
        continue;
      }

      closeTable();

      if (/^###\s+/.test(line)) {
        closeList();
        html.push(`<h3>${escapeHtml(line.replace(/^###\s+/, ''))}</h3>`);
        continue;
      }
      if (/^##\s+/.test(line)) {
        closeList();
        html.push(`<h2>${escapeHtml(line.replace(/^##\s+/, ''))}</h2>`);
        continue;
      }
      if (/^#\s+/.test(line)) {
        closeList();
        html.push(`<h1>${escapeHtml(line.replace(/^#\s+/, ''))}</h1>`);
        continue;
      }
      if (/^[-*]\s+/.test(line)) {
        if (!inList) {
          html.push('<ul>');
          inList = true;
        }
        html.push(`<li>${escapeHtml(line.replace(/^[-*]\s+/, ''))}</li>`);
        continue;
      }

      closeList();
      if (!line.trim()) {
        html.push('');
        continue;
      }
      html.push(`<p>${escapeHtml(line)}</p>`);
    }

    closeList();
    closeTable();
    return html.join('\n');
  }

  function normaliseRelativePath(inputPath) {
    const raw = inputPath || '.';
    const normalised = path.posix.normalize(String(raw).replace(/\\/g, '/'));
    return normalised === '.' ? '.' : normalised.replace(/^\/+/, '');
  }

  function resolveWorkspacePath(relativePath) {
    const rel = normaliseRelativePath(relativePath);
    const abs = path.resolve(workspaceRoot, rel === '.' ? '' : rel);
    if (!abs.startsWith(workspaceRoot)) {
      const err = new Error('Path escaped workspace root');
      err.code = 'PATH_DENIED';
      throw err;
    }
    return { rel, abs };
  }

  function rootAllows(rel) {
    if (rel === '.') return true;
    return resolvedConfig.approvedRoots.some((root) => {
      const cleanRoot = normaliseRelativePath(root);
      if (cleanRoot === '.') return true;
      if (cleanRoot.endsWith('/')) {
        const prefix = cleanRoot.replace(/\/$/, '');
        return rel === prefix || rel.startsWith(`${prefix}/`);
      }
      return rel === cleanRoot;
    });
  }

  function isWithinPotentialRoot(rel) {
    return rootAllows(rel) || resolvedConfig.approvedRoots.some((root) => normaliseRelativePath(root).startsWith(`${rel}/`));
  }

  function matchPattern(pattern, rel) {
    const normPattern = normaliseRelativePath(pattern);
    if (normPattern.endsWith('/**')) {
      const prefix = normPattern.slice(0, -3);
      return rel === prefix || rel.startsWith(`${prefix}/`);
    }
    return rel === normPattern;
  }

  function getTier(rel) {
    for (const rule of resolvedConfig.tierRules) {
      if (matchPattern(rule.pattern, rel)) return rule.tier;
    }
    return 3;
  }

  function isEditable(tier) {
    return tier < 3;
  }

  function isRenderable(filePath) {
    return /\.(md|markdown|txt|json|html|htm)$/i.test(filePath) || !path.extname(filePath);
  }

  function isMarkdownFile(filePath) {
    return /\.(md|markdown)$/i.test(filePath);
  }

  function isSearchableTextFile(rel) {
    const lowerName = path.basename(rel).toLowerCase();
    const binaryMarkers = ['.so', '.node', '.dll', '.dylib', '.exe', '.bin', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf', '.zip', '.tar', '.gz'];
    if (binaryMarkers.some((marker) => lowerName === marker.slice(1) || lowerName.endsWith(marker) || lowerName.includes(`${marker}.`))) return false;
    return /\.(md|markdown|txt|json|csv|yaml|yml|html|htm)$/i.test(lowerName) || !path.extname(lowerName);
  }

  function getDefaultSearchRoots() {
    return [...DEFAULT_SEARCH_ROOTS];
  }

  function rootSelectionAllows(rel, roots) {
    return roots.some((root) => {
      const cleanRoot = normaliseRelativePath(root);
      if (cleanRoot === '.') return true;
      const prefix = cleanRoot.replace(/\/$/, '');
      return rel === prefix || rel.startsWith(`${prefix}/`);
    });
  }

  function isWithinPotentialSelectedRoot(rel, roots) {
    return rootSelectionAllows(rel, roots) || roots.some((root) => normaliseRelativePath(root).startsWith(`${rel}/`));
  }

  function isExtensionQuery(lowerQuery) {
    return /^\.[a-z0-9]{2,6}$/i.test(lowerQuery);
  }

  function scoreSearchEntry(entry, lowerQuery) {
    const extensionQuery = isExtensionQuery(lowerQuery);
    if (entry.nameLower === lowerQuery) return 2;
    if (entry.pathLower.endsWith(`/${lowerQuery}`) || entry.pathLower === lowerQuery) return 1.6;
    if (entry.nameLower.includes(lowerQuery)) return 1.2;
    if (entry.pathLower.includes(lowerQuery)) return 1;
    if (!extensionQuery && entry.contentLower.includes(lowerQuery)) return 0.6;
    return 0;
  }

  function snippetForQuery(content, lowerQuery) {
    if (isExtensionQuery(lowerQuery)) return { line: null, snippet: '' };
    const lines = content.split(/\r?\n/);
    const idx = lines.findIndex((item) => item.toLowerCase().includes(lowerQuery));
    if (idx < 0) return { line: null, snippet: '' };
    return { line: idx + 1, snippet: lines[idx].trim().slice(0, 240) };
  }

  function countTableColumns(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').length;
  }

  function validateMarkdownForRender(content) {
    const lines = String(content).split(/\r?\n/);
    const issues = [];
    let activeTable = null;

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trim();
      const nextLine = lines[index + 1] || '';

      if (!activeTable && /^\|.+\|$/.test(trimmed) && /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(nextLine.trim())) {
        activeTable = { headerLine: index + 1, columns: countTableColumns(trimmed) };
        index += 1;
        continue;
      }

      if (activeTable) {
        if (!trimmed) {
          activeTable = null;
          continue;
        }
        if (/^\|.+\|$/.test(trimmed)) {
          const columns = countTableColumns(trimmed);
          if (columns !== activeTable.columns) {
            issues.push({ line: index + 1, code: 'MARKDOWN_TABLE_COLUMN_MISMATCH', message: `Markdown table row has ${columns} columns but header has ${activeTable.columns}. This often means an unescaped | or malformed table row.` });
          }
          continue;
        }
        activeTable = null;
      }
    }

    return { ok: issues.length === 0, issues };
  }

  function assertRenderableMarkdown(rel, content) {
    if (!isMarkdownFile(rel)) return;
    const validation = validateMarkdownForRender(content);
    if (!validation.ok) {
      const err = new Error(validation.issues[0].message);
      err.code = 'MARKDOWN_RENDER_VALIDATION_FAILED';
      err.status = 400;
      err.issues = validation.issues;
      throw err;
    }
  }

  async function collectSearchEntriesForRoot(rel, roots, bucket) {
    if (!rootAllows(rel)) return;
    const { abs } = resolveWorkspacePath(rel);
    const stats = await fsp.stat(abs).catch(() => null);
    if (!stats) return;
    if (stats.isDirectory()) {
      const dirEntries = await fsp.readdir(abs, { withFileTypes: true });
      for (const entry of dirEntries) {
        if (entry.name.startsWith('.')) continue;
        const childRel = rel === '.' ? entry.name : `${rel}/${entry.name}`;
        const explicitlySelectedSkippedRoot = roots.some((root) => root === childRel || root.startsWith(`${childRel}/`));
        if (entry.isDirectory() && SEARCH_SKIP_DIR_NAMES.has(entry.name) && !explicitlySelectedSkippedRoot) continue;
        if (!isWithinPotentialSelectedRoot(childRel, roots)) continue;
        await collectSearchEntriesForRoot(childRel, roots, bucket);
      }
      return;
    }
    if (!isSearchableTextFile(rel)) return;
    const text = await fsp.readFile(abs, 'utf8').catch(() => null);
    if (text == null) return;
    const tier = getTier(rel);
    bucket.push({ path: rel, pathLower: rel.toLowerCase(), name: path.basename(rel), nameLower: path.basename(rel).toLowerCase(), tier, content: text, contentLower: text.toLowerCase() });
  }

  async function rebuildSearchIndex(reason = 'manual') {
    if (searchIndexState.buildPromise) return searchIndexState.buildPromise;
    searchIndexState.buildPromise = (async () => {
      const roots = getDefaultSearchRoots();
      const entries = [];
      for (const root of roots) await collectSearchEntriesForRoot(root, roots, entries);
      searchIndexState.entries = entries;
      searchIndexState.builtAt = new Date().toISOString();
      searchIndexState.lastError = null;
      logger.info('search_index_rebuilt', { reason, entry_count: entries.length });
      return { reason, count: entries.length, builtAt: searchIndexState.builtAt };
    })().catch((error) => {
      searchIndexState.lastError = error.message || String(error);
      logger.error('search_index_rebuild_failed', { reason, error: error.message || String(error) });
      throw error;
    }).finally(() => {
      searchIndexState.buildPromise = null;
    });
    return searchIndexState.buildPromise;
  }

  async function ensureSearchIndexReady() {
    if (!searchIndexState.builtAt && !searchIndexState.buildPromise) await rebuildSearchIndex('startup');
    else if (searchIndexState.buildPromise) await searchIndexState.buildPromise;
  }

  function filterIndexedEntriesByRoots(roots) {
    return searchIndexState.entries.filter((entry) => rootSelectionAllows(entry.path, roots));
  }

  async function ensureParent(filePath) {
    await fsp.mkdir(path.dirname(filePath), { recursive: true });
  }

  async function sha256File(filePath) {
    const data = await fsp.readFile(filePath);
    return `sha256:${crypto.createHash('sha256').update(data).digest('hex')}`;
  }

  async function fileMeta(rel) {
    const { abs } = resolveWorkspacePath(rel);
    const stats = await fsp.stat(abs);
    const tier = getTier(rel);
    return {
      path: rel,
      name: path.basename(abs),
      isDir: stats.isDirectory(),
      tier,
      tierLabel: tierLabels[tier] || 'protected',
      editable: !stats.isDirectory() && isEditable(tier),
      renderable: !stats.isDirectory() && isRenderable(rel),
      archivable: !stats.isDirectory() && tier < 3,
      mtime: stats.mtime.toISOString(),
      size: stats.size,
      etag: stats.isDirectory() ? null : await sha256File(abs)
    };
  }

  async function appendAudit(entry) {
    await ensureParent(auditLogPath);
    await fsp.appendFile(auditLogPath, `${JSON.stringify({ time: new Date().toISOString(), ...entry })}\n`);
  }

  function requireAuth(req) {
    if (!authToken) {
      const err = new Error('Gateway token not configured');
      err.status = 500;
      err.code = 'AUTH_NOT_CONFIGURED';
      throw err;
    }
    const header = req.headers.authorization || '';
    const expected = `Bearer ${authToken}`;
    if (header !== expected) {
      const err = new Error('Authentication failed');
      err.status = 401;
      err.code = 'AUTH_FAILED';
      throw err;
    }
  }

  async function parseBody(req) {
    return new Promise((resolve, reject) => {
      let body = '';
      req.on('data', (chunk) => {
        body += chunk;
        if (body.length > 5 * 1024 * 1024) {
          reject(new Error('Body too large'));
          req.destroy();
        }
      });
      req.on('end', () => {
        if (!body) return resolve({});
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          error.code = 'INVALID_JSON';
          reject(error);
        }
      });
      req.on('error', reject);
    });
  }
  const devProjectsController = createDevProjectsController({
    config: resolvedConfig,
    projectRoot: path.resolve(__dirname, '..', '..'),
    sendJson,
    success,
    failure,
    parseBody
  });

  const aiBriefingsController = createAiBriefingsController({
    config: resolvedConfig,
    sendJson,
    success,
    failure,
    parseBody
  });

  const taskSystemController = createTaskSystemController({
    brokerAdapterOptions: resolvedConfig.taskContextBroker || {},
    // Local default is the bounded package-only writer; tests/integration may inject a mock.
    emailDraftExecutor: options.emailDraftExecutor || emailDraft.createDraft,
    compositionProvider: options.compositionProvider || createProductionCompositionProvider(),
    contextDiscovery: async ({ briefText, entity, workType, exact_terms: exactTerms }) => {
      const stopWords = new Set(['draft', 'write', 'prepare', 'phase', 'work', 'task', 'email', 'client', 'follow', 'up', 'the', 'and', 'for', 'with']);
      const validatedExactTerms = Array.isArray(exactTerms) && exactTerms.length >= 2 && exactTerms.length <= 6 && exactTerms.every((term) => typeof term === 'string' && /^[a-z0-9][a-z0-9_-]{2,63}$/.test(term)) ? [...new Set(exactTerms)] : null;
      const exactCommercialReply = workType === 'email_reply_draft' && validatedExactTerms?.length === exactTerms.length;
      const terms = exactCommercialReply ? validatedExactTerms : [...new Set(`${entity || ''} ${briefText || ''} ${workType || ''}`
        .toLowerCase().replace(/[^a-z0-9@._ -]/g, ' ').split(/\s+/)
        .filter((term) => term.length >= 4 && !stopWords.has(term)))].slice(0, 8);
      const roots = exactCommercialReply ? ['sharepoint-cache'] : (resolvedConfig.contextDiscoveryRoots || [
        'stackstone', 'reference', 'projects', 'sharepoint-cache',
        'MICROSOFT_INBOX.md', 'GMAIL_INBOX.md', 'WHATSAPP_RECENT.md', 'TEAMS_RECENT.md'
      ]);
      const hits = [];
      for (const term of terms) {
        const results = await searchReferences(term, roots, 8);
        for (const result of results) {
          if (!hits.some((hit) => hit.path === result.path)) hits.push({ ...result, matched_term: term });
          if (hits.length >= 24) break;
        }
        if (hits.length >= 24) break;
      }
      return { status: 'complete', query_terms: terms, roots, results: hits, result_count: hits.length, bounded: true };
    }
  });

  const linkedinMirrorController = createLinkedinMirrorController({
    workspaceRoot,
    logger,
    sendJson,
    success,
    failure,
    parseBody
  });

  const expenseReviewController = createExpenseReviewController({
    snapshotPath: resolvedConfig.expenseReview?.snapshotPath,
    financeRoot: resolvedConfig.expenseReview?.financeRoot,
    databasePath: resolvedConfig.expenseReview?.databasePath,
    logger,
    sendJson,
    success,
    failure,
    parseBody
  });

  async function listEntries(rel, depth = 1) {
    if (!rootAllows(rel)) {
      const err = new Error('Path is outside approved roots');
      err.code = 'PATH_DENIED';
      throw err;
    }
    const { abs } = resolveWorkspacePath(rel);
    const stats = await fsp.stat(abs);
    if (!stats.isDirectory()) return [await fileMeta(rel)];

    async function walk(currentRel, currentAbs, remainingDepth) {
      const dirEntries = await fsp.readdir(currentAbs, { withFileTypes: true });
      const results = [];
      for (const entry of dirEntries) {
        if (entry.name.startsWith('.')) continue;
        const childRel = currentRel === '.' ? entry.name : `${currentRel}/${entry.name}`;
        if (!isWithinPotentialRoot(childRel)) continue;
        results.push(await fileMeta(childRel));
        if (entry.isDirectory() && remainingDepth > 1) results.push(...await walk(childRel, path.join(currentAbs, entry.name), remainingDepth - 1));
      }
      return results.sort((a, b) => a.path.localeCompare(b.path));
    }
    return walk(rel, abs, depth);
  }

  async function createSnapshot(rel, abs, summary) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const safeRel = rel.replace(/[\/]/g, '__');
    const snapshotId = `${timestamp}__${safeRel}`;
    const snapshotFile = path.join(snapshotRoot, snapshotId);
    await ensureParent(snapshotFile);
    await fsp.copyFile(abs, snapshotFile);
    await appendAudit({ action: 'snapshot', path: rel, snapshotId, summary });
    return snapshotId;
  }

  async function searchReferences(query, roots, limit) {
    const lowerQuery = String(query || '').toLowerCase();
    if (!lowerQuery) return [];
    await ensureSearchIndexReady();
    const indexedEntries = filterIndexedEntriesByRoots(roots);
    const discoveredEntries = [...indexedEntries];
    for (const root of roots) {
      if (discoveredEntries.some((entry) => entry.path === root || entry.path.startsWith(`${root}/`))) continue;
      await collectSearchEntriesForRoot(root, roots, discoveredEntries);
    }
    const results = [];
    for (const entry of discoveredEntries) {
      if (!entry.contentLower.includes(lowerQuery) && !entry.pathLower.includes(lowerQuery)) continue;
      const lines = entry.content.split(/\r?\n/);
      const matches = [];
      for (let i = 0; i < lines.length; i += 1) {
        if (lines[i].toLowerCase().includes(lowerQuery)) {
          matches.push({ line: i + 1, snippet: lines[i].trim().slice(0, 240) });
          if (matches.length >= 3) break;
        }
      }
      if (!matches.length) continue;
      results.push({ path: entry.path, name: entry.name, matchCount: matches.length, matches });
      if (results.length >= limit) break;
    }
    return results;
  }

  async function handleSearch(body) {
    const query = String(body.query || '').trim();
    const roots = Array.isArray(body.roots) && body.roots.length ? body.roots.map(normaliseRelativePath) : getDefaultSearchRoots();
    const limit = Number(body.limit || 20);
    if (!query) {
      const err = new Error('Query is required');
      err.code = 'INVALID_QUERY';
      throw err;
    }
    await ensureSearchIndexReady();
    const lowerQuery = query.toLowerCase();
    const extensionQuery = isExtensionQuery(lowerQuery);
    return filterIndexedEntriesByRoots(roots)
      .map((entry) => {
        if (extensionQuery && !entry.pathLower.includes(lowerQuery) && !entry.nameLower.includes(lowerQuery)) return null;
        const score = scoreSearchEntry(entry, lowerQuery);
        if (!score) return null;
        const { line, snippet } = snippetForQuery(entry.content, lowerQuery);
        return { path: entry.path, name: entry.name, tier: entry.tier, score, snippet, line };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score || a.path.localeCompare(b.path))
      .slice(0, limit);
  }

  function queryOptionsFromUrl(url) {
    return { sort: url.searchParams.get('sort') || undefined, direction: url.searchParams.get('direction') || undefined, limit: url.searchParams.get('limit') || undefined };
  }

  function execFileLimited(command, args, options = {}) {
    return new Promise((resolve) => {
      const child = execFile(command, args, {
        timeout: options.timeoutMs || 10000,
        maxBuffer: options.maxBuffer || 256 * 1024,
        env: { ...process.env, HOME: process.env.HOME || '/home/tomdean88' },
      }, (error, stdout, stderr) => {
        resolve({
          ok: !error,
          code: error?.code ?? 0,
          signal: error?.signal || null,
          stdout: String(stdout || '').slice(0, 12000),
          stderr: String(stderr || '').slice(0, 12000),
          error: error ? error.message : null,
        });
      });
      child.stdin?.end();
    });
  }

  async function openclawGatewayStatus() {
    const isActive = await execFileLimited('/usr/bin/systemctl', ['--user', 'is-active', 'openclaw-gateway.service'], { timeoutMs: 5000 });
    const show = await execFileLimited('/usr/bin/systemctl', ['--user', 'show', 'openclaw-gateway.service', '--property=ActiveState,SubState,MainPID,ExecMainStatus,ExecMainCode,NRestarts'], { timeoutMs: 5000 });
    return {
      unit: 'openclaw-gateway.service',
      active: isActive.ok && isActive.stdout.trim() === 'active',
      is_active_output: isActive.stdout.trim() || isActive.stderr.trim(),
      systemd: show.stdout.trim(),
      checked_at: new Date().toISOString(),
    };
  }

  async function handleAdminRoute(req, res, pathname) {
    if (pathname === '/admin/openclaw-gateway/status' && req.method === 'GET') {
      return sendJson(res, 200, success(await openclawGatewayStatus()));
    }
    if (pathname === '/admin/openclaw-gateway/restart' && req.method === 'POST') {
      const body = await parseBody(req);
      if (body.confirm !== 'restart-openclaw-gateway') {
        return sendJson(res, 400, failure('CONFIRMATION_REQUIRED', 'confirm must equal restart-openclaw-gateway'));
      }
      const before = await openclawGatewayStatus();
      const restarted = await execFileLimited('/usr/bin/systemctl', ['--user', 'restart', 'openclaw-gateway.service'], { timeoutMs: 20000 });
      const after = await openclawGatewayStatus();
      await appendAudit({ action: 'admin_restart_openclaw_gateway', before, after, command_ok: restarted.ok });
      return sendJson(res, restarted.ok ? 200 : 500, {
        ok: restarted.ok,
        data: { before, restart: restarted, after },
        ...(restarted.ok ? {} : { error: { code: 'RESTART_FAILED', message: restarted.error || restarted.stderr || 'restart failed' } }),
      });
    }
    return false;
  }

  async function route(req, res) {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
    const pathname = url.pathname;

    if (pathname === '/health' && req.method === 'GET') {
      return sendJson(res, 200, success({ service: 'workspace-pi-gateway', status: 'ok', time: new Date().toISOString() }));
    }

    requireAuth(req);

    const adminHandled = await handleAdminRoute(req, res, pathname);
    if (adminHandled !== false) return adminHandled;

    if (pathname === '/dev/projects' || pathname.startsWith('/dev/projects/')) return devProjectsController.handle(req, res, pathname);
    if (pathname === '/ai-briefings' || pathname.startsWith('/ai-briefings/')) return aiBriefingsController.handle(req, res, pathname);
    if (pathname === '/linkedin-mirror' || pathname.startsWith('/linkedin-mirror/')) return linkedinMirrorController.handle(req, res, pathname);
    const expenseReviewHandled = await expenseReviewController.handle(req, res, pathname);
    if (expenseReviewHandled !== false) return expenseReviewHandled;
    const taskSystemHandled = await taskSystemController(req, res, pathname);
    if (taskSystemHandled !== false) return taskSystemHandled;
    if (pathname === '/roots' && req.method === 'GET') return sendJson(res, 200, success({ roots: resolvedConfig.browseRoots }));
    if (pathname === '/files' && req.method === 'GET') {
      const rel = normaliseRelativePath(url.searchParams.get('path') || '.');
      const depth = Math.max(1, Math.min(5, Number(url.searchParams.get('depth') || 1)));
      return sendJson(res, 200, success({ path: rel, entries: await listEntries(rel, depth) }));
    }
    if (pathname === '/file/meta' && req.method === 'GET') {
      const rel = normaliseRelativePath(url.searchParams.get('path'));
      if (!rootAllows(rel)) return sendJson(res, 403, failure('PATH_DENIED', 'Path is outside approved roots'));
      return sendJson(res, 200, success({ file: await fileMeta(rel) }));
    }
    if (pathname === '/file/raw' && req.method === 'GET') {
      const rel = normaliseRelativePath(url.searchParams.get('path'));
      if (!rootAllows(rel)) return sendJson(res, 403, failure('PATH_DENIED', 'Path is outside approved roots'));
      const { abs } = resolveWorkspacePath(rel);
      return sendJson(res, 200, success({ file: await fileMeta(rel), content: await fsp.readFile(abs, 'utf8') }));
    }
    if (pathname === '/file/rendered' && req.method === 'GET') {
      const rel = normaliseRelativePath(url.searchParams.get('path'));
      if (!rootAllows(rel)) return sendJson(res, 403, failure('PATH_DENIED', 'Path is outside approved roots'));
      const { abs } = resolveWorkspacePath(rel);
      const content = await fsp.readFile(abs, 'utf8');
      const html = /\.(html|htm)$/i.test(rel) ? content : renderMarkdownLite(content);
      return sendJson(res, 200, success({ file: await fileMeta(rel), html }));
    }
    if (pathname === '/search' && req.method === 'POST') {
      const body = await parseBody(req);
      return sendJson(res, 200, success({ query: body.query, results: await handleSearch(body) }));
    }
    if (pathname === '/references' && req.method === 'POST') {
      const body = await parseBody(req);
      const query = String(body.query || '').trim();
      if (!query) return sendJson(res, 400, failure('INVALID_QUERY', 'Query is required'));
      const roots = Array.isArray(body.roots) && body.roots.length ? body.roots.map(normaliseRelativePath) : ['projects', 'reference', 'stackstone/reference', 'stackstone/crm.md', 'stackstone/partnerships.md'];
      const limit = Number(body.limit || 20);
      return sendJson(res, 200, success({ query, results: await searchReferences(query, roots, limit) }));
    }
    if (pathname === '/file/create' && req.method === 'POST') {
      const body = await parseBody(req);
      const rel = normaliseRelativePath(body.path);
      if (!rootAllows(rel)) return sendJson(res, 403, failure('PATH_DENIED', 'Path is outside approved roots'));
      const tier = getTier(rel);
      if (!isEditable(tier)) return sendJson(res, 403, failure('WRITE_DENIED', 'Destination is protected'));
      const { abs } = resolveWorkspacePath(rel);
      if (fs.existsSync(abs)) return sendJson(res, 409, failure('FILE_EXISTS', 'File already exists'));
      const contentToWrite = String(body.content || '');
      assertRenderableMarkdown(rel, contentToWrite);
      await ensureParent(abs);
      await fsp.writeFile(abs, contentToWrite, 'utf8');
      await appendAudit({ action: 'create', path: rel, summary: body.summary || '' });
      await rebuildSearchIndex('create');
      const meta = await fileMeta(rel);
      return sendJson(res, 201, success({ path: rel, etag: meta.etag, mtime: meta.mtime }));
    }
    if (pathname === '/file/update' && req.method === 'POST') {
      const body = await parseBody(req);
      const rel = normaliseRelativePath(body.path);
      if (!rootAllows(rel)) return sendJson(res, 403, failure('PATH_DENIED', 'Path is outside approved roots'));
      const tier = getTier(rel);
      if (!isEditable(tier)) return sendJson(res, 403, failure('WRITE_DENIED', 'File is protected'));
      const { abs } = resolveWorkspacePath(rel);
      if (!fs.existsSync(abs)) return sendJson(res, 404, failure('FILE_NOT_FOUND', 'File not found'));
      const currentEtag = await sha256File(abs);
      if (body.baseEtag && currentEtag !== body.baseEtag) return sendJson(res, 409, failure('ETAG_CONFLICT', 'File changed since it was loaded', { currentEtag }));
      const newContent = String(body.newContent || '');
      assertRenderableMarkdown(rel, newContent);
      const snapshotId = await createSnapshot(rel, abs, body.summary || '');
      await fsp.writeFile(abs, newContent, 'utf8');
      await rebuildSearchIndex('update');
      const meta = await fileMeta(rel);
      await appendAudit({ action: 'update', path: rel, snapshotId, summary: body.summary || '' });
      return sendJson(res, 200, success({ path: rel, etag: meta.etag, mtime: meta.mtime, snapshotId }));
    }
    if (pathname === '/file/move' && req.method === 'POST') {
      const body = await parseBody(req);
      const fromPath = normaliseRelativePath(body.fromPath);
      const toPath = normaliseRelativePath(body.toPath);
      if (!rootAllows(fromPath) || !rootAllows(toPath)) return sendJson(res, 403, failure('PATH_DENIED', 'Source or destination is outside approved roots'));
      const sourceTier = getTier(fromPath);
      const destinationTier = getTier(toPath);
      if (!isEditable(sourceTier) || !isEditable(destinationTier)) return sendJson(res, 403, failure('WRITE_DENIED', 'Source or destination is protected'));
      const { abs: fromAbs } = resolveWorkspacePath(fromPath);
      const { abs: toAbs } = resolveWorkspacePath(toPath);
      if (!fs.existsSync(fromAbs)) return sendJson(res, 404, failure('FILE_NOT_FOUND', 'Source file not found'));
      if (fs.existsSync(toAbs)) return sendJson(res, 409, failure('FILE_EXISTS', 'Destination already exists'));
      const currentEtag = await sha256File(fromAbs);
      if (body.baseEtag && currentEtag !== body.baseEtag) return sendJson(res, 409, failure('ETAG_CONFLICT', 'File changed since it was loaded', { currentEtag }));
      const snapshotId = await createSnapshot(fromPath, fromAbs, body.summary || '');
      const referenceQueries = [fromPath, path.basename(fromPath)].filter(Boolean);
      const referenceRoots = ['projects', 'reference', 'stackstone/reference'];
      const referenceHits = [];
      for (const query of referenceQueries) {
        const hits = await searchReferences(query, referenceRoots, 25);
        for (const hit of hits) {
          if (hit.path === fromPath) continue;
          if (!referenceHits.some((existing) => existing.path === hit.path)) referenceHits.push(hit);
        }
      }
      await ensureParent(toAbs);
      await fsp.rename(fromAbs, toAbs);
      await rebuildSearchIndex('move');
      const destinationMeta = await fileMeta(toPath);
      await appendAudit({ action: 'move', path: fromPath, toPath, snapshotId, summary: body.summary || '', referenceHitCount: referenceHits.length });
      return sendJson(res, 200, success({ fromPath, toPath, etag: destinationMeta.etag, mtime: destinationMeta.mtime, snapshotId, warnings: { referencesMayNeedReview: referenceHits.length > 0, referenceHitCount: referenceHits.length }, referenceHits }));
    }
    if (pathname === '/file/archive' && req.method === 'POST') {
      const body = await parseBody(req);
      const rel = normaliseRelativePath(body.path);
      if (!rootAllows(rel)) return sendJson(res, 403, failure('PATH_DENIED', 'Path is outside approved roots'));
      const tier = getTier(rel);
      if (!isEditable(tier)) return sendJson(res, 403, failure('WRITE_DENIED', 'File is protected'));
      const { abs } = resolveWorkspacePath(rel);
      if (!fs.existsSync(abs)) return sendJson(res, 404, failure('FILE_NOT_FOUND', 'File not found'));
      const archivedTo = path.join(archiveRoot, rel);
      await ensureParent(archivedTo);
      await fsp.rename(abs, archivedTo);
      await appendAudit({ action: 'archive', path: rel, archivedTo, reason: body.reason || '' });
      await rebuildSearchIndex('archive');
      return sendJson(res, 200, success({ path: rel, archivedTo }));
    }
    if (pathname === '/history' && req.method === 'GET') {
      const rel = normaliseRelativePath(url.searchParams.get('path'));
      const history = [];
      try {
        const auditRaw = await fsp.readFile(auditLogPath, 'utf8');
        for (const line of auditRaw.split(/\r?\n/)) {
          if (!line.trim()) continue;
          const item = JSON.parse(line);
          if ((item.path === rel || item.toPath === rel) && item.snapshotId) history.push({ snapshotId: item.snapshotId, createdAt: item.time, summary: item.summary || '', actor: 'gateway', action: item.action || 'snapshot' });
        }
      } catch (_) {}
      return sendJson(res, 200, success({ path: rel, history: history.reverse() }));
    }
    if (pathname === '/file/restore' && req.method === 'POST') {
      const body = await parseBody(req);
      const rel = normaliseRelativePath(body.path);
      if (!rootAllows(rel)) return sendJson(res, 403, failure('PATH_DENIED', 'Path is outside approved roots'));
      const tier = getTier(rel);
      if (!isEditable(tier)) return sendJson(res, 403, failure('WRITE_DENIED', 'File is protected'));
      const snapshotId = String(body.snapshotId || '');
      const snapshotFile = path.join(snapshotRoot, snapshotId);
      if (!fs.existsSync(snapshotFile)) return sendJson(res, 404, failure('SNAPSHOT_NOT_FOUND', 'Snapshot not found'));
      const { abs } = resolveWorkspacePath(rel);
      await ensureParent(abs);
      if (fs.existsSync(abs)) await createSnapshot(rel, abs, body.summary || 'pre-restore snapshot');
      await fsp.copyFile(snapshotFile, abs);
      await rebuildSearchIndex('restore');
      const meta = await fileMeta(rel);
      await appendAudit({ action: 'restore', path: rel, snapshotId, summary: body.summary || '' });
      return sendJson(res, 200, success({ path: rel, etag: meta.etag, mtime: meta.mtime }));
    }

    return sendJson(res, 404, failure('NOT_FOUND', 'Route not found'));
  }

  const server = http.createServer(async (req, res) => {
    const startedAt = Date.now();
    const requestId = crypto.randomUUID();
    try {
      await route(req, res);
      logger.info('http_request_completed', {
        request_id: requestId,
        method: req.method,
        path: req.url,
        status_code: res.statusCode,
        duration_ms: Date.now() - startedAt,
        outcome: 'ok'
      });
    } catch (error) {
      const status = error.status || (error.code === 'PATH_DENIED' ? 403 : error.code === 'INVALID_QUERY' || error.code === 'VALIDATION_ERROR' ? 400 : 500);
      logger.error('http_request_failed', {
        request_id: requestId,
        method: req.method,
        path: req.url,
        status_code: status,
        duration_ms: Date.now() - startedAt,
        error_code: error.code || 'INTERNAL_ERROR',
        error_message: error.message || 'Internal error'
      });
      sendJson(res, status, failure(error.code || 'INTERNAL_ERROR', error.message || 'Internal error', error.issues ? { issues: error.issues } : {}));
    }
  });

  const interval = setInterval(() => {
    rebuildSearchIndex('interval').catch(() => {});
  }, SEARCH_INDEX_REFRESH_MS);

  interval.unref?.();

  async function bootstrap() {}

  async function start(port = resolvedConfig.port) {
    await bootstrap();
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen(port, () => {
        server.off('error', reject);
        resolve();
      });
    });
    logger.info('gateway_started', { port: server.address().port });
    rebuildSearchIndex('startup').catch(() => {});
    return server.address();
  }

  async function close() {
    clearInterval(interval);
    await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
  }

  return {
    server,
    start,
    close,
    bootstrap,
    logger,
    helpers: {
      sendJson,
      success,
      failure,
      parseBody,
      normaliseRelativePath,
      resolveWorkspacePath
    }
  };
}

if (require.main === module) {
  const gateway = createGatewayServer();
  gateway.start().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

module.exports = {
  createGatewayServer
};
