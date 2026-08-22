from __future__ import annotations

from dataclasses import dataclass, field

from tarav.poi.runtime import (
    Check,
    Evaluator,
    Finding,
    GateResult,
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


def _structural(_ctx: _Context) -> list[Finding]:
    return []


def _record_check(ctx: _Context) -> list[Finding]:
    return [
        Finding(
            "Test.Linter/Record.Bad",
            {"record_id": record},
            {"expected": "good", "actual": "bad"},
            surface={"workspace": "test"},
        )
        for record in ctx.selected_records()
    ]


def _corpus_check(_ctx: _Context) -> list[Finding]:
    return []


def _dev_check(ctx: _Context) -> list[Finding]:
    return _record_check(ctx)


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
        Check("load", Tier.STRUCTURAL, _structural),
        Check("record", Tier.REPORTABLE, _record_check),
        Check("corpus", Tier.REPORTABLE, _corpus_check),
        Check(
            "record-dev",
            Tier.REPORTABLE,
            _dev_check,
            dev=True,
            replaces="record",
        ),
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
    def blocked(_ctx: _Context) -> list[Finding]:
        return [
            Finding(
                "Test.Linter/Archive.Unavailable",
                {"archive": "chat"},
                {"actual": "missing"},
                status=Status.BLOCKED,
            )
        ]

    def broken_structure(_ctx: _Context) -> list[Finding]:
        return [
            Finding(
                "Test.Linter/Cargo.Unloadable",
                {"record_id": "r0"},
                {"actual": "malformed"},
            )
        ]

    report = run_checks(
        _Context(),
        (
            Check("blocked", Tier.REPORTABLE, blocked),
            Check("failed", Tier.REPORTABLE, _record_check),
        ),
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
        (
            Check("load", Tier.STRUCTURAL, broken_structure),
            Check("never", Tier.REPORTABLE, _record_check),
        ),
    )
    assert stopped.short_circuited is True
    assert [result.name for result in stopped.results] == ["load"]


def test_gate_blocks_once_without_subject_findings() -> None:
    report = run_checks(
        _Context(),
        (
            Check(
                "archive",
                Tier.REPORTABLE,
                _record_check,
                gate=lambda _ctx: GateResult.blocked("archive unavailable"),
            ),
        ),
    )

    assert report.findings == ()
    assert report.blocked == ()
    assert report.results[0].status is Status.BLOCKED
    assert report.results[0].reason == "archive unavailable"


def test_one_document_drives_complete_summaries_and_bounded_rendering() -> None:
    report = run_checks(
        _Context(),
        (Check("record", Tier.REPORTABLE, _record_check),),
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
