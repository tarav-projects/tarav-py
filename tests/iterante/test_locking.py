"""Tests for File.Locking — the persisted per-file version registry."""

import pytest

from tarav.iterante.locking import LockViolation, record, verify


def test_record_then_verify_is_clean(tmp_path):
    f = tmp_path / "run.json"
    f.write_text('{"a": 1}')
    record(f)
    verify(f)  # no raise


def test_verify_raises_after_out_of_band_edit(tmp_path):
    f = tmp_path / "run.json"
    f.write_text('{"a": 1}')
    record(f)

    f.write_text('{"a": 2}')  # changed outside the system
    with pytest.raises(LockViolation) as ei:
        verify(f)
    assert str(f) in str(ei.value)


def test_re_record_reauthorizes(tmp_path):
    f = tmp_path / "run.json"
    f.write_text('{"a": 1}')
    record(f)
    f.write_text('{"a": 2}')
    record(f)  # legal write re-signs the new content
    verify(f)  # no raise


def test_verify_without_log_is_a_violation(tmp_path):
    f = tmp_path / "run.json"
    f.write_text("never recorded")
    with pytest.raises(LockViolation):
        verify(f)


def test_record_appends_to_per_file_log(tmp_path):
    f = tmp_path / "run.json"
    f.write_text("v1")
    record(f)
    f.write_text("v2")
    record(f)

    log = tmp_path / "run.json.lock.jsonl"
    lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2  # append-only: one event per legal write
