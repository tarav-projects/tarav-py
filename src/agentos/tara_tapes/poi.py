# $kw: ^tara-poi-adapter --from POI.System --from POI.Linter --note [DF] Tara issue messages map to stable placeholder POI classes at the command boundary ^c20260729-49u
from __future__ import annotations

from collections.abc import Callable

from agentos.poi import POIInstance, POILinterReport, POILocation, build_poi_report
from agentos.tara_tapes.core import (
    MANIFEST_FILENAME,
    SEGMENTS_DIRNAME,
    STAGE_DIRNAME,
)
from agentos.wayfinder import poi_class_reference


TARA_TAPE_POI_CODES = (
    "Path.NotDirectory",
    "Manifest.Missing",
    "Manifest.Invalid",
    "Manifest.NotObject",
    "Manifest.TapeName",
    "Manifest.SpecVersion",
    "Manifest.CreatedAt",
    "Segments.Missing",
    "Segments.NotDirectory",
    "Segment.NonFile",
    "Segment.NonJsonl",
    "Segment.BlankLine",
    "Segment.InvalidJson",
    "Segment.Unreadable",
    "Stage.Missing",
    "Stage.NotDirectory",
)


def _contains(value: str) -> Callable[[str], bool]:
    return lambda message: value in message


_ISSUE_CODES: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("Path.NotDirectory", lambda message: message == "path is not a directory"),
    (
        "Manifest.Missing",
        lambda message: message == f"missing {MANIFEST_FILENAME}",
    ),
    (
        "Manifest.Invalid",
        lambda message: message.startswith(f"invalid {MANIFEST_FILENAME}:"),
    ),
    (
        "Manifest.NotObject",
        lambda message: message == f"{MANIFEST_FILENAME} is not a JSON object",
    ),
    ("Manifest.TapeName", lambda message: message == "missing or empty tape_name"),
    ("Manifest.SpecVersion", lambda message: message.startswith("tara_tape_spec is ")),
    ("Manifest.CreatedAt", lambda message: message == "missing or empty created_at"),
    (
        "Segments.Missing",
        lambda message: message == f"missing {SEGMENTS_DIRNAME}/ directory",
    ),
    (
        "Segments.NotDirectory",
        lambda message: message == f"{SEGMENTS_DIRNAME} exists but is not a directory",
    ),
    ("Segment.NonFile", _contains(f"non-file entry in {SEGMENTS_DIRNAME}/")),
    ("Segment.NonJsonl", _contains(f"non-jsonl file in {SEGMENTS_DIRNAME}/")),
    ("Segment.BlankLine", _contains(": blank line at line ")),
    ("Segment.InvalidJson", _contains(": invalid JSON at line ")),
    ("Segment.Unreadable", _contains(": cannot read file:")),
    (
        "Stage.Missing",
        lambda message: message == f"missing {STAGE_DIRNAME}/ directory",
    ),
    (
        "Stage.NotDirectory",
        lambda message: message == f"{STAGE_DIRNAME} exists but is not a directory",
    ),
)


def tara_issue_code(message: str) -> str:
    for code, predicate in _ISSUE_CODES:
        if predicate(message):
            return code
    raise ValueError(f"unclassified Tara tape issue: {message!r}")


def build_tara_linter_report(result: dict[str, object]) -> POILinterReport:
    tape_path = str(result["tape_path"])
    raw_issues = result.get("issues", [])
    if not isinstance(raw_issues, list) or not all(
        isinstance(issue, str) for issue in raw_issues
    ):
        raise ValueError("Tara tape check issues must be a list of strings")

    instances = tuple(
        POIInstance.create(
            class_reference=poi_class_reference(
                "agentos-pkg", f"Tara.Tape.Linter/{tara_issue_code(issue)}"
            ),
            target=POILocation(path=tape_path),
            severity="error",
            situation=issue,
            evidence={"issue": issue, "ordinal": ordinal},
        )
        for ordinal, issue in enumerate(raw_issues)
    )
    return POILinterReport(
        poi_report=build_poi_report(instances),
        summary={
            "poi_count": len(instances),
            "conformant": bool(result.get("conformant")),
        },
        domain={key: value for key, value in result.items() if key != "issues"},
    )


__all__ = [
    "TARA_TAPE_POI_CODES",
    "build_tara_linter_report",
    "tara_issue_code",
]
