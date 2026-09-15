#!/usr/bin/env python3
"""Adapt LinkedIn message snapshots into canonical mirror events and proposal state.

This script is deliberately read-only with respect to LinkedIn and CRM/SharePoint.
It consumes the local snapshot written by capture_linkedin_messages.py, emits
canonical mirror events, maintains a small seen-state for baseline/only-new, and
writes review proposals for consequential items. It does not send LinkedIn
messages and does not write CRM/SharePoint directly.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

WORKSPACE = Path("/home/tomdean88/.openclaw/workspace")
DEFAULT_SNAPSHOT = WORKSPACE / "memory" / "linkedin-messages.json"
DEFAULT_EVENTS_OUT = WORKSPACE / "memory" / "linkedin-mirror-events.json"
DEFAULT_STATE = WORKSPACE / "memory" / "linkedin-mirror-state.json"
DEFAULT_PROPOSALS = WORKSPACE / "memory" / "linkedin-crm-proposals.json"
DEFAULT_PROPOSALS_MD = WORKSPACE / "LINKEDIN_CRM_PROPOSALS.md"
MIRROR_ROUTER = WORKSPACE / "scripts" / "mirror_router.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def load_router():
    spec = importlib.util.spec_from_file_location("mirror_router", MIRROR_ROUTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load mirror_router from {MIRROR_ROUTER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["mirror_router"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def participant_names(thread: dict[str, Any]) -> list[str]:
    names = []
    for participant in thread.get("participants") or []:
        name = str(participant.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def source_id_for(thread: dict[str, Any], message: dict[str, Any]) -> str:
    if message.get("message_key"):
        return str(message["message_key"])
    basis = "|".join(
        str(part or "")
        for part in [
            thread.get("thread_key"),
            thread.get("thread_url"),
            message.get("timestamp"),
            message.get("timestamp_text"),
            message.get("sender"),
            message.get("body_hash"),
            message.get("body_preview"),
        ]
    )
    return f"linkedin:{stable_hash(basis)}"


def snapshot_to_events(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    coverage_state = str(snapshot.get("coverage_state") or "unknown")
    generated_at = snapshot.get("generated_at")
    events: list[dict[str, Any]] = []
    for thread in snapshot.get("threads") or []:
        names = participant_names(thread)
        participants = ["Tom Dean", *names]
        messages = thread.get("messages") or []
        if not messages and thread.get("latest_preview"):
            messages = [{
                "message_key": None,
                "timestamp": thread.get("latest_timestamp"),
                "timestamp_text": thread.get("latest_timestamp_text"),
                "direction": thread.get("latest_direction") or "unknown",
                "sender": names[0] if names else "unknown",
                "body_preview": thread.get("latest_preview") or "",
                "body_hash": None,
                "raw_evidence_ref": f"memory/linkedin-messages.json#thread_key={thread.get('thread_key')}",
            }]
        for message in messages:
            body_preview = str(message.get("body_preview") or thread.get("latest_preview") or "")
            source_id = source_id_for(thread, message)
            sender = str(message.get("sender") or (names[0] if names else "unknown"))
            event = {
                "surface": "linkedin_messages",
                "source_type": "linkedin_message",
                "source_timestamp": message.get("timestamp") or thread.get("latest_timestamp") or generated_at,
                "direction": str(message.get("direction") or thread.get("latest_direction") or "unknown"),
                "sender": sender,
                "participants": participants,
                "thread_key": thread.get("thread_key"),
                "source_id": source_id,
                "subject_or_location": "LinkedIn DM",
                "body_preview": body_preview,
                "raw_evidence_ref": message.get("raw_evidence_ref") or f"memory/linkedin-messages.json#thread_key={thread.get('thread_key')}",
                "trust_class": "external_social_message",
                "coverage_state": coverage_state,
                "metadata": {
                    "thread_url": thread.get("thread_url"),
                    "timestamp_text": message.get("timestamp_text") or thread.get("latest_timestamp_text"),
                    "body_hash": message.get("body_hash"),
                    "capture_generated_at": generated_at,
                },
            }
            events.append(event)
    return events


def load_seen(path: Path) -> set[str]:
    payload = read_json(path, {"seen_item_keys": []})
    return set(payload.get("seen_item_keys") or [])


def write_seen(path: Path, seen: Iterable[str], *, mode: str, event_count: int) -> None:
    write_json(path, {
        "updated_at": utc_now(),
        "mode": mode,
        "event_count": event_count,
        "seen_item_keys": sorted(set(seen)),
    })


def proposals_to_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# LINKEDIN_CRM_PROPOSALS.md",
        "",
        f"_Generated: {payload.get('generated_at')}_",
        "",
        f"- Mode: `{payload.get('mode')}`",
        f"- Coverage state: `{payload.get('coverage_state')}`",
        f"- Events assessed: {payload.get('event_count', 0)}",
        f"- New events assessed: {payload.get('new_event_count', 0)}",
        f"- Proposals: {len(payload.get('proposals') or [])}",
        "",
    ]
    if payload.get("coverage_state") in {"login_required", "blocked", "coverage_incomplete", "incomplete"}:
        blocker = payload.get("blocker") or "coverage incomplete"
        lines.extend([f"Coverage is not clean: {blocker}", ""])
    proposals = payload.get("proposals") or []
    if not proposals:
        lines.extend(["No LinkedIn CRM/follow-up proposals in this pass.", ""])
        return "\n".join(lines)
    lines.extend(["## Review proposals", ""])
    for proposal in proposals:
        lines.append(f"### {proposal.get('sender') or 'Unknown sender'}")
        lines.append(f"- Routing flags: `{', '.join(proposal.get('routing_flags') or [])}`")
        if proposal.get("candidate_entities"):
            lines.append(f"- Candidate entities: {', '.join(proposal.get('candidate_entities'))}")
        lines.append(f"- Preview: {proposal.get('body_preview') or ''}")
        lines.append(f"- Evidence: `{proposal.get('raw_evidence_ref')}`")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route local LinkedIn message snapshot into canonical mirror events/proposals")
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--events-out", default=str(DEFAULT_EVENTS_OUT))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--proposals-out", default=str(DEFAULT_PROPOSALS))
    parser.add_argument("--proposals-md", default=str(DEFAULT_PROPOSALS_MD))
    parser.add_argument("--baseline", action="store_true", help="Mark current visible LinkedIn events as seen without proposing them")
    parser.add_argument("--only-new", action="store_true", help="Only assess events not already in seen state")
    parser.add_argument("--write", action="store_true", help="Write outputs/state instead of printing JSON only")
    args = parser.parse_args(argv)

    snapshot_path = Path(args.snapshot)
    snapshot = read_json(snapshot_path, {})
    if not snapshot:
        result = {"ok": False, "status": "missing_snapshot", "snapshot": str(snapshot_path)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    events = snapshot_to_events(snapshot)
    router = load_router()
    entity_candidates = router.load_crm_entity_candidates()
    classified = []
    for raw in events:
        event = router.event_from_dict(raw)
        classified.append(router.classify_mirror_event(event, entity_candidates=entity_candidates))

    seen = load_seen(Path(args.state))
    event_keys = [item["stable_item_key"] for item in classified]
    new_indexes = [idx for idx, key in enumerate(event_keys) if key not in seen]
    assess_indexes = new_indexes if args.only_new or args.baseline else list(range(len(classified)))

    proposals = []
    if not args.baseline:
        for idx in assess_indexes:
            item = classified[idx]
            if item.get("management_relevance") != "needs_management":
                continue
            proposals.append({
                "created_at": utc_now(),
                "proposal_type": "linkedin_crm_follow_up_candidate",
                "status": "review_required",
                "stable_item_key": item.get("stable_item_key"),
                "surface": item.get("surface"),
                "sender": item.get("sender"),
                "thread_key": item.get("thread_key"),
                "source_id": item.get("source_id"),
                "body_preview": item.get("body_preview"),
                "raw_evidence_ref": next((e.get("raw_evidence_ref") for e in events if e.get("source_id") == item.get("source_id")), "memory/linkedin-messages.json"),
                "routing_flags": item.get("routing_flags") or [],
                "candidate_entities": item.get("candidate_entities") or [],
                "reasons": item.get("reasons") or [],
                "next_action": "Tom/L1 review; no CRM/SharePoint write-through has occurred.",
            })

    mode = "baseline" if args.baseline else "only_new" if args.only_new else "assess_all"
    payload = {
        "ok": True,
        "generated_at": utc_now(),
        "mode": mode,
        "coverage_state": snapshot.get("coverage_state"),
        "blocker": snapshot.get("blocker"),
        "event_count": len(events),
        "new_event_count": len(new_indexes),
        "events": events,
        "classified": classified,
        "proposals": proposals,
    }

    if args.write:
        write_json(Path(args.events_out), {
            "generated_at": payload["generated_at"],
            "surface": "linkedin_messages",
            "coverage_state": snapshot.get("coverage_state"),
            "items": events,
            "classified": classified,
        })
        write_json(Path(args.proposals_out), payload)
        Path(args.proposals_md).write_text(proposals_to_markdown(payload), encoding="utf-8")
        if args.baseline:
            write_seen(Path(args.state), event_keys, mode="baseline", event_count=len(event_keys))
        elif args.only_new:
            write_seen(Path(args.state), seen | set(event_keys), mode="only_new", event_count=len(event_keys))
    print(json.dumps({k: v for k, v in payload.items() if k not in {"events", "classified"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
