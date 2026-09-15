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

import importlib
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

EXPENSE_LEDGER_PATH = "/Expenses/Expense ledger.md"
FINANCE_LEDGER_PATH = "/Finance/Finance ledger.md"


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


class QueueBoundary:
    """Operational queue adapter for deployments with an external writer.

    This is intentionally not a business-authority fallback.  It records a
    bounded retry request and reports ``verified=False`` until the writer (or
    the seer-finance implementation) performs readback.
    """

    def __init__(self, queue_path: str | Path | None = None) -> None:
        self.queue_path = Path(
            queue_path
            or os.environ.get(
                "OPENCLAW_SHAREPOINT_QUEUE",
                str(Path.home() / ".openclaw" / "sharepoint-queue.json"),
            )
        )
        self.lock_path = Path(
            os.environ.get(
                "SEER_FINANCE_SHAREPOINT_QUEUE_LOCK",
                str(self.queue_path.parent / "integrations" / "microsoft" / "sp-queue.lock"),
            )
        )

    def write_verified(
        self,
        path: str,
        content: str,
        *,
        operation: str = "append",
        base_etag: str | None = None,
        expected_source_sha256: str | None = None,
    ) -> BoundaryResult:
        if operation not in {"create", "update", "append"}:
            raise ValueError("unsupported SharePoint write operation")
        if path not in {EXPENSE_LEDGER_PATH, FINANCE_LEDGER_PATH}:
            raise ValueError("finance boundary only permits canonical ledger paths")
        if path in {EXPENSE_LEDGER_PATH, FINANCE_LEDGER_PATH} and (
            operation != "update" or not base_etag or not expected_source_sha256
        ):
            return BoundaryResult(
                operation=operation,
                path=path,
                accepted=False,
                verified=False,
                blocker=(
                    "canonical ledger queue requests require seer-finance "
                    "base_etag and expected_source_sha256"
                ),
            )
        if expected_source_sha256 and (
            len(expected_source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_source_sha256.lower())
        ):
            raise ValueError("expected_source_sha256 must be a SHA-256 hex digest")
        operation_id = "finance-boundary-" + hashlib.sha256(
            f"{path}\0{content}\0{base_etag or ''}\0{expected_source_sha256 or ''}".encode("utf-8")
        ).hexdigest()
        item = {
            "id": operation_id,
            "operation": operation,
            "path": path,
            "content": content,
            "verify_readback": True,
            "no_totp": True,
        }
        if base_etag:
            item["base_etag"] = base_etag
        if expected_source_sha256:
            item["expected_source_sha256"] = expected_source_sha256.lower()
        self.enqueue_operation(item)
        return BoundaryResult(
            operation=operation,
            path=path,
            accepted=True,
            verified=False,
            blocker="SharePoint write queued; verified readback is pending",
        )

    def enqueue_operation(self, operation: Mapping[str, Any]) -> bool:
        """Append using the same flock/atomic producer protocol as the processor."""
        if not isinstance(operation, Mapping):
            raise TypeError("SharePoint queue operation must be an object")
        item = dict(operation)
        operation_id = str(item.get("id") or "").strip()
        if not operation_id:
            raise ValueError("SharePoint queue operation requires a stable id")
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                try:
                    current = json.loads(self.queue_path.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    current = []
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise SharePointBoundaryError(
                        f"SharePoint operation queue is malformed: {exc}"
                    ) from exc
                if not isinstance(current, list):
                    raise SharePointBoundaryError("SharePoint operation queue is malformed")
                if any(
                    isinstance(existing, dict) and str(existing.get("id", "")) == operation_id
                    for existing in current
                ):
                    return False
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.queue_path.parent,
                    prefix=f".{self.queue_path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    json.dump(current + [item], handle, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                    temporary = Path(handle.name)
                temporary.replace(self.queue_path)
                return True
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def read(self, path: str) -> str:
        raise SharePointBoundaryError(
            f"SharePoint readback unavailable for {path}; queued writes remain operational recovery state"
        )


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
        kwargs: dict[str, Any] = {"operation": operation}
        if base_etag is not None:
            kwargs["base_etag"] = base_etag
        if expected_source_sha256 is not None:
            kwargs["expected_source_sha256"] = expected_source_sha256
        return self.transport.write_verified(path, content, **kwargs)

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

    def append_validated_expense(self, candidate: Mapping[str, Any]) -> BoundaryResult:
        module = importlib.import_module("seer_finance.ledger.sharepoint_finance_writer")
        loader = importlib.import_module("seer_finance.ledger.loader")
        try:
            transaction = loader.parse_transaction(dict(candidate), 0)
            reference = module.SharePointFinanceWriter(store=self.store).validate_and_write(transaction)
        except Exception as exc:
            return BoundaryResult(
                operation="append",
                path=FINANCE_LEDGER_PATH,
                accepted=True,
                verified=False,
                blocker=f"SharePoint finance write pending readback: {exc}",
            )
        return BoundaryResult(
            operation="append",
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
    if os.environ.get("OPENCLAW_SHAREPOINT_QUEUE"):
        return QueueBoundary()
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