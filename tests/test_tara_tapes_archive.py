from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main
from agentos.tara_tapes.archive import archive_tapes


def _make_tape_dir(root: Path, name: str) -> Path:
    tape_path = root / name
    tape_path.mkdir(parents=True)
    manifest = {"tape_name": name, "formatVersion": "0.0.1"}
    (tape_path / "tape.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tape_path / "data.jsonl").write_text('{"x": 1}\n', encoding="utf-8")
    return tape_path


def test_archive_moves_tapes(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    a_home = tmp_path / "archive"

    tape_a = _make_tape_dir(tapes_dir, "tape-a")
    tape_b = _make_tape_dir(tapes_dir, "tape-b")

    result = archive_tapes([tape_a, tape_b], archive_home=a_home)

    assert result["archived"] is True
    assert result["dry_run"] is False
    assert len(result["tapes"]) == 2

    # Tapes were moved
    assert not tape_a.exists()
    assert not tape_b.exists()

    # Archive directory contains both tapes
    a_dir = Path(result["archive_path"])
    assert (a_dir / "tape-a" / "tape.json").exists()
    assert (a_dir / "tape-b" / "tape.json").exists()
    assert (a_dir / "manifest.json").exists()

    # Manifest has provenance
    manifest = json.loads((a_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_id"] == result["archive_id"]
    assert len(manifest["tapes"]) == 2


def test_archive_noop_when_empty(tmp_path: Path) -> None:
    a_home = tmp_path / "archive"
    result = archive_tapes([], archive_home=a_home)

    assert result["archived"] is False
    assert result["tapes"] == []
    assert not a_home.exists()


def test_archive_uuid_prevents_overwrite(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    a_home = tmp_path / "archive"

    tape1 = _make_tape_dir(tapes_dir, "bad")
    result1 = archive_tapes([tape1], archive_home=a_home)

    tape2 = _make_tape_dir(tapes_dir, "bad")
    result2 = archive_tapes([tape2], archive_home=a_home)

    assert result1["archive_id"] != result2["archive_id"]
    assert Path(result1["archive_path"]).exists()
    assert Path(result2["archive_path"]).exists()


def test_archive_dry_run_does_not_move(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    a_home = tmp_path / "archive"

    tape = _make_tape_dir(tapes_dir, "bad")

    result = archive_tapes([tape], archive_home=a_home, dry_run=True)

    assert result["dry_run"] is True
    assert result["archived"] is False
    assert len(result["tapes"]) == 1

    # Tape was NOT moved
    assert tape.exists()
    # Archive dir was NOT created
    assert not a_home.exists()


def test_archive_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    a_home = tmp_path / "archive"

    tape = _make_tape_dir(tapes_dir, "nok")

    assert main([
        "tara-tapes", "archive",
        str(tape),
        "--archive-home", str(a_home),
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["archived"] is True
    assert not tape.exists()


def test_archive_dry_run_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    a_home = tmp_path / "archive"

    tape = _make_tape_dir(tapes_dir, "old-tape")

    assert main([
        "tara-tapes", "archive",
        str(tape),
        "--archive-home", str(a_home),
        "--dry-run",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert tape.exists()
    assert not a_home.exists()
