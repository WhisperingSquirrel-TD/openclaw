#!/usr/bin/env python3
"""Bounded stdin adapter for the service-owned SharePoint queue producer."""

import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_processor():
    configured = os.environ.get("OPENCLAW_SHAREPOINT_QUEUE_PROCESSOR", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path.home() / ".openclaw/integrations/microsoft/sharepoint_queue_processor.py",
    ]
    for candidate in candidates:
        if not candidate or not candidate.is_file():
            continue
        spec = importlib.util.spec_from_file_location("openclaw_sharepoint_queue_processor", candidate)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise RuntimeError("SharePoint queue processor is not installed")


def main() -> int:
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    operation = str(request.get("operation", "")).strip().lower()
    path = str(request.get("path", "")).strip()
    content = request.get("content")
    if operation not in {"create", "update", "append"}:
        raise ValueError("operation must be create, update, or append")
    if not path or ".." in Path(path).parts:
        raise ValueError("unsafe SharePoint path")
    if not isinstance(content, str) or not content:
        raise ValueError("content must be a non-empty string")

    processor = _load_processor()
    allowed, rejection = processor._queue_path_allowed(path)
    if not allowed:
        raise ValueError(rejection)
    operation_payload = {
        "operation": operation,
        "path": path,
        "content": content,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "requested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    operation_payload["id"] = "sharepoint-write:" + hashlib.sha256(
        f"{operation}\n{path}\n{content}".encode("utf-8")
    ).hexdigest()
    for source, target in (
        ("baseEtag", "base_etag"),
        ("expectedSourceSha256", "expected_source_sha256"),
    ):
        if source in request:
            operation_payload[target] = request[source]
    queued = processor.enqueue_operation(operation_payload)
    print(json.dumps({
        "ok": True,
        "queued": queued,
        "operation": operation_payload["operation"],
        "path": operation_payload["path"],
        "operation_id": operation_payload.get("id"),
    }))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        raise SystemExit(2)