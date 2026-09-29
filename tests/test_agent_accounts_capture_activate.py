from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import pytest

from tarav.l1.agent.commands.accounts import _cmd_agent_accounts_activate, _cmd_agent_accounts_capture
from tarav.l0.testing import TaravTestEnvironment

UUID = "07de2ad9-c2c5-4c05-8a09-3aa235a30650"


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _auth_json(uuid: str) -> dict[str, object]:
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": uuid}, "email": "x@e.com"})
    return {"tokens": {"access_token": access, "id_token": _jwt({}), "account_id": uuid}}


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    TaravTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from tarav.l0._core.project import tarav_home_dir

    prov = tarav_home_dir() / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {"br": {"identity": {"provider_account_id": UUID},
                            "auth_methods": {"file": {"class": "auth-json"}}}},
    }))


def _home(tmp_path: Path, name: str, uuid: str) -> Path:
    h = tmp_path / name
    h.mkdir()
    (h / "auth.json").write_text(json.dumps(_auth_json(uuid)))
    return h


def test_capture_files_by_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    home = _home(tmp_path, "codex-br", UUID)

    assert _cmd_agent_accounts_capture(argparse.Namespace(
        provider="codex", home=str(home), global_sweep=False, json=False, _agentos_argv=[])) == 0

    from tarav.l1.agent import auth_registry as R
    rec = json.loads(R.captures_path("codex").read_text().splitlines()[-1])
    assert rec["account"] == "br" and rec["method"] == "file"
    assert R.read_artifact("codex", rec["artifact_id"]) is not None


def test_capture_orphan_to_unknown_account(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    home = _home(tmp_path, "stray", "ffffffff-0000-0000-0000-000000000000")

    _cmd_agent_accounts_capture(argparse.Namespace(
        provider="codex", home=str(home), global_sweep=False, json=False, _agentos_argv=[]))

    from tarav.l1.agent import auth_registry as R
    rec = json.loads(R.captures_path("codex").read_text().splitlines()[-1])
    assert rec["account"] == R.UNKNOWN_ACCOUNT  # Unknown.Account bucket
    assert rec["method"] == "auth-json"  # orphan method axis is the auth_class
    assert R.read_artifact("codex", rec["artifact_id"]) is not None


def _profile(home_root: Path, pid: str, homes: list[Path], accounts: list[str]) -> None:
    (home_root / "profiles").mkdir(parents=True, exist_ok=True)
    (home_root / "profiles" / f"{pid}.json").write_text(json.dumps(
        {"id": pid, "provider": "codex", "homes": [str(h) for h in homes], "accounts": accounts}
    ))


def test_capture_global_sweeps_provider_homes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l0._core.project import tarav_home_dir

    known = _home(tmp_path, "codex-br", UUID)
    orphan = _home(tmp_path, "stray", "ffffffff-0000-0000-0000-000000000000")
    _profile(tarav_home_dir(), "codex-main", [known, orphan], ["br/file"])

    rc = _cmd_agent_accounts_capture(argparse.Namespace(
        provider="codex", home=None, global_sweep=True, json=False, _agentos_argv=[]))
    assert rc == 0

    from tarav.l1.agent import auth_registry as R
    accounts = {json.loads(line)["account"]
                for line in R.captures_path("codex").read_text().splitlines()}
    assert accounts == {"br", R.UNKNOWN_ACCOUNT}


def test_capture_global_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l0._core.project import tarav_home_dir

    known = _home(tmp_path, "codex-br", UUID)
    _profile(tarav_home_dir(), "codex-main", [known], ["br/file"])

    rc = _cmd_agent_accounts_capture(argparse.Namespace(
        provider="codex", home=None, global_sweep=True, dry_run=True, json=False, _agentos_argv=[]))
    assert rc == 0

    from tarav.l1.agent import auth_registry as R
    assert not R.captures_path("codex").exists()
    assert "dry-run" in capsys.readouterr().out


def test_capture_single_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    home = _home(tmp_path, "codex-br", UUID)

    rc = _cmd_agent_accounts_capture(argparse.Namespace(
        provider="codex", home=str(home), global_sweep=False, dry_run=True, json=False, _agentos_argv=[]))
    assert rc == 0

    from tarav.l1.agent import auth_registry as R
    assert not R.captures_path("codex").exists()


def test_capture_global_and_home_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l0._core.errors import CliError

    with pytest.raises(CliError):
        _cmd_agent_accounts_capture(argparse.Namespace(
            provider="codex", home="/some/home", global_sweep=True, json=False, _agentos_argv=[]))


def test_capture_single_requires_provider_and_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l0._core.errors import CliError

    with pytest.raises(CliError):
        _cmd_agent_accounts_capture(argparse.Namespace(
            provider=None, home="/some/home", global_sweep=False, json=False, _agentos_argv=[]))


def test_activate_sets_pointer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l1.agent import auth_registry as R
    from tarav.l1.agent.account_status import AccountIdentity
    from tarav.l1.agent.auth_method import AuthData

    artifact_id = R.store_artifact("codex", AuthData(payload=_auth_json(UUID)))
    R.append_capture("codex", account="br", method="file", auth_class="auth-json",
                     auth_ref=AccountIdentity(), ref_id=artifact_id, artifact_id=artifact_id)

    assert _cmd_agent_accounts_activate(argparse.Namespace(
        provider="codex", account="br/file", ref=artifact_id, json=False, _agentos_argv=[])) == 0
    assert R.active_ref("codex", "br", "file") == artifact_id


def test_activate_rejects_missing_artifact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l0._core.errors import CliError

    with pytest.raises(CliError):
        _cmd_agent_accounts_activate(argparse.Namespace(
            provider="codex", account="br/file", ref="deadbeef", json=False, _agentos_argv=[]))
