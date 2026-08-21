from __future__ import annotations

from dataclasses import replace
import json

from tarav.index.linter import CheckResult, Finding, LintReport
from tarav.index.report import build_linter_document, render_linter_text
from tarav.index.verdict import Status


def _report() -> LintReport:
    return LintReport(
        findings=(
            Finding("Index.Linter/Zeta", "record-2", {"value": "z"}, source="z.py:9"),
            Finding("Index.Linter/Alpha", "record-1", {"value": "a"}, source="a.py:7"),
        ),
        blocked=(
            Finding(
                "Index.Linter/Alpha",
                "record-3",
                {"value": "blocked"},
                status=Status.BLOCKED,
                source="a.py:7",
            ),
        ),
        blessed=(
            Finding("Index.Linter/Zeta", "record-4", {"value": "accepted"}, source="z.py:9"),
        ),
        results=(
            CheckResult("alpha-check", Status.FAILED),
            CheckResult("blocked-check", Status.BLOCKED, "archive unavailable"),
        ),
        records_loaded=10,
        records_checked=4,
        surface_files_loaded=2,
        surface_lines_checked=8,
        elapsed_ms=125.5,
        project_id="11111111-1111-4111-8111-111111111111",
        project_root="/tmp/project",
    )


def test_document_keeps_complete_classes_while_limiting_instances() -> None:
    document = build_linter_document(_report(), limit=2)

    assert document["class"] == "Index.Linter.Run"
    assert document["status"] == "failed"
    assert document["execution"] == {
        "project_id": "11111111-1111-4111-8111-111111111111",
        "project_root": "/tmp/project",
        "elapsed_ms": 125.5,
        "records_loaded": 10,
        "records_checked": 4,
        "surface_files_loaded": 2,
        "surface_lines_loaded": 8,
    }
    assert document["checks"]["summary"] == {
        "run": 2,
        "passed": 0,
        "failed": 1,
        "blocked": 1,
    }

    classes = document["poi_classes"]
    assert [row["class_address"] for row in classes] == [
        "Index.Linter/Alpha",
        "Index.Linter/Zeta",
    ]
    assert classes[0]["counts"] == {
        "total": 2,
        "failed": 1,
        "blocked": 1,
        "blessed": 0,
    }
    assert classes[1]["counts"] == {
        "total": 2,
        "failed": 1,
        "blocked": 0,
        "blessed": 1,
    }
    assert classes[0]["sources"] == ["a.py:7"]

    window = document["poi_instances"]
    assert window["total"] == 4
    assert window["matching"] == 4
    assert window["shown"] == 2
    assert window["limit"] == 2
    assert window["truncated"] is True
    assert [item["status"] for item in window["items"]] == ["failed", "failed"]
    assert all(item["class"] == "POI.Instance" for item in window["items"])
    assert all(isinstance(item["class_reference"], dict) for item in window["items"])
    json.dumps(document)


def test_zero_limit_is_summary_only_and_text_renders_the_same_document() -> None:
    document = build_linter_document(_report(), limit=0)

    assert document["poi_instances"]["items"] == []
    assert document["poi_instances"]["shown"] == 0
    assert len(document["poi_classes"]) == 2

    rendered = render_linter_text(document)
    assert "showing 0 of 4 matching POI instances (4 total)" in rendered
    assert "Index.Linter/Alpha" in rendered
    assert "Concentration" not in rendered


def test_instance_filters_do_not_narrow_class_summary_or_run_verdict() -> None:
    report = _report()
    selected_id = report.blocked[0].identity

    document = build_linter_document(
        report,
        limit=20,
        poi_classes=("Index.Linter/Alpha",),
        poi_ids=(selected_id,),
        statuses=("blocked",),
    )

    assert document["status"] == "failed"
    assert len(document["poi_classes"]) == 2
    window = document["poi_instances"]
    assert window["total"] == 4
    assert window["matching"] == 1
    assert window["shown"] == 1
    assert window["items"][0]["instance_id"] == selected_id
    assert window["items"][0]["status"] == "blocked"
    assert document["selection"] == {
        "poi_classes": ["Index.Linter/Alpha"],
        "poi_ids": [selected_id],
        "statuses": ["blocked"],
    }


def test_a_run_with_only_unavailable_evidence_is_blocked_not_failed_or_passed() -> None:
    report = _report()
    document = build_linter_document(
        replace(
            report,
            findings=(),
            blessed=(),
            results=(CheckResult("gate-verifies", Status.BLOCKED, "unavailable"),),
        ),
        limit=20,
    )

    assert document["status"] == "blocked"
    assert document["poi_instances"]["items"][0]["status"] == "blocked"


def test_one_stable_poi_identity_renders_once_with_every_observation() -> None:
    report = _report()
    first = Finding(
        "Index.Linter/Repeated",
        "record-5",
        {"coordinate": "turn-1"},
        source="repeated.py:5",
    )
    second = Finding(
        "Index.Linter/Repeated",
        "record-5",
        {"coordinate": "turn-2"},
        source="repeated.py:5",
    )
    assert first.identity == second.identity

    document = build_linter_document(
        replace(report, findings=(*report.findings, first, second)),
        limit=20,
        poi_classes=("Index.Linter/Repeated",),
    )

    window = document["poi_instances"]
    assert window["matching"] == 1
    assert window["shown"] == 1
    instance = window["items"][0]
    assert instance["instance_id"] == first.identity
    assert instance["evidence"]["observation_count"] == 2
    assert instance["evidence"]["observations"] == [
        {"operands": {"coordinate": "turn-1"}},
        {"operands": {"coordinate": "turn-2"}},
    ]
    repeated_class = next(
        row
        for row in document["poi_classes"]
        if row["class_address"] == "Index.Linter/Repeated"
    )
    assert repeated_class["counts"]["total"] == 1
