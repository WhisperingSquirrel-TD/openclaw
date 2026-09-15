#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from api_client import BriefingApiClient
from config import load_config
from crm_import import eligible_leads
from send_queue import append_email_log, build_send_command, due_now, execute_send_command

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = PROJECT_ROOT / "outbound.db"
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "outbound_email.txt"

BRIEFING_QUEUED = "queued-for-briefing"
BRIEFING_SUBMITTED = "submitted"
BRIEFING_PROCESSING = "processing"
BRIEFING_COMPLETED = "completed"
BRIEFING_FAILED = "failed"
SEND_DRAFT = "draft-pending-review"
SEND_APPROVED = "approved-to-send"
SEND_SENT = "sent"
SEND_FAILED = "send-failed"
OUTBOUND_SCHEDULED = "scheduled"
OUTBOUND_SENDING = "sending"
OUTBOUND_SENT = "sent"
OUTBOUND_FAILED = "failed"


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn(db_path) as conn:
        conn.executescript(schema)
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


def add_target(db_path: Path, target: Target) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO briefing_queue (
              crm_id, company_name, website_url, contact_name, contact_email,
              campaign_segment, force_regenerate, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target.crm_id,
                target.company_name,
                target.website_url,
                target.contact_name,
                target.contact_email,
                target.campaign_segment,
                1 if target.force_regenerate else 0,
                BRIEFING_QUEUED,
                now_iso(),
            ),
        )
    print(f"Queued target: {target.company_name} <{target.contact_email}>")


def import_crm_targets(db_path: Path, limit: int, force_regenerate: bool = False) -> None:
    leads = eligible_leads(limit=limit)
    if not leads:
        print("No eligible CRM leads found")
        return
    imported = 0
    for lead in leads:
        add_target(
            db_path,
            Target(
                crm_id=lead.crm_id,
                company_name=lead.company_name,
                website_url=lead.website_url,
                contact_name=lead.contact_name,
                contact_email=lead.contact_email,
                campaign_segment=lead.campaign_segment,
                force_regenerate=force_regenerate,
            ),
        )
        imported += 1
    print(f"Imported CRM targets into Queue A: {imported}")


def preview_crm_targets(limit: int) -> None:
    leads = eligible_leads(limit=limit)
    if not leads:
        print("No eligible CRM leads found")
        return
    for lead in leads:
        print(
            {
                "crm_id": lead.crm_id,
                "company_name": lead.company_name,
                "website_url": lead.website_url,
                "contact_name": lead.contact_name,
                "contact_email": lead.contact_email,
                "campaign_segment": lead.campaign_segment,
                "status": lead.status,
            }
        )


def list_rows(db_path: Path, table: str) -> None:
    with get_conn(db_path) as conn:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC").fetchall()
    if not rows:
        print(f"No rows in {table}")
        return
    for row in rows:
        print(dict(row))


def render_template(company_name: str, contact_name: str | None, report_url: str) -> tuple[str, str]:
    raw = TEMPLATE_PATH.read_text(encoding="utf-8")
    greeting = contact_name if contact_name and contact_name.strip() else "there"
    rendered = (
        raw.replace("{{company_name}}", company_name)
           .replace("{{report_url}}", report_url)
           .replace("{{contact_name_or_fallback}}", greeting)
    )
    first, _, rest = rendered.partition("\n")
    subject = first.removeprefix("Subject: ").strip()
    body = rest.lstrip("\n")
    return subject, body


def build_send_packs(db_path: Path) -> None:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM briefing_queue
            WHERE status = ? AND report_url IS NOT NULL
              AND id NOT IN (SELECT briefing_queue_id FROM send_packs)
            ORDER BY id ASC
            """,
            (BRIEFING_COMPLETED,),
        ).fetchall()
        built = 0
        for row in rows:
            subject, body = render_template(
                company_name=row["company_name"],
                contact_name=row["contact_name"],
                report_url=row["report_url"],
            )
            conn.execute(
                """
                INSERT INTO send_packs (
                  briefing_queue_id, crm_id, company_name, contact_name, contact_email,
                  report_url, email_subject, email_body, campaign_segment, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["crm_id"],
                    row["company_name"],
                    row["contact_name"],
                    row["contact_email"],
                    row["report_url"],
                    subject,
                    body,
                    row["campaign_segment"],
                    SEND_DRAFT,
                ),
            )
            built += 1
    print(f"Built send-packs: {built}")


def approve_send_pack(db_path: Path, send_pack_id: int) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE send_packs SET status = ?, approved_at = ? WHERE id = ?",
            (SEND_APPROVED, now_iso(), send_pack_id),
        )
    print(f"Approved send-pack: {send_pack_id}")


def schedule_send(db_path: Path, send_pack_id: int, scheduled_send_at: str) -> None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM send_packs WHERE id = ?", (send_pack_id,)).fetchone()
        if row is None:
            raise SystemExit(f"Send-pack not found: {send_pack_id}")
        if row["status"] != SEND_APPROVED:
            raise SystemExit(f"Send-pack {send_pack_id} is not approved")
        conn.execute(
            "UPDATE send_packs SET status = ?, scheduled_send_at = ? WHERE id = ?",
            (OUTBOUND_SCHEDULED, scheduled_send_at, send_pack_id),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO outbound_queue (
              send_pack_id, contact_email, email_subject, email_body,
              report_url, scheduled_send_at, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["contact_email"],
                row["email_subject"],
                row["email_body"],
                row["report_url"],
                scheduled_send_at,
                OUTBOUND_SCHEDULED,
                now_iso(),
            ),
        )
    print(f"Scheduled send-pack {send_pack_id} for {scheduled_send_at}")


def run_send_queue(db_path: Path, execute: bool = False, limit: int = 10) -> None:
    config = load_config()
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM outbound_queue WHERE status = ? ORDER BY scheduled_send_at ASC, id ASC LIMIT ?",
            (OUTBOUND_SCHEDULED, limit),
        ).fetchall()
        if not rows:
            print("No scheduled outbound items")
            return
        for row in rows:
            if not due_now(row["scheduled_send_at"]):
                print(f"Not due yet: outbound {row['id']} scheduled for {row['scheduled_send_at']}")
                continue
            command = build_send_command(
                outbound_id=row["id"],
                recipient=row["contact_email"],
                subject=row["email_subject"],
                body=row["email_body"],
                account=config.send_account,
                from_name=config.send_from_name,
            )
            if not execute:
                print({
                    "outbound_id": row["id"],
                    "contact_email": row["contact_email"],
                    "scheduled_send_at": row["scheduled_send_at"],
                    "command": command,
                })
                continue
            conn.execute("UPDATE outbound_queue SET status = ? WHERE id = ?", (OUTBOUND_SENDING, row["id"]))
            result = execute_send_command(command)
            if result.returncode == 0:
                sent_at = now_iso()
                conn.execute(
                    "UPDATE outbound_queue SET status = ?, sent_at = ?, error_message = NULL WHERE id = ?",
                    (OUTBOUND_SENT, sent_at, row["id"]),
                )
                send_pack_id = row["send_pack_id"]
                conn.execute(
                    "UPDATE send_packs SET status = ?, sent_at = ?, error_message = NULL WHERE id = ?",
                    (SEND_SENT, sent_at, send_pack_id),
                )
                append_email_log(row["contact_email"], row["email_subject"], "Sent")
                print(f"Sent outbound {row['id']} to {row['contact_email']}")
            else:
                err = (result.stderr or result.stdout or "send failed").strip()
                conn.execute(
                    "UPDATE outbound_queue SET status = ?, error_message = ? WHERE id = ?",
                    (OUTBOUND_FAILED, err, row["id"]),
                )
                send_pack_id = row["send_pack_id"]
                conn.execute(
                    "UPDATE send_packs SET status = ?, error_message = ? WHERE id = ?",
                    (SEND_FAILED, err, send_pack_id),
                )
                append_email_log(row["contact_email"], row["email_subject"], f"Failed: {err[:120]}")
                print(f"Failed outbound {row['id']} -> {err}")


def submit_briefings(db_path: Path) -> None:
    config = load_config()
    client = BriefingApiClient(config)
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM briefing_queue WHERE status = ? ORDER BY id ASC LIMIT ?",
            (BRIEFING_QUEUED, config.briefing_queue_concurrency),
        ).fetchall()
        if not rows:
            print("No queued briefing items")
            return
        for row in rows:
            resp = client.create_briefing(
                company_name=row["company_name"],
                website_url=row["website_url"],
                source="crm-outbound",
                external_ref=row["crm_id"],
                force_regenerate=bool(row["force_regenerate"]),
            )
            payload = resp.payload
            if resp.status_code in (200, 202) and payload.get("success"):
                status = payload.get("status") or BRIEFING_SUBMITTED
                conn.execute(
                    """
                    UPDATE briefing_queue
                    SET status = ?, job_id = ?, submitted_at = ?, report_url = COALESCE(?, report_url),
                        completed_at = COALESCE(?, completed_at),
                        pack_created_at = COALESCE(?, pack_created_at),
                        error_message = NULL
                    WHERE id = ?
                    """,
                    (
                        BRIEFING_COMPLETED if status == BRIEFING_COMPLETED else BRIEFING_SUBMITTED,
                        payload.get("job_id"),
                        now_iso(),
                        payload.get("report_url"),
                        payload.get("completed_at"),
                        payload.get("pack_created_at"),
                        row["id"],
                    ),
                )
                print(f"Submitted: {row['company_name']} -> job {payload.get('job_id')} ({status})")
            else:
                conn.execute(
                    "UPDATE briefing_queue SET status = ?, error_message = ? WHERE id = ?",
                    (BRIEFING_FAILED, payload.get("error", f"HTTP {resp.status_code}"), row["id"]),
                )
                print(f"Failed submit: {row['company_name']} -> {payload.get('error', f'HTTP {resp.status_code}')} ")


def poll_briefings(db_path: Path, once: bool = False) -> None:
    config = load_config()
    client = BriefingApiClient(config)
    started = time.time()
    while True:
        made_progress = False
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM briefing_queue WHERE status IN (?, ?) AND job_id IS NOT NULL ORDER BY id ASC",
                (BRIEFING_SUBMITTED, BRIEFING_PROCESSING),
            ).fetchall()
            if not rows:
                print("No submitted/processing briefing items")
                return
            for row in rows:
                resp = client.get_briefing(row["job_id"])
                payload = resp.payload
                if resp.status_code == 200 and payload.get("success"):
                    status = payload.get("status")
                    if status in ("queued", "processing"):
                        conn.execute(
                            "UPDATE briefing_queue SET status = ?, error_message = NULL WHERE id = ?",
                            (BRIEFING_PROCESSING if status == "processing" else BRIEFING_SUBMITTED, row["id"]),
                        )
                        print(f"Polling: {row['company_name']} -> {status}")
                    elif status == BRIEFING_COMPLETED:
                        conn.execute(
                            """
                            UPDATE briefing_queue
                            SET status = ?, report_url = ?, completed_at = ?,
                                pack_created_at = COALESCE(?, pack_created_at), error_message = NULL
                            WHERE id = ?
                            """,
                            (
                                BRIEFING_COMPLETED,
                                payload.get("report_url"),
                                payload.get("completed_at"),
                                payload.get("pack_created_at"),
                                row["id"],
                            ),
                        )
                        made_progress = True
                        print(f"Completed: {row['company_name']} -> {payload.get('report_url')}")
                    else:
                        conn.execute(
                            "UPDATE briefing_queue SET status = ?, error_message = ? WHERE id = ?",
                            (BRIEFING_FAILED, payload.get("error", f"Unexpected status: {status}"), row["id"]),
                        )
                        made_progress = True
                        print(f"Failed: {row['company_name']} -> {payload.get('error', status)}")
                else:
                    conn.execute(
                        "UPDATE briefing_queue SET error_message = ? WHERE id = ?",
                        (payload.get("error", f"HTTP {resp.status_code}"), row["id"]),
                    )
                    print(f"Polling error: {row['company_name']} -> {payload.get('error', f'HTTP {resp.status_code}')} ")
        if once:
            return
        if time.time() - started > config.briefing_timeout_seconds:
            print("Polling timeout reached")
            return
        if made_progress:
            time.sleep(1)
        else:
            time.sleep(config.briefing_poll_interval_seconds)


def load_target_from_args(args: argparse.Namespace) -> Target:
    return Target(
        crm_id=args.crm_id,
        company_name=args.company_name,
        website_url=args.website_url,
        contact_name=args.contact_name,
        contact_email=args.contact_email,
        campaign_segment=args.campaign_segment,
        force_regenerate=args.force_regenerate,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Briefing Outbound Runner")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")
    sub.add_parser("list-briefings")
    sub.add_parser("list-send-packs")
    sub.add_parser("list-outbound")
    sub.add_parser("build-send-packs")
    sub.add_parser("submit-briefings")
    poll = sub.add_parser("poll-briefings")
    poll.add_argument("--once", action="store_true")

    preview = sub.add_parser("preview-crm-targets")
    preview.add_argument("--limit", type=int)

    import_cmd = sub.add_parser("import-crm-targets")
    import_cmd.add_argument("--limit", type=int)
    import_cmd.add_argument("--force-regenerate", action="store_true")

    add = sub.add_parser("add-target")
    add.add_argument("--crm-id", required=True)
    add.add_argument("--company-name", required=True)
    add.add_argument("--website-url", required=True)
    add.add_argument("--contact-email", required=True)
    add.add_argument("--contact-name")
    add.add_argument("--campaign-segment")
    add.add_argument("--force-regenerate", action="store_true")

    approve = sub.add_parser("approve-send-pack")
    approve.add_argument("--send-pack-id", type=int, required=True)

    schedule = sub.add_parser("schedule-send")
    schedule.add_argument("--send-pack-id", type=int, required=True)
    schedule.add_argument("--scheduled-send-at", required=True)

    send = sub.add_parser("run-send-queue")
    send.add_argument("--execute", action="store_true")
    send.add_argument("--limit", type=int, default=10)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    config = load_config()

    if args.command == "init-db":
        init_db(db_path)
    elif args.command == "preview-crm-targets":
        preview_crm_targets(limit=args.limit or config.default_crm_import_limit)
    elif args.command == "import-crm-targets":
        import_crm_targets(
            db_path,
            limit=args.limit or config.default_crm_import_limit,
            force_regenerate=args.force_regenerate,
        )
    elif args.command == "add-target":
        add_target(db_path, load_target_from_args(args))
    elif args.command == "submit-briefings":
        submit_briefings(db_path)
    elif args.command == "poll-briefings":
        poll_briefings(db_path, once=args.once)
    elif args.command == "list-briefings":
        list_rows(db_path, "briefing_queue")
    elif args.command == "build-send-packs":
        build_send_packs(db_path)
    elif args.command == "list-send-packs":
        list_rows(db_path, "send_packs")
    elif args.command == "approve-send-pack":
        approve_send_pack(db_path, args.send_pack_id)
    elif args.command == "schedule-send":
        schedule_send(db_path, args.send_pack_id, args.scheduled_send_at)
    elif args.command == "run-send-queue":
        run_send_queue(db_path, execute=args.execute, limit=args.limit)
    elif args.command == "list-outbound":
        list_rows(db_path, "outbound_queue")
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
