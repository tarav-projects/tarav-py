from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main
from agentos.tara_tapes.core import bootstrap_tara_tape
from agentos.tara_tapes.quarantine import quarantine_tapes


def _make_tape_dir(root: Path, name: str) -> Path:
    tape_path = root / name
    tape_path.mkdir(parents=True)
    manifest = {"tape_name": name, "formatVersion": "0.0.1"}
    (tape_path / "tape.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tape_path / "data.jsonl").write_text('{"x": 1}\n', encoding="utf-8")
    return tape_path


def test_quarantine_moves_tapes(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    tape_a = _make_tape_dir(tapes_dir, "tape-a")
    tape_b = _make_tape_dir(tapes_dir, "tape-b")

    result = quarantine_tapes([tape_a, tape_b], quarantine_home=q_home)

    assert result["quarantined"] is True
    assert result["dry_run"] is False
    assert len(result["tapes"]) == 2

    # Tapes were moved
    assert not tape_a.exists()
    assert not tape_b.exists()

    # Quarantine directory contains both tapes
    q_dir = Path(result["quarantine_path"])
    assert (q_dir / "tape-a" / "tape.json").exists()
    assert (q_dir / "tape-b" / "tape.json").exists()
    assert (q_dir / "manifest.json").exists()

    # Manifest has provenance
    manifest = json.loads((q_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["quarantine_id"] == result["quarantine_id"]
    assert len(manifest["tapes"]) == 2


def test_quarantine_noop_when_empty(tmp_path: Path) -> None:
    q_home = tmp_path / "quarantine"
    result = quarantine_tapes([], quarantine_home=q_home)

    assert result["quarantined"] is False
    assert result["tapes"] == []
    assert not q_home.exists()


def test_quarantine_uuid_prevents_overwrite(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    tape1 = _make_tape_dir(tapes_dir, "bad")
    result1 = quarantine_tapes([tape1], quarantine_home=q_home)

    tape2 = _make_tape_dir(tapes_dir, "bad")
    result2 = quarantine_tapes([tape2], quarantine_home=q_home)

    assert result1["quarantine_id"] != result2["quarantine_id"]
    assert Path(result1["quarantine_path"]).exists()
    assert Path(result2["quarantine_path"]).exists()


def test_quarantine_dry_run_does_not_move(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    tape = _make_tape_dir(tapes_dir, "bad")

    result = quarantine_tapes([tape], quarantine_home=q_home, dry_run=True)

    assert result["dry_run"] is True
    assert result["quarantined"] is False
    assert len(result["tapes"]) == 1

    # Tape was NOT moved
    assert tape.exists()
    # Quarantine dir was NOT created
    assert not q_home.exists()


def test_quarantine_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    tape = _make_tape_dir(tapes_dir, "nok")

    assert main([
        "tara-tapes", "quarantine",
        str(tape),
        "--quarantine-home", str(q_home),
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["quarantined"] is True
    assert not tape.exists()


def test_quarantine_dry_run_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    tape = _make_tape_dir(tapes_dir, "old-tape")

    assert main([
        "tara-tapes", "quarantine",
        str(tape),
        "--quarantine-home", str(q_home),
        "--dry-run",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert tape.exists()
    assert not q_home.exists()
