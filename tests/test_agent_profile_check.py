from __future__ import annotations

import argparse
from pathlib import Path

from agentos.agent import auth_registry
from agentos.agent import commands
from agentos.agent import profile_check as pc
from agentos.agent.account_status import AgentAccountContext
from agentos.agent.primitives import ProfileCheckCapable, RunnableMixin
from agentos.agent.profile_check import CheckpointResult, ProfileCheck, _profile_check


class _Agent:
    def __init__(self, provider: str, account: str | None, home: Path | None) -> None:
        self.provider = provider
        self.account = (
            AgentAccountContext(provider=provider, account=account) if account else None
        )
        self.home = home


def _patch(monkeypatch, *, registered: bool, status: dict) -> None:
    monkeypatch.setattr(auth_registry, "account_exists", lambda p, a: registered)
    monkeypatch.setattr(pc, "status_for_home", lambda target: status)


def _by_id(result: ProfileCheck) -> dict[str, object]:
    return {c.id: c for c in result.checkpoints}


def test_profile_check_all_pass(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "h"
    home.mkdir()
    _patch(monkeypatch, registered=True, status={"status": "aligned"})
    result = _profile_check(_Agent("codex", "br", home))
    assert result.ok is True
    assert all(c.passed for c in result.checkpoints)
    assert set(_by_id(result)) == {"account_registered", "home_exists", "home_aligned"}


def test_profile_check_unregistered_account_fails(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "h"
    home.mkdir()
    _patch(monkeypatch, registered=False, status={"status": "aligned"})
    result = _profile_check(_Agent("codex", "br", home))
    assert result.ok is False
    checks = _by_id(result)
    assert checks["account_registered"].passed is False
    assert checks["account_registered"].reason is not None
    # collect-all: the other checkpoints still ran
    assert checks["home_exists"].passed is True


def test_profile_check_missing_home_fails(tmp_path: Path, monkeypatch) -> None:
    _patch(monkeypatch, registered=True, status={"status": "aligned"})
    result = _profile_check(_Agent("codex", "br", tmp_path / "nope"))
    checks = _by_id(result)
    assert checks["home_exists"].passed is False
    assert result.ok is False


def test_profile_check_drift_fails_with_reason(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "h"
    home.mkdir()
    _patch(
        monkeypatch,
        registered=True,
        status={"status": "drift:home-newer", "reason": "home credential is newer than active — rotate"},
    )
    result = _profile_check(_Agent("codex", "br", home))
    checks = _by_id(result)
    assert checks["home_aligned"].passed is False
    assert "drift:home-newer" in checks["home_aligned"].reason
    assert result.ok is False


def test_profile_check_no_account_bound(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "h"
    home.mkdir()
    _patch(monkeypatch, registered=True, status={"status": "aligned"})
    result = _profile_check(_Agent("codex", None, home))
    checks = _by_id(result)
    assert checks["account_registered"].passed is False
    assert result.ok is False


class _MethodAgent(RunnableMixin):
    def __init__(self, provider: str, account: str | None, home: Path) -> None:
        self.provider = provider
        self.account = (
            AgentAccountContext(provider=provider, account=account) if account else None
        )
        self.home = home


def test_profile_check_method_delegates(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "h"
    home.mkdir()
    _patch(monkeypatch, registered=True, status={"status": "aligned"})
    agent = _MethodAgent("codex", "br", home)
    assert isinstance(agent, ProfileCheckCapable)
    result = agent.profile_check()
    assert isinstance(result, ProfileCheck)
    assert result.ok is True


class _CliAgent:
    def __init__(self, result: ProfileCheck) -> None:
        self._result = result

    def profile_check(self) -> ProfileCheck:
        return self._result


def test_cmd_profile_check_pass(monkeypatch, capsys) -> None:
    result = ProfileCheck(
        checkpoints=(
            CheckpointResult("account_registered", True, None),
            CheckpointResult("home_exists", True, None),
            CheckpointResult("home_aligned", True, None),
        ),
        ok=True,
    )
    monkeypatch.setattr(
        commands, "_resolve_agent_run_target", lambda args: (_CliAgent(result), None)
    )
    rc = commands._cmd_agent_profile_check(argparse.Namespace())
    assert rc == 0
    out = capsys.readouterr().out
    assert "home_aligned" in out


def test_cmd_profile_check_fail_exits_nonzero(monkeypatch, capsys) -> None:
    result = ProfileCheck(
        checkpoints=(
            CheckpointResult("account_registered", True, None),
            CheckpointResult("home_aligned", False, "drift:home-newer: home is newer"),
        ),
        ok=False,
    )
    monkeypatch.setattr(
        commands, "_resolve_agent_run_target", lambda args: (_CliAgent(result), None)
    )
    rc = commands._cmd_agent_profile_check(argparse.Namespace())
    assert rc != 0
    out = capsys.readouterr().out
    assert "drift:home-newer" in out
