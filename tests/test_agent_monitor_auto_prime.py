from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from tarav.agent.monitor.auto_prime_registry import (
    AUTO_PRIME_EVENT_ATTEMPT_STARTED,
    AUTO_PRIME_EVENT_ATTEMPT_SUCCEEDED,
    AUTO_PRIME_EVENT_ELIGIBLE,
    AUTO_PRIME_EVENT_SKIPPED_ALREADY_PRIMED,
    AUTO_PRIME_EVENT_VERIFICATION_EFFECTIVE,
    AUTO_PRIME_EVENT_VERIFICATION_INEFFECTIVE,
    auto_prime_event_registry_path,
)
from tarav.agent.monitor.models import (
    AUTO_PRIME_PING_SUCCEEDED_STATUS,
    AUTO_PRIME_VERIFICATION_EFFECTIVE,
    AUTO_PRIME_VERIFICATION_INEFFECTIVE,
    AUTO_PRIME_VERIFICATION_PENDING,
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorState,
    MonitorTarget,
    MonitorWorkflowConfig,
)
import tarav.agent.monitor.workflows.auto_prime as auto_prime
from tarav.agent.monitor.workflows import (
    AutoPrimeZeroLimitsWorkflow,
)
from tarav.agent.account_status import AgentAccountContext
from tarav.agent.ping import AgentPingResult
from tarav.agent.primitives import AgentPingConfig, RunnableMixin
from tarav.agent.run_runtime import AgentRunResult
import tarav.agent.providers.claude_code.keychain as claude_keychain
from tarav.testing import TaravTestEnvironment

from tarav.testing import codex_auth_json, seed_claude_account, seed_codex_account, write_claude_home
from _helpers import write_text_file
from tarav.agent.monitor.workflows.state import (
    AutoPrimeTargetState,
    LimitsTargetState,
    LimitsWorkflowState,
)
from _monitor_helpers import _limit, _target_state


def _set_fake_agentos_home(monkeypatch, root: Path) -> Path:
    environment = TaravTestEnvironment.create(root)
    environment.apply_environment(monkeypatch.setenv)
    return environment.tarav_home

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

def _source_state(
    *,
    limit: dict[str, object],
    recorded_at: datetime.datetime | None = None,
    account: str = "jp",
    home: str = "/tmp/codex-jp",
) -> LimitsTargetState:
    account_status: dict[str, object] = {"limits": [limit]}
    if recorded_at is not None:
        account_status["raw"] = {
            "usage_record": {
                "recorded_at": recorded_at.isoformat(),
            }
        }
    return LimitsTargetState(
        provider="codex",
        account=account,
        home=home,
        status="ok",
        account_status=account_status,
    )

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

def test_auto_prime_status_part_uses_priority_order(monkeypatch) -> None:
    monkeypatch.setattr(auto_prime.time, "monotonic", lambda: 100.0)

    assert (
        auto_prime._auto_prime_status_part(
            AutoPrimeTargetState(**{
                "last_decision": {
                    "limit_id": "burst",
                    "classification": "non-primed",
                    "action": "pinged",
                },
                "last_error": {"message": "failed"},
            })
        )
        == "burst non-primed/pinged"
    )
    assert (
        auto_prime._auto_prime_status_part(AutoPrimeTargetState(last_error={"message": "failed"}))
        == "prime failed"
    )
    assert (
        auto_prime._auto_prime_status_part(
            AutoPrimeTargetState(**{
                "primed_periods": {
                    "burst": {
                        "verification_status": AUTO_PRIME_VERIFICATION_INEFFECTIVE,
                        "next_retry_after_monotonic": 580.0,
                    }
                }
            })
        )
        == "prime ineffective"
    )
    assert (
        auto_prime._auto_prime_status_part(
            AutoPrimeTargetState(**{
                "primed_periods": {
                    "burst": {
                        "verification_status": AUTO_PRIME_VERIFICATION_PENDING,
                        "next_retry_after_monotonic": 580.0,
                    }
                }
            })
        )
        == "prime retry in 8m"
    )
    assert (
        auto_prime._auto_prime_status_part(
            AutoPrimeTargetState(**{
                "retry_after_monotonic": 580.0,
            })
        )
        == "prime retry in 8m"
    )
    assert (
        auto_prime._auto_prime_status_part(
            AutoPrimeTargetState(**{
                "primed_periods": {
                    "burst": {
                        "verification_status": AUTO_PRIME_VERIFICATION_PENDING,
                    }
                }
            })
        )
        == "prime pending"
    )
    assert (
        auto_prime._auto_prime_status_part(
            AutoPrimeTargetState(**{
                "primed_periods": {
                    "burst": {
                        "verification_status": AUTO_PRIME_VERIFICATION_EFFECTIVE,
                    }
                }
            })
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
    primed_periods = target_state.primed_periods
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
    primed_periods = target_state.primed_periods
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
    target_state.primed_periods = {
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

    assert period_key not in target_state.primed_periods
    assert _events()[-1]["event_type"] == AUTO_PRIME_EVENT_VERIFICATION_EFFECTIVE

def test_auto_prime_verification_marks_persistent_uninitialized_ineffective(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    target_state = _target_state()
    period_key = "codex|jp|/tmp/codex-jp|burst|uninitialized"
    target_state.primed_periods = {
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

    primed_period = target_state.primed_periods[period_key]  # type: ignore[index]
    assert primed_period["verification_status"] == AUTO_PRIME_VERIFICATION_INEFFECTIVE  # type: ignore[index]
    assert _events()[-1]["event_type"] == AUTO_PRIME_EVENT_VERIFICATION_INEFFECTIVE

def test_auto_prime_attempts_write_durable_events_and_do_not_run_live_provider(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []

    def fake_ping(source_target_state: dict[str, object]) -> AgentPingResult:
        calls.append(source_target_state)
        return AgentPingResult(
            ok=True, model="codex-x", elapsed_ms=5, exit_code=0, output="745", failure=None
        )

    monkeypatch.setattr(auto_prime, "_run_account_prime_ping", fake_ping)
    now = datetime.datetime.now(tz=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    state = MonitorState(
        data={
            LIMITS_TRACKING_WORKFLOW: LimitsWorkflowState(
                targets={
                    "codex/jp@/tmp/codex-jp": _source_state(
                        limit=_limit(used_percent=1, now=now)
                    ),
                    "codex/mm@/tmp/codex-mm": _source_state(
                        limit=_limit(used_percent=1, now=now), account="mm",
                        home="/tmp/codex-mm",
                    ),
                }
            )
        }
    )
    workflow_state = workflow._workflow_state(state)

    workflow._scan_and_prime(state, workflow_state=workflow_state, tick=3)

    assert len(calls) == 1
    assert workflow_state.last_scan["pinged"] == 1  # type: ignore[index]
    target_state = workflow_state.targets["codex/jp@/tmp/codex-jp"]  # type: ignore[index]
    assert target_state.last_decision["limit_id"] == "burst"  # type: ignore[index]
    assert target_state.last_decision["classification"] == "non-primed"  # type: ignore[index]
    assert target_state.last_decision["action"] == "pinged"  # type: ignore[index]
    event_types = [event["event_type"] for event in _events()]
    assert event_types == [
        AUTO_PRIME_EVENT_ELIGIBLE,
        AUTO_PRIME_EVENT_ATTEMPT_STARTED,
        AUTO_PRIME_EVENT_ATTEMPT_SUCCEEDED,
    ]

def _single_target_state(now: datetime.datetime) -> MonitorState:
    return MonitorState(
        data={
            LIMITS_TRACKING_WORKFLOW: LimitsWorkflowState(
                targets={
                    "codex/jp@/tmp/codex-jp": _source_state(
                        limit=_limit(used_percent=1, now=now)
                    )
                }
            )
        }
    )

def test_auto_prime_success_records_ping_telemetry(monkeypatch, tmp_path: Path) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)

    def fake_ping(source_target_state: dict[str, object]) -> AgentPingResult:
        return AgentPingResult(
            ok=True, model="codex-x", elapsed_ms=42, exit_code=0, output="745", failure=None
        )

    monkeypatch.setattr(auto_prime, "_run_account_prime_ping", fake_ping)
    now = datetime.datetime.now(tz=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    state = _single_target_state(now)
    workflow_state = workflow._workflow_state(state)

    workflow._scan_and_prime(state, workflow_state=workflow_state, tick=3)

    assert workflow_state.last_scan["pinged"] == 1  # type: ignore[index]
    target_state = workflow_state.targets["codex/jp@/tmp/codex-jp"]  # type: ignore[index]
    primed = next(iter(target_state.primed_periods.values()))  # type: ignore[index]
    assert primed["ping_model"] == "codex-x"
    assert primed["ping_elapsed_ms"] == 42

def test_auto_prime_ping_failure_records_last_error_from_result(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)

    def fake_ping(source_target_state: dict[str, object]) -> AgentPingResult:
        return AgentPingResult(
            ok=False,
            model="codex-x",
            elapsed_ms=1,
            exit_code=2,
            output="",
            failure="provider command exited with 2",
        )

    monkeypatch.setattr(auto_prime, "_run_account_prime_ping", fake_ping)
    now = datetime.datetime.now(tz=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    state = _single_target_state(now)
    workflow_state = workflow._workflow_state(state)

    workflow._scan_and_prime(state, workflow_state=workflow_state, tick=3)

    assert workflow_state.last_scan["pinged"] == 0  # type: ignore[index]
    assert workflow_state.last_scan["failed"] == 1  # type: ignore[index]
    target_state = workflow_state.targets["codex/jp@/tmp/codex-jp"]  # type: ignore[index]
    assert target_state.last_error["message"] == "provider command exited with 2"

def test_auto_prime_ping_records_claude_verified_auth_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_keychain.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    seed_claude_account("browser-br", account_uuid="acc_browser-br")
    monkeypatch.setattr(
        auto_prime,
        "resolve_account_runtime_agent",
        lambda **kwargs: _FakeClaudePrimeAgent(home=Path(kwargs["home"])),
    )

    auto_prime._run_account_prime_ping(
        LimitsTargetState(
            provider="claude-code",
            account="browser-br",
            home=str(home),
        )
    )

    # Auto-prime no longer auto-promotes credentials into the old registry
    # (disconnected in 658; new-model capture workflow is a deferred re-integration).
    assert not (
        environment.tarav_home / "accounts" / "claude-code" / "verifications.jsonl"
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
        auto_prime,
        "resolve_account_runtime_agent",
        fake_resolve_account_runtime_agent,
    )

    auto_prime._run_account_prime_ping(
        LimitsTargetState(
            provider="codex",
            account="br",
            home=str(home),
            profile="codex-br",
            start_path=str(tmp_path),
        )
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
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-br"
    write_text_file(home / "auth.json", codex_auth_json(account_id="acc_br", email="br@example.com"))
    seed_codex_account("br")
    monkeypatch.setattr(
        auto_prime,
        "resolve_account_runtime_agent",
        lambda **kwargs: _FakeCodexPrimeAgent(home=Path(kwargs["home"])),
    )

    auto_prime._run_account_prime_ping(
        LimitsTargetState(
            provider="codex",
            account="br",
            home=str(home),
        )
    )

    # Auto-prime no longer auto-promotes credentials into the old registry (658).
    assert not (
        environment.tarav_home / "accounts" / "codex" / "verifications.jsonl"
    ).exists()

def test_auto_prime_decisions_only_include_configured_limits() -> None:
    now = datetime.datetime(2026, 5, 19, 18, 0, tzinfo=datetime.UTC)
    workflow = _workflow(triggers=("near_zero_full_window",))
    target_state = _target_state()
    source_state = _source_state(
        limit=_limit(used_percent=40, now=now),
    )
    account_status = source_state.account_status
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
    assert target_state.last_decision["limit_id"] == "burst"  # type: ignore[index]
    assert target_state.last_decision["classification"] == "primed"  # type: ignore[index]
    assert target_state.last_decision["action"] == "skipped"  # type: ignore[index]
    assert [decision["limit_id"] for decision in target_state.last_decisions] == [  # type: ignore[index]
        "burst"
    ]

class _FakeClaudePrimeAgent(RunnableMixin):
    provider = "claude-code"
    profile_id = "claude-br"
    default_model = None
    account = AgentAccountContext(provider="claude-code", account="browser-br")
    ping_config = AgentPingConfig(expected_number=745)

    def __init__(self, *, home: Path) -> None:
        self.home = home

    def run(self, command_config, run_config) -> AgentRunResult:
        return AgentRunResult(exit_code=0, stdout="745")

    def run_dry(self, command_config):
        raise NotImplementedError

class _FakeCodexPrimeAgent(RunnableMixin):
    provider = "codex"
    profile_id = "codex-br"
    default_model = None
    account = AgentAccountContext(provider="codex", account="br")
    ping_config = AgentPingConfig(expected_number=745)

    def __init__(self, *, home: Path) -> None:
        self.home = home

    def run(self, command_config, run_config) -> AgentRunResult:
        return AgentRunResult(exit_code=0, stdout="745")

    def run_dry(self, command_config):
        raise NotImplementedError
