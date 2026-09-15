#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from api_client import BriefingApiClient
from config import load_config
from crm_import import eligible_leads
from send_queue import (
    append_email_log,
    build_send_command,
    due_now,
    execute_send_command,
    extract_provider_message_id,
    verify_from_sent_surfaces,
)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = PROJECT_ROOT / "outbound.db"
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "outbound_email.txt"
SIGNATURE_PATH = PROJECT_ROOT / "templates" / "signature.txt"
SUBMIT_LOG_PATH = PROJECT_ROOT / "submit-debug.jsonl"

BRIEFING_QUEUED = "queued-for-briefing"
BRIEFING_SUBMITTED = "submitted"
BRIEFING_PROCESSING = "processing"
BRIEFING_COMPLETED = "completed"
BRIEFING_FAILED = "failed"
SEND_DRAFT = "draft-pending-review"
SEND_APPROVED = "approved-to-send"
SEND_ACCEPTED = "accepted"
SEND_SENT_VERIFIED = "sent_verified"
SEND_VERIFICATION_FAILED = "verification_failed"
SEND_FAILED = "send-failed"
OUTBOUND_SCHEDULED = "scheduled"
OUTBOUND_SENDING = "sending"
OUTBOUND_ACCEPTED = "accepted"
OUTBOUND_SENT_VERIFIED = "sent_verified"
OUTBOUND_VERIFICATION_FAILED = "verification_failed"
OUTBOUND_FAILED = "failed"
MODE_GENERATE_ONLY = "generate_only"
MODE_GENERATE_AND_PREPARE = "generate_and_prepare"
VALID_OK = "valid"
VALID_FAIL = "invalid"
VALID_PENDING = "pending"
RUN_DRAFT = "draft"
RUN_SUBMITTED = "submitted"
RUN_WATCHING = "watching"
RUN_COMPLETED = "completed"
RUN_COMPLETED_WITH_FAILURES = "completed_with_failures"

REMOTE_ACTIVE_STATUSES = {
    "queued",
    "processing",
    "preparing_context",
    "ready_for_batch",
    "submitted_to_batch",
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_submit_log(entry: dict) -> None:
    with SUBMIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": now_iso(), **entry}, ensure_ascii=False) + "\n")


def ensure_runtime_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          mode TEXT NOT NULL DEFAULT 'generate_only',
          state TEXT NOT NULL DEFAULT 'draft',
          created_at TEXT NOT NULL,
          notes TEXT,
          watch_started_at TEXT,
          watch_finished_at TEXT,
          last_summary_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_targets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id INTEGER NOT NULL,
          briefing_queue_id INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY (run_id) REFERENCES batch_runs(id) ON DELETE CASCADE,
          FOREIGN KEY (briefing_queue_id) REFERENCES briefing_queue(id) ON DELETE CASCADE,
          UNIQUE (run_id, briefing_queue_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS outbound_attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          send_pack_id INTEGER NOT NULL,
          outbound_queue_id INTEGER,
          attempt_number INTEGER NOT NULL,
          archived_at TEXT NOT NULL,
          archive_reason TEXT,
          contact_email TEXT NOT NULL,
          email_subject TEXT NOT NULL,
          email_body TEXT NOT NULL,
          report_url TEXT NOT NULL,
          scheduled_send_at TEXT,
          status TEXT NOT NULL,
          provider_message_id TEXT,
          verification_notes TEXT,
          created_at TEXT,
          sent_at TEXT,
          error_message TEXT,
          FOREIGN KEY (send_pack_id) REFERENCES send_packs(id) ON DELETE CASCADE
        )
        """
    )
    existing_runs = {row[1] for row in conn.execute("PRAGMA table_info(batch_runs)").fetchall()}
    for col, ddl in [
        ("state", "ALTER TABLE batch_runs ADD COLUMN state TEXT NOT NULL DEFAULT 'draft'"),
        ("watch_started_at", "ALTER TABLE batch_runs ADD COLUMN watch_started_at TEXT"),
        ("watch_finished_at", "ALTER TABLE batch_runs ADD COLUMN watch_finished_at TEXT"),
        ("last_summary_json", "ALTER TABLE batch_runs ADD COLUMN last_summary_json TEXT"),
    ]:
        if col not in existing_runs:
            conn.execute(ddl)

    existing_bq = {row[1] for row in conn.execute("PRAGMA table_info(briefing_queue)").fetchall()}
    for col, ddl in [
        ("run_id", "ALTER TABLE briefing_queue ADD COLUMN run_id INTEGER"),
        ("post_generation_action", "ALTER TABLE briefing_queue ADD COLUMN post_generation_action TEXT NOT NULL DEFAULT 'generate_only'"),
        ("remote_status", "ALTER TABLE briefing_queue ADD COLUMN remote_status TEXT"),
        ("batch_id", "ALTER TABLE briefing_queue ADD COLUMN batch_id TEXT"),
        ("last_polled_at", "ALTER TABLE briefing_queue ADD COLUMN last_polled_at TEXT"),
    ]:
        if col not in existing_bq:
            conn.execute(ddl)

    existing_sp = {row[1] for row in conn.execute("PRAGMA table_info(send_packs)").fetchall()}
    for col, ddl in [
        ("validation_status", "ALTER TABLE send_packs ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'pending'"),
        ("validation_errors", "ALTER TABLE send_packs ADD COLUMN validation_errors TEXT"),
        ("signature_present", "ALTER TABLE send_packs ADD COLUMN signature_present INTEGER NOT NULL DEFAULT 0"),
        ("delivery_status", "ALTER TABLE send_packs ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'pending'"),
        ("provider_message_id", "ALTER TABLE send_packs ADD COLUMN provider_message_id TEXT"),
        ("verification_notes", "ALTER TABLE send_packs ADD COLUMN verification_notes TEXT"),
    ]:
        if col not in existing_sp:
            conn.execute(ddl)

    existing_oq = {row[1] for row in conn.execute("PRAGMA table_info(outbound_queue)").fetchall()}
    for col, ddl in [
        ("provider_message_id", "ALTER TABLE outbound_queue ADD COLUMN provider_message_id TEXT"),
        ("verification_notes", "ALTER TABLE outbound_queue ADD COLUMN verification_notes TEXT"),
    ]:
        if col not in existing_oq:
            conn.execute(ddl)


def get_conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    ensure_runtime_schema(conn)
    return conn


def init_db(db_path: Path) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn(db_path) as conn:
        conn.executescript(schema)
        ensure_runtime_schema(conn)
    print(f"Initialised database: {db_path}")


@dataclass
class Target:
    crm_id: str
    company_name: str
    website_url: str
    contact_name: str | None
    contact_email: str
    campaign_segment: str | None
    force_regenerate: bool = False
    run_id: int | None = None
    post_generation_action: str = MODE_GENERATE_ONLY


def _normalise_mode(mode: str) -> str:
    if mode not in {MODE_GENERATE_ONLY, MODE_GENERATE_AND_PREPARE}:
        raise SystemExit(f"Invalid mode: {mode}")
    return mode


def load_signature() -> str:
    return SIGNATURE_PATH.read_text(encoding="utf-8").strip()


def append_signature(body: str) -> tuple[str, bool]:
    signature = load_signature()
    if signature in body:
        return body, True
    return body.rstrip() + "\n\n" + signature + "\n", True


def _run_has_target_links(conn: sqlite3.Connection, run_id: int) -> bool:
    row = conn.execute("SELECT 1 FROM run_targets WHERE run_id = ? LIMIT 1", (run_id,)).fetchone()
    return row is not None


def _run_target_rows(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    if _run_has_target_links(conn, run_id):
        return conn.execute(
            """
            SELECT bq.*
            FROM briefing_queue bq
            JOIN run_targets rt ON rt.briefing_queue_id = bq.id
            WHERE rt.run_id = ?
            ORDER BY bq.id DESC
            """,
            (run_id,),
        ).fetchall()
    return conn.execute("SELECT * FROM briefing_queue WHERE run_id = ? ORDER BY id DESC", (run_id,)).fetchall()


def _run_summary_dict(conn: sqlite3.Connection, run_id: int) -> dict:
    run = conn.execute("SELECT * FROM batch_runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        raise SystemExit(f"Run not found: {run_id}")
    run_dict = dict(run)
    if run_dict.get("last_summary_json"):
        try:
            last_summary = json.loads(run_dict["last_summary_json"])
            if isinstance(last_summary, dict) and "summary" in last_summary:
                run_dict["last_summary"] = last_summary["summary"]
        except Exception:
            pass
    run_dict.pop("last_summary_json", None)
    rows = _run_target_rows(conn, run_id)
    total = len(rows)
    queued = sum(1 for row in rows if row["status"] == BRIEFING_QUEUED)
    active = sum(1 for row in rows if row["status"] in (BRIEFING_SUBMITTED, BRIEFING_PROCESSING))
    completed = sum(1 for row in rows if row["status"] == BRIEFING_COMPLETED)
    failed = sum(1 for row in rows if row["status"] == BRIEFING_FAILED)
    terminal = queued == 0 and active == 0
    return {"run": run_dict, "summary": {"total": total, "queued": queued, "active": active, "completed": completed, "failed": failed, "terminal": terminal}}


def _persist_run_summary(conn: sqlite3.Connection, run_id: int) -> dict:
    payload = _run_summary_dict(conn, run_id)
    summary = payload["summary"]
    if summary["terminal"]:
        state = RUN_COMPLETED_WITH_FAILURES if summary["failed"] > 0 else RUN_COMPLETED
        conn.execute("UPDATE batch_runs SET state = ?, watch_finished_at = ?, last_summary_json = ? WHERE id = ?", (state, now_iso(), json.dumps(payload), run_id))
    else:
        conn.execute("UPDATE batch_runs SET last_summary_json = ? WHERE id = ?", (json.dumps(payload), run_id))
    return payload


def create_run(db_path: Path, name: str, mode: str = MODE_GENERATE_ONLY, notes: str | None = None) -> None:
    mode = _normalise_mode(mode)
    with get_conn(db_path) as conn:
        cur = conn.execute("INSERT INTO batch_runs (name, mode, state, created_at, notes) VALUES (?, ?, ?, ?, ?)", (name, mode, RUN_DRAFT, now_iso(), notes))
        run_id = cur.lastrowid
    print({"run_id": run_id, "name": name, "mode": mode, "state": RUN_DRAFT})


def list_runs(db_path: Path) -> None:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM batch_runs ORDER BY id DESC").fetchall()
    print("No batch runs" if not rows else "\n".join(str(dict(r)) for r in rows))


def run_summary(db_path: Path, run_id: int) -> None:
    with get_conn(db_path) as conn:
        print(_run_summary_dict(conn, run_id))


def add_target(db_path: Path, target: Target) -> None:
    with get_conn(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO briefing_queue (run_id, crm_id, company_name, website_url, contact_name, contact_email, campaign_segment, post_generation_action, force_regenerate, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (target.run_id, target.crm_id, target.company_name, target.website_url, target.contact_name, target.contact_email, target.campaign_segment, target.post_generation_action, 1 if target.force_regenerate else 0, BRIEFING_QUEUED, now_iso()))
        row = conn.execute(
            "SELECT * FROM briefing_queue WHERE crm_id = ? AND website_url = ? AND contact_email = ? ORDER BY id DESC LIMIT 1",
            (target.crm_id, target.website_url, target.contact_email),
        ).fetchone()
        if row is None:
            raise SystemExit(f"Failed to queue target: {target.company_name}")
        # If this target already exists from an older run, re-queue it cleanly for the new run.
        if row["status"] != BRIEFING_QUEUED or row["job_id"] or row["remote_status"] or row["report_url"] or row["error_message"]:
            conn.execute(
                "UPDATE briefing_queue SET run_id = ?, company_name = ?, website_url = ?, contact_name = ?, contact_email = ?, campaign_segment = ?, post_generation_action = ?, force_regenerate = ?, status = ?, job_id = NULL, remote_status = NULL, batch_id = NULL, last_polled_at = NULL, report_url = NULL, submitted_at = NULL, completed_at = NULL, pack_created_at = NULL, error_message = NULL WHERE id = ?",
                (target.run_id, target.company_name, target.website_url, target.contact_name, target.contact_email, target.campaign_segment, target.post_generation_action, 1 if target.force_regenerate else 0, BRIEFING_QUEUED, row["id"]),
            )
        if target.run_id is not None:
            conn.execute(
                "INSERT OR IGNORE INTO run_targets (run_id, briefing_queue_id, created_at) VALUES (?, ?, ?)",
                (target.run_id, row["id"], now_iso()),
            )
    print(f"Queued target: {target.company_name} <{target.contact_email}> run={target.run_id} mode={target.post_generation_action}")


def import_crm_targets(db_path: Path, limit: int, force_regenerate: bool = False, run_id: int | None = None, post_generation_action: str = MODE_GENERATE_ONLY) -> None:
    leads = eligible_leads(limit=limit)
    if not leads:
        print("No eligible CRM leads found")
        return
    for lead in leads:
        add_target(db_path, Target(lead.crm_id, lead.company_name, lead.website_url, lead.contact_name, lead.contact_email, lead.campaign_segment, force_regenerate, run_id, post_generation_action))
    print(f"Imported CRM targets into Queue A: {len(leads)}")


def preview_crm_targets(limit: int) -> None:
    leads = eligible_leads(limit=limit)
    print("No eligible CRM leads found" if not leads else "\n".join(str(l.__dict__) for l in leads))


def list_rows(db_path: Path, table: str) -> None:
    with get_conn(db_path) as conn:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC").fetchall()
    print(f"No rows in {table}" if not rows else "\n".join(str(dict(r)) for r in rows))


def render_template(company_name: str, contact_name: str | None, report_url: str) -> tuple[str, str]:
    raw = TEMPLATE_PATH.read_text(encoding="utf-8")
    greeting = contact_name if contact_name and contact_name.strip() else "there"
    rendered = raw.replace("{{company_name}}", company_name).replace("{{report_url}}", report_url).replace("{{contact_name_or_fallback}}", greeting)
    first, _, rest = rendered.partition("\n")
    subject = first.removeprefix("Subject: ").strip()
    body = rest.lstrip("\n")
    body, _ = append_signature(body)
    return subject, body


def _next_attempt_number(conn: sqlite3.Connection, send_pack_id: int) -> int:
    row = conn.execute("SELECT COALESCE(MAX(attempt_number), 0) AS n FROM outbound_attempts WHERE send_pack_id = ?", (send_pack_id,)).fetchone()
    return int(row["n"] if row and row["n"] is not None else 0) + 1


def _archive_existing_outbound(conn: sqlite3.Connection, send_pack_id: int, reason: str) -> None:
    rows = conn.execute("SELECT * FROM outbound_queue WHERE send_pack_id = ? ORDER BY id ASC", (send_pack_id,)).fetchall()
    if not rows:
        return
    attempt_number = _next_attempt_number(conn, send_pack_id)
    for row in rows:
        conn.execute(
            """
            INSERT INTO outbound_attempts (
              send_pack_id, outbound_queue_id, attempt_number, archived_at, archive_reason,
              contact_email, email_subject, email_body, report_url, scheduled_send_at,
              status, provider_message_id, verification_notes, created_at, sent_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                send_pack_id,
                row["id"],
                attempt_number,
                now_iso(),
                reason,
                row["contact_email"],
                row["email_subject"],
                row["email_body"],
                row["report_url"],
                row["scheduled_send_at"],
                row["status"],
                row["provider_message_id"],
                row["verification_notes"],
                row["created_at"],
                row["sent_at"],
                row["error_message"],
            ),
        )
    conn.execute("DELETE FROM outbound_queue WHERE send_pack_id = ?", (send_pack_id,))


def validate_send_pack(db_path: Path, send_pack_id: int, persist: bool = True) -> dict:
    with get_conn(db_path) as conn:
        sp = conn.execute("SELECT * FROM send_packs WHERE id = ?", (send_pack_id,)).fetchone(); bq = conn.execute("SELECT * FROM briefing_queue WHERE id = ?", (sp["briefing_queue_id"],)).fetchone() if sp else None
        if sp is None or bq is None: raise SystemExit(f"Missing send-pack or briefing row for {send_pack_id}")
        sig = load_signature(); errors=[]
        if not sp["crm_id"]: errors.append("missing crm_id")
        if not sp["briefing_queue_id"]: errors.append("missing briefing_queue_id")
        if not bq["job_id"]: errors.append("missing job_id on briefing row")
        if sp["company_name"] != bq["company_name"]: errors.append("company_name mismatch")
        if sp["contact_email"] != bq["contact_email"]: errors.append("contact_email mismatch")
        if sp["report_url"] != bq["report_url"]: errors.append("report_url mismatch")
        if bq["status"] != BRIEFING_COMPLETED: errors.append("briefing row not completed")
        if sp["report_url"] not in (sp["email_body"] or ""): errors.append("report_url missing from email body")
        if sp["company_name"] not in (sp["email_body"] or ""): errors.append("company_name missing from email body")
        if not (sp["email_body"] or "").startswith("Hi"): errors.append("greeting missing")
        if sig not in (sp["email_body"] or ""): errors.append("signature missing")
        payload={"send_pack_id":send_pack_id,"crm_id":sp["crm_id"],"briefing_queue_id":sp["briefing_queue_id"],"job_id":bq["job_id"],"company_name":sp["company_name"],"contact_email":sp["contact_email"],"report_url":sp["report_url"],"validation_status":VALID_OK if not errors else VALID_FAIL,"validation_errors":errors,"signature_present":sig in (sp["email_body"] or "")}
        if persist: conn.execute("UPDATE send_packs SET validation_status=?, validation_errors=?, signature_present=? WHERE id=?", (payload["validation_status"], json.dumps(errors), 1 if payload["signature_present"] else 0, send_pack_id))
    print(payload); return payload


def build_send_packs(db_path: Path, run_id: int | None = None, include_generate_only: bool = False) -> None:
    built=[]
    with get_conn(db_path) as conn:
        if run_id is not None and _run_has_target_links(conn, run_id):
            sql = "SELECT bq.* FROM briefing_queue bq JOIN run_targets rt ON rt.briefing_queue_id = bq.id WHERE rt.run_id = ? AND bq.status = ? AND bq.report_url IS NOT NULL AND bq.id NOT IN (SELECT briefing_queue_id FROM send_packs)"
            params = [run_id, BRIEFING_COMPLETED]
            if not include_generate_only:
                sql += " AND bq.post_generation_action = ?"
                params.append(MODE_GENERATE_AND_PREPARE)
            sql += " ORDER BY bq.id ASC"
            rows = conn.execute(sql, tuple(params)).fetchall()
        else:
            where=["status = ?","report_url IS NOT NULL","id NOT IN (SELECT briefing_queue_id FROM send_packs)"]; params=[BRIEFING_COMPLETED]
            if run_id is not None: where.append("run_id = ?"); params.append(run_id)
            if not include_generate_only: where.append("post_generation_action = ?"); params.append(MODE_GENERATE_AND_PREPARE)
            sql=f"SELECT * FROM briefing_queue WHERE {' AND '.join(where)} ORDER BY id ASC"
            rows = conn.execute(sql, tuple(params)).fetchall()
        for row in rows:
            subject, body = render_template(row["company_name"], row["contact_name"], row["report_url"])
            cur=conn.execute("INSERT INTO send_packs (briefing_queue_id, crm_id, company_name, contact_name, contact_email, report_url, email_subject, email_body, campaign_segment, validation_status, validation_errors, signature_present, delivery_status, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (row["id"], row["crm_id"], row["company_name"], row["contact_name"], row["contact_email"], row["report_url"], subject, body, row["campaign_segment"], VALID_PENDING, None, 1, 'pending', SEND_DRAFT))
            built.append(cur.lastrowid)
    for spid in built: validate_send_pack(db_path, spid, True)
    print(f"Built send-packs: {len(built)}")


def mark_run_for_prepare(db_path: Path, run_id: int) -> None:
    with get_conn(db_path) as conn:
        if _run_has_target_links(conn, run_id):
            conn.execute("UPDATE briefing_queue SET post_generation_action = ? WHERE id IN (SELECT briefing_queue_id FROM run_targets WHERE run_id = ?)", (MODE_GENERATE_AND_PREPARE, run_id))
        else:
            conn.execute("UPDATE briefing_queue SET post_generation_action = ? WHERE run_id = ?", (MODE_GENERATE_AND_PREPARE, run_id))
    print({"run_id": run_id, "post_generation_action": MODE_GENERATE_AND_PREPARE})


def approve_send_pack(db_path: Path, send_pack_id: int) -> None:
    res=validate_send_pack(db_path, send_pack_id, True)
    if res["validation_status"] != VALID_OK: raise SystemExit(f"Send-pack {send_pack_id} failed validation: {res['validation_errors']}")
    with get_conn(db_path) as conn: conn.execute("UPDATE send_packs SET status=?, approved_at=? WHERE id=?", (SEND_APPROVED, now_iso(), send_pack_id))
    print(f"Approved send-pack: {send_pack_id}")


def schedule_send(db_path: Path, send_pack_id: int, scheduled_send_at: str) -> None:
    res=validate_send_pack(db_path, send_pack_id, True)
    if res["validation_status"] != VALID_OK: raise SystemExit(f"Send-pack {send_pack_id} failed validation: {res['validation_errors']}")
    with get_conn(db_path) as conn:
        row=conn.execute("SELECT * FROM send_packs WHERE id=?", (send_pack_id,)).fetchone()
        if row is None or row["status"] != SEND_APPROVED: raise SystemExit(f"Send-pack {send_pack_id} is not approved")
        conn.execute("UPDATE send_packs SET status=?, scheduled_send_at=? WHERE id=?", (OUTBOUND_SCHEDULED, scheduled_send_at, send_pack_id))
        conn.execute("INSERT OR REPLACE INTO outbound_queue (send_pack_id, contact_email, email_subject, email_body, report_url, scheduled_send_at, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (row["id"], row["contact_email"], row["email_subject"], row["email_body"], row["report_url"], scheduled_send_at, OUTBOUND_SCHEDULED, now_iso()))
    print(f"Scheduled send-pack {send_pack_id} for {scheduled_send_at}")


def resend_send_pack(db_path: Path, send_pack_id: int, recipient_override: str | None = None, scheduled_send_at: str | None = None) -> None:
    res = validate_send_pack(db_path, send_pack_id, True)
    if res["validation_status"] != VALID_OK:
        raise SystemExit(f"Send-pack {send_pack_id} failed validation: {res['validation_errors']}")
    scheduled_at = scheduled_send_at or now_iso()
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM send_packs WHERE id = ?", (send_pack_id,)).fetchone()
        if row is None:
            raise SystemExit(f"Send-pack not found: {send_pack_id}")
        _archive_existing_outbound(conn, send_pack_id, "resend_reset")
        contact_email = recipient_override or row["contact_email"]
        conn.execute(
            "UPDATE send_packs SET status=?, delivery_status=?, scheduled_send_at=?, sent_at=NULL, provider_message_id=NULL, verification_notes=NULL, error_message=NULL WHERE id=?",
            (OUTBOUND_SCHEDULED, 'pending', scheduled_at, send_pack_id),
        )
        conn.execute(
            "INSERT INTO outbound_queue (send_pack_id, contact_email, email_subject, email_body, report_url, scheduled_send_at, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row["id"], contact_email, row["email_subject"], row["email_body"], row["report_url"], scheduled_at, OUTBOUND_SCHEDULED, now_iso()),
        )
    print({"send_pack_id": send_pack_id, "scheduled_send_at": scheduled_at, "recipient_override": recipient_override, "status": OUTBOUND_SCHEDULED})


def verify_outbound(db_path: Path, send_pack_id: int) -> None:
    with get_conn(db_path) as conn:
        sp = conn.execute("SELECT * FROM send_packs WHERE id = ?", (send_pack_id,)).fetchone()
        out = conn.execute("SELECT * FROM outbound_queue WHERE send_pack_id = ? ORDER BY id DESC LIMIT 1", (send_pack_id,)).fetchone()
        if sp is None or out is None:
            raise SystemExit(f"Missing send-pack/outbound for {send_pack_id}")
        ok, note = verify_from_sent_surfaces(out["contact_email"], out["email_subject"])
        if ok:
            conn.execute("UPDATE outbound_queue SET status=?, verification_notes=? WHERE id=?", (OUTBOUND_SENT_VERIFIED, note, out["id"]))
            conn.execute("UPDATE send_packs SET status=?, delivery_status=?, verification_notes=? WHERE id=?", (SEND_SENT_VERIFIED, SEND_SENT_VERIFIED, note, send_pack_id))
            print({"send_pack_id": send_pack_id, "verification": "sent_verified", "note": note})
        else:
            conn.execute("UPDATE outbound_queue SET status=?, verification_notes=? WHERE id=?", (OUTBOUND_VERIFICATION_FAILED, note, out["id"]))
            conn.execute("UPDATE send_packs SET status=?, delivery_status=?, verification_notes=? WHERE id=?", (SEND_VERIFICATION_FAILED, SEND_VERIFICATION_FAILED, note, send_pack_id))
            print({"send_pack_id": send_pack_id, "verification": "verification_failed", "note": note})


def run_send_queue(db_path: Path, execute: bool = False, limit: int = 10) -> None:
    config = load_config()
    with get_conn(db_path) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM outbound_queue WHERE status = ? ORDER BY scheduled_send_at ASC, id ASC LIMIT ?", (OUTBOUND_SCHEDULED, limit)).fetchall()]
    if not rows:
        print("No scheduled outbound items")
        return
    for row in rows:
        validation = validate_send_pack(db_path, row["send_pack_id"], True)
        if validation["validation_status"] != VALID_OK:
            with get_conn(db_path) as conn:
                conn.execute("UPDATE outbound_queue SET status=?, error_message=? WHERE id=?", (OUTBOUND_FAILED, json.dumps(validation["validation_errors"]), row["id"]))
            print(f"Blocked outbound {row['id']} due to validation failure")
            continue
        if not due_now(row["scheduled_send_at"]):
            print({"outbound_id": row["id"], "status": "not_due_yet", "scheduled_send_at": row["scheduled_send_at"]})
            continue
        command = build_send_command(row["id"], row["contact_email"], row["email_subject"], row["email_body"], account=config.send_account, from_name=config.send_from_name)
        if not execute:
            print({"outbound_id": row["id"], "contact_email": row["contact_email"], "command": command})
            continue
        with get_conn(db_path) as conn:
            conn.execute("UPDATE outbound_queue SET status=? WHERE id=?", (OUTBOUND_SENDING, row["id"]))
        result_exec = execute_send_command(command)
        if result_exec.returncode == 0:
            accepted_at=now_iso(); provider_id=extract_provider_message_id(result_exec.stdout, result_exec.stderr)
            with get_conn(db_path) as conn:
                conn.execute("UPDATE outbound_queue SET status=?, sent_at=?, provider_message_id=?, error_message=NULL WHERE id=?", (OUTBOUND_ACCEPTED, accepted_at, provider_id, row["id"]))
                conn.execute("UPDATE send_packs SET status=?, delivery_status=?, sent_at=?, provider_message_id=?, error_message=NULL WHERE id=?", (SEND_ACCEPTED, SEND_ACCEPTED, accepted_at, provider_id, row["send_pack_id"]))
            append_email_log(row["contact_email"], row["email_subject"], "Accepted by send transport")
            print(f"Accepted outbound {row['id']} to {row['contact_email']}")
        else:
            err=(result_exec.stderr or result_exec.stdout or 'send failed').strip()
            with get_conn(db_path) as conn:
                conn.execute("UPDATE outbound_queue SET status=?, error_message=? WHERE id=?", (OUTBOUND_FAILED, err, row["id"]))
                conn.execute("UPDATE send_packs SET status=?, delivery_status=?, error_message=? WHERE id=?", (SEND_FAILED, SEND_FAILED, err, row["send_pack_id"]))
            append_email_log(row["contact_email"], row["email_subject"], f"Failed: {err[:120]}")
            print(f"Failed outbound {row['id']} -> {err}")


def _local_status_from_remote(remote_status: str) -> str:
    if remote_status == BRIEFING_COMPLETED: return BRIEFING_COMPLETED
    if remote_status in REMOTE_ACTIVE_STATUSES: return BRIEFING_SUBMITTED if remote_status == 'queued' else BRIEFING_PROCESSING
    return BRIEFING_FAILED


def submit_briefings(db_path: Path, run_id: int | None = None) -> None:
    config = load_config(); client = BriefingApiClient(config)
    with get_conn(db_path) as conn:
        if run_id is not None and _run_has_target_links(conn, run_id):
            sql = 'SELECT bq.* FROM briefing_queue bq JOIN run_targets rt ON rt.briefing_queue_id = bq.id WHERE bq.status = ? AND rt.run_id = ? ORDER BY bq.id ASC LIMIT ?'
            params=[BRIEFING_QUEUED, run_id, config.briefing_queue_concurrency]
        else:
            sql='SELECT * FROM briefing_queue WHERE status = ?'
            params=[BRIEFING_QUEUED]
            if run_id is not None: sql += ' AND run_id = ?'; params.append(run_id)
            sql += ' ORDER BY id ASC LIMIT ?'; params.append(config.briefing_queue_concurrency)
        rows=conn.execute(sql, tuple(params)).fetchall()
        if not rows: print('No queued briefing items'); return
        for row in rows:
            append_submit_log({
                'phase': 'pre_request',
                'run_id': run_id,
                'briefing_queue_id': row['id'],
                'company_name': row['company_name'],
                'website_url': row['website_url'],
                'crm_id': row['crm_id'],
                'force_regenerate': bool(row['force_regenerate']),
                'api_base_url': config.briefing_api_base_url,
                'api_key_env': config.briefing_api_key_env,
                'api_key_present': bool(config.api_key),
            })
            resp=client.create_briefing(company_name=row['company_name'], website_url=row['website_url'], source='crm-outbound', external_ref=row['crm_id'], force_regenerate=bool(row['force_regenerate']))
            payload=resp.payload
            append_submit_log({
                'phase': 'post_response',
                'run_id': run_id,
                'briefing_queue_id': row['id'],
                'company_name': row['company_name'],
                'website_url': row['website_url'],
                'crm_id': row['crm_id'],
                'status_code': resp.status_code,
                'response': payload,
            })
            accepted = resp.status_code in (200, 202) and payload.get('success') and bool(payload.get('job_id'))
            if accepted:
                remote_status=payload.get('status') or 'queued'
                report_url_val = payload.get('report_url')
                completed_at_val = payload.get('completed_at')
                pack_created_at_val = payload.get('pack_created_at')
                conn.execute("UPDATE briefing_queue SET status=?, remote_status=?, batch_id=COALESCE(?, batch_id), job_id=?, submitted_at=?, report_url=?, completed_at=?, pack_created_at=?, error_message=NULL WHERE id=?", (_local_status_from_remote(remote_status), remote_status, payload.get('batch_id'), payload.get('job_id'), now_iso(), report_url_val, completed_at_val, pack_created_at_val, row['id']))
                if remote_status == 'completed' and report_url_val:
                    print(f"Submitted: {row['company_name']} -> job {payload.get('job_id')} ({remote_status}) ✅ URL saved: {report_url_val}")
                else:
                    print(f"Submitted: {row['company_name']} -> job {payload.get('job_id')} ({remote_status})")
            else:
                error_text = payload.get('error') or f'Handshake failed: status={resp.status_code}, job_id={payload.get("job_id")}, success={payload.get("success")}'
                conn.execute("UPDATE briefing_queue SET status=?, error_message=? WHERE id=?", (BRIEFING_FAILED, error_text, row['id']))
                print(f"Failed submit: {row['company_name']} -> {error_text}")
        if run_id is not None:
            conn.execute("UPDATE batch_runs SET state=?, watch_finished_at=NULL WHERE id=?", (RUN_SUBMITTED, run_id)); _persist_run_summary(conn, run_id)


def poll_briefings(db_path: Path, once: bool = False, run_id: int | None = None, until_run_complete: bool = False) -> None:
    config=load_config(); client=BriefingApiClient(config); started=time.time()
    while True:
        made_progress=False
        should_submit_more=False
        should_continue_after_submit=False
        with get_conn(db_path) as conn:
            if run_id is not None and _run_has_target_links(conn, run_id):
                sql='SELECT bq.* FROM briefing_queue bq JOIN run_targets rt ON rt.briefing_queue_id = bq.id WHERE bq.status IN (?, ?) AND bq.job_id IS NOT NULL AND rt.run_id = ? ORDER BY bq.id ASC'
                params=[BRIEFING_SUBMITTED, BRIEFING_PROCESSING, run_id]
                queued_sql = 'SELECT COUNT(*) AS c FROM briefing_queue bq JOIN run_targets rt ON rt.briefing_queue_id = bq.id WHERE bq.status = ? AND rt.run_id = ?'
                queued_params = (BRIEFING_QUEUED, run_id)
            else:
                sql='SELECT * FROM briefing_queue WHERE status IN (?, ?) AND job_id IS NOT NULL'; params=[BRIEFING_SUBMITTED, BRIEFING_PROCESSING]
                if run_id is not None: sql += ' AND run_id = ?'; params.append(run_id)
                sql += ' ORDER BY id ASC'
                queued_sql = 'SELECT COUNT(*) AS c FROM briefing_queue WHERE status = ?'
                queued_params = [BRIEFING_QUEUED]
                if run_id is not None:
                    queued_sql += ' AND run_id = ?'
                    queued_params.append(run_id)
            rows=conn.execute(sql, tuple(params)).fetchall()
            if not rows:
                queued_count = conn.execute(queued_sql, tuple(queued_params)).fetchone()['c']
                if queued_count and run_id is not None:
                    should_submit_more=True
                    should_continue_after_submit=True
                    payload=_persist_run_summary(conn, run_id)
                    if once and not until_run_complete:
                        print(payload)
                        return
                else:
                    print('No submitted/processing briefing items')
                    if run_id is not None and until_run_complete: print(_persist_run_summary(conn, run_id))
                    return
            else:
                for row in rows:
                    resp=client.get_briefing(row['job_id']); payload=resp.payload
                    if resp.status_code == 200 and payload.get('success'):
                        remote_status=payload.get('status') or row['remote_status'] or 'queued'
                        if remote_status in REMOTE_ACTIVE_STATUSES:
                            conn.execute("UPDATE briefing_queue SET status=?, remote_status=?, batch_id=COALESCE(?, batch_id), last_polled_at=?, error_message=NULL WHERE id=?", (_local_status_from_remote(remote_status), remote_status, payload.get('batch_id'), now_iso(), row['id']))
                        elif remote_status == BRIEFING_COMPLETED:
                            conn.execute("UPDATE briefing_queue SET status=?, remote_status=?, batch_id=COALESCE(?, batch_id), report_url=?, completed_at=?, pack_created_at=COALESCE(?, pack_created_at), last_polled_at=?, error_message=NULL WHERE id=?", (BRIEFING_COMPLETED, remote_status, payload.get('batch_id'), payload.get('report_url'), payload.get('completed_at'), payload.get('pack_created_at'), now_iso(), row['id']))
                            made_progress=True
                        else:
                            conn.execute("UPDATE briefing_queue SET status=?, remote_status=?, batch_id=COALESCE(?, batch_id), last_polled_at=?, error_message=? WHERE id=?", (BRIEFING_FAILED, remote_status, payload.get('batch_id'), now_iso(), payload.get('error', f'Unexpected status: {remote_status}'), row['id']))
                            made_progress=True
                    else:
                        error_text = payload.get('error', f'HTTP {resp.status_code}')
                        if resp.status_code == 404:
                            conn.execute("UPDATE briefing_queue SET status=?, remote_status=?, last_polled_at=?, error_message=? WHERE id=?", (BRIEFING_FAILED, 'failed', now_iso(), f'Stale/deleted remote job: {error_text}', row['id']))
                            made_progress=True
                        else:
                            conn.execute("UPDATE briefing_queue SET last_polled_at=?, error_message=? WHERE id=?", (now_iso(), error_text, row['id']))
                queued_count = conn.execute(queued_sql, tuple(queued_params)).fetchone()['c']
                if queued_count and run_id is not None:
                    should_submit_more=True
                if run_id is not None:
                    payload=_persist_run_summary(conn, run_id)
                    if until_run_complete and payload['summary']['terminal']:
                        print(payload); return
        if should_submit_more and run_id is not None:
            submit_briefings(db_path, run_id=run_id)
        if should_continue_after_submit:
            time.sleep(1)
            continue
        if once and not until_run_complete: return
        if time.time()-started > config.briefing_timeout_seconds:
            if run_id is not None:
                with get_conn(db_path) as conn: print(_persist_run_summary(conn, run_id))
            return
        time.sleep(1 if made_progress else config.briefing_poll_interval_seconds)


def watch_run(db_path: Path, run_id: int) -> None:
    with get_conn(db_path) as conn:
        conn.execute("UPDATE batch_runs SET state=?, watch_started_at=?, watch_finished_at=NULL WHERE id=?", (RUN_WATCHING, now_iso(), run_id)); print(_persist_run_summary(conn, run_id))
    poll_briefings(db_path, once=False, run_id=run_id, until_run_complete=True)


def load_target_from_args(args: argparse.Namespace) -> Target:
    return Target(args.crm_id, args.company_name, args.website_url, args.contact_name, args.contact_email, args.campaign_segment, args.force_regenerate, args.run_id, args.post_generation_action)


def parse_args() -> argparse.Namespace:
    parser=argparse.ArgumentParser(description='AI Briefing Outbound Runner'); parser.add_argument('--db', default=str(DEFAULT_DB)); sub=parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-db'); sub.add_parser('list-briefings'); sub.add_parser('list-send-packs'); sub.add_parser('list-outbound'); sub.add_parser('list-runs')
    c=sub.add_parser('create-run'); c.add_argument('--name', required=True); c.add_argument('--mode', default=MODE_GENERATE_ONLY); c.add_argument('--notes')
    rs=sub.add_parser('run-summary'); rs.add_argument('--run-id', type=int, required=True)
    wr=sub.add_parser('watch-run'); wr.add_argument('--run-id', type=int, required=True)
    val=sub.add_parser('validate-send-pack'); val.add_argument('--send-pack-id', type=int, required=True)
    ver=sub.add_parser('verify-outbound'); ver.add_argument('--send-pack-id', type=int, required=True)
    b=sub.add_parser('build-send-packs'); b.add_argument('--run-id', type=int); b.add_argument('--include-generate-only', action='store_true')
    s=sub.add_parser('submit-briefings'); s.add_argument('--run-id', type=int)
    p=sub.add_parser('poll-briefings'); p.add_argument('--once', action='store_true'); p.add_argument('--run-id', type=int); p.add_argument('--until-run-complete', action='store_true')
    prev=sub.add_parser('preview-crm-targets'); prev.add_argument('--limit', type=int)
    imp=sub.add_parser('import-crm-targets'); imp.add_argument('--limit', type=int); imp.add_argument('--force-regenerate', action='store_true'); imp.add_argument('--run-id', type=int); imp.add_argument('--post-generation-action', default=MODE_GENERATE_ONLY)
    a=sub.add_parser('add-target'); a.add_argument('--crm-id', required=True); a.add_argument('--company-name', required=True); a.add_argument('--website-url', required=True); a.add_argument('--contact-email', required=True); a.add_argument('--contact-name'); a.add_argument('--campaign-segment'); a.add_argument('--force-regenerate', action='store_true'); a.add_argument('--run-id', type=int); a.add_argument('--post-generation-action', default=MODE_GENERATE_ONLY)
    m=sub.add_parser('mark-run-for-prepare'); m.add_argument('--run-id', type=int, required=True)
    ap=sub.add_parser('approve-send-pack'); ap.add_argument('--send-pack-id', type=int, required=True)
    sch=sub.add_parser('schedule-send'); sch.add_argument('--send-pack-id', type=int, required=True); sch.add_argument('--scheduled-send-at', required=True)
    rsp=sub.add_parser('resend-send-pack'); rsp.add_argument('--send-pack-id', type=int, required=True); rsp.add_argument('--recipient-override'); rsp.add_argument('--scheduled-send-at')
    rsq=sub.add_parser('run-send-queue'); rsq.add_argument('--execute', action='store_true'); rsq.add_argument('--limit', type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args=parse_args(); db_path=Path(args.db); config=load_config()
    if args.command=='init-db': init_db(db_path)
    elif args.command=='create-run': create_run(db_path, args.name, args.mode, args.notes)
    elif args.command=='list-runs': list_runs(db_path)
    elif args.command=='run-summary': run_summary(db_path, args.run_id)
    elif args.command=='watch-run': watch_run(db_path, args.run_id)
    elif args.command=='preview-crm-targets': preview_crm_targets(limit=args.limit or config.default_crm_import_limit)
    elif args.command=='import-crm-targets': import_crm_targets(db_path, args.limit or config.default_crm_import_limit, args.force_regenerate, args.run_id, args.post_generation_action)
    elif args.command=='add-target': add_target(db_path, load_target_from_args(args))
    elif args.command=='submit-briefings': submit_briefings(db_path, args.run_id)
    elif args.command=='poll-briefings': poll_briefings(db_path, args.once, args.run_id, args.until_run_complete)
    elif args.command=='list-briefings': list_rows(db_path, 'briefing_queue')
    elif args.command=='mark-run-for-prepare': mark_run_for_prepare(db_path, args.run_id)
    elif args.command=='build-send-packs': build_send_packs(db_path, args.run_id, args.include_generate_only)
    elif args.command=='validate-send-pack': validate_send_pack(db_path, args.send_pack_id, True)
    elif args.command=='verify-outbound': verify_outbound(db_path, args.send_pack_id)
    elif args.command=='list-send-packs': list_rows(db_path, 'send_packs')
    elif args.command=='approve-send-pack': approve_send_pack(db_path, args.send_pack_id)
    elif args.command=='schedule-send': schedule_send(db_path, args.send_pack_id, args.scheduled_send_at)
    elif args.command=='resend-send-pack': resend_send_pack(db_path, args.send_pack_id, args.recipient_override, args.scheduled_send_at)
    elif args.command=='run-send-queue': run_send_queue(db_path, args.execute, args.limit)
    elif args.command=='list-outbound': list_rows(db_path, 'outbound_queue')
    else: raise SystemExit(f'Unknown command: {args.command}')

if __name__ == '__main__':
    main()
