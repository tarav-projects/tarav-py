from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0._core.persistence import atomic_write_json, atomic_write_text


def test_atomic_write_text_creates_parent_and_replaces_content(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "state.txt"

    atomic_write_text(target, "first\n")
    atomic_write_text(target, "second\n")

    assert target.read_text(encoding="utf-8") == "second\n"
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_text_preserves_existing_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.txt"
    target.write_text("old\n", encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("tarav.l0._core.persistence.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_json_uses_stable_pretty_format(tmp_path: Path) -> None:
    target = tmp_path / "state.json"

    atomic_write_json(target, {"z": 1, "a": "café"}, ensure_ascii=False)

    text = target.read_text(encoding="utf-8")
    assert json.loads(text) == {"a": "café", "z": 1}
    assert text.endswith("\n")
    assert text.index('"a"') < text.index('"z"')
