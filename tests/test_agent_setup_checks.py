"""Agent setup checks report broken configuration as POIs instead of raising."""

from __future__ import annotations

from pathlib import Path

import pytest

from tarav.l0.testing import TaravTestEnvironment
from tarav.l2.agent_setup import (
    AccountNotRegistered,
    AgentSetup,
    AgentSetupSuite,
    HomeMissing,
    MonitorConfigInvalid,
)
from tarav.l3.runtime import create_runtime


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaravTestEnvironment:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    create_runtime()
    return environment


def _findings(suite) -> list[tuple[str, str]]:
    return sorted((type(poi).__name__, poi.message) for poi in suite.pois())


def test_empty_setup_completes_without_findings(env: TaravTestEnvironment) -> None:
    env.write_global_config()

    suite = AgentSetup(env.root).checks.run()

    assert isinstance(suite, AgentSetupSuite)
    assert suite.complete
    assert suite.pois() == ()


def test_stale_monitor_target_is_a_finding_not_a_crash(
    env: TaravTestEnvironment,
) -> None:
    env.write_global_config(agent={"accounts": {"monitor": [{
        "workflow": "limits-tracking",
        "targets": [{"provider": "claude-code", "account": "om/browser",
                     "profile": "claude-om", "home": str(env.root / "browser-om")}],
    }]}})

    suite = AgentSetup(env.root).checks.run()

    assert suite.complete
    [poi] = suite.pois()
    assert isinstance(poi, MonitorConfigInvalid)
    assert poi.message == (
        "Account monitor config does not load: agent.accounts.monitor[0].targets[0].account "
        "references unknown account: claude-code/om"
    )


def test_agent_with_missing_home_and_unregistered_account(env: TaravTestEnvironment) -> None:
    env.write_global_config()
    missing_home = env.root / "gone-home"
    env.write_profile("codex-gone", provider="codex", accounts=["gone/file"],
                      homes=[str(missing_home)])

    suite = AgentSetup(env.root).checks.run()

    assert suite.complete
    assert _findings(suite) == [
        ("AccountNotRegistered", "codex/codex-gone: account not registered: codex.gone"),
        ("HomeMissing", f"codex/codex-gone: home does not exist: {missing_home}"),
    ]
    assert {type(poi) for poi in suite.pois()} == {AccountNotRegistered, HomeMissing}
