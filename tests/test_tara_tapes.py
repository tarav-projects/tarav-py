from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.cli import main
from agentos.tara_tapes.core import (
    append_tara_tape_stage_record,
    bootstrap_tara_tape,
    commit_tara_tape_stage,
    get_tara_tape_manifest_path,
    list_tara_tape_segments,
    load_tara_tape_manifest,
    read_tara_tape_records,
    read_tara_tape_segment_records,
    save_tara_tape_manifest,
    verify_tara_tape,
)


def test_bootstrap_tara_tape_creates_spec_layout(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    manifest, created = bootstrap_tara_tape(root, tape_name="events")

    assert created is True
    assert manifest["tape_name"] == "events"
    assert manifest["tara_tape_spec"] == "0.1"
    assert (root / "tape.json").is_file()
    assert (root / "segments").is_dir()
    assert (root / "stage").is_dir()


def test_manifest_round_trip_preserves_unknown_fields(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tara_tape(
        root,
        tape_name="events",
        manifest_extra={"owner": "alice", "provenance": {"source": "test"}},
    )

    manifest = load_tara_tape_manifest(root)
    assert manifest["owner"] == "alice"
    assert manifest["provenance"] == {"source": "test"}

    manifest["note"] = "kept"
    save_tara_tape_manifest(root, manifest)

    reloaded = load_tara_tape_manifest(root)
    assert reloaded["owner"] == "alice"
    assert reloaded["provenance"] == {"source": "test"}
    assert reloaded["note"] == "kept"


def test_append_and_commit_accept_opaque_json_values_and_delete_stage_files(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tara_tape(root, tape_name="events")

    append_tara_tape_stage_record(root, writer_id="writer-a", segment_name="alpha.jsonl", record=42)
    append_tara_tape_stage_record(
        root,
        writer_id="writer-a",
        segment_name="alpha.jsonl",
        record={"class_id": "snap.scope", "value": {"x": 1}},
    )
    append_tara_tape_stage_record(root, writer_id="writer-b", segment_name="beta.jsonl", record=["a", 1])

    result = commit_tara_tape_stage(root)
    assert result["committed_record_count"] == 3
    assert result["processed_stage_file_count"] == 2
    assert result["segments_touched"] == ["alpha.jsonl", "beta.jsonl"]
    assert not (root / "stage" / "writer-a").exists()
    assert not (root / "stage" / "writer-b").exists()

    assert list_tara_tape_segments(root) == ["alpha.jsonl", "beta.jsonl"]
    assert read_tara_tape_segment_records(root, segment_name="alpha.jsonl") == [
        42,
        {"class_id": "snap.scope", "value": {"x": 1}},
    ]
    assert read_tara_tape_records(root) == [
        42,
        {"class_id": "snap.scope", "value": {"x": 1}},
        ["a", 1],
    ]


def test_scan_reads_only_committed_segments(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tara_tape(root, tape_name="events")

    append_tara_tape_stage_record(root, writer_id="writer-a", segment_name="alpha.jsonl", record={"x": 1})

    assert read_tara_tape_records(root) == []

    commit_tara_tape_stage(root)
    assert read_tara_tape_records(root) == [{"x": 1}]


def test_append_requires_jsonl_segment_name(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tara_tape(root, tape_name="events")

    with pytest.raises(CliError, match="segment must end with \\.jsonl"):
        append_tara_tape_stage_record(root, writer_id="writer-a", segment_name="alpha", record={"x": 1})


def test_committed_segments_do_not_gain_metadata_headers(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tara_tape(root, tape_name="events")

    append_tara_tape_stage_record(root, writer_id="writer-a", segment_name="alpha.jsonl", record={"k": "v"})
    commit_tara_tape_stage(root)

    lines = (root / "segments" / "alpha.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines == [json.dumps({"k": "v"})]


def test_verify_reports_layout_and_record_counts(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tara_tape(root, tape_name="events")
    append_tara_tape_stage_record(root, writer_id="writer-a", segment_name="alpha.jsonl", record={"x": 1})

    payload = verify_tara_tape(root)
    assert payload["segment_count"] == 0
    assert payload["stage_writer_count"] == 1
    assert payload["stage_writer_ids"] == ["writer-a"]
    assert payload["stage_file_count"] == 1
    assert payload["staged_record_count"] == 1


def test_tara_tapes_cli_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "tape"

    assert (
        main(
            [
                "tara-tapes",
                "init",
                "--root",
                str(root),
                "--tape-name",
                "events",
                "--manifest-json",
                '{"owner":"alice"}',
            ]
        )
        == 0
    )
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["tape_created"] is True
    assert init_payload["manifest"]["owner"] == "alice"

    assert (
        main(
            [
                "tara-tapes",
                "append",
                "--root",
                str(root),
                "--writer-id",
                "proc-a",
                "--segment",
                "session.jsonl",
                "--record-json",
                '{"class_id":"var.inline","value":42}',
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "tara-tapes",
                "append",
                "--root",
                str(root),
                "--writer-id",
                "proc-b",
                "--segment",
                "session.jsonl",
                "--record-json",
                'true',
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["tara-tapes", "scan", "--root", str(root)]) == 0
    scan_before_commit = json.loads(capsys.readouterr().out)
    assert scan_before_commit["records"] == []

    assert main(["tara-tapes", "commit", "--root", str(root)]) == 0
    commit_payload = json.loads(capsys.readouterr().out)
    assert commit_payload["committed_record_count"] == 2
    assert commit_payload["processed_stage_file_count"] == 2

    assert main(["tara-tapes", "segments", "--root", str(root)]) == 0
    segments_payload = json.loads(capsys.readouterr().out)
    assert segments_payload["segments"] == ["session.jsonl"]

    assert main(["tara-tapes", "read-segment", "--root", str(root), "--segment", "session.jsonl"]) == 0
    read_segment_payload = json.loads(capsys.readouterr().out)
    assert read_segment_payload["records"] == [
        {"class_id": "var.inline", "value": 42},
        True,
    ]

    assert main(["tara-tapes", "scan", "--root", str(root)]) == 0
    scan_payload = json.loads(capsys.readouterr().out)
    assert scan_payload["records"] == [
        {"class_id": "var.inline", "value": 42},
        True,
    ]

    assert main(["tara-tapes", "manifest", "--root", str(root)]) == 0
    manifest_payload = json.loads(capsys.readouterr().out)
    assert manifest_payload["tape_name"] == "events"
    assert manifest_payload["owner"] == "alice"

    assert main(["tara-tapes", "verify", "--root", str(root)]) == 0
    verify_payload = json.loads(capsys.readouterr().out)
    assert verify_payload["segment_count"] == 1
    assert verify_payload["committed_record_count"] == 2
    assert verify_payload["stage_file_count"] == 0

    manifest_path = get_tara_tape_manifest_path(root)
    assert manifest_path.name == "tape.json"
