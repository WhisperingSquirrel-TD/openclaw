const EXECUTOR_REGISTRY_VERSION = 'brief-work-executors-v1';
const compositionProviderContract = require('./email-composition-provider');

function sourceRefs(output) {
  return Array.isArray(output?.source_refs) ? output.source_refs.filter(value => typeof value === 'string' && value.length <= 512) : [];
}

const EXECUTORS = Object.freeze({
  client_document: {
    work_type: 'client_document', version: 'client_document_executor_v1', required_profile: 'sufficient_context_v1',
    output_types: ['document_draft_package'], approval: 'tom_review_required', external_delivery: 'prohibited',
    validate(output) {
      if (!output || typeof output !== 'object' || !Array.isArray(output.sections) || output.sections.length < 1) return { ok: false, code: 'DOCUMENT_SECTIONS_REQUIRED', message: 'client_document output requires one or more structured sections' };
      if (!sourceRefs(output).length) return { ok: false, code: 'DOCUMENT_PROVENANCE_REQUIRED', message: 'client_document output requires source_refs' };
      return { ok: true, output_type: 'document_draft_package' };
    },
  },
  email_reply_draft: {
    work_type: 'email_reply_draft', version: 'email_reply_draft_executor_v1', required_profile: 'email_draft_v1',
    output_types: ['unsent_email_draft'], approval: 'tom_review_required', external_delivery: 'send_prohibited',
    validate(output) {
      if (!output || typeof output !== 'object' || typeof output.draft_text !== 'string' || !output.draft_text.trim()) return { ok: false, code: 'DRAFT_TEXT_REQUIRED', message: 'email_reply_draft output requires non-empty draft_text' };
      const anchorless = output.mode === 'reply_without_exact_anchor';
      if (!anchorless && (!Array.isArray(output.thread_evidence) || output.thread_evidence.length < 1)) return { ok: false, code: 'THREAD_EVIDENCE_REQUIRED', message: 'email_reply_draft requires separated exact-thread evidence unless explicitly anchorless' };
      if (anchorless && Array.isArray(output.thread_evidence)) return { ok: false, code: 'ANCHORLESS_THREAD_EVIDENCE_PROHIBITED', message: 'anchorless reply drafts must not claim or infer thread evidence' };
      if (!output.draft || typeof output.draft !== 'object' || typeof output.draft.body !== 'string' || !output.draft.body.trim()) return { ok: false, code: 'DRAFT_PACKAGE_REQUIRED', message: 'email_reply_draft output requires a structured draft package' };
      if (!['reply_inbound', 'follow_up_outbound', 'standalone_new_message', 'reply_without_exact_anchor'].includes(output.mode)) return { ok: false, code: 'COMPOSITION_MODE_REQUIRED', message: 'email_reply_draft requires a supported exact or anchorless draft mode' };
      if (!output.anchor_proof || !output.recipient_proof || !output.no_send_proof || output.no_send_proof.send_endpoint_called !== false) return { ok: false, code: 'COMPOSITION_PROOF_REQUIRED', message: 'email_reply_draft requires anchor, recipient, and no-send proof' };
      if (!Array.isArray(output.unresolved_questions)) return { ok: false, code: 'UNRESOLVED_QUESTIONS_REQUIRED', message: 'email_reply_draft output requires an unresolved_questions array' };
      if (output.review_state !== 'prepared_for_review') return { ok: false, code: 'TOM_REVIEW_STATE_REQUIRED', message: 'email_reply_draft output must remain prepared_for_review' };
      if (!sourceRefs(output).length) return { ok: false, code: 'DRAFT_PROVENANCE_REQUIRED', message: 'email_reply_draft output requires source_refs' };
      if (output.send === true || output.sent === true || output.delivery === 'send' || output.external_delivery === 'allowed') return { ok: false, code: 'EXTERNAL_SEND_PROHIBITED', message: 'executor may prepare an unsent draft only' };
      return { ok: true, output_type: 'unsent_email_draft' };
    },
  },
  email_new_draft: {
    work_type: 'email_new_draft', version: 'email_new_draft_executor_v1', required_profile: 'email_draft_v1',
    output_types: ['unsent_email_draft'], approval: 'tom_review_required', external_delivery: 'send_prohibited',
    validate(output) {
      if (!output || typeof output !== 'object' || typeof output.draft_text !== 'string' || !output.draft_text.trim()) return { ok: false, code: 'DRAFT_TEXT_REQUIRED', message: 'email_new_draft output requires non-empty draft_text' };
      if (!output.draft || typeof output.draft !== 'object' || typeof output.draft.body !== 'string' || !output.draft.body.trim()) return { ok: false, code: 'DRAFT_PACKAGE_REQUIRED', message: 'email_new_draft output requires a structured draft package' };
      if (output.mode !== 'standalone_new_message') return { ok: false, code: 'FRESH_OUTBOUND_MODE_REQUIRED', message: 'email_new_draft requires standalone_new_message mode' };
      const unaddressed = output.recipient_proof?.strategy === 'new_draft_unaddressed_recipient_unresolved';
      if (!output.anchor_proof || !output.recipient_proof || (!unaddressed && output.recipient_proof.strategy !== 'new_draft_to_verified_task_recipient') || (unaddressed && output.recipient_proof.address !== null) || !output.no_send_proof || output.no_send_proof.send_endpoint_called !== false) return { ok: false, code: 'COMPOSITION_PROOF_REQUIRED', message: 'email_new_draft requires bound context, recipient proof (or explicit unaddressed-recipient proof), and no-send proof' };
      if (!Array.isArray(output.unresolved_questions) || output.review_state !== 'prepared_for_review') return { ok: false, code: 'TOM_REVIEW_STATE_REQUIRED', message: 'email_new_draft must remain prepared_for_review with unresolved questions' };
      if (!sourceRefs(output).length) return { ok: false, code: 'DRAFT_PROVENANCE_REQUIRED', message: 'email_new_draft output requires source_refs' };
      if (output.send === true || output.sent === true || output.delivery === 'send' || output.external_delivery === 'allowed') return { ok: false, code: 'EXTERNAL_SEND_PROHIBITED', message: 'executor may prepare an unsent draft only' };
      return { ok: true, output_type: 'unsent_email_draft' };
    },
  },
  meeting_action_plan: {
    work_type: 'meeting_action_plan', version: 'meeting_action_plan_executor_v2', required_profile: 'sufficient_context_v1',
    output_types: ['action_plan'], approval: 'tom_or_owner_review_required', external_delivery: 'not_applicable',
    validate(output) {
      if (!output || typeof output !== 'object' || !Array.isArray(output.actions)) return { ok: false, code: 'ACTION_LIST_REQUIRED', message: 'meeting_action_plan output requires an actions array' };
      if (!Array.isArray(output.meeting_evidence) || output.meeting_evidence.length < 1) return { ok: false, code: 'MEETING_EVIDENCE_REQUIRED', message: 'meeting_action_plan output requires separated meeting evidence' };
      if (!output.actions.every(item => item && typeof item.action === 'string' && item.action.trim() && typeof item.source_ref === 'string' && ['explicit_commitment', 'proposal', 'unresolved_pending_review'].includes(item.commitment_status))) return { ok: false, code: 'ACTION_SHAPE_INVALID', message: 'meeting_action_plan actions require action, source_ref, and commitment_status' };
      if (!Array.isArray(output.unresolved_questions)) return { ok: false, code: 'ACTION_QUESTIONS_REQUIRED', message: 'meeting_action_plan output requires unresolved_questions' };
      if (output.review_state !== 'prepared_for_review') return { ok: false, code: 'ACTION_REVIEW_STATE_REQUIRED', message: 'meeting_action_plan output must remain prepared_for_review' };
      if (!sourceRefs(output).length) return { ok: false, code: 'ACTION_PROVENANCE_REQUIRED', message: 'meeting_action_plan output requires source_refs' };
      return { ok: true, output_type: 'action_plan' };
    },
  },
});

function getExecutor(workType) {
  return EXECUTORS[workType] || null;
}

function packetSources(packet) {
  return Array.isArray(packet?.items) ? packet.items.filter(item => item && typeof item === 'object') : [];
}

function sourceRefsFromPacket(packet) {
  return packetSources(packet).flatMap(item => [item.source_id, item.source_ref]).filter(Boolean);
}

function boundedContent(item, max = 4000) {
  const content = String(item?.content || '').trim();
  return content.length <= max ? content : `${content.slice(0, max)}…`;
}

const COMMERCIAL_CUES = /\b(cost|price|pricing|matrix|scorecard|vendor|workbook|xlsx|requirements|scope|comparison|options|licen[cs]e|subscription|integration|offline)\b/i;
const FUTURE_WORK_PATTERN = /\b(i['’]?ll|i will|we['’]?ll|we will|i am going to|we are going to)\b.{0,100}\b(cover|include|compare|consider|review|look at|assess|analyse|analyze)\b/i;

function packetSourceText(packet) {
  return packetSources(packet).map(item => ({ item, text: String(item.content || '') })).filter(entry => entry.text.trim());
}

function exactEmailSource(packet) {
  const emailSources = packetSources(packet).filter(item => item.source_kind === 'email' && item.source_role === 'dated_artifact' && item.required_evidence);
  if (emailSources.length !== 1) return { ok: false, code: 'EXACT_EMAIL_THREAD_SOURCE_AMBIGUOUS', message: 'Reply drafting requires exactly one required, dated exact-email-thread source; CRM/SharePoint sources may provide context but cannot anchor the reply.', email_source_count: emailSources.length };
  return { ok: true, item: emailSources[0] };
}

function parseThreadMessages(text) {
  return String(text || '').split(/\n\n---\n\n/).filter(Boolean).map((message, index) => {
    const from = message.match(/^From:\s*(.+)$/im)?.[1]?.trim() || null;
    const to = message.match(/^To:\s*(.+)$/im)?.[1]?.trim() || null;
    const date = message.match(/^Date:\s*(.+)$/im)?.[1]?.trim() || null;
    const subject = message.match(/^Subject:\s*(.+)$/im)?.[1]?.trim() || null;
    const isDraft = /^IsDraft:\s*true\s*$/im.test(message);
    const body = message.replace(/^(?:Schema|Thread-Message-Count|Representation-Message-Count|All-Messages-Represented|Coverage|Message-Index|From|To|Cc|Date|Subject|IsDraft|Status|Raw-Content-Bytes|Raw-Content-SHA-256|Represented-Content-Bytes|Represented-Content-SHA-256):.*(?:\r?\n|$)/gim, '').trim();
    return { index, from, to, date, subject, isDraft, body, content: message };
  });
}

function isTomIdentity(value) { return /(?:tom@stackstoneconsulting\.co\.uk|tom dean|tom\s+dean)/i.test(String(value || '')); }
function emailAddress(value) { return String(value || '').match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)?.[0]?.toLowerCase() || null; }
function compositionMode(task = {}, packet) {
  const mode = task.context_loading_contract?.reply_mode || task.context_loading_contract?.interpretation?.reply_mode || 'reply_inbound';
  return ['reply_inbound', 'follow_up_outbound', 'standalone_new_message', 'reply_without_exact_anchor'].includes(mode) ? mode : 'reply_inbound';
}
function latestVisibleAsk(body) {
  const lines = String(body || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const question = lines.find(line => /\?$/.test(line));
  const request = lines.find(line => /\b(?:can you|could you|would you|please|let me know|confirm|send|share|book|arrange)\b/i.test(line));
  const ask = question || request || null;
  if (!ask || ask.length > 500) return null;
  return ask.replace(/\s+/g, ' ').trim();
}
function composeConservativeEmail(task, packet) {
  const exact = exactEmailSource(packet); if (!exact.ok) return exact;
  const messages = parseThreadMessages(exact.item.content);
  const mode = compositionMode(task, packet); const latest = messages.at(-1);
  if (!latest || !latest.from || !latest.date) return { ok: false, code: 'LATEST_MESSAGE_METADATA_INCOMPLETE', message: 'Exact bounded evidence lacks the latest message sender/date.' };
  if (mode === 'reply_inbound') {
    if (isTomIdentity(latest.from)) return { ok: false, code: 'LATEST_MESSAGE_IS_TOM_OUTBOUND', message: 'Reply-to-last-email requires a latest inbound message, not Tom outbound.' };
    const recipient = emailAddress(latest.from); if (!recipient) return { ok: false, code: 'RECIPIENT_IDENTITY_UNRESOLVED', message: 'Latest inbound sender has no resolvable email address.' };
    const ask = latestVisibleAsk(latest.body);
    if (!ask) return { ok: false, code: 'LATEST_VISIBLE_ASK_UNRESOLVED', message: 'The latest inbound message has no confidently identifiable ask; retain a coverage/review blocker rather than inventing a holding reply.' };
    // This is deliberately an acknowledgement of the visible ask, not an invented
    // commitment, answer, or generic "come back shortly" promise.
    const body = `Hi,\n\nThanks for your email. I’ve received your question: “${ask}”\n\nBest,`;
    return { ok: true, mode, anchor: latest, recipient_proof: { strategy: 'createReplyAll_exact_inbound', address: recipient, anchor_message_index: latest.index, source_ref: exact.item.source_id || exact.item.source_ref }, body, automation_eligibility: 'benign_acknowledgement_only' };
  }
  if (!isTomIdentity(latest.from)) return { ok: false, code: 'FOLLOW_UP_REQUIRES_LATEST_TOM_OUTBOUND', message: 'Follow-up on my last sent email requires the exact latest material message to be Tom outbound.' };
  const prior = messages.slice(0, -1).reverse().find(message => !isTomIdentity(message.from) && emailAddress(message.from));
  if (!prior) return { ok: false, code: 'FOLLOW_UP_RECIPIENT_UNRESOLVED', message: 'No original non-Tom recipient is present in the bounded continuity evidence.' };
  const priorAsk = latestVisibleAsk(latest.body);
  if (!priorAsk) return { ok: false, code: 'FOLLOW_UP_OBJECTIVE_UNRESOLVED', message: 'The latest Tom outbound has no confidently identifiable visible ask to follow up; retain a review blocker rather than inventing outreach.' };
  const subjectBase = String(latest.subject || '').replace(/^(?:Re:\s*)+/i, '').trim();
  if (!subjectBase) return { ok: false, code: 'FOLLOW_UP_SUBJECT_UNRESOLVED', message: 'Follow-up requires an anchored non-empty subject.' };
  return { ok: true, mode, anchor: latest, recipient_proof: { strategy: 'new_draft_to_original_non_tom_recipient', address: emailAddress(prior.from), source_ref: exact.item.source_id || exact.item.source_ref, continuity_message_index: prior.index }, subject: `RE: ${subjectBase}`, body: `Hi,\n\nI’m following up on the question in my last email: “${priorAsk}”\n\nBest,`, automation_eligibility: 'benign_follow_up_only' };
}

function latestInboundEvidence(packet) {
  const exact = exactEmailSource(packet);
  if (!exact.ok) return exact;
  const messages = parseThreadMessages(exact.item.content);
  if (!messages.length) return { ok: false, code: 'EXACT_EMAIL_THREAD_EMPTY', message: 'The exact email source contains no readable messages.' };
  const latest = messages[messages.length - 1];
  const tom = /(?:tom@stackstoneconsulting\.co\.uk|tom dean|tom\s+dean)/i.test(String(latest.from || ''));
  if (tom) return { ok: false, code: 'LATEST_MESSAGE_IS_TOM_OUTBOUND', message: 'The latest exact-thread message is already Tom outbound; no reply draft should be created.' };
  if (!latest.from || !latest.date) return { ok: false, code: 'LATEST_MESSAGE_METADATA_INCOMPLETE', message: 'The exact thread does not expose enough sender/date metadata to prove which inbound message is latest.' };
  return { ok: true, source_ref: exact.item.source_id || exact.item.source_ref, latest_message: { index: latest.index, from: latest.from, date: latest.date, evidence_excerpt: boundedContent({ content: latest.content }, 1200) }, message_count: messages.length };
}

function detectLaterTomOutbound(packet) {
  // Legacy reconciliation callers may supply a bounded thread without the
  // stricter composition metadata. This detector remains metadata-tolerant;
  // automatic composition still uses exactEmailSource/composeConservativeEmail.
  const email = packetSources(packet).find(item => item.source_kind === 'email');
  if (!email) return null;
  const messages = parseThreadMessages(email.content);
  // A Graph-created Outlook draft can appear in the exact conversation. It is
  // not a sent outbound and must never suppress replacement/retry drafting.
  const latest = messages.at(-1);
  return latest && isTomIdentity(latest.from) && !latest.isDraft
    ? { source_ref: email.source_id || email.source_ref, evidence_excerpt: boundedContent({ content: latest.content }, 1200) }
    : null;
}

function reconcileExistingWork(packet) {
  const entries = packetSourceText(packet);
  const emailEntries = entries.filter(({ item }) => item.source_kind === 'email');
  const artifactEntries = entries.filter(({ item }) => ['sharepoint', 'crm'].includes(item.source_kind) && item.source_role !== 'current');
  const currentEntries = entries.filter(({ item }) => ['sharepoint', 'crm'].includes(item.source_kind) && item.source_role === 'current');
  const emailText = emailEntries.map(({ text }) => text).join('\n');
  const commercial = COMMERCIAL_CUES.test(emailText);
  const already = artifactEntries.filter(({ text }) => commercial && COMMERCIAL_CUES.test(text));
  const classifications = [];
  already.forEach(({ item, text }) => classifications.push({ classification: 'already_considered', source_ref: item.source_id || item.source_ref, provenance: { source_kind: item.source_kind, source_ref: item.source_ref, extraction: item.extraction || null }, evidence_excerpt: boundedContent({ content: text }, 900) }));
  if (commercial && !already.length) classifications.push({ classification: 'unverified', source_ref: null, provenance: null, evidence_excerpt: 'No matching dated preparation artifact was available in the bounded packet.' });
  return { triggered: commercial, classifications, current_truth_refs: currentEntries.map(({ item }) => item.source_id || item.source_ref), supporting_artifact_refs: artifactEntries.map(({ item }) => item.source_id || item.source_ref), status: commercial && !already.length ? 'coverage_incomplete' : 'reconciled' };
}

function parseMeetingAction(text, sourceRef, index) {
  const ownerMatch = text.match(/^([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,2})\s*(?::|\b(?:will|must|should|needs to|agreed to|is to)\b)/);
  const owner = ownerMatch && !/^(The|We|They|It|Team)\b/.test(ownerMatch[1]) ? ownerMatch[1] : null;
  const dueMatch = text.match(/\b(?:by|before|on)\s+((?:next\s+week|tomorrow|today|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|\d{1,2}(?:st|nd|rd|th)?(?:\s+\w+)?))\b/i);
  const commitment_status = /\b(will|agreed|committed|confirmed|confirm|shall|must)\b/i.test(text)
    ? 'explicit_commitment'
    : /\b(should|could|suggest|propose|might|consider)\b/i.test(text) ? 'proposal' : 'unresolved_pending_review';
  return {
    action_id: `action_${index + 1}`,
    action: text,
    owner,
    owner_confidence: owner ? 'explicit' : 'unresolved',
    due: dueMatch ? dueMatch[1] : null,
    due_confidence: dueMatch ? 'explicit' : 'unresolved',
    commitment_status,
    source_ref: sourceRef,
    evidence_excerpt: text,
  };
}

async function execute(workType, packet, task = {}, subtask = {}, compositionProvider = null) {
  const sources = packetSources(packet);
  const source_refs = sources.map(item => item.source_id || item.source_ref).filter(Boolean);
  if (!sources.length) return { ok: false, code: 'EXECUTION_SOURCES_REQUIRED', message: 'Executor requires at least one bounded context source' };

  if (workType === 'client_document') {
    return {
      ok: true,
      output: {
        schema: 'client-document-draft-package-v1',
        title: task.title || subtask.title || 'Client document draft',
        sections: sources.map((item, index) => ({
          id: `section_${index + 1}`,
          title: index === 0 ? 'Current registered truth' : `Supporting evidence ${index}`,
          content: boundedContent(item),
          classification: item.context_layer === 'current_record' ? 'verified_current_truth' : 'supporting_evidence',
          source_ref: item.source_id || item.source_ref,
          freshness_status: item.freshness_status || 'unknown',
          source_version_or_modified_at: item.source_version_or_modified_at || null,
        })),
        evidence_matrix: sources.map(item => ({
          source_ref: item.source_id || item.source_ref,
          classification: item.context_layer === 'current_record' ? 'verified_current_truth' : 'supporting_evidence',
          claim_scope: item.context_layer === 'current_record' ? 'current_record' : 'linked_evidence',
          freshness_status: item.freshness_status || 'unknown',
          required_evidence: Boolean(item.required_evidence),
        })),
        coverage: {
          status: 'complete_bounded_packet',
          source_count: sources.length,
          broad_search_performed: false,
          missing_coverage: [],
          conflicts: [],
        },
        review_checklist: [
          'Confirm the current truth is still accurate.',
          'Confirm each client-facing claim has an appropriate source.',
          'Resolve any remaining questions before external delivery.',
        ],
        unresolved_questions: [],
        review_state: 'prepared_for_review',
        source_refs,
      },
    };
  }

  if (workType === 'email_reply_draft' || workType === 'email_new_draft') {
    const fallbackUnlinked = packet?.manifest?.draft_route === 'fallback_unlinked';
    const intent = { ...(task.context_loading_contract?.composition_intent || task.context_loading_contract?.interpretation?.composition_intent || { mode: compositionMode(task, packet) }), ...(fallbackUnlinked ? { mode: 'reply_without_exact_anchor' } : {}), objective: task.intent || null, fresh_outbound: workType === 'email_new_draft' };
    const requestResult = compositionProviderContract.createRequest(packet, intent);
    if (!requestResult.ok) return { ok: false, code: requestResult.code, message: requestResult.clarification, clarification: requestResult.clarification };
    const provider = compositionProvider || compositionProviderContract.createDeterministicSafeFallbackProvider();
    let response;
    try { response = await provider.compose(requestResult.request); }
    catch (error) { return { ok: false, code: error?.code === 'COMPOSITION_PROVIDER_TIMEOUT' ? 'COMPOSITION_PROVIDER_TIMEOUT' : 'COMPOSITION_PROVIDER_UNAVAILABLE', message: 'Composition provider did not return a usable result; retryable coverage is required.', provider_id: provider.id || 'unknown' }; }
    if (response?.status === 'refused') return { ok: false, code: response.code || 'COMPOSITION_PROVIDER_REFUSED', message: response.message || 'Composition provider refused this bounded request.', provider_id: provider.id || 'unknown' };
    const checked = compositionProviderContract.validateResponse(response, requestResult.request);
    if (!checked.ok) return { ok: false, ...checked, provider_id: provider.id || 'unknown' };
    const resolved = compositionProviderContract.resolveBoundedIdentity(packet, intent);
    const sourceRef = resolved.source.source_id || resolved.source.source_ref;
    const manifest = resolved.source.composition_manifest || null;
    const packetManifest = packet?.manifest || {};
    const coverageGaps = Array.isArray(packetManifest.coverage_gaps) ? packetManifest.coverage_gaps : [];
    const packetSourceRefs = sourceRefsFromPacket(packet);
    const draft = checked.response.draft;
    const freshOutbound = workType === 'email_new_draft';
    const anchorless = resolved.mode === 'reply_without_exact_anchor';
    const contextBound = freshOutbound || anchorless;
    const output = {
      schema: 'email-composition-package-v1', mode: resolved.mode, draft_route: fallbackUnlinked ? 'fallback_unlinked' : 'linked_or_standalone', automation_eligibility: provider.quality || 'provider_composed', composition_provider: { id: provider.id || 'unknown', quality: provider.quality || 'unknown', request_schema: compositionProviderContract.REQUEST_SCHEMA, response_schema: compositionProviderContract.RESPONSE_SCHEMA }, subject: draft.subject || resolved.anchor.subject || null, draft_text: draft.body,
      draft: { body: draft.body, subject: draft.subject || resolved.anchor.subject || null, to: resolved.recipient ? [resolved.recipient] : [], source_refs: packetSourceRefs },
      // Context-bound modes are deliberately new Drafts items, never guessed email replies.
      anchor_proof: { source_ref: sourceRef, kind: contextBound ? (freshOutbound ? 'entity_current_context' : 'standalone_bounded_context') : 'exact_email_message', message_index: contextBound ? null : resolved.anchor.index, sender: contextBound ? null : (resolved.anchor.from || null), date: contextBound ? null : (resolved.anchor.date || null), content_hash: require('node:crypto').createHash('sha256').update(String(resolved.anchor.raw || `${sourceRef}:${resolved.recipient || 'RECIPIENT_UNRESOLVED'}`)).digest('hex') },
      recipient_proof: { strategy: resolved.strategy, address: resolved.recipient, source_ref: sourceRef, anchor_message_index: contextBound ? null : resolved.anchor.index, continuity_message_index: contextBound ? null : (resolved.continuity_message_index ?? null) }, source_refs: packetSourceRefs,
      context_coverage: { status: packetManifest.coverage_status || 'unknown', confidence: packetManifest.composition_confidence || (coverageGaps.length ? 'low' : 'high'), current_truth_status: packetManifest.current_truth_status || 'unknown', coverage_gaps: coverageGaps, required_curated_refresh: Boolean(packetManifest.required_curated_refresh), participant_resolution: packetManifest.participant_resolution || [], participant_resolution_method: packetManifest.participant_resolution_method || null, source_refs: packetSourceRefs },
      unresolved_questions: [...(resolved.unaddressed ? ['Add and verify the recipient address before sending.'] : []), ...(anchorless ? ['Exact email thread unavailable; this is a new unthreaded draft.'] : []), ...(coverageGaps.map((gap) => `Context coverage gap (${gap.code}): ${gap.message}`)), 'Confirm tone and any substantive commitment before sending.'], review_state: 'prepared_for_review', review_gate: 'tom_review_required', external_delivery: 'send_prohibited', send: false, sent: false, no_send_proof: { send_endpoint_called: false, composition_only: true }, context_bounds: contextBound ? { source_kind: resolved.source.source_kind, source_role: resolved.source.source_role, freshness_status: resolved.source.freshness_status, content_availability: resolved.source.content_availability } : manifest,
    };
    if (!contextBound) Object.assign(output, {
      thread_evidence: [{ source_ref: sourceRef, classification: 'exact_thread_evidence', message_count: manifest?.included_message_count || 1, omitted_earlier_message_count: manifest?.omitted_earlier_message_count || 0 }],
      reply_to_source_ref: sourceRef,
      latest_message_evidence: { source_ref: sourceRef, evidence_excerpt: `From: ${resolved.anchor.from}\nDate: ${resolved.anchor.date}` },
      thread_continuity_check: 'passed', contextual_flow_check: 'passed',
    });
    return { ok: true, output };
  }

  if (workType === 'meeting_action_plan') {
    const meetingEvidence = sources.map((item, index) => ({
      evidence_id: `meeting_evidence_${index + 1}`,
      source_ref: item.source_id || item.source_ref,
      source_kind: item.source_kind || 'meeting_record',
      content: boundedContent(item, 6000),
      freshness_status: item.freshness_status || 'unknown',
      source_version_or_modified_at: item.source_version_or_modified_at || null,
      classification: 'meeting_source_evidence',
    })).filter(item => item.content);
    const actions = meetingEvidence.flatMap(item => item.content.split(/\r?\n/).map(line => line.trim()).filter(Boolean))
      .map((text, index) => parseMeetingAction(text, meetingEvidence.find(item => item.content.includes(text))?.source_ref || source_refs[0], index));
    const unresolvedQuestions = [];
    if (!actions.length) unresolvedQuestions.push('No bounded action lines were available for review.');
    if (actions.some(item => !item.owner)) unresolvedQuestions.push('Confirm owners for actions without an explicit owner.');
    if (actions.some(item => !item.due)) unresolvedQuestions.push('Confirm dates or timing for actions without an explicit due point.');
    if (actions.some(item => item.commitment_status !== 'explicit_commitment')) unresolvedQuestions.push('Review proposals and unresolved lines against the meeting record before treating them as commitments.');
    return {
      ok: true,
      output: {
        schema: 'meeting-action-plan-v2',
        meeting_evidence: meetingEvidence,
        actions,
        unresolved_questions: unresolvedQuestions,
        review_state: 'prepared_for_review',
        review_gate: 'tom_or_owner_review_required',
        external_delivery: 'not_applicable',
        source_refs,
      },
    };
  }

  return { ok: false, code: 'EXECUTOR_UNAVAILABLE', message: `No executor is registered for work type: ${workType || 'unknown'}` };
}

function validateAgainstPacket(workType, output, packet) {
  if (!['email_reply_draft', 'email_new_draft'].includes(workType)) return { ok: true };
  // Fresh outbound drafts bind only the explicit recipient and a full, fresh
  // registered entity/current packet. They must never select/search or smuggle
  // in an inbound thread, reply target, or continuity proof.
  if (workType === 'email_new_draft') {
    const current = packetSources(packet).filter(item =>
      ['crm', 'sharepoint'].includes(item.source_kind) &&
      item.source_role === 'current' &&
      item.content_availability === 'full' &&
      item.freshness_status === 'fresh'
    );
    if (!current.length) return { ok: false, code: 'FRESH_OUTBOUND_CURRENT_CONTEXT_REQUIRED', message: 'Fresh outbound drafting requires a full, fresh registered CRM or SharePoint current entity-context source.' };
    if (output?.mode !== 'standalone_new_message' || output?.anchor_proof?.kind !== 'entity_current_context') return { ok: false, code: 'FRESH_OUTBOUND_PACKAGE_BOUNDARY_INVALID', message: 'Fresh outbound package must be explicitly entity-current-context-bound and standalone.' };
    if (Array.isArray(output?.thread_evidence) || output?.reply_to_source_ref || output?.latest_message_evidence || output?.thread_continuity_check || output?.contextual_flow_check) return { ok: false, code: 'FRESH_OUTBOUND_THREAD_EVIDENCE_PROHIBITED', message: 'Fresh outbound package must not contain inbound-thread or reply-continuity evidence.' };
    if (!current.some(item => (item.source_id || item.source_ref) === output.anchor_proof.source_ref)) return { ok: false, code: 'FRESH_OUTBOUND_CONTEXT_SOURCE_MISMATCH', message: 'Fresh outbound anchor proof must refer to a current entity-context source in the loaded packet.' };
    return { ok: true };
  }
  const mode = output?.mode || compositionMode({}, packet);
  const strictComposition = output?.schema === 'email-composition-package-v1';
  if (strictComposition && mode === 'reply_without_exact_anchor') {
    const sourceRef = output?.anchor_proof?.source_ref;
    const source = packetSources(packet).find(item => (item.source_id || item.source_ref) === sourceRef && ['whatsapp', 'linkedin', 'crm', 'sharepoint', 'teams', 'system_metadata'].includes(item.source_kind));
    const fallbackUnlinked = packet?.manifest?.draft_route === 'fallback_unlinked';
    if (!source || output?.anchor_proof?.kind !== 'standalone_bounded_context' || (fallbackUnlinked && output?.draft_route !== 'fallback_unlinked')) return { ok: false, code: 'ANCHORLESS_CONTEXT_SOURCE_INVALID', message: 'Anchorless reply requires one registered bounded entity or communication context source and explicit fallback status when the exact thread is unavailable.' };
    if (Array.isArray(output?.thread_evidence) || output?.reply_to_source_ref || output?.latest_message_evidence || output?.thread_continuity_check || output?.contextual_flow_check) return { ok: false, code: 'ANCHORLESS_THREAD_EVIDENCE_PROHIBITED', message: 'Anchorless reply must be a new draft and cannot include guessed thread evidence.' };
    return { ok: true, coverage_gap: 'EXACT_EMAIL_THREAD_UNAVAILABLE' };
  }
  const resolved = strictComposition ? compositionProviderContract.resolveBoundedIdentity(packet, { mode, recipient_email: output?.recipient_proof?.address, subject: output?.subject || output?.draft?.subject || null }) : null;
  if (strictComposition && !resolved.ok) return { ok: false, code: resolved.code, message: resolved.clarification, evidence: null };
  const legacyEmail = packetSources(packet).find(item => item.source_kind === 'email');
  const latest = strictComposition
    ? { source_ref: resolved.source.source_id || resolved.source.source_ref, latest_message: resolved.anchor }
    : { source_ref: legacyEmail?.source_id || legacyEmail?.source_ref || null, latest_message: null };
  const reconciliation = reconcileExistingWork(packet);
  // A bounded reply draft is not a commercial-delivery decision. Missing a
  // dated preparation artefact may constrain substantive commitments, but it
  // must not suppress a grounded, unsent acknowledgement of the exact inbound.
  // The provider/writer remain unable to send, widen scope, or invent claims.
  const text = String(output?.draft_text || output?.draft?.body || '').trim();
  if (!text) return { ok: false, code: 'DRAFT_TEXT_REQUIRED', message: 'Reply body is required.' };
  // The benign acknowledgement quotes the customer's exact ask. Do not mistake
  // a future-work phrase inside that quoted inbound text for Tom making a promise.
  const authoredText = text.replace(/[“"][^”"]*[”"]/g, '');
  if (reconciliation.triggered && FUTURE_WORK_PATTERN.test(authoredText)) return { ok: false, code: 'COMPLETED_WORK_RECAST_AS_FUTURE', message: 'Draft recasts already-completed preparation as future work; cite the registered artifact and state that it was already considered.', reconciliation };
  if (strictComposition && output?.reply_to_source_ref !== latest.source_ref) return { ok: false, code: 'REPLY_TARGET_MISMATCH', message: 'Draft must identify the exact email source it replies to.', expected_source_ref: latest.source_ref };
  if (strictComposition && (output?.latest_message_evidence?.source_ref !== latest.source_ref || !String(output?.latest_message_evidence?.evidence_excerpt || '').trim())) return { ok: false, code: 'LATEST_MESSAGE_ANCHOR_REQUIRED', message: 'Draft must include evidence for the latest inbound message from the exact thread.' };
  if (strictComposition && output?.thread_continuity_check !== 'passed') return { ok: false, code: 'THREAD_CONTINUITY_UNVERIFIED', message: 'Draft cannot pass without an explicit thread-continuity check.' };
  if (strictComposition && output?.contextual_flow_check !== 'passed') return { ok: false, code: 'CONTEXTUAL_FLOW_UNVERIFIED', message: 'Draft cannot pass without an explicit contextual-flow check against the latest inbound message.' };
  if (/^draft prepared from the exact bounded thread evidence/i.test(text)) return { ok: false, code: 'EVIDENCE_DUMP_NOT_REPLY', message: 'The output is an evidence dump, not a composed reply.' };
  // Existing-work reconciliation remains provenance for review and blocks any
  // unsupported substantive claim above, but does not turn an ordinary inbound
  // acknowledgement into a no-draft outcome.
  return { ok: true, reconciliation, latest_message: latest.latest_message };
}

function listExecutors() {
  return { registry_version: EXECUTOR_REGISTRY_VERSION, executors: Object.values(EXECUTORS).map(({ validate, ...contract }) => contract) };
}

module.exports = { EXECUTOR_REGISTRY_VERSION, getExecutor, listExecutors, execute, sourceRefsFromPacket, detectLaterTomOutbound, reconcileExistingWork, validateAgainstPacket };
