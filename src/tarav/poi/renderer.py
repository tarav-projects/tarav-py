# $kw: --from POI.Renderer
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from tarav.wayfinder import (
    Wayfinder,
    WayfinderReference,
    WayfinderResolutionPOI,
    WayfinderResolutionResult,
)

from .model import POIInstance, reference_sugar


_LINE_TYPE_RE = re.compile(r"^\[[A-Z]{2}\]\s+")
_TRAILING_ANCHOR_RE = re.compile(r"\s+\^[A-Za-z0-9][A-Za-z0-9-]*$")


@dataclass(frozen=True)
class POIClassGroup:
    reference: WayfinderReference
    description: str | None
    documentation: WayfinderResolutionResult | WayfinderResolutionPOI
    instances: tuple[POIInstance, ...]

    def as_dict(self) -> dict[str, object]:
        documentation = self.documentation.as_dict()
        if isinstance(self.documentation, WayfinderResolutionResult):
            target = dict(documentation["target"])  # type: ignore[arg-type]
            target.pop("content", None)
            documentation = {
                **documentation,
                "target": target,
            }
        payload: dict[str, object] = {
            "reference": self.reference.as_dict(),
            "reference_sugar": reference_sugar(self.reference),
            "documentation": documentation,
            "instances": [instance.as_dict() for instance in self.instances],
        }
        if self.description is not None:
            payload["description"] = self.description
        return payload


@dataclass(frozen=True)
class POIReport:
    groups: tuple[POIClassGroup, ...]

    @property
    def instances(self) -> tuple[POIInstance, ...]:
        return tuple(instance for group in self.groups for instance in group.instances)

    def as_dict(self) -> dict[str, object]:
        return {
            "classes": [group.as_dict() for group in self.groups],
            "instances": [instance.as_dict() for instance in self.instances],
        }

    def render_text(self) -> str:
        if not self.groups:
            return ""
        lines = ["POIs:"]
        for group in self.groups:
            lines.append("")
            lines.append(str(group.reference.address))
            lines.append(f"  Documentation: {reference_sugar(group.reference)}")
            if group.description is not None:
                lines.append(f"  {group.description}")
            else:
                lines.append(
                    f"  Documentation unresolved: {group.documentation.message}"  # type: ignore[union-attr]
                )
            for instance in group.instances:
                lines.append(
                    f"  - [{instance.severity.upper()}] {instance.target.display} "
                    f"[{instance.instance_id}] - {instance.situation}"
                )
        return "\n".join(lines)


def build_poi_report(
    instances: Iterable[POIInstance],
    *,
    wayfinder: Wayfinder,
) -> POIReport:
    grouped: dict[str, list[POIInstance]] = {}
    references: dict[str, WayfinderReference] = {}
    for instance in instances:
        key = instance.class_reference.to_json()
        grouped.setdefault(key, []).append(instance)
        references.setdefault(key, instance.class_reference)

    groups: list[POIClassGroup] = []
    for key, class_instances in grouped.items():
        reference = references[key]
        documentation = wayfinder.resolve(reference)
        description = (
            _description_from(documentation)
            if isinstance(documentation, WayfinderResolutionResult)
            else None
        )
        groups.append(
            POIClassGroup(
                reference=reference,
                description=description,
                documentation=documentation,
                instances=tuple(class_instances),
            )
        )
    return POIReport(groups=tuple(groups))


def _description_from(resolution: WayfinderResolutionResult) -> str | None:
    content = resolution.target.get("content")
    if not isinstance(content, str):
        return None
    for raw_line in content.splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        line = _LINE_TYPE_RE.sub("", line)
        line = _TRAILING_ANCHOR_RE.sub("", line)
        return line.strip() or None
    return None


__all__ = [
    "POIClassGroup",
    "POIReport",
    "build_poi_report",
]
