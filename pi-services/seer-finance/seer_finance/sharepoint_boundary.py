"""Public SharePoint authority adapter for Pi-side consumers.

It exposes the queue/results/cache contract without importing a Graph client.
The queue processor remains the only component allowed to perform remote
SharePoint operations.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from typing import Any

from .ledger.sharepoint_contract import (
    SharePointDocumentStore,
    SharePointContractError,
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
            "/Expenses/Expense ledger.md",
            "/Finance/Finance ledger.md",
        }:
            return _boundary_result(
                operation=operation, path=canonical, accepted=False, verified=False,
                content=content,
                blocker=(
                    "canonical SharePoint ledgers prohibit append operations; "
                    "submit a base_etag/expected_source_sha256 checked update"
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

    def read(self, path: str) -> str:
        content = self.store.read(path)
        if content is None:
            raise SharePointContractError(f"SharePoint cache has no readback for {path}")
        return content


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