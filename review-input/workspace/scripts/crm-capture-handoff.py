#!/usr/bin/env python3
"""Fail-closed CRM capture and controlled SharePoint handoff.

The router owns admission into ``memory/crm-capture-state.json``.  This worker
is the only proposed writer: it queues a dated evidence artifact and a Current
append, makes a deliberately worded local CRM control update, and waits for
both queue-result proofs before marking an event confirmed.  It never infers
an entity, source evidence, CRM row, or SharePoint success.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from intake_ledger import canonical_event_id, record_receipt

WORKSPACE = Path('/home/tomdean88/.openclaw/workspace')
EVENTS = WORKSPACE / 'memory/mirror-events.json'
STATE = WORKSPACE / 'memory/crm-capture-state.json'
REPORT = WORKSPACE / 'memory/crm-capture-handoff.md'
CRM = WORKSPACE / 'stackstone/crm.md'
SHAREPOINT_QUEUE = WORKSPACE.parent / 'sharepoint-queue.json'
SHAREPOINT_RESULTS = WORKSPACE.parent / 'sharepoint-queue-results.json'
MAX_TERMINAL = 500
CONTROL_TYPES = {'Account', 'Opportunity'}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def load(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return fallback


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(content)
    tmp.replace(path)


def canonical_source_key(event_id: str) -> str:
    parts = event_id.split(':', 3)
    if len(parts) != 4 or parts[3] == 'no-source-id':
        return event_id
    _surface, source_type, thread_key, source_id = parts
    return f'{source_type}:{thread_key}:{source_id}'


def capture(payload: dict, prior: dict) -> dict:
    """Admit router events while preserving writer-owned durable fields."""
    stamp = now()
    existing: dict[str, dict] = {}
    for item in prior.get('items', []):
        event_id = str(item.get('event_id') or '')
        if event_id:
            migrated = dict(item)
            migrated['canonical_source_key'] = str(item.get('canonical_source_key') or canonical_source_key(event_id))
            existing.setdefault(migrated['canonical_source_key'], migrated)
    for event in payload.get('items') or []:
        if event.get('owning_system') != 'crm' or event.get('management_relevance') != 'needs_management':
            continue
        event_id = str(event.get('stable_item_key') or '')
        if not event_id:
            continue
        source_key = canonical_source_key(event_id)
        candidates = event.get('candidate_entities') or []
        router_state = event.get('crm_capture_state')
        blocker = event.get('crm_capture_blocker')
        if router_state not in {'pending', 'queued', 'blocked'}:
            router_state = 'pending' if len(candidates) == 1 else 'blocked'
            blocker = blocker or ('multiple candidate entities; resolve attribution before CRM/SharePoint write' if len(candidates) > 1 else 'CRM signal has no deterministic entity')
        old = existing.get(source_key, {})
        if old.get('state') in {'confirmed', 'reconciled', 'not_needed'}:
            continue
        mapping = event.get('entity_mapping') or {'status': 'mapped' if len(candidates) == 1 else ('ambiguous' if len(candidates) > 1 else 'unmapped'), 'entity': candidates[0] if len(candidates) == 1 else None, 'candidates': candidates}
        preserved = {k: deepcopy(v) for k, v in old.items() if k in {'writer', 'reconciliation_proof'} }
        state = 'blocked' if router_state == 'blocked' else old.get('state') if old.get('state') == 'sharepoint_queued' else 'queued'
        existing[source_key] = {
            **preserved,
            'event_id': old.get('event_id') or event_id,
            'canonical_source_key': source_key,
            'entity': candidates[0] if len(candidates) == 1 else None,
            'candidate_entities': candidates,
            'entity_mapping': mapping,
            'source_timestamp': event.get('source_timestamp'),
            'source_line_ref': event.get('source_line_ref') or event.get('proof_source') or event.get('raw_evidence_ref'),
            'surface': event.get('surface'), 'direction': event.get('direction'),
            'evidence_ref': event.get('proof_source') or event.get('raw_evidence_ref'),
            'subject_or_location': event.get('subject_or_location'), 'router_state': router_state,
            'state': state, 'blocker': blocker if state == 'blocked' else old.get('blocker'),
            'last_touch_date': (event.get('outbound_commitment_control') or {}).get('last_touch_date') or str(event.get('source_timestamp') or '')[:10] or None,
            'next_action_control': (event.get('outbound_commitment_control') or {}).get('next_action') or event.get('required_next_action'),
            'sharepoint_requirement': (event.get('outbound_commitment_control') or {}).get('sharepoint_requirement') or 'Reconcile against SharePoint Current and retain required artifact/write proof.',
            'required_sharepoint_artifacts': ['Current.md', 'dated communication or commitment artifact', 'write proof'],
            'outbound_commitment_control': event.get('outbound_commitment_control') or {'detected': False},
            'first_captured_at': old.get('first_captured_at', stamp), 'last_seen_at': stamp,
        }
    items = list(existing.values())
    terminal = [x for x in items if x.get('state') in {'confirmed', 'reconciled', 'not_needed'}]
    open_items = [x for x in items if x.get('state') not in {'confirmed', 'reconciled', 'not_needed'}]
    terminal.sort(key=lambda x: x.get('last_seen_at', ''), reverse=True)
    open_items.sort(key=lambda x: (x.get('state') != 'blocked', x.get('source_timestamp') or ''))
    return {'schema_version': 2, 'generated_at': stamp, 'items': open_items + terminal[:MAX_TERMINAL]}


def _queue_id(event_id: str, kind: str) -> str:
    return f"crmcap-{hashlib.sha256(event_id.encode()).hexdigest()[:16]}-{kind}"


def _crm_row(crm_text: str, entity: str, entity_type: str) -> tuple[int, list[str], str] | None:
    """Return one exact control row, only in the named Account/Opportunity table."""
    section = f'## {entity_type}s'
    start = crm_text.find(section)
    if start < 0:
        return None
    end = crm_text.find('\n## ', start + len(section))
    end = len(crm_text) if end < 0 else end
    matches = []
    for offset, line in enumerate(crm_text[start:end].splitlines()):
        if not line.startswith('|') or line.startswith('|---'):
            continue
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        if cells and cells[0] == entity:
            matches.append((start + sum(len(x) + 1 for x in crm_text[start:end].splitlines()[:offset]), cells, line))
    return matches[0] if len(matches) == 1 and len(matches[0][1]) >= 7 else None


def _row_path(cells: list[str], entity_type: str, entity: str) -> str | None:
    # Table notes may contain literal pipes, so use the final absolute Current path.
    found = re.findall(r'/(?:Accounts|Opportunities)/[^|]+? - Current\.md', ' | '.join(cells))
    if len(found) != 1:
        return None
    path = found[0]
    expected = f'/{entity_type}s/'
    return path if path.startswith(expected) and entity in path else None


def _safe_title(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9 .,&()-]+', ' ', value or 'Outbound Commitment').strip()
    return cleaned[:80] or 'Outbound Commitment'


def _requirements(item: dict, crm_text: str) -> tuple[dict | None, str | None]:
    mapping = item.get('entity_mapping') or {}
    entity, entity_type = item.get('entity'), mapping.get('entity_type')
    if mapping.get('status') != 'mapped' or not entity or entity_type not in CONTROL_TYPES:
        return None, 'entity mapping is not a deterministic Account/Opportunity mapping'
    source_ref = item.get('source_line_ref') or item.get('evidence_ref')
    if not source_ref:
        return None, 'source evidence/ref is required'
    if not item.get('source_timestamp') or not item.get('last_touch_date') or not item.get('next_action_control'):
        return None, 'source timestamp, last-touch date and next-action control are required'
    row = _crm_row(crm_text, entity, entity_type)
    if not row:
        return None, 'exact local CRM control row is missing or non-unique'
    path = _row_path(row[1], entity_type, entity)
    if not path:
        return None, 'deterministic SharePoint Current.md path is missing from the exact CRM row'
    return {'entity': entity, 'entity_type': entity_type, 'source_ref': source_ref, 'row': row, 'path': path}, None


def _proof_by_id(results: list[dict], op_id: str) -> dict | None:
    matches = [r for r in results if r.get('id') == op_id]
    return matches[-1] if matches else None


def controlled_write(state: dict, crm_text: str, queue: list[dict], results: list[dict]) -> tuple[dict, str, list[dict], list[dict]]:
    """Pure controlled writer. Returned artifacts are persisted only by --execute."""
    state, queue = deepcopy(state), deepcopy(queue)
    actions: list[dict] = []
    lines = crm_text.splitlines(keepends=True)
    for item in state.get('items', []):
        if item.get('state') in {'confirmed', 'reconciled', 'not_needed'}:
            continue
        if item.get('state') == 'blocked':
            actions.append({'event_id': item.get('event_id'), 'outcome': 'blocked', 'reason': item.get('blocker') or 'blocked before controlled writer'})
            continue
        details, blocker = _requirements(item, ''.join(lines))
        if blocker:
            item['state'], item['blocker'] = 'blocked', blocker
            actions.append({'event_id': item.get('event_id'), 'outcome': 'blocked', 'reason': blocker})
            continue
        event_id = item['event_id']; artifact_id = _queue_id(event_id, 'artifact'); current_id = _queue_id(event_id, 'current')
        prior_writer = item.get('writer') or {}
        proof_a, proof_c = _proof_by_id(results, artifact_id), _proof_by_id(results, current_id)
        if proof_a or proof_c:
            if proof_a and proof_c and proof_a.get('success') is True and proof_c.get('success') is True:
                item['state'], item['blocker'] = 'confirmed', None
                item['reconciliation_proof'] = {'confirmed_at': now(), 'artifact': proof_a, 'current': proof_c}
                actions.append({'event_id': event_id, 'outcome': 'confirmed', 'queue_ids': [artifact_id, current_id]})
            elif any(p and p.get('success') is False for p in (proof_a, proof_c)):
                item['state'] = 'blocked'; item['blocker'] = 'SharePoint queue reported a failed required operation'
                item['reconciliation_proof'] = {'artifact': proof_a, 'current': proof_c}
                actions.append({'event_id': event_id, 'outcome': 'blocked', 'reason': item['blocker']})
            else:
                item['state'] = 'sharepoint_queued'
                actions.append({'event_id': event_id, 'outcome': 'awaiting_proof', 'queue_ids': [artifact_id, current_id]})
            continue
        if prior_writer.get('queue_ids'):
            item['state'] = 'sharepoint_queued'
            actions.append({'event_id': event_id, 'outcome': 'awaiting_proof', 'queue_ids': prior_writer['queue_ids']})
            continue
        date = item['last_touch_date']; title = _safe_title(item.get('subject_or_location') or 'Outbound Commitment')
        artifact_path = f"/{details['entity_type']}s/{details['entity']}/{date} - Outbound Commitment - {title}.md"
        artifact_content = (f"# {date} — Outbound commitment\n\n- **Entity:** {details['entity']}\n- **Source evidence:** `{details['source_ref']}`\n- **Source timestamp:** {item['source_timestamp']}\n- **Commitment/control:** {item['next_action_control']}\n- **Status:** SharePoint confirmation pending.\n")
        current_content = (f"\n\n## {date} — outbound commitment (confirmation pending)\n"
                           f"- Source evidence: `{details['source_ref']}`\n- Last touch: {date}\n- Next step: {item['next_action_control']}\n- Dated artifact queued: `{artifact_path}`\n")
        if any(q.get('id') in {artifact_id, current_id} for q in queue):
            item['state'] = 'blocked'; item['blocker'] = 'queue contains a partial/colliding controlled-writer operation; manual reconciliation required'
            actions.append({'event_id': event_id, 'outcome': 'blocked', 'reason': item['blocker']})
            continue
        # Exact row only: preserve all non-control cells, including notes containing pipes.
        row_offset, cells, old_line = details['row']
        cells[3] = date
        cells[4] = f"{item['next_action_control']} SharePoint artifact and Current.md update queued; confirmation pending."
        new_line = '| ' + ' | '.join(cells) + ' |'
        pos = ''.join(lines).find(old_line)
        if pos < 0:
            item['state'] = 'blocked'; item['blocker'] = 'exact CRM row changed during controlled write preparation'
            actions.append({'event_id': event_id, 'outcome': 'blocked', 'reason': item['blocker']})
            continue
        rebuilt = ''.join(lines).replace(old_line, new_line, 1)
        lines = rebuilt.splitlines(keepends=True)
        requested_at = now()
        queue.extend([
            {'id': artifact_id, 'operation': 'create', 'path': artifact_path, 'content': artifact_content, 'requested_at': requested_at, 'source': 'crm-capture-controlled-writer', 'event_id': event_id},
            {'id': current_id, 'operation': 'append', 'path': details['path'], 'content': current_content, 'requested_at': requested_at, 'source': 'crm-capture-controlled-writer', 'event_id': event_id},
        ])
        item['state'], item['blocker'] = 'sharepoint_queued', None
        item['writer'] = {'queued_at': requested_at, 'queue_ids': [artifact_id, current_id], 'artifact_path': artifact_path, 'current_path': details['path'], 'proof_requirements': {'all_queue_ids_must_succeed': True, 'result_source': str(SHAREPOINT_RESULTS)}}
        actions.append({'event_id': event_id, 'outcome': 'queued', 'queue_ids': [artifact_id, current_id]})
    state['schema_version'], state['writer_last_run_at'] = 2, now()
    return state, ''.join(lines), queue, actions


def sync_canonical_receipts(state: dict, *, ledger_root: Path = WORKSPACE / 'memory') -> int:
    """Advance only existing canonical CRM receipts from controlled-writer proof state.

    A state transition to ``confirmed`` is accepted solely when controlled_write
    has already retained both SharePoint result proofs.  Unknown or legacy events
    are ignored rather than creating a receipt detached from the router ledger.
    """
    events_path = ledger_root / 'intake-events.jsonl'
    try:
        canonical_ids = {json.loads(line).get('event_id') for line in events_path.read_text().splitlines() if line.strip()}
    except (OSError, json.JSONDecodeError):
        canonical_ids = set()
    written = 0
    for item in state.get('items') or []:
        stable = str(item.get('event_id') or '')
        parts = stable.split(':', 3)
        if len(parts) != 4:
            continue
        surface, _kind, thread_key, source_id = parts
        try:
            event_id = canonical_event_id(surface=surface, provider_event_id=source_id, provider_conversation_id=thread_key)
        except ValueError:
            continue
        if event_id not in canonical_ids:
            continue
        state_name = str(item.get('state') or '')
        if state_name == 'confirmed':
            receipt_state, error = 'verified', None
            proof = item.get('reconciliation_proof') or {}
            destination = json.dumps({'artifact': proof.get('artifact', {}).get('id'), 'current': proof.get('current', {}).get('id')}, sort_keys=True)
        elif state_name == 'blocked':
            receipt_state, error, destination = 'blocked', str(item.get('blocker') or 'crm_capture_blocked'), None
        elif state_name == 'sharepoint_queued':
            receipt_state, error, destination = 'queued', None, None
        else:
            receipt_state, error, destination = 'pending', None, None
        record_receipt({
            'event_id': event_id, 'route': 'crm', 'state': receipt_state,
            'owner': 'crm-capture-handoff',
            'evidence_ref': item.get('source_line_ref') or item.get('evidence_ref'),
            'destination_ref': destination,
            'error_code': error,
            'next_review_at': None if receipt_state == 'verified' else now(),
        }, root=ledger_root)
        written += 1
    return written


def render(state: dict) -> str:
    lines = ['# CRM Capture Handoff', f"_Generated: {state.get('generated_at')}_", '', 'Events are only **confirmed** after both SharePoint queue IDs have successful result proof.', '', '| state | entity | source | next action / blocker |', '|---|---|---|---|']
    for x in state.get('items') or []:
        text = x.get('blocker') or x.get('next_action_control') or ''
        lines.append(f"| {x.get('state','')} | {x.get('entity') or 'unresolved'} | `{x.get('source_line_ref') or x.get('evidence_ref') or ''}` | {text.replace('|','/')} |")
    if not state.get('items'): lines.append('| clean | — | — | No pending CRM capture events |')
    return '\n'.join(lines) + '\n'


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument('--execute', action='store_true'); args = ap.parse_args()
    admitted = capture(load(EVENTS, {}), load(STATE, {}))
    state, crm, queue, actions = controlled_write(admitted, CRM.read_text(), load(SHAREPOINT_QUEUE, []), load(SHAREPOINT_RESULTS, []))
    if args.execute:
        atomic_write(CRM, crm)
        atomic_write(SHAREPOINT_QUEUE, json.dumps(queue, indent=2, sort_keys=True) + '\n')
        atomic_write(STATE, json.dumps(state, indent=2) + '\n')
        sync_canonical_receipts(state)
        atomic_write(REPORT, render(state))
    print(json.dumps({'actions': actions, 'execute': args.execute}, indent=2))

if __name__ == '__main__':
    main()
