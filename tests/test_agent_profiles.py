from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tarav.l0._core.errors import CliError
from tarav.l1.agent.commands import register_agent_commands
from tarav.l1.agent.commands.accounts import _cmd_agent_accounts_materialize
from tarav.l1.agent.commands.run import _cmd_agent_run
from tarav.l1.agent.account_status import AgentAccountContext
from tarav.l1.agent.config import load_agent_configs, profile_path, write_agent_profile
from tarav.l1.agent.primitives import AgentConfig
from tarav.l1.agent.run_runtime import (
    CLAUDE_CONFIG_DIR_ENV_VAR,
    CODEX_HOME_ENV_VAR,
    COPILOT_HOME_ENV_VAR,
    HARNESS_INJECTED_ENV_ALLOWLIST,
    AgentCommandConfig,
    AgentRunConfig,
)
from tarav.l1.agent.providers.registry import resolve_account_runtime_agent, resolve_agent_config
from tarav.l1.agent.providers.claude_code.agent import ClaudeAgent
from tarav.l1.agent.providers.codex.agent import CodexAgent
from tarav.l1.agent.providers.copilot_cli.agent import CopilotAgent
from tarav.l1.agent.providers.pi.agent import PiAgent
from tarav.l0.testing import TaravTestEnvironment

from tarav.l0.testing import codex_auth_json, seed_claude_account, seed_codex_account
from _helpers import (
    read_json_file,
    read_jsonl_file,
    write_text_file,
)


def test_profile_file_loads_complete_agent_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
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
            "env": {"TARAV_TEST": "1"},
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
    environment = TaravTestEnvironment.create(tmp_path)
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


def test_profile_file_without_default_model_uses_provider_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-main"
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profile(
        "codex-main",
        **{
            "provider": "codex",
            "homes": [str(home)],
            "accounts": ["jp"],
        },
    )

    config = load_agent_configs()[0]

    assert config.default_model is None


def test_profile_file_rejects_unknown_account_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
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
    environment = TaravTestEnvironment.create(tmp_path)
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


def test_account_runtime_agent_uses_profile_env_and_account_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "claude-br"
    seed_claude_account("browser-br", account_uuid="acc_browser-br")
    environment.write_profile(
        "claude-br",
        provider="claude-code",
        cli_command=["/bin/echo"],
        homes=[str(home)],
        accounts=["browser-br"],
        run_args=["--dangerously-skip-permissions"],
        env={
            "DISABLE_AUTOUPDATER": "1",
            "DISABLE_UPDATES": "1",
        },
    )

    agent = resolve_account_runtime_agent(
        provider="claude-code",
        account="browser-br",
        home=home,
        profile="claude-br",
        start_path=tmp_path,
    )

    assert agent.profile_id == "claude-br"
    assert agent.account == AgentAccountContext(
        provider="claude-code",
        account="browser-br",
    )
    assert agent.cli_command == ("/bin/echo",)
    assert agent.run_args == ("--dangerously-skip-permissions",)
    assert dict(agent.env) == {
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_UPDATES": "1",
    }


def test_account_runtime_agent_rejects_profile_account_out_of_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "claude-br"
    seed_claude_account("browser-br", account_uuid="acc_browser-br")
    environment.write_profile(
        "claude-jp",
        provider="claude-code",
        homes=[str(home)],
        accounts=["browser-jp"],
    )

    with pytest.raises(CliError, match="allows accounts: browser-jp"):
        resolve_account_runtime_agent(
            provider="claude-code",
            account="browser-br",
            home=home,
            profile="claude-jp",
            start_path=tmp_path,
        )


def test_account_runtime_agent_infers_unique_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-br"
    auth_file = tmp_path / "auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_br"))
    seed_codex_account("br", account_id="acc_br")
    environment.write_profile(
        "codex-br",
        provider="codex",
        homes=[str(home)],
        accounts=["br"],
        env={"TARAV_RUNTIME_TEST": "1"},
    )

    agent = resolve_account_runtime_agent(
        provider="codex",
        account="br",
        home=home,
        profile=None,
        start_path=tmp_path,
    )

    assert agent.profile_id == "codex-br"
    assert dict(agent.env) == {"TARAV_RUNTIME_TEST": "1"}
    assert agent.account == AgentAccountContext(provider="codex", account="br")


def test_account_runtime_agent_requires_unique_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-br"
    auth_file = tmp_path / "auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_br"))
    seed_codex_account("br", account_id="acc_br")
    environment.write_profile(
        "codex-br-a",
        provider="codex",
        homes=[str(home)],
        accounts=["br"],
    )
    environment.write_profile(
        "codex-br-b",
        provider="codex",
        homes=[str(home)],
        accounts=["br"],
    )

    with pytest.raises(CliError, match="matches multiple profiles"):
        resolve_account_runtime_agent(
            provider="codex",
            account="br",
            home=home,
            profile=None,
            start_path=tmp_path,
        )

    with pytest.raises(CliError, match="requires --profile"):
        resolve_account_runtime_agent(
            provider="codex",
            account="br",
            home=tmp_path / "unconfigured",
            profile=None,
            start_path=tmp_path,
        )


def test_agent_run_rejects_provider_home_without_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)

    with pytest.raises(CliError, match="requires --profile"):
        _cmd_agent_run(
            argparse.Namespace(
                provider="codex",
                profile=None,
                home=str(tmp_path / "codex-home"),
                account=None,
                model=None,
                project=None,
                cwd=None,
                argv=[],
                prompt="hello",
                non_interactive=False,
                dry_run=True,
            )
        )


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
            env=(("TARAV_TEST_CONFIG_ENV", "1"),),
        )
    )

    command = agent._build_command(AgentCommandConfig(prompt="hello"))

    assert command.env_overrides["TARAV_TEST_CONFIG_ENV"] == "1"
    assert command.env_overrides[CODEX_HOME_ENV_VAR] == str(tmp_path / "codex-home")
    harness_env = set(command.env_overrides) - {"TARAV_TEST_CONFIG_ENV"}
    assert harness_env <= HARNESS_INJECTED_ENV_ALLOWLIST["codex"]


@pytest.mark.parametrize(
    ("provider", "env_key"),
    [
        ("codex", CODEX_HOME_ENV_VAR),
        ("claude-code", CLAUDE_CONFIG_DIR_ENV_VAR),
        ("copilot-cli", COPILOT_HOME_ENV_VAR),
    ],
)
def test_profile_env_rejects_harness_injected_home_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    env_key: str,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_profile(
        "blocked-harness-env",
        provider=provider,
        homes=[str(tmp_path / "home")],
        env={env_key: str(tmp_path / "home")},
    )

    with pytest.raises(CliError, match=f"env.{env_key}.*harness-injected"):
        load_agent_configs()




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
    environment = TaravTestEnvironment.create(tmp_path)
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




def test_accounts_materialize_unsupported_provider_errors() -> None:
    # claude-code is now supported on the new model; copilot-cli is not.
    with pytest.raises(
        CliError,
        match="agent accounts materialize is not supported for provider copilot-cli",
    ):
        _cmd_agent_accounts_materialize(
            argparse.Namespace(
                provider="copilot-cli",
                home="/tmp/copilot",
                account="jp/gh-token",
                check=False,
                force=False,
                json=False,
                _agentos_argv=[],
            )
        )


def _provider_configs() -> dict[str, dict[str, object]]:
    return {"codex": {"cli_command": ["/bin/echo"]}}


def _account_events(tarav_home: Path) -> list[dict[str, object]]:
    event_files = sorted((tarav_home / "accounts" / "events").glob("*.jsonl"))
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
    environment = TaravTestEnvironment.create(tmp_path)
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
    environment = TaravTestEnvironment.create(tmp_path)
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
    from tarav.l1.agent.config import validate_provider_profile
    import tarav.l1.agent.providers.claude_code.agent as claude_agent_module

    calls: list[dict[str, object]] = []

    def fake_validate(profile_json: dict[str, object]) -> None:
        calls.append(dict(profile_json))

    monkeypatch.setattr(claude_agent_module, "validate_profile", fake_validate)

    environment = TaravTestEnvironment.create(tmp_path)
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
    from tarav.l1.agent.providers.claude_code.agent import ClaudeAgent
    from tarav.l1.agent.account_status import AgentAccountContext

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
    from tarav.l1.agent.providers.gemini_cli.agent import GeminiAgent

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
        ("claude-code", "tarav.l1.agent.providers.claude_code.agent:ClaudeAgent", True, True),
        ("codex", "tarav.l1.agent.providers.codex.agent:CodexAgent", True, True),
        ("copilot-cli", "tarav.l1.agent.providers.copilot_cli.agent:CopilotAgent", True, True),
        ("pi", "tarav.l1.agent.providers.pi.agent:PiAgent", True, False),
        ("gemini-cli", "tarav.l1.agent.providers.gemini_cli.agent:GeminiAgent", False, False),
        ("opencode", "tarav.l1.agent.providers.opencode.agent:OpencodeAgent", False, False),
        ("openclaw", "tarav.l1.agent.providers.openclaw.agent:OpenclawAgent", False, False),
    ],
)
def test_capability_protocols_match_provider_capability_matrix(
    provider: str,
    agent_import: str,
    expect_run: bool,
    expect_account_status: bool,
) -> None:
    import importlib

    from tarav.l1.agent.primitives import (
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
    environment = TaravTestEnvironment.create(tmp_path)
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
