"""Pure, receipt-safe adapters for calendar and SharePoint change fixtures.

This module deliberately has no provider client, filesystem access, or destination
writer.  It only turns a caller-supplied provider change into a stable internal
shape and proposes the one owning route for that surface.  A record with no
provider resource identity is rejected rather than being matched by title, path,
or human-readable metadata.
"""
from __future__ import annotations

from typing import Any, Mapping

CALENDAR_SURFACE = "calendar"
SHAREPOINT_SURFACE = "sharepoint"


def _text(value: Any) -> str:
    """Return a non-empty, stripped string (or an empty string)."""
    return str(value or "").strip()


def _required_text(change: Mapping[str, Any], *names: str, label: str) -> str:
    """Read the first non-empty alias or fail closed with a useful error."""
    for name in names:
        value = _text(change.get(name))
        if value:
            return value
    raise ValueError(f"{label} is required")


def _validate_change(change: Mapping[str, Any]) -> None:
    if not isinstance(change, Mapping):
        raise TypeError("provider change must be a mapping")


def _base_receipt(
    change: Mapping[str, Any], *, surface: str, provider_resource_id: str, resource_kind: str
) -> dict[str, Any]:
    """Build the common evidence-bearing portion of a normalized change."""
    provider_change_id = _required_text(
        change,
        "provider_change_id",
        "change_id",
        "delta_id",
        label="provider_change_id",
    )
    source_timestamp = _required_text(
        change, "source_timestamp", "last_modified_at", "timestamp", label="source_timestamp"
    )
    observed_at = _required_text(change, "observed_at", label="observed_at")
    evidence_ref = _required_text(change, "evidence_ref", label="evidence_ref")
    change_type = _text(change.get("change_type") or change.get("change_kind")) or "updated"

    return {
        "surface": surface,
        "provider_resource_id": provider_resource_id,
        "provider_change_id": provider_change_id,
        "resource_kind": resource_kind,
        "change_type": change_type,
        "source_timestamp": source_timestamp,
        "observed_at": observed_at,
        "evidence_refs": [evidence_ref],
        "identity_state": "receipt_safe",
    }


def _owned_route(route: str, owner: str) -> list[dict[str, str]]:
    # These are proposals, not delivery receipts: this adapter owns no runtime
    # route and never causes a provider, CRM, or SharePoint write.
    return [{"route": route, "owner": owner, "state": "proposed"}]


def normalise_calendar_change(change: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one calendar-provider change with an event and change ID.

    Calendar subject, attendees, organiser and body are intentionally not used
    as identity.  They may be copied into ``metadata`` only after stable
    provider identity and evidence have passed the receipt-safety gate.
    """
    _validate_change(change)
    provider_event_id = _required_text(change, "provider_event_id", "event_id", label="provider_event_id")
    result = _base_receipt(
        change, surface=CALENDAR_SURFACE, provider_resource_id=provider_event_id, resource_kind="calendar_event"
    )
    result["provider_event_id"] = provider_event_id
    result["proposed_routes"] = _owned_route("calendar", "calendar")
    result["adapter_metadata"] = {
        "adapter": "operational_surface_calendar_v1",
        "external_writes": False,
        "automatic_entity_matching": False,
    }
    return result


def normalise_sharepoint_change(change: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one SharePoint-provider change with an item and change ID.

    A display name, web URL, server-relative path, or folder name is not an
    acceptable substitute for ``provider_item_id``.  This prevents an ambiguous
    document from acquiring a receipt or an owned route.
    """
    _validate_change(change)
    provider_item_id = _required_text(change, "provider_item_id", "item_id", label="provider_item_id")
    result = _base_receipt(
        change, surface=SHAREPOINT_SURFACE, provider_resource_id=provider_item_id, resource_kind="sharepoint_item"
    )
    result["provider_item_id"] = provider_item_id
    result["proposed_routes"] = _owned_route("sharepoint", "sharepoint")
    result["adapter_metadata"] = {
        "adapter": "operational_surface_sharepoint_v1",
        "external_writes": False,
        "automatic_entity_matching": False,
    }
    return result


def normalise_operational_surface_change(surface: str, change: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch a bounded fixture to the appropriate surface adapter."""
    normalised_surface = _text(surface).lower()
    if normalised_surface == CALENDAR_SURFACE:
        return normalise_calendar_change(change)
    if normalised_surface == SHAREPOINT_SURFACE:
        return normalise_sharepoint_change(change)
    raise ValueError("surface must be calendar or sharepoint")


# American spelling is retained as a small caller-facing compatibility alias.
normalize_calendar_change = normalise_calendar_change
normalize_sharepoint_change = normalise_sharepoint_change
normalize_operational_surface_change = normalise_operational_surface_change
