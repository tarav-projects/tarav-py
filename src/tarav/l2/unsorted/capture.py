"""tarav.l2.unsorted.capture: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

# tarav.breadcrumb df0b5c99e50e194c37d02e1ffda580202fad44a0f2fa0f0a75c928a8dd7b0a9e

import tarav.l2.unsorted.pois as diagram_pois

from tarav.l2.unsorted.contracts import AnnotationDraftInterface
from tarav.l2.lines.records import BlockShipRecord
from tarav.l2.unsorted.constants import CAPTURE_AUTHORIZATION_GATE_TYPE
from tarav.l2.unsorted.constants import CAPTURE_MANIFEST_TYPE
from tarav.l2.unsorted.constants import CAPTURE_RECEIPT_TYPE
from tarav.l2.lines.records import CHATLAS_INDEX_EDITION_RECORD_TYPES
from tarav.l2.unsorted.constants import CHATLAS_INDEX_NAMESPACES
from tarav.l2.unsorted.constants import CHATLAS_INDEX_SHIP_TYPES
from tarav.l2.unsorted.constants import COLLECTION_SHIP_TYPE
from tarav.l2.unsorted.authorization import CaptureAuthorizationGateRecord
from tarav.l2.lines.records import CollectionShipRecord
from pydantic import ConfigDict
from tarav.l2.unsorted.records import DiagramAnnotation
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l2.lines.references import DiagramHostReferenceInterface
from tarav.l2.unsorted.primitives import DiagramModelError
from tarav.l2.unsorted.records import DiagramShip
from tarav.l2.unsorted.primitives import DiagramShipSpecializationError
from tarav.l2.unsorted.pois import DiagramPOI, poi_from_dict
from tarav.l2.unsorted.constants import JsonObject
from tarav.l2.lines.records import LineAnnotationRecord
from tarav.l2.lines.records import LineShipRecord
from typing import Literal
from tarav.l2.unsorted.constants import SCHEMA_VERSION
from tarav.l2.unsorted.contracts import ShipDraftInterface
from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TaravObject
from tarav.l0.kernel import TypeRegistry
from tarav.l0.kernel import TypeShip
from tarav.l2.unsorted.identity import UNSORTED_WORKFLOW_SHIP
from tarav.l2.unsorted.primitives import _array
from tarav.l2.unsorted.primitives import _authorization_gate_ids
from tarav.l2.unsorted.contracts import _dedupe_pois
from tarav.l2.unsorted.primitives import _edition_id
from tarav.l2.lines.records import _line_annotation_editions
from tarav.l2.unsorted.primitives import _object
from tarav.l2.unsorted.io import _read_json
from tarav.l2.unsorted.primitives import _record_is
from tarav.l2.unsorted.primitives import _record_is_any
from tarav.l2.unsorted.primitives import _uuid
from tarav.l0.kernel import entity
from pydantic import field_validator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel
    from tarav.l2.unsorted.evidence import ChatlasEvidence
    from tarav.l2.unsorted.storage import DiagramNamespace
    from collections.abc import Iterable
    from pathlib import Path

class CaptureManifest(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('48c00327-fc23-4cff-99f8-d8f053546aa1'),
            name=CAPTURE_MANIFEST_TYPE,
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal[CAPTURE_MANIFEST_TYPE]
        schema_version: Literal[SCHEMA_VERSION]
        model_ship: str
        ships: list[ShipDraftInterface]
        annotations: list[AnnotationDraftInterface]

        @field_validator("model_ship")
        @classmethod
        def validate_model_ship(cls, value: str) -> str:
            return _uuid(value, field="Capture.Manifest.model_ship")

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> CaptureManifest:
        result = super()._from_record(record_data)
        result._model_ship = record_data.model_ship
        result._ship_drafts = tuple(record_data.ships)
        result._annotations = tuple(record_data.annotations)
        return result

    @classmethod
    def create(
        cls,
        model_ship: str,
        ships: Iterable[ShipDraftInterface] = (),
        annotations: Iterable[AnnotationDraftInterface] = (),
    ) -> CaptureManifest:
        return cls.records.from_record(
            {
                "type": entity(cls).name,
                "schema_version": SCHEMA_VERSION,
                "model_ship": model_ship,
                "ships": [
                    item.model_dump(mode="json", exclude_unset=True) for item in ships
                ],
                "annotations": [
                    item.model_dump(mode="json", exclude_unset=True)
                    for item in annotations
                ],
            }
        )

    @property
    def model_ship(self) -> str:
        return self._model_ship

    @property
    def ship_drafts(self) -> tuple[ShipDraftInterface, ...]:
        return self._ship_drafts

    @property
    def annotations(self) -> tuple[AnnotationDraftInterface, ...]:
        return self._annotations

    @classmethod
    def read(cls, path: Path) -> CaptureManifest:
        registry = TypeRegistry(TaravObject, (cls, CaptureReceipt))
        record_type = registry.resolve(_read_json(path))
        if record_type is not cls:
            raise DiagramModelError("record is not a Capture.Manifest")
        return cls.records.from_record(_read_json(path))

    @classmethod
    def template(
        cls,
        *,
        model_ship: str,
    ) -> CaptureManifest:
        return cls.create(model_ship)

    def check(
        self, namespace: DiagramNamespace, *, evidence: ChatlasEvidence | None = None
    ) -> tuple[DiagramPOI, ...]:
        pois: list[DiagramPOI] = []
        seen: dict[str, JsonObject] = {}
        draft_annotations: list[DiagramAnnotation] = []
        seen_ships: dict[str, JsonObject] = {}
        for index, draft in enumerate(self.ship_drafts):
            path = f"ships[{index}]"
            if draft.id in seen_ships:
                pois.append(
                    diagram_pois.ManifestDuplicateShipId(path=f'{path}.id', message='Capture.Manifest repeats one Ship identity.')
                )
                if seen_ships[draft.id] != draft.record:
                    pois.append(
                        diagram_pois.ManifestShipIdentityRebound(path=f'{path}.id', message='One Ship identity names incompatible content.')
                    )
            seen_ships[draft.id] = draft.record
            ship = DiagramShip(draft.id, namespace, draft.record)
            allowed_ship = ship.type in namespace.allowed_ship_types or (
                namespace.name in CHATLAS_INDEX_NAMESPACES
                and ship.type in CHATLAS_INDEX_SHIP_TYPES
            )
            if namespace.allowed_ship_types and not allowed_ship:
                pois.append(
                    diagram_pois.ManifestShipTypeNotAllowed(path=f'{path}.type', message=f'Namespace {namespace.name} does not allow Ship type {ship.type}.')
                )
            try:
                typed_ship = ship.specialize()
            except DiagramShipSpecializationError as exc:
                pois.append(
                    diagram_pois.ManifestShipSpecializationUnavailable(path=f'{path}.type', message=str(exc), evidence={"error": str(exc)})
                )
                continue
            if isinstance(
                typed_ship, (BlockShipRecord, LineShipRecord, CollectionShipRecord)
            ):
                if typed_ship.model_ship != self.model_ship:
                    pois.append(
                        diagram_pois.ManifestCaptureModelMismatch(path=f'{path}.model_ship', message='Ship is not located in the Capture.Manifest Model.')
                    )
            draft_annotations.extend(typed_ship.edition_annotations())
            for edition_index, annotation in enumerate(
                typed_ship.edition_annotations()
            ):
                pois.extend(
                    namespace.pois(
                        annotation,
                        path=f"{path}.editions[{edition_index}]",
                        evidence=evidence,
                    )
                )
        for index, draft in enumerate(self.annotations):
            path = f"annotations[{index}]"
            if _record_is_any(draft.record, CHATLAS_INDEX_EDITION_RECORD_TYPES):
                pois.append(
                    diagram_pois.ManifestShipEditionInAnnotationCollection(path=f'{path}.type', message='Ship editions belong in Capture.Manifest.ships, not annotations.')
                )
            if draft.id in seen:
                pois.append(
                    diagram_pois.ManifestDuplicateAnnotationId(path=f'{path}.id', message='Capture.Manifest repeats one Annotation identity.')
                )
                if seen[draft.id] != draft.record:
                    pois.append(
                        diagram_pois.ManifestAnnotationIdentityRebound(path=f'{path}.id', message='One Annotation identity names different content.')
                    )
            seen[draft.id] = draft.record
            annotation = DiagramAnnotation(draft.id, namespace, draft.record)
            draft_annotations.append(annotation)
            pois.extend(
                namespace.pois(annotation, path=path, evidence=evidence)
            )
            try:
                model_location = annotation.specialize().model_location()
            except (DiagramError, DiagramModelError):
                model_location = None
            if model_location is not None and model_location[0] != self.model_ship:
                pois.append(
                    diagram_pois.ManifestCaptureModelMismatch(path=f'{path}.{model_location[1]}', message='Annotation is not located in the Capture.Manifest Model.')
                )
        existing_gate_ids = {
            item.id
            for item in namespace.annotations()
            if item.type == CAPTURE_AUTHORIZATION_GATE_TYPE
        }
        draft_gate_ids = {
            item.id
            for item in self.annotations
            if _record_is(item.record, CaptureAuthorizationGateRecord)
        }
        known_gate_ids = existing_gate_ids | draft_gate_ids
        known_collection_ids = {
            item.id for item in namespace.ships() if item.type == COLLECTION_SHIP_TYPE
        } | {
            item.id
            for item in self.ship_drafts
            if _record_is(item.record, CollectionShipRecord)
        }
        for index, draft in enumerate(self.ship_drafts):
            for edition_index, value in enumerate(
                _array(draft.record.get("editions", []), field="Ship.editions")
            ):
                edition = _object(value, field="Ship.editions[]")
                path = f"ships[{index}].editions[{edition_index}]"
                host = edition.get("host")
                if host is not None:
                    reference = DiagramHostReferenceInterface.model_validate(host)
                    if (
                        reference.kind == "collection"
                        and reference.id not in known_collection_ids
                    ):
                        pois.append(
                            diagram_pois.ManifestEditionHostUnresolved(path=f'{path}.host', message='Edition host Collection does not resolve.')
                        )
                for gate_id in _authorization_gate_ids(edition):
                    if gate_id not in known_gate_ids:
                        pois.append(
                            diagram_pois.CaptureAuthorizationGateUnresolved(path=f'{path}.authorization_gates', message=f'Capture.Authorization.Gate does not resolve: {gate_id}.')
                        )
        for index, draft in enumerate(self.annotations):
            records = (
                _line_annotation_editions(draft.record)
                if _record_is(draft.record, LineAnnotationRecord)
                else (draft.record,)
            )
            for record_index, record in enumerate(records):
                path = f"annotations[{index}]"
                if len(records) > 1:
                    path += f".editions[{record_index}]"
                for gate_id in _authorization_gate_ids(record):
                    if gate_id not in known_gate_ids:
                        pois.append(
                            diagram_pois.CaptureAuthorizationGateUnresolved(path=f'{path}.authorization_gates', message=f'Capture.Authorization.Gate does not resolve: {gate_id}.')
                        )
        projection = namespace.project(self.model_ship, extra=draft_annotations)
        pois.extend(projection.pois)
        assertion_engine = namespace.assertion_engine(evidence=evidence)
        pois.extend(
            poi
            for block in projection.blocks
            for poi in block.mechanical_pois(assertion_engine)
        )
        return _dedupe_pois(pois)


class CaptureReceipt(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('1443e564-ae45-4f42-97e8-6877af4162c6'),
            name=CAPTURE_RECEIPT_TYPE,
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal[CAPTURE_RECEIPT_TYPE]
        namespace_id: str
        created: list[str]
        existing: list[str]
        pois: list[JsonObject]
        committed: bool
        base_commit: str
        commit: str | None
        created_ships: list[str]
        updated_ships: list[str]
        created_editions: list[str]
        existing_editions: list[str]
        created_annotations: list[str]
        existing_annotations: list[str]
        authorizations: list[JsonObject]

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> CaptureReceipt:
        result = super()._from_record(record_data)
        result._data = record_data.model_copy(deep=True)
        return result

    @classmethod
    def create(
        cls,
        namespace_id: str,
        created: Iterable[str],
        existing: Iterable[str],
        pois: Iterable[DiagramPOI],
        committed: bool,
        base_commit: str,
        commit: str | None,
        created_ships: Iterable[str] = (),
        updated_ships: Iterable[str] = (),
        created_editions: Iterable[str] = (),
        existing_editions: Iterable[str] = (),
        created_annotations: Iterable[str] = (),
        existing_annotations: Iterable[str] = (),
        authorizations: Iterable[JsonObject] = (),
    ) -> CaptureReceipt:
        return cls.records.from_record(
            {
                "type": entity(cls).name,
                "namespace_id": namespace_id,
                "created": list(created),
                "existing": list(existing),
                "created_ships": list(created_ships),
                "updated_ships": list(updated_ships),
                "created_editions": list(created_editions),
                "existing_editions": list(existing_editions),
                "created_annotations": list(created_annotations),
                "existing_annotations": list(existing_annotations),
                "authorizations": [dict(item) for item in authorizations],
                "pois": [item.to_dict() for item in pois],
                "committed": committed,
                "base_commit": base_commit,
                "commit": commit,
            }
        )

    def __getattr__(self, name: str) -> object:
        data = self._data
        if name == "pois":
            return tuple(poi_from_dict(item) for item in data.pois)
        if name in type(data).model_fields:
            value = getattr(data, name)
            return tuple(value) if isinstance(value, list) else value
        raise AttributeError(name)


def _authorization_coverage(
    ships: Iterable[ShipDraftInterface], annotations: Iterable[AnnotationDraftInterface]
) -> tuple[JsonObject, ...]:
    coverage: dict[str, list[JsonObject]] = {}
    for draft in ships:
        for edition in _array(draft.record.get("editions", []), field="Ship.editions"):
            retained = _object(edition, field="Ship.editions[]")
            for gate in _authorization_gate_ids(retained):
                coverage.setdefault(gate, []).append(
                    {"kind": "edition", "id": _edition_id(retained), "ship": draft.id}
                )
    for draft in annotations:
        records = (
            _line_annotation_editions(draft.record)
            if _record_is(draft.record, LineAnnotationRecord)
            else (draft.record,)
        )
        for record in records:
            for gate in _authorization_gate_ids(record):
                coverage.setdefault(gate, []).append(
                    {"kind": "annotation", "id": draft.id}
                )
    return tuple(
        {"gate": gate, "objects": objects} for gate, objects in coverage.items()
    )
