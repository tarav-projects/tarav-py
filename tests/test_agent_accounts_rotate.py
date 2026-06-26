from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import pytest

from agentos.agent.commands import _cmd_agent_accounts_rotate
from agentos.testing import AgentosTestEnvironment

UUID = "07de2ad9-c2c5-4c05-8a09-3aa235a30650"


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _auth_json(uuid: str, exp: int) -> dict[str, object]:
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": uuid}, "exp": exp})
    return {"tokens": {"access_token": access, "account_id": uuid}}


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from agentos._core.project import agentos_home_dir

    home_root = agentos_home_dir()
    prov = home_root / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {"br": {"identity": {"provider_account_id": UUID},
                            "auth_methods": {"file": {"class": "auth-json"}}}},
    }))
    return home_root


def _home(tmp_path: Path, name: str, exp: int) -> Path:
    h = tmp_path / name
    h.mkdir()
    (h / "auth.json").write_text(json.dumps(_auth_json(UUID, exp)))
    return h


def _profile(home_root: Path, pid: str, homes: list[Path]) -> None:
    (home_root / "profiles").mkdir(parents=True, exist_ok=True)
    (home_root / "profiles" / f"{pid}.json").write_text(json.dumps(
        {"id": pid, "provider": "codex", "homes": [str(h) for h in homes], "accounts": ["br/file"]}
    ))


def _ns(**kw: object) -> argparse.Namespace:
    base = dict(provider="codex", account=None, no_capture=False, dry_run=False,
               json=False, _agentos_argv=[])
    base.update(kw)
    return argparse.Namespace(**base)


def test_rotate_captures_first_then_flips_active(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    fresh_home = _home(tmp_path, "codex-br", exp=2_000_000_000)
    _profile(home_root, "codex-main", [fresh_home])

    # active points at an older artifact that is NOT in any home
    from agentos.agent import auth_registry as R
    from agentos.agent.auth_method import AuthData
    stale = R.store_artifact("codex", AuthData(payload=_auth_json(UUID, exp=1_000_000_000)))
    R.set_active("codex", "br", "file", stale)

    assert _cmd_agent_accounts_rotate(_ns()) == 0
    # capture-first pulled the fresh home into the pool; rotation activated it
    fresh_id = AuthData(payload=_auth_json(UUID, exp=2_000_000_000)).content_id()
    assert R.active_artifact_id("codex", "br", "file") == fresh_id


def test_rotate_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    fresh_home = _home(tmp_path, "codex-br", exp=2_000_000_000)
    _profile(home_root, "codex-main", [fresh_home])

    from agentos.agent import auth_registry as R
    from agentos.agent.auth_method import AuthData
    stale = R.store_artifact("codex", AuthData(payload=_auth_json(UUID, exp=1_000_000_000)))
    R.set_active("codex", "br", "file", stale)

    assert _cmd_agent_accounts_rotate(_ns(dry_run=True)) == 0
    assert R.active_artifact_id("codex", "br", "file") == stale  # unchanged
    assert not R.captures_path("codex").exists()  # capture was dry too


def test_rotate_no_capture_skips_home_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    fresh_home = _home(tmp_path, "codex-br", exp=2_000_000_000)
    _profile(home_root, "codex-main", [fresh_home])

    from agentos.agent import auth_registry as R

    assert _cmd_agent_accounts_rotate(_ns(no_capture=True)) == 0
    # no capture happened → empty pool → nothing written
    assert not R.captures_path("codex").exists()


def test_rotate_account_requires_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.errors import CliError

    with pytest.raises(CliError):
        _cmd_agent_accounts_rotate(_ns(provider=None, account="br/file"))
