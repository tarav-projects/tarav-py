from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_iso_z_drops_microseconds_and_uses_z() -> None:
    from agentos._core.clock import iso_z

    value = datetime(2026, 6, 27, 14, 32, 7, 123456, tzinfo=timezone.utc)
    assert iso_z(value) == "2026-06-27T14:32:07Z"


def test_iso_z_keeps_microseconds_when_asked() -> None:
    from agentos._core.clock import iso_z

    value = datetime(2026, 6, 27, 14, 32, 7, 123456, tzinfo=timezone.utc)
    assert iso_z(value, drop_micros=False) == "2026-06-27T14:32:07.123456Z"


def test_iso_z_normalizes_to_utc() -> None:
    from agentos._core.clock import iso_z

    # a +02:00 wall-clock instant is the same instant as 12:32:07Z
    value = datetime(2026, 6, 27, 14, 32, 7, tzinfo=timezone(timedelta(hours=2)))
    assert iso_z(value) == "2026-06-27T12:32:07Z"


def test_utc_now_iso_still_z_suffixed() -> None:
    from agentos._core.clock import utc_now_iso

    assert utc_now_iso().endswith("Z")
