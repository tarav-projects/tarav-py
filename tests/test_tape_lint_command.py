from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main


def _setup_project_tape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    assert main(["init", "--scope", "project", "--project", str(tmp_path)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(tmp_path)
    assert main(["tape", "init", "--tape", "bla"]) == 0
    capsys.readouterr()
    return (tmp_path / ".agentos" / "tapes" / "bla").resolve()


def test_tape_lint_passes_for_valid_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _setup_project_tape(tmp_path, monkeypatch, capsys)

    assert (
        main(
            [
                "tape",
                "append",
                "--tape",
                "bla",
                "--writer-id",
                "proc-a",
                "--class",
                "event.alpha",
                "--data-json",
                '{"k":"v"}',
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["tape", "consolidate", "--tape", "bla"]) == 0
    capsys.readouterr()

    assert main(["tape", "lint", "--tape", "bla"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "tape lint"
    assert payload["summary"]["errors"] == 0
    assert payload["valid_records"] == 1


def test_tape_lint_reports_invalid_minimal_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tape_root = _setup_project_tape(tmp_path, monkeypatch, capsys)

    assert (
        main(
            [
                "tape",
                "append",
                "--tape",
                "bla",
                "--writer-id",
                "proc-a",
                "--class",
                "event.alpha",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["tape", "consolidate", "--tape", "bla"]) == 0
    capsys.readouterr()

    segment_path = tape_root / "segments" / "0001.jsonl"
    with segment_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"class": "event.invalid", "created_at": "2026-03-02T00:00:00Z"}))
        handle.write("\n")

    assert main(["tape", "lint", "--tape", "bla"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["errors"] >= 1
    assert any(
        finding["code"] == "invalid-record" and finding["source_kind"] == "committed"
        for finding in payload["findings"]
    )


def test_tape_lint_reports_invalid_staging_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tape_root = _setup_project_tape(tmp_path, monkeypatch, capsys)

    staging_path = tape_root / "staging" / "proc-a.jsonl"
    staging_path.write_text(
        "\n".join(
            [
                json.dumps({"class": "wrong.staging.header", "staging_filename": "proc-a.jsonl"}),
                json.dumps(
                    {
                        "class": "event.alpha",
                        "writer": "proc-a",
                        "created_at": "2026-03-02T00:00:00Z",
                    }
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert main(["tape", "lint", "--tape", "bla"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["errors"] >= 1
    assert any(finding["code"] == "invalid-staging-header" for finding in payload["findings"])


def test_tape_lint_reports_disallowed_record_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--project", str(tmp_path)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "tape",
                "init",
                "--tape",
                "bla",
                "--allowed-classes-json",
                '["event.alpha"]',
            ]
        )
        == 0
    )
    capsys.readouterr()

    tape_root = (tmp_path / ".agentos" / "tapes" / "bla").resolve()
    segment_path = tape_root / "segments" / "0001.jsonl"
    segment_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "class": "tape.segment.metadata",
                        "created_at": "2026-03-02T00:00:00Z",
                        "naming_strategy": "sequential",
                        "segment_filename": "0001.jsonl",
                    }
                ),
                json.dumps(
                    {
                        "class": "event.beta",
                        "writer": "proc-a",
                        "created_at": "2026-03-02T00:01:00Z",
                    }
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert main(["tape", "lint", "--tape", "bla"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["errors"] >= 1
    assert any(
        finding["code"] == "invalid-record" and "not allowed" in finding["message"]
        for finding in payload["findings"]
    )
