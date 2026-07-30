# $kw: ^mdblocks-poi-adapter --from POI.System --from POI.Linter --note [DF] Markdown block issues map once into package-owned POI instances ^c20260729-49u
from __future__ import annotations

from typing import Any

from agentos.poi import (
    POIInstance,
    POILinterReport,
    POILocation,
    build_poi_report,
)
from agentos.wayfinder import poi_class_reference


MDBLOCKS_POI_CLASSES = {
    "no_headings": "Markdown.Block.Linter/Headings.None",
    "unclosed_code_fence": "Markdown.Block.Linter/CodeFence.Unclosed",
    "preamble_text_before_first_block": (
        "Markdown.Block.Linter/Preamble.BeforeFirstBlock"
    ),
    "separator_outside_block_semantics": (
        "Markdown.Block.Linter/Separator.OutsideBlockSemantics"
    ),
    "empty_heading_title": "Markdown.Block.Linter/Heading.Title.Empty",
    "block_too_long": "Markdown.Block.Linter/Block.TooLong",
    "duplicate_heading_title_same_level": (
        "Markdown.Block.Linter/Heading.Title.DuplicateSameLevel"
    ),
}
MDBLOCKS_POI_CODES = tuple(MDBLOCKS_POI_CLASSES)


def mdblocks_issue_to_poi(issue: dict[str, Any]) -> POIInstance:
    evidence = dict(issue.get("details") or {})
    return POIInstance.create(
        class_reference=poi_class_reference(
            "agentos-pkg", MDBLOCKS_POI_CLASSES[str(issue["code"])]
        ),
        target=POILocation(
            path=str(issue["path"]),
            line=int(issue["line"]) if issue.get("line") is not None else None,
        ),
        severity=str(issue["severity"]),  # type: ignore[arg-type]
        situation=str(issue["message"]),
        evidence=evidence,
    )


def build_mdblocks_linter_report(payload: dict[str, Any]) -> POILinterReport:
    files = [
        {key: value for key, value in file_report.items() if key != "issues"}
        for file_report in payload["files"]
    ]
    domain = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "issues",
            "files",
            "issue_count",
            "error_count",
            "warning_count",
        }
    }
    domain["files"] = files
    return POILinterReport(
        poi_report=build_poi_report(
            mdblocks_issue_to_poi(issue) for issue in payload["issues"]
        ),
        summary={
            "file_count": payload["file_count"],
            "poi_count": payload["issue_count"],
            "error_count": payload["error_count"],
            "warning_count": payload["warning_count"],
        },
        domain=domain,
    )


__all__ = [
    "MDBLOCKS_POI_CODES",
    "MDBLOCKS_POI_CLASSES",
    "build_mdblocks_linter_report",
    "mdblocks_issue_to_poi",
]
