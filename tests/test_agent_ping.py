from __future__ import annotations

from pathlib import Path

import pytest

from agentos.agent.ping import AgentPingError, ping_agent
from agentos.agent.primitives import AgentPingConfig
from agentos.agent.run_runtime import AgentRunResult


class _StubRunnableAgent:
    """Minimal RunCapable stand-in: records the run call, returns a canned result."""

    provider = "stub"
    profile_id = "p1"
    default_model = "default-x"

    def __init__(self, *, ping: AgentPingConfig, run_result: AgentRunResult) -> None:
        self.ping = ping
        self._run_result = run_result
        self.calls: list[tuple[object, object]] = []

    def run(self, command_config, run_config):
        self.calls.append((command_config, run_config))
        return self._run_result

    def run_dry(self, command_config):  # present so isinstance(RunCapable) holds
        raise NotImplementedError


class _StubNonRunnableAgent:
    provider = "stub"
    profile_id = "p1"
    default_model = None
    ping = AgentPingConfig(enabled=True, prompt="ping", expected_number=745)


def _ping(expected_number: int | None = 745, model: str | None = None) -> AgentPingConfig:
    return AgentPingConfig(
        enabled=True, prompt="What is X?", expected_number=expected_number, model=model
    )


def test_ping_agent_ok_when_expected_number_present(tmp_path: Path) -> None:
    agent = _StubRunnableAgent(
        ping=_ping(),
        run_result=AgentRunResult(exit_code=0, stdout="The answer is 745"),
    )
    result = ping_agent(agent, cwd=tmp_path)
    assert result.ok is True
    assert result.failure is None
    assert result.exit_code == 0
    assert "745" in result.output
    assert result.elapsed_ms >= 0
    # run was issued non-interactive, capture-mode
    command_config, run_config = agent.calls[0]
    assert command_config.interaction_mode == "non_interactive"
    assert run_config.process_mode == "capture"
    assert run_config.cwd == tmp_path


def test_ping_agent_failure_when_expected_number_missing(tmp_path: Path) -> None:
    agent = _StubRunnableAgent(
        ping=_ping(expected_number=745),
        run_result=AgentRunResult(exit_code=0, stdout="The answer is 12."),
    )
    result = ping_agent(agent, cwd=tmp_path)
    assert result.ok is False
    assert result.failure is not None
    assert "745" in result.failure


def test_ping_agent_failure_on_nonzero_exit(tmp_path: Path) -> None:
    agent = _StubRunnableAgent(
        ping=_ping(),
        run_result=AgentRunResult(exit_code=2, stderr="boom"),
    )
    result = ping_agent(agent, cwd=tmp_path)
    assert result.ok is False
    assert result.failure is not None
    assert "2" in result.failure
    assert "boom" in result.failure


def test_ping_agent_ok_when_expected_number_is_none(tmp_path: Path) -> None:
    agent = _StubRunnableAgent(
        ping=_ping(expected_number=None),
        run_result=AgentRunResult(exit_code=0, stdout="anything"),
    )
    result = ping_agent(agent, cwd=tmp_path)
    assert result.ok is True


def test_ping_agent_model_resolution_and_overrides(tmp_path: Path) -> None:
    # no override -> falls back to ping.model, then default_model for display
    agent = _StubRunnableAgent(
        ping=_ping(model="ping-model"),
        run_result=AgentRunResult(exit_code=0, stdout="745"),
    )
    result = ping_agent(agent, cwd=tmp_path)
    assert result.model == "ping-model"
    command_config, _ = agent.calls[0]
    assert command_config.model == "ping-model"

    # explicit override wins, account passes through
    agent2 = _StubRunnableAgent(
        ping=_ping(model="ping-model"),
        run_result=AgentRunResult(exit_code=0, stdout="745"),
    )
    result2 = ping_agent(agent2, cwd=tmp_path, model="override", account="acct")
    assert result2.model == "override"
    command_config2, _ = agent2.calls[0]
    assert command_config2.model == "override"
    assert command_config2.account == "acct"


def test_ping_agent_display_model_falls_back_to_default(tmp_path: Path) -> None:
    agent = _StubRunnableAgent(
        ping=_ping(model=None),
        run_result=AgentRunResult(exit_code=0, stdout="745"),
    )
    result = ping_agent(agent, cwd=tmp_path)
    assert result.model == "default-x"


def test_ping_agent_raises_when_disabled(tmp_path: Path) -> None:
    agent = _StubRunnableAgent(
        ping=AgentPingConfig(enabled=False, prompt=None, expected_number=None),
        run_result=AgentRunResult(exit_code=0, stdout="745"),
    )
    with pytest.raises(AgentPingError):
        ping_agent(agent, cwd=tmp_path)


def test_ping_agent_raises_when_agent_not_runnable(tmp_path: Path) -> None:
    with pytest.raises(AgentPingError):
        ping_agent(_StubNonRunnableAgent(), cwd=tmp_path)
