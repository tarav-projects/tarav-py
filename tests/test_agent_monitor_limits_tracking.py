from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from tarav.l1.agent.monitor.models import (
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorFrame,
    MonitorState,
    MonitorTarget,
    MonitorUsageTimeRow,
    MonitorWorkflowConfig,
)
from tarav.l1.agent.monitor.render import format_monitor_frame, monitor_result_payload
import tarav.l1.agent.monitor.workflows.auto_prime as auto_prime
import tarav.l1.agent.monitor.workflows.limits_tracking as limits_tracking
from tarav.l1.agent.monitor.workflows.state import (
    AutoPrimeTargetState,
    AutoPrimeWorkflowState,
    LimitsTargetState,
    LimitsWorkflowState,
)
from tarav.l1.agent.monitor.workflows import (
    LimitsTrackingWorkflow,
)
from tarav.l1.agent.usage_registry import append_usage_record
from tarav.l1.agent.providers.claude_code.usage_hooks import (
    CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE,
)
from tarav.l1.agent.providers.codex.usage_hooks import CODEX_SESSION_HOOK_USAGE_SOURCE
from tarav.l0.testing import TaravTestEnvironment

from _monitor_helpers import _limit

from tarav.l1.agent.monitor.burst_ratio import BurstRatioMeasurement


def _burst_ratios(accounts: dict[str, float]) -> BurstRatioMeasurement:
    return BurstRatioMeasurement(
        accounts=dict(accounts),
        computed_at=datetime.datetime.now(tz=datetime.UTC),
    )


def test_limits_tracking_refresh_uses_profile_resolved_runtime_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeAccountStatus:
        def summary(self) -> dict[str, object]:
            return {
                "limits": [],
                "raw": {
                    "claude_policy_env": {
                        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
                    }
                },
            }

    class FakeAgent:
        def account_status(self) -> FakeAccountStatus:
            return FakeAccountStatus()

    def fake_resolve_account_runtime_agent(**kwargs) -> FakeAgent:
        calls.append(kwargs)
        return FakeAgent()

    monkeypatch.setattr(
        limits_tracking,
        "resolve_account_runtime_agent",
        fake_resolve_account_runtime_agent,
    )
    home = tmp_path / "claude-br"
    target = MonitorTarget(
        provider="claude-code",
        account="browser-br",
        home=home,
        profile="claude-br",
    )
    workflow = LimitsTrackingWorkflow(
        MonitorWorkflowConfig(
            name=LIMITS_TRACKING_WORKFLOW,
            targets=(target,),
            refresh_interval_sec=60,
            raw_config={},
            start_path=tmp_path,
        )
    )
    target_state = workflow._target_state(
        LimitsWorkflowState(), target=target, target_key="target"
    )

    workflow._refresh_target(target_state, target=target, tick=7)

    assert calls == [
        {
            "provider": "claude-code",
            "account": "browser-br",
            "home": home,
            "profile": "claude-br",
            "start_path": tmp_path,
        }
    ]
    assert target_state.profile == "claude-br"
    assert target_state.start_path == str(tmp_path)
    assert target_state.account_status == {
        "limits": [],
        "raw": {"claude_policy_env": {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}},
    }


def _codex_hook_quota_payload(*, resets_at: int) -> dict[str, object]:
    return {
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": 17,
                "windowDurationMins": 10080,
                "resetsAt": resets_at,
            },
            "secondary": None,
        },
        "observation": {
            "sessionId": "session-123",
            "observedAt": "2026-08-11T12:01:00Z",
        },
    }


def test_limits_tracking_refresh_uses_fresh_claude_hook_observation_without_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    append_usage_record(
        provider="claude-code",
        account="om",
        home=tmp_path / "active-claude-home",
        source=CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE,
        payload={
            "rate_limits": {
                "five_hour": {
                    "used_percentage": 23,
                    "resets_at": int(
                        (
                            datetime.datetime.now(tz=datetime.UTC)
                            + datetime.timedelta(hours=1)
                        ).timestamp()
                    ),
                }
            },
            "observation": {"sessionId": "session-123"},
        },
    )
    monkeypatch.setattr(
        limits_tracking,
        "resolve_account_runtime_agent",
        lambda **kwargs: pytest.fail(f"provider should not be resolved: {kwargs}"),
    )
    target = MonitorTarget(
        provider="claude-code",
        account="om",
        home=tmp_path / "monitor-claude-home",
    )
    workflow = LimitsTrackingWorkflow(
        MonitorWorkflowConfig(
            name=LIMITS_TRACKING_WORKFLOW,
            targets=(target,),
            refresh_interval_sec=60,
            raw_config={},
        )
    )
    target_state = workflow._target_state(
        LimitsWorkflowState(), target=target, target_key="target"
    )

    workflow._refresh_target(target_state, target=target, tick=1)

    assert target_state.status == "ok"
    assert target_state.account_status is not None
    assert (
        target_state.account_status["limits"][0]["usage_over_time"]["used_percent"]
        == 23
    )  # type: ignore[index]
    assert (
        target_state.account_status["raw"]["usage_record"]["source"]
        == CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE
    )  # type: ignore[index]


def test_limits_tracking_refresh_uses_fresh_account_hook_observation_without_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    observed_home = tmp_path / "active-codex-home"
    target_home = tmp_path / "monitor-codex-home"
    append_usage_record(
        provider="codex",
        account="jp",
        home=observed_home,
        source=CODEX_SESSION_HOOK_USAGE_SOURCE,
        payload=_codex_hook_quota_payload(
            resets_at=int(
                (
                    datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(days=1)
                ).timestamp()
            )
        ),
    )
    monkeypatch.setattr(
        limits_tracking,
        "resolve_account_runtime_agent",
        lambda **kwargs: pytest.fail(f"provider should not be resolved: {kwargs}"),
    )
    target = MonitorTarget(provider="codex", account="jp", home=target_home)
    workflow = LimitsTrackingWorkflow(
        MonitorWorkflowConfig(
            name=LIMITS_TRACKING_WORKFLOW,
            targets=(target,),
            refresh_interval_sec=60,
            raw_config={},
        )
    )
    target_state = workflow._target_state(
        LimitsWorkflowState(), target=target, target_key="target"
    )

    workflow._refresh_target(target_state, target=target, tick=1)

    assert target_state.status == "ok"
    assert target_state.account_status is not None
    assert (
        target_state.account_status["limits"][0]["usage_over_time"]["used_percent"]
        == 17
    )  # type: ignore[index]
    assert (
        target_state.account_status["raw"]["usage_record"]["source"]
        == CODEX_SESSION_HOOK_USAGE_SOURCE
    )  # type: ignore[index]


@pytest.mark.parametrize("stale_reason", ["age", "reset"])
def test_limits_tracking_refresh_probes_provider_when_hook_observation_is_stale(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stale_reason: str,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    target_home = tmp_path / "monitor-codex-home"
    reset_at = (
        1
        if stale_reason == "reset"
        else int(
            (
                datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(days=1)
            ).timestamp()
        )
    )
    append_usage_record(
        provider="codex",
        account="jp",
        home=tmp_path / "active-codex-home",
        source=CODEX_SESSION_HOOK_USAGE_SOURCE,
        payload=_codex_hook_quota_payload(resets_at=reset_at),
    )
    if stale_reason == "age":
        monkeypatch.setattr(limits_tracking, "usage_record_age_sec", lambda value: 61)

    calls: list[object] = []

    class FakeStatus:
        def summary(self) -> dict[str, object]:
            return {"limits": [], "raw": {}}

    class FakeAgent:
        def account_status(self) -> FakeStatus:
            calls.append("account_status")
            return FakeStatus()

    monkeypatch.setattr(
        limits_tracking,
        "resolve_account_runtime_agent",
        lambda **kwargs: FakeAgent(),
    )
    target = MonitorTarget(provider="codex", account="jp", home=target_home)
    workflow = LimitsTrackingWorkflow(
        MonitorWorkflowConfig(
            name=LIMITS_TRACKING_WORKFLOW,
            targets=(target,),
            refresh_interval_sec=60,
            raw_config={},
        )
    )
    target_state = workflow._target_state(
        LimitsWorkflowState(), target=target, target_key="target"
    )

    workflow._refresh_target(target_state, target=target, tick=1)

    assert calls == ["account_status"]


def _account_status(
    *,
    usage_record_status: str = "fresh",
    age_sec: int | None = None,
    limits: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    usage_record: dict[str, object] = {
        "status": usage_record_status,
        "recorded_at": now.isoformat(),
    }
    if age_sec is not None:
        usage_record["age_sec"] = age_sec
    return {
        "limits": limits if limits is not None else [_limit(used_percent=20, now=now)],
        "raw": {
            "usage_record": usage_record,
        },
    }


def _freeze_monitor_now(
    monkeypatch: pytest.MonkeyPatch, now: datetime.datetime
) -> None:
    original_datetime = datetime.datetime

    class FixedDateTime(original_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            if tz is None:
                return now.replace(tzinfo=None)
            return now.astimezone(tz)

    monkeypatch.setattr(auto_prime.datetime, "datetime", FixedDateTime)


def test_limits_tracking_account_lane_includes_fetch_and_prime_status() -> None:
    target = MonitorTarget(
        provider="codex",
        account="jp",
        home=Path("/tmp/codex-jp"),
    )
    workflow = LimitsTrackingWorkflow(
        MonitorWorkflowConfig(
            name=LIMITS_TRACKING_WORKFLOW,
            targets=(target,),
            refresh_interval_sec=60,
            raw_config={},
        )
    )
    state = MonitorState(
        data={
            LIMITS_TRACKING_WORKFLOW: LimitsWorkflowState(
                targets={
                    "codex/jp@/tmp/codex-jp": LimitsTargetState(
                        provider="codex",
                        account="jp",
                        home="/tmp/codex-jp",
                        status="ok",
                        account_status=_account_status(),
                    )
                },
            ),
            AUTO_PRIME_ZERO_LIMITS_WORKFLOW: AutoPrimeWorkflowState(
                targets={
                    "codex/jp@/tmp/codex-jp": AutoPrimeTargetState(
                        last_decision={
                            "limit_id": "burst",
                            "classification": "non-primed",
                            "action": "pinged",
                        }
                    )
                }
            ),
        }
    )
    frame = MonitorFrame()
    workflow_state = state.data[LIMITS_TRACKING_WORKFLOW]
    assert isinstance(workflow_state, LimitsWorkflowState)

    workflow._write_frame_block(frame, state=state, workflow_state=workflow_state)
    rendered = format_monitor_frame(frame)
    payload = monitor_result_payload(frame, state)
    account_row = payload["frame"]["blocks"][0]["rows"][0]  # type: ignore[index]

    assert "⬢ codex/jp:" in rendered
    assert "fresh · burst non-primed/pinged" in rendered
    assert "⬢ codex/jp:            | fresh · burst non-primed/pinged" in rendered
    assert "usage/time" in rendered
    assert isinstance(account_row, dict)
    assert account_row["status"] == "fresh · burst non-primed/pinged"


def test_limits_tracking_weekly_usage_time_animates_burst_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    _freeze_monitor_now(monkeypatch, now)
    target = MonitorTarget(
        provider="codex",
        account="jp",
        home=Path("/tmp/codex-jp"),
    )
    workflow = LimitsTrackingWorkflow(
        MonitorWorkflowConfig(
            name=LIMITS_TRACKING_WORKFLOW,
            targets=(target,),
            refresh_interval_sec=60,
            raw_config={},
        )
    )
    weekly = _limit(
        used_percent=63,
        now=now,
        limit_id="weekly",
        end_offset_mins=6048,
        duration_mins=10080,
    )
    state = MonitorState(
        data={
            LIMITS_TRACKING_WORKFLOW: LimitsWorkflowState(
                targets={
                    "codex/jp@/tmp/codex-jp": LimitsTargetState(
                        provider="codex",
                        account="jp",
                        home="/tmp/codex-jp",
                        status="ok",
                        account_status=_account_status(limits=[weekly]),
                    )
                },
                burst_ratios=_burst_ratios({"codex/jp": 15.7}),
            ),
        }
    )
    frame = MonitorFrame()
    workflow_state = state.data[LIMITS_TRACKING_WORKFLOW]
    assert isinstance(workflow_state, LimitsWorkflowState)

    workflow._write_frame_block(frame, state=state, workflow_state=workflow_state)
    payload = monitor_result_payload(frame, state)
    usage_row = payload["frame"]["blocks"][0]["rows"][1]  # type: ignore[index]

    assert "63% / 40% = 1.6 [%]" in format_monitor_frame(frame)
    assert isinstance(usage_row, dict)
    assert usage_row["variants"] == [
        {
            "label": "    usage/time [used]",
            "value": "63% / 40% = 1.6 [%]",
        },
        {
            "label": "    time/usage [left]",
            "value": "20.2 / 2.4 = 8.6 [Burst]",
        },
    ]
    assert usage_row["burst_unit"]["weekly_burst_percent"] == 15.7  # type: ignore[index]
    assert usage_row["burst_unit"]["usage_burst_units_left"] == pytest.approx(
        2.4, abs=0.05
    )  # type: ignore[index]
    assert usage_row["burst_unit"]["time_burst_units_left"] == pytest.approx(
        20.2, abs=0.05
    )  # type: ignore[index]
    assert usage_row["burst_unit"]["left_ratio"] == pytest.approx(8.6, abs=0.05)  # type: ignore[index]
    assert usage_row["used_percent"] == 63
    assert usage_row["elapsed_percent"] == 40

    for _ in range(5):
        frame.step_animations()

    rendered = format_monitor_frame(frame)
    assert "usage/time [used]" in rendered
    assert "63% / 40% = 1.6 [%]" in rendered

    state.data["monitor_display"] = {"usage_variant": "left"}

    rendered = format_monitor_frame(frame, state)
    assert "time/usage [left]" in rendered
    assert "20.2 / 2.4 = 8.6 [Burst]" in rendered


def test_limits_tracking_burst_limit_does_not_get_weekly_burst_unit_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    _freeze_monitor_now(monkeypatch, now)
    burst = _limit(used_percent=63, now=now, limit_id="burst")

    rows = limits_tracking._account_limit_rows(
        _account_status(limits=[burst]),
        provider="codex",
        account="jp",
        workflow_state=LimitsWorkflowState(
            burst_ratios=_burst_ratios({"codex/jp": 15.7})
        ),
    )

    usage_row = rows[0]
    assert isinstance(usage_row, MonitorUsageTimeRow)
    assert usage_row.variants == ()
    assert usage_row.burst_unit is None


def test_limits_tracking_unmeasured_provider_does_not_get_burst_unit_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    _freeze_monitor_now(monkeypatch, now)
    weekly = _limit(
        used_percent=63,
        now=now,
        limit_id="weekly",
        end_offset_mins=6048,
        duration_mins=10080,
    )

    rows = limits_tracking._account_limit_rows(
        _account_status(limits=[weekly]),
        provider="copilot-cli",
        account="jp",
        workflow_state=LimitsWorkflowState(
            burst_ratios=_burst_ratios({"codex/jp": 15.7})
        ),
    )

    usage_row = rows[0]
    assert isinstance(usage_row, MonitorUsageTimeRow)
    assert usage_row.variants == ()
    assert usage_row.burst_unit is None
