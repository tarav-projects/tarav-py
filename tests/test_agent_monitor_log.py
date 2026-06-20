from __future__ import annotations

import datetime
from pathlib import Path

from agentos.agent.account_status import AccountStatusError
from agentos.agent.account_usage_fallback import account_usage_registry_fallback
from agentos.agent.monitor.workflows import AutoPrimeZeroLimitsWorkflow
from agentos.agent.monitor_log import (
    MONITOR_LOG_CLASS,
    MONITOR_LOG_SCHEMA_VERSION,
    append_monitor_log_event,
    monitor_log_dir,
)
from agentos.agent.usage_registry import append_usage_record
from agentos.testing import AgentosTestEnvironment

from _helpers import read_jsonl_file


def _set_fake_agentos_home(monkeypatch, root: Path) -> Path:
    environment = AgentosTestEnvironment.create(root)
    environment.apply_environment(monkeypatch.setenv)
    return environment.agentos_home


def _events(path: Path, event: str) -> list[dict]:
    if not path.exists():
        return []
    return [r for r in read_jsonl_file(path) if r.get("event") == event]


def _log_file() -> Path:
    today = datetime.datetime.now(tz=datetime.UTC)
    return monitor_log_dir() / f"{today:%Y%m%d}.jsonl"


def test_append_writes_dated_file_and_roundtrips(monkeypatch, tmp_path):
    home = _set_fake_agentos_home(monkeypatch, tmp_path)

    path = append_monitor_log_event(
        event="stale_fallback_served",
        provider="claude-code",
        account="browser-br",
        home="/some/home",
        tick=7,
        payload={"source": "claude-statusline", "age_sec": 82220},
    )

    today = datetime.datetime.now(tz=datetime.UTC)
    expected_dir = home / "agent" / "monitor-log"
    assert path == expected_dir / f"{today:%Y%m%d}.jsonl"
    assert expected_dir.is_dir()

    records = read_jsonl_file(path)
    assert len(records) == 1
    record = records[0]
    assert record["schema_version"] == MONITOR_LOG_SCHEMA_VERSION
    assert record["class"] == MONITOR_LOG_CLASS
    assert record["event"] == "stale_fallback_served"
    assert record["provider"] == "claude-code"
    assert record["account"] == "browser-br"
    assert record["tick"] == 7
    assert record["payload"]["age_sec"] == 82220
    assert isinstance(record["recorded_at"], str) and record["recorded_at"].endswith("Z")


def test_append_uses_compact_serialization(monkeypatch, tmp_path):
    _set_fake_agentos_home(monkeypatch, tmp_path)

    path = append_monitor_log_event(event="monitor_start", payload={"a": 1, "b": 2})

    line = path.read_text(encoding="utf-8").strip()
    assert ", " not in line  # compact separators
    assert ": " not in line


def test_append_appends_without_truncating(monkeypatch, tmp_path):
    _set_fake_agentos_home(monkeypatch, tmp_path)

    append_monitor_log_event(event="workflow_error", payload={"n": 1})
    path = append_monitor_log_event(event="workflow_error", payload={"n": 2})

    records = read_jsonl_file(path)
    assert [r["payload"]["n"] for r in records] == [1, 2]


def test_append_is_best_effort_on_unserializable_payload(monkeypatch, tmp_path):
    _set_fake_agentos_home(monkeypatch, tmp_path)

    # A non-JSON-serializable payload must not raise into the caller.
    result = append_monitor_log_event(event="boom", payload={"bad": object()})

    assert result is None
    log_dir = monitor_log_dir()
    today = datetime.datetime.now(tz=datetime.UTC)
    target = log_dir / f"{today:%Y%m%d}.jsonl"
    # No partial/garbage line was written.
    assert not target.exists() or target.read_text(encoding="utf-8") == ""


# --- Slice 2: error events --------------------------------------------------


def test_stale_fallback_served_is_logged(monkeypatch, tmp_path):
    home = _set_fake_agentos_home(monkeypatch, tmp_path) / "browser-br"
    home.mkdir(parents=True, exist_ok=True)
    append_usage_record(
        provider="claude-code",
        account="browser-br",
        home=home,
        source="claude-statusline",
        payload={"rate_limits": {"five_hour": {"used_percentage": 1}}},
    )

    result = account_usage_registry_fallback(
        provider="claude-code",
        account="browser-br",
        home=home,
        source="claude-statusline",
        parser=lambda payload: (),
        live_error=AccountStatusError(error_type="timeout", message="live timed out"),
        fallback_to_usage_registry=True,
    )

    # The fallback still serves the cached payload.
    assert result[2] == {"rate_limits": {"five_hour": {"used_percentage": 1}}}
    served = _events(_log_file(), "stale_fallback_served")
    assert len(served) == 1
    payload = served[0]["payload"]
    assert served[0]["provider"] == "claude-code"
    assert served[0]["account"] == "browser-br"
    assert payload["live_error_type"] == "timeout"
    assert payload["age_sec"] is not None


def test_refresh_error_logged_when_no_fallback_record(monkeypatch, tmp_path):
    home = _set_fake_agentos_home(monkeypatch, tmp_path) / "browser-br"
    home.mkdir(parents=True, exist_ok=True)

    account_usage_registry_fallback(
        provider="claude-code",
        account="browser-br",
        home=home,
        source="claude-statusline",
        parser=lambda payload: (),
        live_error=AccountStatusError(error_type="http_error", message="500"),
        fallback_to_usage_registry=True,
    )

    errors = _events(_log_file(), "target_refresh_error")
    assert len(errors) == 1
    assert errors[0]["payload"]["reason"] == "no_registry_record"
    assert errors[0]["payload"]["error_type"] == "http_error"


def test_auto_prime_failed_and_retry_blocked_are_logged(monkeypatch, tmp_path):
    _set_fake_agentos_home(monkeypatch, tmp_path)
    target_state = {"provider": "codex", "account": "jp", "home": "/h"}
    decision_failed = {"tick": 3, "limit_id": "burst", "classification": "non-primed"}
    decision_retry = {"tick": 4, "limit_id": "burst", "classification": "non-primed"}
    decision_ok = {"tick": 5, "limit_id": "burst", "classification": "non-primed"}

    AutoPrimeZeroLimitsWorkflow._log_decision_error(
        target_state, decision=decision_failed, action="ping failed"
    )
    AutoPrimeZeroLimitsWorkflow._log_decision_error(
        target_state, decision=decision_retry, action="retry"
    )
    AutoPrimeZeroLimitsWorkflow._log_decision_error(
        target_state, decision=decision_ok, action="pinged"
    )

    path = _log_file()
    assert len(_events(path, "auto_prime_failed")) == 1
    assert len(_events(path, "auto_prime_retry_blocked")) == 1
    assert _events(path, "auto_prime_pinged") == []  # success not logged as error


def test_workflow_error_is_logged_through_monitor_loop(monkeypatch, tmp_path):
    from agentos.agent.monitor.loop import MonitorLoop
    from agentos.agent.monitor.models import MonitorFrame, MonitorState

    _set_fake_agentos_home(monkeypatch, tmp_path)

    class _RaisingWorkflow:
        name = "boom-workflow"

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            raise RuntimeError("setup exploded")

        def loop(self, state, frame, trigger) -> None:  # pragma: no cover - unused
            pass

    loop = MonitorLoop(
        workflows=(_RaisingWorkflow(),),
        interval_sec=0,
        max_ticks=1,
    )
    loop.run(wait_for_first_frame=True)

    errors = _events(_log_file(), "workflow_error")
    assert len(errors) == 1
    assert errors[0]["payload"]["workflow"] == "boom-workflow"
    assert errors[0]["payload"]["phase"] == "setup"
    assert errors[0]["payload"]["error_type"] == "RuntimeError"
    # monitor_start (Tier B lifecycle) is also emitted at construction.
    assert len(_events(_log_file(), "monitor_start")) == 1


# --- Slice 3: low-frequency target transitions ------------------------------


def _limits_workflow(refresh_interval_sec=60.0):
    from agentos.agent.monitor.models import (
        LIMITS_TRACKING_WORKFLOW,
        MonitorTarget,
        MonitorWorkflowConfig,
    )
    from agentos.agent.monitor.workflows import LimitsTrackingWorkflow

    config = MonitorWorkflowConfig(
        name=LIMITS_TRACKING_WORKFLOW,
        targets=(
            MonitorTarget(provider="claude-code", account="browser-br", home=Path("/h")),
        ),
        refresh_interval_sec=refresh_interval_sec,
        raw_config={},
    )
    return LimitsTrackingWorkflow(config)


def _state_with_age(age_sec):
    return {
        "status": "ok",
        "error": None,
        "account_status": {"raw": {"usage_record": {"age_sec": age_sec}}},
    }


def test_target_transition_logged_on_fresh_to_stale(monkeypatch, tmp_path):
    _set_fake_agentos_home(monkeypatch, tmp_path)
    workflow = _limits_workflow(refresh_interval_sec=60.0)  # stale threshold = 120s
    target = workflow.config.targets[0]

    prior = workflow._effective_target_state(_state_with_age(10))
    new = workflow._effective_target_state(_state_with_age(82220))
    assert prior["staleness"] == "fresh"
    assert new["staleness"] == "stale"

    workflow._maybe_log_transition(target, prior=prior, new=new, tick=5)

    transitions = _events(_log_file(), "target_transition")
    assert len(transitions) == 1
    assert transitions[0]["payload"]["from"]["staleness"] == "fresh"
    assert transitions[0]["payload"]["to"]["staleness"] == "stale"
    assert transitions[0]["account"] == "browser-br"


def test_no_transition_logged_when_unchanged(monkeypatch, tmp_path):
    _set_fake_agentos_home(monkeypatch, tmp_path)
    workflow = _limits_workflow()
    target = workflow.config.targets[0]

    same = workflow._effective_target_state(_state_with_age(10))
    workflow._maybe_log_transition(target, prior=same, new=dict(same), tick=5)

    assert _events(_log_file(), "target_transition") == []
