from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import agentos.claude.agent as claude_agent_module
from agentos._core.errors import CliError
from agentos.agent.commands import _cmd_agent_ping, _cmd_agent_run
from agentos.agent.run_runtime import AgentRunResult
from agentos.claude.account_registry import register_claude_account
from agentos.codex.account_registry import (
    inspect_codex_account_home,
    materialize_codex_account_to_home,
    read_codex_auth_info,
    register_codex_account_from_auth_file,
)
from agentos.testing import AgentosTestEnvironment

from _helpers import (
    codex_auth_json,
    read_json_file,
    read_jsonl_file,
    write_claude_home,
    write_text_file,
)


def test_agent_run_dry_run_reports_stale_codex_materialization_without_mutating(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    old_auth, active_auth = _make_stale_profile_home(tmp_path, home=home, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(home)])
    old_info = read_codex_auth_info(old_auth)

    result = _cmd_agent_run(_run_args(profile="codex-mm", prompt="hello", dry_run=True))

    assert result == 0
    output = capsys.readouterr().out
    assert (
        "[agentos] would materialize codex auth for profile codex-mm from account mm"
        in output
    )
    assert "/bin/echo" in output
    assert read_codex_auth_info(home / "auth.json").sha256 == old_info.sha256
    assert read_codex_auth_info(active_auth).sha256 != old_info.sha256


def test_agent_run_materializes_stale_codex_home_before_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    _, active_auth = _make_stale_profile_home(tmp_path, home=home, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(home)])
    active_info = read_codex_auth_info(active_auth)

    result = _cmd_agent_run(_run_args(profile="codex-mm", prompt="hello"))

    assert result == 0
    output = capsys.readouterr().out
    assert (
        "[agentos] materialized codex auth for profile codex-mm from account mm"
        in output
    )
    assert read_codex_auth_info(home / "auth.json").sha256 == active_info.sha256


def test_agent_run_materializes_stale_same_account_home_with_explicit_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    _, active_auth = _make_stale_profile_home(tmp_path, home=home, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(home)])
    active_info = read_codex_auth_info(active_auth)

    result = _cmd_agent_run(_run_args(profile="codex-mm", account="mm", prompt="hello"))

    assert result == 0
    output = capsys.readouterr().out
    assert (
        "[agentos] materialized codex auth for profile codex-mm from account mm"
        in output
    )
    assert read_codex_auth_info(home / "auth.json").sha256 == active_info.sha256


def test_agent_ping_uses_codex_account_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    _, active_auth = _make_stale_profile_home(tmp_path, home=home, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(home, ping={"prompt": "745", "expected_number": 745})])
    active_info = read_codex_auth_info(active_auth)

    result = _cmd_agent_ping(_ping_args(profile="codex-mm"))

    assert result == 0
    output = capsys.readouterr().out
    assert (
        "[agentos] materialized codex auth for profile codex-mm from account mm"
        in output
    )
    assert "pong model=" in output
    assert read_codex_auth_info(home / "auth.json").sha256 == active_info.sha256
    verifications = read_jsonl_file(
        environment.agentos_home / "accounts" / "codex" / "verifications.jsonl"
    )
    assert verifications[-1]["artifact_id"] == active_info.sha256
    assert verifications[-1]["source"] == "agent.ping"


def test_agent_ping_records_claude_verified_auth_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    import agentos.claude.account_registry as claude_account_registry

    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    register_claude_account(account="browser-br", email="br@example.com")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles(
        [
            {
                "id": "claude-br",
                "provider": "claude-code",
                "homes": [str(home)],
                "accounts": ["browser-br"],
                "ping": {"prompt": "745", "expected_number": 745},
            }
        ]
    )
    monkeypatch.setattr(
        claude_agent_module,
        "execute_agent_command",
        lambda command, *, run_config: AgentRunResult(exit_code=0, stdout="745"),
    )

    result = _cmd_agent_ping(_ping_args(profile="claude-br", provider="claude-code"))

    assert result == 0
    assert "pong model=" in capsys.readouterr().out
    account_payload = read_json_file(
        environment.agentos_home / "accounts" / "claude-code" / "accounts.json"
    )
    artifact_id = account_payload["accounts"]["browser-br"]["active_artifact_id"]
    verifications = read_jsonl_file(
        environment.agentos_home / "accounts" / "claude-code" / "verifications.jsonl"
    )
    assert verifications[-1]["artifact_id"] == artifact_id
    assert verifications[-1]["source"] == "agent.ping"


def test_agent_run_does_not_mutate_codex_home_without_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    configured_home = tmp_path / "configured-codex"
    override_home = tmp_path / "materialized-codex"
    auth_file = tmp_path / "auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=auth_file, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles(
        [_codex_profile(configured_home, extra_homes=[override_home], account=None)]
    )

    result = _cmd_agent_run(
        _run_args(
            profile="codex-mm",
            home=override_home,
            prompt="hello",
            dry_run=True,
        )
    )

    assert result == 0
    assert "[agentos]" not in capsys.readouterr().out
    status = inspect_codex_account_home(home=override_home)
    assert status["classification"] == "missing"


def test_agent_run_materializes_codex_home_with_explicit_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "configured-codex"
    override_home = tmp_path / "materialized-codex"
    auth_file = tmp_path / "auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=auth_file, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(configured_home, extra_homes=[override_home])])

    result = _cmd_agent_run(
        _run_args(
            profile="codex-mm",
            home=override_home,
            account="mm",
            prompt="hello",
        )
    )

    assert result == 0
    assert (
        "[agentos] materialized codex auth for profile codex-mm from account mm"
        in capsys.readouterr().out
    )
    status = inspect_codex_account_home(home=override_home)
    assert status["classification"] == "matching-active"
    assert status["auth"]["account_id"] == "acc_mm"
    removed_registry_name = "links" + ".json"
    assert not (agentos_home / "accounts" / "codex" / removed_registry_name).exists()


def test_agent_run_dry_run_reports_explicit_account_materialization_without_mutating(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    configured_home = tmp_path / "configured-codex"
    override_home = tmp_path / "materialized-codex"
    auth_file = tmp_path / "auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=auth_file, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(configured_home, extra_homes=[override_home])])

    result = _cmd_agent_run(
        _run_args(
            profile="codex-mm",
            home=override_home,
            account="mm",
            prompt="hello",
            dry_run=True,
        )
    )

    assert result == 0
    assert (
        "[agentos] would materialize codex auth for profile codex-mm from account mm"
        in capsys.readouterr().out
    )
    status = inspect_codex_account_home(home=override_home)
    assert status["classification"] == "missing"


def test_agent_run_materializes_when_explicit_account_differs_from_home_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-br"
    br_auth = tmp_path / "br-auth.json"
    mm_auth = tmp_path / "mm-auth.json"
    write_text_file(br_auth, codex_auth_json(account_id="acc_br"))
    write_text_file(mm_auth, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=br_auth, account="br")
    register_codex_account_from_auth_file(auth_file=mm_auth, account="mm")
    materialize_codex_account_to_home(home=home, account="br")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles(
        [_codex_profile(home, profile_id="codex-br", accounts=["br", "mm"])]
    )

    result = _cmd_agent_run(
        _run_args(
            profile="codex-br",
            account="mm",
            prompt="hello",
            dry_run=True,
        )
    )

    assert result == 0


def test_agent_run_home_current_uses_allowed_current_codex_home_without_materializing_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-main"
    br_auth = tmp_path / "br-auth.json"
    mm_auth = tmp_path / "mm-auth.json"
    write_text_file(br_auth, codex_auth_json(account_id="acc_br"))
    write_text_file(mm_auth, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=br_auth, account="br")
    register_codex_account_from_auth_file(auth_file=mm_auth, account="mm")
    materialize_codex_account_to_home(home=home, account="br")
    br_info = read_codex_auth_info(home / "auth.json")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles(
        [
            _codex_profile(
                home,
                profile_id="codex-main",
                accounts=["mm", "br"],
                account_policy="home-current",
            )
        ]
    )

    result = _cmd_agent_run(
        _run_args(profile="codex-main", prompt="hello", dry_run=True)
    )

    assert result == 0
    assert "[agentos]" not in capsys.readouterr().out
    assert read_codex_auth_info(home / "auth.json").sha256 == br_info.sha256


def test_agent_run_home_current_missing_codex_home_auth_errors_without_materializing_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-main"
    mm_auth = tmp_path / "mm-auth.json"
    write_text_file(mm_auth, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=mm_auth, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles(
        [
            _codex_profile(
                home,
                profile_id="codex-main",
                accounts=["mm"],
                account_policy="home-current",
            )
        ]
    )

    with pytest.raises(CliError, match="current codex home auth is missing"):
        _cmd_agent_run(_run_args(profile="codex-main", prompt="hello", dry_run=True))

    assert inspect_codex_account_home(home=home)["classification"] == "missing"


def test_agent_run_home_current_rejects_current_codex_home_auth_outside_profile_accounts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-main"
    br_auth = tmp_path / "br-auth.json"
    mm_auth = tmp_path / "mm-auth.json"
    write_text_file(br_auth, codex_auth_json(account_id="acc_br"))
    write_text_file(mm_auth, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=br_auth, account="br")
    register_codex_account_from_auth_file(auth_file=mm_auth, account="mm")
    materialize_codex_account_to_home(home=home, account="br")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles(
        [
            _codex_profile(
                home,
                profile_id="codex-main",
                accounts=["mm"],
                account_policy="home-current",
            )
        ]
    )

    with pytest.raises(CliError, match="not allowed by profile codex-main"):
        _cmd_agent_run(_run_args(profile="codex-main", prompt="hello", dry_run=True))


def test_agent_run_home_current_explicit_account_still_materializes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-main"
    br_auth = tmp_path / "br-auth.json"
    mm_auth = tmp_path / "mm-auth.json"
    write_text_file(br_auth, codex_auth_json(account_id="acc_br"))
    write_text_file(mm_auth, codex_auth_json(account_id="acc_mm"))
    register_codex_account_from_auth_file(auth_file=br_auth, account="br")
    register_codex_account_from_auth_file(auth_file=mm_auth, account="mm")
    materialize_codex_account_to_home(home=home, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles(
        [
            _codex_profile(
                home,
                profile_id="codex-main",
                accounts=["mm", "br"],
                account_policy="home-current",
            )
        ]
    )

    result = _cmd_agent_run(
        _run_args(
            profile="codex-main",
            account="br",
            prompt="hello",
            dry_run=True,
        )
    )

    assert result == 0
    assert (
        "[agentos] would materialize codex auth for profile codex-main from account br"
        in capsys.readouterr().out
    )


def _make_stale_profile_home(
    tmp_path: Path,
    *,
    home: Path,
    account: str,
) -> tuple[Path, Path]:
    old_auth = tmp_path / f"{account}-old-auth.json"
    active_auth = tmp_path / f"{account}-active-auth.json"
    write_text_file(
        old_auth,
        codex_auth_json(
            account_id=f"acc_{account}", email=f"{account}-old@example.com"
        ),
    )
    write_text_file(
        active_auth,
        codex_auth_json(
            account_id=f"acc_{account}",
            email=f"{account}-active@example.com",
        ).replace("2026-05-12T17:00:07Z", "2026-05-23T17:00:07Z"),
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account=account)
    materialize_codex_account_to_home(home=home, account=account)
    register_codex_account_from_auth_file(auth_file=active_auth, account=account)
    return old_auth, active_auth


def _provider_configs() -> dict[str, dict[str, object]]:
    return {
        "claude-code": {"cli_command": ["claude"]},
        "codex": {"cli_command": ["/bin/echo"]},
    }


def _codex_profile(
    home: Path,
    *,
    profile_id: str = "codex-mm",
    account: str | None = "mm",
    accounts: list[str] | None = None,
    extra_homes: list[Path] | None = None,
    ping: dict[str, object] | None = None,
    account_policy: str | None = None,
) -> dict[str, object]:
    profile: dict[str, object] = {
        "id": profile_id,
        "provider": "codex",
        "homes": [str(home), *(str(extra_home) for extra_home in extra_homes or [])],
    }
    if accounts is not None:
        profile["accounts"] = accounts
    elif account is not None:
        profile["accounts"] = [account]
    if ping is not None:
        profile["ping"] = ping
    if account_policy is not None:
        profile["account_policy"] = account_policy
    return profile


def _run_args(
    *,
    profile: str,
    prompt: str,
    home: Path | None = None,
    account: str | None = None,
    dry_run: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        provider="codex",
        profile=profile,
        home=str(home) if home is not None else None,
        account=account,
        model=None,
        project=None,
        cwd=None,
        argv=[],
        prompt=prompt,
        non_interactive=False,
        dry_run=dry_run,
    )


def _ping_args(*, profile: str, provider: str = "codex") -> argparse.Namespace:
    return argparse.Namespace(
        provider=provider,
        profile=profile,
        home=None,
        account=None,
        model=None,
        project=None,
        cwd=None,
    )
