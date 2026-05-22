from __future__ import annotations

import datetime
import json
from pathlib import Path

from agentos.agent.monitor.auto_prime_registry import auto_prime_event_registry_path
from agentos.agent.monitor.config import _auto_prime_triggers, _target_limit_ids
from agentos.agent.monitor.loop import MonitorLoop
from agentos.agent.monitor.models import (
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorState,
    MonitorTarget,
    MonitorWorkflowConfig,
)
import agentos.agent.monitor.workflows as monitor_workflows
from agentos.agent.monitor.workflows import AutoPrimeZeroLimitsWorkflow


def _set_fake_agentos_home(monkeypatch, root: Path) -> Path:
    agentos_home = root / ".agentos"
    agentos_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    return agentos_home


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


def _source_state(
    *, limit: dict[str, object], recorded_at: datetime.datetime | None = None
) -> dict[str, object]:
    account_status: dict[str, object] = {"limits": [limit]}
    if recorded_at is not None:
        account_status["raw"] = {
            "usage_record": {
                "recorded_at": recorded_at.isoformat(),
            }
        }
    return {
        "status": "ok",
        "provider": "codex",
        "account": "jp",
        "home": "/tmp/codex-jp",
        "account_status": account_status,
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
        scan_at=now,
        monotonic_now=1.0,
    )


def _events() -> list[dict[str, object]]:
    path = auto_prime_event_registry_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_auto_prime_period_keys_distinguish_zero_and_near_zero_usage(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    zero_periods = _eligible(
        _workflow(triggers=("zero_usage",)),
        _target_state(),
        _limit(used_percent=0, now=now),
        now=now,
    )

    assert len(zero_periods) == 1
    assert zero_periods[0]["trigger_reasons"] == ("zero_usage",)
    assert zero_periods[0]["period_key"].endswith(
        "|burst|2026-05-19T18:00:00+00:00|2026-05-19T23:00:00+00:00"
    )

    workflow = _workflow(triggers=("near_zero_full_window",))
    target_state = _target_state()
    first = _eligible(workflow, target_state, _limit(used_percent=1, now=now), now=now)
    assert len(first) == 1
    assert first[0]["trigger_reasons"] == ("near_zero_full_window",)
    assert first[0]["period_key"].endswith("|burst|uninitialized")
    primed_periods = target_state["primed_periods"]
    assert isinstance(primed_periods, dict)
    primed_periods[first[0]["period_key"]] = {
        "status": "ping_succeeded",
        "verification_status": "pending_verification",
        "uninitialized": True,
        "next_retry_after_monotonic": 600.0,
    }

    second = _eligible(
        workflow,
        target_state,
        _limit(used_percent=1, now=now + datetime.timedelta(seconds=90)),
        now=now + datetime.timedelta(seconds=90),
    )
    assert second == []
    assert [event["event_type"] for event in _events()] == [
        "eligible",
        "eligible",
        "skipped_already_primed",
    ]
    assert "stdout" not in json.dumps(_events())


def test_auto_prime_moving_period_triggers_use_uninitialized_key(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    now = datetime.datetime.now(tz=datetime.UTC)

    for trigger, used_percent in [
        ("sliding_reset", 2),
        ("period_key_churn", 1),
    ]:
        workflow = _workflow(triggers=(trigger,))
        target_state = _target_state()
        assert not _eligible(
            workflow,
            target_state,
            _limit(used_percent=used_percent, now=now),
            now=now,
        )

        periods = _eligible(
            workflow,
            target_state,
            _limit(used_percent=used_percent, now=now + datetime.timedelta(seconds=90)),
            now=now + datetime.timedelta(seconds=90),
        )
        assert len(periods) == 1
        assert periods[0]["trigger_reasons"] == (trigger,)
        assert periods[0]["period_key"].endswith("|burst|uninitialized")


def test_auto_prime_uses_recorded_at_for_full_window_detection(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    recorded_at = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    scan_at = recorded_at + datetime.timedelta(minutes=10)
    workflow = _workflow(triggers=("near_zero_full_window",))
    target_state = _target_state()

    periods = workflow._eligible_periods(
        _source_state(
            limit=_limit(used_percent=1, now=recorded_at),
            recorded_at=recorded_at,
        ),
        target_state=target_state,
        scan_at=scan_at,
        monotonic_now=1.0,
    )

    assert len(periods) == 1
    assert periods[0]["observed_at"] == recorded_at.isoformat()
    assert periods[0]["scan_at"] == scan_at.isoformat()


def test_auto_prime_retries_uninitialized_after_cooldown(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    target_state = _target_state()
    first = _eligible(
        workflow,
        target_state,
        _limit(used_percent=1, now=now),
        now=now,
    )
    period_key = str(first[0]["period_key"])
    primed_periods = target_state["primed_periods"]
    assert isinstance(primed_periods, dict)
    primed_periods[period_key] = {
        "status": "ping_succeeded",
        "verification_status": "ineffective",
        "uninitialized": True,
        "next_retry_after_monotonic": 10.0,
    }

    retry = workflow._eligible_periods(
        _source_state(limit=_limit(used_percent=1, now=now)),
        target_state=target_state,
        scan_at=now,
        monotonic_now=11.0,
    )

    assert len(retry) == 1
    assert retry[0]["period_key"] == period_key


def test_auto_prime_verification_clears_uninitialized_after_stable_observation(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    target_state = _target_state()
    period_key = "codex|jp|/tmp/codex-jp|burst|uninitialized"
    target_state["primed_periods"] = {
        period_key: {
            "status": "ping_succeeded",
            "verification_status": "pending_verification",
            "uninitialized": True,
            "trigger_reasons": ("near_zero_full_window",),
            "last_attempt_at": now.isoformat(),
        }
    }

    workflow._verify_existing_primes(
        _source_state(limit=_limit(used_percent=5, now=now)),
        target_state=target_state,
        scan_at=now,
        tick=7,
    )

    assert period_key not in target_state["primed_periods"]
    assert _events()[-1]["event_type"] == "verification_effective"


def test_auto_prime_verification_marks_persistent_uninitialized_ineffective(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    target_state = _target_state()
    period_key = "codex|jp|/tmp/codex-jp|burst|uninitialized"
    target_state["primed_periods"] = {
        period_key: {
            "status": "ping_succeeded",
            "verification_status": "pending_verification",
            "uninitialized": True,
            "trigger_reasons": ("near_zero_full_window",),
            "last_attempt_at": (
                now - datetime.timedelta(seconds=601)
            ).isoformat(),
        }
    }

    workflow._verify_existing_primes(
        _source_state(limit=_limit(used_percent=1, now=now)),
        target_state=target_state,
        scan_at=now,
        tick=8,
    )

    primed_period = target_state["primed_periods"][period_key]  # type: ignore[index]
    assert primed_period["verification_status"] == "ineffective"  # type: ignore[index]
    assert _events()[-1]["event_type"] == "verification_ineffective"


def test_auto_prime_attempts_write_durable_events_and_do_not_run_live_provider(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []

    def fake_ping(source_target_state: dict[str, object]) -> None:
        calls.append(source_target_state)

    monkeypatch.setattr(monitor_workflows, "_run_account_prime_ping", fake_ping)
    now = datetime.datetime.now(tz=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    state = MonitorState(
        data={
            LIMITS_TRACKING_WORKFLOW: {
                "targets": {
                    "codex/jp@/tmp/codex-jp": _source_state(
                        limit=_limit(used_percent=1, now=now)
                    ),
                    "codex/mm@/tmp/codex-mm": _source_state(
                        limit=_limit(used_percent=1, now=now)
                    ),
                }
            }
        }
    )
    workflow_state = workflow._workflow_state(state)

    workflow._scan_and_prime(state, workflow_state=workflow_state, tick=3)

    assert len(calls) == 1
    assert workflow_state["last_scan"]["pinged"] == 1  # type: ignore[index]
    event_types = [event["event_type"] for event in _events()]
    assert event_types == ["eligible", "attempt_started", "attempt_succeeded"]


def test_auto_prime_partial_config_maps_merge_with_defaults() -> None:
    raw_config: dict[str, object] = {
        "target_limits": {"codex": ["weekly"]},
        "triggers": {"codex": ["zero_usage"]},
    }

    assert _target_limit_ids(raw_config, field_name="target_limits") == {
        "codex": ("weekly",),
        "claude-code": ("burst",),
    }
    assert _auto_prime_triggers(raw_config, field_name="triggers") == {
        "codex": ("zero_usage",),
        "claude-code": ("zero_usage",),
    }


def test_monitor_loop_surfaces_config_fingerprint_drift() -> None:
    loop = MonitorLoop(
        workflows=(),
        interval_sec=0,
        max_ticks=1,
        config_fingerprint="old",
        config_fingerprint_loader=lambda: "new",
    )

    loop._check_config_fingerprint()

    setup = loop.state.data["monitor_setup"]
    assert isinstance(setup, dict)
    assert setup["config_stale"] is True
    assert setup["current_config_fingerprint"] == "new"
