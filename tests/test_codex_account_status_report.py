from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from agentos.testing import AgentosTestEnvironment


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _auth_json(uuid: str, email: str) -> dict[str, object]:
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": uuid}, "email": email})
    return {"tokens": {"access_token": access, "id_token": _jwt({}), "account_id": uuid},
            "last_refresh": "2026-01-01T00:00:00Z"}


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from agentos._core.project import agentos_home_dir

    return agentos_home_dir()


def _home(root: Path, name: str, *, uuid: str) -> Path:
    home = root / name
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_text(json.dumps(_auth_json(uuid, f"{name}@e.com")))
    return home


def _settings(home_root: Path, *, account: str, uuid: str) -> None:
    prov = home_root / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {account: {"identity": {"provider_account_id": uuid},
                               "auth_methods": {"file": {"class": "auth-json"}}}},
    }))


def _profile(home_root: Path, pid: str, homes: list[Path], accounts: list[str]) -> None:
    (home_root / "profiles").mkdir(parents=True, exist_ok=True)
    (home_root / "profiles" / f"{pid}.json").write_text(json.dumps(
        {"id": pid, "provider": "codex", "homes": [str(h) for h in homes], "accounts": accounts}))


def test_codex_status_aligned_and_unlisted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home_root = _env(monkeypatch, tmp_path)
    UUID = "07de2ad9-c2c5-4c05-8a09-3aa235a30650"

    aligned = _home(tmp_path / "homes", "codex-br", uuid=UUID)
    foreign = _home(tmp_path / "homes", "codex-foreign", uuid="ffffffff-0000-0000-0000-000000000000")

    _settings(home_root, account="br", uuid=UUID)
    _profile(home_root, "codex-br", [aligned], ["br/file"])
    _profile(home_root, "codex-x", [foreign], ["br/file"])

    # capture + activate the aligned home's auth.json
    from agentos.agent import auth_registry as R
    from agentos.agent.providers.codex.auth_method import CodexAuthMethod

    auth = CodexAuthMethod().read_auth_data(aligned)
    artifact_id = R.store_artifact("codex", auth)
    R.set_active("codex", "br", "file", artifact_id)

    from agentos.agent.account_status_report import build_status_report

    by_home = {i["home"]: i for i in build_status_report("codex")["homes"]}
    assert by_home[str(aligned.resolve())]["status"] == "aligned"
    assert by_home[str(aligned.resolve())]["account"] == "br"
    assert by_home[str(foreign.resolve())]["status"] == "error:unlisted-account"
