from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from agentos.cli import main
from _helpers import write_global_config as _write_global_config, write_project_config as _write_project_config, write_project_marker as _write_project_marker, write_text_file as _write


def _readlink(path: Path) -> Path:
    target = Path(os.readlink(path))
    if target.is_absolute():
        return target
    return (path.parent / target).resolve()


def test_agent_run_uses_configured_agent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "label": "Codex work",
                "home": str(work_home),
                "cli_command": ["/opt/homebrew/bin/codex"],
                "env": {
                    "CODEX_HOME": str(work_home),
                },
                "default_model": "gpt-5.4",
                "model_flag": "--model",
            }
        ],
    )

    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["cwd"] = cwd
        observed["env_home"] = env["HOME"]
        observed["check"] = check
        return subprocess.CompletedProcess(command, 0)

    import agentos.agent.run_runtime as agent_run_runtime

    monkeypatch.setattr(agent_run_runtime.subprocess, "run", fake_run)

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--prompt",
                "hello from agentos",
            ]
        )
        == 0
    )

    assert observed["command"] == [
        "/opt/homebrew/bin/codex",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "gpt-5.4",
        "hello from agentos",
    ]
    assert observed["env_home"] == str(home)
    assert observed["command"][0] == "/opt/homebrew/bin/codex"
    assert observed["check"] is False
    assert observed["cwd"] == str(Path.cwd().resolve())


def test_agent_run_uses_configured_instance_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["/opt/homebrew/bin/codex"],
                "env": {
                    "CODEX_HOME": str(work_home),
                },
            }
        ],
    )

    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed["codex_home"] = env["CODEX_HOME"]
        return subprocess.CompletedProcess(command, 0)

    import agentos.agent.run_runtime as agent_run_runtime

    monkeypatch.setattr(agent_run_runtime.subprocess, "run", fake_run)

    assert main(["agent", "run", "--provider", "codex", "--profile", "work", "--prompt", "hello"]) == 0

    assert observed["codex_home"] == str(work_home)


def test_agent_run_home_override_updates_provider_home_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    configured_home = tmp_path / "codex-configured"
    override_home = tmp_path / "codex-override"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(configured_home),
                "cli_command": ["codex"],
                "env": {
                    "CODEX_HOME": str(configured_home),
                },
            }
        ],
    )

    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, check
        observed["command"] = command
        observed["codex_home"] = env["CODEX_HOME"]
        return subprocess.CompletedProcess(command, 0)

    import agentos.agent.run_runtime as agent_run_runtime

    monkeypatch.setattr(agent_run_runtime.subprocess, "run", fake_run)

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--home",
                str(override_home),
                "--prompt",
                "hello",
            ]
        )
        == 0
    )

    assert observed["command"] == [
        "codex",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "gpt-5.4",
        "hello",
    ]
    assert observed["codex_home"] == str(override_home.resolve())


def test_agent_run_codex_account_dry_run_uses_profile_home_override(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    configured_home = tmp_path / "codex-configured"
    override_home = tmp_path / "codex-override"
    auth_path = agentos_home / "accounts" / "codex" / "tk" / "auth.json"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write(auth_path, "{}\n")
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(configured_home),
                "cli_command": ["codex"],
            }
        ],
    )

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--home",
                str(override_home),
                "--account",
                "tk",
                "--dry-run",
                "--prompt",
                "hello",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out.strip().splitlines()
    assert output == [
        f"link {override_home.resolve() / 'auth.json'} -> {auth_path.resolve()}",
        f"CODEX_HOME={override_home.resolve()} codex --dangerously-bypass-approvals-and-sandbox --model gpt-5.4 hello",
    ]


def test_agent_link_codex_switches_auth_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    codex_home = tmp_path / "codex-home"
    auth_path = agentos_home / "accounts" / "codex" / "tk" / "auth.json"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write(auth_path, "{}\n")

    assert (
        main(
            [
                "agent",
                "link",
                "--provider",
                "codex",
                "--home",
                str(codex_home),
                "--account",
                "tk",
            ]
        )
        == 0
    )

    assert (codex_home / "auth.json").is_symlink()
    assert _readlink(codex_home / "auth.json") == auth_path


def test_agent_link_codex_dry_run_prints_link_without_mutating(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    accounts_root = tmp_path / "codex-accounts"
    codex_home = tmp_path / "codex-home"
    auth_path = accounts_root / "tk" / "auth.json"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write(auth_path, "{}\n")
    _write(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "codex": {"mux": {"accounts_root": str(accounts_root)}},
            }
        ),
    )

    assert (
        main(
            [
                "agent",
                "link",
                "--provider",
                "codex",
                "--home",
                str(codex_home),
                "--account",
                "tk",
                "--dry-run",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out.strip() == f"link {codex_home.resolve() / 'auth.json'} -> {auth_path.resolve()}"
    assert not (codex_home / "auth.json").exists()


def test_agent_link_rejects_unsupported_provider(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    assert (
        main(
            [
                "agent",
                "link",
                "--provider",
                "pi",
                "--home",
                str(tmp_path / "pi-home"),
                "--account",
                "tk",
            ]
        )
        == 1
    )

    assert "agent link is not supported for provider pi" in capsys.readouterr().err


def test_agent_link_help_has_no_profile(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["agent", "link", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--provider" in output
    assert "--home" in output
    assert "--account" in output
    assert "--dry-run" in output
    assert "--profile" not in output


@pytest.mark.parametrize(
    "args, expected_error",
    [
        pytest.param(
            ["agent", "link", "--provider", "codex", "--account", "tk"],
            "the following arguments are required: --home",
            id="missing-home",
        ),
        pytest.param(
            ["agent", "link", "--provider", "codex", "--home", "/tmp/codex-home"],
            "the following arguments are required: --account",
            id="missing-account",
        ),
    ],
)
def test_agent_link_requires_home_and_account(
    args: list[str],
    expected_error: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(args)

    assert exc_info.value.code == 2
    assert expected_error in capsys.readouterr().err


def test_agent_run_invokes_provider_native_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    cwd = tmp_path / "workspace"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["codex"],
            }
        ],
    )

    from agentos.agent.run_runtime import AgentRunRequest, AgentRunResult
    from agentos.codex.agent import CodexAgent

    observed: dict[str, object] = {}

    def fake_run(self: CodexAgent, request: AgentRunRequest) -> AgentRunResult:
        observed["provider"] = self.provider
        observed["request"] = request
        return AgentRunResult(exit_code=7)

    monkeypatch.setattr(CodexAgent, "run", fake_run)

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--model",
                "gpt-5.2",
                "--account",
                "tk",
                "--cwd",
                str(cwd),
                "--prompt",
                "hello",
            ]
        )
        == 7
    )

    request = observed["request"]
    assert observed["provider"] == "codex"
    assert request == AgentRunRequest(
        prompt="hello",
        argv=(),
        model="gpt-5.2",
        cwd=cwd.resolve(),
        account="tk",
    )


def test_agent_run_dry_invokes_provider_native_run_dry(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["codex"],
            }
        ],
    )

    from agentos.agent.run_runtime import AgentRunDryResult, AgentRunRequest
    from agentos.codex.agent import CodexAgent

    observed: dict[str, object] = {}

    def fake_run_dry(self: CodexAgent, request: AgentRunRequest) -> AgentRunDryResult:
        observed["provider"] = self.provider
        observed["request"] = request
        return AgentRunDryResult(lines=("provider dry line",))

    monkeypatch.setattr(CodexAgent, "run_dry", fake_run_dry)

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--dry-run",
                "--prompt",
                "hello dry",
            ]
        )
        == 0
    )

    request = observed["request"]
    assert observed["provider"] == "codex"
    assert request == AgentRunRequest(
        prompt="hello dry",
        argv=(),
        model=None,
        cwd=Path.cwd().resolve(),
        account=None,
    )
    assert capsys.readouterr().out.strip() == "provider dry line"


def test_agent_run_dry_invokes_provider_native_run_dry_with_raw_argv(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["codex"],
            }
        ],
    )

    from agentos.agent.run_runtime import AgentRunDryResult, AgentRunRequest
    from agentos.codex.agent import CodexAgent

    observed: dict[str, object] = {}

    def fake_run_dry(self: CodexAgent, request: AgentRunRequest) -> AgentRunDryResult:
        observed["provider"] = self.provider
        observed["request"] = request
        return AgentRunDryResult(lines=("provider raw dry line",))

    monkeypatch.setattr(CodexAgent, "run_dry", fake_run_dry)

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--dry-run",
                "--",
                "exec",
                "hello",
            ]
        )
        == 0
    )

    request = observed["request"]
    assert observed["provider"] == "codex"
    assert request == AgentRunRequest(
        prompt=None,
        argv=("exec", "hello"),
        model=None,
        cwd=Path.cwd().resolve(),
        account=None,
    )
    assert capsys.readouterr().out.strip() == "provider raw dry line"


def test_configured_codex_agent_uses_provider_native_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["/opt/homebrew/bin/codex"],
            }
        ],
    )

    from agentos.agent.providers import load_configured_agents
    from agentos.codex.agent import CodexAgent

    agents = load_configured_agents()

    assert len(agents) == 1
    assert isinstance(agents[0], CodexAgent)
    assert agents[0].instance_id == "work"


def test_codex_agent_discovers_session_refs_and_loads_sessions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = (
        work_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    )
    index_path = work_home / "session_index.jsonl"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write(
        rollout_path,
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-08T01:08:59.089Z",
                        "type": "session_meta",
                        "payload": {"id": session_id},
                    }
                )
            ]
        )
        + "\n",
    )
    _write(
        index_path,
        json.dumps(
            {
                "id": session_id,
                "thread_name": "codex-session-ref-thread",
                "updated_at": "2026-03-08T01:09:00Z",
            }
        )
        + "\n",
    )
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["/opt/homebrew/bin/codex"],
            }
        ],
    )

    from agentos.agent.providers import load_configured_agents
    from agentos.codex.agent import CodexAgent
    from agentos.codex.session import CodexSession, CodexSessionRef

    agent = load_configured_agents()[0]

    assert isinstance(agent, CodexAgent)
    session_refs = agent.discover_session_refs()
    assert len(session_refs) == 1
    assert isinstance(session_refs[0], CodexSessionRef)
    assert session_refs[0].native_session_id == session_id
    assert session_refs[0].rollout_paths == (rollout_path,)
    assert session_refs[0].index_paths == (index_path,)
    assert session_refs[0].thread_name == "codex-session-ref-thread"

    session = agent.load_session(session_refs[0])

    assert isinstance(session, CodexSession)
    assert session.native_session_id == session_id
    assert session.rollout_paths == (rollout_path,)


def test_configured_provider_agents_use_provider_native_models(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "claude-code",
                "id": "claude-main",
                "cli_command": ["claude"],
            },
            {
                "provider": "copilot-cli",
                "id": "copilot-main",
            },
            {
                "provider": "pi",
                "id": "pi-main",
            },
        ],
    )

    from agentos.agent.providers import load_configured_agents
    from agentos.claude.agent import ClaudeAgent
    from agentos.copilot.agent import CopilotAgent
    from agentos.pi.agent import PiAgent

    agents = load_configured_agents()

    assert [type(agent) for agent in agents] == [ClaudeAgent, CopilotAgent, PiAgent]
    assert [agent.instance_id for agent in agents] == [
        "claude-main",
        "copilot-main",
        "pi-main",
    ]


def test_session_capable_provider_agents_expose_session_ref_discovery() -> None:
    from agentos.claude.agent import ClaudeAgent
    from agentos.codex.agent import CodexAgent
    from agentos.copilot.agent import CopilotAgent
    from agentos.gemini.agent import GeminiAgent
    from agentos.openclaw.agent import OpenclawAgent
    from agentos.opencode.agent import OpencodeAgent
    from agentos.pi.agent import PiAgent

    agents = (
        ClaudeAgent(),
        CodexAgent(),
        CopilotAgent(),
        GeminiAgent(),
        OpenclawAgent(),
        OpencodeAgent(),
        PiAgent(),
    )

    for agent in agents:
        assert agent.discover_session_refs() == ()


def test_agent_run_uses_copilot_cli_agent_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "copilot-cli",
                "id": "copilot-main",
                "label": "Copilot main",
            }
        ],
    )

    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["cwd"] = cwd
        observed["env_home"] = env["HOME"]
        observed["check"] = check
        return subprocess.CompletedProcess(command, 0)

    import agentos.agent.run_runtime as agent_run_runtime

    monkeypatch.setattr(agent_run_runtime.subprocess, "run", fake_run)

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "copilot-cli",
                "--profile",
                "copilot-main",
                "--model",
                "gpt-5.2",
                "--prompt",
                "hello from agentos",
            ]
        )
        == 0
    )

    assert observed["command"] == [
        "copilot",
        "--allow-all-tools",
        "--no-ask-user",
        "--model",
        "gpt-5.2",
        "-p",
        "hello from agentos",
    ]
    assert observed["env_home"] == str(home)
    assert observed["check"] is False
    assert observed["cwd"] == str(Path.cwd().resolve())


def test_agent_run_uses_pi_provider_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    pi_home = tmp_path / ".pi" / "profiles" / "codex-mm"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "pi",
                "id": "pi-mm",
                "home": str(pi_home),
                "default_model": "gpt-5.4-mini",
                "env": {
                    "PI_CODING_AGENT_DIR": str(pi_home),
                },
            }
        ],
    )

    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["cwd"] = cwd
        observed["agent_dir"] = env["PI_CODING_AGENT_DIR"]
        observed["check"] = check
        return subprocess.CompletedProcess(command, 0)

    import agentos.agent.run_runtime as agent_run_runtime

    monkeypatch.setattr(agent_run_runtime.subprocess, "run", fake_run)

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "pi",
                "--profile",
                "pi-mm",
                "--prompt",
                "hello from agentos",
            ]
        )
        == 0
    )

    assert observed["command"] == [
        "pi",
        "--model",
        "gpt-5.4-mini",
        "-p",
        "hello from agentos",
    ]
    assert observed["agent_dir"] == str(pi_home)
    assert observed["check"] is False
    assert observed["cwd"] == str(Path.cwd().resolve())


def test_agent_run_dry_run_prints_instance_env_prefix(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    pi_home = tmp_path / ".pi" / "profiles" / "codex-mm"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "pi",
                "id": "pi-mm",
                "home": str(pi_home),
                "default_model": "gpt-5.4-mini",
                "env": {
                    "PI_CODING_AGENT_DIR": str(pi_home),
                },
            }
        ],
    )

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "pi",
                "--profile",
                "pi-mm",
                "--dry-run",
                "--prompt",
                "hello from agentos",
            ]
        )
        == 0
    )

    assert (
        capsys.readouterr().out.strip()
        == f"PI_CODING_AGENT_DIR={pi_home} pi --model gpt-5.4-mini -p 'hello from agentos'"
    )


def test_agent_run_codex_provider_argv_dry_run_uses_configured_run_args(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    codex_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(codex_home),
                "cli_command": ["codex"],
            }
        ],
    )

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--dry-run",
                "--",
                "exec",
                "hello",
            ]
        )
        == 0
    )

    assert (
        capsys.readouterr().out.strip()
        == f"CODEX_HOME={codex_home} codex --dangerously-bypass-approvals-and-sandbox --model gpt-5.4 exec hello"
    )


def test_agent_run_codex_raw_argv_with_account_links_auth(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    codex_home = tmp_path / "codex-home"
    auth_path = agentos_home / "accounts" / "codex" / "tk" / "auth.json"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write(auth_path, "{}\n")

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(codex_home),
                "cli_command": ["codex"],
            }
        ],
    )

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--account",
                "tk",
                "--dry-run",
                "--",
                "exec",
                "hello",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out.strip().splitlines()
    assert output == [
        f"link {codex_home / 'auth.json'} -> {auth_path.resolve()}",
        f"CODEX_HOME={codex_home} codex --dangerously-bypass-approvals-and-sandbox --model gpt-5.4 exec hello",
    ]


def test_agent_run_copilot_raw_argv_dry_run(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "copilot-cli",
                "id": "copilot-main",
                "cli_command": ["copilot"],
            }
        ],
    )

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "copilot-cli",
                "--profile",
                "copilot-main",
                "--dry-run",
                "--",
                "auth",
                "status",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out.strip() == "copilot --allow-all-tools --no-ask-user auth status"


def test_agent_run_pi_raw_argv_dry_run(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    pi_home = tmp_path / ".pi" / "profiles" / "codex-mm"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "pi",
                "id": "pi-mm",
                "home": str(pi_home),
                "env": {
                    "PI_CODING_AGENT_DIR": str(pi_home),
                },
            }
        ],
    )

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "pi",
                "--profile",
                "pi-mm",
                "--dry-run",
                "--",
                "status",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out.strip() == f"PI_CODING_AGENT_DIR={pi_home} pi status"


def test_agent_run_help_describes_prompt_option_not_positional_prompt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["agent", "run", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--prompt" in output
    assert "Prompt to pass after --" not in output
    assert "Raw provider arguments to pass after --" in output


@pytest.mark.parametrize(
    "args, expected_error",
    [
        pytest.param(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--prompt",
                "hello",
                "--",
                "exec",
                "hello",
            ],
            "--prompt cannot be combined with provider arguments after --",
            id="prompt-and-provider-argv",
        ),
    ],
)
def test_agent_run_rejects_invalid_prompt_and_argv_combinations(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    expected_error: str,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["codex"],
            }
        ],
    )

    assert main(args) == 1
    assert expected_error in capsys.readouterr().err


def test_agent_run_without_prompt_defaults_to_empty_raw_argv(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["codex"],
            }
        ],
    )

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "work",
                "--dry-run",
                "--",
            ]
        )
        == 0
    )
    assert (
        capsys.readouterr().out.strip()
        == f"CODEX_HOME={work_home} codex --dangerously-bypass-approvals-and-sandbox --model gpt-5.4"
    )


def test_agent_list_prints_configured_agents(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "label": "Codex work",
                "home": str(work_home),
                "cli_command": ["codex"],
                "env": {
                    "CODEX_HOME": str(work_home),
                },
                "default_model": "gpt-5.4",
                "model_flag": "--model",
            }
        ],
    )

    assert main(["agent", "list", "--provider", "codex"]) == 0
    output_lines = capsys.readouterr().out.strip().splitlines()
    assert output_lines == [
        f"codex [id=work; Codex work; model=gpt-5.4; homes=home={work_home}]"
    ]


def test_agent_list_json_includes_configured_instance_fields(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "work",
                "home": str(work_home),
                "cli_command": ["/opt/homebrew/bin/codex"],
                "env": {
                    "CODEX_HOME": str(work_home),
                },
                "default_model": "gpt-5.4",
                "model_flag": "--model",
            }
        ],
    )

    assert main(["agent", "list", "--provider", "codex", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["instances"]) == 1
    configured = payload["instances"][0]
    assert configured["provider"] == "codex"
    assert configured["cli_command"] == [
        "/opt/homebrew/bin/codex",
    ]
    assert configured["default_model"] == "gpt-5.4"
    assert configured["env"]["CODEX_HOME"] == str(work_home)


def test_provider_capabilities_are_scoped_by_subsystem() -> None:
    from agentos.agent.providers import supported_default_run_provider_families
    from agentos.agent.accounts import supported_account_provider_families
    from agentos.chatlas.raw import supported_chatlas_provider_families
    from agentos.home.providers import supported_home_providers

    default_run_providers = set(supported_default_run_provider_families())
    account_providers = {
        provider.family
        for provider in supported_account_provider_families()
    }
    chatlas_providers = {
        provider.family
        for provider in supported_chatlas_provider_families()
    }
    home_providers_with_session_layout = {
        provider.family
        for provider in supported_home_providers()
        if provider.supports_session_discovery
    }

    assert "pi" in default_run_providers
    assert "pi" not in account_providers
    assert "pi" in chatlas_providers
    assert "pi" in home_providers_with_session_layout
    assert "claude-code" not in default_run_providers
    assert "claude-code" in account_providers
    assert "claude-code" in chatlas_providers
    assert "claude-code" in home_providers_with_session_layout


def test_chat_provider_specs_reuse_shared_provider_home_topology() -> None:
    from agentos.agent.config import canonical_chat_provider_spec_for_name
    from agentos.providers import canonical_provider_spec_for_name

    provider_spec = canonical_provider_spec_for_name("codex")
    chat_provider_spec = canonical_chat_provider_spec_for_name("codex")

    assert provider_spec is not None
    assert chat_provider_spec is not None
    assert chat_provider_spec.home_slots == provider_spec.home_slots


def test_agent_run_uses_explicit_project_target_for_config_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    project_root = tmp_path / "project"
    workspace = tmp_path / "workspace"
    work_home = tmp_path / "codex-home"
    home.mkdir()
    agentos_home.mkdir()
    project_root.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    monkeypatch.chdir(workspace)

    _write_project_marker(project_root)
    _write_project_config(
        project_root / ".agentos" / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "project-work",
                "label": "Project work",
                "home": str(work_home),
                "cli_command": ["/opt/homebrew/bin/codex"],
                "env": {
                    "CODEX_HOME": str(work_home),
                },
            }
        ],
    )

    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["cwd"] = cwd
        observed["codex_home"] = env["CODEX_HOME"]
        observed["check"] = check
        return subprocess.CompletedProcess(command, 0)

    import agentos.agent.run_runtime as agent_run_runtime

    monkeypatch.setattr(agent_run_runtime.subprocess, "run", fake_run)

    assert (
        main(
            [
                "agent",
                "run",
                "--provider",
                "codex",
                "--profile",
                "project-work",
                "--project",
                str(project_root),
                "--prompt",
                "hello from project config",
            ]
        )
        == 0
    )

    assert observed["command"] == [
        "/opt/homebrew/bin/codex",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "gpt-5.4",
        "hello from project config",
    ]
    assert observed["cwd"] == str(workspace.resolve())
    assert observed["codex_home"] == str(work_home)
    assert observed["check"] is False


def test_agent_accounts_stats_uses_configured_agent_account_instances(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "codex-main",
                "label": "Codex main",
                "cli_command": ["codex"],
            },
            {
                "provider": "claude-code",
                "id": "claude-main",
                "label": "Claude main",
                "cli_command": ["claude"],
            },
        ],
        account_instance_ids=["claude-main"],
    )

    from agentos.agent import accounts as chat_accounts

    monkeypatch.setattr(chat_accounts, "_utc_now_iso", lambda: "2026-03-25T12:00:00Z")

    observed_calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check, env, timeout
        observed_calls.append(command)
        if command == ["claude", "auth", "status", "--json"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "loggedIn": True,
                        "authMethod": "claude.ai",
                        "subscriptionType": "pro",
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)

    assert main(["agent", "accounts", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert observed_calls == [["claude", "auth", "status", "--json"]]
    assert payload["command"] == "agent accounts stats"
    assert payload["provider_count"] == 1
    assert payload["account_count"] == 1
    assert [provider["provider"] for provider in payload["providers"]] == ["claude-code"]
    assert payload["providers"][0]["accounts"][0]["id"] == "claude-main"
