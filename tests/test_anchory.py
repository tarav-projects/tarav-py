from __future__ import annotations

import hashlib
import json
import multiprocessing
from pathlib import Path

import pytest

from agentos.anchory import (
    AnchorExistsError,
    AnchorNotFoundError,
    AnchoryDepot,
    AnchoryEntry,
    AnchoryRuntimeCache,
    AnchorySourceMatch,
    InvalidAnchoryInputError,
    scan_anchory_source,
)


def _register_after_signal(root: str, anchor: str, value: int, start: object) -> None:
    start.wait()  # type: ignore[attr-defined]
    AnchoryDepot(root).register({"value": value}, anchor=anchor)


def _register_prefix_after_signal(
    root: str,
    prefix: str,
    value: int,
    start: object,
    results: object,
) -> None:
    start.wait()  # type: ignore[attr-defined]
    entry = AnchoryDepot(root).register({"value": value}, alloc_prefix=prefix)
    results.put(entry.anchor)  # type: ignore[attr-defined]


def _same_shard_anchors() -> tuple[str, str]:
    seen: dict[str, str] = {}
    for index in range(1_000):
        anchor = f"concurrent-{index}"
        shard = hashlib.sha256(anchor.encode("utf-8")).hexdigest()[:2]
        if shard in seen:
            return seen[shard], anchor
        seen[shard] = anchor
    raise AssertionError("failed to find two anchors in one shard")


def test_register_and_resolve_round_trip_in_expected_shard(tmp_path: Path) -> None:
    root = tmp_path / "anchory"
    anchor = "20260706-0"
    record = {"session_id": "session-1", "turn": 12}

    entry = AnchoryDepot(root).register(record, anchor=anchor)

    assert entry == AnchoryEntry(anchor=anchor, record=record)
    assert AnchoryDepot(root).resolve(anchor).record == record
    shard = hashlib.sha256(anchor.encode("utf-8")).hexdigest()[:2]
    assert json.loads(
        (root / "global" / f"{shard}.json").read_text(encoding="utf-8")
    ) == {anchor: record}


def test_same_anchor_is_independent_per_depot(tmp_path: Path) -> None:
    first = AnchoryDepot(tmp_path / "first")
    second = AnchoryDepot(tmp_path / "second")

    first.register({"value": 1}, anchor="shared")
    second.register({"value": 2}, anchor="shared")

    assert first.resolve("shared").record == {"value": 1}
    assert second.resolve("shared").record == {"value": 2}


def test_runtime_cache_reuses_resolution_and_mutation_invalidates_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agentos.anchory.core as core

    cache = AnchoryRuntimeCache(capacity=8)
    depot = AnchoryDepot(tmp_path / "anchory", runtime_cache=cache)
    depot.register({"value": 1}, anchor="stable")
    original_read = core._read_shard
    reads = 0

    def counted_read(path: Path):
        nonlocal reads
        reads += 1
        return original_read(path)

    monkeypatch.setattr(core, "_read_shard", counted_read)
    assert depot.resolve("stable").record == {"value": 1}
    assert depot.resolve("stable").record == {"value": 1}
    assert reads == 1

    depot.amend("stable", {"value": 2})
    assert depot.resolve("stable").record == {"value": 2}
    assert reads == 3


def test_runtime_cache_capacity_evicts_old_resolutions(tmp_path: Path) -> None:
    cache = AnchoryRuntimeCache(capacity=1)
    depot = AnchoryDepot(tmp_path / "anchory", runtime_cache=cache)
    depot.register({"value": 1}, anchor="first")
    depot.register({"value": 2}, anchor="second")

    depot.resolve("first")
    depot.resolve("second")

    assert cache.resolution_count == 1


def test_duplicate_registration_is_rejected_and_amend_requires_existing_anchor(
    tmp_path: Path,
) -> None:
    depot = AnchoryDepot(tmp_path / "anchory")
    depot.register({"value": 1}, anchor="stable")

    with pytest.raises(AnchorExistsError, match="anchor already exists"):
        depot.register({"value": 2}, anchor="stable")

    assert depot.resolve("stable").record == {"value": 1}
    assert depot.amend("stable", {"value": 3}) == AnchoryEntry(
        anchor="stable", record={"value": 3}
    )
    assert depot.resolve("stable").record == {"value": 3}
    with pytest.raises(AnchorNotFoundError, match="anchor does not exist"):
        depot.amend("missing", {"value": 4})


def test_concurrent_same_shard_registrations_do_not_lose_records(
    tmp_path: Path,
) -> None:
    root = tmp_path / "anchory"
    first_anchor, second_anchor = _same_shard_anchors()
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    processes = [
        context.Process(
            target=_register_after_signal,
            args=(str(root), first_anchor, 1, start),
        ),
        context.Process(
            target=_register_after_signal,
            args=(str(root), second_anchor, 2, start),
        ),
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=10)

    assert [process.exitcode for process in processes] == [0, 0]
    depot = AnchoryDepot(root)
    assert depot.resolve(first_anchor).record == {"value": 1}
    assert depot.resolve(second_anchor).record == {"value": 2}


def test_prefix_registration_allocates_max_plus_one_and_ignores_unrelated_suffixes(
    tmp_path: Path,
) -> None:
    depot = AnchoryDepot(tmp_path / "anchory")

    assert depot.register({"value": 0}, alloc_prefix="20260708") == AnchoryEntry(
        anchor="20260708-0",
        record={"value": 0},
    )
    depot.register({"value": 2}, anchor="20260708-2")
    depot.register({"value": "ignored"}, anchor="20260708-alpha")
    depot.register({"value": "adjacent"}, anchor="202607080-9")
    depot.register({"value": "broader"}, anchor="2026-9")

    assert depot.register({"value": 3}, alloc_prefix="20260708") == AnchoryEntry(
        anchor="20260708-3",
        record={"value": 3},
    )
    assert depot.register({"value": 10}, alloc_prefix="2026") == AnchoryEntry(
        anchor="2026-10",
        record={"value": 10},
    )


def test_register_requires_exactly_one_anchor_identity(tmp_path: Path) -> None:
    depot = AnchoryDepot(tmp_path / "anchory")

    with pytest.raises(InvalidAnchoryInputError, match="exactly one"):
        depot.register({"value": 1})
    with pytest.raises(InvalidAnchoryInputError, match="exactly one"):
        depot.register({"value": 1}, anchor="stable", alloc_prefix="20260708")


def test_concurrent_prefix_registrations_allocate_distinct_anchors(
    tmp_path: Path,
) -> None:
    root = tmp_path / "anchory"
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=_register_prefix_after_signal,
            args=(str(root), "20260708", value, start, results),
        )
        for value in (1, 2)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=10)

    assert [process.exitcode for process in processes] == [0, 0]
    anchors = {results.get(timeout=10) for _ in processes}
    assert anchors == {"20260708-0", "20260708-1"}


def test_failed_atomic_replace_preserves_shard_and_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "anchory"
    depot = AnchoryDepot(root)
    depot.register({"value": 1}, anchor="stable")

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("agentos.anchory.core.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        depot.amend("stable", {"value": 2})

    assert depot.resolve("stable").record == {"value": 1}
    assert list((root / "global").glob("*.tmp")) == []


def test_query_is_anchor_sorted_and_supports_prefix_filtering(tmp_path: Path) -> None:
    depot = AnchoryDepot(tmp_path / "anchory")
    depot.register({"value": 2}, anchor="beta")
    depot.register({"value": 3}, anchor="alpha-2")
    depot.register({"value": 1}, anchor="alpha-1")

    assert depot.query() == (
        AnchoryEntry(anchor="alpha-1", record={"value": 1}),
        AnchoryEntry(anchor="alpha-2", record={"value": 3}),
        AnchoryEntry(anchor="beta", record={"value": 2}),
    )
    assert depot.query(prefix="alpha-") == (
        AnchoryEntry(anchor="alpha-1", record={"value": 1}),
        AnchoryEntry(anchor="alpha-2", record={"value": 3}),
    )


def test_check_reports_corruption_without_mutating_the_depot(tmp_path: Path) -> None:
    root = tmp_path / "anchory"
    namespace = root / "global"
    namespace.mkdir(parents=True)
    malformed = namespace / "00.json"
    invalid_record = namespace / "01.json"
    misplaced = namespace / "02.json"
    empty_anchor = namespace / "e3.json"
    malformed.write_text("{", encoding="utf-8")
    invalid_record.write_text('{"bad":[]}\n', encoding="utf-8")
    misplaced.write_text('{"misplaced":{"value":1}}\n', encoding="utf-8")
    empty_anchor.write_text('{"":{}}\n', encoding="utf-8")
    before = {path: path.read_bytes() for path in namespace.iterdir()}

    result = AnchoryDepot(root).check()

    assert result.ok is False
    assert {finding.code for finding in result.findings} == {
        "invalid-json",
        "invalid-record",
        "invalid-anchor",
        "misplaced-anchor",
    }
    assert {path: path.read_bytes() for path in namespace.iterdir()} == before


def test_check_accepts_an_empty_or_valid_depot(tmp_path: Path) -> None:
    depot = AnchoryDepot(tmp_path / "anchory")
    assert depot.check().ok is True
    depot.register({"value": 1}, anchor="valid")
    assert depot.check().ok is True


def test_scan_anchory_source_extracts_named_anchor_group_with_location() -> None:
    text = "intro @alpha\nnext @beta\n"

    assert scan_anchory_source(text, r"@(?P<anchor>[a-z]+)") == (
        AnchorySourceMatch(anchor="alpha", line=1, column=8, start=7, end=12),
        AnchorySourceMatch(anchor="beta", line=2, column=7, start=19, end=23),
    )


def test_scan_anchory_source_extracts_first_group_or_whole_match() -> None:
    text = "refs: [alpha] beta"

    assert scan_anchory_source(text, r"\[([a-z]+)\]") == (
        AnchorySourceMatch(anchor="alpha", line=1, column=8, start=7, end=12),
    )
    assert scan_anchory_source(text, r"beta") == (
        AnchorySourceMatch(anchor="beta", line=1, column=15, start=14, end=18),
    )


def test_scan_anchory_source_deduplicates_after_first_occurrence() -> None:
    text = "@alpha\n@beta\n@alpha\n"

    assert scan_anchory_source(text, r"@(?P<anchor>[a-z]+)") == (
        AnchorySourceMatch(anchor="alpha", line=1, column=2, start=1, end=6),
        AnchorySourceMatch(anchor="beta", line=2, column=2, start=8, end=12),
    )
