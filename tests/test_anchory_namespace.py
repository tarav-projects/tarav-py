from __future__ import annotations

from pathlib import Path

import pytest

from tarav.anchory import (
    AnchoryDepot,
    InvalidAnchoryInputError,
)


def _chatlas_depot(tmp_path: Path) -> AnchoryDepot:
    depot = AnchoryDepot(tmp_path / "anchory")
    depot.write_namespace_meta(
        "chatlas",
        prefix="c",
        intention="chat-turn anchors; tags: u=user turn, a=assistant turn",
    )
    return depot


def test_namespace_register_composes_key_from_meta_prefix_alloc_prefix_and_tag(
    tmp_path: Path,
) -> None:
    depot = _chatlas_depot(tmp_path)

    first = depot.register(
        {"at": "2026-07-18T08:00:00Z"},
        namespace="chatlas",
        alloc_prefix="20260718",
        tag="u",
    )
    assert first.anchor == "c20260718-0u"

    second = depot.register(
        {"at": "2026-07-18T09:00:00Z"},
        namespace="chatlas",
        alloc_prefix="20260718",
        tag="a",
    )
    assert second.anchor == "c20260718-1a"

    tagless = depot.register(
        {"at": "2026-07-18T10:00:00Z"},
        namespace="chatlas",
        alloc_prefix="20260718",
    )
    assert tagless.anchor == "c20260718-2"


def test_resolve_reports_tag_mismatch_instead_of_not_found(tmp_path: Path) -> None:
    depot = _chatlas_depot(tmp_path)
    depot.register(
        {"at": "2026-07-18T08:00:00Z"},
        namespace="chatlas",
        alloc_prefix="20260718",
        tag="u",
    )

    exact = depot.resolve("c20260718-0u")
    assert exact is not None
    assert exact.anchor == "c20260718-0u"
    assert exact.namespace == "chatlas"
    assert exact.tag_mismatch is False
    assert exact.record["at"] == "2026-07-18T08:00:00Z"

    mistagged = depot.resolve("c20260718-0a")
    assert mistagged is not None
    assert mistagged.anchor == "c20260718-0u"
    assert mistagged.tag_mismatch is True

    assert depot.resolve("c20260718-9u") is None


def test_named_namespace_requires_declared_prefix_for_allocation(tmp_path: Path) -> None:
    depot = AnchoryDepot(tmp_path / "anchory")
    with pytest.raises(InvalidAnchoryInputError, match="declared prefix"):
        depot.register({"v": 1}, namespace="skw", alloc_prefix="20260718")


def test_tag_must_be_a_single_lowercase_letter(tmp_path: Path) -> None:
    depot = _chatlas_depot(tmp_path)
    for bad in ("uu", "U", "1", ""):
        with pytest.raises(InvalidAnchoryInputError, match="tag"):
            depot.register(
                {"v": 1}, namespace="chatlas", alloc_prefix="20260718", tag=bad
            )


def test_namespace_meta_round_trip_and_validation(tmp_path: Path) -> None:
    depot = AnchoryDepot(tmp_path / "anchory")
    depot.write_namespace_meta("chatlas", prefix="c", intention="x", semantics="skills/chatlas")
    meta = depot.namespace_meta("chatlas")
    assert meta == {"prefix": "c", "intention": "x", "semantics": "skills/chatlas"}
    assert depot.namespace_meta("missing") is None
    with pytest.raises(InvalidAnchoryInputError, match="prefix"):
        depot.write_namespace_meta("bad", prefix="cc")


def test_global_namespace_still_allocates_bare_keys(tmp_path: Path) -> None:
    depot = AnchoryDepot(tmp_path / "anchory")
    entry = depot.register({"v": 1}, alloc_prefix="20260718")
    assert entry.anchor == "20260718-0"
    resolved = depot.resolve("20260718-0")
    assert resolved is not None
    assert resolved.record == {"v": 1}
    assert resolved.namespace == "global"


def test_query_and_check_span_namespaces(tmp_path: Path) -> None:
    depot = _chatlas_depot(tmp_path)
    depot.register({"v": 1}, namespace="chatlas", alloc_prefix="20260718", tag="u")
    depot.register({"v": 2}, alloc_prefix="20260718")

    anchors = [entry.anchor for entry in depot.query()]
    assert anchors == ["20260718-0", "c20260718-0u"]

    chatlas_only = [entry.anchor for entry in depot.query(namespace="chatlas")]
    assert chatlas_only == ["c20260718-0u"]

    assert depot.check().ok is True


def test_check_warns_on_tagless_keys_in_prefixed_namespace(tmp_path: Path) -> None:
    depot = _chatlas_depot(tmp_path)
    depot.register({"v": 1}, namespace="chatlas", alloc_prefix="20260718", tag="u")
    depot.register({"v": 2}, namespace="chatlas", alloc_prefix="20260718")

    result = depot.check()
    assert result.ok is True
    tagless = [f for f in result.findings if f.code == "tagless-anchor"]
    assert len(tagless) == 1
    assert tagless[0].anchor == "c20260718-1"
    assert tagless[0].severity == "warning"
