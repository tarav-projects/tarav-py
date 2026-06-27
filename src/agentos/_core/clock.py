from __future__ import annotations

from datetime import datetime, timezone


def iso_z(value: datetime) -> str:
    """Format a datetime as a UTC ISO-8601 string with a ``Z`` suffix.

    Normalizes to UTC and drops sub-second precision — the house-wide timestamp shape.
    """
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return iso_z(datetime.now(timezone.utc))
