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


def _auth_json(uuid: str, marker: str = "") -> dict[str, object]:
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": uuid}, "email": "x@e.com"})
    tokens: dict[str, object] = {"access_token": access, "id_token": _jwt({}), "account_id": uuid}
    if marker:
        tokens["marker"] = marker
    return {"tokens": tokens}


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from agentos._core.project import agentos_home_dir

    prov = agentos_home_dir() / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {"br": {"identity": {"provider_account_id": UUID},
                            "auth_methods": {"file": {"class": "auth-json"}}}},
    }))


def _home(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    h = tmp_path / name
    h.mkdir()
    (h / "auth.json").write_text(json.dumps(payload))
    return h


def _set_active(payload: dict[str, object]) -> str:
    from agentos.agent import auth_registry as R
    from agentos.agent.auth_method import AuthData

    ref = R.store_artifact("codex", AuthData(payload=payload))
    R.set_active("codex", "br", "file", ref)
    return ref


def test_materialize_account_writes_stale_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.materialization import materialize_account

    active_payload = _auth_json(UUID, marker="ACTIVE")
    active_ref = _set_active(active_payload)
    home = _home(tmp_path, "stale", _auth_json(UUID, marker="OLD"))

    result = materialize_account("codex", "br", "file", home, check=False)

    assert result.status == "materialized"
    assert result.active_ref == active_ref
    assert json.loads((home / "auth.json").read_text()) == active_payload


def test_materialize_account_aligned_home_is_not_rewritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.materialization import materialize_account

    active_payload = _auth_json(UUID, marker="ACTIVE")
    _set_active(active_payload)
    home = _home(tmp_path, "aligned", active_payload)  # already holds the active ref

    result = materialize_account("codex", "br", "file", home, check=False)

    assert result.status == "aligned"
    assert json.loads((home / "auth.json").read_text()) == active_payload


def _profile(home_root: Path, pid: str, homes: list[Path], accounts: list[str]) -> None:
    (home_root / "profiles").mkdir(parents=True, exist_ok=True)
    (home_root / "profiles" / f"{pid}.json").write_text(json.dumps(
        {"id": pid, "provider": "codex", "homes": [str(h) for h in homes], "accounts": accounts}
    ))


def test_materialize_all_reconciles_stale_skips_aligned_and_orphan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.project import agentos_home_dir
    from agentos.agent.materialization import materialize_all

    active_payload = _auth_json(UUID, marker="ACTIVE")
    _set_active(active_payload)

    stale = _home(tmp_path, "stale", _auth_json(UUID, marker="OLD"))
    aligned = _home(tmp_path, "aligned", active_payload)
    orphan = _home(tmp_path, "orphan", _auth_json("ffffffff-0000-0000-0000-000000000000"))
    orphan_before = (orphan / "auth.json").read_text()
    _profile(agentos_home_dir(), "codex-main", [stale, aligned, orphan], ["br/file"])

    results = {r.home: r.status for r in materialize_all("codex", check=False)}

    assert results[stale.resolve()] == "materialized"
    assert results[aligned.resolve()] == "aligned"
    assert results[orphan.resolve()] == "skipped"
    # only the stale home was rewritten
    assert json.loads((stale / "auth.json").read_text()) == active_payload
    assert json.loads((aligned / "auth.json").read_text()) == active_payload
    assert (orphan / "auth.json").read_text() == orphan_before
