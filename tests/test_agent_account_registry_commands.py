from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from _helpers import set_fake_agentos_home as _set_fake_agentos_home
from _helpers import write_text_file as _write
from agentos.cli import main


def _jwt(payload: dict[str, object]) -> str:
    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return ".".join([encode({"alg": "none"}), encode(payload), "signature"])


def _auth_json(
    *,
    account_id: str = "acc_123",
    email: str = "person@example.com",
    last_refresh: str = "2026-05-12T17:00:07Z",
    iat: int = 1_776_000_000,
) -> str:
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": {
                "id_token": _jwt({"email": email, "iat": iat}),
                "access_token": _jwt({"iat": iat}),
                "refresh_token": "secret-refresh-token",
                "account_id": account_id,
            },
            "last_refresh": last_refresh,
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _read_registry(path: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        assert isinstance(payload, dict)
        entries.append(payload)
    return entries


def _register_args(auth_file: Path) -> list[str]:
    return [
        "agent",
        "accounts",
        "register",
        "--provider",
        "codex",
        "--account",
        "br",
        "--auth-file",
        str(auth_file),
    ]


def test_agent_accounts_register_uses_auth_file_and_flat_registry(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "named-anything.json"
    target_home = tmp_path / "codex"
    auth_text = _auth_json()
    auth_sha = _sha(auth_text)
    _write(source_auth, auth_text)

    assert main(_register_args(source_auth)) == 0
    register_payload = json.loads(capsys.readouterr().out)
    assert register_payload["auth"]["account_id"] == "acc_123"
    assert register_payload["auth"]["email"] == "person@example.com"
    assert register_payload["registry_appended"] is True
    assert "secret-refresh-token" not in json.dumps(register_payload)

    provider_root = agentos_home / "accounts" / "codex"
    stored_file = provider_root / "files" / f"{auth_sha}.auth.json"
    registry_path = provider_root / "registry.jsonl"
    manifest_path = provider_root / "accounts" / "br" / "manifest.json"
    pointer_path = provider_root / "accounts" / "br" / "auth.json"
    assert stored_file.read_text(encoding="utf-8") == auth_text

    registry_entries = _read_registry(registry_path)
    assert len(registry_entries) == 1
    assert registry_entries[0]["provider"] == "codex"
    assert registry_entries[0]["account"] == "br"
    assert registry_entries[0]["account_id"] == "acc_123"
    assert registry_entries[0]["sha256"] == auth_sha
    assert registry_entries[0]["file"] == f"files/{auth_sha}.auth.json"
    assert "secret-refresh-token" not in json.dumps(registry_entries)

    manifest = _read_json(manifest_path)
    assert manifest["provider"] == "codex"
    assert manifest["account"] == "br"
    assert manifest["account_id"] == "acc_123"
    assert manifest["active_sha256"] == auth_sha
    assert manifest["active_file"] == f"../../files/{auth_sha}.auth.json"
    assert "secret-refresh-token" not in json.dumps(manifest)
    assert pointer_path.is_symlink()
    assert os.readlink(pointer_path) == f"../../files/{auth_sha}.auth.json"
    assert pointer_path.resolve() == stored_file

    assert (
        main(
            [
                "agent",
                "accounts",
                "link",
                "--provider",
                "codex",
                "--account",
                "br",
                "--home",
                str(target_home),
            ]
        )
        == 0
    )
    link_payload = json.loads(capsys.readouterr().out)
    target_auth = target_home / "auth.json"
    assert target_auth.is_file()
    assert not target_auth.is_symlink()
    assert target_auth.read_text(encoding="utf-8") == auth_text
    assert link_payload["copied_auth"]["sha256"] == auth_sha
    assert "secret-refresh-token" not in json.dumps(link_payload)

    assert (
        main(
            [
                "agent",
                "accounts",
                "status",
                "--provider",
                "codex",
                "--home",
                str(target_home),
            ]
        )
        == 0
    )
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["classification"] == "matching-active"
    assert status_payload["auth"]["account_id"] == "acc_123"
    assert status_payload["registry_matches"][0]["sha256"] == auth_sha
    assert status_payload["latest_link_event"]["event_type"] == "agent.accounts.link"

    assert (
        main(
            [
                "stdlib",
                "utils",
                "cmd-logger",
                "query",
                "--event-type",
                "agent.accounts.link",
                "--json",
            ]
        )
        == 0
    )
    log_payload = json.loads(capsys.readouterr().out)
    assert log_payload["count"] == 1
    assert log_payload["events"][0]["payload"]["account"] == "br"
    assert "secret-refresh-token" not in json.dumps(log_payload)


def test_agent_accounts_register_rejects_old_home_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_home = tmp_path / "codex-br"
    _write(source_home / "auth.json", _auth_json())

    with pytest.raises(SystemExit):
        main(
            [
                "agent",
                "accounts",
                "register",
                "--provider",
                "codex",
                "--home",
                str(source_home),
                "--account",
                "br",
            ]
        )


def test_agent_accounts_register_same_hash_is_noop(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "auth.json"
    auth_text = _auth_json(account_id="acc_123")
    _write(source_auth, auth_text)

    assert main(_register_args(source_auth)) == 0
    first_payload = json.loads(capsys.readouterr().out)
    assert first_payload["registry_appended"] is True
    assert main(_register_args(source_auth)) == 0
    second_payload = json.loads(capsys.readouterr().out)
    assert second_payload["registry_appended"] is False

    registry_entries = _read_registry(agentos_home / "accounts" / "codex" / "registry.jsonl")
    assert len(registry_entries) == 1
    assert registry_entries[0]["sha256"] == _sha(auth_text)


def test_agent_accounts_register_accepts_manual_email_metadata(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "auth.json"
    _write(source_auth, '{"tokens":{"account_id":"acc_123"}}\n')

    assert main([*_register_args(source_auth), "--email", "manual@example.com"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auth"]["email"] == "manual@example.com"

    manifest = _read_json(agentos_home / "accounts" / "codex" / "accounts" / "br" / "manifest.json")
    assert manifest["email"] == "manual@example.com"
    registry_entries = _read_registry(agentos_home / "accounts" / "codex" / "registry.jsonl")
    assert registry_entries[0]["email"] == "manual@example.com"


def test_agent_accounts_register_new_hash_updates_manifest_and_pointer(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    first_auth = tmp_path / "first.json"
    second_auth = tmp_path / "second.json"
    first_text = _auth_json(last_refresh="2026-05-01T00:00:00Z", iat=1_775_000_000)
    second_text = _auth_json(last_refresh="2026-05-12T00:00:00Z", iat=1_776_000_000)
    _write(first_auth, first_text)
    _write(second_auth, second_text)

    assert main(_register_args(first_auth)) == 0
    capsys.readouterr()
    assert main(_register_args(second_auth)) == 0
    capsys.readouterr()

    provider_root = agentos_home / "accounts" / "codex"
    registry_entries = _read_registry(provider_root / "registry.jsonl")
    assert [entry["sha256"] for entry in registry_entries] == [_sha(first_text), _sha(second_text)]
    manifest = _read_json(provider_root / "accounts" / "br" / "manifest.json")
    assert manifest["active_sha256"] == _sha(second_text)
    assert os.readlink(provider_root / "accounts" / "br" / "auth.json") == (
        f"../../files/{_sha(second_text)}.auth.json"
    )
    assert (provider_root / "files" / f"{_sha(first_text)}.auth.json").read_text(encoding="utf-8") == first_text
    assert (provider_root / "files" / f"{_sha(second_text)}.auth.json").read_text(encoding="utf-8") == second_text


def test_agent_accounts_register_refuses_account_id_mismatch_without_touching_current(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    first_auth = tmp_path / "first.json"
    second_auth = tmp_path / "second.json"
    first_text = _auth_json(account_id="acc_123")
    second_text = _auth_json(account_id="acc_999")
    _write(first_auth, first_text)
    _write(second_auth, second_text)

    assert main(_register_args(first_auth)) == 0
    capsys.readouterr()
    assert main(_register_args(second_auth)) == 1
    assert "is already registered for account_id acc_123" in capsys.readouterr().err

    provider_root = agentos_home / "accounts" / "codex"
    manifest = _read_json(provider_root / "accounts" / "br" / "manifest.json")
    assert manifest["active_sha256"] == _sha(first_text)
    assert os.readlink(provider_root / "accounts" / "br" / "auth.json") == (
        f"../../files/{_sha(first_text)}.auth.json"
    )
    registry_entries = _read_registry(provider_root / "registry.jsonl")
    assert len(registry_entries) == 1
    assert registry_entries[0]["sha256"] == _sha(first_text)
    assert not (provider_root / "files" / f"{_sha(second_text)}.auth.json").exists()


def test_agent_accounts_register_preserves_existing_regular_account_pointer(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    provider_root = agentos_home / "accounts" / "codex"
    account_dir = provider_root / "accounts" / "br"
    existing_text = _auth_json(last_refresh="2026-05-01T00:00:00Z", iat=1_775_000_000)
    new_text = _auth_json(last_refresh="2026-05-12T00:00:00Z", iat=1_776_000_000)
    _write(account_dir / "auth.json", existing_text)
    _write(tmp_path / "new.json", new_text)

    assert main(_register_args(tmp_path / "new.json")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["preserved_previous_pointer"]["sha256"] == _sha(existing_text)

    assert (provider_root / "files" / f"{_sha(existing_text)}.auth.json").read_text(encoding="utf-8") == existing_text
    assert (provider_root / "files" / f"{_sha(new_text)}.auth.json").read_text(encoding="utf-8") == new_text
    assert (account_dir / "auth.json").is_symlink()
    assert os.readlink(account_dir / "auth.json") == f"../../files/{_sha(new_text)}.auth.json"
    registry_entries = _read_registry(provider_root / "registry.jsonl")
    assert {entry["sha256"] for entry in registry_entries} == {_sha(existing_text), _sha(new_text)}


def test_agent_accounts_link_registers_same_account_auth_before_copy(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    old_auth = _auth_json(last_refresh="2026-05-01T00:00:00Z", iat=1_775_000_000)
    refreshed_auth = _auth_json(last_refresh="2026-05-12T00:00:00Z", iat=1_776_000_000)
    _write(source_auth, old_auth)
    _write(target_home / "auth.json", refreshed_auth)

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "agent",
                "accounts",
                "link",
                "--provider",
                "codex",
                "--account",
                "br",
                "--home",
                str(target_home),
            ]
        )
        == 0
    )
    link_payload = json.loads(capsys.readouterr().out)
    assert link_payload["copied_auth"]["sha256"] == _sha(refreshed_auth)
    assert (target_home / "auth.json").read_text(encoding="utf-8") == refreshed_auth

    provider_root = agentos_home / "accounts" / "codex"
    registry_entries = _read_registry(provider_root / "registry.jsonl")
    assert {entry["sha256"] for entry in registry_entries} == {_sha(old_auth), _sha(refreshed_auth)}
    manifest = _read_json(provider_root / "accounts" / "br" / "manifest.json")
    assert manifest["active_sha256"] == _sha(refreshed_auth)


def test_agent_accounts_link_refuses_different_account_and_logs_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    target_auth = _auth_json(account_id="acc_999")
    _write(source_auth, _auth_json(account_id="acc_123"))
    _write(target_home / "auth.json", target_auth)

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "agent",
                "accounts",
                "link",
                "--provider",
                "codex",
                "--account",
                "br",
                "--home",
                str(target_home),
            ]
        )
        == 1
    )
    assert "refusing to replace codex auth for a different account" in capsys.readouterr().err
    assert (target_home / "auth.json").read_text(encoding="utf-8") == target_auth

    assert (
        main(
            [
                "stdlib",
                "utils",
                "cmd-logger",
                "query",
                "--event-type",
                "agent.accounts.link",
                "--json",
            ]
        )
        == 0
    )
    log_payload = json.loads(capsys.readouterr().out)
    assert log_payload["count"] == 1
    assert log_payload["events"][0]["status"] == "error"
    assert log_payload["events"][0]["payload"]["previous_home_account_id"] == "acc_999"


def test_agent_accounts_link_refuses_broken_current_auth_without_deleting_it(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    broken_auth = "{not-json\n"
    _write(source_auth, _auth_json(account_id="acc_123"))
    _write(target_home / "auth.json", broken_auth)

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "agent",
                "accounts",
                "link",
                "--provider",
                "codex",
                "--account",
                "br",
                "--home",
                str(target_home),
            ]
        )
        == 1
    )
    assert "invalid codex auth JSON" in capsys.readouterr().err
    assert (target_home / "auth.json").read_text(encoding="utf-8") == broken_auth

    assert (
        main(
            [
                "agent",
                "accounts",
                "status",
                "--provider",
                "codex",
                "--home",
                str(target_home),
            ]
        )
        == 0
    )
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["classification"] == "broken"


def test_agent_accounts_status_reports_known_account_new_hash(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    _write(source_auth, _auth_json(last_refresh="2026-05-01T00:00:00Z", iat=1_775_000_000))
    _write(target_home / "auth.json", _auth_json(last_refresh="2026-05-12T00:00:00Z", iat=1_776_000_000))

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "agent",
                "accounts",
                "status",
                "--provider",
                "codex",
                "--home",
                str(target_home),
            ]
        )
        == 0
    )
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["classification"] == "known-account-new-hash"
    assert status_payload["auth"]["account_id"] == "acc_123"
    assert len(status_payload["account_registry_matches"]) == 1
