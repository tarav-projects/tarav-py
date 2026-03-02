from __future__ import annotations

from pathlib import Path

from agentos.cli import main


def test_tmp_folder_new_returns_path_without_creating_directory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["utils", "tmp-folder", "new"]) == 0
    out = capsys.readouterr().out.strip()

    generated_path = Path(out)
    expected_parent = (tmp_path / ".agentos" / "tmp").resolve()
    assert generated_path.is_absolute()
    assert generated_path.parent == expected_parent
    assert not generated_path.exists()
    assert expected_parent.is_dir()


def test_tmp_folder_new_returns_distinct_paths_per_call(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["utils", "tmp-folder", "new"]) == 0
    first = Path(capsys.readouterr().out.strip())

    assert main(["utils", "tmp-folder", "new"]) == 0
    second = Path(capsys.readouterr().out.strip())

    assert first != second
    assert not first.exists()
    assert not second.exists()


def test_tmp_folder_new_with_create_creates_directory_under_project_tmp(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["utils", "tmp-folder", "new", "--create"]) == 0
    out = capsys.readouterr().out.strip()

    created_path = Path(out)
    expected_parent = (tmp_path / ".agentos" / "tmp").resolve()
    assert created_path.is_absolute()
    assert created_path.is_dir()
    assert created_path.parent == expected_parent


def test_tmp_folder_new_requires_agentos_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["utils", "tmp-folder", "new"]) == 1
    stderr = capsys.readouterr().err
    assert "not inside an agentos project" in stderr
