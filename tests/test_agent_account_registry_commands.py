from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

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


def test_agent_accounts_register_link_status_for_codex(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_home = tmp_path / "codex-br"
    target_home = tmp_path / "codex"
    auth_text = _auth_json()
    _write(source_home / "auth.json", auth_text)

    assert (
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
        == 0
    )
    register_payload = json.loads(capsys.readouterr().out)
    assert register_payload["registry_key"] == "codex.br"
    assert register_payload["auth"]["account_id"] == "acc_123"
    assert register_payload["auth"]["email"] == "person@example.com"

    config = _read_json(agentos_home / "config.json")
    account_registry = config["agent"]["account_registry"]
    assert account_registry["codex.br"]["provider"] == "codex"
    assert account_registry["codex.br"]["account"] == "br"
    assert account_registry["codex.br"]["account_id"] == "acc_123"
    assert account_registry["codex.br"]["email"] == "person@example.com"
    assert "secret-refresh-token" not in json.dumps(config)

    manifest = _read_json(agentos_home / "accounts" / "codex" / "br" / "manifest.json")
    snapshots = manifest["snapshots"]
    assert len(snapshots) == 1
    assert snapshots[0]["sha256"] == _sha(auth_text)
    snapshot_path = Path(snapshots[0]["path"])
    assert snapshot_path.is_file()
    assert snapshot_path.read_text(encoding="utf-8") == auth_text
    assert "secret-refresh-token" not in json.dumps(manifest)

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
    assert link_payload["copied_auth"]["sha256"] == _sha(auth_text)

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
    assert status_payload["classification"] == "registered"
    assert status_payload["auth"]["account_id"] == "acc_123"
    assert status_payload["registered_snapshot"]["sha256"] == _sha(auth_text)
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


def test_agent_accounts_link_registers_same_account_drift_before_copy(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_home = tmp_path / "codex-br"
    target_home = tmp_path / "codex"
    old_auth = _auth_json(last_refresh="2026-05-01T00:00:00Z", iat=1_775_000_000)
    refreshed_auth = _auth_json(last_refresh="2026-05-12T00:00:00Z", iat=1_776_000_000)
    _write(source_home / "auth.json", old_auth)
    _write(target_home / "auth.json", refreshed_auth)

    assert (
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
        == 0
    )
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
    assert target_home.joinpath("auth.json").read_text(encoding="utf-8") == refreshed_auth

    manifest = _read_json(agentos_home / "accounts" / "codex" / "br" / "manifest.json")
    assert {snapshot["sha256"] for snapshot in manifest["snapshots"]} == {
        _sha(old_auth),
        _sha(refreshed_auth),
    }
    assert manifest["selected_sha256"] == _sha(refreshed_auth)


def test_agent_accounts_link_refuses_different_account_and_logs_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_home = tmp_path / "codex-br"
    target_home = tmp_path / "codex"
    _write(source_home / "auth.json", _auth_json(account_id="acc_123"))
    _write(target_home / "auth.json", _auth_json(account_id="acc_999"))

    assert (
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
        == 0
    )
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
