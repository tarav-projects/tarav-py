from __future__ import annotations

from pathlib import Path

from agentos.tara_tapes.check import check_tape
from agentos.tara_tapes.poi import (
    TARA_TAPE_POI_CODES,
    build_tara_linter_report,
    tara_issue_code,
)


def test_tara_adapter_preserves_issue_order_and_messages(tmp_path: Path) -> None:
    tape = tmp_path / "tape"
    tape.mkdir()
    (tape / "tape.json").write_text("{}", encoding="utf-8")

    result = check_tape(tape)
    report = build_tara_linter_report(result)

    assert [instance.situation for instance in report.instances] == result["issues"]
    assert report.as_dict()["domain"]["conformant"] is False
    assert "issues" not in report.as_dict()["domain"]
    assert all(
        str(instance.class_reference.address).startswith("Tara.Tape.Linter/")
        for instance in report.instances
    )


def test_every_tara_issue_branch_has_a_registered_code() -> None:
    messages = (
        "path is not a directory",
        "missing tape.json",
        "invalid tape.json: bad data",
        "tape.json is not a JSON object",
        "missing or empty tape_name",
        "tara_tape_spec is None, expected '0.1'",
        "missing or empty created_at",
        "missing segments/ directory",
        "segments exists but is not a directory",
        "non-file entry in segments/: nested",
        "non-jsonl file in segments/: data.txt",
        "segments/data.jsonl: blank line at line 2",
        "segments/data.jsonl: invalid JSON at line 3",
        "segments/data.jsonl: cannot read file: denied",
        "missing stage/ directory",
        "stage exists but is not a directory",
    )

    assert (
        tuple(tara_issue_code(message) for message in messages) == TARA_TAPE_POI_CODES
    )


def test_tara_instance_identity_is_deterministic(tmp_path: Path) -> None:
    result = {
        "tape_path": str(tmp_path),
        "conformant": False,
        "issues": ["missing tape.json"],
    }

    first = build_tara_linter_report(result).instances[0]
    second = build_tara_linter_report(result).instances[0]
    assert first.instance_id == second.instance_id
