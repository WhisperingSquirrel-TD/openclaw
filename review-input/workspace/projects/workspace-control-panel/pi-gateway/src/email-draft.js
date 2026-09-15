'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const GRAPH_BASE = 'https://graph.microsoft.com/v1.0';
const TOKEN_ROOT = path.join(process.env.HOME || '/home/tomdean88', '.openclaw', 'integrations');
const SIGNATURE_PATH = '/home/tomdean88/.openclaw/integrations/microsoft-l1/signature-adaptive.html';
const SOURCE_REF_RE = /^(microsoft_inbox|microsoft_external):email:[^:]+:([A-Za-z0-9+/=_-]{20,512})$/;

function sha256(value) { return crypto.createHash('sha256').update(String(value || '')).digest('hex'); }
function escapeHtml(value) { return String(value || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
// Output verification is deliberately literal rather than trusting Graph's
// create/patch acknowledgement.  A draft is reviewable only if a fresh
// readback contains the authored body (not merely a signature or quote).
function decodeHtml(value) {
  return String(value || '').replace(/<br\s*\/?>/gi, '\n').replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>').replace(/&quot;/gi, '"').replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ').trim();
}
function verifyDraftBodyReadback(verifiedDraft, authoredBody) {
  const expected = String(authoredBody || '').replace(/\s+/g, ' ').trim();
  const actual = decodeHtml(verifiedDraft?.body?.content || '');
  if (expected.length < 12) throw Object.assign(new Error('Draft verification failed: authored body is below the minimum reviewable length'), { code: 'DRAFT_BODY_TOO_SHORT' });
  if (actual.length < expected.length || !actual.includes(expected)) throw Object.assign(new Error('Draft verification failed: readback body is empty, truncated, or does not contain the authored text'), { code: 'DRAFT_BODY_READBACK_MISMATCH' });
  return { body_hash: `sha256:${sha256(expected)}`, body_length: expected.length, readback_body_length: actual.length };
}
// The governed signature is the sole identity block. This final writer boundary
// is deliberately deterministic so an upstream composer cannot create a double
// name by supplying its own conventional sign-off.
function stripRedundantAuthoredName(body) {
  return String(body || '').replace(/(\n(?:best|kind regards|regards|thanks|cheers|many thanks)[,:]?)\s*\n\s*tom(?:\s+dean)?\s*$/i, '$1');
}
function htmlBody(body, signature) { return `<div>${escapeHtml(stripRedundantAuthoredName(body)).replace(/\r?\n/g, '<br>')}</div><div><br></div>${signature}`; }
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function writeJsonAtomic(file, value) { const tmp = `${file}.tmp-${process.pid}`; fs.writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 }); fs.renameSync(tmp, file); }
function resolveTokenFile(account = 'microsoft') {
  if (!fs.existsSync(TOKEN_ROOT)) throw new Error('Microsoft integration directory is unavailable');
  const dirs = fs.readdirSync(TOKEN_ROOT, { withFileTypes: true }).filter((entry) => entry.isDirectory() && entry.name.startsWith('microsoft')).map((entry) => path.join(TOKEN_ROOT, entry.name));
  const candidates = [];
  for (const dir of dirs.sort((a, b) => b.length - a.length || a.localeCompare(b))) candidates.push(path.join(dir, `token-${account}.json`));
  for (const dir of dirs) candidates.push(path.join(dir, 'token-microsoft.json'), path.join(dir, 'token.json'));
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error(`Microsoft token for account ${account} is unavailable`);
  return found;
}
async function refreshToken(tokenFile) {
  const token = readJson(tokenFile);
  if (!token.client_id || !token.refresh_token) throw new Error('Microsoft token lacks refresh credentials');
  const form = new URLSearchParams({ client_id: token.client_id, refresh_token: token.refresh_token, grant_type: 'refresh_token', scope: 'Mail.ReadWrite offline_access' });
  if (token.client_secret) form.set('client_secret', token.client_secret);
  const response = await fetch(`https://login.microsoftonline.com/${token.tenant_id || 'common'}/oauth2/v2.0/token`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form });
  const data = await response.json();
  if (!response.ok || !data.access_token) throw new Error(`Microsoft token refresh failed: ${response.status}`);
  writeJsonAtomic(tokenFile, { ...token, access_token: data.access_token, refresh_token: data.refresh_token || token.refresh_token, expires_at: Date.now() + Number(data.expires_in || 3600) * 1000 });
  return data.access_token;
}
async function graph(accessToken, method, endpoint, body) {
  const response = await fetch(`${GRAPH_BASE}${endpoint}`, { method, headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await response.text(); let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = { raw: text }; }
  if (!response.ok) throw new Error(`Microsoft Graph ${method} ${endpoint} failed: ${response.status}`);
  return data;
}
function getExactMessageId(task, subtask, protectedBinding = null) {
  // Provider locators are never accepted from a task, a brief, or an API
  // payload at this writer boundary. The broker creates this non-enumerable
  // capability only after reading the one registered read-only exact thread.
  if (protectedBinding && protectedBinding.schema === 'broker-proven-microsoft-message-locator-v1' && protectedBinding.task_id === task?.id && protectedBinding.subtask_id === subtask?.id && /^[A-Za-z0-9+/=_-]{20,512}$/.test(String(protectedBinding.message_locator || ''))) return protectedBinding.message_locator;
  throw new Error('Draft requires a broker-proven exact Microsoft email binding');
}
function getExistingOutput(db, idempotencyKey) { const row = db.prepare('SELECT * FROM task_outputs WHERE idempotency_key=?').get(idempotencyKey); if (!row) return null; try { return JSON.parse(row.result_json); } catch (_) { return null; } }
function persistOutput(db, task, subtask, idempotencyKey, result, addEvent, workType = 'email_reply_draft') {
  const now = new Date().toISOString(); const outputId = `out_${crypto.randomBytes(8).toString('hex')}`;
  const output = { id: outputId, task_id: task.id, subtask_id: subtask.id, draft_id: result.draft_id, web_link: result.web_link || null, subject: result.subject || null, outcome: 'draft_created_not_sent', draft_route: result.draft_route || 'linked_or_standalone', coverage_status: 'complete', review_required: true, verified: true, verification: result.verification || null };
  db.prepare(`INSERT INTO task_outputs (id, idempotency_key, task_id, subtask_id, work_type, output_type, status, output_json, provenance_json, result_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .run(outputId, idempotencyKey, task.id, subtask.id, workType, 'outlook_draft', 'created', JSON.stringify(output), JSON.stringify({ source: 'task-bound composition package', no_send_endpoint_called: true, body_hash: result.body_hash }), JSON.stringify(output), now, now);
  addEvent(db, subtask.id, 'email_draft_created', { event_type: 'email_draft_created', output_id: outputId, draft_id: result.draft_id, web_link: result.web_link || null, verified: true, no_send_endpoint_called: true, body_hash: result.body_hash, draft_route: result.draft_route || 'linked_or_standalone' });
  return output;
}
function isTomIdentity(value) { return /(?:tom@stackstoneconsulting\.co\.uk|tom dean|tom\s+dean)/i.test(String(value || '')); }
function validAddress(value) { return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(value || '')); }
function normaliseFollowUpSubject(value) {
  const base = String(value || '').replace(/^(?:re:\s*)+/i, '').trim();
  if (!base) throw new Error('Follow-up draft requires a non-empty anchored subject');
  return `RE: ${base}`;
}
function validateCompositionPackage(pkg) {
  if (!pkg || typeof pkg !== 'object' || pkg.schema !== 'email-composition-package-v1') throw new Error('Draft writer requires email-composition-package-v1; arbitrary raw body is not accepted');
  if (!['reply_inbound', 'follow_up_outbound', 'standalone_new_message', 'reply_without_exact_anchor'].includes(pkg.mode)) throw new Error('Composition package mode is invalid');
  if (typeof pkg.draft?.body !== 'string' || !pkg.draft.body.trim()) throw new Error('Composition package requires a non-empty draft body');
  if (!pkg.anchor_proof || !pkg.recipient_proof || pkg.no_send_proof?.send_endpoint_called !== false) throw new Error('Composition package lacks required anchor, recipient, or no-send proof');
  if (!Array.isArray(pkg.unresolved_questions) || pkg.review_state !== 'prepared_for_review') throw new Error('Composition package must remain prepared_for_review with unresolved_questions');
  if (pkg.mode === 'reply_inbound' && pkg.recipient_proof.strategy !== 'createReplyAll_exact_inbound') throw new Error('Inbound reply package must require createReplyAll exact inbound');
  if (pkg.mode === 'follow_up_outbound') {
    if (pkg.recipient_proof.strategy !== 'new_draft_to_original_non_tom_recipient' || !validAddress(pkg.recipient_proof.address) || isTomIdentity(pkg.recipient_proof.address)) throw new Error('Follow-up package requires the verified original non-Tom recipient');
    if (pkg.subject !== normaliseFollowUpSubject(pkg.subject || pkg.draft?.subject)) throw new Error('Follow-up package subject must be a validated RE: subject');
  }
  if (['standalone_new_message', 'reply_without_exact_anchor'].includes(pkg.mode)) {
    const addressed = pkg.recipient_proof.strategy === 'new_draft_to_verified_task_recipient' && validAddress(pkg.recipient_proof.address) && !isTomIdentity(pkg.recipient_proof.address);
    const unaddressed = pkg.recipient_proof.strategy === 'new_draft_unaddressed_recipient_unresolved' && pkg.recipient_proof.address === null;
    if (!addressed && !unaddressed) throw new Error('Standalone or anchorless package requires a verified non-Tom recipient or explicit unaddressed recipient state');
    if (typeof (pkg.subject || pkg.draft?.subject) !== 'string' || !(pkg.subject || pkg.draft?.subject).trim()) throw new Error('Standalone or anchorless package requires a non-empty subject');
  }
  return pkg;
}
async function writerDependencies(deps) {
  const signature = deps.getSignature ? await deps.getSignature() : fs.readFileSync(SIGNATURE_PATH, 'utf8').trim();
  if (!signature) throw new Error('governed Stackstone signature is unavailable');
  const accessToken = deps.getAccessToken ? await deps.getAccessToken() : await refreshToken(resolveTokenFile('microsoft'));
  return { signature, accessToken, callGraph: deps.graph || graph };
}
async function verifyReplyThread(callGraph, accessToken, exactMessageId, verifiedDraft) {
  // Folder/isDraft proof is insufficient: a standalone message can also be a
  // valid Drafts item. A reply must remain in the original Graph conversation.
  const original = await callGraph(accessToken, 'GET', `/me/messages/${encodeURIComponent(exactMessageId)}?$select=id,conversationId`);
  if (!original?.conversationId || !verifiedDraft?.conversationId || original.conversationId !== verifiedDraft.conversationId) {
    throw new Error('Draft verification failed: Graph did not prove that the reply remains in the original conversation');
  }
}
async function createCompositionDraft(db, payload, deps = {}) {
  const taskId = String(payload.task_id || ''); const subtaskId = String(payload.subtask_id || '');
  const pkg = validateCompositionPackage(payload.composition_package);
  const task = deps.getEntity(db, 'task', taskId); const subtask = deps.getEntity(db, 'subtask', subtaskId);
  if (!task || !subtask || subtask.parent_id !== task.id) throw new Error('task/subtask binding is invalid');
  if (subtask.owner !== 'L1' || !['do_now', 'prepare_for_review'].includes(subtask.execution_mode)) throw new Error('subtask is not L1-authorised for draft preparation');
  const protectedBinding = Object.prototype.propertyIsEnumerable.call(payload || {}, 'protected_reply_binding') ? null : payload?.protected_reply_binding;
  const exactMessageId = pkg.mode === 'reply_inbound' ? getExactMessageId(task, subtask, protectedBinding) : null;
  const bodyHash = `sha256:${sha256(pkg.draft.body)}`;
  const idempotencyKey = `email-draft:${task.id}:${subtask.id}:${sha256(JSON.stringify({ mode: pkg.mode, anchor: pkg.anchor_proof, recipient: pkg.recipient_proof, subject: pkg.subject || pkg.draft.subject, body: pkg.draft.body }))}`;
  const existing = getExistingOutput(db, idempotencyKey); if (existing) return { ok: true, reused: true, ...existing };
  const { signature, accessToken, callGraph } = await writerDependencies(deps);
  let created; let draftId; let subject;
  if (pkg.mode === 'reply_inbound') {
    created = await callGraph(accessToken, 'POST', `/me/messages/${encodeURIComponent(exactMessageId)}/createReplyAll`);
    draftId = created?.id; if (!draftId) throw new Error('Microsoft Graph did not return a reply draft ID');
    const quoted = created?.body?.content || (await callGraph(accessToken, 'GET', `/me/messages/${encodeURIComponent(draftId)}?$select=body`))?.body?.content;
    if (!quoted) throw new Error('Graph reply draft did not include quoted thread content; refusing to overwrite it');
    const patched = await callGraph(accessToken, 'PATCH', `/me/messages/${encodeURIComponent(draftId)}`, { body: { contentType: 'HTML', content: `${htmlBody(pkg.draft.body, signature)}<div><br></div>${quoted}` } });
    subject = patched?.subject || created?.subject || pkg.draft.subject || null;
  } else {
    subject = pkg.mode === 'follow_up_outbound' ? normaliseFollowUpSubject(pkg.subject || pkg.draft.subject) : String(pkg.subject || pkg.draft.subject).trim();
    const message = { subject, body: { contentType: 'HTML', content: htmlBody(pkg.draft.body, signature) } };
    if (pkg.recipient_proof.strategy !== 'new_draft_unaddressed_recipient_unresolved') message.toRecipients = [{ emailAddress: { address: pkg.recipient_proof.address } }];
    created = await callGraph(accessToken, 'POST', '/me/messages', message);
    draftId = created?.id; if (!draftId) throw new Error(`Microsoft Graph did not return a ${['standalone_new_message', 'reply_without_exact_anchor'].includes(pkg.mode) ? 'standalone' : 'follow-up'} draft ID`);
  }
  const draftsFolder = await callGraph(accessToken, 'GET', '/me/mailFolders/drafts?$select=id');
  const verifiedDraft = await callGraph(accessToken, 'GET', `/me/messages/${encodeURIComponent(draftId)}?$select=id,isDraft,parentFolderId,subject,webLink,toRecipients,conversationId,body,lastModifiedDateTime`);
  const recipientMatches = pkg.mode === 'reply_inbound' || (pkg.recipient_proof.strategy === 'new_draft_unaddressed_recipient_unresolved' ? (verifiedDraft?.toRecipients || []).length === 0 : ((verifiedDraft?.toRecipients || []).length === 1 && String(verifiedDraft.toRecipients[0]?.emailAddress?.address || '').toLowerCase() === pkg.recipient_proof.address.toLowerCase()));
  const verified = Boolean(verifiedDraft?.isDraft && verifiedDraft.parentFolderId === draftsFolder?.id && recipientMatches);
  if (!verified) throw Object.assign(new Error('Draft verification failed: Graph did not prove the expected unsent Drafts item'), { code: 'DRAFT_FOLDER_OR_RECIPIENT_UNVERIFIED' });
  if (pkg.mode === 'reply_inbound') await verifyReplyThread(callGraph, accessToken, exactMessageId, verifiedDraft);
  const bodyProof = verifyDraftBodyReadback(verifiedDraft, pkg.draft.body);
  const fallbackUnlinked = pkg.mode === 'reply_without_exact_anchor';
  const result = { draft_id: draftId, web_link: verifiedDraft.webLink || created?.webLink || null, subject: verifiedDraft.subject || subject, verified: true, draft_route: fallbackUnlinked ? 'fallback_unlinked' : 'linked_or_standalone', body_hash: bodyHash, verification: { mode: pkg.mode, linkage_status: fallbackUnlinked ? 'fallback_unlinked' : (pkg.mode === 'reply_inbound' ? 'linked_exact_thread' : 'standalone'), recipient_verified: recipientMatches, subject: verifiedDraft.subject || subject, saved_at: verifiedDraft.lastModifiedDateTime || null, ...bodyProof } };
  return { ok: true, reused: false, ...persistOutput(db, task, subtask, idempotencyKey, result, deps.addEvent, String(payload.work_type || 'email_reply_draft')) };
}

// A correction may update only a draft that this task-system writer previously
// created for the same task/subtask. It cannot be used to reach arbitrary mail.
async function updateCompositionDraft(db, payload, deps = {}) {
  const taskId = String(payload.task_id || ''); const subtaskId = String(payload.subtask_id || ''); const draftId = String(payload.draft_id || '');
  const pkg = validateCompositionPackage(payload.composition_package);
  const task = deps.getEntity(db, 'task', taskId); const subtask = deps.getEntity(db, 'subtask', subtaskId);
  if (!task || !subtask || subtask.parent_id !== task.id) throw new Error('task/subtask binding is invalid');
  const outputs = db.prepare('SELECT * FROM task_outputs WHERE task_id=? AND subtask_id=? AND output_type=?').all(task.id, subtask.id, 'outlook_draft');
  const owned = outputs.find((row) => { try { return JSON.parse(row.result_json || '{}').draft_id === draftId; } catch (_) { return false; } });
  if (!owned) throw new Error('Draft update requires a task-system-created draft belonging to this exact task/subtask');
  const { signature, accessToken, callGraph } = await writerDependencies(deps);
  const exactMessageId = pkg.mode === 'reply_inbound' ? getExactMessageId(task, subtask) : null;
  const subject = pkg.mode === 'follow_up_outbound' ? normaliseFollowUpSubject(pkg.subject || pkg.draft.subject) : String(pkg.subject || pkg.draft.subject || '').trim();
  const patched = await callGraph(accessToken, 'PATCH', `/me/messages/${encodeURIComponent(draftId)}`, { subject, body: { contentType: 'HTML', content: htmlBody(pkg.draft.body, signature) } });
  const draftsFolder = await callGraph(accessToken, 'GET', '/me/mailFolders/drafts?$select=id');
  const verifiedDraft = await callGraph(accessToken, 'GET', `/me/messages/${encodeURIComponent(draftId)}?$select=id,isDraft,parentFolderId,subject,webLink,toRecipients,conversationId,body,lastModifiedDateTime`);
  const recipientMatches = pkg.mode === 'reply_inbound' || (pkg.recipient_proof.strategy === 'new_draft_unaddressed_recipient_unresolved' ? (verifiedDraft?.toRecipients || []).length === 0 : ((verifiedDraft?.toRecipients || []).length === 1 && String(verifiedDraft.toRecipients[0]?.emailAddress?.address || '').toLowerCase() === pkg.recipient_proof.address.toLowerCase()));
  if (!(verifiedDraft?.isDraft && verifiedDraft.parentFolderId === draftsFolder?.id && recipientMatches)) throw Object.assign(new Error('Draft update verification failed: Graph did not prove the expected unsent Drafts item'), { code: 'DRAFT_FOLDER_OR_RECIPIENT_UNVERIFIED' });
  if (pkg.mode === 'reply_inbound') await verifyReplyThread(callGraph, accessToken, exactMessageId, verifiedDraft);
  const bodyProof = verifyDraftBodyReadback(verifiedDraft, pkg.draft.body);
  const result = { id: owned.id, task_id: task.id, subtask_id: subtask.id, draft_id: draftId, web_link: verifiedDraft.webLink || patched?.webLink || null, subject: verifiedDraft.subject || subject, outcome: 'draft_updated_not_sent', coverage_status: 'complete', review_required: true, verified: true, verification: { mode: pkg.mode, recipient_verified: recipientMatches, subject: verifiedDraft.subject || subject, saved_at: verifiedDraft.lastModifiedDateTime || null, ...bodyProof } };
  db.prepare('UPDATE task_outputs SET status=?, output_json=?, result_json=?, updated_at=? WHERE id=?').run('updated', JSON.stringify(result), JSON.stringify(result), new Date().toISOString(), owned.id);
  deps.addEvent(db, subtask.id, 'email_draft_updated', { event_type: 'email_draft_updated', output_id: owned.id, draft_id: draftId, verified: true, no_send_endpoint_called: true });
  return { ok: true, reused: false, ...result };
}

// Compatibility aliases deliberately retain package-only admission.
async function createReplyDraft(db, payload, deps = {}) { return createCompositionDraft(db, payload, deps); }
async function createDraft(db, payload, deps = {}) { return payload?.draft_id ? updateCompositionDraft(db, payload, deps) : createCompositionDraft(db, payload, deps); }

module.exports = { createDraft, createReplyDraft, createCompositionDraft, updateCompositionDraft, validateCompositionPackage, stripRedundantAuthoredName, SOURCE_REF_RE, getMicrosoftReadAccessToken: () => refreshToken(resolveTokenFile('microsoft')) };
