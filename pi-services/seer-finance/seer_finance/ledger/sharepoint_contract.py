"""Queue/results/cache boundary for the authoritative SharePoint ledgers.

This module deliberately does not import Graph clients or perform network calls.
The Pi SharePoint queue processor is the transport.  A write is usable only
after its queue result reports processed success *and* the corresponding cache
file contains the exact submitted document.
"""

from __future__ import annotations

import hashlib
import base64
import binascii
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

EXPENSE_LEDGER_PATH = "/Expenses/Expense ledger.xlsx"
FINANCE_LEDGER_PATH = "/Finance/Finance ledger.xlsx"
LEGACY_EXPENSE_LEDGER_PATH = "/Expenses/Expense ledger.md"
LEGACY_FINANCE_LEDGER_PATH = "/Finance/Finance ledger.md"

DEFAULT_QUEUE_PATH = Path(
    os.environ.get("SEER_FINANCE_SHAREPOINT_QUEUE", str(Path.home() / ".openclaw/sharepoint-queue.json"))
)
DEFAULT_RESULTS_PATH = Path(
    os.environ.get(
        "SEER_FINANCE_SHAREPOINT_RESULTS",
        str(Path.home() / ".openclaw/sharepoint-queue-results.json"),
    )
)
DEFAULT_CACHE_ROOT = Path(
    os.environ.get(
        "SEER_FINANCE_SHAREPOINT_CACHE",
        str(Path.home() / ".openclaw/workspace/sharepoint-cache"),
    )
)
MAX_CACHE_AGE_SECONDS = int(
    os.environ.get("SEER_FINANCE_SHAREPOINT_MAX_CACHE_AGE_SECONDS", "3600")
)


class SharePointContractError(RuntimeError):
    """The local Pi queue/results/cache contract is unavailable or malformed."""


class SharePointWritePending(SharePointContractError):
    """A write has not yet been both processed successfully and read back."""


class SharePointCacheUnavailable(SharePointContractError):
    """The canonical cache lacks an authenticated, fresh document snapshot."""


class SharePointMutationBlocked(SharePointWritePending):
    """A prior local mutation is still unresolved or has a stale base."""


class SharePointRebaseRequired(SharePointWritePending):
    """The remote writer rejected a stale base; caller must retry on fresh cache."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # mkstemp is private on supported platforms, but keep the transport
        # contract explicit so a queue rewrite cannot inherit a wider mode
        # from a future implementation or filesystem wrapper.
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _clean_path(path: str) -> str:
    clean = str(path).strip()
    if not clean.startswith("/") or ".." in Path(clean).parts:
        raise ValueError("SharePoint path must be an absolute path without '..'")
    return "/" + clean.strip("/")


def cache_path(cache_root: str | Path, sharepoint_path: str) -> Path:
    """Map one canonical SharePoint path into the Pi content cache safely."""
    clean = _clean_path(sharepoint_path)
    relative = Path(clean.lstrip("/"))
    root = Path(cache_root).resolve()
    destination = (root / relative).resolve()
    if root != destination and root not in destination.parents:
        raise ValueError("SharePoint cache path escapes cache root")
    return destination


def cache_body(raw: str) -> str:
    """Remove the optional poller header while preserving document content."""
    header_end = raw.find("\n")
    if header_end <= 0:
        return raw
    header = raw[:header_end]
    # This is exactly the two-newline prefix emitted by
    # sharepoint_cache_poller._write_cached_file: the generated header's line
    # ending plus one separator newline. Do not normalize or strip content
    # after that separator; leading blank lines are document bytes.
    if (
        header.startswith("<!-- sharepoint-cache: /")
        and " | synced: " in header
        and header.endswith(" -->")
        and raw.startswith("\n", header_end + 1)
    ):
        return raw[header_end + 2:]
    return raw


class SharePointDocumentStore:
    """Small synchronous facade over the Pi's asynchronous write contract."""

    def __init__(
        self,
        *,
        queue_path: str | Path = DEFAULT_QUEUE_PATH,
        results_path: str | Path = DEFAULT_RESULTS_PATH,
        cache_root: str | Path = DEFAULT_CACHE_ROOT,
    ) -> None:
        self.queue_path = Path(queue_path)
        self.results_path = Path(results_path)
        self.cache_root = Path(cache_root)
        # This is the same lock used by the Pi queue processor for the default
        # ~/.openclaw queue.  A configurable queue gets a sibling state root so
        # tests/recovery sandboxes never contend on the live Pi lock.
        default_lock = self.queue_path.parent / "integrations" / "microsoft" / "sp-queue.lock"
        self.queue_lock_path = Path(
            os.environ.get("SEER_FINANCE_SHAREPOINT_QUEUE_LOCK", str(default_lock))
        )
        self.journal_path = Path(os.environ.get(
            "SEER_FINANCE_SHAREPOINT_MUTATION_JOURNAL",
            str(self.queue_path.parent / "seer-finance-mutation-journal.json"),
        ))

    def read(self, path: str) -> Any:
        if _is_workbook_path(path):
            return self.read_workbook_snapshot(path)["content_bytes"]  # type: ignore[return-value]
        return self.read_snapshot(path)["content"]

    def read_snapshot(self, path: str) -> dict[str, Any]:
        """Read content only with manifest proof of its remote identity/freshness."""
        clean = _clean_path(path)
        if _is_workbook_path(clean):
            return self.read_workbook_snapshot(clean)  # type: ignore[return-value]
        destination = cache_path(self.cache_root, clean)
        manifest_path = self.cache_root / ".manifest.json"
        try:
            raw = destination.read_text(encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SharePointCacheUnavailable(
                f"canonical SharePoint cache is missing for {clean}; bootstrap is not implicit"
            ) from exc
        except (OSError, UnicodeError) as exc:
            raise SharePointCacheUnavailable(f"cannot read SharePoint cache for {clean}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SharePointCacheUnavailable(f"SharePoint cache manifest is malformed: {exc}") from exc
        if not isinstance(manifest, dict) or not isinstance(manifest.get("cached"), dict):
            raise SharePointCacheUnavailable("SharePoint cache manifest has no cached file records")
        relative = clean.lstrip("/")
        entry = (
            manifest["cached"].get(relative)
            or manifest["cached"].get(clean)
            or next(
                (
                    item for item in manifest["cached"].values()
                    if isinstance(item, dict) and item.get("sp_path", "").strip("/") == relative
                ),
                None,
            )
        )
        if not isinstance(entry, dict):
            raise SharePointCacheUnavailable(f"SharePoint cache manifest has no record for {clean}")
        nested = entry.get("remote") if isinstance(entry.get("remote"), dict) else {}
        etag = _metadata_value(entry, nested, "etag", "eTag", "sp_etag", "remote_etag")
        version = _metadata_value(
            entry, nested, "version", "sp_version", "remote_version", "cTag", "ctag"
        )
        synced_at = _metadata_value(entry, nested, "synced_at", "syncedAt", "fetched_at")
        declared_hash = _metadata_value(
            entry, nested, "content_sha256", "content_hash", "sha256", "hash"
        )
        if not etag or not version or not synced_at or entry.get("stale") is True:
            raise SharePointCacheUnavailable(
                f"SharePoint cache record for {clean} lacks fresh remote etag/version metadata"
            )
        if not declared_hash:
            raise SharePointCacheUnavailable(
                f"SharePoint cache record for {clean} lacks content hash metadata"
            )
        body = cache_body(raw)
        content_hash = _content_hash(body)
        if declared_hash != content_hash:
            raise SharePointCacheUnavailable(
                f"SharePoint cache content hash mismatch for {clean}"
            )
        try:
            synced = datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SharePointCacheUnavailable(
                f"SharePoint cache freshness timestamp is invalid for {clean}"
            ) from exc
        if synced.tzinfo is None:
            raise SharePointCacheUnavailable(
                f"SharePoint cache freshness timestamp is stale or invalid for {clean}"
            )
        age_seconds = (datetime.now(timezone.utc) - synced).total_seconds()
        if synced > datetime.now(timezone.utc) or age_seconds > MAX_CACHE_AGE_SECONDS:
            raise SharePointCacheUnavailable(
                f"SharePoint cache freshness timestamp is stale or invalid for {clean}"
            )
        return {
            "content": body,
            "etag": str(etag),
            "version": str(version),
            "synced_at": str(synced_at),
            "content_sha256": content_hash,
        }

    def read_workbook_snapshot(self, path: str) -> dict[str, Any]:
        """Read and validate an authenticated raw XLSX cache entry.

        ``content_sha256`` is always the SHA-256 of the exact bytes on disk.
        The semantic hash is computed from visible editable tables and is
        intentionally separate because Office may rewrite ZIP/XML metadata on
        readback without changing ledger meaning.
        """
        clean = _clean_path(path)
        if not _is_workbook_path(clean):
            raise SharePointCacheUnavailable(f"{clean} is not an XLSX SharePoint ledger path")
        destination, entry = self._validated_cache_entry(clean, binary=True)
        try:
            content_bytes = destination.read_bytes()
        except (OSError, IOError) as exc:
            raise SharePointCacheUnavailable(
                f"cannot read SharePoint workbook cache for {clean}: {exc}"
            ) from exc
        content_hash = _bytes_hash(content_bytes)
        declared_hash = _metadata_value(
            entry,
            entry.get("remote") if isinstance(entry.get("remote"), dict) else {},
            "content_sha256",
            "content_hash",
            "sha256",
            "hash",
        )
        if declared_hash != content_hash:
            raise SharePointCacheUnavailable(
                f"SharePoint workbook cache content hash mismatch for {clean}"
            )
        try:
            from .workbook_codec import WorkbookCodec, WorkbookCodecError
            semantic_hash = WorkbookCodec.semantic_hash(content_bytes)
        except (WorkbookCodecError, ValueError) as exc:
            raise SharePointCacheUnavailable(
                f"SharePoint workbook cache is malformed for {clean}: {exc}"
            ) from exc
        nested = entry.get("remote") if isinstance(entry.get("remote"), dict) else {}
        declared_semantic = _metadata_value(
            entry, nested, "semantic_sha256", "semantic_workbook_sha256"
        )
        if declared_semantic and declared_semantic != semantic_hash:
            raise SharePointCacheUnavailable(
                f"SharePoint workbook semantic hash mismatch for {clean}"
            )
        return {
            "content": content_bytes,
            "content_bytes": content_bytes,
            "content_base64": base64.b64encode(content_bytes).decode("ascii"),
            "content_sha256": content_hash,
            "semantic_workbook_sha256": semantic_hash,
            "semantic_sha256": semantic_hash,
            "etag": _metadata_value(entry, nested, "etag", "eTag", "sp_etag", "remote_etag"),
            "version": _metadata_value(
                entry, nested, "version", "sp_version", "remote_version", "cTag", "ctag"
            ),
            "synced_at": _metadata_value(entry, nested, "synced_at", "syncedAt", "fetched_at"),
        }

    def write_workbook(
        self,
        *,
        path: str,
        content_base64: str,
        content_sha256: str,
        base_etag: str,
        expected_source_sha256: str,
        expected_snapshot: Mapping[str, Any] | None = None,
        semantic_workbook_sha256: str | None = None,
        delivery: Mapping[str, Any] | None = None,
    ) -> str:
        """Queue an idempotent base-checked ``update_workbook`` operation.

        The queue payload is deliberately binary-safe and contains no decoded
        JSON authority.  Repository callers pass the exact decoded
        ``expected_snapshot`` they mutated; this method never refreshes that
        authorization from a newer cache entry.  The queue processor checks the
        supplied etag/hash against SharePoint while holding its own lock.
        """
        clean_path = _clean_path(path)
        if not _is_workbook_path(clean_path):
            raise ValueError("write_workbook requires a canonical .xlsx path")
        if not isinstance(base_etag, str) or not base_etag.strip():
            raise ValueError("base_etag must be a non-empty authenticated cache etag")
        content_bytes = _decode_workbook_base64(content_base64)
        actual_hash = _bytes_hash(content_bytes)
        if content_sha256 != actual_hash:
            raise ValueError("content_sha256 must be SHA-256 of the exact XLSX bytes")
        if not _is_sha256(content_sha256) or not _is_sha256(expected_source_sha256):
            raise ValueError("content_sha256 and expected_source_sha256 must be lowercase SHA-256 values")
        try:
            from .workbook_codec import WorkbookCodec, WorkbookCodecError
            decoded_semantic_hash = WorkbookCodec.semantic_hash(content_bytes)
        except (WorkbookCodecError, ValueError) as exc:
            raise ValueError(f"malformed XLSX workbook: {exc}") from exc
        if semantic_workbook_sha256 is not None and semantic_workbook_sha256 != decoded_semantic_hash:
            raise ValueError("semantic_workbook_sha256 does not match the submitted XLSX")
        semantic_workbook_sha256 = decoded_semantic_hash

        if expected_snapshot is None:
            # Keep direct queue users source-compatible, but never refresh the
            # cache here.  Repository callers must pass the decoded snapshot
            # they mutated so a later cache read cannot authorize a stale
            # whole-workbook rewrite.
            supplied_base: dict[str, Any] = {
                "etag": str(base_etag),
                "version": "",
                "content_sha256": str(expected_source_sha256),
            }
        else:
            if not isinstance(expected_snapshot, Mapping):
                raise ValueError("expected_snapshot must be the decoded workbook snapshot")
            supplied_base = dict(expected_snapshot)
            if (
                supplied_base.get("etag") != base_etag
                or supplied_base.get("content_sha256") != expected_source_sha256
            ):
                raise ValueError(
                    "base_etag/expected_source_sha256 must match expected_snapshot"
                )
            if not supplied_base.get("version"):
                raise ValueError("expected_snapshot must include authenticated version")
        supplied_base["etag"] = str(supplied_base["etag"])
        supplied_base["content_sha256"] = str(supplied_base["content_sha256"])
        operation_id = "seer-finance-workbook:" + hashlib.sha256(
            f"{clean_path}\0{base_etag}\0{expected_source_sha256}\0"
            f"{semantic_workbook_sha256}".encode("utf-8")
        ).hexdigest()
        with self._lock():
            # Do not reread and silently rebase against a newer cache entry.
            # The remote processor receives this exact base proof and is the
            # authority on whether the remote document still matches it.
            current = supplied_base
            journal = self._read_journal()
            retired = next(
                (
                    item for item in journal
                    if item.get("path") == clean_path
                    and item.get("state") == "rebase_required"
                    and item.get("base_etag") == current["etag"]
                    and item.get("base_version") == current.get("version")
                    and item.get("semantic_workbook_sha256") == semantic_workbook_sha256
                ),
                None,
            )
            if retired is not None:
                raise SharePointRebaseRequired(
                    f"fresh SharePoint workbook cache version required before retrying {clean_path}"
                )
            pending = next(
                (
                    item for item in journal
                    if item.get("path") == clean_path and item.get("state") == "pending"
                ),
                None,
            )
            if pending is not None:
                pending_result = self._result(str(pending.get("id")))
                if self._is_rebase_required(pending_result):
                    self._retire_rebase_locked(
                        str(pending.get("id")), clean_path, pending, pending_result
                    )
                    raise SharePointRebaseRequired(
                        f"SharePoint remote requested rebase for {clean_path} ({pending.get('id')})"
                    )
                if (
                    self._workbook_result_proves(
                        str(pending.get("id")),
                        clean_path,
                        str(pending.get("content_sha256")),
                        str(pending.get("semantic_workbook_sha256")),
                        current,
                    )
                ):
                    pending["state"] = "verified"
                    pending["verified_at"] = _now()
                    self._write_journal(journal)
                    if (
                        content_sha256 == pending.get("content_sha256")
                        and semantic_workbook_sha256 == pending.get("semantic_workbook_sha256")
                    ):
                        return str(pending["id"])
                elif current["content_sha256"] == pending.get("content_sha256"):
                    raise SharePointMutationBlocked(
                        f"prior SharePoint workbook mutation proof was evicted for {clean_path}"
                    )
                elif (
                    current["etag"] == pending.get("base_etag")
                    and current["content_sha256"] == pending.get("base_content_sha256")
                ):
                    self._enqueue_locked(self._journal_entry_workbook(pending))
                    raise SharePointWritePending(
                        f"SharePoint workbook mutation recovery queued for {clean_path}"
                    )
                else:
                    raise SharePointMutationBlocked(
                        f"another unresolved SharePoint workbook mutation blocks {clean_path}"
                    )
            if any(
                item.get("id") == operation_id and item.get("state") == "verified"
                for item in journal
            ):
                return operation_id
            # A semantic no-op is already authoritative even when a caller
            # regenerated different ZIP/XML metadata.  Record the exact bytes
            # in the journal, but do not queue a needless SharePoint write.
            if (
                current.get("semantic_workbook_sha256")
                and current.get("semantic_workbook_sha256") == semantic_workbook_sha256
            ):
                journal.append({
                    "id": operation_id,
                    "path": clean_path,
                    "operation": "update_workbook",
                    "state": "verified",
                    "no_op": True,
                    "base_etag": current["etag"],
                    "base_version": current.get("version", ""),
                    "base_content_sha256": current["content_sha256"],
                    "expected_source_sha256": current["content_sha256"],
                    "content_base64": content_base64,
                    "content_sha256": content_sha256,
                    "semantic_workbook_sha256": semantic_workbook_sha256,
                    "semantic_sha256": semantic_workbook_sha256,
                    "created_at": _now(),
                    "verified_at": _now(),
                })
                self._write_journal(journal)
                return operation_id
            entry = self._build_workbook_entry(
                operation_id, clean_path, content_base64, content_sha256,
                semantic_workbook_sha256, current, delivery,
            )
            journal.append({
                "id": operation_id,
                "path": clean_path,
                "operation": "update_workbook",
                "state": "pending",
                "base_etag": current["etag"],
                "base_version": current.get("version", ""),
                "base_content_sha256": current["content_sha256"],
                "expected_source_sha256": current["content_sha256"],
                "content_base64": content_base64,
                "content_sha256": content_sha256,
                "semantic_workbook_sha256": semantic_workbook_sha256,
                "semantic_sha256": semantic_workbook_sha256,
                "delivery": dict(delivery or {}),
                "created_at": _now(),
            })
            self._write_journal(journal)
            self._enqueue_locked(entry)

        result = self._result(operation_id)
        if self._is_rebase_required(result):
            self._retire_rebase(
                operation_id, clean_path, current, content_sha256,
                semantic_workbook_sha256, result,
            )
            raise SharePointRebaseRequired(
                f"SharePoint remote requested rebase for {clean_path} ({operation_id})"
            )
        if result is None:
            raise SharePointWritePending(
                f"SharePoint workbook write pending processed success for {clean_path} ({operation_id})"
            )
        try:
            readback = self.read_workbook_snapshot(clean_path)
        except SharePointContractError:
            readback = None
        if (
            readback is None
            or not self._workbook_result_proves(
                operation_id, clean_path, content_sha256,
                semantic_workbook_sha256, readback,
            )
        ):
            raise SharePointWritePending(
                f"SharePoint workbook write pending processed success for {clean_path} ({operation_id})"
            )
        if (
            readback["etag"] == current["etag"]
            and readback.get("version") == current.get("version")
        ):
            raise SharePointWritePending(
                f"SharePoint workbook write readback base did not advance for {clean_path} ({operation_id})"
            )
        with self._lock():
            journal = self._read_journal()
            for item in journal:
                if item.get("id") == operation_id:
                    item["state"] = "verified"
                    item["verified_at"] = _now()
            self._write_journal(journal)
        return operation_id

    def _validated_cache_entry(
        self, clean: str, *, binary: bool = False
    ) -> tuple[Path, dict[str, Any]]:
        destination = cache_path(self.cache_root, clean)
        manifest_path = self.cache_root / ".manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SharePointCacheUnavailable(
                f"canonical SharePoint cache is missing for {clean}; bootstrap is not implicit"
            ) from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SharePointCacheUnavailable(f"SharePoint cache manifest is malformed: {exc}") from exc
        if not isinstance(manifest, dict) or not isinstance(manifest.get("cached"), dict):
            raise SharePointCacheUnavailable("SharePoint cache manifest has no cached file records")
        relative = clean.lstrip("/")
        entry = (
            manifest["cached"].get(relative)
            or manifest["cached"].get(clean)
            or next(
                (
                    item for item in manifest["cached"].values()
                    if isinstance(item, dict) and item.get("sp_path", "").strip("/") == relative
                ),
                None,
            )
        )
        if not isinstance(entry, dict):
            raise SharePointCacheUnavailable(f"SharePoint cache manifest has no record for {clean}")
        nested = entry.get("remote") if isinstance(entry.get("remote"), dict) else {}
        etag = _metadata_value(entry, nested, "etag", "eTag", "sp_etag", "remote_etag")
        version = _metadata_value(
            entry, nested, "version", "sp_version", "remote_version", "cTag", "ctag"
        )
        synced_at = _metadata_value(entry, nested, "synced_at", "syncedAt", "fetched_at")
        if not etag or not version or not synced_at or entry.get("stale") is True:
            raise SharePointCacheUnavailable(
                f"SharePoint cache record for {clean} lacks fresh remote etag/version metadata"
            )
        try:
            synced = datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SharePointCacheUnavailable(
                f"SharePoint cache freshness timestamp is invalid for {clean}"
            ) from exc
        if synced.tzinfo is None:
            raise SharePointCacheUnavailable(
                f"SharePoint cache freshness timestamp is stale or invalid for {clean}"
            )
        age_seconds = (datetime.now(timezone.utc) - synced).total_seconds()
        if synced > datetime.now(timezone.utc) or age_seconds > MAX_CACHE_AGE_SECONDS:
            raise SharePointCacheUnavailable(
                f"SharePoint cache freshness timestamp is stale or invalid for {clean}"
            )
        if binary and destination.suffix.lower() != ".xlsx":
            raise SharePointCacheUnavailable(f"workbook cache path is not .xlsx: {clean}")
        return destination, entry

    def write(self, *, path: str, content: str, delivery: Mapping[str, Any] | None = None) -> str:
        """Queue a base-checked update, accepting it only after exact readback.

        The local journal serialises mutations and enables recovery. It does
        not make the asynchronous remote commit atomic; a pending entry stays
        blocked until cache readback proves its outcome.
        """
        clean_path = _clean_path(path)
        if _is_workbook_path(clean_path):
            raise ValueError(
                "canonical XLSX ledgers require write_workbook(content_base64, "
                "content_sha256, base_etag, expected_source_sha256)"
            )
        if not isinstance(content, str) or not content:
            raise ValueError("SharePoint document content must be non-empty text")
        base = self.read_snapshot(clean_path)
        desired_hash = _content_hash(content)
        operation_id = "seer-finance:" + hashlib.sha256(
            f"{clean_path}\0{base['etag']}\0{base['version']}\0{desired_hash}".encode("utf-8")
        ).hexdigest()
        entry = self._build_entry(
            operation_id, clean_path, content, base, desired_hash, delivery
        )
        with self._lock():
            # Re-read under the mutation lock. A cache update between the
            # first read and journal write means the caller must retry against
            # the new remote base rather than queueing a stale whole document.
            current = self.read_snapshot(clean_path)
            journal = self._read_journal()
            pending = next(
                (
                    item for item in journal
                    if item.get("path") == clean_path and item.get("state") == "pending"
                ),
                None,
            )
            retired = next(
                (
                    item for item in journal
                    if item.get("path") == clean_path
                    and item.get("state") == "rebase_required"
                    and item.get("base_etag") == current["etag"]
                    and item.get("base_version") == current["version"]
                    and item.get("content_sha256") == desired_hash
                ),
                None,
            )
            if retired is not None:
                raise SharePointRebaseRequired(
                    f"fresh SharePoint cache version required before retrying {clean_path}"
                )
            if pending is not None:
                pending_result = self._result(str(pending.get("id")))
                if self._is_rebase_required(pending_result):
                    self._retire_rebase_locked(
                        str(pending.get("id")), clean_path, pending, pending_result
                    )
                    raise SharePointRebaseRequired(
                        f"SharePoint remote requested rebase for {clean_path} "
                        f"({pending.get('id')})"
                    )
                if (
                    current["content_sha256"] == pending.get("content_sha256")
                    and self._result_proves(
                        str(pending.get("id")), clean_path,
                        str(pending.get("content_sha256")), current,
                    )
                ):
                    pending["state"] = "verified"
                    pending["verified_at"] = _now()
                    self._write_journal(journal)
                    if desired_hash == pending.get("content_sha256"):
                        return str(pending["id"])
                    # The old remote commit is now part of the authenticated
                    # base. Build a fresh operation against that base rather
                    # than allowing a stale whole-document payload through.
                    base = current
                    operation_id = "seer-finance:" + hashlib.sha256(
                        f"{clean_path}\0{base['etag']}\0{base['version']}\0{desired_hash}".encode("utf-8")
                    ).hexdigest()
                    entry = self._build_entry(
                        operation_id, clean_path, content, base, desired_hash, delivery
                    )
                    pending = None
                elif current["content_sha256"] == pending.get("content_sha256"):
                    raise SharePointMutationBlocked(
                        f"prior SharePoint mutation proof was evicted for {clean_path}"
                    )
                elif (
                    current["etag"] == pending.get("base_etag")
                    and current["version"] == pending.get("base_version")
                ):
                    # The queue processor may have evicted a failed write
                    # while the durable journal survived. Requeue the exact
                    # base-checked operation rather than inventing a new ID.
                    self._enqueue_locked(self._journal_entry(pending))
                    raise SharePointWritePending(
                        f"SharePoint mutation recovery queued for {clean_path}"
                    )
                else:
                    raise SharePointMutationBlocked(
                        f"another unresolved SharePoint mutation blocks {clean_path}"
                    )
            if pending is not None:
                raise SharePointMutationBlocked(
                    f"another unresolved SharePoint mutation blocks {clean_path}"
                )
            if current["etag"] != base["etag"] or current["version"] != base["version"]:
                raise SharePointMutationBlocked(
                    f"SharePoint base changed before mutation for {clean_path}"
                )
            journal.append({
                "id": operation_id,
                "path": clean_path,
                "state": "pending",
                "base_etag": base["etag"],
                "base_version": base["version"],
                "base_content_sha256": base["content_sha256"],
                "expected_source_sha256": base["content_sha256"],
                "content_sha256": desired_hash,
                "content": content,
                "delivery": dict(delivery or {}),
                "created_at": _now(),
            })
            self._write_journal(journal)
            self._enqueue_locked(entry)

        result = self._result(operation_id)
        if self._is_rebase_required(result):
            self._retire_rebase(
                operation_id, clean_path, base, desired_hash, desired_hash, result
            )
            raise SharePointRebaseRequired(
                f"SharePoint remote requested rebase for {clean_path} ({operation_id})"
            )
        try:
            result_snapshot = self.read_snapshot(clean_path)
        except SharePointContractError:
            result_snapshot = None
        if (
            result_snapshot is None
            or not self._result_proves(
                operation_id, clean_path, desired_hash, result_snapshot
            )
        ):
            raise SharePointWritePending(
                f"SharePoint write pending processed success for {clean_path} ({operation_id})"
            )
        readback = result_snapshot
        if (
            readback["content"] != content
            or readback["content_sha256"] != desired_hash
            or (
                readback["etag"] == base["etag"]
                and readback["version"] == base["version"]
            )
        ):
            raise SharePointWritePending(
                f"SharePoint write readback mismatch for {clean_path} ({operation_id})"
            )
        with self._lock():
            journal = self._read_journal()
            for item in journal:
                if item.get("id") == operation_id:
                    item["state"] = "verified"
                    item["verified_at"] = _now()
            self._write_journal(journal)
        return operation_id

    def upload_binary(
        self,
        *,
        path: str,
        source_path: str | Path,
        content_sha256: str,
        mime_type: str,
        delivery: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Queue one immutable binary and return only a verified transport result.

        Receipt uploads use the existing locked SharePoint transport, but do
        not use the canonical workbook writer. The queue processor owns the
        actual Graph upload; this method owns operation identity, source-hash
        validation, idempotent enqueue, and exact path/status/eTag proof.
        """
        clean_path = _clean_path(path)
        if _is_workbook_path(clean_path):
            raise ValueError("receipt uploads cannot target canonical XLSX ledgers")
        source = Path(source_path)
        if not source.is_file():
            raise SharePointContractError(f"receipt source file is unavailable: {source}")
        if (
            not isinstance(mime_type, str)
            or "/" not in mime_type
            or "\n" in mime_type
        ):
            raise ValueError("receipt mime_type must be a valid MIME type")
        actual_hash = _bytes_hash(source.read_bytes())
        if not _is_sha256(content_sha256) or content_sha256 != actual_hash:
            raise ValueError("content_sha256 must match the exact receipt bytes")
        operation_id = "seer-finance-receipt:" + hashlib.sha256(
            f"{clean_path}\0{content_sha256}".encode("utf-8")
        ).hexdigest()
        entry: dict[str, Any] = {
            "id": operation_id,
            "operation": "upload_binary",
            "path": clean_path,
            "source_path": str(source),
            "content_sha256": content_sha256,
            "mime_type": mime_type,
            "verify_readback": True,
            "no_totp": True,
            "requested_at": _now(),
        }
        if delivery:
            entry["delivery"] = dict(delivery)
        with self._lock():
            result = self._result(operation_id)
            if result is None:
                queue = self._read_json_list(self.queue_path, "queue")
                if not any(
                    isinstance(item, dict) and item.get("id") == operation_id
                    for item in queue
                ):
                    queue.append(entry)
                    _atomic_json(self.queue_path, queue)
                result = self._result(operation_id)
        if result is None:
            raise SharePointWritePending(
                f"receipt upload pending transport processing for {clean_path} ({operation_id})"
            )
        output = result.get("output")
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                output = None
        if (
            result.get("success") is True
            and result.get("processed_at")
            and isinstance(output, dict)
            and output.get("status") in {"uploaded", "exists"}
            and output.get("path") == clean_path
            and isinstance(output.get("etag"), str)
            and bool(output["etag"].strip())
            and output.get("readback_sha256") == content_sha256
        ):
            return {
                "id": operation_id,
                "path": clean_path,
                "success": True,
                "processed_at": result["processed_at"],
                "etag": output["etag"],
                "readback_sha256": output["readback_sha256"],
                "result": dict(result),
            }
        raise SharePointWritePending(
            f"receipt upload lacks verified remote result for {clean_path} ({operation_id}): "
            f"{result.get('output') or result.get('error') or 'pending'}"
        )

    def bootstrap(
        self, *, path: str, content: str, delivery: Mapping[str, Any] | None = None
    ) -> str:
        """Explicitly create a previously absent canonical document.

        Bootstrap is disabled unless an operator separately gates it. Normal
        capture/review/post code never calls this and never treats absence as
        an empty ledger.
        """
        if os.environ.get("SEER_FINANCE_ALLOW_BOOTSTRAP") != "1":
            raise SharePointCacheUnavailable(
                "canonical SharePoint bootstrap is disabled; set "
                "SEER_FINANCE_ALLOW_BOOTSTRAP=1 for an explicit operation"
            )
        clean = _clean_path(path)
        try:
            self.read_snapshot(clean)
        except SharePointCacheUnavailable:
            pass
        else:
            raise SharePointContractError(f"cannot bootstrap existing SharePoint path {clean}")
        desired_hash = _content_hash(content)
        operation_id = "seer-finance-bootstrap:" + hashlib.sha256(
            f"{clean}\0{desired_hash}".encode("utf-8")
        ).hexdigest()
        entry: dict[str, Any] = {
            "id": operation_id,
            "operation": "create",
            "path": clean,
            "content": content,
            "content_sha256": desired_hash,
            "verify_readback": True,
            "no_totp": True,
            "bootstrap": True,
            "requested_at": _now(),
        }
        if delivery:
            entry["delivery"] = dict(delivery)
        with self._lock():
            journal = self._read_journal()
            journal.append({
                "id": operation_id, "path": clean, "state": "pending",
                "content_sha256": desired_hash, "bootstrap": True, "created_at": _now(),
            })
            self._write_journal(journal)
            self._enqueue_locked(entry)
        if not self._result_proves(operation_id, clean, desired_hash, self.read_snapshot(clean)):
            raise SharePointWritePending(
                f"SharePoint bootstrap pending processed success for {clean} ({operation_id})"
            )
        snapshot = self.read_snapshot(clean)
        if snapshot["content"] != content or snapshot["content_sha256"] != desired_hash:
            raise SharePointWritePending(
                f"SharePoint bootstrap readback mismatch for {clean} ({operation_id})"
            )
        with self._lock():
            journal = self._read_journal()
            for item in journal:
                if item.get("id") == operation_id:
                    item["state"] = "verified"
                    item["verified_at"] = _now()
            self._write_journal(journal)
        return operation_id

    def _build_entry(
        self, operation_id: str, path: str, content: str, base: Mapping[str, str],
        desired_hash: str, delivery: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": operation_id,
            "operation": "update",
            "path": path,
            "content": content,
            "content_sha256": desired_hash,
            "content_hash": desired_hash,
            "base_etag": base["etag"],
            "base_version": base["version"],
            "base_content_sha256": base["content_sha256"],
            "base_content_hash": base["content_sha256"],
            "expected_source_sha256": base["content_sha256"],
            "if_match": base["etag"],
            "verify_readback": True,
            "required_result_fields": [
                "path", "success", "processed_at",
                "resulting_etag|etag", "readback_sha256",
            ],
            "no_totp": True,
            "requested_at": _now(),
        }
        if delivery:
            entry["delivery"] = dict(delivery)
        return entry

    def _build_workbook_entry(
        self,
        operation_id: str,
        path: str,
        content_base64: str,
        content_sha256: str,
        semantic_workbook_sha256: str,
        base: Mapping[str, Any],
        delivery: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": operation_id,
            "operation": "update_workbook",
            "path": path,
            "content_base64": content_base64,
            "content_sha256": content_sha256,
            "semantic_workbook_sha256": semantic_workbook_sha256,
            "semantic_sha256": semantic_workbook_sha256,
            "base_etag": base["etag"],
            "base_version": base["version"],
            "base_content_sha256": base["content_sha256"],
            "expected_source_sha256": base["content_sha256"],
            "if_match": base["etag"],
            "verify_readback": True,
            "required_result_fields": [
                "path", "success", "processed_at",
                "resulting_etag|etag", "readback_sha256",
                "readback_semantic_workbook_sha256|semantic_workbook_sha256|semantic_sha256",
            ],
            "no_totp": True,
            "requested_at": _now(),
        }
        if delivery:
            entry["delivery"] = dict(delivery)
        return entry

    def _enqueue(self, entry: Mapping[str, Any]) -> None:
        """Read/modify/write the queue while holding the processor's flock."""
        with self._lock():
            self._enqueue_locked(entry)

    def _enqueue_locked(self, entry: Mapping[str, Any]) -> None:
        queue = self._read_json_list(self.queue_path, "queue")
        if not any(
            isinstance(item, dict) and item.get("id") == entry.get("id")
            for item in queue
        ):
            queue.append(dict(entry))
            _atomic_json(self.queue_path, queue)

    def _retire_rebase(
        self, operation_id: str, path: str, base: Mapping[str, str],
        desired_hash: str, desired_semantic: str,
        result: Mapping[str, Any] | None,
    ) -> None:
        with self._lock():
            self._retire_rebase_locked(
                operation_id, path,
                {
                    "base_etag": base["etag"],
                    "base_version": base["version"],
                    "content_sha256": desired_hash,
                    "semantic_workbook_sha256": desired_semantic,
                },
                result,
            )

    def _retire_rebase_locked(
        self, operation_id: str, path: str, base: Mapping[str, Any],
        result: Mapping[str, Any] | None,
    ) -> None:
        journal = self._read_journal()
        for item in journal:
            if item.get("id") == operation_id:
                item["state"] = "rebase_required"
                item["resolved_at"] = _now()
                item["conflict"] = dict(result or {})
                item["base_etag"] = base["base_etag"]
                item["base_version"] = base["base_version"]
                item["content_sha256"] = base["content_sha256"]
                if "semantic_workbook_sha256" in base:
                    item["semantic_workbook_sha256"] = base["semantic_workbook_sha256"]
        self._write_journal(journal)
        queue = self._read_json_list(self.queue_path, "queue")
        remaining = [
            item for item in queue
            if not (isinstance(item, dict) and item.get("id") == operation_id)
        ]
        if len(remaining) != len(queue):
            _atomic_json(self.queue_path, remaining)

    @contextmanager
    def _lock(self):
        self.queue_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.queue_lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read_journal(self) -> list[dict[str, Any]]:
        if not self.journal_path.exists():
            return []
        try:
            value = json.loads(self.journal_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SharePointContractError(f"mutation journal malformed: {exc}") from exc
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise SharePointContractError("mutation journal malformed")
        return value

    def _write_journal(self, journal: list[dict[str, Any]]) -> None:
        _atomic_json(self.journal_path, journal)

    @staticmethod
    def _journal_entry(item: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(item.get("content"), str):
            raise SharePointMutationBlocked(
                f"mutation journal entry {item.get('id')} has no replayable content"
            )
        return {
            "id": item["id"],
            "operation": "update",
            "path": item["path"],
            "content": item["content"],
            "content_sha256": item["content_sha256"],
            "content_hash": item["content_sha256"],
            "base_etag": item["base_etag"],
            "base_version": item["base_version"],
            "base_content_sha256": item["base_content_sha256"],
            "base_content_hash": item["base_content_sha256"],
            "expected_source_sha256": item["base_content_sha256"],
            "if_match": item["base_etag"],
            "verify_readback": True,
            "required_result_fields": [
                "path", "success", "processed_at",
                "resulting_etag|etag", "readback_sha256",
            ],
            "no_totp": True,
            "requested_at": item.get("created_at", _now()),
            "delivery": dict(item.get("delivery") or {}),
        }

    @staticmethod
    def _journal_entry_workbook(item: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(item.get("content_base64"), str):
            raise SharePointMutationBlocked(
                f"mutation journal entry {item.get('id')} has no replayable workbook content"
            )
        return {
            "id": item["id"],
            "operation": "update_workbook",
            "path": item["path"],
            "content_base64": item["content_base64"],
            "content_sha256": item["content_sha256"],
            "semantic_workbook_sha256": item["semantic_workbook_sha256"],
            "semantic_sha256": item.get("semantic_sha256", item["semantic_workbook_sha256"]),
            "base_etag": item["base_etag"],
            "base_version": item["base_version"],
            "base_content_sha256": item["base_content_sha256"],
            "expected_source_sha256": item["base_content_sha256"],
            "if_match": item["base_etag"],
            "verify_readback": True,
            "required_result_fields": [
                "path", "success", "processed_at",
                "resulting_etag|etag", "readback_sha256",
                "readback_semantic_workbook_sha256|semantic_workbook_sha256|semantic_sha256",
            ],
            "no_totp": True,
            "requested_at": item.get("created_at", _now()),
            "delivery": dict(item.get("delivery") or {}),
        }

    def _result(self, operation_id: str) -> dict[str, Any] | None:
        results = self._read_json_list(self.results_path, "results", missing_ok=True)
        return next(
            (
                item for item in results
                if isinstance(item, dict) and item.get("id") == operation_id
            ),
            None,
        )

    def _result_proves(
        self, operation_id: str, path: str, expected_hash: str,
        snapshot: Mapping[str, str],
    ) -> bool:
        result = self._result(operation_id)
        if (
            result is None
            or result.get("success") is not True
            or not result.get("processed_at")
            or result.get("path") != path
            or result.get("readback_sha256") != expected_hash
            or result.get("readback_sha256") != snapshot.get("content_sha256")
        ):
            return False
        resulting_etag = result.get("resulting_etag") or result.get("etag")
        resulting_version = result.get("resulting_version") or result.get("version")
        if not (
            isinstance(resulting_etag, str)
            and bool(resulting_etag)
            and resulting_etag == snapshot.get("etag")
        ):
            return False
        # Version is carried by the cache manifest in the current Pi contract.
        # If a processor also returns it, require that proof to agree too.
        return (
            resulting_version is None
            or (
                isinstance(resulting_version, str)
                and bool(resulting_version)
                and resulting_version == snapshot.get("version")
            )
        )

    def _workbook_result_proves(
        self,
        operation_id: str,
        path: str,
        expected_binary_hash: str,
        expected_semantic_hash: str,
        snapshot: Mapping[str, Any],
    ) -> bool:
        result = self._result(operation_id)
        if (
            result is None
            or result.get("success") is not True
            or not result.get("processed_at")
            or result.get("path") != path
            or result.get("readback_sha256") != snapshot.get("content_sha256")
            or (
                snapshot.get("semantic_workbook_sha256") is not None
                and snapshot.get("semantic_workbook_sha256") != expected_semantic_hash
            )
        ):
            return False
        # If Office preserved bytes exactly this is the submitted hash.  If it
        # injected package metadata, the queue result must report the actual
        # readback binary hash instead; in both cases it must agree with cache.
        reported_binary = result.get("readback_sha256")
        if not isinstance(reported_binary, str) or not _is_sha256(reported_binary):
            return False
        reported_semantic = (
            result.get("readback_semantic_workbook_sha256")
            or result.get("semantic_workbook_sha256")
            or result.get("semantic_sha256")
            or result.get("readback_workbook_semantic_sha256")
        )
        if reported_semantic != expected_semantic_hash:
            return False
        resulting_etag = result.get("resulting_etag") or result.get("etag")
        resulting_version = result.get("resulting_version") or result.get("version")
        if not (
            isinstance(resulting_etag, str)
            and bool(resulting_etag)
            and resulting_etag == snapshot.get("etag")
        ):
            return False
        return (
            resulting_version is None
            or (
                isinstance(resulting_version, str)
                and bool(resulting_version)
                and resulting_version == snapshot.get("version")
            )
        )

    @staticmethod
    def _is_rebase_required(result: Mapping[str, Any] | None) -> bool:
        if not isinstance(result, Mapping):
            return False
        if any(
            result.get(key) == "rebase_required"
            for key in ("error_code", "code", "reason", "status")
        ):
            return True
        if result.get("rebase_required") is True:
            return True
        nested = result.get("error")
        return isinstance(nested, Mapping) and (
            nested.get("rebase_required") is True
            or any(
                nested.get(key) == "rebase_required"
                for key in ("error_code", "code", "reason", "status")
            )
        )

    @staticmethod
    def _read_json_list(path: Path, name: str, *, missing_ok: bool = False) -> list[Any]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if missing_ok:
                return []
            return []
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SharePointContractError(f"{name} manifest malformed: {exc}") from exc
        if not isinstance(raw, list):
            raise SharePointContractError(f"{name} manifest malformed: expected a list")
        return raw


def document_content(title: str, payload: Mapping[str, Any]) -> str:
    """Render machine-readable data in a human-readable Markdown document."""
    return (
        f"# {title}\n\n"
        "```json\n"
        + json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n```\n"
    )


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _bytes_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _decode_workbook_base64(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("content_base64 must be a non-empty base64 string")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError("content_base64 is not valid base64") from exc
    if not decoded:
        raise ValueError("content_base64 must decode to non-empty XLSX bytes")
    return decoded


def _is_workbook_path(path: str) -> bool:
    return str(path).lower().endswith(".xlsx")


def _metadata_value(entry: Mapping[str, Any], nested: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = entry.get(name)
        if value is None:
            value = nested.get(name)
        if value not in (None, ""):
            return str(value)
    return None


def parse_document(content: str, *, path: str) -> dict[str, Any]:
    """Parse only documents emitted by :func:`document_content`."""
    try:
        start = content.index("```json\n") + len("```json\n")
        end = content.index("\n```", start)
        value = json.loads(content[start:end])
    except (ValueError, json.JSONDecodeError) as exc:
        raise SharePointContractError(f"invalid cached SharePoint document {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SharePointContractError(f"invalid cached SharePoint document {path}: expected an object")
    return value