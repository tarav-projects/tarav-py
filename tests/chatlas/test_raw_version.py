from __future__ import annotations

from pathlib import Path

from tarav.l1.chatlas.index_store import iter_session_index_rows
from tarav.l1.chatlas.index_writer import _upsert_session_index_rows

IDENTITY = "a" * 64


def _row(*transcripts: Path, uri: str = "tarav://one") -> dict[str, object]:
    return {
        "provider": "codex",
        "instance": "work",
        "provider_instance_fingerprint": "f" * 64,
        "session_id": "session-one",
        "identity_hash": IDENTITY,
        "uri": uri,
        "last_activity_at": "2026-10-18T00:00:00Z",
        "backing_artifacts": [
            {"role": "transcript", "path": str(path)} for path in transcripts
        ],
    }


def _indexed(root: Path, *rows: dict[str, object]) -> dict[str, object]:
    _upsert_session_index_rows(root, rows=list(rows))
    (row,) = iter_session_index_rows(root, provider="codex", identity_hash=IDENTITY)
    return row


def test_an_indexed_row_carries_the_version_of_its_raw_data(tmp_path: Path) -> None:
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text("one\n", encoding="utf-8")
    index = tmp_path / "index"

    first = _indexed(index, _row(transcript))
    again = _indexed(index, _row(transcript))
    transcript.write_text("one\ntwo\n", encoding="utf-8")
    grown = _indexed(index, _row(transcript))

    assert str(first["raw_version"]).startswith("sha256:")
    assert again["raw_version"] == first["raw_version"]
    assert grown["raw_version"] != first["raw_version"]


def test_the_raw_version_covers_archive_versions_without_entering_them(
    tmp_path: Path,
) -> None:
    old = tmp_path / "old.jsonl"
    new = tmp_path / "new.jsonl"
    old.write_text("old\n", encoding="utf-8")
    new.write_text("new\n", encoding="utf-8")
    index = tmp_path / "index"

    merged = _indexed(index, _row(old, uri="tarav://old"), _row(new, uri="tarav://new"))
    before = merged["raw_version"]
    old.write_text("old, amended\n", encoding="utf-8")
    after = _indexed(index, _row(new, uri="tarav://new"))["raw_version"]

    versions = merged["archive_versions"]
    assert isinstance(versions, list) and len(versions) == 2
    assert all("raw_version" not in version for version in versions)
    assert after != before


def test_a_missing_transcript_leaves_no_raw_version(tmp_path: Path) -> None:
    row = _indexed(tmp_path / "index", _row(tmp_path / "absent.jsonl"))

    assert row["raw_version"] is None
