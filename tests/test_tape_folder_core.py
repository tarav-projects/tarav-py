from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.cli import main
from agentos.tape.folder_core import (
    append_staging_record,
    bootstrap_tape_folder,
    consolidate_staging_records,
    read_best_effort_records,
    read_committed_records,
    verify_segment_headers,
)


def test_bootstrap_folder_tape_creates_manifest_and_dirs(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    config, created = bootstrap_tape_folder(
        root,
        tape_name="events",
        naming_strategy="sequential",
        max_records_per_segment=100,
    )
    assert created is True
    assert config.tape_name == "events"
    assert (root / "segments").is_dir()
    assert (root / "staging").is_dir()

    manifest = json.loads((root / "tape.manifest.json").read_text(encoding="utf-8"))
    assert manifest["class"] == "tape.folder.config"
    assert manifest["config"]["naming_strategy"] == "sequential"
    assert manifest["config"]["max_records_per_segment"] == 100


def test_consolidation_rolls_sequential_segments(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tape_folder(
        root,
        tape_name="events",
        naming_strategy="sequential",
        max_records_per_segment=2,
    )

    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.alpha",
        created_at="2026-03-01T10:00:00Z",
    )
    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.beta",
        created_at="2026-03-01T10:01:00Z",
    )
    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.gamma",
        created_at="2026-03-01T10:02:00Z",
    )

    result = consolidate_staging_records(root)
    assert result["processed_count"] == 3
    assert result["segments_touched"] == ["0001.jsonl", "0002.jsonl"]

    committed = read_committed_records(root)
    assert [item.record["class"] for item in committed] == ["event.alpha", "event.beta", "event.gamma"]


def test_consolidation_rolls_monthly_segments(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tape_folder(
        root,
        tape_name="events",
        naming_strategy="monthly",
        max_records_per_segment=1,
    )

    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.alpha",
        created_at="2026-03-01T10:00:00Z",
    )
    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.beta",
        created_at="2026-03-11T10:00:00Z",
    )
    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.gamma",
        created_at="2026-04-01T10:00:00Z",
    )

    result = consolidate_staging_records(root)
    assert result["processed_count"] == 3
    assert result["segments_touched"] == ["2603.jsonl", "2604.jsonl"]


def test_consolidation_rolls_daily_segments(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tape_folder(
        root,
        tape_name="events",
        naming_strategy="daily",
        max_records_per_segment=1,
    )

    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.alpha",
        created_at="2026-03-01T10:00:00Z",
    )
    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.beta",
        created_at="2026-03-01T11:00:00Z",
    )
    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.gamma",
        created_at="2026-03-02T10:00:00Z",
    )

    result = consolidate_staging_records(root)
    assert result["processed_count"] == 3
    assert result["segments_touched"] == ["260301.jsonl", "260302.jsonl"]


def test_verify_fails_on_segment_filename_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tape_folder(
        root,
        tape_name="events",
        naming_strategy="sequential",
        max_records_per_segment=100,
    )

    segment_path = root / "segments" / "0001.jsonl"
    segment_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "class": "tape.segment.metadata",
                        "segment_filename": "wrong-name.jsonl",
                        "created_at": "2026-03-01T00:00:00Z",
                    }
                ),
                json.dumps({"class": "event.alpha", "created_at": "2026-03-01T00:01:00Z"}),
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(CliError, match="filename mismatch"):
        verify_segment_headers(root)


def test_best_effort_reads_merge_staging_and_committed(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tape_folder(
        root,
        tape_name="events",
        naming_strategy="sequential",
        max_records_per_segment=100,
    )

    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.committed",
        created_at="2026-03-01T10:00:00Z",
    )
    consolidate_staging_records(root)
    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.staged",
        created_at="2026-02-01T10:00:00Z",
    )

    committed = read_committed_records(root)
    assert [item.record["class"] for item in committed] == ["event.committed"]

    best_effort = read_best_effort_records(root)
    assert [item.record["class"] for item in best_effort] == ["event.staged", "event.committed"]


def test_append_staging_record_validates_data_schema(tmp_path: Path) -> None:
    root = tmp_path / "tape"
    bootstrap_tape_folder(
        root,
        tape_name="events",
        naming_strategy="sequential",
        max_records_per_segment=100,
        data_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["k"],
            "properties": {
                "k": {"type": "string"},
            },
            "additionalProperties": False,
        },
    )

    append_staging_record(
        root,
        writer_id="writer-1",
        record_class="event.valid",
        created_at="2026-03-01T10:00:00Z",
        data={"k": "ok"},
    )

    with pytest.raises(CliError, match="does not match data_schema"):
        append_staging_record(
            root,
            writer_id="writer-1",
            record_class="event.invalid",
            created_at="2026-03-01T10:01:00Z",
            data={"k": 123},
        )


def test_folder_cli_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "tape"
    assert (
        main(
            [
                "tape",
                "init",
                "--root",
                str(root),
                "--tape-name",
                "events",
                "--max-records-per-segment",
                "10",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "tape",
                "append",
                "--root",
                str(root),
                "--writer-id",
                "proc-a",
                "--class",
                "event.alpha",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["tape", "consolidate", "--root", str(root)]) == 0
    capsys.readouterr()

    assert main(["tape", "query", "--root", str(root), "--count"]) == 0
    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["count"] == 1
