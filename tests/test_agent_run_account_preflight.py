from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import agentos.claude.agent as claude_agent_module
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
    write_claude_home,
    write_text_file,
)


def test_agent_run_dry_run_does_not_materialize_stale_codex_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    old_auth, _ = _make_stale_profile_home(tmp_path, home=home, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(home)])
    old_info = read_codex_auth_info(old_auth)

    result = _cmd_agent_run(_run_args(profile="codex-mm", prompt="hello", dry_run=True))

    assert result == 0
    output = capsys.readouterr().out
    # no auto-materialization: only explicit `agent accounts materialize` writes a home
    assert "materialize codex auth" not in output
    assert "/bin/echo" in output
    assert read_codex_auth_info(home / "auth.json").sha256 == old_info.sha256


def test_agent_run_does_not_materialize_stale_codex_home_before_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    old_auth, _ = _make_stale_profile_home(tmp_path, home=home, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(home)])
    old_info = read_codex_auth_info(old_auth)

    result = _cmd_agent_run(_run_args(profile="codex-mm", prompt="hello"))

    assert result == 0
    assert "materialize codex auth" not in capsys.readouterr().out
    # the run uses the home as-is; the stale home auth is unchanged
    assert read_codex_auth_info(home / "auth.json").sha256 == old_info.sha256


def test_agent_run_does_not_materialize_same_account_home_with_explicit_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    old_auth, _ = _make_stale_profile_home(tmp_path, home=home, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(home)])
    old_info = read_codex_auth_info(old_auth)

    result = _cmd_agent_run(_run_args(profile="codex-mm", account="mm", prompt="hello"))

    assert result == 0
    assert "materialize codex auth" not in capsys.readouterr().out
    assert read_codex_auth_info(home / "auth.json").sha256 == old_info.sha256


def test_agent_ping_codex_uses_home_as_is_without_materializing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-mm"
    old_auth, _ = _make_stale_profile_home(tmp_path, home=home, account="mm")
    environment.write_global_config(agent={"providers": _provider_configs()})
    environment.write_profiles([_codex_profile(home, ping={"prompt": "745", "expected_number": 745})])
    old_info = read_codex_auth_info(old_auth)

    result = _cmd_agent_ping(_ping_args(profile="codex-mm"))

    assert result == 0
    output = capsys.readouterr().out
    assert "materialize codex auth" not in output
    assert "pong model=" in output
    # ping ran against the home as-is — the stale home auth was not replaced
    assert read_codex_auth_info(home / "auth.json").sha256 == old_info.sha256


def test_agent_ping_claude_does_not_auto_promote(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # New model: claude ping/run is read-only toward the registry — no automatic
    # post-run promote/verification. (Old auto-promote path removed in 654.)
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
    # no automatic verification/promotion was recorded by the ping
    assert not (
        environment.agentos_home / "accounts" / "claude-code" / "verifications.jsonl"
    ).exists()


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


def test_agent_run_does_not_materialize_codex_home_with_explicit_account(
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
        )
    )

    assert result == 0
    assert "materialize codex auth" not in capsys.readouterr().out
    # the home was never materialized — it stays missing (run used it as-is)
    status = inspect_codex_account_home(home=override_home)
    assert status["classification"] == "missing"


def test_agent_run_dry_run_does_not_materialize_explicit_account(
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
    assert "materialize codex auth" not in capsys.readouterr().out
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






def test_agent_run_home_current_explicit_account_does_not_materialize(
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
    mm_info = read_codex_auth_info(home / "auth.json")
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
    assert "materialize codex auth" not in capsys.readouterr().out
    # the home keeps its current (mm) auth — no materialization to br
    assert read_codex_auth_info(home / "auth.json").sha256 == mm_info.sha256


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
