# $kw: ^mdblocks-poi-adapter --from Dependency.Profile.Split --from Agent.Navigable.Codebase --note [DF] the POI bridge imports Markdown.Block and POI while the stdlib core imports neither upward --note [DF] reusable mdblocks behavior lives beneath the Python stdlib namespace matching its CLI --supp ^c20260811-62u
from __future__ import annotations

from typing import Any

from tarav.poi import (
    POIInstance,
    POILinterReport,
    POILocation,
    build_poi_report,
    tarav_poi_class_reference,
)
from tarav.wayfinder import Wayfinder


def _mdblocks_poi(issue: dict[str, Any], class_name: str) -> POIInstance:
    evidence = dict(issue.get("details") or {})
    return POIInstance.create(
        class_reference=tarav_poi_class_reference(class_name),
        target=POILocation(
            path=str(issue["path"]),
            line=int(issue["line"]) if issue.get("line") is not None else None,
        ),
        severity=str(issue["severity"]),  # type: ignore[arg-type]
        situation=str(issue["message"]),
        evidence=evidence,
    )


# $kw: Markdown.Block.Linter/Headings.None
# --note [DF] a scanned Markdown file contains no headings in the configured range
# --note [CT] the existing validator reports this condition as a warning
# --note [RJ] class-level interpretation is not yet established
def _no_headings(issue: dict[str, Any]) -> POIInstance:
    return _mdblocks_poi(issue, "Markdown.Block.Linter/Headings.None")


# $kw: Markdown.Block.Linter/CodeFence.Unclosed
# --note [DF] a scanned Markdown file appears to contain an unclosed fenced code block
# --note [CT] the instance preserves the detected ending line
# --note [RJ] class-level repair guidance is not yet established
def _unclosed_code_fence(issue: dict[str, Any]) -> POIInstance:
    return _mdblocks_poi(issue, "Markdown.Block.Linter/CodeFence.Unclosed")


# $kw: Markdown.Block.Linter/Preamble.BeforeFirstBlock
# --note [DF] a scanned Markdown file has nonempty text before its first block anchor
# --note [CT] the existing validator reports the nonempty-line count as evidence
# --note [RJ] class-level interpretation is not yet established
def _preamble_before_first_block(issue: dict[str, Any]) -> POIInstance:
    return _mdblocks_poi(
        issue,
        "Markdown.Block.Linter/Preamble.BeforeFirstBlock",
    )


# $kw: Markdown.Block.Linter/Separator.OutsideBlockSemantics
# --note [DF] a `****` separator is not consumed as a block opening or closing boundary
# --note [CT] the instance preserves the separator line and existing validator message
# --note [RJ] class-level repair guidance is not yet established
def _separator_outside_semantics(issue: dict[str, Any]) -> POIInstance:
    return _mdblocks_poi(
        issue,
        "Markdown.Block.Linter/Separator.OutsideBlockSemantics",
    )


# $kw: Markdown.Block.Linter/Heading.Title.Empty
# --note [DF] a block heading is empty after Markdown sanitization
# --note [CT] the instance preserves the heading line
# --note [RJ] class-level repair guidance is not yet established
def _empty_heading_title(issue: dict[str, Any]) -> POIInstance:
    return _mdblocks_poi(issue, "Markdown.Block.Linter/Heading.Title.Empty")


# $kw: Markdown.Block.Linter/Block.TooLong
# --note [DF] a separator-anchored Markdown block exceeds the existing hard line limit
# --note [CT] the instance preserves line span, limit, and ending-line evidence
# --note [RJ] this migration does not change the configured limit
def _block_too_long(issue: dict[str, Any]) -> POIInstance:
    return _mdblocks_poi(issue, "Markdown.Block.Linter/Block.TooLong")


# $kw: Markdown.Block.Linter/Heading.Title.DuplicateSameLevel
# --note [DF] a Markdown heading repeats an earlier title at the same level
# --note [CT] the instance preserves the first and repeated heading locations
# --note [RJ] class-level interpretation is not yet established
def _duplicate_heading_title(issue: dict[str, Any]) -> POIInstance:
    return _mdblocks_poi(
        issue,
        "Markdown.Block.Linter/Heading.Title.DuplicateSameLevel",
    )


CHECK_REGISTRY = {
    "no_headings": _no_headings,
    "unclosed_code_fence": _unclosed_code_fence,
    "preamble_text_before_first_block": _preamble_before_first_block,
    "separator_outside_block_semantics": _separator_outside_semantics,
    "empty_heading_title": _empty_heading_title,
    "block_too_long": _block_too_long,
    "duplicate_heading_title_same_level": _duplicate_heading_title,
}
MDBLOCKS_POI_CODES = tuple(CHECK_REGISTRY)


def mdblocks_issue_to_poi(issue: dict[str, Any]) -> POIInstance:
    return CHECK_REGISTRY[str(issue["code"])](issue)


def build_mdblocks_linter_report(
    payload: dict[str, Any],
    *,
    wayfinder: Wayfinder,
) -> POILinterReport:
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
            (mdblocks_issue_to_poi(issue) for issue in payload["issues"]),
            wayfinder=wayfinder,
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
    "CHECK_REGISTRY",
    "build_mdblocks_linter_report",
    "mdblocks_issue_to_poi",
]
