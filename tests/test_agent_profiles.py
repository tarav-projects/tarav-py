from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.commands import (
    _cmd_agent_accounts_materialize,
    _cmd_agent_run,
    register_agent_commands,
)
from agentos.agent.account_status import AgentAccountContext
from agentos.agent.config import load_agent_configs, profile_path, write_agent_profile
from agentos.agent.primitives import AgentConfig
from agentos.agent.run_prepare import AgentRunPrepareRequest
from agentos.agent.run_runtime import (
    CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR,
    HARNESS_INJECTED_ENV_ALLOWLIST,
    AgentCommandConfig,
    AgentRunConfig,
)
from agentos.agent.providers import resolve_agent_config
import agentos.claude.account_registry as claude_account_registry
from agentos.claude.agent import ClaudeAgent
from agentos.claude.account_registry import ClaudeOAuthTokenMaterialization
from agentos.codex.agent import CodexAgent
from agentos.codex.account_registry import (
    inspect_codex_account_home,
    materialize_codex_account_to_home,
    read_codex_auth_info,
    register_codex_account_from_auth_file,
)
from agentos.copilot.agent import CopilotAgent
from agentos.pi.agent import PiAgent
from agentos.testing import AgentosTestEnvironment

from _helpers import (
    codex_auth_json,
    read_json_file,
    read_jsonl_file,
    write_text_file,
)


def test_profile_file_loads_complete_agent_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profile(
        "codex-mm",
        **{
            "provider": "codex",
            "homes": [str(home)],
            "accounts": ["mm"],
            "default_model": "gpt-5.4-mini",
            "run_args": ["--dangerously-bypass-approvals-and-sandbox"],
            "env": {"AGENTOS_TEST": "1"},
            "ping": {"model": "gpt-5.4-mini"},
        },
    )

    configs = load_agent_configs()

    assert len(configs) == 1
    config = configs[0]
    assert config.profile_id == "codex-mm"
    assert config.provider == "codex"
    assert config.home == home.resolve()
    assert config.homes == (home.resolve(),)
    assert config.account is not None
    assert config.account.account == "mm"
    assert [account.account for account in config.accounts] == ["mm"]
    assert config.default_model == "gpt-5.4-mini"
    assert config.cli_command == ("/bin/echo",)


def test_profile_file_loads_home_current_account_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-main"
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profile(
        "codex-main",
        **{
            "provider": "codex",
            "homes": [str(home)],
            "accounts": ["jp", "mm"],
            "account_policy": "home-current",
        },
    )

    config = load_agent_configs()[0]

    assert config.account_policy == "home-current"
    assert config.account is not None
    assert config.account.account == "jp"
    assert config.summary()["account_policy"] == "home-current"


def test_profile_file_rejects_unknown_account_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_profile(
        "codex-main",
        **{
            "provider": "codex",
            "homes": [str(tmp_path / "codex-main")],
            "accounts": ["jp", "mm"],
            "account_policy": "legacy-link",
        },
    )

    with pytest.raises(CliError, match="account_policy"):
        load_agent_configs()


def test_profile_resolution_does_not_require_provider_and_asserts_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_profile(
        "codex-mm",
        **{
            "provider": "codex",
            "homes": [str(tmp_path / "codex-mm")],
            "accounts": ["mm"],
        },
    )

    selected = resolve_agent_config(
        provider=None, profile="codex-mm", start_path=tmp_path
    )

    assert selected.provider == "codex"
    with pytest.raises(CliError, match="uses provider codex, not claude-code"):
        resolve_agent_config(
            provider="claude-code",
            profile="codex-mm",
            start_path=tmp_path,
        )
    with pytest.raises(CliError, match="--home is required"):
        resolve_agent_config(provider="codex", profile=None, start_path=tmp_path)


def test_agent_run_account_short_option_parses() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_agent_commands(subparsers)

    args = parser.parse_args(
        [
            "agent",
            "run",
            "--profile",
            "codex-main",
            "-a",
            "mm",
            "--prompt",
            "hello",
        ]
    )

    assert args.account == "mm"
    assert args.profile == "codex-main"


@pytest.mark.parametrize(
    ("provider", "agent_cls"),
    [
        ("codex", CodexAgent),
        ("claude-code", ClaudeAgent),
        ("copilot-cli", CopilotAgent),
        ("pi", PiAgent),
    ],
)
def test_minimal_command_env_only_contains_harness_injected_allowlist(
    tmp_path: Path,
    provider: str,
    agent_cls: type,
) -> None:
    agent = agent_cls.from_config(
        AgentConfig(
            provider=provider,
            profile_id=f"{provider}-minimal",
            home=tmp_path / provider,
            cli_command=("/bin/echo",),
        )
    )

    command = agent._build_command(AgentCommandConfig(prompt="hello"))

    assert set(command.env_overrides) <= HARNESS_INJECTED_ENV_ALLOWLIST[provider]


def test_profile_env_is_config_injected_not_harness_injected(tmp_path: Path) -> None:
    agent = CodexAgent.from_config(
        AgentConfig(
            provider="codex",
            profile_id="codex-config-env",
            home=tmp_path / "codex-home",
            cli_command=("/bin/echo",),
            env=(("AGENTOS_TEST_CONFIG_ENV", "1"),),
        )
    )

    command = agent._build_command(AgentCommandConfig(prompt="hello"))

    assert command.env_overrides["AGENTOS_TEST_CONFIG_ENV"] == "1"
    harness_env = set(command.env_overrides) - {"AGENTOS_TEST_CONFIG_ENV"}
    assert harness_env <= HARNESS_INJECTED_ENV_ALLOWLIST["codex"]


def test_claude_managed_credential_env_is_harness_injected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        claude_account_registry,
        "has_claude_oauth_token_kind",
        lambda account: account == "browser-token",
    )
    monkeypatch.setattr(
        claude_account_registry,
        "load_claude_oauth_token_for_account",
        lambda account: ClaudeOAuthTokenMaterialization(
            account=account,
            artifact_id="a" * 64,
            token="secret-token",
            artifact_file="token.txt",
        ),
    )
    agent = ClaudeAgent.from_config(
        AgentConfig(
            provider="claude-code",
            profile_id="claude-token",
            home=tmp_path / "claude-home",
            cli_command=("/bin/echo",),
            account=AgentAccountContext(
                provider="claude-code",
                account="browser-token",
            ),
        )
    )

    prepare_result = agent.prepare_run(
        AgentRunPrepareRequest(
            agent=agent,
            command_config=AgentCommandConfig(prompt="hello"),
            start_path=tmp_path,
            dry_run=False,
            source="agent.run",
        )
    )

    assert prepare_result.env_overrides == {CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR: "secret-token"}
    assert set(prepare_result.env_overrides) <= HARNESS_INJECTED_ENV_ALLOWLIST[
        "claude-code"
    ]


def test_claude_non_interactive_does_not_author_permission_policy() -> None:
    agent = ClaudeAgent.from_config(
        AgentConfig(
            provider="claude-code",
            profile_id="claude-non-interactive",
            cli_command=("/bin/echo",),
        )
    )

    command = agent._build_command(
        AgentCommandConfig(prompt="hello", interaction_mode="non_interactive")
    )

    assert "--dangerously-skip-permissions" not in command.argv


def test_profile_home_override_must_be_in_profile_homes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    default_home = tmp_path / "codex-default"
    allowed_home = tmp_path / "codex-allowed"
    blocked_home = tmp_path / "codex-blocked"
    environment.write_profile(
        "codex-mm",
        **{
            "provider": "codex",
            "homes": [str(default_home), str(allowed_home)],
            "accounts": ["mm"],
        },
    )

    default_selected = resolve_agent_config(
        provider=None, profile="codex-mm", start_path=tmp_path
    )
    assert default_selected.home == default_home.resolve()

    allowed_selected = resolve_agent_config(
        provider=None,
        profile="codex-mm",
        start_path=tmp_path,
        home=allowed_home,
    )
    assert allowed_selected.home == allowed_home.resolve()

    with pytest.raises(CliError, match="cannot use --home"):
        resolve_agent_config(
            provider=None,
            profile="codex-mm",
            start_path=tmp_path,
            home=blocked_home,
        )


def test_profile_account_materialization_uses_profile_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    home = tmp_path / "codex-mm"
    br_auth = tmp_path / "br-auth.json"
    mm_auth = tmp_path / "mm-auth.json"
    write_text_file(br_auth, codex_auth_json(account_id="acc_br"))
    write_text_file(mm_auth, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=br_auth, account="br")
    register_codex_account_from_auth_file(auth_file=mm_auth, account="mm")
    materialize_codex_account_to_home(home=home, account="br")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profile(
        "codex-mm",
        **{"provider": "codex", "homes": [str(home)], "accounts": ["mm"]},
    )
    old_info = read_codex_auth_info(home / "auth.json")

    result = _cmd_agent_run(
        _run_args(provider=None, profile="codex-mm", prompt="hello", dry_run=True)
    )

    assert result == 0
    assert (
        "[agentos] would materialize codex auth for profile codex-mm from account mm"
        in capsys.readouterr().out
    )
    assert read_codex_auth_info(home / "auth.json").sha256 == old_info.sha256

    result = _cmd_agent_run(
        _run_args(provider=None, profile="codex-mm", prompt="hello")
    )

    assert result == 0
    assert (
        "[agentos] materialized codex auth for profile codex-mm from account mm"
        in capsys.readouterr().out
    )
    status = inspect_codex_account_home(home=home)
    assert status["classification"] == "matching-active"
    assert status["auth"]["account_id"] == "acc_mm"
    removed_registry_name = "links" + ".json"
    assert not (agentos_home / "accounts" / "codex" / removed_registry_name).exists()
    events = _account_events(agentos_home)
    materialized_events = [
        event for event in events if event["event"] == "account.auth.materialized"
    ]
    run_events = [
        event for event in materialized_events if event["source"] == "agent.run"
    ]
    assert run_events[-1]["provider"] == "codex"
    assert run_events[-1]["profile"] == "codex-mm"
    assert run_events[-1]["account"] == "mm"


def test_accounts_materialize_codex_check_does_not_mutate_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    auth_file = tmp_path / "mm-auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=auth_file, account="mm")

    result = _cmd_agent_accounts_materialize(
        argparse.Namespace(
            provider="codex",
            home=str(home),
            account="mm",
            check=True,
            force=False,
            json=False,
            _agentos_argv=[],
        )
    )

    assert result == 0
    assert inspect_codex_account_home(home=home)["classification"] == "missing"
    assert not any(
        event["event"] == "account.auth.materialized"
        for event in _account_events(environment.agentos_home)
    )


def test_accounts_materialize_codex_writes_home_and_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    auth_file = tmp_path / "mm-auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=auth_file, account="mm")

    result = _cmd_agent_accounts_materialize(
        argparse.Namespace(
            provider="codex",
            home=str(home),
            account="mm",
            check=False,
            force=False,
            json=False,
            _agentos_argv=[],
        )
    )

    assert result == 0
    status = inspect_codex_account_home(home=home)
    assert status["classification"] == "matching-active"
    events = _account_events(environment.agentos_home)
    assert events[-1]["event"] == "account.auth.materialized"
    assert events[-1]["source"] == "agent accounts materialize"
    assert events[-1]["provider"] == "codex"
    assert events[-1]["account"] == "mm"


def test_accounts_materialize_unsupported_provider_errors() -> None:
    with pytest.raises(
        CliError,
        match="agent accounts materialize is not supported for provider claude-code",
    ):
        _cmd_agent_accounts_materialize(
            argparse.Namespace(
                provider="claude-code",
                home="/tmp/claude",
                account="browser-mm",
                check=False,
                force=False,
                json=False,
                _agentos_argv=[],
            )
        )


def _provider_configs() -> dict[str, dict[str, object]]:
    return {"codex": {"cli_command": ["/bin/echo"]}}


def _account_events(agentos_home: Path) -> list[dict[str, object]]:
    event_files = sorted((agentos_home / "accounts" / "events").glob("*.jsonl"))
    events: list[dict[str, object]] = []
    for event_file in event_files:
        events.extend(read_jsonl_file(event_file))
    return events


def _run_args(
    *,
    provider: str | None,
    profile: str,
    prompt: str,
    dry_run: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        provider=provider,
        profile=profile,
        home=None,
        account=None,
        model=None,
        project=None,
        cwd=None,
        argv=[],
        prompt=prompt,
        non_interactive=False,
        dry_run=dry_run,
    )



def test_profile_accounts_and_homes_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_global_config(agent={"providers": _provider_configs()})

    home = tmp_path / "claude-br"
    write_agent_profile(
        AgentConfig(
            provider="claude-code",
            profile_id="claude-br",
            cli_command=("claude",),
            home=home,
            homes=(home,),
            account=None,
            accounts=(),
        )
    )

    payload = read_json_file(profile_path("claude-br"))
    assert payload["homes"] == [str(home)]
    assert "home" not in payload
    assert "account" not in payload
    assert "account_policy" not in payload

    configs = {config.profile_id: config for config in load_agent_configs()}
    assert configs["claude-br"].homes == (home.resolve(),)
    assert configs["claude-br"].accounts == ()


def test_profile_rejects_removed_account_home_policy_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_global_config(agent={"providers": _provider_configs()})

    for field_name, value in {
        "account": "mm",
        "home": str(tmp_path / "codex-mm"),
    }.items():
        environment.write_profile(
            "codex-mm",
            provider="codex",
            **{field_name: value},
        )
        with pytest.raises(CliError, match=f"{field_name}.*no longer supported"):
            load_agent_configs()


def test_provider_validate_profile_is_invoked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentos.agent.config import validate_provider_profile
    import agentos.claude.agent as claude_agent_module

    calls: list[dict[str, object]] = []

    def fake_validate(profile_json: dict[str, object]) -> None:
        calls.append(dict(profile_json))

    monkeypatch.setattr(claude_agent_module, "validate_profile", fake_validate)

    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_profile(
        "claude-main",
        **{"provider": "claude-code", "cli_command": ["claude"]},
    )

    configs = load_agent_configs()

    assert len(configs) == 1
    assert len(calls) == 1
    assert calls[0]["provider"] == "claude-code"

    def raising_validate(profile_json: dict[str, object]) -> None:
        raise CliError("claude-specific validation failed")

    monkeypatch.setattr(claude_agent_module, "validate_profile", raising_validate)
    with pytest.raises(CliError, match="claude-specific validation failed"):
        validate_provider_profile("claude-code", {"provider": "claude-code"})


def test_profile_account_scope_enforced_on_direct_agent_run_call() -> None:
    from agentos.claude.agent import ClaudeAgent
    from agentos.agent.account_status import AgentAccountContext

    agent = ClaudeAgent.from_config(
        AgentConfig(
            profile_id="claude-locked",
            provider="claude-code",
            cli_command=("claude",),
            account=AgentAccountContext(provider="claude-code", account="browser-br"),
            accounts=(AgentAccountContext(provider="claude-code", account="browser-br"),),
        )
    )
    with pytest.raises(CliError, match="allows accounts: browser-br"):
        agent.run(
            AgentCommandConfig(prompt="hello", account="claude-br-auth"),
            AgentRunConfig(cwd="/tmp"),
        )


def test_session_only_provider_has_no_run_or_account_status_capability() -> None:
    from agentos.gemini.agent import GeminiAgent

    agent = GeminiAgent.from_config(
        AgentConfig(
            profile_id="gemini-test",
            provider="gemini-cli",
            cli_command=("gemini",),
        )
    )
    assert not hasattr(agent, "run")
    assert not hasattr(agent, "run_dry")
    assert not hasattr(agent, "account_status")


@pytest.mark.parametrize(
    ("provider", "agent_import", "expect_run", "expect_account_status"),
    [
        ("claude-code", "agentos.claude.agent:ClaudeAgent", True, True),
        ("codex", "agentos.codex.agent:CodexAgent", True, True),
        ("copilot-cli", "agentos.copilot.agent:CopilotAgent", True, True),
        ("pi", "agentos.pi.agent:PiAgent", True, False),
        ("gemini-cli", "agentos.gemini.agent:GeminiAgent", False, False),
        ("opencode", "agentos.opencode.agent:OpencodeAgent", False, False),
        ("openclaw", "agentos.openclaw.agent:OpenclawAgent", False, False),
    ],
)
def test_capability_protocols_match_provider_capability_matrix(
    provider: str,
    agent_import: str,
    expect_run: bool,
    expect_account_status: bool,
) -> None:
    import importlib

    from agentos.agent.primitives import (
        AccountStatusCapable,
        AgentAdapter,
        RunCapable,
        SessionDiscoveryCapable,
    )

    module_name, class_name = agent_import.split(":")
    agent_cls = getattr(importlib.import_module(module_name), class_name)
    agent = agent_cls.from_config(
        AgentConfig(profile_id="cap-test", provider=provider, cli_command=("cli",))
    )

    # every adapter satisfies the base contract and session discovery
    assert isinstance(agent, AgentAdapter)
    assert isinstance(agent, SessionDiscoveryCapable)
    assert isinstance(agent, RunCapable) is expect_run
    assert isinstance(agent, AccountStatusCapable) is expect_account_status


def test_run_on_session_only_provider_fails_with_capability_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_profile(
        "gemini-x",
        **{
            "provider": "gemini-cli",
            "homes": [str(tmp_path / "gemini")],
            "cli_command": ["gemini"],
        },
    )

    with pytest.raises(CliError, match="does not support run"):
        _cmd_agent_run(
            _run_args(
                provider=None,
                profile="gemini-x",
                prompt="hello",
                dry_run=True,
            )
        )
