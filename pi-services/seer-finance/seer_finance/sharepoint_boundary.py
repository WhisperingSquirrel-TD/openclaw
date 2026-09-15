"""Public SharePoint authority adapter for Pi-side consumers.

It exposes the queue/results/cache contract without importing a Graph client.
The queue processor remains the only component allowed to perform remote
SharePoint operations.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from typing import Any, Mapping

from .ledger.sharepoint_contract import (
    SharePointDocumentStore,
    SharePointContractError,
    SharePointWritePending,
    _clean_path,
)


@dataclass(frozen=True)
class BoundaryResult:
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


class SharePointBoundary:
    def __init__(self, *, store: SharePointDocumentStore | None = None, **store_paths: Any) -> None:
        self.store = store or SharePointDocumentStore(**store_paths)

    def write_verified(self, path: str, content: str, *, operation: str = "update") -> BoundaryResult:
        canonical = _clean_path(path)
        if operation.lower() == "append" and canonical in {
            "/Expenses/Expense ledger.xlsx",
            "/Finance/Finance ledger.xlsx",
        }:
            return _boundary_result(
                operation=operation, path=canonical, accepted=False, verified=False,
                content=content,
                blocker=(
                    "canonical SharePoint ledgers prohibit append operations; "
                    "submit a base_etag/expected_source_sha256 checked workbook update"
                ),
            )
        if canonical.lower().endswith(".xlsx"):
            return _boundary_result(
                operation=operation, path=canonical, accepted=False, verified=False,
                content=content,
                blocker=(
                    "canonical XLSX ledgers require write_workbook_verified with "
                    "content_base64/content_sha256/base_etag/expected_source_sha256"
                ),
            )
        try:
            reference = self.store.write(path=canonical, content=content)
        except SharePointContractError as exc:
            return _boundary_result(
                operation=operation, path=canonical, accepted=True, verified=False,
                content=content, blocker=str(exc),
            )
        return _boundary_result(
            operation=operation, path=canonical, accepted=True, verified=True,
            canonical_ref=reference, content=content,
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
        semantic_workbook_sha256: str | None = None,
        operation: str = "update_workbook",
    ) -> BoundaryResult:
        """Submit a binary-safe workbook update through the Pi queue contract."""
        canonical = _clean_path(path)
        if not canonical.lower().endswith(".xlsx"):
            return _boundary_result(
                operation=operation, path=canonical, accepted=False, verified=False,
                blocker="write_workbook_verified requires an .xlsx canonical path",
            )
        try:
            reference = self.store.write_workbook(
                path=canonical,
                content_base64=content_base64,
                content_sha256=content_sha256,
                base_etag=base_etag,
                expected_source_sha256=expected_source_sha256,
                expected_snapshot=expected_snapshot,
                semantic_workbook_sha256=semantic_workbook_sha256,
            )
        except (SharePointContractError, ValueError) as exc:
            return _boundary_result(
                operation=operation, path=canonical,
                accepted=not isinstance(exc, ValueError), verified=False,
                content=content_base64, blocker=str(exc),
            )
        return _boundary_result(
            operation=operation, path=canonical, accepted=True, verified=True,
            canonical_ref=reference, content=content_base64,
        )

    def read(self, path: str) -> Any:
        content = self.store.read(path)
        if content is None:
            raise SharePointContractError(f"SharePoint cache has no readback for {path}")
        return content

    def read_workbook_snapshot(self, path: str) -> dict[str, Any]:
        """Return validated raw XLSX bytes and both transport hashes."""
        return self.store.read_workbook_snapshot(path)

    def upload_receipt_verified(
        self,
        *,
        path: str,
        source_ref: str,
        local_path: str,
        content_sha256: str,
        mime_type: str,
    ) -> BoundaryResult:
        """Upload receipt evidence through the existing verified queue transport."""
        canonical = _clean_path(path)
        try:
            proof = self.store.upload_binary(
                path=canonical,
                source_path=local_path,
                content_sha256=content_sha256,
                mime_type=mime_type,
                delivery={"kind": "seer_finance_receipt", "source_ref": source_ref},
            )
        except SharePointWritePending as exc:
            return _boundary_result(
                operation="upload_binary",
                path=canonical,
                accepted=True,
                verified=False,
                blocker=str(exc),
            )
        except (SharePointContractError, ValueError) as exc:
            return _boundary_result(
                operation="upload_binary",
                path=canonical,
                accepted=False,
                verified=False,
                blocker=str(exc),
            )
        return _boundary_result(
            operation="upload_binary",
            path=canonical,
            accepted=True,
            verified=True,
            canonical_ref=f"{canonical}#{proof['etag']}",
        )


def get_boundary() -> SharePointBoundary:
    return SharePointBoundary()


BOUNDARY = get_boundary


def _boundary_result(**values: Any) -> Any:
    """Use the Pi adapter's result class when this module is loaded by watcher."""
    try:
        external = importlib.import_module("sharepoint_boundary")
        result_type = getattr(external, "BoundaryResult", None)
        if result_type is not None and result_type is not BoundaryResult:
            return result_type(**values)
    except ImportError:
        pass
    return BoundaryResult(**values)