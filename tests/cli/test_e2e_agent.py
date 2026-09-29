from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tarav.l0.testing import TaravTestEnvironment
from tarav.l3.cli.cli import main
from _helpers import captured_json


def test_agent_run_executes_configured_provider_command(tmp_path: Path, monkeypatch) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = environment.home
    work_home = tmp_path / "codex-home"
    environment.write_profile(
        "work",
        provider="codex",
        homes=[str(work_home)],
        cli_command=["/opt/homebrew/bin/codex"],
        default_model="gpt-5.4",
        model_flag="--model",
    )
    observed: dict[str, object] = {}

    def fake_run(command: list[str], *, cwd: str, env: dict[str, str], check: bool) -> subprocess.CompletedProcess[str]:
        observed.update(command=command, cwd=cwd, home=env["HOME"], check=check)
        return subprocess.CompletedProcess(command, 0)

    import tarav.l0._core.process as process_runner

    monkeypatch.setattr(process_runner.subprocess, "run", fake_run)

    # --force skips the pre-flight profile-check gate; this test covers command
    # construction and env resolution, not profile fitness.
    assert main(["agent", "run", "--provider", "codex", "--profile", "work", "--force", "--prompt", "hello"]) == 0
    assert observed["command"] == [
        "/opt/homebrew/bin/codex",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "gpt-5.4",
        "hello",
    ]
    assert observed["home"] == str(home)
    assert observed["cwd"] == str(Path.cwd().resolve())
    assert observed["check"] is False


def test_agent_run_dry_run_covers_env_prefix_and_raw_argv(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    pi_home = tmp_path / ".pi" / "profiles" / "codex-mm"
    environment.write_global_config(agent={"providers": {"pi": {"cli_command": ["pi"]}}})
    environment.write_profiles(
        [
            {"provider": "codex", "id": "work", "homes": [str(codex_home)], "cli_command": ["codex"]},
            {
                "provider": "pi",
                "id": "pi-mm",
                "homes": [str(pi_home)],
                "default_model": "gpt-5.4-mini",
                "env": {"PI_CODING_AGENT_DIR": str(pi_home)},
            },
            {"provider": "copilot-cli", "id": "copilot-main", "cli_command": ["copilot"]},
        ]
    )

    assert main(["agent", "run", "--provider", "codex", "--profile", "work", "--dry-run", "--", "exec", "hello"]) == 0
    assert capsys.readouterr().out.strip() == (
        f"CODEX_HOME={codex_home} codex --dangerously-bypass-approvals-and-sandbox exec hello"
    )

    assert main(["agent", "run", "--provider", "pi", "--profile", "pi-mm", "--dry-run", "--prompt", "hello from tarav"]) == 0
    assert capsys.readouterr().out.strip() == (
        f"PI_CODING_AGENT_DIR={pi_home} pi --model gpt-5.4-mini -p 'hello from tarav'"
    )

    assert main(["agent", "run", "--provider", "copilot-cli", "--profile", "copilot-main", "--dry-run", "--", "auth", "status"]) == 0
    assert capsys.readouterr().out.strip() == "copilot --allow-all-tools --no-ask-user auth status"


def test_agent_profile_account_policy_invalid_value_rejected(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_profile(
        "claude-bad",
        provider="claude-code",
        cli_command=["claude"],
        account_policy="frozen",
    )

    assert main(["agent", "run", "--profile", "claude-bad", "--prompt", "say ok"]) == 1
    err = capsys.readouterr().err
    assert "account_policy" in err
    assert "profile-default" in err
    assert "home-current" in err


def test_agent_run_reports_user_facing_validation_errors(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_profile(
        "work",
        provider="codex",
        homes=[str(tmp_path / "codex-home")],
        cli_command=["codex"],
    )

    assert main(["agent", "run", "--provider", "codex", "--profile", "work", "--prompt", "hello", "--", "exec", "hello"]) == 1
    assert "--prompt cannot be combined with provider arguments after --" in capsys.readouterr().err

    with pytest.raises(SystemExit) as exc_info:
        main(["agent", "run", "--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--prompt" in output
    assert "Raw provider arguments to pass after --" in output


def test_agent_list_reports_configured_instances(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    work_home = tmp_path / "codex-home"
    environment.write_profile(
        "work",
        provider="codex",
        label="Codex work",
        homes=[str(work_home)],
        cli_command=["/opt/homebrew/bin/codex"],
        default_model="gpt-5.4",
    )

    assert main(["agent", "list", "--provider", "codex"]) == 0
    assert capsys.readouterr().out.strip() == f"codex [id=work; Codex work; model=gpt-5.4; home={work_home}]"

    assert main(["agent", "list", "--provider", "codex", "--json"]) == 0
    payload = captured_json(capsys)
    assert payload["agents"][0]["provider"] == "codex"
    assert payload["agents"][0]["cli_command"] == ["/opt/homebrew/bin/codex"]
    assert payload["agents"][0]["default_model"] == "gpt-5.4"
