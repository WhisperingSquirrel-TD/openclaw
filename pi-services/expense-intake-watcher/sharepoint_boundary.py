"""Small adapter for the SharePoint-authoritative seer-finance boundary.

The watcher owns source observation and recovery state only.  It must not
create a local business ledger while the SharePoint boundary is unavailable.
The seer-finance package supplies the live implementation in deployments; this
module deliberately talks to it through a tiny duck-typed protocol so the
watcher remains usable in tests and during a staged cutover.

Routine writes are expected to be no-TOTP writes performed by the background
SharePoint writer.  A write is successful only when that boundary reports a
verified readback.  Queueing a write, or receiving an upload URL, is not proof
that the canonical document contains the requested content.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

EXPENSE_LEDGER_PATH = "/Expenses/Expense ledger.xlsx"
FINANCE_LEDGER_PATH = "/Finance/Finance ledger.xlsx"


class SharePointBoundaryError(RuntimeError):
    """The authoritative SharePoint boundary could not complete safely."""


@dataclass(frozen=True)
class BoundaryResult:
    """Result returned by a boundary operation.

    ``verified`` is intentionally separate from ``accepted``.  The latter can
    mean that an operation was queued for retry; only verified readback may be
    used as business completion proof.
    """

    operation: str
    path: str
    accepted: bool
    verified: bool
    canonical_ref: str | None = None
    content: str | None = None
    blocker: str | None = None

    @property
    def complete(self) -> bool:
        return self.accepted and self.verified

    @property
    def expense_id(self) -> str | None:
        """Compatibility name for source adapters during the cutover."""
        return self.canonical_ref


@runtime_checkable
class SharePointBoundary(Protocol):
    """Public protocol implemented by seer-finance's live authority.

    Implementations must perform the write through their routine no-TOTP
    service account and read the document back before returning ``verified``.
    ``write_verified`` may also accept ``operation`` as a keyword argument.
    """

    def write_verified(
        self,
        path: str,
        content: str,
        *,
        operation: str = "append",
        base_etag: str | None = None,
        expected_source_sha256: str | None = None,
    ) -> BoundaryResult:
        ...

    def read(self, path: str) -> str:
        ...


class UnavailableBoundary:
    """Fail-closed implementation used until the live boundary is installed."""

    def write_verified(
        self,
        path: str,
        content: str,
        *,
        operation: str = "append",
        base_etag: str | None = None,
        expected_source_sha256: str | None = None,
    ) -> BoundaryResult:
        return BoundaryResult(
            operation=operation,
            path=path,
            accepted=False,
            verified=False,
            blocker="seer-finance SharePoint authority is unavailable",
        )

    def read(self, path: str) -> str:
        raise SharePointBoundaryError(
            "seer-finance SharePoint authority is unavailable; no local ledger fallback is permitted"
        )

    def write_workbook_verified(
        self,
        path: str,
        content_base64: str,
        *,
        content_sha256: str,
        base_etag: str,
        expected_source_sha256: str,
        expected_snapshot: Mapping[str, Any] | None = None,
        semantic_sha256: str,
    ) -> BoundaryResult:
        del (
            content_base64,
            content_sha256,
            base_etag,
            expected_source_sha256,
            expected_snapshot,
            semantic_sha256,
        )
        return BoundaryResult(
            operation="update_workbook",
            path=path,
            accepted=False,
            verified=False,
            blocker="seer-finance workbook authority is unavailable",
        )

    update_workbook = write_workbook_verified


class QueueBoundary(UnavailableBoundary):
    """Compatibility name for the retired direct-queue adapter.

    Older tests/importers may still refer to ``QueueBoundary``.  It deliberately
    performs no filesystem queue operation: canonical workbook writes can only
    use the seer-finance boundary, and an unavailable boundary must fail closed.
    """

    def __init__(self, queue_path: str | Path | None = None) -> None:
        del queue_path


class _ReadbackRequiredStore:
    """Give seer-finance repositories a fail-closed cache view.

    ``SharePointDocumentStore.read`` returns ``None`` for a missing cache so
    callers can choose an initialization policy.  Expense capture and finance
    posting must not choose that policy: an absent authoritative document is a
    deployment/readback blocker, never an empty document to append against.
    """

    def __init__(self, transport: Any) -> None:
        self.transport = transport
        self.store = transport.store
        self._snapshots: dict[str, str] = {}
        self._workbook_snapshots: dict[str, tuple[str, str]] = {}

    def read(self, path: str) -> str:
        content = self.transport.read(path)
        self._snapshots[path] = content
        return content

    def write(self, **kwargs: Any) -> str:
        path = str(kwargs.get("path", ""))
        expected = self._snapshots.get(path)
        if expected is None:
            raise SharePointBoundaryError(
                f"cannot write {path}: authoritative cache was not read first"
            )
        current = self.transport.read(path)
        if current != expected:
            raise SharePointBoundaryError(
                f"cannot write {path}: authoritative cache changed during preparation"
            )
        return self.store.write(**kwargs)

    def read_workbook_snapshot(self, path: str) -> dict[str, Any]:
        """Read an authenticated XLSX snapshot and retain its exact base proof.

        The repositories deliberately depend on this richer interface rather
        than ``read()``: workbook updates need the original bytes' SHA-256 and
        native eTag, not a decoded text representation.
        """
        reader = getattr(self.transport, "read_workbook_snapshot", None)
        if not callable(reader):
            reader = getattr(self.store, "read_workbook_snapshot", None)
        if not callable(reader):
            raise SharePointBoundaryError(
                "seer-finance transport does not expose read_workbook_snapshot"
            )
        snapshot = reader(path)
        if not isinstance(snapshot, dict):
            raise SharePointBoundaryError("seer-finance workbook snapshot is not an object")
        etag = snapshot.get("etag")
        content_sha256 = snapshot.get("content_sha256")
        content_bytes = snapshot.get("content_bytes")
        if (
            not isinstance(etag, str)
            or not etag
            or not isinstance(content_sha256, str)
            or not content_sha256
            or not isinstance(content_bytes, (bytes, bytearray))
        ):
            raise SharePointBoundaryError(
                "seer-finance workbook snapshot lacks authenticated bytes, etag, or hash"
            )
        if hashlib.sha256(bytes(content_bytes)).hexdigest() != content_sha256:
            raise SharePointBoundaryError(
                f"seer-finance workbook snapshot hash does not match authenticated bytes for {path}"
            )
        self._workbook_snapshots[path] = (etag, content_sha256)
        return snapshot

    def write_workbook(self, **kwargs: Any) -> str:
        """Write only against the exact workbook snapshot previously read."""
        path = str(kwargs.get("path", ""))
        expected = self._workbook_snapshots.get(path)
        if expected is None:
            raise SharePointBoundaryError(
                f"cannot write {path}: authoritative workbook was not read first"
            )
        if kwargs.get("base_etag") != expected[0]:
            raise SharePointBoundaryError(
                f"cannot write {path}: base_etag does not match the authenticated snapshot"
            )
        if kwargs.get("expected_source_sha256") != expected[1]:
            raise SharePointBoundaryError(
                f"cannot write {path}: expected_source_sha256 does not match the authenticated snapshot"
            )
        encoded = kwargs.get("content_base64")
        content_sha256 = kwargs.get("content_sha256")
        if not isinstance(encoded, str) or not isinstance(content_sha256, str):
            raise SharePointBoundaryError(
                f"cannot write {path}: workbook content and content_sha256 are required"
            )
        try:
            content_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise SharePointBoundaryError(
                f"cannot write {path}: workbook content_base64 is invalid"
            ) from exc
        if hashlib.sha256(content_bytes).hexdigest() != content_sha256:
            raise SharePointBoundaryError(
                f"cannot write {path}: content_sha256 does not match content_base64"
            )
        current = self.read_workbook_snapshot(path)
        if (current.get("etag"), current.get("content_sha256")) != expected:
            raise SharePointBoundaryError(
                f"cannot write {path}: authoritative workbook changed during preparation"
            )
        writer = getattr(self.store, "write_workbook", None)
        if not callable(writer):
            raise SharePointBoundaryError(
                "seer-finance transport does not expose write_workbook"
            )
        return writer(**kwargs)


class _SeerFinanceBoundaryAdapter:
    """Adapt the concurrent seer-finance public boundary to this protocol."""

    def __init__(self, transport: Any) -> None:
        self.transport = transport
        self.store = _ReadbackRequiredStore(transport)

    def write_verified(
        self,
        path: str,
        content: str,
        *,
        operation: str = "append",
        base_etag: str | None = None,
        expected_source_sha256: str | None = None,
    ) -> BoundaryResult:
        if path in {EXPENSE_LEDGER_PATH, FINANCE_LEDGER_PATH} or path.lower().endswith(".xlsx"):
            return BoundaryResult(
                operation=operation,
                path=path,
                accepted=False,
                verified=False,
                blocker=(
                    "canonical XLSX paths require seer-finance "
                    "write_workbook_verified/update_workbook"
                ),
            )
        kwargs: dict[str, Any] = {"operation": operation}
        if base_etag is not None:
            kwargs["base_etag"] = base_etag
        if expected_source_sha256 is not None:
            kwargs["expected_source_sha256"] = expected_source_sha256
        return self.transport.write_verified(path, content, **kwargs)

    def write_workbook_verified(
        self,
        path: str,
        content_base64: str,
        *,
        content_sha256: str,
        base_etag: str,
        expected_source_sha256: str,
        expected_snapshot: Mapping[str, Any] | None = None,
        semantic_sha256: str,
    ) -> BoundaryResult:
        """Forward the complete workbook contract without queue-file access."""
        method = getattr(self.transport, "write_workbook_verified", None)
        if not callable(method):
            return BoundaryResult(
                operation="update_workbook",
                path=path,
                accepted=False,
                verified=False,
                blocker="seer-finance workbook boundary is unavailable",
            )
        snapshot_kwargs = (
            {"expected_snapshot": expected_snapshot}
            if expected_snapshot is not None
            else {}
        )
        try:
            result = method(
                path,
                content_base64,
                content_sha256=content_sha256,
                base_etag=base_etag,
                expected_source_sha256=expected_source_sha256,
                **snapshot_kwargs,
                semantic_sha256=semantic_sha256,
            )
        except TypeError as exc:
            # Current seer-finance releases used the longer internal keyword;
            # keep the public watcher contract stable while accepting that
            # release during the staged deployment.
            if "semantic_sha256" not in str(exc):
                raise
            result = method(
                path,
                content_base64,
                content_sha256=content_sha256,
                base_etag=base_etag,
                expected_source_sha256=expected_source_sha256,
                **snapshot_kwargs,
                semantic_workbook_sha256=semantic_sha256,
            )
        if not isinstance(result, BoundaryResult):
            raise SharePointBoundaryError("seer-finance workbook boundary returned an invalid result")
        return result

    update_workbook = write_workbook_verified

    def upload_receipt_verified(
        self,
        *,
        path: str,
        source_ref: str,
        local_path: Path,
        content_sha256: str,
        mime_type: str,
    ) -> BoundaryResult:
        """Forward receipt evidence when the authority explicitly supports it."""
        method = getattr(self.transport, "upload_receipt_verified", None)
        if not callable(method):
            return BoundaryResult(
                operation="upload_binary",
                path=path,
                accepted=False,
                verified=False,
                blocker="seer-finance receipt boundary is unavailable",
            )
        result = method(
            path=path,
            source_ref=source_ref,
            local_path=local_path,
            content_sha256=content_sha256,
            mime_type=mime_type,
        )
        if not isinstance(result, BoundaryResult):
            raise SharePointBoundaryError("seer-finance receipt boundary returned an invalid result")
        return result

    def read(self, path: str) -> str:
        return self.transport.read(path)

    def capture_candidate(
        self,
        *,
        source_surface: str,
        source_ref: str,
        facts: Mapping[str, Any],
    ) -> BoundaryResult:
        module = importlib.import_module("seer_finance.ledger.sharepoint_repository")
        repository = module.SharePointExpenseRepository(store=self.store)
        try:
            expense = repository.capture(
                source_surface=source_surface,
                source_ref=source_ref,
                **dict(facts),
            )
        except Exception as exc:
            return BoundaryResult(
                operation="capture",
                path=EXPENSE_LEDGER_PATH,
                accepted=True,
                verified=False,
                blocker=f"SharePoint expense capture pending readback: {exc}",
            )
        return BoundaryResult(
            operation="capture",
            path=EXPENSE_LEDGER_PATH,
            accepted=True,
            verified=True,
            canonical_ref=f"{EXPENSE_LEDGER_PATH}#{expense.expense_id}",
        )

    def update_validated_expense(self, candidate: Mapping[str, Any]) -> BoundaryResult:
        module = importlib.import_module("seer_finance.ledger.sharepoint_finance_writer")
        loader = importlib.import_module("seer_finance.ledger.loader")
        try:
            transaction = loader.parse_transaction(dict(candidate), 0)
            reference = module.SharePointFinanceWriter(store=self.store).validate_and_write(transaction)
        except Exception as exc:
            return BoundaryResult(
                operation="update_workbook",
                path=FINANCE_LEDGER_PATH,
                accepted=True,
                verified=False,
                blocker=f"SharePoint finance write pending readback: {exc}",
            )
        return BoundaryResult(
            operation="update_workbook",
            path=FINANCE_LEDGER_PATH,
            accepted=True,
            verified=True,
            canonical_ref=reference,
        )

def _candidate_modules() -> tuple[str, ...]:
    # The Pi service is installed beside the source-only seer-finance package,
    # not as a system package.  Add that package root only for its public
    # SharePoint boundary; no private/local ledger modules are imported.
    for root in (
        os.environ.get("SEER_FINANCE_CODE_ROOT"),
        str(Path(__file__).resolve().parent.parent / "seer-finance"),
        "/home/tomdean88/pi-services/seer-finance",
    ):
        if root and (Path(root) / "seer_finance").is_dir() and root not in sys.path:
            sys.path.insert(0, root)
    configured = os.environ.get("SEER_FINANCE_BOUNDARY_MODULE")
    return tuple(
        item
        for item in (
            configured,
            "seer_finance.sharepoint_boundary",
            "seer_finance.ledger.sharepoint_boundary",
        )
        if item
    )


def resolve_boundary() -> SharePointBoundary:
    """Load the concurrent seer-finance authority without inventing a fallback."""
    for module_name in _candidate_modules():
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for name in ("get_boundary", "get_sharepoint_boundary", "BOUNDARY"):
            candidate = getattr(module, name, None)
            if callable(candidate) and name != "BOUNDARY":
                candidate = candidate()
            if isinstance(candidate, SharePointBoundary):
                return _SeerFinanceBoundaryAdapter(candidate)
    return UnavailableBoundary()


def write_verified(
    path: str,
    content: str,
    *,
    operation: str = "append",
    base_etag: str | None = None,
    expected_source_sha256: str | None = None,
    boundary: SharePointBoundary | None = None,
) -> BoundaryResult:
    """Write through the authority and require verified readback."""
    if path in {EXPENSE_LEDGER_PATH, FINANCE_LEDGER_PATH} or path.lower().endswith(".xlsx"):
        return BoundaryResult(
            operation=operation,
            path=path,
            accepted=False,
            verified=False,
            blocker=(
                "canonical XLSX paths require seer-finance "
                "write_workbook_verified/update_workbook"
            ),
        )
    target = boundary or resolve_boundary()
    kwargs: dict[str, Any] = {"operation": operation}
    if base_etag is not None:
        kwargs["base_etag"] = base_etag
    if expected_source_sha256 is not None:
        kwargs["expected_source_sha256"] = expected_source_sha256
    result = target.write_verified(path, content, **kwargs)
    if not isinstance(result, BoundaryResult):
        raise SharePointBoundaryError("seer-finance boundary returned an invalid result")
    return result


def capture_candidate(
    *,
    source_surface: str,
    source_ref: str,
    facts: Mapping[str, Any] | None = None,
    boundary: SharePointBoundary | None = None,
) -> BoundaryResult:
    """Capture source facts through the public seer-finance boundary.

    A boundary may expose a richer ``capture_candidate`` method.  Otherwise
    this generic adapter fails closed rather than serialising a second ledger.
    """
    target = boundary or resolve_boundary()
    method = getattr(target, "capture_candidate", None)
    if callable(method):
        result = method(
            source_surface=source_surface,
            source_ref=source_ref,
            facts=dict(facts or {}),
        )
        if not isinstance(result, BoundaryResult):
            raise SharePointBoundaryError("seer-finance capture returned an invalid result")
        return result
    return BoundaryResult(
        operation="capture",
        path=EXPENSE_LEDGER_PATH,
        accepted=False,
        verified=False,
        canonical_ref=None,
        blocker=(
            "seer-finance SharePoint capture boundary is unavailable; "
            "candidate retained for operational retry only"
        ),
    )