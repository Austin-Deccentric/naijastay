"""Temporal boundaries. Ops principle: UTC everywhere.

All business-date decisions ("is check-in today?", "default report date?",
"is this booking in the past?") use UTC, independent of the machine's local
timezone. Lagos wall-clock is a presentation-layer concern for future
frontends, never a backend rule.
"""

from datetime import UTC, date, datetime


def utc_today() -> date:
    """Current date in UTC. Single source for all business-date boundaries."""
    return datetime.now(UTC).date()
