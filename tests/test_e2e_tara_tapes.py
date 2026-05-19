from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main
from _helpers import captured_json


def _write_legacy_tape(root: Path, name: str) -> Path:
    tape = root / name
    tape.mkdir(parents=True)
    (tape / "tape.json").write_text(
        json.dumps({"tape_name": name, "formatVersion": "0.0.1"}),
        encoding="utf-8",
    )
    (tape / "data.jsonl").write_text('{"x": 1}\n', encoding="utf-8")
    return tape


def test_tara_tapes_cli_lifecycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "tape"

    assert main(["tara-tapes", "init", "--root", str(root), "--tape-name", "events", "--manifest-json", '{"owner":"alice"}']) == 0
    init_payload = captured_json(capsys)
    assert init_payload["tape_created"] is True
    assert init_payload["manifest"]["owner"] == "alice"
    assert (root / "segments").is_dir()
    assert (root / "stage").is_dir()

    assert main(["tara-tapes", "append", "--root", str(root), "--writer-id", "proc-a", "--segment", "session.jsonl", "--record-json", '{"class_id":"var.inline","value":42}']) == 0
    capsys.readouterr()
    assert main(["tara-tapes", "append", "--root", str(root), "--writer-id", "proc-b", "--segment", "session.jsonl", "--record-json", "true"]) == 0
    capsys.readouterr()

    assert main(["tara-tapes", "scan", "--root", str(root)]) == 0
    assert captured_json(capsys)["records"] == []

    assert main(["tara-tapes", "commit", "--root", str(root)]) == 0
    commit_payload = captured_json(capsys)
    assert commit_payload["committed_record_count"] == 2
    assert commit_payload["processed_stage_file_count"] == 2

    assert main(["tara-tapes", "segments", "--root", str(root)]) == 0
    assert captured_json(capsys)["segments"] == ["session.jsonl"]

    assert main(["tara-tapes", "read-segment", "--root", str(root), "--segment", "session.jsonl"]) == 0
    assert captured_json(capsys)["records"] == [
        {"class_id": "var.inline", "value": 42},
        True,
    ]

    assert main(["tara-tapes", "manifest", "--root", str(root)]) == 0
    manifest_payload = captured_json(capsys)
    assert manifest_payload["tape_name"] == "events"
    assert manifest_payload["owner"] == "alice"

    assert main(["tara-tapes", "verify", "--root", str(root)]) == 0
    verify_payload = captured_json(capsys)
    assert verify_payload["segment_count"] == 1
    assert verify_payload["committed_record_count"] == 2
    assert verify_payload["stage_file_count"] == 0


def test_tara_tapes_check_reports_conformance(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "ok"
    assert main(["tara-tapes", "init", "--root", str(root), "--tape-name", "ok"]) == 0
    capsys.readouterr()

    assert main(["tara-tapes", "check", "--root", str(root)]) == 0
    assert captured_json(capsys)["conformant"] is True

    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    (bad_root / "tape.json").write_text(
        json.dumps({"tape_name": "bad", "tara_tape_spec": "0.1"}),
        encoding="utf-8",
    )
    (bad_root / "stage").mkdir()
    assert main(["tara-tapes", "check", "--root", str(bad_root)]) == 0
    bad_payload = captured_json(capsys)
    assert bad_payload["conformant"] is False
    assert any("segments" in issue for issue in bad_payload["issues"])


def test_tara_tapes_archive_and_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    archive_home = tmp_path / "archive"
    movable = _write_legacy_tape(tmp_path / "tapes", "movable")
    dry_run = _write_legacy_tape(tmp_path / "tapes", "dry-run")

    assert main(["tara-tapes", "archive", str(movable), "--archive-home", str(archive_home)]) == 0
    archive_payload = captured_json(capsys)
    assert archive_payload["archived"] is True
    assert not movable.exists()
    assert (Path(archive_payload["archive_path"]) / "movable" / "tape.json").is_file()

    assert main(["tara-tapes", "archive", str(dry_run), "--archive-home", str(archive_home), "--dry-run"]) == 0
    dry_payload = captured_json(capsys)
    assert dry_payload["dry_run"] is True
    assert dry_run.exists()
