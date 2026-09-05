from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from tarav.agent.monitor.burst_ratio import (
    BurstRatioMeasurement,
    burst_ratios_from_observations,
    measure_burst_ratios,
)
from tarav.agent.monitor.burst_ratio import _Observation
from tarav.agent.usage_registry import append_usage_record
from tarav.testing import TaravTestEnvironment


NOW = datetime.datetime(2026, 9, 5, 12, 0, tzinfo=datetime.UTC)


def _observation(
    *,
    minute: int,
    burst_used: float,
    weekly_used: float,
    burst_reset: str = "burst-1",
    weekly_reset: str = "weekly-1",
) -> _Observation:
    recorded_at = (NOW + datetime.timedelta(minutes=minute)).isoformat()
    return _Observation(
        recorded_at=recorded_at,
        burst_used=burst_used,
        burst_reset=burst_reset,
        weekly_used=weekly_used,
        weekly_reset=weekly_reset,
    )


def _measure(series: list[_Observation], key: str = "codex/jp") -> BurstRatioMeasurement:
    return burst_ratios_from_observations({key: series}, computed_at=NOW)


def test_ratio_is_weekly_delta_over_burst_delta() -> None:
    series = [
        _observation(minute=0, burst_used=0, weekly_used=10),
        _observation(minute=60, burst_used=50, weekly_used=18),
    ]

    measurement = _measure(series)

    assert measurement.accounts["codex/jp"] == pytest.approx(16.0)
    assert measurement.sample_counts["codex/jp"] == 1


def test_run_splits_on_reset_identity_change_without_a_decrease() -> None:
    """A window that resets while idle reads zero on both sides of the boundary.

    A decrease-only split rule would merge the two windows and pool the second
    window's burst movement against the first window's weekly movement.
    """
    series = [
        _observation(minute=0, burst_used=0, weekly_used=10),
        _observation(minute=60, burst_used=40, weekly_used=16),
        # burst window rolls over; usage happens to read 0 on both sides
        _observation(minute=120, burst_used=0, weekly_used=16, burst_reset="burst-2"),
        _observation(minute=180, burst_used=40, weekly_used=22, burst_reset="burst-2"),
    ]

    measurement = _measure(series)

    # two clean runs of 6 weekly per 40 burst, not one merged run
    assert measurement.accounts["codex/jp"] == pytest.approx(15.0)
    assert measurement.sample_counts["codex/jp"] == 2


def test_run_splits_on_used_percent_decrease() -> None:
    series = [
        _observation(minute=0, burst_used=0, weekly_used=10),
        _observation(minute=60, burst_used=40, weekly_used=16),
        _observation(minute=120, burst_used=5, weekly_used=16),
        _observation(minute=180, burst_used=45, weekly_used=22),
    ]

    measurement = _measure(series)

    assert measurement.accounts["codex/jp"] == pytest.approx(15.0)
    assert measurement.sample_counts["codex/jp"] == 2


def test_run_uses_telescoped_endpoints_not_per_step_deltas() -> None:
    """Whole-number reporting makes per-step deltas lossy; endpoints are not."""
    series = [
        _observation(minute=0, burst_used=0, weekly_used=0),
        _observation(minute=30, burst_used=25, weekly_used=3),
        _observation(minute=60, burst_used=50, weekly_used=7),
        _observation(minute=90, burst_used=75, weekly_used=11),
        _observation(minute=120, burst_used=100, weekly_used=16),
    ]

    measurement = _measure(series)

    assert measurement.accounts["codex/jp"] == pytest.approx(16.0)
    assert measurement.sample_counts["codex/jp"] == 1


def test_provider_value_is_the_median_across_accounts_not_a_pooled_sum() -> None:
    """One high-volume account must not drag the provider value."""
    observations = {
        # 16.0 across a very large burst volume
        "codex/br": [
            _observation(minute=0, burst_used=0, weekly_used=0),
            _observation(minute=60, burst_used=1000, weekly_used=160),
        ],
        "codex/jp": [
            _observation(minute=0, burst_used=0, weekly_used=0),
            _observation(minute=60, burst_used=50, weekly_used=5),
        ],
        "codex/mm": [
            _observation(minute=0, burst_used=0, weekly_used=0),
            _observation(minute=60, burst_used=50, weekly_used=6),
        ],
    }

    measurement = burst_ratios_from_observations(observations, computed_at=NOW)

    assert measurement.accounts["codex/br"] == pytest.approx(16.0)
    assert measurement.providers["codex"] == pytest.approx(12.0)


def test_account_lookup_falls_back_to_the_provider_median() -> None:
    observations = {
        "codex/jp": [
            _observation(minute=0, burst_used=0, weekly_used=0),
            _observation(minute=60, burst_used=50, weekly_used=8),
        ],
    }

    measurement = burst_ratios_from_observations(observations, computed_at=NOW)

    assert measurement.weekly_burst_percent(
        provider="codex", account="jp"
    ) == pytest.approx(16.0)
    assert measurement.weekly_burst_percent(
        provider="codex", account="unmeasured"
    ) == pytest.approx(16.0)


def test_unmeasured_provider_has_no_ratio() -> None:
    measurement = burst_ratios_from_observations({}, computed_at=NOW)

    assert measurement.weekly_burst_percent(provider="copilot-cli", account="jp") is None


def test_idle_account_yields_no_ratio() -> None:
    series = [
        _observation(minute=0, burst_used=0, weekly_used=0),
        _observation(minute=60, burst_used=0, weekly_used=0),
    ]

    measurement = _measure(series)

    assert "codex/jp" not in measurement.accounts
    assert measurement.providers == {}


def test_measurement_is_stale_after_the_ttl() -> None:
    measurement = burst_ratios_from_observations({}, computed_at=NOW)

    assert not measurement.is_stale(now=NOW + datetime.timedelta(hours=23))
    assert measurement.is_stale(now=NOW + datetime.timedelta(hours=25))
    assert BurstRatioMeasurement().is_stale(now=NOW)


def _codex_payload(
    *, burst_used: int, weekly_used: int, swap: bool = False
) -> dict[str, object]:
    burst = {
        "usedPercent": burst_used,
        "resetsAt": 1788622510,
        "windowDurationMins": 300,
    }
    weekly = {
        "usedPercent": weekly_used,
        "resetsAt": 1788763130,
        "windowDurationMins": 10080,
    }
    first, second = (weekly, burst) if swap else (burst, weekly)
    return {"rateLimits": {"primary": first, "secondary": second}}


def _claude_payload(*, burst_used: int, weekly_used: int) -> dict[str, object]:
    return {
        "rate_limits": {
            "five_hour": {"resets_at": 1788622200, "used_percentage": burst_used},
            "seven_day": {"resets_at": 1789207200, "used_percentage": weekly_used},
        }
    }


@pytest.mark.parametrize("swap", [False, True])
def test_codex_windows_are_matched_by_duration_not_position(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, swap: bool
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    for burst_used, weekly_used in ((0, 10), (50, 18)):
        append_usage_record(
            provider="codex",
            account="jp",
            home=tmp_path / "codex-jp",
            source="app_server",
            payload=_codex_payload(
                burst_used=burst_used, weekly_used=weekly_used, swap=swap
            ),
        )

    measurement = measure_burst_ratios()

    assert measurement.accounts["codex/jp"] == pytest.approx(16.0)


def test_claude_windows_are_measured_alongside_codex(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    for burst_used, weekly_used in ((0, 10), (50, 15)):
        append_usage_record(
            provider="claude-code",
            account="jp",
            home=tmp_path / "claude-jp",
            source="statusline",
            payload=_claude_payload(burst_used=burst_used, weekly_used=weekly_used),
        )

    measurement = measure_burst_ratios()

    assert measurement.accounts["claude-code/jp"] == pytest.approx(10.0)
    assert measurement.providers["claude-code"] == pytest.approx(10.0)


def test_single_window_payload_produces_no_observation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The outage shape: a weekly window with no burst window beside it."""
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    for weekly_used in (10, 18):
        append_usage_record(
            provider="codex",
            account="jp",
            home=tmp_path / "codex-jp",
            source="app_server",
            payload={
                "rateLimits": {
                    "primary": {
                        "usedPercent": weekly_used,
                        "resetsAt": 1788763130,
                        "windowDurationMins": 10080,
                    },
                    "secondary": None,
                }
            },
        )

    measurement = measure_burst_ratios()

    assert measurement.accounts == {}
    assert measurement.weekly_burst_percent(provider="codex", account="jp") is None


def test_records_older_than_the_window_are_not_scanned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    for burst_used, weekly_used in ((0, 10), (50, 18)):
        append_usage_record(
            provider="codex",
            account="jp",
            home=tmp_path / "codex-jp",
            source="app_server",
            payload=_codex_payload(burst_used=burst_used, weekly_used=weekly_used),
        )

    later = datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(days=30)
    measurement = measure_burst_ratios(now=later, window=datetime.timedelta(days=1))

    assert measurement.accounts == {}
