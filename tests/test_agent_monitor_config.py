from __future__ import annotations

from pathlib import Path

import pytest

from tarav.l0._core.errors import CliError
from tarav.agent.monitor.config import (
    _auto_prime_triggers,
    _target_limit_ids,
    load_monitor_workflow_configs,
)
from tarav.agent.monitor.models import (
    ACCOUNT_ROTATION_WORKFLOW,
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    MonitorTarget,
    MonitorWorkflowConfig,
)
import tarav.agent.monitor.workflows as monitor_workflows
from tarav.testing import TaravTestEnvironment

from tarav.testing import codex_auth_json, seed_codex_account
from _helpers import write_text_file


def test_monitor_profile_target_accepts_explicit_scoped_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
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
    environment = TaravTestEnvironment.create(tmp_path)
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

def test_build_monitor_workflows_includes_auto_prime_when_configured() -> None:
    config = MonitorWorkflowConfig(
        name=AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
        targets=(
            MonitorTarget(provider="codex", account="jp", home=Path("/tmp/codex-jp")),
        ),
        refresh_interval_sec=60,
        retry_cooldown_sec=600,
        target_limit_ids={"codex": ("burst",)},
        triggers={"codex": ("near_zero_full_window",)},
        raw_config={},
    )
    workflows = monitor_workflows.build_monitor_workflows((config,))
    assert any(w.name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW for w in workflows)

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


def test_account_rotation_config_can_disable_auto_materialize(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_global_config(
        agent={
            "accounts": {
                "monitor": [
                    {
                        "workflow": ACCOUNT_ROTATION_WORKFLOW,
                        "auto_materialize": False,
                        "refresh_interval_sec": 120,
                    }
                ]
            }
        }
    )

    configs = load_monitor_workflow_configs(start_path=tmp_path)

    assert configs[0].name == ACCOUNT_ROTATION_WORKFLOW
    assert configs[0].targets == ()
    workflow = next(
        w
        for w in monitor_workflows.build_monitor_workflows(configs)
        if w.name == ACCOUNT_ROTATION_WORKFLOW
    )
    assert workflow.auto_materialize is False
    assert workflow.refresh_interval_sec == 120


def test_account_rotation_defaults_to_auto_materialize() -> None:
    workflow = next(
        w
        for w in monitor_workflows.build_monitor_workflows(())
        if w.name == ACCOUNT_ROTATION_WORKFLOW
    )

    assert workflow.auto_materialize is True


def test_account_rotation_config_rejects_non_boolean_auto_materialize(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_global_config(
        agent={
            "accounts": {
                "monitor": [
                    {
                        "workflow": ACCOUNT_ROTATION_WORKFLOW,
                        "auto_materialize": "no",
                    }
                ]
            }
        }
    )

    with pytest.raises(CliError, match="auto_materialize must be true or false"):
        load_monitor_workflow_configs(start_path=tmp_path)
