# $kw: ^poi-linter-report --from POI.System --from POI.Linter --note [DF] common report keeps POIs diagnostics summaries and domain data distinct ^c20260729-49u
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from tarav._core.errors import CliError

from .model import POILocation
from .renderer import POIReport


@dataclass(frozen=True)
class POIDiagnostic:
    code: str
    target: POILocation
    message: str
    severity: str = "error"
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("diagnostic code must be non-empty")
        if not self.message:
            raise ValueError("diagnostic message must be non-empty")
        if self.severity not in {"error", "warning"}:
            raise ValueError(f"unsupported diagnostic severity: {self.severity!r}")

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code,
            "target": self.target.as_dict(),
            "severity": self.severity,
            "message": self.message,
        }
        if self.evidence:
            payload["evidence"] = _normalize_json_object(self.evidence)
        return payload


@dataclass(frozen=True)
class POILinterReport:
    poi_report: POIReport
    diagnostics: tuple[POIDiagnostic, ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)
    domain: dict[str, Any] = field(default_factory=dict)

    @property
    def instances(self):
        return self.poi_report.instances

    def as_dict(self) -> dict[str, object]:
        poi_payload = self.poi_report.as_dict()
        return {
            "poi_classes": poi_payload["classes"],
            "pois": poi_payload["instances"],
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
            "summary": _normalize_json_object(self.summary),
            "domain": _normalize_json_object(self.domain),
        }

    def render_text(self) -> str:
        sections: list[str] = []
        poi_text = self.poi_report.render_text()
        if poi_text:
            sections.append(poi_text)
        if self.diagnostics:
            lines = ["Diagnostics:"]
            for diagnostic in self.diagnostics:
                lines.append(
                    f"- [{diagnostic.severity.upper()}] "
                    f"{diagnostic.target.display} [{diagnostic.code}] - "
                    f"{diagnostic.message}"
                )
            sections.append("\n".join(lines))
        return "\n\n".join(sections)


_SELECTOR_CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")


@runtime_checkable
class SelectableCheck(Protocol):
    @property
    def code(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def default_on(self) -> bool: ...

    @property
    def structural(self) -> bool: ...


def check_selector(code: str) -> str:
    tail = code.split("/", 1)[-1]
    if tail.startswith("Check."):
        tail = tail[len("Check.") :]
    words: list[str] = []
    for segment in tail.split("."):
        words.extend(_SELECTOR_CAMEL_RE.findall(segment))
    return "-".join(word.lower() for word in words)


def resolve_enabled_checks(checks, *, include=(), exclude=()):
    by_selector = {check_selector(check.code): check for check in checks}
    include_set, exclude_set = set(include), set(exclude)
    unknown = (include_set | exclude_set) - set(by_selector)
    if unknown:
        raise CliError(
            "unknown linter check selector(s): "
            + ", ".join(sorted(unknown))
            + f" (known: {', '.join(sorted(by_selector))})"
        )
    enabled = []
    for selector, check in by_selector.items():
        if check.structural:
            enabled.append(check)
            continue
        on = check.default_on or selector in include_set
        if selector in exclude_set:
            on = False
        if on:
            enabled.append(check)
    return enabled


def check_registry(checks) -> list[dict[str, object]]:
    return [
        {
            "selector": check_selector(check.code),
            "code": check.code,
            "title": check.title,
            "default_on": check.default_on,
            "structural": check.structural,
        }
        for check in checks
    ]


def add_check_selection_args(parser, *, unit: str = "check") -> None:
    parser.add_argument(
        "--check",
        action="append",
        default=[],
        metavar="SELECTOR",
        help=f"Enable a {unit} by selector (repeatable); opts into default-off {unit}s.",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="SELECTOR",
        help=f"Disable a {unit} by selector (repeatable); structural {unit}s cannot be disabled.",
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help=f"List {unit} selectors with their default state and tier, then exit.",
    )


def render_check_registry(rows) -> list[str]:
    lines = []
    for row in rows:
        state = "on " if row["default_on"] else "off"
        tier = "structural" if row["structural"] else "reportable"
        lines.append(f"{row['selector']:<24} [{state}] {tier:<11} {row['title']}")
    return lines


def _normalize_json_object(value: dict[str, Any]) -> dict[str, Any]:
    try:
        normalized = json.loads(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("linter report data must be JSON-serializable") from exc
    if not isinstance(normalized, dict):
        raise ValueError("linter report data must be a JSON object")
    return normalized


__all__ = [
    "POIDiagnostic",
    "POILinterReport",
    "SelectableCheck",
    "add_check_selection_args",
    "check_registry",
    "check_selector",
    "render_check_registry",
    "resolve_enabled_checks",
]
