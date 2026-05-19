from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentos.cli import main
from _helpers import (
    captured_json,
    isolate_agentos,
    write_global_config,
    write_project_config,
    write_project_marker,
)


def test_agent_run_executes_configured_provider_command(tmp_path: Path, monkeypatch) -> None:
    home, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    work_home = tmp_path / "codex-home"
    write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["/opt/homebrew/bin/codex"],
                "default_model": "gpt-5.4",
                "model_flag": "--model",
            }
        ],
    )
    observed: dict[str, object] = {}

    def fake_run(command: list[str], *, cwd: str, env: dict[str, str], check: bool) -> subprocess.CompletedProcess[str]:
        observed.update(command=command, cwd=cwd, home=env["HOME"], check=check)
        return subprocess.CompletedProcess(command, 0)

    import agentos._core.process as process_runner

    monkeypatch.setattr(process_runner.subprocess, "run", fake_run)

    assert main(["agent", "run", "--provider", "codex", "--profile", "work", "--prompt", "hello"]) == 0
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
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    codex_home = tmp_path / "codex-home"
    pi_home = tmp_path / ".pi" / "profiles" / "codex-mm"
    write_global_config(
        agentos_home / "config.json",
        provider_configs={"pi": {"cli_command": ["pi"]}},
        provider_instances=[
            {"provider": "codex", "id": "work", "home": str(codex_home), "cli_command": ["codex"]},
            {
                "provider": "pi",
                "id": "pi-mm",
                "home": str(pi_home),
                "default_model": "gpt-5.4-mini",
                "env": {"PI_CODING_AGENT_DIR": str(pi_home)},
            },
            {"provider": "copilot-cli", "id": "copilot-main", "cli_command": ["copilot"]},
        ],
    )

    assert main(["agent", "run", "--provider", "codex", "--profile", "work", "--dry-run", "--", "exec", "hello"]) == 0
    assert capsys.readouterr().out.strip() == (
        f"CODEX_HOME={codex_home} codex --dangerously-bypass-approvals-and-sandbox --model gpt-5.4 exec hello"
    )

    assert main(["agent", "run", "--provider", "pi", "--profile", "pi-mm", "--dry-run", "--prompt", "hello from agentos"]) == 0
    assert capsys.readouterr().out.strip() == (
        f"PI_CODING_AGENT_DIR={pi_home} pi --model gpt-5.4-mini -p 'hello from agentos'"
    )

    assert main(["agent", "run", "--provider", "copilot-cli", "--profile", "copilot-main", "--dry-run", "--", "auth", "status"]) == 0
    assert capsys.readouterr().out.strip() == "copilot --allow-all-tools --no-ask-user auth status"


def test_agent_run_reports_user_facing_validation_errors(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {"provider": "codex", "id": "work", "home": str(tmp_path / "codex-home"), "cli_command": ["codex"]}
        ],
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
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    work_home = tmp_path / "codex-home"
    write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "label": "Codex work",
                "home": str(work_home),
                "cli_command": ["/opt/homebrew/bin/codex"],
                "default_model": "gpt-5.4",
            }
        ],
    )

    assert main(["agent", "list", "--provider", "codex"]) == 0
    assert capsys.readouterr().out.strip() == f"codex [id=work; Codex work; model=gpt-5.4; home={work_home}]"

    assert main(["agent", "list", "--provider", "codex", "--json"]) == 0
    payload = captured_json(capsys)
    assert payload["instances"][0]["provider"] == "codex"
    assert payload["instances"][0]["cli_command"] == ["/opt/homebrew/bin/codex"]
    assert payload["instances"][0]["default_model"] == "gpt-5.4"


def test_agent_run_uses_explicit_project_target_for_config_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    isolate_agentos(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    workspace = tmp_path / "workspace"
    work_home = tmp_path / "project-codex-home"
    project_root.mkdir()
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    write_project_marker(project_root)
    write_project_config(
        project_root / ".agentos" / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "project-work",
                "home": str(work_home),
                "cli_command": ["/opt/homebrew/bin/codex"],
            }
        ],
    )
    observed: dict[str, object] = {}

    def fake_run(command: list[str], *, cwd: str, env: dict[str, str], check: bool) -> subprocess.CompletedProcess[str]:
        observed.update(command=command, cwd=cwd, codex_home=env["CODEX_HOME"], check=check)
        return subprocess.CompletedProcess(command, 0)

    import agentos._core.process as process_runner

    monkeypatch.setattr(process_runner.subprocess, "run", fake_run)

    assert main(["agent", "run", "--provider", "codex", "--profile", "project-work", "--project", str(project_root), "--prompt", "hello"]) == 0
    assert observed["command"][0] == "/opt/homebrew/bin/codex"
    assert observed["codex_home"] == str(work_home)
    assert observed["cwd"] == str(workspace.resolve())
