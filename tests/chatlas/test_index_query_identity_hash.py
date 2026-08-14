from __future__ import annotations

from typing import Any

from tarav.chatlas.index_query import chatlas_index_row_matches


def _matches(row: dict[str, Any], identity_hash: str | None) -> bool:
    return chatlas_index_row_matches(
        row,
        uri=None,
        identity_hash=identity_hash,
        project=None,
        project_base=None,
        providers=None,
        instances=None,
        provider_instance_fingerprint=None,
        session_id=None,
        display_name=None,
        extractable_only=False,
        active_after=None,
    )


def test_identity_hash_full_match() -> None:
    row = {"identity_hash": "abc123def456"}
    assert _matches(row, "abc123def456")


def test_identity_hash_prefix_match() -> None:
    row = {"identity_hash": "abc123def456"}
    assert _matches(row, "abc1")


def test_identity_hash_prefix_miss() -> None:
    row = {"identity_hash": "abc123def456"}
    assert not _matches(row, "xyz")


def test_identity_hash_none_passes_through() -> None:
    row = {"identity_hash": "abc123def456"}
    assert _matches(row, None)


def test_identity_hash_missing_in_row() -> None:
    row: dict[str, Any] = {}
    assert not _matches(row, "abc1")
