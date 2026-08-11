from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from agentos.testing import AgentosTestEnvironment

UUID = "07de2ad9-c2c5-4c05-8a09-3aa235a30650"


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _auth_json(uuid: str) -> dict[str, object]:
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": uuid}, "email": "x@e.com"})
    return {"tokens": {"access_token": access, "id_token": _jwt({}), "account_id": uuid}}


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


def _home(tmp_path: Path, name: str, uuid: str) -> Path:
    h = tmp_path / name
    h.mkdir()
    (h / "auth.json").write_text(json.dumps(_auth_json(uuid)))
    return h


def _profile(home_root: Path, pid: str, homes: list[Path], accounts: list[str]) -> None:
    (home_root / "profiles").mkdir(parents=True, exist_ok=True)
    (home_root / "profiles" / f"{pid}.json").write_text(json.dumps(
        {"id": pid, "provider": "codex", "homes": [str(h) for h in homes], "accounts": accounts}
    ))


def test_capture_home_returns_result_for_known_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    home = _home(tmp_path, "codex-br", UUID)

    from agentos.agent.capture import capture_home

    result = capture_home("codex", home)
    assert result is not None
    assert result.provider == "codex"
    assert result.account == "br" and result.method == "file"
    assert result.is_new is True

    # second capture of identical bytes is not new (idempotent)
    again = capture_home("codex", home)
    assert again is not None and again.is_new is False


def test_capture_home_files_orphan_to_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    home = _home(tmp_path, "stray", "ffffffff-0000-0000-0000-000000000000")

    from agentos.agent.auth_registry import UNKNOWN_ACCOUNT
    from agentos.agent.capture import capture_home

    result = capture_home("codex", home)
    assert result is not None
    assert result.account == UNKNOWN_ACCOUNT and result.method == "auth-json"


def test_capture_home_returns_none_for_empty_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    from agentos.agent.capture import capture_home

    assert capture_home("codex", empty) is None


def test_capture_all_homes_sweeps_profile_homes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    known = _home(tmp_path, "codex-br", UUID)
    orphan = _home(tmp_path, "stray", "ffffffff-0000-0000-0000-000000000000")
    _profile(home_root, "codex-main", [known, orphan], ["br/file"])

    from agentos.agent.auth_registry import UNKNOWN_ACCOUNT
    from agentos.agent.capture import capture_all_homes

    results = capture_all_homes("codex")
    by_account = {r.account: r for r in results}
    assert set(by_account) == {"br", UNKNOWN_ACCOUNT}
    assert all(r.is_new for r in results)

    # idempotent: a second sweep captures nothing new
    again = capture_all_homes("codex")
    assert again and all(not r.is_new for r in again)


def test_capture_home_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    home = _home(tmp_path, "codex-br", UUID)

    from agentos.agent import auth_registry as R
    from agentos.agent.capture import capture_home

    result = capture_home("codex", home, dry_run=True)
    assert result is not None
    assert result.account == "br" and result.method == "file" and result.is_new is True
    # nothing was written: no capture log, no artifact blob
    assert not R.captures_path("codex").exists()
    assert R.read_artifact("codex", result.artifact_id) is None
    # the reported artifact_id still equals the real content id
    from agentos.agent.providers.codex.auth_method import CodexAuthMethod
    assert result.artifact_id == CodexAuthMethod().read_auth_data(home).content_id()


def test_capture_all_homes_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    known = _home(tmp_path, "codex-br", UUID)
    orphan = _home(tmp_path, "stray", "ffffffff-0000-0000-0000-000000000000")
    _profile(home_root, "codex-main", [known, orphan], ["br/file"])

    from agentos.agent import auth_registry as R
    from agentos.agent.capture import capture_all_homes

    results = capture_all_homes("codex", dry_run=True)
    assert {r.account for r in results} == {"br", R.UNKNOWN_ACCOUNT}
    assert all(r.is_new for r in results)
    assert not R.captures_path("codex").exists()


def test_providers_with_auth_methods_lists_only_implemented(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from agentos.agent.auth_method_registry import providers_with_auth_methods

    assert set(providers_with_auth_methods()) == {"codex", "claude-code"}


def test_capture_all_homes_skips_missing_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    known = _home(tmp_path, "codex-br", UUID)
    missing = tmp_path / "does-not-exist"
    _profile(home_root, "codex-main", [known, missing], ["br/file"])

    from agentos.agent.capture import capture_all_homes

    results = capture_all_homes("codex")
    assert len(results) == 1 and results[0].account == "br"
