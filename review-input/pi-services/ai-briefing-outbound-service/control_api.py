#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from api_client import BriefingApiClient
from runner import (
    BRIEFING_COMPLETED,
    BRIEFING_FAILED,
    BRIEFING_PROCESSING,
    BRIEFING_QUEUED,
    BRIEFING_SUBMITTED,
    DEFAULT_DB,
    REMOTE_ACTIVE_STATUSES,
    Target,
    add_target,
    approve_send_pack,
    build_send_packs,
    create_run,
    import_crm_targets,
    init_db,
    mark_run_for_prepare,
    now_iso,
    poll_briefings,
    run_send_queue,
    schedule_send,
    resend_send_pack,
    submit_briefings,
    validate_send_pack,
    verify_outbound,
    watch_run,
)
from config import load_config
from crm_import import eligible_leads

HOST = "127.0.0.1"
PORT = 8766
DB_PATH = DEFAULT_DB
WORKSPACE_ROOT = Path("/home/tomdean88/.openclaw/workspace")
HANDOFF_LEDGER_PATH = WORKSPACE_ROOT / "memory" / "ai-briefing-pack-handoffs.json"
WRITEBACK_QUEUE_PATH = WORKSPACE_ROOT / "memory" / "ai-briefing-writeback-queue.json"


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _rows(table: str, where: str = "", params: tuple = ()) -> list[dict]:
    conn = _conn()
    try:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _run_items(run_id: int) -> list[dict]:
    conn = _conn()
    try:
        linked = conn.execute("SELECT 1 FROM run_targets WHERE run_id = ? LIMIT 1", (run_id,)).fetchone()
        if linked is not None:
            rows = conn.execute(
                """
                SELECT bq.*
                FROM briefing_queue bq
                JOIN run_targets rt ON rt.briefing_queue_id = bq.id
                WHERE rt.run_id = ?
                ORDER BY bq.id DESC
                """,
                (run_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM briefing_queue WHERE run_id = ? ORDER BY id DESC", (run_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _local_status_from_remote(remote_status: str) -> str:
    if remote_status == "completed":
        return BRIEFING_COMPLETED
    if remote_status in REMOTE_ACTIVE_STATUSES:
        return BRIEFING_SUBMITTED if remote_status == "queued" else BRIEFING_PROCESSING
    return BRIEFING_FAILED


def _remote_briefing_items_payload() -> dict | None:
    try:
        client = BriefingApiClient(load_config())
        response = client.list_briefings()
        payload = response.payload or {}
        if response.status_code != 200 or not payload.get("success", True):
            return None
        return payload
    except Exception:
        return None


def _remote_items_from_payload(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    for key in ("items", "jobs", "briefings", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _remote_match_key(item: dict) -> str:
    if item.get("job_id"):
        return f"job:{str(item['job_id']).strip()}"
    if item.get("external_ref"):
        return f"ext:{str(item['external_ref']).strip()}"
    company = str(item.get("company_name") or "").strip().lower()
    website = str(item.get("website_url") or "").strip().lower()
    if company or website:
        return f"cw:{company}|{website}"
    return ""


def _row_match_key(row: dict) -> str:
    if row.get("job_id"):
        return f"job:{str(row['job_id']).strip()}"
    if row.get("crm_id"):
        return f"ext:{str(row['crm_id']).strip()}"
    company = str(row.get("company_name") or "").strip().lower()
    website = str(row.get("website_url") or "").strip().lower()
    if company or website:
        return f"cw:{company}|{website}"
    return ""


def _normalise_company_name(name: str | None) -> str:
    text = (name or "").strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"\b(limited|ltd|limited\.)\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _company_variants(name: str | None) -> list[str]:
    base = _normalise_company_name(name)
    variants = {base}
    if base.endswith(" limited"):
        variants.add(base[: -len(" limited")].strip())
    if base.endswith(" ltd"):
        variants.add(base[: -len(" ltd")].strip())
    return [v for v in variants if v]


def _load_existing_handoff_ledger() -> dict:
    if not HANDOFF_LEDGER_PATH.exists():
        return {"last_updated": None, "schema_version": 1, "allowed_statuses": [], "notes": [], "packs": []}
    try:
        return json.loads(HANDOFF_LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"last_updated": None, "schema_version": 1, "allowed_statuses": [], "notes": [], "packs": []}


def _send_pack_rows_by_company() -> dict[str, list[dict]]:
    rows = _rows("send_packs")
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        key = _normalise_company_name(row.get("company_name"))
        if not key:
            continue
        grouped.setdefault(key, []).append(row)
    return grouped


def _derive_pack_status(remote_item: dict, send_pack_rows: list[dict]) -> tuple[str, int | None, str | None]:
    chosen_send_pack_id = None
    notes = []
    sent_verified_rows = [r for r in send_pack_rows if str(r.get("delivery_status") or "") == "sent_verified"]
    if sent_verified_rows:
        chosen = sent_verified_rows[0]
        chosen_send_pack_id = chosen.get("id")
        notes.append(f"Send-pack {chosen_send_pack_id} has sent_verified delivery evidence.")
        return "sent_to_client", chosen_send_pack_id, " ".join(notes)
    accepted_rows = [r for r in send_pack_rows if str(r.get("status") or "") in {"accepted", "approved-to-send"}]
    if accepted_rows:
        chosen = accepted_rows[0]
        chosen_send_pack_id = chosen.get("id")
        notes.append(f"Latest visible accepted/approved send-pack is {chosen_send_pack_id}.")
        return "approved_ready_to_send", chosen_send_pack_id, " ".join(notes)
    notes.append("No send-pack evidence visible; treat as generated and not sent.")
    return "generated_not_sent", chosen_send_pack_id, " ".join(notes)


def _build_handoff_sync_payload() -> dict:
    existing = _load_existing_handoff_ledger()
    remote_payload = _remote_briefing_items_payload() or {}
    remote_items = _remote_items_from_payload(remote_payload)
    send_pack_groups = _send_pack_rows_by_company()
    existing_by_company = {
        _normalise_company_name(entry.get("company")): entry
        for entry in existing.get("packs", [])
        if _normalise_company_name(entry.get("company"))
    }
    packs: list[dict] = []
    verified_at = now_iso()
    for item in remote_items:
        company_name = str(item.get("company_name") or "").strip()
        if not company_name:
            continue
        existing_entry = None
        for variant in _company_variants(company_name):
            existing_entry = existing_by_company.get(variant)
            if existing_entry:
                break
        send_pack_rows = []
        for variant in _company_variants(company_name):
            send_pack_rows.extend(send_pack_groups.get(variant, []))
        status, send_pack_id, derived_note = _derive_pack_status(item, send_pack_rows)
        canonical_url = item.get("report_url")
        crm_entity = existing_entry.get("crm_entity") if existing_entry else None
        pack = {
            "company": existing_entry.get("company", company_name) if existing_entry else company_name,
            "crm_entity": crm_entity,
            "briefing_id": item.get("job_id"),
            "send_pack_id": send_pack_id,
            "status": status,
            "canonical_url": canonical_url,
            "last_verified": verified_at,
            "sent_at": None,
            "notes": f"Auto-synced from website briefing list and local send-pack state on {verified_at}. {derived_note}".strip(),
        }
        packs.append(pack)
    for entry in existing.get("packs", []):
        if not entry.get("company"):
            continue
        norm = _normalise_company_name(entry.get("company"))
        if any(_normalise_company_name(p.get("company")) == norm for p in packs):
            continue
        stale = dict(entry)
        stale["last_verified"] = verified_at
        stale["notes"] = ((entry.get("notes") or "") + " Rechecked on " + verified_at + "; no matching live website briefing item currently visible.").strip()
        packs.append(stale)
    packs.sort(key=lambda p: (str(p.get("company") or "").lower(), str(p.get("canonical_url") or "")))
    return {
        "last_updated": verified_at,
        "schema_version": existing.get("schema_version", 1),
        "allowed_statuses": existing.get("allowed_statuses") or [
            "generated_not_sent",
            "approved_ready_to_send",
            "sent_to_client",
            "superseded",
            "coverage_incomplete",
        ],
        "notes": [
            "Canonical local handoff ledger between AI briefing pack generation and CRM/SharePoint current truth.",
            "Use this before searching chat history when Tom asks whether a pack exists, was sent, or what URL should be used in follow-up mail.",
            "Status is derived from live website briefing list plus local send-pack state. Do not infer sent state without explicit send evidence.",
        ],
        "packs": packs,
    }


def _write_handoff_sync_payload(payload: dict) -> None:
    HANDOFF_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    HANDOFF_LEDGER_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_writeback_queue() -> dict:
    if not WRITEBACK_QUEUE_PATH.exists():
        return {"last_updated": None, "items": []}
    try:
        return json.loads(WRITEBACK_QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"last_updated": None, "items": []}


def _load_crm_snapshot_lines() -> list[str]:
    crm_path = WORKSPACE_ROOT / "stackstone" / "crm.md"
    if not crm_path.exists():
        return []
    try:
        return crm_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []


def _crm_context_for_entity(crm_entity: str | None) -> dict:
    if not crm_entity:
        return {"entity_type": None, "company": None, "row_excerpt": None}
    lines = _load_crm_snapshot_lines()
    company = crm_entity.split("/", 1)[-1].strip() if "/" in crm_entity else crm_entity
    for line in lines:
        if line.startswith("|") and company.lower() in line.lower():
            return {
                "entity_type": crm_entity.split("/", 1)[0] if "/" in crm_entity else None,
                "company": company,
                "row_excerpt": line,
            }
    return {"entity_type": crm_entity.split("/", 1)[0] if "/" in crm_entity else None, "company": company, "row_excerpt": None}


def _writeback_destinations(entry: dict) -> list[str]:
    destinations = ["handoff_ledger"]
    if entry.get("crm_entity"):
        destinations.append("crm_summary")
        parts = str(entry.get("crm_entity") or "")
        if parts.startswith("Opportunities/") or parts.startswith("Accounts/"):
            destinations.append("sharepoint_current_truth")
    return destinations


def _build_writeback_payload() -> dict:
    handoff = _load_existing_handoff_ledger()
    verified_at = now_iso()
    items = []
    for entry in handoff.get("packs", []):
        crm_context = _crm_context_for_entity(entry.get("crm_entity"))
        items.append({
            "company": entry.get("company"),
            "crm_entity": entry.get("crm_entity"),
            "entity_type": crm_context.get("entity_type"),
            "canonical_url": entry.get("canonical_url"),
            "status": entry.get("status"),
            "send_pack_id": entry.get("send_pack_id"),
            "briefing_id": entry.get("briefing_id"),
            "last_verified": entry.get("last_verified"),
            "source_event": "ai_briefing_pack_state_refresh",
            "destinations": _writeback_destinations(entry),
            "crm_row_excerpt": crm_context.get("row_excerpt"),
            "llm_context_packet": {
                "company": entry.get("company"),
                "crm_entity": entry.get("crm_entity"),
                "status": entry.get("status"),
                "canonical_url": entry.get("canonical_url"),
                "last_verified": entry.get("last_verified"),
                "notes": entry.get("notes"),
                "required_writeback_rule": "Update CRM summary and, where commercially meaningful, SharePoint Current.md to reflect pack existence, state, canonical URL, and last verified date without overstating sent status.",
            },
        })
    return {
        "last_updated": verified_at,
        "items": items,
        "notes": [
            "Automatic initiation layer for AI briefing pack write-back.",
            "This queue is intended for LLM-authored CRM/SharePoint narrative updates, not blind line-by-line hard-coded text writes.",
            "Generation of this queue is deterministic; narrative application remains a separate writing/reconciliation step.",
        ],
    }


def _write_writeback_payload(payload: dict) -> None:
    WRITEBACK_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    WRITEBACK_QUEUE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sync_local_briefings_with_remote(payload: dict | None) -> None:
    remote_items = _remote_items_from_payload(payload)
    if not remote_items:
        return
    remote_map = {key: item for item in remote_items if (key := _remote_match_key(item))}
    conn = _conn()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM briefing_queue ORDER BY id DESC").fetchall()]
        for row in rows:
            key = _row_match_key(row)
            remote = remote_map.get(key)
            if not remote:
                continue
            remote_status = str(remote.get("status") or row.get("remote_status") or "").strip()
            if not remote_status:
                continue
            conn.execute(
                "UPDATE briefing_queue SET status = ?, remote_status = ?, batch_id = COALESCE(?, batch_id), report_url = COALESCE(?, report_url), completed_at = COALESCE(?, completed_at), pack_created_at = COALESCE(?, pack_created_at), last_polled_at = ?, error_message = CASE WHEN ? = ? THEN NULL ELSE error_message END WHERE id = ?",
                (
                    _local_status_from_remote(remote_status),
                    remote_status,
                    remote.get("batch_id"),
                    remote.get("report_url"),
                    remote.get("completed_at"),
                    remote.get("pack_created_at"),
                    now_iso(),
                    remote_status,
                    "completed",
                    row["id"],
                ),
            )
    finally:
        conn.close()


def _merged_run_rows(run_id: int, payload: dict | None) -> list[dict]:
    rows = _run_items(run_id)
    remote_items = _remote_items_from_payload(payload)
    remote_map = {key: item for item in remote_items if (key := _remote_match_key(item))}
    merged = []
    for row in rows:
        merged_row = dict(row)
        remote = remote_map.get(_row_match_key(merged_row))
        if remote:
            remote_status = str(remote.get("status") or merged_row.get("remote_status") or "").strip()
            if remote_status:
                merged_row["remote_status"] = remote_status
                merged_row["status"] = _local_status_from_remote(remote_status)
            for key in ("report_url", "completed_at", "pack_created_at", "batch_id", "job_id"):
                if remote.get(key):
                    merged_row[key] = remote.get(key)
        merged.append(merged_row)
    return merged


def _run_summary_payload(run_id: int) -> dict:
    remote_payload = _remote_briefing_items_payload()
    _sync_local_briefings_with_remote(remote_payload)
    conn = _conn()
    try:
        run = conn.execute("SELECT * FROM batch_runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        run_dict = dict(run)
        if run_dict.get("last_summary_json"):
            try:
                last_summary = json.loads(run_dict["last_summary_json"])
                if isinstance(last_summary, dict) and "summary" in last_summary:
                    run_dict["last_summary"] = last_summary["summary"]
            except Exception:
                pass
        run_dict.pop("last_summary_json", None)
        rows = _merged_run_rows(run_id, remote_payload)
        total = len(rows)
        queued = sum(1 for row in rows if row["status"] == BRIEFING_QUEUED)
        active = sum(1 for row in rows if row["status"] in (BRIEFING_SUBMITTED, BRIEFING_PROCESSING))
        completed = sum(1 for row in rows if row["status"] == BRIEFING_COMPLETED)
        failed = sum(1 for row in rows if row["status"] == BRIEFING_FAILED)
        terminal = queued == 0 and active == 0
        payload = {
            "run": run_dict,
            "summary": {
                "total": total,
                "queued": queued,
                "active": active,
                "completed": completed,
                "failed": failed,
                "terminal": terminal,
            },
        }
        if remote_payload:
            if "summary" in remote_payload and isinstance(remote_payload["summary"], dict):
                payload["website_summary"] = remote_payload["summary"]
            if remote_payload.get("as_of"):
                payload["as_of"] = remote_payload["as_of"]
        return payload
    finally:
        conn.close()


def _send_pack_review_card(send_pack_id: int) -> dict:
    conn = _conn()
    try:
        sp = conn.execute("SELECT * FROM send_packs WHERE id = ?", (send_pack_id,)).fetchone()
        if sp is None:
            raise ValueError(f"Send-pack not found: {send_pack_id}")
        bq = conn.execute("SELECT * FROM briefing_queue WHERE id = ?", (sp["briefing_queue_id"],)).fetchone()
        if bq is None:
            raise ValueError(f"Briefing queue item not found for send-pack: {send_pack_id}")
        return {
            "send_pack_id": sp["id"],
            "crm_id": sp["crm_id"],
            "briefing_queue_id": sp["briefing_queue_id"],
            "job_id": bq["job_id"],
            "company_name": sp["company_name"],
            "contact_name": sp["contact_name"],
            "contact_email": sp["contact_email"],
            "report_url": sp["report_url"],
            "validation_status": sp["validation_status"],
            "validation_errors": sp["validation_errors"],
            "signature_present": bool(sp["signature_present"]),
            "status": sp["status"],
            "remote_status": bq["remote_status"],
            "batch_id": bq["batch_id"],
        }
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/health":
                _json(self, 200, {"ok": True, "service": "ai-briefing-outbound-service"})
                return
            if path == "/briefings":
                run_id = qs.get("run_id", [None])[0]
                remote_payload = _remote_briefing_items_payload()
                _sync_local_briefings_with_remote(remote_payload)
                if run_id is not None:
                    items = _merged_run_rows(int(run_id), remote_payload)
                    payload = {"items": items}
                    if remote_payload and isinstance(remote_payload.get("summary"), dict):
                        payload["website_summary"] = remote_payload["summary"]
                    if remote_payload and remote_payload.get("as_of"):
                        payload["as_of"] = remote_payload["as_of"]
                    _json(self, 200, payload)
                else:
                    if remote_payload:
                        payload = dict(remote_payload)
                        payload["items"] = _remote_items_from_payload(remote_payload)
                        if "summary" not in payload and "count" in payload:
                            payload["summary"] = {"total": payload.get("count")}
                    else:
                        payload = {"items": _rows("briefing_queue")}
                    if "items" not in payload:
                        payload["items"] = _rows("briefing_queue")
                    _json(self, 200, payload)
                return
            if path == "/send-packs":
                _json(self, 200, {"items": _rows("send_packs")})
                return
            if path == "/handoff/preview":
                _json(self, 200, _build_handoff_sync_payload())
                return
            if path == "/writeback/preview":
                _json(self, 200, _build_writeback_payload())
                return
            if path.startswith("/send-packs/") and path.endswith("/review-card"):
                send_pack_id = int(path.split("/")[2])
                _json(self, 200, {"item": _send_pack_review_card(send_pack_id)})
                return
            if path == "/outbound":
                _json(self, 200, {"items": _rows("outbound_queue")})
                return
            if path == "/runs":
                _json(self, 200, {"items": _rows("batch_runs")})
                return
            if path.startswith("/runs/") and path.endswith("/summary"):
                run_id = int(path.split("/")[2])
                _json(self, 200, _run_summary_payload(run_id))
                return
            if path == "/crm/preview":
                config = load_config()
                limit = int((qs.get("limit") or [config.default_crm_import_limit])[0])
                leads = [lead.__dict__ for lead in eligible_leads(limit=limit)]
                _json(self, 200, {"items": leads})
                return
            _json(self, 404, {"ok": False, "error": "not found"})
        except BaseException as e:
            _json(self, 400, {"ok": False, "error": str(e)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = _read_json(self)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/init-db":
                init_db(DB_PATH)
                _json(self, 200, {"ok": True})
                return
            if path == "/runs/create":
                create_run(DB_PATH, body["name"], body.get("mode", "generate_only"), body.get("notes"))
                latest = _rows("batch_runs")[0]
                _json(self, 200, {"ok": True, "run": latest})
                return
            if path == "/runs/summary":
                payload = _run_summary_payload(int(body["run_id"]))
                _json(self, 200, payload)
                return
            if path == "/runs/mark-for-prepare":
                run_id = int(body["run_id"])
                mark_run_for_prepare(DB_PATH, run_id)
                _json(self, 200, {"ok": True, **_run_summary_payload(run_id)})
                return
            if path == "/runs/watch":
                run_id = int(body["run_id"])
                watch_run(DB_PATH, run_id)
                _json(self, 200, {"ok": True, **_run_summary_payload(run_id)})
                return
            if path == "/targets/add":
                target = Target(
                    crm_id=body["crm_id"],
                    company_name=body["company_name"],
                    website_url=body["website_url"],
                    contact_name=body.get("contact_name"),
                    contact_email=body["contact_email"],
                    campaign_segment=body.get("campaign_segment"),
                    force_regenerate=bool(body.get("force_regenerate", False)),
                    run_id=body.get("run_id"),
                    post_generation_action=body.get("post_generation_action", "generate_only"),
                )
                add_target(DB_PATH, target)
                _json(self, 200, {"ok": True, "items": _rows("briefing_queue", "crm_id = ?", (target.crm_id,))})
                return
            if path == "/crm/import":
                config = load_config()
                run_id = body.get("run_id")
                import_crm_targets(
                    DB_PATH,
                    limit=int(body.get("limit", config.default_crm_import_limit)),
                    force_regenerate=bool(body.get("force_regenerate", False)),
                    run_id=run_id,
                    post_generation_action=body.get("post_generation_action", "generate_only"),
                )
                payload = {"ok": True}
                if run_id is not None:
                    payload.update(_run_summary_payload(int(run_id)))
                _json(self, 200, payload)
                return
            if path == "/briefings/submit":
                run_id = body.get("run_id")
                submit_briefings(DB_PATH, run_id=run_id)
                payload = {"ok": True}
                if run_id is not None:
                    payload.update(_run_summary_payload(int(run_id)))
                else:
                    payload["items"] = _rows("briefing_queue")[:10]
                _json(self, 200, payload)
                return
            if path == "/briefings/poll":
                run_id = body.get("run_id")
                poll_briefings(DB_PATH, once=bool(body.get("once", True)), run_id=run_id, until_run_complete=bool(body.get("until_run_complete", False)))
                payload = {"ok": True}
                if run_id is not None:
                    payload.update(_run_summary_payload(int(run_id)))
                else:
                    payload["items"] = _rows("briefing_queue")[:10]
                _json(self, 200, payload)
                return
            if path == "/send-packs/build":
                run_id = body.get("run_id")
                build_send_packs(DB_PATH, run_id=run_id, include_generate_only=bool(body.get("include_generate_only", False)))
                if run_id is not None:
                    conn = _conn()
                    try:
                        linked = conn.execute("SELECT 1 FROM run_targets WHERE run_id = ? LIMIT 1", (int(run_id),)).fetchone()
                        if linked is not None:
                            rows = [dict(r) for r in conn.execute(
                                "SELECT sp.* FROM send_packs sp JOIN run_targets rt ON sp.briefing_queue_id = rt.briefing_queue_id WHERE rt.run_id = ? ORDER BY sp.id DESC",
                                (int(run_id),),
                            ).fetchall()]
                        else:
                            rows = [dict(r) for r in conn.execute(
                                "SELECT sp.* FROM send_packs sp JOIN briefing_queue bq ON sp.briefing_queue_id = bq.id WHERE bq.run_id = ? ORDER BY sp.id DESC",
                                (int(run_id),),
                            ).fetchall()]
                    finally:
                        conn.close()
                    _json(self, 200, {"ok": True, "items": rows})
                else:
                    _json(self, 200, {"ok": True, "items": _rows("send_packs")[:10]})
                return
            if path == "/send-packs/validate":
                payload = validate_send_pack(DB_PATH, int(body["send_pack_id"]), persist=True)
                _json(self, 200, {"ok": True, "item": payload})
                return
            if path == "/outbound/verify":
                verify_outbound(DB_PATH, int(body["send_pack_id"]))
                _json(self, 200, {"ok": True, "items": _rows("outbound_queue")[:10]})
                return
            if path == "/send-packs/approve":
                send_pack_id = int(body["send_pack_id"])
                approve_send_pack(DB_PATH, send_pack_id)
                _json(self, 200, {"ok": True, "item": _send_pack_review_card(send_pack_id)})
                return
            if path == "/outbound/schedule":
                send_pack_id = int(body["send_pack_id"])
                schedule_send(DB_PATH, send_pack_id, body["scheduled_send_at"])
                conn = _conn()
                try:
                    out = conn.execute("SELECT * FROM outbound_queue WHERE send_pack_id = ? ORDER BY id DESC LIMIT 1", (send_pack_id,)).fetchone()
                    payload = {"ok": True, "item": dict(out) if out else None}
                finally:
                    conn.close()
                _json(self, 200, payload)
                return
            if path == "/send-packs/resend":
                send_pack_id = int(body["send_pack_id"])
                resend_send_pack(DB_PATH, send_pack_id, body.get("recipient_override"), body.get("scheduled_send_at"))
                conn = _conn()
                try:
                    out = conn.execute("SELECT * FROM outbound_queue WHERE send_pack_id = ? ORDER BY id DESC LIMIT 1", (send_pack_id,)).fetchone()
                    payload = {"ok": True, "item": dict(out) if out else None}
                finally:
                    conn.close()
                _json(self, 200, payload)
                return
            if path == "/handoff/sync":
                payload = _build_handoff_sync_payload()
                _write_handoff_sync_payload(payload)
                _json(self, 200, {"ok": True, **payload})
                return
            if path == "/writeback/enqueue":
                payload = _build_writeback_payload()
                _write_writeback_payload(payload)
                _json(self, 200, {"ok": True, **payload})
                return
            if path == "/outbound/run":
                run_send_queue(DB_PATH, execute=bool(body.get("execute", False)), limit=int(body.get("limit", 10)))
                _json(self, 200, {"ok": True, "items": _rows("outbound_queue")[:10]})
                return
            _json(self, 404, {"ok": False, "error": "not found"})
        except BaseException as e:
            _json(self, 400, {"ok": False, "error": str(e)})

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"AI Briefing Outbound Service control API listening on http://{HOST}:{PORT}")
    server.serve_forever()
