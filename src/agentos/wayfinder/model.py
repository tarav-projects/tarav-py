# $kw: ^wayfinder-model --from Wayfinder.Reference --from Wayfinder.Resolution --note [DF] canonical reference, trace, result, and resolution-POI models ^c20260729-46u
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit


REFERENCE_SCHEMA = "agentos.wayfinder.reference.v1"
REFERENCE_KEYS = frozenset({"schema", "type", "root", "address"})
ROOT_KEYS = frozenset({"type", "id"})
INDEX_BLOCK_TYPE = "index.block"
PACKAGE_SKILL_ROOT_TYPE = "package.skill"


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
        return {
            "status": "poi",
            "poi": {
                "instance_id": self.instance_id,
                "class": "Wayfinder.Resolution.POI",
                "kind": self.kind,
                "reference": self.reference.as_dict(),
                "message": self.message,
                "trace": [step.as_dict() for step in self.trace],
                "remembered_location": self.remembered_location,
                "relocation_hints": list(self.relocation_hints),
                "candidates": list(self.candidates),
            },
        }


def index_block_reference(package_id: str, block_path: str) -> WayfinderReference:
    _require_string(package_id, "package id")
    _require_string(block_path, "Index block path")
    return WayfinderReference(
        type=INDEX_BLOCK_TYPE,
        root=WayfinderReferenceRoot(type=PACKAGE_SKILL_ROOT_TYPE, id=package_id),
        address=block_path,
    )


def poi_class_reference(package_id: str, class_name: str) -> WayfinderReference:
    return index_block_reference(package_id, class_name)


def parse_reference(value: str) -> WayfinderReference:
    stripped = value.strip()
    if stripped.startswith("{"):
        return WayfinderReference.from_json(stripped)
    parsed = urlsplit(stripped)
    if parsed.scheme != "index" or not parsed.netloc:
        raise InvalidWayfinderReference(
            "reference sugar must be index://<package-id>/<block-path>"
        )
    if parsed.query or parsed.fragment:
        raise InvalidWayfinderReference("index reference sugar cannot carry query or fragment")
    block_path = unquote(parsed.path.lstrip("/"))
    return index_block_reference(unquote(parsed.netloc), block_path)


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
    "INDEX_BLOCK_TYPE",
    "InvalidWayfinderReference",
    "PACKAGE_SKILL_ROOT_TYPE",
    "REFERENCE_SCHEMA",
    "UnsupportedWayfinderReference",
    "WayfinderError",
    "WayfinderReference",
    "WayfinderReferenceRoot",
    "WayfinderResolutionPOI",
    "WayfinderResolutionResult",
    "WayfinderTraceStep",
    "index_block_reference",
    "parse_reference",
    "poi_class_reference",
]
