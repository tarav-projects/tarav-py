from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0._core.errors import CliError
from tarav.l1.chatlas.session_resolver import resolve_session_index_row


def _write_row(root: Path, row: dict[str, object]) -> None:
    identity = str(row["identity_hash"])
    path = root / "index" / "sessions" / str(row["provider"]) / identity[:2] / "sessions.index.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_resolver_requires_an_exact_identity_not_a_prefix(tmp_path: Path) -> None:
    identity = "ab" + "1" * 62
    _write_row(
        tmp_path,
        {
            "provider": "codex",
            "instance": "primary",
            "session_id": "native-one",
            "identity_hash": identity,
        },
    )

    assert resolve_session_index_row(
        identity_hash=identity, chatlas_root=tmp_path
    )["session_id"] == "native-one"
    with pytest.raises(CliError, match="no indexed"):
        resolve_session_index_row(identity_hash="ab", chatlas_root=tmp_path)
