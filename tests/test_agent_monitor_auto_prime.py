from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from _monitor_helpers import _limit
from tarav.l0._core.errors import CliError
from tarav.l1.agent.monitor import config as monitor_config
from tarav.l1.agent.monitor.clock import (
    AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM,
    MonitorClockSnapshot,
)
from tarav.l1.agent.monitor.models import (
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorFrame,
    MonitorState,
    MonitorTarget,
    MonitorWorkflowConfig,
)
from tarav.l1.agent.monitor.workflows import auto_prime
from tarav.l1.agent.monitor.workflows.auto_prime import (
    AutoPrimeZeroLimitsWorkflow,
    _auto_prime_status_part,
)
from tarav.l1.agent.monitor.workflows.builder import build_monitor_workflows
from tarav.l1.agent.monitor.workflows.state import (
    LimitsTargetState,
    LimitsWorkflowState,
)
from tarav.l1.agent.monitor.workflows._common import _target_key
from tarav.l1.agent.ping import AgentPingResult

FIRED = MonitorClockSnapshot(
    tick=1, alarms={}, fired_alarm_names=(AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM,)
)


def _target(account: str, provider: str = "codex") -> MonitorTarget:
    return MonitorTarget(
        provider=provider, account=account, home=Path(f"/tmp/{provider}-{account}")
    )


def _reading(
    target: MonitorTarget,
    *,
    elapsed_mins: int | None,
    status: str = "ok",
    used_percent: int = 0,
) -> LimitsTargetState:
    """A 300-minute burst window with ``elapsed_mins`` already elapsed."""
    limits = (
        []
        if elapsed_mins is None
        else [
            _limit(
                used_percent=used_percent,
                now=datetime.datetime.now(tz=datetime.UTC),
                end_offset_mins=300 - elapsed_mins,
            )
        ]
    )
    return LimitsTargetState(
        provider=target.provider,
        account=target.account,
        home=str(target.home),
        status=status,
        account_status={"limits": limits},
    )


def _workflow(*targets: MonitorTarget, threshold: float = 3) -> AutoPrimeZeroLimitsWorkflow:
    return AutoPrimeZeroLimitsWorkflow(
        MonitorWorkflowConfig(
            name=AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
            targets=targets,
            refresh_interval_sec=600,
            threshold_percent=threshold,
            raw_config={},
        )
    )


def _state(*readings: tuple[MonitorTarget, LimitsTargetState]) -> MonitorState:
    state = MonitorState()
    state.data[LIMITS_TRACKING_WORKFLOW] = LimitsWorkflowState(
        targets={_target_key(target): reading for target, reading in readings}
    )
    return state


@pytest.fixture
def pings(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the real ping and monitor log; record pinged accounts and events."""

    pinged: list[str] = []
    events: list[str] = []

    def fake_ping(reading: LimitsTargetState) -> AgentPingResult:
        pinged.append(reading.account)
        ok = reading.account != "broken"
        return AgentPingResult(
            ok=ok,
            model="gpt-6-luna",
            elapsed_ms=10,
            exit_code=0 if ok else 1,
            output="745" if ok else "",
            failure=None if ok else "model not supported",
        )

    monkeypatch.setattr(auto_prime, "_run_account_prime_ping", fake_ping)
    monkeypatch.setattr(
        auto_prime,
        "append_monitor_log_event",
        lambda *, event, **_: events.append(event),
    )
    return SimpleNamespace(accounts=pinged, events=events)


def test_pings_only_targets_whose_burst_window_is_not_running(
    pings: SimpleNamespace,
) -> None:
    fresh, expired, running, busy = (
        _target("fresh"),
        _target("expired"),
        _target("running"),
        _target("busy"),
    )
    state = _state(
        (fresh, _reading(fresh, elapsed_mins=5)),
        (expired, _reading(expired, elapsed_mins=320)),
        (running, _reading(running, elapsed_mins=10)),
        (busy, _reading(busy, elapsed_mins=120, used_percent=1)),
    )
    workflow = _workflow(fresh, expired, running, busy)

    workflow.loop(state, MonitorFrame(tick=1), FIRED)

    assert pings.accounts == ["fresh", "expired"]
    workflow_state = state.data[AUTO_PRIME_ZERO_LIMITS_WORKFLOW]
    assert workflow_state.last_scan == {"tick": 1, "pinged": 2, "failed": 0}
    assert workflow_state.targets[_target_key(running)].burst_elapsed_percent == 3.3
    assert _auto_prime_status_part(workflow_state.targets[_target_key(fresh)]) == (
        "ping ok just now"
    )
    assert _auto_prime_status_part(workflow_state.targets[_target_key(busy)]) is None


def test_does_not_ping_again_once_the_window_has_started(
    pings: SimpleNamespace,
) -> None:
    idle = _target("idle")
    state = _state((idle, _reading(idle, elapsed_mins=0)))
    workflow = _workflow(idle)

    workflow.loop(state, MonitorFrame(tick=1), FIRED)
    state.data[LIMITS_TRACKING_WORKFLOW].targets[_target_key(idle)] = _reading(
        idle, elapsed_mins=10
    )
    workflow.loop(state, MonitorFrame(tick=2), MonitorClockSnapshot(2, {}, ()))
    workflow.loop(state, MonitorFrame(tick=3), FIRED)

    assert pings.accounts == ["idle"]


def test_skips_targets_without_an_ok_burst_reading(pings: SimpleNamespace) -> None:
    errored, empty, missing, untracked = (
        _target("errored"),
        _target("empty"),
        _target("missing"),
        _target("untracked"),
    )
    state = _state(
        (errored, _reading(errored, elapsed_mins=0, status="error")),
        (empty, _reading(empty, elapsed_mins=None)),
    )

    _workflow(errored, empty, missing, untracked).loop(
        state, MonitorFrame(tick=1), FIRED
    )

    assert pings.accounts == []


def test_failed_ping_is_recorded_and_logged(pings: SimpleNamespace) -> None:
    broken = _target("broken")
    state = _state((broken, _reading(broken, elapsed_mins=0)))
    frame = MonitorFrame(tick=1)

    _workflow(broken).loop(state, frame, FIRED)

    target_state = state.data[AUTO_PRIME_ZERO_LIMITS_WORKFLOW].targets[
        _target_key(broken)
    ]
    assert target_state.last_error == {
        "message": "model not supported",
        "error_type": "ping-failed",
    }
    assert _auto_prime_status_part(target_state) == "ping failed just now"
    assert pings.events == ["auto_prime_failed"]
    rows = frame.blocks[0].rows
    assert any("codex/broken failed: model not supported" in row.value for row in rows)


def test_multiple_configs_merge_targets_interval_and_threshold() -> None:
    first = MonitorWorkflowConfig(
        name=AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
        targets=(_target("jp"),),
        refresh_interval_sec=600,
        threshold_percent=5,
        raw_config={},
    )
    second = MonitorWorkflowConfig(
        name=AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
        targets=(_target("jp"), _target("br", provider="claude-code")),
        refresh_interval_sec=300,
        threshold_percent=10,
        raw_config={},
    )

    (workflow,) = [
        workflow
        for workflow in build_monitor_workflows((first, second))
        if workflow.name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW
    ]

    assert [target.account for target in workflow.config.targets] == ["jp", "br"]
    assert workflow.refresh_interval_sec == 300
    assert workflow.threshold_percent == 10


def _load_with_targets(
    monkeypatch: pytest.MonkeyPatch,
    raw_config: dict[str, object],
    targets: tuple[MonitorTarget, ...],
) -> MonitorWorkflowConfig:
    monkeypatch.setattr(
        monitor_config,
        "load_chat_config_documents",
        lambda **_: ({"agent": {"accounts": {"monitor": [raw_config]}}},),
    )
    monkeypatch.setattr(monitor_config, "_load_targets", lambda *_, **__: targets)
    (loaded,) = monitor_config.load_monitor_workflow_configs()
    return loaded


def test_config_defaults_to_ten_minutes_and_three_percent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _load_with_targets(
        monkeypatch, {"workflow": AUTO_PRIME_ZERO_LIMITS_WORKFLOW}, (_target("jp"),)
    )

    assert loaded.refresh_interval_sec == 600
    assert loaded.threshold_percent == 3


def test_config_rejects_providers_other_than_codex_and_claude(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(CliError, match="not supported by auto-prime-zero-limits"):
        _load_with_targets(
            monkeypatch,
            {"workflow": AUTO_PRIME_ZERO_LIMITS_WORKFLOW},
            (_target("jp", provider="copilot-cli"),),
        )
