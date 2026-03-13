from __future__ import annotations

import json
from pathlib import Path

from agentos.cli import main
from agentos.tara_tapes.check import check_tape, check_tapes, discover_tape_candidates
from agentos.tara_tapes.core import bootstrap_tara_tape


def _make_conformant_tape(root: Path, name: str) -> Path:
    tape_path = root / name
    bootstrap_tara_tape(tape_path, tape_name=name)
    return tape_path


def _make_non_conformant_tape(root: Path, name: str) -> Path:
    tape_path = root / name
    tape_path.mkdir(parents=True)
    manifest = {"tape_name": name, "formatVersion": "0.0.1"}
    (tape_path / "tape.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tape_path


def test_discover_finds_tape_candidates(tmp_path: Path) -> None:
    _make_conformant_tape(tmp_path, "good-tape")
    _make_non_conformant_tape(tmp_path, "bad-tape")
    (tmp_path / "not-a-tape").mkdir()

    candidates = discover_tape_candidates(tmp_path)
    names = [c.name for c in candidates]
    assert "good-tape" in names
    assert "bad-tape" in names
    assert "not-a-tape" not in names


def test_check_conformant_tape(tmp_path: Path) -> None:
    tape_path = _make_conformant_tape(tmp_path, "ok-tape")
    result = check_tape(tape_path)
    assert result["conformant"] is True
    assert result["issues"] == []


def test_check_missing_spec_version(tmp_path: Path) -> None:
    tape_path = _make_non_conformant_tape(tmp_path, "old-tape")
    result = check_tape(tape_path)
    assert result["conformant"] is False
    assert any("tara_tape_spec" in issue for issue in result["issues"])


def test_check_missing_segments_dir(tmp_path: Path) -> None:
    tape_path = tmp_path / "no-segments"
    tape_path.mkdir()
    manifest = {
        "tape_name": "no-segments",
        "tara_tape_spec": "0.1",
        "created_at": "2026-01-01T00:00:00Z",
    }
    (tape_path / "tape.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tape_path / "stage").mkdir()

    result = check_tape(tape_path)
    assert result["conformant"] is False
    assert any("segments" in issue for issue in result["issues"])


def test_check_missing_stage_dir(tmp_path: Path) -> None:
    tape_path = tmp_path / "no-stage"
    tape_path.mkdir()
    manifest = {
        "tape_name": "no-stage",
        "tara_tape_spec": "0.1",
        "created_at": "2026-01-01T00:00:00Z",
    }
    (tape_path / "tape.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tape_path / "segments").mkdir()

    result = check_tape(tape_path)
    assert result["conformant"] is False
    assert any("stage" in issue for issue in result["issues"])


def test_check_invalid_jsonl_in_segments(tmp_path: Path) -> None:
    tape_path = _make_conformant_tape(tmp_path, "bad-jsonl")
    segment = tape_path / "segments" / "data.jsonl"
    segment.write_text('{"ok": true}\nnot json\n', encoding="utf-8")

    result = check_tape(tape_path)
    assert result["conformant"] is False
    assert any("invalid JSON" in issue for issue in result["issues"])


def test_check_non_jsonl_file_in_segments(tmp_path: Path) -> None:
    tape_path = _make_conformant_tape(tmp_path, "wrong-ext")
    (tape_path / "segments" / "readme.txt").write_text("hi", encoding="utf-8")

    result = check_tape(tape_path)
    assert result["conformant"] is False
    assert any("non-jsonl" in issue for issue in result["issues"])


def test_check_tapes_scans_directory(tmp_path: Path) -> None:
    _make_conformant_tape(tmp_path, "good")
    _make_non_conformant_tape(tmp_path, "bad")

    result = check_tapes(tmp_path)
    assert result["tape_count"] == 2
    assert result["conformant_count"] == 1
    assert result["non_conformant_count"] == 1


def test_check_missing_manifest(tmp_path: Path) -> None:
    result = check_tape(tmp_path / "nonexistent")
    assert result["conformant"] is False


def test_check_invalid_manifest_json(tmp_path: Path) -> None:
    tape_path = tmp_path / "bad-json"
    tape_path.mkdir()
    (tape_path / "tape.json").write_text("{not valid json", encoding="utf-8")

    result = check_tape(tape_path)
    assert result["conformant"] is False
    assert any("invalid" in issue for issue in result["issues"])


def test_check_cli_multi_tape(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_conformant_tape(tmp_path, "ok")
    _make_non_conformant_tape(tmp_path, "nok")

    assert main(["tara-tapes", "check", "--root", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tape_count"] == 2
    assert payload["conformant_count"] == 1
    assert payload["non_conformant_count"] == 1


def test_check_cli_single_tape(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tape_path = _make_conformant_tape(tmp_path, "single")

    assert main(["tara-tapes", "check", "--root", str(tape_path), "--single"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["conformant"] is True


import pytest
