from __future__ import annotations

from pathlib import Path

import pytest

from tarav.l1.agent.ping import AgentPingError, AgentPingResult
from tarav.l1.agent.primitives import AgentPingConfig, RunnableMixin
from tarav.l1.agent.run_runtime import AgentRunResult


class _PingStub(RunnableMixin):
    """A RunnableMixin agent whose run() returns a canned result — exercises the
    `ping()` capability method without spawning a process."""

    provider = "stub"
    profile_id = "p1"
    default_model = "default-x"

    def __init__(self, *, ping_config: AgentPingConfig, run_result: AgentRunResult) -> None:
        self.ping_config = ping_config
        self._run_result = run_result
        self.calls: list[tuple[object, object]] = []

    def run(self, command_config, run_config):
        self.calls.append((command_config, run_config))
        return self._run_result

    def run_dry(self, command_config):  # present so isinstance(RunCapable) holds
        raise NotImplementedError


def _cfg(expected_number: int | None = 745, model: str | None = None) -> AgentPingConfig:
    return AgentPingConfig(
        enabled=True, prompt="What is X?", expected_number=expected_number, model=model
    )


def test_ping_ok_when_expected_number_present(tmp_path: Path) -> None:
    agent = _PingStub(
        ping_config=_cfg(),
        run_result=AgentRunResult(exit_code=0, stdout="The answer is 745"),
    )
    result = agent.ping(cwd=tmp_path)
    assert isinstance(result, AgentPingResult)
    assert result.ok is True
    assert result.failure is None
    assert "745" in result.output
    assert result.elapsed_ms >= 0
    command_config, run_config = agent.calls[0]
    assert command_config.interaction_mode == "non_interactive"
    assert run_config.process_mode == "capture"
    assert run_config.cwd == tmp_path


def test_ping_failure_when_expected_number_missing(tmp_path: Path) -> None:
    agent = _PingStub(
        ping_config=_cfg(expected_number=745),
        run_result=AgentRunResult(exit_code=0, stdout="The answer is 12"),
    )
    result = agent.ping(cwd=tmp_path)
    assert result.ok is False
    assert result.failure is not None
    assert "745" in result.failure


def test_ping_failure_on_nonzero_exit(tmp_path: Path) -> None:
    agent = _PingStub(
        ping_config=_cfg(),
        run_result=AgentRunResult(exit_code=2, stderr="boom"),
    )
    result = agent.ping(cwd=tmp_path)
    assert result.ok is False
    assert "2" in result.failure
    assert "boom" in result.failure


def test_ping_ok_when_expected_number_is_none(tmp_path: Path) -> None:
    agent = _PingStub(
        ping_config=_cfg(expected_number=None),
        run_result=AgentRunResult(exit_code=0, stdout="anything"),
    )
    assert agent.ping(cwd=tmp_path).ok is True


def test_ping_model_resolution_and_overrides(tmp_path: Path) -> None:
    agent = _PingStub(
        ping_config=_cfg(model="ping-model"),
        run_result=AgentRunResult(exit_code=0, stdout="745"),
    )
    result = agent.ping(cwd=tmp_path)
    assert result.model == "ping-model"
    assert agent.calls[0][0].model == "ping-model"

    agent2 = _PingStub(
        ping_config=_cfg(model="ping-model"),
        run_result=AgentRunResult(exit_code=0, stdout="745"),
    )
    result2 = agent2.ping(cwd=tmp_path, model="override", account="acct")
    assert result2.model == "override"
    command_config2 = agent2.calls[0][0]
    assert command_config2.model == "override"
    assert command_config2.account == "acct"


def test_ping_display_model_falls_back_to_default(tmp_path: Path) -> None:
    agent = _PingStub(
        ping_config=_cfg(model=None),
        run_result=AgentRunResult(exit_code=0, stdout="745"),
    )
    assert agent.ping(cwd=tmp_path).model == "default-x"


def test_ping_raises_when_disabled(tmp_path: Path) -> None:
    agent = _PingStub(
        ping_config=AgentPingConfig(enabled=False, prompt=None, expected_number=None),
        run_result=AgentRunResult(exit_code=0, stdout="745"),
    )
    with pytest.raises(AgentPingError):
        agent.ping(cwd=tmp_path)


def test_ping_defaults_cwd_when_omitted() -> None:
    agent = _PingStub(
        ping_config=_cfg(),
        run_result=AgentRunResult(exit_code=0, stdout="745"),
    )
    result = agent.ping()
    assert result.ok is True
    assert agent.calls[0][1].cwd is not None
