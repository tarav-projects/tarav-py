from __future__ import annotations

from pathlib import Path

import pytest

import agentos.codex.account_reconcile as codex_account_reconcile
from agentos.agent.account_registry import append_verification
from agentos.agent.account_status import AgentAccountContext
from agentos.agent.primitives import AgentPingConfig
from agentos.agent.run_runtime import AgentRunResult
from agentos.codex.account_registry import (
    inspect_codex_account_home,
    read_codex_auth_info,
    register_codex_account_from_auth_file,
    link_codex_account_to_home,
    promote_verified_codex_auth_from_home,
)
from agentos.codex.account_reconcile import (
    discover_codex_reconcile_homes,
    reconcile_codex_accounts,
)
from agentos.codex.agent import CodexAgent
from agentos.testing import AgentosTestEnvironment
import agentos.codex.account_status as codex_account_status

from _helpers import (
    codex_auth_json,
    read_json_file,
    read_jsonl_file,
    write_text_file,
)


def test_codex_reconcile_registers_fresh_known_home_without_activating(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "codex-br"
    system_home = agentos_home / "agent" / "homes" / "codex" / "br"
    old_auth = tmp_path / "old-auth.json"
    write_text_file(
        old_auth, codex_auth_json(account_id="acc_br", email="old@example.com")
    )
    write_text_file(
        configured_home / "auth.json",
        _newer_codex_auth_json(account_id="acc_br", email="fresh@example.com"),
    )
    environment.write_profiles(
        [{"id": "codex-br", "provider": "codex", "homes": [str(configured_home)]}]
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account="br")
    link_codex_account_to_home(home=system_home, account="br")
    fresh_info = read_codex_auth_info(configured_home / "auth.json")

    payload = reconcile_codex_accounts(start_path=tmp_path)

    actions = payload["actions"]
    assert isinstance(actions, list)
    assert {action["kind"] for action in actions if isinstance(action, dict)} == {
        "registered_artifact",
    }
    account_payload = read_json_file(
        agentos_home / "accounts" / "codex" / "accounts.json"
    )
    assert account_payload["accounts"]["br"]["active_artifact_id"] != fresh_info.sha256
    artifacts = read_jsonl_file(agentos_home / "accounts" / "codex" / "artifacts.jsonl")
    assert {artifact["artifact_id"] for artifact in artifacts} >= {fresh_info.sha256}
    system_status = inspect_codex_account_home(home=system_home)
    assert system_status["classification"] == "matching-active"
    assert system_status["auth"]["artifact_id"] != fresh_info.sha256


def test_codex_reconcile_warns_and_skips_unknown_account_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "codex-unknown"
    write_text_file(
        configured_home / "auth.json", codex_auth_json(account_id="acc_unknown")
    )
    environment.write_profiles(
        [{"id": "codex-unknown", "provider": "codex", "homes": [str(configured_home)]}]
    )

    payload = reconcile_codex_accounts(start_path=tmp_path)

    assert payload["action_count"] == 0
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert [warning["kind"] for warning in warnings if isinstance(warning, dict)] == [
        "unknown_account_auth"
    ]
    assert not (agentos_home / "accounts" / "codex" / "artifacts.jsonl").exists()


def test_codex_reconcile_does_not_activate_older_stale_system_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    system_home = agentos_home / "agent" / "homes" / "codex" / "br"
    active_auth = tmp_path / "active-auth.json"
    stale_auth = tmp_path / "stale-auth.json"
    write_text_file(
        active_auth,
        _newer_codex_auth_json(account_id="acc_br", email="active@example.com"),
    )
    write_text_file(
        stale_auth, codex_auth_json(account_id="acc_br", email="stale@example.com")
    )
    register_codex_account_from_auth_file(auth_file=active_auth, account="br")
    link_codex_account_to_home(home=system_home, account="br")
    write_text_file(system_home / "auth.json", stale_auth.read_text(encoding="utf-8"))
    active_info = read_codex_auth_info(active_auth)

    payload = reconcile_codex_accounts(start_path=tmp_path)

    account_payload = read_json_file(
        agentos_home / "accounts" / "codex" / "accounts.json"
    )
    assert account_payload["accounts"]["br"]["active_artifact_id"] == active_info.sha256
    actions = payload["actions"]
    assert isinstance(actions, list)
    registered = [
        action
        for action in actions
        if isinstance(action, dict) and action["kind"] == "registered_artifact"
    ]
    assert registered[0]["detail"]["activated"] is False
    system_status = inspect_codex_account_home(home=system_home)
    assert system_status["auth"]["artifact_id"] != active_info.sha256


def test_codex_reconcile_check_does_not_mutate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "codex-br"
    old_auth = tmp_path / "old-auth.json"
    write_text_file(
        old_auth, codex_auth_json(account_id="acc_br", email="old@example.com")
    )
    write_text_file(
        configured_home / "auth.json",
        _newer_codex_auth_json(account_id="acc_br", email="fresh@example.com"),
    )
    environment.write_profiles(
        [{"id": "codex-br", "provider": "codex", "homes": [str(configured_home)]}]
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account="br")
    old_info = read_codex_auth_info(old_auth)

    payload = reconcile_codex_accounts(start_path=tmp_path, check=True)

    assert payload["check"] is True
    assert [action["kind"] for action in payload["actions"]] == ["would_register_artifact"]
    account_payload = read_json_file(
        agentos_home / "accounts" / "codex" / "accounts.json"
    )
    assert account_payload["accounts"]["br"]["active_artifact_id"] == old_info.sha256


def test_codex_verified_promotion_records_evidence_and_active_pointer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-br"
    auth_file = home / "auth.json"
    write_text_file(auth_file, codex_auth_json(account_id="acc_br", email="br@example.com"))
    register_codex_account_from_auth_file(
        auth_file=auth_file,
        account="br",
        register_only=True,
    )

    payload = promote_verified_codex_auth_from_home(
        home=home,
        account="br",
        source="agent.ping",
    )

    account_payload = read_json_file(
        environment.agentos_home / "accounts" / "codex" / "accounts.json"
    )
    account = account_payload["accounts"]["br"]
    artifact_id = payload["artifact_id"]
    assert account["active_artifact_id"] == artifact_id
    assert account["last_verified_source"] == "agent.ping"
    verifications = read_jsonl_file(
        environment.agentos_home / "accounts" / "codex" / "verifications.jsonl"
    )
    assert verifications[-1]["account"] == "br"
    assert verifications[-1]["artifact_id"] == artifact_id
    assert verifications[-1]["auth_kind"] == "auth-json"
    assert verifications[-1]["source"] == "agent.ping"
    assert "tokens" not in str(verifications[-1])


def test_codex_reconcile_activates_verified_artifact_and_syncs_stale_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "codex-br"
    system_home = agentos_home / "agent" / "homes" / "codex" / "br"
    old_auth = tmp_path / "old-auth.json"
    write_text_file(old_auth, codex_auth_json(account_id="acc_br", email="old@example.com"))
    write_text_file(
        configured_home / "auth.json",
        _newer_codex_auth_json(account_id="acc_br", email="fresh@example.com"),
    )
    environment.write_profiles(
        [{"id": "codex-br", "provider": "codex", "homes": [str(configured_home)]}]
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account="br")
    link_codex_account_to_home(home=system_home, account="br")
    registered = register_codex_account_from_auth_file(
        auth_file=configured_home / "auth.json",
        account="br",
        register_only=True,
    )
    verified_artifact_id = registered["auth"]["artifact_id"]
    append_verification(
        "codex",
        {
            "account": "br",
            "artifact_id": verified_artifact_id,
            "auth_kind": "auth-json",
            "home": str(configured_home),
            "source": "agent.ping",
            "verified_at": "2026-06-09T00:00:00Z",
        },
    )

    payload = reconcile_codex_accounts(start_path=tmp_path)

    assert [action["kind"] for action in payload["actions"]] == [
        "activated_verified_artifact",
        "synced_home",
    ]
    account_payload = read_json_file(
        agentos_home / "accounts" / "codex" / "accounts.json"
    )
    assert account_payload["accounts"]["br"]["active_artifact_id"] == verified_artifact_id
    system_status = inspect_codex_account_home(home=system_home)
    assert system_status["classification"] == "matching-active"
    assert system_status["auth"]["artifact_id"] == verified_artifact_id


def test_codex_reconcile_ping_verifies_successful_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-br"
    write_text_file(home / "auth.json", codex_auth_json(account_id="acc_br", email="br@example.com"))
    environment.write_profiles(
        [{"id": "codex-br", "provider": "codex", "homes": [str(home)], "accounts": ["br"]}]
    )
    register_codex_account_from_auth_file(
        auth_file=home / "auth.json",
        account="br",
        register_only=True,
    )
    monkeypatch.setattr(
        codex_account_reconcile,
        "_build_registered_account_agent",
        lambda **kwargs: _FakePingAgent(home=Path(kwargs["home"]), stdout="745"),
    )

    payload = reconcile_codex_accounts(start_path=tmp_path, ping=True)

    assert [action["kind"] for action in payload["actions"]] == [
        "verified_artifact",
        "synced_home",
    ]
    account_payload = read_json_file(
        environment.agentos_home / "accounts" / "codex" / "accounts.json"
    )
    artifact_id = read_codex_auth_info(home / "auth.json").sha256
    assert account_payload["accounts"]["br"]["active_artifact_id"] == artifact_id
    verifications = read_jsonl_file(
        environment.agentos_home / "accounts" / "codex" / "verifications.jsonl"
    )
    assert verifications[-1]["source"] == "accounts.reconcile.ping"


def test_codex_reconcile_check_ping_does_not_run_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-br"
    write_text_file(home / "auth.json", codex_auth_json(account_id="acc_br", email="br@example.com"))
    environment.write_profiles(
        [{"id": "codex-br", "provider": "codex", "homes": [str(home)], "accounts": ["br"]}]
    )
    register_codex_account_from_auth_file(
        auth_file=home / "auth.json",
        account="br",
        register_only=True,
    )

    def fail_build_registered_account_agent(**kwargs):
        raise AssertionError("check ping must not build a live agent")

    monkeypatch.setattr(
        codex_account_reconcile,
        "_build_registered_account_agent",
        fail_build_registered_account_agent,
    )

    payload = reconcile_codex_accounts(start_path=tmp_path, ping=True, check=True)

    assert [action["kind"] for action in payload["actions"]] == ["would_ping"]
    assert not (
        environment.agentos_home / "accounts" / "codex" / "verifications.jsonl"
    ).exists()


def test_codex_reconcile_discovers_only_known_homes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "configured-codex"
    old_auth = tmp_path / "auth.json"
    write_text_file(old_auth, codex_auth_json(account_id="acc_br"))
    environment.write_profiles(
        [{"id": "codex-br", "provider": "codex", "homes": [str(configured_home)]}]
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account="br")

    homes = discover_codex_reconcile_homes(start_path=tmp_path)

    discovered = {home["home"] for home in homes}
    assert discovered == {
        str(configured_home.resolve()),
        str((agentos_home / "agent" / "homes" / "codex" / "br").resolve()),
    }


def test_codex_account_status_runs_reconciliation_before_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "codex-br"
    system_home = agentos_home / "agent" / "homes" / "codex" / "br"
    old_auth = tmp_path / "old-auth.json"
    write_text_file(
        old_auth, codex_auth_json(account_id="acc_br", email="old@example.com")
    )
    write_text_file(
        configured_home / "auth.json",
        _newer_codex_auth_json(account_id="acc_br", email="fresh@example.com"),
    )
    environment.write_profiles(
        [{"id": "codex-br", "provider": "codex", "homes": [str(configured_home)]}]
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account="br")
    link_codex_account_to_home(home=system_home, account="br")
    system_info = read_codex_auth_info(system_home / "auth.json")

    monkeypatch.setattr(
        codex_account_status,
        "_account_usage_app_server",
        lambda agent: (
            (
                codex_account_status.AccountLimit(
                    limit_class="usage",
                    limit_id="test",
                    limit_name="Test",
                    limit_label="Test",
                ),
            ),
            (),
            {},
            {},
            {"status": "fresh", "source": codex_account_status.CODEX_APP_SERVER_USAGE_SOURCE},
        ),
    )

    status = CodexAgent(
        home=system_home,
        account=AgentAccountContext(provider="codex", account="br"),
    ).account_status(record_usage=False)

    assert status.check_status == "ok"
    assert status.raw["home_status"]["auth"]["artifact_id"] == system_info.sha256
    reconciliation = status.raw["reconciliation"]
    assert isinstance(reconciliation, dict)
    assert reconciliation["action_count"] >= 1
    auth_record = status.raw["auth_artifact_record"]
    assert isinstance(auth_record, dict)
    assert auth_record["status"] == "ok"
    assert auth_record["artifact_id"] == system_info.sha256


def _newer_codex_auth_json(*, account_id: str, email: str) -> str:
    return codex_auth_json(account_id=account_id, email=email).replace(
        "2026-05-12T17:00:07Z",
        "2026-05-23T17:00:07Z",
    )


class _FakePingAgent:
    provider = "codex"
    profile_id = "codex-br"
    account = AgentAccountContext(provider="codex", account="br")
    ping = AgentPingConfig(expected_number=745)

    def __init__(self, *, home: Path, stdout: str, exit_code: int = 0) -> None:
        self.home = home
        self.stdout = stdout
        self.exit_code = exit_code

    def run(self, command_config, run_config) -> AgentRunResult:
        return AgentRunResult(exit_code=self.exit_code, stdout=self.stdout)
