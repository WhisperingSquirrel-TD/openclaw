#!/usr/bin/env python3
"""Create idempotent task-system reply-prep work from routed tom@ email events.

Trusted Microsoft inbox reply candidates—including both simple direct-draft
candidates and context-heavy threads—and consequential external/body-withheld
candidates are admitted as bounded task-system work. External items are created
as explicit blocked handoffs until an approved exact-thread reader proves
complete evidence. This worker never sends email or changes the safe-sender list.
A missing CRM/SharePoint enrichment source never blocks a readable exact-thread
reply; missing exact-thread evidence remains a visible retryable blocker.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from intake_ledger import canonical_event_id, record_receipt

WORKSPACE = Path("/home/tomdean88/.openclaw/workspace")
EVENTS_PATH = WORKSPACE / "memory/mirror-events.json"
STATE_PATH = WORKSPACE / "memory/email-reply-task-handoff-state.json"
REPORT_PATH = WORKSPACE / "memory/email-reply-task-handoff.md"
GATEWAY_ENV = Path("/home/tomdean88/.config/workspace-pi-gateway/env")
GATEWAY_BASE = "http://127.0.0.1:4312"
# Existing commercial-conversation objective. Keep this explicit rather than
# silently inventing a hierarchy on every monitor pass.
DEFAULT_OBJECTIVE_ID = "obj_2dbcde0cda45ce3d"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def bearer_token() -> str:
    for line in GATEWAY_ENV.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("WORKSPACE_PI_GATEWAY_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"WORKSPACE_PI_GATEWAY_TOKEN missing from {GATEWAY_ENV}")


def api(method: str, path: str, token: str, payload: dict | None = None, allow_error: bool = False) -> dict:
    response = requests.request(
        method,
        f"{GATEWAY_BASE}{path}",
        headers={"Authorization": f"Bearer {token}", **({"Content-Type": "application/json"} if payload else {})},
        json=payload,
        timeout=20,
    )
    try:
        result = response.json()
    except ValueError:
        result = {"ok": False, "error": {"code": "TASK_SYSTEM_NON_JSON", "message": response.text}}
    if not response.ok and not allow_error:
        raise RuntimeError(f"task-system {method} {path} failed: {response.status_code} {response.text}")
    if not response.ok:
        result.setdefault("ok", False)
        result.setdefault("http_status", response.status_code)
    return result


def event_candidates(events: list[dict]) -> list[dict]:
    candidates = []
    for event in events:
        # mirror-events contains canonical raw event fields plus the routing result
        # once written by inbound-monitoring.py. Admit only bounded reply-prep
        # candidates. External/body-withheld items are preserved as blocked task
        # work; they are never treated as readable or draft-ready here.
        if event.get("direction") != "inbound":
            continue

        # Task admission is also the explicit reply/no-reply decision boundary.
        # Prefer the router's durable decision; fail closed when it is absent.
        decision = event.get("reply_decision")
        if decision not in {"reply_needed", "no_reply_needed", "blocked_to_decide"}:
            likelihood = event.get("reply_likelihood")
            decision = {
                "likely": "reply_needed",
                "maybe": "blocked_to_decide",
                "none": "no_reply_needed",
            }.get(likelihood, "blocked_to_decide")
            event["reply_decision"] = decision
            event["reply_decision_reason"] = event.get("reply_decision_reason") or "Reply decision was absent from routing metadata; preserved as blocked until explicitly classified."
        if decision == "no_reply_needed":
            continue

        # Admission is deliberately keyed to the reply decision, not to the
        # safe-sender class or to a perfectly populated draft_mode field.
        # `draft_mode` is an execution hint; it must never become a silent
        # suppression gate. A classifier/handoff schema mismatch previously
        # allowed a real reply candidate to vanish between routing and draft
        # preparation.
        #
        # Safe-sender/TOTP controls protected reads, promotion, configuration
        # and sending—not admission to unsent draft preparation. Trusted and
        # external Microsoft email candidates both enter this handoff. The
        # bounded broker/executor then proves exact-thread coverage or writes a
        # durable retryable blocker.
        if event.get("surface") not in {"microsoft_inbox", "microsoft_external"}:
            continue
        if event.get("draft_mode") in {"none", ""} and event.get("reply_decision") == "reply_needed":
            event["draft_mode"] = "direct_trusted" if event.get("surface") == "microsoft_inbox" else "task_system_context"
            event["reply_mode"] = event.get("reply_mode") or "reply_all"
            event["reply_decision_reason"] = (event.get("reply_decision_reason") or "") + " Admission repaired from explicit reply_needed decision; draft_mode was incomplete."
        if event.get("reply_decision") == "blocked_to_decide":
            # Preserve ambiguous candidates only when the router supplied a
            # usable email identity; the created task remains blocked pending
            # the missing evidence/decision rather than being dropped.
            event["draft_mode"] = event.get("draft_mode") or ("direct_trusted" if event.get("surface") == "microsoft_inbox" else "task_system_context")
        if event.get("draft_mode") not in {"task_system_context", "direct_trusted", "gated_full_read"}:
            continue
        stable_key = event.get("stable_item_key")
        if not stable_key or not event.get("source_id") or not event.get("thread_key"):
            continue
        candidates.append(event)
    return candidates


def short(value: str, limit: int = 110) -> str:
    value = " ".join((value or "").split())
    return value[: limit - 1] + "…" if len(value) > limit else value


def exact_email_source_ref(event: dict) -> str:
    """Return the broker's bounded exact-email source reference when available."""
    stable_key = event.get("stable_item_key") or ""
    if stable_key.startswith(("microsoft_inbox:email:", "microsoft_external:email:")):
        return stable_key
    surface = event.get("surface")
    conversation_id = event.get("conversation_id") or event.get("thread_id") or event.get("thread_key")
    message_id = event.get("message_id") or event.get("opaque_message_id") or event.get("source_id")
    if surface in {"microsoft_inbox", "microsoft_external"} and conversation_id and message_id:
        prefix = "microsoft_inbox" if surface == "microsoft_inbox" else "microsoft_external"
        return f"{prefix}:email:{conversation_id}:{message_id}"
    return stable_key


def create_reply_prep(event: dict, token: str, objective_id: str) -> tuple[str, str, str, dict]:
    """Atomically admit one exact inbound through the gateway intake contract.

    `brief_intakes.idempotency_key` is gateway-owned durable duplicate protection.
    The worker's JSON state remains a reporting cache only: replaying after a
    crash returns the same task tree rather than creating a second one.
    """
    subject = short(event.get("subject_or_location") or "Untitled email")
    sender = short(event.get("sender") or "Unknown sender", 80)
    stable_key = event["stable_item_key"]
    exact_source_ref = exact_email_source_ref(event)
    mailbox = "microsoft_external" if event.get("surface") == "microsoft_external" else "microsoft_inbox"
    result = api("POST", "/task-intake/brief", token, {
        "brief_text": f"Prepare an unsent reply to the exact inbound email from {sender}: {subject}. Never send.",
        "idempotency_key": f"email-reply-admission:{stable_key}",
        "title": f"Reply prep — {sender}: {subject}",
        "work_type": "email_reply_draft",
        "reply_mode": "reply_inbound",
        "source_refs": [exact_source_ref],
        "mailbox": mailbox,
        "constraints": ["draft_only", "send_prohibited", "exact_thread_only"],
        "approval_mode": "tom_review_required",
    })
    tree = result.get("task") or {}
    subtasks = result.get("subtasks") or []
    task_id = tree.get("id")
    prep_id = subtasks[0].get("id") if subtasks else None
    review_id = subtasks[-1].get("id") if subtasks else None
    if not task_id or not prep_id:
        raise RuntimeError("gateway email admission did not return an executable task/subtask tree")
    # Context-ready intake emits the operator signal itself. Context failures
    # remain explicit, task-held coverage blockers; neither branch sends email.
    return task_id, prep_id, review_id or "", result

def recover_one_retryable_draft(items: dict[str, dict], token: str, dry_run: bool) -> dict | None:
    """Retry one existing blocked email draft per router pass.

    Admission is idempotent, but a transient reader/composer/writer failure must
    not make that exact inbound invisible forever. Recovery remains bounded to
    the task already created for that exact source, respects a 15-minute quiet
    period and a three-attempt cap, and never sends email. The executor still
    performs later-Tom-outbound suppression before it can create a draft.
    """
    now = datetime.now(timezone.utc)
    for key, record in items.items():
        task_id = record.get("task_id")
        if not task_id:
            continue
        recovery = record.get("recovery") or {}
        attempts = int(recovery.get("attempts") or 0)
        if attempts >= 3:
            continue
        last = recovery.get("last_attempt_at")
        if last:
            try:
                if (now - datetime.fromisoformat(str(last).replace("Z", "+00:00"))).total_seconds() < 900:
                    continue
            except ValueError:
                pass
        if dry_run:
            return {"stable_item_key": key, "task_id": task_id, "outcome": "would_recover_one"}
        subtasks = api("GET", f"/subtasks?task_id={task_id}", token).get("items") or []
        candidates = [item for item in subtasks if item.get("owner") == "L1" and item.get("state") == "blocked"]
        if not candidates:
            continue
        # The preparation subtask is normally the latest L1 blocked unit; it
        # carries the same task-bound exact-email contract as the parent.
        subtask = candidates[-1]
        attempt = attempts + 1
        result = api("POST", "/task-intake/execute", token, {
            "task_id": task_id,
            "subtask_id": subtask["id"],
            "idempotency_key": f"email-reply-recovery:{key}:{attempt}",
        }, allow_error=True)
        record["recovery"] = {
            "attempts": attempt,
            "last_attempt_at": utc_now(),
            "last_subtask_id": subtask["id"],
            "last_outcome": result.get("status") or result.get("error", {}).get("code") or "unknown",
        }
        return {"stable_item_key": key, "task_id": task_id, "subtask_id": subtask["id"], "result": result}
    return None


def sync_task_destination_receipt(record: dict, *, ledger_root: Path = WORKSPACE / "memory") -> bool:
    """Mark an existing task route verified only after the gateway returned its task tree.

    The task destination is the durable task-system object, not an unsent email
    draft. Unknown/legacy source keys are deliberately ignored.
    """
    stable = str(record.get("stable_item_key") or "")
    parts = stable.split(":", 3)
    if len(parts) != 4 or not record.get("task_id"):
        return False
    surface, _kind, thread_key, source_id = parts
    try:
        event_id = canonical_event_id(surface=surface, provider_event_id=source_id, provider_conversation_id=thread_key)
    except ValueError:
        return False
    try:
        known = {json.loads(line).get("event_id") for line in (ledger_root / "intake-events.jsonl").read_text().splitlines() if line.strip()}
    except (OSError, json.JSONDecodeError):
        return False
    if event_id not in known:
        return False
    record_receipt({
        "event_id": event_id, "route": "task", "state": "verified", "owner": "email-reply-task-handoff",
        "evidence_ref": stable, "destination_ref": f"task:{record['task_id']}", "error_code": None,
        "next_review_at": None,
    }, root=ledger_root)
    return True


def write_report(created: list[dict], skipped: list[str], dry_run: bool, recovery: dict | None = None) -> None:
    lines = [
        "# Email Reply Task Handoff",
        f"_Generated: {utc_now()}_",
        f"_Mode: {'dry-run' if dry_run else 'execute'}_",
        "",
        "## Created / proposed",
    ]
    if created:
        for item in created:
            lines.append(f"- `{item['stable_item_key']}` → task `{item.get('task_id', 'dry-run')}`, prep `{item.get('prep_subtask_id', 'dry-run')}`, Tom review `{item.get('review_subtask_id', 'dry-run')}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Skipped (idempotent)"])
    lines.extend(f"- `{key}`" for key in skipped) if skipped else lines.append("- None")
    lines.extend(["", "## Recovery"])
    lines.append(f"- `{recovery.get('stable_item_key')}` → `{recovery.get('result', {}).get('status') or recovery.get('outcome') or recovery.get('result', {}).get('error', {}).get('code')}`" if recovery else "- None")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Create task-system work; default is dry-run")
    parser.add_argument("--objective-id", default=os.environ.get("EMAIL_REPLY_TASK_OBJECTIVE_ID", DEFAULT_OBJECTIVE_ID))
    args = parser.parse_args()

    payload = load_json(EVENTS_PATH, {})
    # inbound-monitoring writes classified, newly routed records as `items`.
    # Fall back to `events` only for older/canonical producer shapes.
    events = payload.get("items", payload.get("events", payload if isinstance(payload, list) else []))
    state = load_json(STATE_PATH, {"version": 1, "items": {}})
    items = state.setdefault("items", {})
    created: list[dict] = []
    skipped: list[str] = []
    token = bearer_token() if args.execute else ""

    for event in event_candidates(events):
        key = event["stable_item_key"]
        if key in items:
            skipped.append(key)
            continue
        record = {"stable_item_key": key, "seen_at": utc_now(), "mode": "execute" if args.execute else "dry-run"}
        if args.execute:
            task_id, prep_id, review_id, draft_result = create_reply_prep(event, token, args.objective_id)
            record.update({"task_id": task_id, "prep_subtask_id": prep_id, "review_subtask_id": review_id, "draft_result": draft_result, "created_at": utc_now()})
            items[key] = record
            save_json(STATE_PATH, state)
            sync_task_destination_receipt(record)
        created.append(record)

    recovery = recover_one_retryable_draft(items, token, dry_run=not args.execute)
    if args.execute and recovery:
        save_json(STATE_PATH, state)
    write_report(created, skipped, dry_run=not args.execute, recovery=recovery)
    print(json.dumps({"ok": True, "mode": "execute" if args.execute else "dry-run", "created": created, "skipped": skipped, "recovery": recovery}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
