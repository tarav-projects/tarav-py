from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import pytest

from agentos.agent.commands import _cmd_agent_accounts_materialize
from agentos.testing import AgentosTestEnvironment


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _auth_json(uuid: str, *, token: str) -> dict[str, object]:
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": uuid}, "email": "jp@e.com"})
    return {"tokens": {"access_token": access, "id_token": _jwt({}), "account_id": uuid},
            "marker": token, "last_refresh": "2026-06-23T00:00:00Z"}


UUID = "3b74c6d3-b4a8-45ea-9d5b-852bdbd92899"


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)


def _settings() -> None:
    from agentos._core.project import agentos_home_dir

    prov = agentos_home_dir() / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {"jp": {"identity": {"provider_account_id": UUID},
                            "auth_methods": {"file": {"class": "auth-json"}}}},
    }))


def _args(**kw: object) -> argparse.Namespace:
    base = dict(provider="codex", account="jp/file", home=None,
               check=False, force=False, json=False, _agentos_argv=[])
    base.update(kw)
    return argparse.Namespace(**base)


def test_codex_materialize_writes_auth_json_and_aligns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    _settings()
    from agentos.agent import auth_registry as R
    from agentos.agent.auth_method import AuthData
    from agentos.codex.auth_method import CodexAuthMethod

    active = AuthData(payload=_auth_json(UUID, token="ACTIVE"))
    active_id = R.store_artifact("codex", active)
    R.set_active("codex", "jp", "file", active_id)

    home = tmp_path / "codex-jp"  # empty home (no auth.json)

    assert _cmd_agent_accounts_materialize(_args(home=str(home))) == 0
    assert (home / "auth.json").is_file()
    back = CodexAuthMethod().read_auth_data(home)
    assert back is not None and back.content_id() == active_id


def test_codex_materialize_captures_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    _settings()
    from agentos.agent import auth_registry as R
    from agentos.agent.auth_method import AuthData
    from agentos.codex.auth_method import CodexAuthMethod

    active_id = R.store_artifact("codex", AuthData(payload=_auth_json(UUID, token="ACTIVE")))
    R.set_active("codex", "jp", "file", active_id)

    home = tmp_path / "codex-jp"
    home.mkdir()
    (home / "auth.json").write_text(json.dumps(_auth_json(UUID, token="OLD")))  # home holds an older snapshot
    old_id = CodexAuthMethod().read_auth_data(home).content_id()

    _cmd_agent_accounts_materialize(_args(home=str(home)))

    assert old_id != active_id
    assert old_id in R.captures_path("codex").read_text()  # prior home credential archived first


def test_codex_materialize_check_is_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    _settings()
    from agentos.agent import auth_registry as R
    from agentos.agent.auth_method import AuthData

    active_id = R.store_artifact("codex", AuthData(payload=_auth_json(UUID, token="ACTIVE")))
    R.set_active("codex", "jp", "file", active_id)

    home = tmp_path / "codex-jp"
    assert _cmd_agent_accounts_materialize(_args(home=str(home), check=True)) == 0
    assert not (home / "auth.json").exists()  # nothing written under --check
