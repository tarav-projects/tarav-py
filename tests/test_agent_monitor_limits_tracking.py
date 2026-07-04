from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from agentos.agent.monitor.models import (
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorFrame,
    MonitorState,
    MonitorTarget,
    MonitorUsageTimeRow,
    MonitorWorkflowConfig,
)
from agentos.agent.monitor.render import format_monitor_frame, monitor_result_payload
import agentos.agent.monitor.workflows.auto_prime as auto_prime
import agentos.agent.monitor.workflows.limits_tracking as limits_tracking
from agentos.agent.monitor.workflows.state import (
    AutoPrimeTargetState,
    AutoPrimeWorkflowState,
    LimitsTargetState,
    LimitsWorkflowState,
)
from agentos.agent.monitor.workflows import (
    LimitsTrackingWorkflow,
)

from _monitor_helpers import _limit


def test_limits_tracking_refresh_uses_profile_resolved_runtime_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeAccountStatus:
        def summary(self) -> dict[str, object]:
            return {
                "limits": [],
                "raw": {"claude_policy_env": {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}},
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
    assert usage_row["burst_unit"]["usage_burst_units_left"] == pytest.approx(2.4, abs=0.05)  # type: ignore[index]
    assert usage_row["burst_unit"]["time_burst_units_left"] == pytest.approx(20.2, abs=0.05)  # type: ignore[index]
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
        _account_status(limits=[burst]), provider="codex"
    )

    usage_row = rows[0]
    assert isinstance(usage_row, MonitorUsageTimeRow)
    assert usage_row.variants == ()
    assert usage_row.burst_unit is None

def test_limits_tracking_unknown_provider_does_not_get_burst_unit_variant(
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
        _account_status(limits=[weekly]), provider="copilot-cli"
    )

    usage_row = rows[0]
    assert isinstance(usage_row, MonitorUsageTimeRow)
    assert usage_row.variants == ()
    assert usage_row.burst_unit is None
