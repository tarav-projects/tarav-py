# $kw: ^poi-instance-identity --from POI.System --from POI.Linter --note [CT] POI instances support producer-established identities and advisory severity ^c20260729-49u
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import quote

from agentos.wayfinder import WayfinderReference


POISeverity = Literal["error", "warning", "advisory"]


@dataclass(frozen=True)
class POILocation:
    path: str
    line: int | None = None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("POI target path must be non-empty")
        if self.line is not None and self.line < 1:
            raise ValueError("POI target line must be positive")

    @property
    def display(self) -> str:
        return f"{self.path}:{self.line}" if self.line is not None else self.path

    def __str__(self) -> str:
        return self.display

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"path": self.path}
        if self.line is not None:
            payload["line"] = self.line
            payload["path_line"] = self.display
        return payload


@dataclass(frozen=True)
class POIInstance:
    instance_id: str
    class_reference: WayfinderReference
    target: POILocation
    severity: POISeverity
    situation: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        class_reference: WayfinderReference,
        target: POILocation,
        severity: POISeverity,
        situation: str,
        evidence: dict[str, Any] | None = None,
        instance_id: str | None = None,
    ) -> POIInstance:
        if severity not in {"error", "warning", "advisory"}:
            raise ValueError(f"unsupported POI severity: {severity!r}")
        if not situation:
            raise ValueError("POI situation must be non-empty")
        if instance_id is not None and not instance_id:
            raise ValueError("producer-established POI instance ID must be non-empty")
        normalized_evidence = _normalize_json_object(evidence or {})
        if instance_id is None:
            identity = {
                "class": class_reference.as_dict(),
                "target": target.as_dict(),
                "evidence": normalized_evidence,
            }
            instance_id = hashlib.sha256(
                _canonical_json(identity).encode("utf-8")
            ).hexdigest()[:12]
        return cls(
            instance_id=instance_id,
            class_reference=class_reference,
            target=target,
            severity=severity,
            situation=situation,
            evidence=normalized_evidence,
        )

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "instance_id": self.instance_id,
            "class": self.class_reference.as_dict(),
            "class_sugar": reference_sugar(self.class_reference),
            "target": self.target.as_dict(),
            "severity": self.severity,
            "situation": self.situation,
        }
        if self.evidence:
            payload["evidence"] = self.evidence
        return payload


def reference_sugar(reference: WayfinderReference) -> str:
    if reference.type != "index.block" or not isinstance(reference.address, str):
        return reference.to_json()
    package = quote(reference.root.id, safe="")
    address = quote(reference.address, safe="/.")
    return f"index://{package}/{address}"


def _normalize_json_object(value: dict[str, Any]) -> dict[str, Any]:
    try:
        normalized = json.loads(_canonical_json(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("POI evidence must be JSON-serializable") from exc
    if not isinstance(normalized, dict):
        raise ValueError("POI evidence must be a JSON object")
    return normalized


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = [
    "POIInstance",
    "POILocation",
    "POISeverity",
    "reference_sugar",
]
