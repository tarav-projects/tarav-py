from __future__ import annotations

import argparse

import pytest

from agentos._core.errors import CliError
from agentos.agent.commands import run as commands
from agentos.agent.profile_check import CheckpointResult, ProfileCheck
from agentos.agent.run_runtime import AgentRunResult


class _FakeAgent:
    def __init__(self, check: ProfileCheck, exit_code: int = 0) -> None:
        self._check = check
        self._run_result = AgentRunResult(exit_code=exit_code)
        self.run_called = False

    def profile_check(self) -> ProfileCheck:
        return self._check

    def run(self, command_config, run_config) -> AgentRunResult:
        self.run_called = True
        return self._run_result


def _args(*, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        argv=[], prompt="hi", non_interactive=False, dry_run=False, force=force
    )


def _fit() -> ProfileCheck:
    return ProfileCheck(
        checkpoints=(CheckpointResult("home_exists", True, None),), ok=True
    )


def _unfit() -> ProfileCheck:
    return ProfileCheck(
        checkpoints=(
            CheckpointResult("account_registered", True, None),
            CheckpointResult("home_aligned", False, "drift:home-older: active is newer"),
        ),
        ok=False,
    )


def _patch(monkeypatch, agent: _FakeAgent) -> None:
    monkeypatch.setattr(
        commands, "_resolve_agent_run", lambda args, **kw: (agent, None, None)
    )


def test_run_blocked_when_unfit(monkeypatch, capsys) -> None:
    agent = _FakeAgent(_unfit())
    _patch(monkeypatch, agent)
    with pytest.raises(CliError):
        commands._cmd_agent_run(_args())
    assert agent.run_called is False
    assert "home_aligned" in capsys.readouterr().out


def test_run_proceeds_when_fit(monkeypatch) -> None:
    agent = _FakeAgent(_fit(), exit_code=7)
    _patch(monkeypatch, agent)
    rc = commands._cmd_agent_run(_args())
    assert agent.run_called is True
    assert rc == 7


def test_force_bypasses_gate(monkeypatch) -> None:
    agent = _FakeAgent(_unfit(), exit_code=3)
    _patch(monkeypatch, agent)
    rc = commands._cmd_agent_run(_args(force=True))
    assert agent.run_called is True
    assert rc == 3
