from __future__ import annotations

from pathlib import Path

from tarav.testing import TaravTestEnvironment
from tarav.cli.cli import main
from _helpers import captured_json


def test_init_project_storage_dirs_exclude_legacy_tapes(
    tmp_path: Path,
    capsys,
) -> None:
    assert main(["init", "--project", str(tmp_path)]) == 0
    payload = captured_json(capsys)

    assert sorted(payload["dirs"]) == ["indexes", "state", "tmp"]
    assert not (tmp_path / ".tarav" / "tapes").exists()


def test_init_global_storage_dirs_exclude_legacy_tapes(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home_dir = environment.tarav_home

    assert main(["init", "--scope", "global"]) == 0
    payload = captured_json(capsys)

    assert sorted(payload["dirs"]) == ["cache", "indexes", "tmp"]
    assert not (home_dir / "tapes").exists()
