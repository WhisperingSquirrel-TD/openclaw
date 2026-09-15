"""SQLite repository for the Phase 1 SEER expense operational ledger.

This is deliberately a narrow persistence boundary.  It captures source facts
without deriving missing financial values, and is the only module that changes
expense review state.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 4


class ExpenseStatus(str, Enum):
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    NOT_BUSINESS = "not_business"
    DUPLICATE = "duplicate"
    LEDGER_READY = "ledger_ready"
    LEDGER_WRITTEN = "ledger_written"
    BLOCKED = "blocked"


_ALLOWED_TRANSITIONS: dict[ExpenseStatus, frozenset[ExpenseStatus]] = {
    ExpenseStatus.NEEDS_REVIEW: frozenset({
        ExpenseStatus.CONFIRMED, ExpenseStatus.NOT_BUSINESS,
        ExpenseStatus.DUPLICATE, ExpenseStatus.BLOCKED,
    }),
    ExpenseStatus.CONFIRMED: frozenset({ExpenseStatus.LEDGER_READY, ExpenseStatus.BLOCKED}),
    ExpenseStatus.LEDGER_READY: frozenset({ExpenseStatus.LEDGER_WRITTEN, ExpenseStatus.BLOCKED}),
    ExpenseStatus.BLOCKED: frozenset({ExpenseStatus.NEEDS_REVIEW}),
    ExpenseStatus.NOT_BUSINESS: frozenset(),
    ExpenseStatus.DUPLICATE: frozenset(),
    ExpenseStatus.LEDGER_WRITTEN: frozenset(),
}


class ExpenseRepositoryError(RuntimeError):
    """Base class for repository errors."""


class InvalidTransitionError(ExpenseRepositoryError):
    """Raised when an expense status change is not permitted."""


@dataclass(frozen=True)
class Expense:
    expense_id: str
    source_surface: str
    source_ref: str
    status: ExpenseStatus
    source_timestamp: str | None
    observed_timestamp: str
    supplier: str | None
    amount_pence: int | None
    currency: str | None
    expense_date: str | None
    category: str | None
    evidence_ref: str | None
    evidence_state: str | None
    settlement_state: str | None
    finance_ledger_ref: str | None
    validation_result: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ReceiptEvidence:
    """An immutable receipt-evidence record linked to an expense source reference."""

    evidence_id: str
    source_ref: str
    evidence_kind: str
    local_path: str | None
    sha256: str | None
    sharepoint_path: str | None
    sharepoint_url: str | None
    sharepoint_etag: str | None
    source_timestamp: str | None
    created_at: str


class ExpenseRepository:
    """Owns schema migration, idempotent candidate capture, and transitions."""

    def __init__(self, database: str | Path) -> None:
        self.connection = sqlite3.connect(str(database))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def close(self) -> None:
        self.connection.close()

    def migrate(self) -> None:
        """Apply the current schema once, recording the migration version."""
        with self.connection:
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            version_one_applied = self.connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 1"
            ).fetchone()
            if not version_one_applied:
                self.connection.executescript(
                    """
                CREATE TABLE expenses (
                    expense_id TEXT PRIMARY KEY,
                    source_surface TEXT NOT NULL,
                    source_ref TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK (status IN (
                        'needs_review', 'confirmed', 'not_business', 'duplicate',
                        'ledger_ready', 'ledger_written', 'blocked'
                    )),
                    source_timestamp TEXT,
                    observed_timestamp TEXT NOT NULL,
                    supplier TEXT,
                    amount_pence INTEGER CHECK (
                        amount_pence IS NULL OR (typeof(amount_pence) = 'integer' AND amount_pence >= 0)
                    ),
                    currency TEXT CHECK (currency IS NULL OR currency GLOB '[A-Z][A-Z][A-Z]'),
                    expense_date TEXT,
                    category TEXT,
                    evidence_ref TEXT,
                    evidence_state TEXT,
                    settlement_state TEXT,
                    finance_ledger_ref TEXT UNIQUE,
                    validation_result TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE expense_events (
                    event_id TEXT PRIMARY KEY,
                    expense_id TEXT NOT NULL REFERENCES expenses(expense_id),
                    event_type TEXT NOT NULL CHECK (event_type IN ('capture', 'transition')),
                    from_status TEXT,
                    to_status TEXT,
                    outcome TEXT NOT NULL CHECK (outcome IN ('applied', 'rejected')),
                    error_code TEXT,
                    occurred_at TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0)
                );
                CREATE TRIGGER expense_events_immutable_update
                BEFORE UPDATE ON expense_events BEGIN
                    SELECT RAISE(ABORT, 'expense events are immutable');
                END;
                CREATE TRIGGER expense_events_immutable_delete
                BEFORE DELETE ON expense_events BEGIN
                    SELECT RAISE(ABORT, 'expense events are immutable');
                END;
                """
                )
                self.connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (1, _now()),
                )
            version_two_applied = self.connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 2"
            ).fetchone()
            if not version_two_applied:
                self.connection.executescript(
                    """
                    CREATE TABLE expense_capture_collisions (
                        collision_id TEXT PRIMARY KEY,
                        expense_id TEXT NOT NULL REFERENCES expenses(expense_id),
                        source_ref TEXT NOT NULL,
                        original_facts_json TEXT NOT NULL,
                        incoming_facts_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        UNIQUE(expense_id, incoming_facts_json)
                    );
                    CREATE TRIGGER expense_capture_collisions_immutable_update
                    BEFORE UPDATE ON expense_capture_collisions BEGIN
                        SELECT RAISE(ABORT, 'expense capture collisions are immutable');
                    END;
                    CREATE TRIGGER expense_capture_collisions_immutable_delete
                    BEFORE DELETE ON expense_capture_collisions BEGIN
                        SELECT RAISE(ABORT, 'expense capture collisions are immutable');
                    END;
                    """
                )
                self.connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (2, _now()),
                )
            version_three_applied = self.connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 3"
            ).fetchone()
            if not version_three_applied:
                self.connection.executescript(
                    """
                    CREATE TABLE receipt_evidence (
                        evidence_id TEXT PRIMARY KEY,
                        source_ref TEXT NOT NULL REFERENCES expenses(source_ref)
                            ON UPDATE RESTRICT ON DELETE RESTRICT,
                        evidence_kind TEXT NOT NULL,
                        local_path TEXT,
                        sha256 TEXT CHECK (
                            sha256 IS NULL OR (
                                length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'
                            )
                        ),
                        sharepoint_path TEXT,
                        sharepoint_url TEXT,
                        sharepoint_etag TEXT,
                        source_timestamp TEXT,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX receipt_evidence_source_ref_idx
                        ON receipt_evidence(source_ref, created_at);
                    CREATE TRIGGER receipt_evidence_immutable_update
                    BEFORE UPDATE ON receipt_evidence BEGIN
                        SELECT RAISE(ABORT, 'receipt evidence is immutable');
                    END;
                    CREATE TRIGGER receipt_evidence_immutable_delete
                    BEFORE DELETE ON receipt_evidence BEGIN
                        SELECT RAISE(ABORT, 'receipt evidence is immutable');
                    END;
                    """
                )
                self.connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (3, _now()),
                )
            version_four_applied = self.connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 4"
            ).fetchone()
            if not version_four_applied:
                # Retrying a replay must not create duplicate evidence rows.  The
                # unique key preserves append-only semantics for distinct proof
                # while treating the same immutable proof as idempotent.
                self.connection.execute(
                    "CREATE UNIQUE INDEX receipt_evidence_idempotency_idx ON receipt_evidence "
                    "(source_ref, evidence_kind, ifnull(sha256, ''), "
                    "ifnull(sharepoint_path, ''), ifnull(sharepoint_etag, ''))"
                )
                self.connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (4, _now()),
                )

    def capture(self, *, source_surface: str, source_ref: str, **facts: Any) -> Expense:
        """Capture by source ref, preserving contradictory repeats as immutable collisions."""
        _require_nonempty(source_surface, "source_surface")
        _require_nonempty(source_ref, "source_ref")
        facts = _validated_facts(facts)
        started = time.monotonic()
        now = _now()
        with self.connection:
            row = self.connection.execute(
                "SELECT * FROM expenses WHERE source_ref = ?", (source_ref,)
            ).fetchone()
            if row is None:
                expense_id = str(uuid.uuid4())
                columns = {
                    "expense_id": expense_id,
                    "source_surface": source_surface,
                    "source_ref": source_ref,
                    "status": ExpenseStatus.NEEDS_REVIEW.value,
                    "observed_timestamp": facts.pop("observed_timestamp", now),
                    "created_at": now,
                    "updated_at": now,
                    **facts,
                }
                names = ", ".join(columns)
                self.connection.execute(
                    f"INSERT INTO expenses ({names}) VALUES ({', '.join('?' for _ in columns)})",
                    tuple(columns.values()),
                )
                self._event(expense_id, "capture", None, ExpenseStatus.NEEDS_REVIEW.value,
                            "applied", None, started)
                outcome = "created"
            else:
                expense_id = row["expense_id"]
                # A repeated reference may enrich absent fields, but never resolves
                # contradictory non-null source facts by discarding either version.
                conflicts = {
                    key: value for key, value in facts.items()
                    if value is not None and row[key] is not None and row[key] != value
                }
                if row["source_surface"] != source_surface:
                    conflicts["source_surface"] = source_surface
                if conflicts:
                    self._record_capture_collision(
                        expense_id=expense_id,
                        source_ref=source_ref,
                        original=_capture_snapshot(row),
                        incoming={"source_surface": source_surface, **facts},
                    )
                updates = {key: value for key, value in facts.items()
                           if value is not None and row[key] is None}
                if updates:
                    updates["updated_at"] = now
                    assignments = ", ".join(f"{key} = ?" for key in updates)
                    self.connection.execute(
                        f"UPDATE expenses SET {assignments} WHERE expense_id = ?",
                        (*updates.values(), expense_id),
                    )
                outcome = "preserved_for_review" if conflicts else "idempotent"
        expense = self.get(expense_id)
        logger.info("expense_capture outcome=%s expense_id=%s source_ref=%s duration_ms=%d",
                    outcome, expense_id, source_ref, _duration_ms(started))
        return expense

    def transition(self, expense_id: str, to_status: ExpenseStatus | str) -> Expense:
        """Apply an explicit state transition, recording both accepts and refusals."""
        try:
            target = ExpenseStatus(to_status)
        except ValueError as exc:
            raise InvalidTransitionError(f"unknown expense status {to_status!r}") from exc
        started = time.monotonic()
        rejection: tuple[ExpenseStatus, str] | None = None
        with self.connection:
            row = self.connection.execute(
                "SELECT * FROM expenses WHERE expense_id = ?", (expense_id,)
            ).fetchone()
            if row is None:
                raise ExpenseRepositoryError(f"unknown expense_id {expense_id!r}")
            current = ExpenseStatus(row["status"])
            if target not in _ALLOWED_TRANSITIONS[current]:
                # Commit the refusal audit record before raising to the caller.
                self._event(expense_id, "transition", current.value, target.value,
                            "rejected", "invalid_transition", started)
                rejection = (current, row["source_ref"])
            else:
                now = _now()
                self.connection.execute(
                    "UPDATE expenses SET status = ?, updated_at = ? WHERE expense_id = ?",
                    (target.value, now, expense_id),
                )
                self._event(expense_id, "transition", current.value, target.value,
                            "applied", None, started)
        if rejection is not None:
            current, source_ref = rejection
            logger.warning("expense_transition outcome=rejected error_code=invalid_transition "
                           "expense_id=%s source_ref=%s from_status=%s to_status=%s duration_ms=%d",
                           expense_id, source_ref, current.value, target.value,
                           _duration_ms(started))
            raise InvalidTransitionError(f"cannot transition {current.value} to {target.value}")
        expense = self.get(expense_id)
        logger.info("expense_transition outcome=applied expense_id=%s source_ref=%s "
                    "from_status=%s to_status=%s duration_ms=%d", expense_id,
                    expense.source_ref, current.value, target.value, _duration_ms(started))
        return expense

    def get(self, expense_id: str) -> Expense:
        row = self.connection.execute("SELECT * FROM expenses WHERE expense_id = ?", (expense_id,)).fetchone()
        if row is None:
            raise ExpenseRepositoryError(f"unknown expense_id {expense_id!r}")
        return _expense(row)

    def finalize_ledger_write(self, expense_id: str, finance_ledger_ref: str) -> Expense:
        """Atomically retain a writer-issued reference and mark an expense written.

        This is intentionally the only repository operation which may set a
        finance reference.  It refuses overwrites, unresolved capture
        collisions, and any state other than ``ledger_ready``.
        """
        _require_nonempty(finance_ledger_ref, "finance_ledger_ref")
        started = time.monotonic()
        with self.connection:
            row = self.connection.execute(
                "SELECT * FROM expenses WHERE expense_id = ?", (expense_id,)
            ).fetchone()
            if row is None:
                raise ExpenseRepositoryError(f"unknown expense_id {expense_id!r}")
            current = ExpenseStatus(row["status"])
            if current is not ExpenseStatus.LEDGER_READY:
                self._event(expense_id, "transition", current.value,
                            ExpenseStatus.LEDGER_WRITTEN.value, "rejected",
                            "invalid_transition", started)
                raise InvalidTransitionError(
                    f"cannot transition {current.value} to ledger_written"
                )
            if row["finance_ledger_ref"] is not None:
                self._event(expense_id, "transition", current.value,
                            ExpenseStatus.LEDGER_WRITTEN.value, "rejected",
                            "finance_reference_already_set", started)
                raise ExpenseRepositoryError("finance_ledger_ref is already set")
            collision = self.connection.execute(
                "SELECT 1 FROM expense_capture_collisions WHERE expense_id = ? LIMIT 1",
                (expense_id,),
            ).fetchone()
            if collision is not None:
                self._event(expense_id, "transition", current.value,
                            ExpenseStatus.LEDGER_WRITTEN.value, "rejected",
                            "capture_collision_unresolved", started)
                raise ExpenseRepositoryError("expense has unresolved capture collisions")
            try:
                self.connection.execute(
                    "UPDATE expenses SET finance_ledger_ref = ?, status = ?, updated_at = ? "
                    "WHERE expense_id = ?",
                    (finance_ledger_ref, ExpenseStatus.LEDGER_WRITTEN.value, _now(), expense_id),
                )
            except sqlite3.IntegrityError as exc:
                self._event(expense_id, "transition", current.value,
                            ExpenseStatus.LEDGER_WRITTEN.value, "rejected",
                            "finance_reference_conflict", started)
                raise ExpenseRepositoryError("finance_ledger_ref conflicts with another expense") from exc
            self._event(expense_id, "transition", current.value,
                        ExpenseStatus.LEDGER_WRITTEN.value, "applied", None, started)
        expense = self.get(expense_id)
        logger.info("expense_ledger_finalize outcome=applied expense_id=%s source_ref=%s "
                    "finance_ledger_ref=%s duration_ms=%d", expense_id,
                    expense.source_ref, finance_ledger_ref, _duration_ms(started))
        return expense

    def record_receipt_evidence(
        self,
        *,
        source_ref: str,
        evidence_kind: str,
        local_path: str | None = None,
        sha256: str | None = None,
        sharepoint_path: str | None = None,
        sharepoint_url: str | None = None,
        sharepoint_etag: str | None = None,
        source_timestamp: str | None = None,
    ) -> ReceiptEvidence:
        """Append receipt evidence for an existing expense identified by ``source_ref``.

        The source reference is the foreign-key link rather than a caller-supplied
        expense ID, preventing a receipt from being attached to an arbitrary or
        non-existent expense. Evidence rows have no update path and database
        triggers protect them from direct mutation too.
        """
        _require_nonempty(source_ref, "source_ref")
        _require_nonempty(evidence_kind, "evidence_kind")
        _validate_receipt_evidence(
            local_path=local_path,
            sha256=sha256,
            sharepoint_path=sharepoint_path,
            sharepoint_url=sharepoint_url,
            sharepoint_etag=sharepoint_etag,
            source_timestamp=source_timestamp,
        )
        evidence_id = str(uuid.uuid4())
        created_at = _now()
        with self.connection:
            expense = self.connection.execute(
                "SELECT 1 FROM expenses WHERE source_ref = ?", (source_ref,)
            ).fetchone()
            if expense is None:
                raise ExpenseRepositoryError(f"unknown source_ref {source_ref!r}")
            try:
                self.connection.execute(
                    "INSERT INTO receipt_evidence "
                    "(evidence_id, source_ref, evidence_kind, local_path, sha256, "
                    "sharepoint_path, sharepoint_url, sharepoint_etag, source_timestamp, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (evidence_id, source_ref, evidence_kind, local_path, sha256,
                     sharepoint_path, sharepoint_url, sharepoint_etag, source_timestamp, created_at),
                )
            except sqlite3.IntegrityError:
                # The immutable proof already exists.  Return it rather than
                # fabricating a duplicate record on a replay retry.
                existing = self.connection.execute(
                    "SELECT * FROM receipt_evidence WHERE source_ref = ? AND evidence_kind = ? "
                    "AND ifnull(sha256, '') = ifnull(?, '') "
                    "AND ifnull(sharepoint_path, '') = ifnull(?, '') "
                    "AND ifnull(sharepoint_etag, '') = ifnull(?, '') "
                    "ORDER BY created_at, rowid LIMIT 1",
                    (source_ref, evidence_kind, sha256, sharepoint_path, sharepoint_etag),
                ).fetchone()
                if existing is None:
                    raise
                return _receipt_evidence(existing)
        evidence = self.receipt_evidence(source_ref)[-1]
        logger.info("receipt_evidence_recorded evidence_id=%s source_ref=%s kind=%s",
                    evidence.evidence_id, source_ref, evidence_kind)
        return evidence

    def receipt_evidence(self, source_ref: str) -> list[ReceiptEvidence]:
        """Return receipt evidence in append order for the linked expense source."""
        _require_nonempty(source_ref, "source_ref")
        return [_receipt_evidence(row) for row in self.connection.execute(
            "SELECT * FROM receipt_evidence WHERE source_ref = ? ORDER BY created_at, rowid",
            (source_ref,),
        )]

    def events(self, expense_id: str) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            "SELECT * FROM expense_events WHERE expense_id = ? ORDER BY occurred_at, rowid", (expense_id,)
        ))

    def capture_collisions(self, expense_id: str) -> list[sqlite3.Row]:
        """Return immutable preserved payload pairs for a source-reference collision."""
        return list(self.connection.execute(
            "SELECT * FROM expense_capture_collisions WHERE expense_id = ? "
            "ORDER BY occurred_at, rowid",
            (expense_id,),
        ))

    def _record_capture_collision(self, *, expense_id: str, source_ref: str,
                                  original: Mapping[str, Any], incoming: Mapping[str, Any]) -> None:
        """Append an auditable pair; a repeated identical conflict is idempotent."""
        original_json = _canonical_json(original)
        incoming_json = _canonical_json(incoming)
        self.connection.execute(
            "INSERT INTO expense_capture_collisions "
            "(collision_id, expense_id, source_ref, original_facts_json, incoming_facts_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(expense_id, incoming_facts_json) DO NOTHING",
            (str(uuid.uuid4()), expense_id, source_ref, original_json, incoming_json, _now()),
        )

    def _event(self, expense_id: str, event_type: str, from_status: str | None,
               to_status: str | None, outcome: str, error_code: str | None,
               started: float) -> None:
        self.connection.execute(
            "INSERT INTO expense_events (event_id, expense_id, event_type, from_status, to_status, "
            "outcome, error_code, occurred_at, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), expense_id, event_type, from_status, to_status, outcome,
             error_code, _now(), _duration_ms(started)),
        )


def _validated_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "source_timestamp", "observed_timestamp", "supplier", "amount_pence", "currency",
        "expense_date", "category", "evidence_ref", "evidence_state", "settlement_state",
        "finance_ledger_ref", "validation_result",
    }
    unknown = set(facts) - allowed
    if unknown:
        raise ValueError(f"unknown expense fact(s): {sorted(unknown)}")
    result = dict(facts)
    amount = result.get("amount_pence")
    if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int) or amount < 0):
        raise ValueError("amount_pence must be a non-negative integer number of pence")
    currency = result.get("currency")
    if currency is not None and (not isinstance(currency, str) or len(currency) != 3 or not currency.isupper()):
        raise ValueError("currency must be a three-letter uppercase ISO code")
    for field in ("source_timestamp", "observed_timestamp", "supplier", "category", "evidence_ref",
                  "evidence_state", "settlement_state", "finance_ledger_ref", "validation_result"):
        if result.get(field) is not None and not isinstance(result[field], str):
            raise ValueError(f"{field} must be a string when supplied")
    expense_date = result.get("expense_date")
    if expense_date is not None:
        if not isinstance(expense_date, str):
            raise ValueError("expense_date must be an ISO date string")
        try:
            date.fromisoformat(expense_date)
        except ValueError as exc:
            raise ValueError("expense_date must be an ISO date string") from exc
    return result


def _expense(row: sqlite3.Row) -> Expense:
    values = dict(row)
    values["status"] = ExpenseStatus(values["status"])
    return Expense(**values)


def _receipt_evidence(row: sqlite3.Row) -> ReceiptEvidence:
    return ReceiptEvidence(**dict(row))


def _validate_receipt_evidence(*, local_path: str | None, sha256: str | None,
                               sharepoint_path: str | None, sharepoint_url: str | None,
                               sharepoint_etag: str | None,
                               source_timestamp: str | None) -> None:
    for field, value in {
        "local_path": local_path,
        "sharepoint_path": sharepoint_path,
        "sharepoint_url": sharepoint_url,
        "sharepoint_etag": sharepoint_etag,
        "source_timestamp": source_timestamp,
    }.items():
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field} must be a string when supplied")
    if sha256 is not None:
        if not isinstance(sha256, str) or len(sha256) != 64 or any(
            character not in "0123456789abcdef" for character in sha256
        ):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters when supplied")


def _capture_snapshot(row: sqlite3.Row) -> dict[str, Any]:
    """Return the source facts as they stood before a conflicting repeat capture."""
    fields = (
        "source_surface", "source_timestamp", "observed_timestamp", "supplier",
        "amount_pence", "currency", "expense_date", "category", "evidence_ref",
        "evidence_state", "settlement_state", "finance_ledger_ref", "validation_result",
    )
    return {field: row[field] for field in fields}


def _canonical_json(values: Mapping[str, Any]) -> str:
    return json.dumps(dict(values), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _require_nonempty(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _duration_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
