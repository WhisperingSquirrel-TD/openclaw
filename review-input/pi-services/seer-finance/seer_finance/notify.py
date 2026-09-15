"""
Daily notification decision engine.

Turns the statutory schedule into a concrete decision: should OpenClaw message
Tom today, about what, and how urgently. This is the piece that makes "don't let
Tom miss an HMRC date" real — cron runs this daily, and OpenClaw sends a message
only when this says to.

It is deterministic and testable. OpenClaw does not decide urgency itself; it
runs this and transports the result.

Escalation model (days before the HARD due date):
  - A "prep" alert fires once the deadline's prep_start date is reached.
  - Reminders then escalate: 30 days out, 14 days, 7 days, 3 days, 1 day, and
    on the day. Between those points, no message (avoids daily nagging).
  - Anything already overdue always fires, at CRITICAL.

Exit code from the CLI wrapper lets cron/OpenClaw branch:
    0  nothing to report today
    1  one or more alerts to send
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .deadlines import Deadline, Severity, build_schedule


class Urgency(str, Enum):
    PREP = "prep"          # time to start preparing
    UPCOMING = "upcoming"  # 30/14 days out
    SOON = "soon"          # 7/3 days out
    IMMINENT = "imminent"  # 1 day / due today
    OVERDUE = "overdue"    # past due


# Days-before thresholds at which a reminder fires (besides prep_start).
_REMINDER_DAYS = (30, 14, 7, 3, 1, 0)


@dataclass(frozen=True)
class Alert:
    title: str
    due: date
    days_until: int          # negative if overdue
    urgency: Urgency
    message: str


def _urgency_for(days_until: int) -> Urgency:
    if days_until < 0:
        return Urgency.OVERDUE
    if days_until <= 1:
        return Urgency.IMMINENT
    if days_until <= 7:
        return Urgency.SOON
    if days_until <= 30:
        return Urgency.UPCOMING
    return Urgency.PREP


def _should_fire(deadline: Deadline, today: date) -> bool:
    """True if today is a day this deadline should produce an alert."""
    if deadline.due is None:
        return False
    days_until = (deadline.due - today).days
    if days_until < 0:
        return True  # overdue always fires
    if days_until in _REMINDER_DAYS:
        return True
    # Fire on the exact prep_start date too (start-of-work nudge).
    prep = deadline.prep_start()
    if prep is not None and prep == today:
        return True
    return False


def _build_message(deadline: Deadline, days_until: int, urgency: Urgency) -> str:
    due_str = deadline.due.isoformat()
    if urgency is Urgency.OVERDUE:
        return (
            f"OVERDUE: '{deadline.title}' was due {due_str} "
            f"({abs(days_until)} days ago). This is a statutory deadline — "
            f"penalties may apply. Act now."
        )
    if urgency is Urgency.IMMINENT:
        when = "TODAY" if days_until == 0 else "TOMORROW"
        return (
            f"DUE {when}: '{deadline.title}' is due {due_str}. "
            f"This is a hard HMRC/Companies House deadline."
        )
    if urgency is Urgency.SOON:
        return (
            f"Due in {days_until} days: '{deadline.title}' ({due_str}). "
            f"Make sure the figures/filing are ready."
        )
    if urgency is Urgency.UPCOMING:
        return (
            f"Coming up in {days_until} days: '{deadline.title}' ({due_str})."
        )
    return (
        f"Time to start preparing: '{deadline.title}' is due {due_str} "
        f"({days_until} days away). Begin the work now to be comfortable."
    )


def alerts_for(profile, today: date | None = None) -> list[Alert]:
    """Return today's alerts for a company profile."""
    today = today or date.today()
    schedule = build_schedule(profile)
    out: list[Alert] = []
    for d in schedule:
        # Only hard/prep dated items drive reminders; watch/info items don't.
        if d.severity not in (Severity.HARD, Severity.PREP):
            continue
        if not _should_fire(d, today):
            continue
        days_until = (d.due - today).days
        urgency = _urgency_for(days_until)
        out.append(
            Alert(
                title=d.title,
                due=d.due,
                days_until=days_until,
                urgency=urgency,
                message=_build_message(d, days_until, urgency),
            )
        )
    # Most urgent first.
    order = {u: i for i, u in enumerate(
        [Urgency.OVERDUE, Urgency.IMMINENT, Urgency.SOON,
         Urgency.UPCOMING, Urgency.PREP]
    )}
    return sorted(out, key=lambda a: (order[a.urgency], a.due))
