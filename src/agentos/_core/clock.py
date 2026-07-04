from __future__ import annotations

from datetime import datetime, timezone


def iso_z(value: datetime, *, drop_micros: bool = True) -> str:
    """Format a datetime as a UTC ISO-8601 string with a ``Z`` suffix.

    Normalizes to UTC — the house-wide timestamp shape. ``drop_micros`` (default) drops
    sub-second precision; pass ``drop_micros=False`` to keep microseconds.
    """
    value = value.astimezone(timezone.utc)
    if drop_micros:
        value = value.replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return iso_z(datetime.now(timezone.utc))
