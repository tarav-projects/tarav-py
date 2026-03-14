from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main
from agentos.tara_tapes.core import bootstrap_tara_tape
from agentos.tara_tapes.quarantine import quarantine_tapes


def _make_conformant_tape(root: Path, name: str) -> Path:
    tape_path = root / name
    bootstrap_tara_tape(tape_path, tape_name=name)
    return tape_path


def _make_non_conformant_tape(root: Path, name: str) -> Path:
    tape_path = root / name
    tape_path.mkdir(parents=True)
    manifest = {"tape_name": name, "formatVersion": "0.0.1"}
    (tape_path / "tape.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tape_path / "data.jsonl").write_text('{"x": 1}\n', encoding="utf-8")
    return tape_path


def test_quarantine_moves_non_conformant(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    _make_conformant_tape(tapes_dir, "good")
    _make_non_conformant_tape(tapes_dir, "bad")

    result = quarantine_tapes(tapes_dir, quarantine_home=q_home)

    assert result["quarantined"] is True
    assert result["conformant_count"] == 1
    assert result["non_conformant_count"] == 1
    assert result["quarantine_id"] is not None

    # Non-conformant tape was moved
    assert not (tapes_dir / "bad").exists()
    # Conformant tape stays
    assert (tapes_dir / "good").exists()

    # Quarantine directory contains the tape
    q_dir = Path(result["quarantine_path"])
    assert (q_dir / "bad" / "tape.json").exists()
    assert (q_dir / "manifest.json").exists()

    # Manifest has provenance
    manifest = json.loads((q_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["quarantine_id"] == result["quarantine_id"]
    assert len(manifest["tapes"]) == 1
    assert manifest["tapes"][0]["tape_name"] == "bad"


def test_quarantine_noop_when_all_conformant(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    _make_conformant_tape(tapes_dir, "good1")
    _make_conformant_tape(tapes_dir, "good2")

    result = quarantine_tapes(tapes_dir, quarantine_home=q_home)

    assert result["quarantined"] is False
    assert result["conformant_count"] == 2
    assert result["non_conformant_count"] == 0
    assert not q_home.exists()


def test_quarantine_uuid_prevents_overwrite(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    q_home = tmp_path / "quarantine"

    # First quarantine operation
    tapes_dir.mkdir()
    _make_non_conformant_tape(tapes_dir, "bad")
    result1 = quarantine_tapes(tapes_dir, quarantine_home=q_home)

    # Create another non-conformant tape with the same name
    _make_non_conformant_tape(tapes_dir, "bad")
    result2 = quarantine_tapes(tapes_dir, quarantine_home=q_home)

    # Both operations produced different UUIDs
    assert result1["quarantine_id"] != result2["quarantine_id"]

    # Both quarantine directories exist
    assert Path(result1["quarantine_path"]).exists()
    assert Path(result2["quarantine_path"]).exists()


def test_quarantine_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    _make_conformant_tape(tapes_dir, "ok")
    _make_non_conformant_tape(tapes_dir, "nok")

    assert main([
        "tara-tapes", "quarantine",
        "--root", str(tapes_dir),
        "--quarantine-home", str(q_home),
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["quarantined"] is True
    assert payload["non_conformant_count"] == 1
    assert not (tapes_dir / "nok").exists()


def test_quarantine_dry_run_does_not_move(tmp_path: Path) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    _make_conformant_tape(tapes_dir, "good")
    _make_non_conformant_tape(tapes_dir, "bad")

    result = quarantine_tapes(tapes_dir, quarantine_home=q_home, dry_run=True)

    assert result["dry_run"] is True
    assert result["quarantined"] is False
    assert result["non_conformant_count"] == 1
    assert len(result["tapes"]) == 1
    assert result["tapes"][0]["tape_name"] == "bad"

    # Tape was NOT moved
    assert (tapes_dir / "bad").exists()
    # Quarantine dir was NOT created
    assert not q_home.exists()


def test_quarantine_dry_run_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tapes_dir = tmp_path / "tapes"
    tapes_dir.mkdir()
    q_home = tmp_path / "quarantine"

    _make_non_conformant_tape(tapes_dir, "old-tape")

    assert main([
        "tara-tapes", "quarantine",
        "--root", str(tapes_dir),
        "--quarantine-home", str(q_home),
        "--dry-run",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["non_conformant_count"] == 1
    # Nothing was moved
    assert (tapes_dir / "old-tape").exists()
    assert not q_home.exists()
