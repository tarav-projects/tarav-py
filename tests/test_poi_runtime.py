from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tarav.poi.runtime import (
    Check,
    Evaluator,
    Finding,
    Status,
    Tier,
    build_linter_document,
    render_linter_text,
    run_checks,
    select_checks,
)


@dataclass
class _Context:
    records: list[str] = field(default_factory=lambda: ["r1", "r2"])
    subjects: frozenset[str] | None = None
    produced: set[str] = field(default_factory=set)

    def selected_records(self) -> list[str]:
        if self.subjects is None:
            return self.records
        return [record for record in self.records if record in self.subjects]


class _StructuralCheck(Check[_Context]):
    name = "load"
    tier = Tier.STRUCTURAL

    def run(self) -> list[Finding]:
        return []


class _RecordCheck(Check[_Context]):
    name = "record"

    def run(self) -> list[Finding]:
        return [
            Finding(
                "Test.Linter/Record.Bad",
                {"record_id": record},
                {"expected": "good", "actual": "bad"},
                surface={"workspace": "test"},
            )
            for record in self.context.selected_records()
        ]


class _CorpusCheck(Check[_Context]):
    name = "corpus"

    def run(self) -> list[Finding]:
        return []


class _DevCheck(_RecordCheck):
    name = "record-dev"
    dev = True
    replaces = "record"


def test_finding_identity_excludes_operands_but_includes_occurrence() -> None:
    first = Finding(
        "Test.Linter/Record.Bad",
        {"record_id": "r1"},
        {"actual": 1},
        surface={"workspace": "test"},
    )
    changed_value = Finding(
        "Test.Linter/Record.Bad",
        {"record_id": "r1"},
        {"actual": 2},
        surface={"workspace": "test"},
    )
    another_record = Finding(
        "Test.Linter/Record.Bad",
        {"record_id": "r2"},
        {"actual": 1},
        surface={"workspace": "test"},
    )

    assert first.identity == changed_value.identity
    assert first.identity != another_record.identity
    assert first.evaluator is Evaluator.CODE


def test_selection_forces_structural_checks_and_honors_target_and_dev_lanes() -> None:
    registry = (
        _StructuralCheck,
        _RecordCheck,
        _CorpusCheck,
        _DevCheck,
    )

    assert [check.name for check in select_checks(registry, check=["record"])] == [
        "load",
        "record",
    ]
    assert [
        check.name
        for check in select_checks(registry, skip=["load"], targeted=True)
    ] == ["load", "record"]
    assert [check.name for check in select_checks(registry, dev=True)] == [
        "load",
        "corpus",
        "record-dev",
    ]
    assert "record-dev" not in {
        check.name for check in select_checks(registry, check=["record-dev"])
    }


def test_run_reports_failed_blocked_and_structural_short_circuit() -> None:
    class BlockedCheck(Check[_Context]):
        name = "blocked"

        def run(self) -> list[Finding]:
            return [
                Finding(
                    "Test.Linter/Archive.Unavailable",
                    {"archive": "chat"},
                    {"actual": "missing"},
                    status=Status.BLOCKED,
                )
            ]

    class BrokenStructureCheck(Check[_Context]):
        name = "load"
        tier = Tier.STRUCTURAL

        def run(self) -> list[Finding]:
            return [
                Finding(
                    "Test.Linter/Cargo.Unloadable",
                    {"record_id": "r0"},
                    {"actual": "malformed"},
                )
            ]

    report = run_checks(
        _Context(),
        (BlockedCheck, _RecordCheck),
        execution=lambda ctx: {"records_loaded": len(ctx.records)},
    )
    assert [result.status for result in report.results] == [
        Status.BLOCKED,
        Status.FAILED,
    ]
    assert report.clean is False
    assert report.verified is False

    stopped = run_checks(
        _Context(),
        (BrokenStructureCheck, _RecordCheck),
    )
    assert stopped.short_circuited is True
    assert [result.name for result in stopped.results] == ["load"]


def test_blocked_check_dependency_blocks_once_without_subject_findings() -> None:
    class ArchiveCheck(Check[_Context]):
        name = "archive"

        def run(self) -> list[Finding]:
            return [
                Finding(
                    "Test.Linter/Archive.Unavailable",
                    {"archive": "chat"},
                    {"actual": "missing"},
                    status=Status.BLOCKED,
                )
            ]

    class DependentCheck(_RecordCheck):
        name = "dependent"
        requires = ("archive",)

    report = run_checks(
        _Context(),
        (ArchiveCheck, DependentCheck),
        check=("dependent",),
    )

    assert report.findings == ()
    assert len(report.blocked) == 1
    assert [result.status for result in report.results] == [
        Status.BLOCKED,
        Status.BLOCKED,
    ]
    assert report.results[1].reason == "blocked by check(s): archive"


def test_failed_dependency_does_not_block_further_evaluation() -> None:
    class DependentCheck(_CorpusCheck):
        name = "dependent"
        requires = ("record",)

    report = run_checks(_Context(), (_RecordCheck, DependentCheck))

    assert [result.status for result in report.results] == [
        Status.FAILED,
        Status.PASSED,
    ]


def test_dev_replacement_satisfies_dependency_without_restoring_displaced_check() -> None:
    class ProductionCheck(Check[_Context]):
        name = "production"

        def run(self) -> list[Finding]:
            raise AssertionError("the active dev replacement must displace this check")

    class DevCheck(Check[_Context]):
        name = "production-dev"
        dev = True
        replaces = "production"

        def run(self) -> list[Finding]:
            return [
                Finding(
                    "Test.Linter/Archive.Unavailable",
                    {"archive": "chat"},
                    {"actual": "missing"},
                    status=Status.BLOCKED,
                )
            ]

    class DependentCheck(Check[_Context]):
        name = "dependent"
        requires = ("production",)

        def run(self) -> list[Finding]:
            raise AssertionError("the blocked replacement must block this check")

    registry = (ProductionCheck, DevCheck, DependentCheck)

    assert [check.name for check in select_checks(registry, dev=True)] == [
        "production-dev",
        "dependent",
    ]
    report = run_checks(_Context(), registry, dev=True)
    assert [result.status for result in report.results] == [
        Status.BLOCKED,
        Status.BLOCKED,
    ]
    assert report.results[1].reason == "blocked by check(s): production-dev"


def test_dev_replacement_declarations_are_unambiguous_and_known() -> None:
    class ProductionCheck(Check[_Context]):
        name = "production"

    class FirstDevCheck(Check[_Context]):
        name = "first-dev"
        dev = True
        replaces = "production"

    class SecondDevCheck(Check[_Context]):
        name = "second-dev"
        dev = True
        replaces = "production"

    class UnknownDevCheck(Check[_Context]):
        name = "unknown-dev"
        dev = True
        replaces = "missing"

    with pytest.raises(ValueError, match="several active replacements"):
        select_checks((ProductionCheck, FirstDevCheck, SecondDevCheck), dev=True)
    with pytest.raises(ValueError, match="replaces unknown check"):
        select_checks((ProductionCheck, UnknownDevCheck), dev=True)


def test_one_document_drives_complete_summaries_and_bounded_rendering() -> None:
    report = run_checks(
        _Context(),
        (_RecordCheck,),
        execution=lambda ctx: {"records_loaded": len(ctx.records)},
    )
    document = build_linter_document(
        report,
        run_class="Test.Linter.Run",
        limit=1,
    )

    assert document["status"] == "failed"
    assert document["checks"]["summary"] == {
        "run": 1,
        "passed": 0,
        "failed": 1,
        "blocked": 0,
    }
    assert document["poi_classes"][0]["counts"]["total"] == 2
    assert document["poi_instances"]["total"] == 2
    assert document["poi_instances"]["shown"] == 1
    assert "showing 1 of 2" in render_linter_text(document)
