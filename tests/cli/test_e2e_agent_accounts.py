from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from agentos.cli.cli import main
from agentos.agent.monitor.config import load_monitor_workflow_configs
from agentos.testing import AgentosTestEnvironment, seed_codex_account
from _helpers import write_text_file

UUID = "07de2ad9-c2c5-4c05-8a09-3aa235a30650"


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _codex_home_auth_json(uuid: str) -> str:
    access = _jwt(
        {"https://api.openai.com/auth": {"chatgpt_account_id": uuid}, "email": "x@e.com"}
    )
    return json.dumps(
        {"tokens": {"access_token": access, "id_token": _jwt({}), "account_id": uuid}}
    )


def _write_monitor_config(
    environment: AgentosTestEnvironment,
    monitor: list[dict[str, object]],
) -> None:
    environment.write_global_config(agent={"accounts": {"monitor": monitor}})


def test_agent_accounts_capture_activate_status_lifecycle(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    seed_codex_account("br", account_id=UUID)
    codex_home = tmp_path / "codex-br"
    write_text_file(codex_home / "auth.json", _codex_home_auth_json(UUID))

    assert (
        main(
            [
                "agent",
                "accounts",
                "capture",
                "--provider",
                "codex",
                "--home",
                str(codex_home),
            ]
        )
        == 0
    )
    capsys.readouterr()

    from agentos.agent import auth_registry as R

    capture = json.loads(R.captures_path("codex").read_text().splitlines()[-1])
    assert capture["account"] == "br"
    assert capture["method"] == "file"
    artifact_id = capture["artifact_id"]
    assert R.read_artifact("codex", artifact_id) is not None

    assert (
        main(
            [
                "agent",
                "accounts",
                "activate",
                "--provider",
                "codex",
                "--account",
                "br/file",
                "--ref",
                artifact_id,
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert R.active_ref("codex", "br", "file") == artifact_id

    assert main(["agent", "accounts", "status", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()
    assert main(["agent", "accounts", "list", "--provider", "codex"]) == 0
    assert "br" in capsys.readouterr().out


def test_agent_accounts_monitor_reports_configuration_errors(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)

    _write_monitor_config(environment, [{"workflow": "limits-tracking", "targets": []}])
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert (
        "agent.accounts.monitor[0].targets must not be empty" in capsys.readouterr().err
    )

    _write_monitor_config(
        environment,
        [
            {
                "workflow": "limits-tracking",
                "targets": [{"provider": "codex", "account": "missing"}],
            }
        ],
    )
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert (
        "agent.accounts.monitor[0].targets[0].account references unknown account:"
        " codex/missing" in capsys.readouterr().err
    )

    _write_monitor_config(
        environment,
        [
            {
                "workflow": "future-workflow",
                "targets": [{"provider": "codex", "account": "missing"}],
            }
        ],
    )
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert "unknown monitor workflow 'future-workflow'" in capsys.readouterr().err


def test_agent_accounts_monitor_auto_prime_trigger_config(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    seed_codex_account("br")

    _write_monitor_config(
        environment,
        [
            {
                "workflow": "auto-prime-zero-limits",
                "targets": [{"provider": "codex", "account": "br"}],
            }
        ],
    )
    config = load_monitor_workflow_configs(start_path=tmp_path)[0]
    assert config.triggers["codex"] == (
        "zero_usage",
        "near_zero_full_window",
        "sliding_reset",
        "period_key_churn",
    )

    _write_monitor_config(
        environment,
        [
            {
                "workflow": "auto-prime-zero-limits",
                "triggers": {"codex": ["zero_usage", "sliding_reset"]},
                "targets": [{"provider": "codex", "account": "br"}],
            }
        ],
    )
    config = load_monitor_workflow_configs(start_path=tmp_path)[0]
    assert config.triggers["codex"] == ("zero_usage", "sliding_reset")

    _write_monitor_config(
        environment,
        [
            {
                "workflow": "auto-prime-zero-limits",
                "triggers": {"codex": ["made_up"]},
                "targets": [{"provider": "codex", "account": "br"}],
            }
        ],
    )
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert (
        "agent.accounts.monitor[0].triggers.codex[0] is not supported"
        in capsys.readouterr().err
    )

    _write_monitor_config(
        environment,
        [
            {
                "workflow": "auto-prime-zero-limits",
                "triggers": {"copilot-cli": ["zero_usage"]},
                "targets": [{"provider": "codex", "account": "br"}],
            }
        ],
    )
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert (
        "agent.accounts.monitor[0].triggers.copilot-cli is not supported"
        in capsys.readouterr().err
    )
