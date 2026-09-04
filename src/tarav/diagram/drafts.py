"""Durable writable workspaces for proposed Tarav.Diagram changes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from tarav._core.data_root import default_tarav_data_root
from tarav._core.persistence import atomic_write_json

from . import (
    AnnotationDraft,
    CaptureManifest,
    CaptureReceipt,
    ChatlasEvidence,
    DIAGRAM_DRAFT_CLASS,
    Diagram,
    DiagramError,
    Finding,
    ShipDraft,
)


DRAFT_SCHEMA_VERSION = 1
JsonObject = dict[str, Any]


class DiagramDraftError(DiagramError):
    pass


def default_diagram_drafts_root() -> Path:
    return default_tarav_data_root() / "diagram" / "drafts"


@dataclass(frozen=True, slots=True)
class DiagramDraft:
    path: Path
    id: str
    model_ship: str
    status: str
    ships: tuple[ShipDraft, ...] = ()
    annotations: tuple[AnnotationDraft, ...] = ()
    receipt: JsonObject | None = None

    def __post_init__(self) -> None:
        _uuid(self.id, field="Diagram.Draft.id")
        _uuid(self.model_ship, field="Diagram.Draft.model_ship")
        if self.status not in {"Open", "Applied"}:
            raise DiagramDraftError("Diagram.Draft status must be Open or Applied")
        if self.status == "Applied" and self.receipt is None:
            raise DiagramDraftError("Applied Diagram.Draft has no Capture.Receipt")

    def to_dict(self) -> JsonObject:
        payload: JsonObject = {
            "class": DIAGRAM_DRAFT_CLASS,
            "schema_version": DRAFT_SCHEMA_VERSION,
            "id": self.id,
            "model_ship": self.model_ship,
            "status": self.status,
            "ships": [item.to_dict() for item in self.ships],
            "annotations": [item.to_dict() for item in self.annotations],
        }
        if self.receipt is not None:
            payload["receipt"] = self.receipt
        return payload

    @classmethod
    def from_dict(cls, path: Path, value: object) -> DiagramDraft:
        data = _object(value, field="Diagram.Draft")
        if (
            data.get("class") != DIAGRAM_DRAFT_CLASS
            or data.get("schema_version") != DRAFT_SCHEMA_VERSION
        ):
            raise DiagramDraftError("Unsupported Diagram.Draft")
        receipt = data.get("receipt")
        return cls(
            path,
            _string(data.get("id"), field="Diagram.Draft.id"),
            _string(data.get("model_ship"), field="Diagram.Draft.model_ship"),
            _string(data.get("status"), field="Diagram.Draft.status"),
            tuple(
                ShipDraft.from_dict(item)
                for item in _array(data.get("ships", []), field="Diagram.Draft.ships")
            ),
            tuple(
                AnnotationDraft.from_dict(item)
                for item in _array(
                    data.get("annotations", []),
                    field="Diagram.Draft.annotations",
                )
            ),
            _object(receipt, field="Diagram.Draft.receipt")
            if receipt is not None
            else None,
        )

    @classmethod
    def read(cls, path: Path) -> DiagramDraft:
        return cls.from_dict(path.expanduser().resolve(), _read_json(path))

    def manifest(self) -> CaptureManifest:
        return CaptureManifest(self.model_ship, self.ships, self.annotations)

    def check(
        self, diagram: Diagram, *, evidence: ChatlasEvidence | None = None
    ) -> tuple[Finding, ...]:
        model = diagram.model(self.model_ship)
        return self.manifest().check(model.namespace, evidence=evidence)

    def reconcile(
        self,
        *,
        ships: Iterable[ShipDraft] = (),
        annotations: Iterable[AnnotationDraft] = (),
        remove_ships: Iterable[str] = (),
        remove_annotations: Iterable[str] = (),
    ) -> DiagramDraft:
        if self.status != "Open":
            raise DiagramDraftError("Applied Diagram.Draft cannot be revised")
        ship_map = {item.id: item for item in self.ships}
        annotation_map = {item.id: item for item in self.annotations}
        for item in ships:
            current = ship_map.get(item.id)
            ship_map[item.id] = (
                _merge_draft_record(current, item, field="Ship")
                if current is not None
                else item
            )
        for item in annotations:
            current = annotation_map.get(item.id)
            annotation_map[item.id] = (
                _merge_draft_record(current, item, field="Annotation")
                if current is not None
                and "editions" in current.record
                and "editions" in item.record
                else item
            )
        for identity in remove_ships:
            ship_map.pop(_uuid(identity, field="remove_ships[]"), None)
        for identity in remove_annotations:
            annotation_map.pop(_uuid(identity, field="remove_annotations[]"), None)
        return DiagramDraft(
            self.path,
            self.id,
            self.model_ship,
            self.status,
            tuple(ship_map.values()),
            tuple(annotation_map.values()),
        )


@dataclass(frozen=True, slots=True)
class DiagramDraftRepository:
    root: Path

    @classmethod
    def open(cls, root: Path | None = None, *, create: bool = False) -> DiagramDraftRepository:
        resolved = (root or default_diagram_drafts_root()).expanduser().resolve()
        if create:
            resolved.mkdir(parents=True, exist_ok=True)
        if not resolved.is_dir():
            raise DiagramDraftError(f"Diagram.Draft repository is missing: {resolved}")
        return cls(resolved)

    def create(self, model_ship: str, *, draft_id: str | None = None) -> DiagramDraft:
        identity = _uuid(draft_id or str(uuid4()), field="Diagram.Draft.id")
        path = self.root / f"{identity}.json"
        if path.exists():
            raise DiagramDraftError(f"Diagram.Draft already exists: {identity}")
        draft = DiagramDraft(path, identity, model_ship, "Open")
        self.save(draft)
        return draft

    def drafts(self) -> tuple[DiagramDraft, ...]:
        return tuple(DiagramDraft.read(path) for path in sorted(self.root.glob("*.json")))

    def draft(self, selector: str) -> DiagramDraft:
        direct = Path(selector).expanduser()
        if direct.is_file():
            return DiagramDraft.read(direct)
        matches = tuple(item for item in self.drafts() if item.id.startswith(selector))
        if len(matches) != 1:
            raise DiagramDraftError(f"Diagram.Draft does not resolve uniquely: {selector}")
        return matches[0]

    def save(self, draft: DiagramDraft) -> DiagramDraft:
        if draft.path.parent != self.root:
            raise DiagramDraftError("Diagram.Draft belongs to another repository")
        atomic_write_json(draft.path, draft.to_dict(), ensure_ascii=False)
        return DiagramDraft.read(draft.path)

    def reconcile(
        self,
        draft: DiagramDraft,
        *,
        ships: Iterable[ShipDraft] = (),
        annotations: Iterable[AnnotationDraft] = (),
        remove_ships: Iterable[str] = (),
        remove_annotations: Iterable[str] = (),
    ) -> DiagramDraft:
        return self.save(
            draft.reconcile(
                ships=ships,
                annotations=annotations,
                remove_ships=remove_ships,
                remove_annotations=remove_annotations,
            )
        )

    def apply(
        self,
        draft: DiagramDraft,
        diagram: Diagram,
        *,
        evidence: ChatlasEvidence | None = None,
        commit: bool = True,
    ) -> CaptureReceipt:
        if draft.status != "Open":
            raise DiagramDraftError("Diagram.Draft has already been applied")
        receipt = diagram.apply(draft.manifest(), evidence=evidence, commit=commit)
        applied = DiagramDraft(
            draft.path,
            draft.id,
            draft.model_ship,
            "Applied",
            draft.ships,
            draft.annotations,
            receipt.to_dict(),
        )
        self.save(applied)
        return receipt


def read_draft_delta(path: Path) -> tuple[tuple[ShipDraft, ...], tuple[AnnotationDraft, ...]]:
    data = _object(_read_json(path), field="Diagram.Draft.Delta")
    return (
        tuple(
            ShipDraft.from_dict(item)
            for item in _array(data.get("ships", []), field="ships")
        ),
        tuple(
            AnnotationDraft.from_dict(item)
            for item in _array(data.get("annotations", []), field="annotations")
        ),
    )


def _merge_draft_record(
    current: ShipDraft | AnnotationDraft,
    incoming: ShipDraft | AnnotationDraft,
    *,
    field: str,
) -> ShipDraft | AnnotationDraft:
    current_base = {
        key: value for key, value in current.record.items() if key != "editions"
    }
    incoming_base = {
        key: value for key, value in incoming.record.items() if key != "editions"
    }
    if current_base != incoming_base:
        raise DiagramDraftError(
            f"Diagram.Draft cannot rebind {field} identity: {current.id}"
        )
    editions = list(_array(current.record.get("editions", []), field=f"{field}.editions"))
    positions = {
        _edition_uuid(value, field=f"{field}.editions[{index}]"): index
        for index, value in enumerate(editions)
    }
    for value in _array(incoming.record.get("editions", []), field=f"{field}.editions"):
        edition = _object(value, field=f"{field}.editions[]")
        identity = _edition_uuid(edition, field=f"{field}.editions[]")
        if identity in positions:
            editions[positions[identity]] = edition
        else:
            positions[identity] = len(editions)
            editions.append(edition)
    record = {**current_base, "editions": editions}
    return type(current)(current.id, record)


def _read_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DiagramDraftError(f"Cannot read Diagram.Draft JSON: {path}: {exc}") from exc
    return _object(value, field=str(path))


def _object(value: object, *, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise DiagramDraftError(f"{field} must be an object")
    return dict(value)


def _array(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise DiagramDraftError(f"{field} must be an array")
    return value


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DiagramDraftError(f"{field} must be a non-empty string")
    return value


def _edition_uuid(value: object, *, field: str) -> str:
    return _uuid(_object(value, field=field).get("id"), field=f"{field}.id")


def _uuid(value: object, *, field: str) -> str:
    text = _string(value, field=field)
    try:
        return str(UUID(text))
    except ValueError as exc:
        raise DiagramDraftError(f"{field} must be a UUID") from exc


__all__ = [
    "DRAFT_SCHEMA_VERSION",
    "DiagramDraft",
    "DiagramDraftError",
    "DiagramDraftRepository",
    "default_diagram_drafts_root",
    "read_draft_delta",
]
