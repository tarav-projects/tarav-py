from __future__ import annotations

import datetime
from pathlib import Path

from agentos.agent.monitor.models import (
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    MonitorTarget,
    MonitorWorkflowConfig,
)
from agentos.agent.monitor.workflows import AutoPrimeZeroLimitsWorkflow


def _workflow(*, triggers: tuple[str, ...]) -> AutoPrimeZeroLimitsWorkflow:
    return AutoPrimeZeroLimitsWorkflow(
        MonitorWorkflowConfig(
            name=AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
            targets=(
                MonitorTarget(
                    provider="codex",
                    account="jp",
                    home=Path("/tmp/codex-jp"),
                ),
            ),
            refresh_interval_sec=60,
            retry_cooldown_sec=600,
            target_limit_ids={"codex": ("burst",)},
            triggers={"codex": triggers},
            raw_config={},
        )
    )


def _target_state() -> dict[str, object]:
    return {
        "provider": "codex",
        "account": "jp",
        "home": "/tmp/codex-jp",
        "primed_periods": {},
        "observations": {},
    }


def _source_state(*, limit: dict[str, object]) -> dict[str, object]:
    return {
        "status": "ok",
        "provider": "codex",
        "account": "jp",
        "home": "/tmp/codex-jp",
        "account_status": {"limits": [limit]},
    }


def _limit(
    *,
    used_percent: int,
    now: datetime.datetime,
    end_offset_mins: int = 300,
    duration_mins: int = 300,
) -> dict[str, object]:
    period_ends_at = now + datetime.timedelta(minutes=end_offset_mins)
    period_started_at = period_ends_at - datetime.timedelta(minutes=duration_mins)
    return {
        "limit_id": "burst",
        "usage_over_time": {
            "used_percent": used_percent,
            "period_started_at": period_started_at.isoformat(),
            "period_ends_at": period_ends_at.isoformat(),
            "period_duration_mins": duration_mins,
            "resets_at": period_ends_at.isoformat(),
        },
    }


def _eligible(
    workflow: AutoPrimeZeroLimitsWorkflow,
    target_state: dict[str, object],
    limit: dict[str, object],
    *,
    now: datetime.datetime,
) -> list[dict[str, object]]:
    return workflow._eligible_periods(
        _source_state(limit=limit),
        target_state=target_state,
        now=now,
        monotonic_now=1.0,
    )


def test_auto_prime_zero_usage_still_uses_normal_period_key() -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("zero_usage",))
    periods = _eligible(
        workflow, _target_state(), _limit(used_percent=0, now=now), now=now
    )

    assert len(periods) == 1
    assert periods[0]["trigger_reasons"] == ("zero_usage",)
    assert periods[0]["period_key"].endswith(
        "|burst|2026-05-19T18:00:00+00:00|2026-05-19T23:00:00+00:00"
    )


def test_auto_prime_near_zero_full_window_uses_uninitialized_key() -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    periods = _eligible(
        workflow, _target_state(), _limit(used_percent=1, now=now), now=now
    )

    assert len(periods) == 1
    assert periods[0]["trigger_reasons"] == ("near_zero_full_window",)
    assert periods[0]["period_key"].endswith("|burst|uninitialized")


def test_auto_prime_sliding_reset_detects_moving_reset() -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("sliding_reset",))
    target_state = _target_state()

    assert not _eligible(
        workflow,
        target_state,
        _limit(used_percent=2, now=now),
        now=now,
    )
    periods = _eligible(
        workflow,
        target_state,
        _limit(used_percent=2, now=now + datetime.timedelta(seconds=90)),
        now=now + datetime.timedelta(seconds=90),
    )

    assert len(periods) == 1
    assert periods[0]["trigger_reasons"] == ("sliding_reset",)
    assert periods[0]["period_key"].endswith("|burst|uninitialized")


def test_auto_prime_period_key_churn_detects_near_zero_moving_period() -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("period_key_churn",))
    target_state = _target_state()

    assert not _eligible(
        workflow,
        target_state,
        _limit(used_percent=1, now=now),
        now=now,
    )
    periods = _eligible(
        workflow,
        target_state,
        _limit(used_percent=1, now=now + datetime.timedelta(seconds=90)),
        now=now + datetime.timedelta(seconds=90),
    )

    assert len(periods) == 1
    assert periods[0]["trigger_reasons"] == ("period_key_churn",)
    assert periods[0]["period_key"].endswith("|burst|uninitialized")


def test_auto_prime_uninitialized_key_prevents_repeat_ping() -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    target_state = _target_state()

    first = _eligible(workflow, target_state, _limit(used_percent=1, now=now), now=now)
    assert len(first) == 1
    primed_periods = target_state["primed_periods"]
    assert isinstance(primed_periods, dict)
    primed_periods[first[0]["period_key"]] = {"status": "ok"}

    second = _eligible(
        workflow,
        target_state,
        _limit(used_percent=1, now=now + datetime.timedelta(seconds=90)),
        now=now + datetime.timedelta(seconds=90),
    )
    assert second == []
