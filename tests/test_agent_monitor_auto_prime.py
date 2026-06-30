from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.monitor.auto_prime_registry import (
    AUTO_PRIME_EVENT_ATTEMPT_STARTED,
    AUTO_PRIME_EVENT_ATTEMPT_SUCCEEDED,
    AUTO_PRIME_EVENT_ELIGIBLE,
    AUTO_PRIME_EVENT_SKIPPED_ALREADY_PRIMED,
    AUTO_PRIME_EVENT_VERIFICATION_EFFECTIVE,
    AUTO_PRIME_EVENT_VERIFICATION_INEFFECTIVE,
    auto_prime_event_registry_path,
)
from agentos.agent.monitor.config import (
    _auto_prime_triggers,
    _target_limit_ids,
    load_monitor_workflow_configs,
)
from agentos.agent.monitor.loop import MonitorLoop, _workflow_alarm_names
from agentos.agent.monitor.models import (
    AUTO_PRIME_PING_SUCCEEDED_STATUS,
    AUTO_PRIME_VERIFICATION_EFFECTIVE,
    AUTO_PRIME_VERIFICATION_INEFFECTIVE,
    AUTO_PRIME_VERIFICATION_PENDING,
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorAccountRow,
    MonitorColumnVariant,
    MonitorFrame,
    MonitorRenderContext,
    MonitorState,
    MonitorTarget,
    MonitorUsageTimeRow,
    MonitorWorkflowConfig,
)
from agentos.agent.monitor.clock import (
    LIMITS_TRACKING_PERIODIC_ALARM,
    MONITOR_USAGE_VARIANT_TOGGLE_ALARM,
)
from agentos.agent.monitor.render import format_monitor_frame, monitor_result_payload
import agentos.agent.monitor.workflows as monitor_workflows
from agentos.agent.monitor.workflows import (
    AutoPrimeZeroLimitsWorkflow,
    LimitsTrackingWorkflow,
)
from agentos.agent.account_status import AgentAccountContext
from agentos.agent.primitives import AgentPingConfig
from agentos.agent.run_runtime import AgentRunResult
import agentos.claude.keychain as claude_keychain
from agentos.testing import AgentosTestEnvironment

from _helpers import codex_auth_json, write_claude_home, write_text_file, seed_claude_account, seed_codex_account


def _set_fake_agentos_home(monkeypatch, root: Path) -> Path:
    environment = AgentosTestEnvironment.create(root)
    environment.apply_environment(monkeypatch.setenv)
    return environment.agentos_home


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


def test_monitor_profile_target_accepts_explicit_scoped_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-jp"
    auth_file = tmp_path / "auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_jp"))
    seed_codex_account("jp")
    environment.write_profile(
        "codex-jp",
        provider="codex",
        accounts=["jp"],
        homes=[str(home)],
    )
    environment.write_global_config(
        agent={
            "accounts": {
                "monitor": [
                    {
                        "workflow": AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
                        "targets": [
                            {
                                "profile": "codex-jp",
                                "provider": "codex",
                                "account": "jp",
                                "home": str(home),
                            }
                        ],
                    }
                ]
            }
        }
    )

    configs = load_monitor_workflow_configs(start_path=tmp_path)

    assert configs[0].targets[0].profile == "codex-jp"
    assert configs[0].targets[0].home == home.resolve()


def test_monitor_profile_target_rejects_unscoped_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    allowed_home = tmp_path / "codex-jp"
    blocked_home = tmp_path / "codex-blocked"
    auth_file = tmp_path / "auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_jp"))
    seed_codex_account("jp")
    environment.write_profile(
        "codex-jp",
        provider="codex",
        accounts=["jp"],
        homes=[str(allowed_home)],
    )
    environment.write_global_config(
        agent={
            "accounts": {
                "monitor": [
                    {
                        "workflow": AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
                        "targets": [
                            {
                                "profile": "codex-jp",
                                "provider": "codex",
                                "account": "jp",
                                "home": str(blocked_home),
                            }
                        ],
                    }
                ]
            }
        }
    )

    with pytest.raises(CliError, match="home must be allowed"):
        load_monitor_workflow_configs(start_path=tmp_path)


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
        monitor_workflows,
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
    target_state = workflow._target_state({}, target=target, target_key="target")

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
    assert target_state["profile"] == "claude-br"
    assert target_state["start_path"] == str(tmp_path)
    assert target_state["account_status"] == {
        "limits": [],
        "raw": {"claude_policy_env": {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}},
    }


def _limit(
    *,
    used_percent: int,
    now: datetime.datetime,
    limit_id: str = "burst",
    end_offset_mins: int = 300,
    duration_mins: int = 300,
) -> dict[str, object]:
    period_ends_at = now + datetime.timedelta(minutes=end_offset_mins)
    period_started_at = period_ends_at - datetime.timedelta(minutes=duration_mins)
    return {
        "limit_id": limit_id,
        "usage_over_time": {
            "used_percent": used_percent,
            "period_started_at": period_started_at.isoformat(),
            "period_ends_at": period_ends_at.isoformat(),
            "period_duration_mins": duration_mins,
            "resets_at": period_ends_at.isoformat(),
        },
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

    monkeypatch.setattr(monitor_workflows.datetime, "datetime", FixedDateTime)


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


def test_monitor_account_row_renders_status_as_full_lane() -> None:
    row = MonitorAccountRow(label="account:", status="fresh")
    context = MonitorRenderContext(
        label_width=12,
        value_width=10,
        suffix_width=8,
        row_indent="",
    )

    rendered = row.render_frame(context)

    assert rendered[:12] == "account:    "
    assert rendered[12:15] == " | "
    assert rendered[15:].startswith("fresh")
    assert rendered.count("|") == 1
    assert row.summary()["status"] == "fresh"


def test_usage_time_row_variant_follows_render_context() -> None:
    row = MonitorUsageTimeRow(
        label="    usage/time [used]",
        value="63% / 40% = 1.6 [%]",
        suffix="Weekly",
        used_percent=63,
        elapsed_percent=40,
        ratio=1.575,
        variants=(
            MonitorColumnVariant(
                label="    usage/time [used]",
                value="63% / 40% = 1.6 [%]",
            ),
            MonitorColumnVariant(
                label="    time/usage [left]",
                value="20.2 / 2.4 = 8.6 [Burst]",
            ),
        ),
    )
    used_context = MonitorRenderContext(row_indent="")
    left_context = MonitorRenderContext(row_indent="", usage_variant="left")

    assert "usage/time [used]" in row.render_frame(used_context)
    assert "63% / 40% = 1.6 [%]" in row.render_frame(used_context)
    for _ in range(5):
        row.step_animation()
    assert "63% / 40% = 1.6 [%]" in row.render_frame(used_context)
    assert "usage/time [used]" in row.render_frame(used_context)

    assert "time/usage [left]" in row.render_frame(left_context)
    assert "20.2 / 2.4 = 8.6 [Burst]" in row.render_frame(left_context)


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
            LIMITS_TRACKING_WORKFLOW: {
                "targets": {
                    "codex/jp@/tmp/codex-jp": {
                        "status": "ok",
                        "account_status": _account_status(),
                    }
                },
            },
            AUTO_PRIME_ZERO_LIMITS_WORKFLOW: {
                "targets": {
                    "codex/jp@/tmp/codex-jp": {
                        "last_decision": {
                            "limit_id": "burst",
                            "classification": "non-primed",
                            "action": "pinged",
                        }
                    }
                }
            },
        }
    )
    frame = MonitorFrame()
    workflow_state = state.data[LIMITS_TRACKING_WORKFLOW]
    assert isinstance(workflow_state, dict)

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
            LIMITS_TRACKING_WORKFLOW: {
                "targets": {
                    "codex/jp@/tmp/codex-jp": {
                        "status": "ok",
                        "account_status": _account_status(limits=[weekly]),
                    }
                },
            },
        }
    )
    frame = MonitorFrame()
    workflow_state = state.data[LIMITS_TRACKING_WORKFLOW]
    assert isinstance(workflow_state, dict)

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

    rows = monitor_workflows._account_limit_rows(
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

    rows = monitor_workflows._account_limit_rows(
        _account_status(limits=[weekly]), provider="copilot-cli"
    )

    usage_row = rows[0]
    assert isinstance(usage_row, MonitorUsageTimeRow)
    assert usage_row.variants == ()
    assert usage_row.burst_unit is None


def test_auto_prime_status_part_uses_priority_order(monkeypatch) -> None:
    monkeypatch.setattr(monitor_workflows.time, "monotonic", lambda: 100.0)

    assert (
        monitor_workflows._auto_prime_status_part(
            {
                "last_decision": {
                    "limit_id": "burst",
                    "classification": "non-primed",
                    "action": "pinged",
                },
                "last_error": {"message": "failed"},
            }
        )
        == "burst non-primed/pinged"
    )
    assert (
        monitor_workflows._auto_prime_status_part({"last_error": {"message": "failed"}})
        == "prime failed"
    )
    assert (
        monitor_workflows._auto_prime_status_part(
            {
                "primed_periods": {
                    "burst": {
                        "verification_status": AUTO_PRIME_VERIFICATION_INEFFECTIVE,
                        "next_retry_after_monotonic": 580.0,
                    }
                }
            }
        )
        == "prime ineffective"
    )
    assert (
        monitor_workflows._auto_prime_status_part(
            {
                "primed_periods": {
                    "burst": {
                        "verification_status": AUTO_PRIME_VERIFICATION_PENDING,
                        "next_retry_after_monotonic": 580.0,
                    }
                }
            }
        )
        == "prime retry in 8m"
    )
    assert (
        monitor_workflows._auto_prime_status_part(
            {
                "retry_after_monotonic": 580.0,
            }
        )
        == "prime retry in 8m"
    )
    assert (
        monitor_workflows._auto_prime_status_part(
            {
                "primed_periods": {
                    "burst": {
                        "verification_status": AUTO_PRIME_VERIFICATION_PENDING,
                    }
                }
            }
        )
        == "prime pending"
    )
    assert (
        monitor_workflows._auto_prime_status_part(
            {
                "primed_periods": {
                    "burst": {
                        "verification_status": AUTO_PRIME_VERIFICATION_EFFECTIVE,
                    }
                }
            }
        )
        == "primed"
    )


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
        "status": AUTO_PRIME_PING_SUCCEEDED_STATUS,
        "verification_status": AUTO_PRIME_VERIFICATION_PENDING,
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
        AUTO_PRIME_EVENT_ELIGIBLE,
        AUTO_PRIME_EVENT_ELIGIBLE,
        AUTO_PRIME_EVENT_SKIPPED_ALREADY_PRIMED,
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
        "status": AUTO_PRIME_PING_SUCCEEDED_STATUS,
        "verification_status": AUTO_PRIME_VERIFICATION_INEFFECTIVE,
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
            "status": AUTO_PRIME_PING_SUCCEEDED_STATUS,
            "verification_status": AUTO_PRIME_VERIFICATION_PENDING,
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
    assert _events()[-1]["event_type"] == AUTO_PRIME_EVENT_VERIFICATION_EFFECTIVE


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
            "status": AUTO_PRIME_PING_SUCCEEDED_STATUS,
            "verification_status": AUTO_PRIME_VERIFICATION_PENDING,
            "uninitialized": True,
            "trigger_reasons": ("near_zero_full_window",),
            "last_attempt_at": (now - datetime.timedelta(seconds=601)).isoformat(),
        }
    }

    workflow._verify_existing_primes(
        _source_state(limit=_limit(used_percent=1, now=now)),
        target_state=target_state,
        scan_at=now,
        tick=8,
    )

    primed_period = target_state["primed_periods"][period_key]  # type: ignore[index]
    assert primed_period["verification_status"] == AUTO_PRIME_VERIFICATION_INEFFECTIVE  # type: ignore[index]
    assert _events()[-1]["event_type"] == AUTO_PRIME_EVENT_VERIFICATION_INEFFECTIVE


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
    target_state = workflow_state["targets"]["codex/jp@/tmp/codex-jp"]  # type: ignore[index]
    assert target_state["last_decision"]["limit_id"] == "burst"  # type: ignore[index]
    assert target_state["last_decision"]["classification"] == "non-primed"  # type: ignore[index]
    assert target_state["last_decision"]["action"] == "pinged"  # type: ignore[index]
    event_types = [event["event_type"] for event in _events()]
    assert event_types == [
        AUTO_PRIME_EVENT_ELIGIBLE,
        AUTO_PRIME_EVENT_ATTEMPT_STARTED,
        AUTO_PRIME_EVENT_ATTEMPT_SUCCEEDED,
    ]


def test_auto_prime_ping_records_claude_verified_auth_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_keychain.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    seed_claude_account("browser-br", account_uuid="acc_browser-br")
    monkeypatch.setattr(
        monitor_workflows,
        "resolve_account_runtime_agent",
        lambda **kwargs: _FakeClaudePrimeAgent(home=Path(kwargs["home"])),
    )

    monitor_workflows._run_account_prime_ping(
        {
            "provider": "claude-code",
            "account": "browser-br",
            "home": str(home),
        }
    )

    # Auto-prime no longer auto-promotes credentials into the old registry
    # (disconnected in 658; new-model capture workflow is a deferred re-integration).
    assert not (
        environment.agentos_home / "accounts" / "claude-code" / "verifications.jsonl"
    ).exists()


def test_auto_prime_ping_uses_profile_resolved_runtime_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    home = tmp_path / "codex-br"

    def fake_resolve_account_runtime_agent(**kwargs) -> _FakeCodexPrimeAgent:
        calls.append(kwargs)
        return _FakeCodexPrimeAgent(home=Path(kwargs["home"]))

    monkeypatch.setattr(
        monitor_workflows,
        "resolve_account_runtime_agent",
        fake_resolve_account_runtime_agent,
    )

    monitor_workflows._run_account_prime_ping(
        {
            "provider": "codex",
            "account": "br",
            "home": str(home),
            "profile": "codex-br",
            "start_path": str(tmp_path),
        }
    )

    assert calls == [
        {
            "provider": "codex",
            "account": "br",
            "home": home,
            "profile": "codex-br",
            "start_path": tmp_path,
        }
    ]


def test_auto_prime_ping_records_codex_verified_auth_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-br"
    write_text_file(home / "auth.json", codex_auth_json(account_id="acc_br", email="br@example.com"))
    seed_codex_account("br")
    monkeypatch.setattr(
        monitor_workflows,
        "resolve_account_runtime_agent",
        lambda **kwargs: _FakeCodexPrimeAgent(home=Path(kwargs["home"])),
    )

    monitor_workflows._run_account_prime_ping(
        {
            "provider": "codex",
            "account": "br",
            "home": str(home),
        }
    )

    # Auto-prime no longer auto-promotes credentials into the old registry (658).
    assert not (
        environment.agentos_home / "accounts" / "codex" / "verifications.jsonl"
    ).exists()


def test_auto_prime_decisions_only_include_configured_limits() -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    target_state = _target_state()
    source_state = _source_state(
        limit=_limit(used_percent=40, now=now),
    )
    account_status = source_state["account_status"]
    assert isinstance(account_status, dict)
    account_status["limits"] = [
        _limit(used_percent=40, now=now, limit_id="burst"),
        _limit(used_percent=1, now=now, limit_id="weekly"),
    ]

    periods = workflow._eligible_periods(
        source_state,
        target_state=target_state,
        scan_at=now,
        monotonic_now=1.0,
        tick=9,
    )

    assert periods == []
    assert target_state["last_decision"]["limit_id"] == "burst"  # type: ignore[index]
    assert target_state["last_decision"]["classification"] == "primed"  # type: ignore[index]
    assert target_state["last_decision"]["action"] == "skipped"  # type: ignore[index]
    assert [decision["limit_id"] for decision in target_state["last_decisions"]] == [  # type: ignore[index]
        "burst"
    ]


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


def test_monitor_loop_usage_variant_toggle_alarm_changes_display_only() -> None:
    loop = MonitorLoop(workflows=(), interval_sec=0, max_ticks=1)
    assert loop.state.data["monitor_display"] == {"usage_variant": "used"}
    row = MonitorUsageTimeRow(
        label="    usage/time [used]",
        value="63% / 40% = 1.6 [%]",
        suffix="Weekly",
        used_percent=63,
        elapsed_percent=40,
        ratio=1.575,
        variants=(
            MonitorColumnVariant(
                label="    usage/time [used]",
                value="63% / 40% = 1.6 [%]",
            ),
            MonitorColumnVariant(
                label="    time/usage [left]",
                value="20.2 / 2.4 = 8.6 [Burst]",
            ),
        ),
    )
    loop.visible_frame.add_block("limits-tracking", rows=[row])
    loop.clock.set_one_shot(MONITOR_USAGE_VARIANT_TOGGLE_ALARM, remaining_ticks=0)
    snapshot = loop.clock.step()

    loop._apply_display_alarms(snapshot)

    assert loop.state.data["monitor_display"] == {"usage_variant": "left"}
    assert "time/usage [left]" in format_monitor_frame(
        loop.visible_frame, loop.state
    )
    refreshed_frame = MonitorFrame()
    refreshed_frame.add_block("limits-tracking", rows=[row])
    assert "time/usage [left]" in format_monitor_frame(refreshed_frame, loop.state)
    assert MONITOR_USAGE_VARIANT_TOGGLE_ALARM not in _workflow_alarm_names(
        snapshot.fired_alarm_names
    )

    loop.clock.set_one_shot(MONITOR_USAGE_VARIANT_TOGGLE_ALARM, remaining_ticks=0)
    snapshot = loop.clock.step()

    loop._apply_display_alarms(snapshot)

    assert loop.state.data["monitor_display"] == {"usage_variant": "used"}
    assert "usage/time [used]" in format_monitor_frame(loop.visible_frame, loop.state)


def test_monitor_loop_usage_variant_toggle_alarm_does_not_hide_workflow_alarms() -> None:
    assert _workflow_alarm_names(
        (MONITOR_USAGE_VARIANT_TOGGLE_ALARM, LIMITS_TRACKING_PERIODIC_ALARM)
    ) == (LIMITS_TRACKING_PERIODIC_ALARM,)


def test_monitor_loop_titles_include_ticks_since_reset_for_periodic_workflows() -> None:
    loop = MonitorLoop(workflows=(), interval_sec=0, max_ticks=1)
    loop.visible_frame.add_block(
        "limits-tracking",
        data={
            "workflow": "limits-tracking",
            "periodic_alarm_name": "limits-tracking.periodic",
        },
    )
    loop.visible_frame.add_block(
        "auto-prime-zero-limits",
        data={
            "workflow": "auto-prime-zero-limits",
            "periodic_alarm_name": "auto-prime-zero-limits.periodic",
        },
    )
    loop.clock.set_periodic(
        "limits-tracking.periodic",
        period_ticks=170,
        remaining_ticks=168,
    )
    loop.clock.set_periodic(
        "auto-prime-zero-limits.periodic",
        period_ticks=8,
        remaining_ticks=8,
    )
    loop._clock_snapshot = loop.clock.snapshot()

    loop._apply_clock_feedback_to_visible_frame()

    assert loop.visible_frame.blocks[0]["title"] == (
        "limits-tracking | next in 168 ticks | reset 2 ticks ago"
    )
    assert loop.visible_frame.blocks[1]["title"] == (
        "auto-prime-zero-limits | next in 8 ticks | reset 0 ticks ago"
    )


class _FakeClaudePrimeAgent:
    provider = "claude-code"
    profile_id = "claude-br"
    default_model = None
    account = AgentAccountContext(provider="claude-code", account="browser-br")
    ping = AgentPingConfig(expected_number=745)

    def __init__(self, *, home: Path) -> None:
        self.home = home

    def run(self, command_config, run_config) -> AgentRunResult:
        return AgentRunResult(exit_code=0, stdout="745")

    def run_dry(self, command_config):
        raise NotImplementedError


class _FakeCodexPrimeAgent:
    provider = "codex"
    profile_id = "codex-br"
    default_model = None
    account = AgentAccountContext(provider="codex", account="br")
    ping = AgentPingConfig(expected_number=745)

    def __init__(self, *, home: Path) -> None:
        self.home = home

    def run(self, command_config, run_config) -> AgentRunResult:
        return AgentRunResult(exit_code=0, stdout="745")

    def run_dry(self, command_config):
        raise NotImplementedError
