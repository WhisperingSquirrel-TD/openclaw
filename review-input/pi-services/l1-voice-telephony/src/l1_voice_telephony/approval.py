"""Session-scoped voice approval policy.

This module deliberately has no telephony, OpenAI, network, or tool-execution code.
It turns a verified caller plus a fresh spoken confirmation into one signed, expiring,
parameter-bound grant. The eventual action adapter must verify and consume this grant
before it invokes any side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import IntEnum
import base64
import hashlib
import hmac
import json
import secrets
from typing import Callable


class ApprovalError(ValueError):
    """Raised when a proposed or presented approval grant is not valid."""


class AuthorityTier(IntEnum):
    INFORMATION = 1
    BOUNDED_EXTERNAL = 2
    MATERIAL_SENSITIVE = 3
    PROHIBITED = 4


@dataclass(frozen=True)
class CallerIdentity:
    """The telephony adapter's verified caller result; never raw caller ID alone."""

    actor_id: str
    registered_tom_number: bool
    carrier_verified: bool

    @property
    def may_open_tom_session(self) -> bool:
        return self.registered_tom_number and self.carrier_verified


@dataclass(frozen=True)
class ActionRequest:
    """A deterministic action proposal, before any downstream tool is called."""

    action: str
    target: str
    parameters: dict[str, object]
    tier: AuthorityTier

    def digest(self) -> str:
        """Stable digest that binds approval to exact action details."""
        payload = {
            "action": self.action,
            "parameters": self.parameters,
            "target": self.target,
            "tier": int(self.tier),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ApprovalGrant:
    """Signed, one-time authority for exactly one proposed action."""

    grant_id: str
    actor_id: str
    action_digest: str
    tier: AuthorityTier
    issued_at: datetime
    expires_at: datetime
    token: str


class ApprovalService:
    """Creates and consumes short-lived scoped grants.

    For phase one, no separate PIN is required: the caller must be the registered Tom
    number and must give a fresh affirmative confirmation after an exact read-back.
    The telephony/session layer is responsible for evidencing that confirmation before
    it calls ``mint``.
    """

    def __init__(
        self,
        signing_key: bytes,
        *,
        now: Callable[[], datetime] | None = None,
        max_lifetime: timedelta = timedelta(minutes=2),
    ) -> None:
        if len(signing_key) < 32:
            raise ValueError("signing_key must be at least 32 bytes")
        if max_lifetime <= timedelta(0):
            raise ValueError("max_lifetime must be positive")
        self._signing_key = signing_key
        self._now = now or (lambda: datetime.now(UTC))
        self._max_lifetime = max_lifetime
        self._consumed_ids: set[str] = set()

    def mint(
        self,
        *,
        caller: CallerIdentity,
        request: ActionRequest,
        spoken_confirmation: bool,
        lifetime: timedelta | None = None,
    ) -> ApprovalGrant:
        """Mint a scoped grant after deterministic checks; never for prohibited work."""
        if not caller.may_open_tom_session:
            raise ApprovalError("caller is not an authenticated Tom session")
        if not spoken_confirmation:
            raise ApprovalError("fresh spoken confirmation is required")
        if request.tier is AuthorityTier.PROHIBITED:
            raise ApprovalError("prohibited actions cannot receive a voice grant")

        effective_lifetime = lifetime or self._max_lifetime
        if effective_lifetime <= timedelta(0) or effective_lifetime > self._max_lifetime:
            raise ApprovalError("grant lifetime exceeds the policy limit")

        issued_at = self._utc(self._now())
        expires_at = issued_at + effective_lifetime
        grant_id = secrets.token_urlsafe(24)
        action_digest = request.digest()
        payload = self._payload(
            grant_id=grant_id,
            actor_id=caller.actor_id,
            action_digest=action_digest,
            tier=request.tier,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        return ApprovalGrant(
            grant_id=grant_id,
            actor_id=caller.actor_id,
            action_digest=action_digest,
            tier=request.tier,
            issued_at=issued_at,
            expires_at=expires_at,
            token=self._sign(payload),
        )

    def consume(
        self,
        *,
        grant: ApprovalGrant,
        caller: CallerIdentity,
        request: ActionRequest,
    ) -> None:
        """Validate and consume once; the caller invokes the side effect only on return."""
        if grant.grant_id in self._consumed_ids:
            raise ApprovalError("approval grant has already been consumed")
        if not caller.may_open_tom_session or caller.actor_id != grant.actor_id:
            raise ApprovalError("caller does not match the approval grant")
        if request.digest() != grant.action_digest or request.tier is not grant.tier:
            raise ApprovalError("action does not match the approved action")
        now = self._utc(self._now())
        if now >= grant.expires_at:
            raise ApprovalError("approval grant has expired")
        payload = self._payload(
            grant_id=grant.grant_id,
            actor_id=grant.actor_id,
            action_digest=grant.action_digest,
            tier=grant.tier,
            issued_at=grant.issued_at,
            expires_at=grant.expires_at,
        )
        if not hmac.compare_digest(grant.token, self._sign(payload)):
            raise ApprovalError("approval grant signature is invalid")
        self._consumed_ids.add(grant.grant_id)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _payload(
        *,
        grant_id: str,
        actor_id: str,
        action_digest: str,
        tier: AuthorityTier,
        issued_at: datetime,
        expires_at: datetime,
    ) -> bytes:
        value = {
            "action_digest": action_digest,
            "actor_id": actor_id,
            "expires_at": expires_at.isoformat(),
            "grant_id": grant_id,
            "issued_at": issued_at.isoformat(),
            "tier": int(tier),
        }
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    def _sign(self, payload: bytes) -> str:
        signature = hmac.new(self._signing_key, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature).decode().rstrip("=")
