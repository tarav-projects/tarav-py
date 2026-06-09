from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.commands import (
    _cmd_agent_accounts_link,
    _cmd_agent_run,
)
from agentos.agent.config import load_agent_configs, profile_path, write_agent_profile
from agentos.agent.primitives import AgentConfig
from agentos.agent.run_runtime import AgentCommandConfig, AgentRunConfig
from agentos.agent.providers import resolve_agent_config
from agentos.codex.account_registry import (
    inspect_codex_account_home,
    link_codex_account_to_home,
    read_codex_auth_info,
    register_codex_account_from_auth_file,
)
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
    assert config.instance_id == "codex-mm"
    assert config.provider == "codex"
    assert config.home == home.resolve()
    assert config.homes == (home.resolve(),)
    assert config.account is not None
    assert config.account.account == "mm"
    assert [account.account for account in config.accounts] == ["mm"]
    assert config.default_model == "gpt-5.4-mini"
    assert config.cli_command == ("/bin/echo",)


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
    link_codex_account_to_home(home=home, account="br")
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
    assert materialized_events[-1]["source"] == "agent.run"
    assert materialized_events[-1]["provider"] == "codex"
    assert materialized_events[-1]["profile"] == "codex-mm"
    assert materialized_events[-1]["account"] == "mm"


def test_accounts_link_profile_updates_profile_and_writes_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
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
    environment.write_profile(
        "codex-mm",
        **{"provider": "codex", "homes": [str(home)], "accounts": ["br"]},
    )

    result = _cmd_agent_accounts_link(
        argparse.Namespace(
            provider=None,
            profile="codex-mm",
            home=None,
            account="mm",
            force=False,
            json=False,
            _agentos_argv=[],
        )
    )

    assert result == 0
    assert read_json_file(profile_path("codex-mm"))["accounts"] == ["mm", "br"]
    status = inspect_codex_account_home(home=home)
    assert status["classification"] == "matching-active"
    assert status["auth"]["account_id"] == "acc_mm"
    removed_registry_name = "links" + ".json"
    assert not (agentos_home / "accounts" / "codex" / removed_registry_name).exists()
    events = _account_events(agentos_home)
    event_names = [event["event"] for event in events]
    assert "account.auth.materialized" in event_names
    assert "profile.account.changed" in event_names
    profile_events = [
        event for event in events if event["event"] == "profile.account.changed"
    ]
    assert profile_events[-1]["provider"] == "codex"
    assert profile_events[-1]["profile"] == "codex-mm"
    assert profile_events[-1]["from_account"] == "br"
    assert profile_events[-1]["to_account"] == "mm"
    assert "tokens" not in json.dumps(events)
    assert "secret-refresh-token" not in json.dumps(events)


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
            instance_id="claude-br",
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

    configs = {config.instance_id: config for config in load_agent_configs()}
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
        "account_policy": "locked",
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
            instance_id="claude-locked",
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


def test_no_run_provider_raises_on_run() -> None:
    from agentos.gemini.agent import GeminiAgent

    agent = GeminiAgent.from_config(
        AgentConfig(
            instance_id="gemini-test",
            provider="gemini-cli",
            cli_command=("gemini",),
        )
    )
    with pytest.raises(CliError, match="does not support run"):
        agent.run(
            AgentCommandConfig(prompt="hello"),
            AgentRunConfig(cwd="/tmp"),
        )
