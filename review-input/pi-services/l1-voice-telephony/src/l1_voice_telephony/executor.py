"""No-call action boundary for the L1 voice gateway.

The future telephony adapter may propose an action, but it cannot invoke a handler
until this boundary has consumed a valid, exact approval grant. This module exposes
only injected mock/local handlers; it intentionally has no OpenClaw, calendar, email,
Twilio, OpenAI, network, or subprocess integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Mapping
from uuid import uuid4

from .approval import ActionRequest, ApprovalGrant, ApprovalService, CallerIdentity


@dataclass(frozen=True)
class ActionAuditEvent:
    event_id: str
    correlation_id: str
    occurred_at: datetime
    actor_id: str
    action_digest: str
    action: str
    target: str
    outcome: str
    detail: str

    def as_safe_dict(self) -> dict[str, str]:
        """Return a structured, non-secret record without action parameters/raw audio."""
        return {
            "action": self.action,
            "action_digest": self.action_digest,
            "actor_id": self.actor_id,
            "correlation_id": self.correlation_id,
            "detail": self.detail,
            "event_id": self.event_id,
            "occurred_at": self.occurred_at.astimezone(UTC).isoformat(),
            "outcome": self.outcome,
            "target": self.target,
        }


class ActionExecutionError(ValueError):
    """A requested approved action had no safe handler or the handler failed."""


class ApprovedActionExecutor:
    """Consumes approval before calling one allowlisted, injected local handler."""

    def __init__(
        self,
        *,
        approvals: ApprovalService,
        handlers: Mapping[str, Callable[[ActionRequest], str]],
        now: Callable[[], datetime] | None = None,
        audit_sink: Callable[[ActionAuditEvent], None] | None = None,
    ) -> None:
        self._approvals = approvals
        self._handlers = dict(handlers)
        self._now = now or (lambda: datetime.now(UTC))
        self._audit_sink = audit_sink or (lambda _event: None)

    def execute(
        self,
        *,
        correlation_id: str,
        caller: CallerIdentity,
        request: ActionRequest,
        grant: ApprovalGrant,
    ) -> str:
        """Consume the exact grant then dispatch to a single named allowlisted handler."""
        self._approvals.consume(grant=grant, caller=caller, request=request)
        handler = self._handlers.get(request.action)
        if handler is None:
            self._audit(correlation_id, caller, request, "rejected", "no_allowlisted_handler")
            raise ActionExecutionError("action has no allowlisted handler")
        try:
            result = handler(request)
        except Exception as exc:
            self._audit(correlation_id, caller, request, "failed", type(exc).__name__)
            raise ActionExecutionError("allowlisted handler failed") from exc
        self._audit(correlation_id, caller, request, "succeeded", "handler_completed")
        return result

    def _audit(
        self,
        correlation_id: str,
        caller: CallerIdentity,
        request: ActionRequest,
        outcome: str,
        detail: str,
    ) -> None:
        occurred_at = self._now()
        if occurred_at.tzinfo is None:
            raise ValueError("clock must return timezone-aware datetime")
        self._audit_sink(
            ActionAuditEvent(
                event_id=str(uuid4()),
                correlation_id=correlation_id,
                occurred_at=occurred_at.astimezone(UTC),
                actor_id=caller.actor_id,
                action_digest=request.digest(),
                action=request.action,
                target=request.target,
                outcome=outcome,
                detail=detail,
            )
        )
