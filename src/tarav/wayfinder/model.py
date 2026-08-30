# $kw: ^wayfinder-model --from Wayfinder.Reference --from Wayfinder.Resolution --from POI.System --note [DF] canonical reference trace result and bootstrap-safe resolution-POI models ^c20260729-46u --supp common POI migration execution ^c20260729-49u
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

from tarav._core.project import TARAV_PROJECT_ID

REFERENCE_SCHEMA = "tarav.wayfinder.reference.v1"
REFERENCE_KEYS = frozenset({"schema", "type", "root", "address"})
ROOT_KEYS = frozenset({"type", "id"})
MANAGED_BLOCK_TYPE = "managed.block"
PROJECT_ROOT_TYPE = "agentos.project"


class WayfinderError(RuntimeError):
    pass


class InvalidWayfinderReference(WayfinderError):
    pass


class UnsupportedWayfinderReference(WayfinderError):
    pass


@dataclass(frozen=True)
class WayfinderReferenceRoot:
    type: str
    id: str

    def __post_init__(self) -> None:
        _require_string(self.type, "reference root type")
        _require_string(self.id, "reference root id")
        if "/" in self.id:
            raise InvalidWayfinderReference("reference root id cannot contain '/'")

    @classmethod
    def from_dict(cls, payload: object) -> WayfinderReferenceRoot:
        if not isinstance(payload, dict) or set(payload) != ROOT_KEYS:
            raise InvalidWayfinderReference(
                "reference root must contain exactly 'type' and 'id'"
            )
        return cls(type=payload["type"], id=payload["id"])  # type: ignore[arg-type]

    def as_dict(self) -> dict[str, str]:
        return {"type": self.type, "id": self.id}

    @property
    def key(self) -> str:
        return _canonical_json(self.as_dict())


@dataclass(frozen=True)
class WayfinderReference:
    type: str
    root: WayfinderReferenceRoot
    address: object
    schema: str = REFERENCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REFERENCE_SCHEMA:
            raise InvalidWayfinderReference(
                f"unsupported Wayfinder reference schema: {self.schema!r}"
            )
        _require_string(self.type, "reference type")
        object.__setattr__(self, "address", _normalize_json(self.address))

    @classmethod
    def from_dict(cls, payload: object) -> WayfinderReference:
        if not isinstance(payload, dict) or set(payload) != REFERENCE_KEYS:
            raise InvalidWayfinderReference(
                "reference must contain exactly schema, type, root, and address"
            )
        return cls(
            schema=payload["schema"],  # type: ignore[arg-type]
            type=payload["type"],  # type: ignore[arg-type]
            root=WayfinderReferenceRoot.from_dict(payload["root"]),
            address=payload["address"],
        )

    @classmethod
    def from_json(cls, value: str) -> WayfinderReference:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise InvalidWayfinderReference(f"invalid reference JSON: {exc}") from exc
        return cls.from_dict(payload)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "type": self.type,
            "root": self.root.as_dict(),
            "address": self.address,
        }

    def to_json(self) -> str:
        return _canonical_json(self.as_dict())


@dataclass(frozen=True)
class WayfinderTraceStep:
    stage: str
    status: str
    detail: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class WayfinderResolutionResult:
    reference: WayfinderReference
    target: dict[str, object]
    trace: tuple[WayfinderTraceStep, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "resolved",
            "reference": self.reference.as_dict(),
            "target": self.target,
            "trace": [step.as_dict() for step in self.trace],
        }


# $kw: Wayfinder.Resolution.POI
# --note [DF] a `Wayfinder.Resolution.POI` is a `POI.Instance` emitted when a `Wayfinder.Resolution` cannot establish one verified reachable result ^c20260729-288u
# --note [CT] its `POI.Class` identifies the failed condition, including missing, ambiguous, stale, malformed, or unreachable resolution ^c20260729-112u
# --note [CT] the instance carries the original reference, resolution context, resolver trace, registry candidates, and available relocation hints ^c20260729-147u
# --note [PR] the POI gives agents enough mechanical evidence to investigate, relocate, register, and retry the requested resource ^c20260729-350u
# --note [CT] the blocked operation retains its original `Wayfinder.Reference` so repair can retry without rewriting the requesting surface ^c20260729-143u
# --note [CT] the bootstrap instance renders without requiring successful resolution of this documentation block
# --note [RJ] failed mechanical resolution is not proof that the referenced resource does not exist ^c20260729-368u
@dataclass(frozen=True)
class WayfinderResolutionPOI:
    instance_id: str
    kind: str
    reference: WayfinderReference
    message: str
    trace: tuple[WayfinderTraceStep, ...]
    remembered_location: str | None = None
    relocation_hints: tuple[object, ...] = ()
    candidates: tuple[dict[str, object], ...] = ()

    def as_dict(self) -> dict[str, object]:
        class_reference = managed_block_reference(
            TARAV_PROJECT_ID,
            "Wayfinder.Resolution.POI",
        )
        return {
            "status": "poi",
            "poi": {
                "instance_id": self.instance_id,
                "class": class_reference.as_dict(),
                "class_sugar": _reference_sugar(class_reference),
                "target": {"reference": self.reference.as_dict()},
                "severity": "error",
                "situation": self.message,
                "evidence": {
                    "kind": self.kind,
                    "trace": [step.as_dict() for step in self.trace],
                    "remembered_location": self.remembered_location,
                    "relocation_hints": list(self.relocation_hints),
                    "candidates": list(self.candidates),
                },
            },
        }


def managed_block_reference(project_id: str, block_path: str) -> WayfinderReference:
    _require_string(project_id, "project id")
    _require_string(block_path, "managed block path")
    return WayfinderReference(
        type=MANAGED_BLOCK_TYPE,
        root=WayfinderReferenceRoot(type=PROJECT_ROOT_TYPE, id=project_id),
        address=block_path,
    )


def parse_reference(value: str) -> WayfinderReference:
    stripped = value.strip()
    if stripped.startswith("{"):
        return WayfinderReference.from_json(stripped)
    parsed = urlsplit(stripped)
    if parsed.scheme != "block" or not parsed.netloc:
        raise InvalidWayfinderReference(
            "reference sugar must be block://<project-id>/<block-path>"
        )
    if parsed.query or parsed.fragment:
        raise InvalidWayfinderReference(
            "reference sugar cannot carry query or fragment"
        )
    block_path = unquote(parsed.path.lstrip("/"))
    return managed_block_reference(unquote(parsed.netloc), block_path)


def _reference_sugar(reference: WayfinderReference) -> str:
    if reference.type == MANAGED_BLOCK_TYPE:
        return (
            f"block://{quote(reference.root.id, safe='')}/"
            f"{quote(str(reference.address), safe='/.')}"
        )
    return reference.to_json()


def resolution_poi_id(
    reference: WayfinderReference,
    kind: str,
    *,
    remembered_location: str | None,
    candidates: tuple[dict[str, object], ...] = (),
) -> str:
    payload = {
        "reference": reference.as_dict(),
        "kind": kind,
        "remembered_location": remembered_location,
        "candidates": list(candidates),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:12]


def _require_string(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidWayfinderReference(f"{label} must be a non-empty string")


def _normalize_json(value: object) -> object:
    try:
        return json.loads(_canonical_json(value))
    except (TypeError, ValueError) as exc:
        raise InvalidWayfinderReference(
            "reference data must be JSON-serializable"
        ) from exc


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = [
    "MANAGED_BLOCK_TYPE",
    "InvalidWayfinderReference",
    "PROJECT_ROOT_TYPE",
    "REFERENCE_SCHEMA",
    "UnsupportedWayfinderReference",
    "WayfinderError",
    "WayfinderReference",
    "WayfinderReferenceRoot",
    "WayfinderResolutionPOI",
    "WayfinderResolutionResult",
    "WayfinderTraceStep",
    "managed_block_reference",
    "parse_reference",
]
