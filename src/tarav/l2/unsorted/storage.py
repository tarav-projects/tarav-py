"""tarav.l2.unsorted.storage: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

# tarav.breadcrumb cbe0cddbcaf7

import tarav.l2.unsorted.pois as diagram_pois

from tarav.l2.unsorted.assessment import AssertionEngine
from tarav.l2.unsorted.constants import CHATLAS_INDEX_ANNOTATION_TYPES
from tarav.l2.lines.records import CHATLAS_INDEX_EDITION_RECORD_TYPES
from tarav.l2.unsorted.constants import CHATLAS_INDEX_EDITION_TYPES
from tarav.l2.unsorted.constants import CHATLAS_INDEX_NAMESPACES
from tarav.l2.unsorted.constants import CHATLAS_INDEX_SHIP_TYPES
from tarav.l2.unsorted.constants import CONFIG_SCHEMA_VERSION
from tarav.l2.unsorted.capture import CaptureReceipt
from pydantic import BaseModel, ConfigDict
from tarav.l2.unsorted.constants import DESIGN_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import DIAGRAM_ATTIC
from tarav.l2.unsorted.constants import DIAGRAM_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import DIAGRAM_COLLECTION_OBJECT_TYPE
from tarav.l2.unsorted.constants import DIAGRAM_CONFIG_TYPE
from tarav.l2.unsorted.records import DiagramAnnotation
from tarav.l2.unsorted.primitives import DiagramAnnotationSpecializationError
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l2.models import Model
from tarav.l2.unsorted.primitives import DiagramModelError
from tarav.l2.lines.projection import DiagramProjectionBuilder
from tarav.l2.unsorted.records import DiagramShip
from tarav.l2.unsorted.primitives import DiagramShipSpecializationError
from tarav.l2.unsorted.pois import DiagramPOI
from tarav.l2.unsorted.constants import IMPL_REQ_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import IMPL_REQ_COLLECTION_OBJECT_TYPE
from tarav.l2.unsorted.constants import ISSUE_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import LINE_ANNOTATION_TYPE
from tarav.l2.unsorted.constants import LINE_EDITION_TYPE
from tarav.l2.unsorted.constants import LINE_GATE_ANNOTATION_TYPE
from tarav.l2.unsorted.constants import LINE_SUPPORT_ANNOTATION_TYPE
from tarav.l2.unsorted.constants import LINE_TYPE_ANNOTATION_TYPE
from tarav.l2.lines.records import LineAnnotationRecord
from tarav.l2.lines.records import LineEditionRecord
from tarav.l2.lines.records import LineGateAnnotation
from tarav.l2.unsorted.contracts import LineReview
from tarav.l2.lines.records import LineSupportAnnotation
from tarav.l2.lines.records import LineTypeAnnotation
from typing import Literal
from tarav.l2.unsorted.constants import MODEL_EDITION_TYPE
from tarav.l2.unsorted.constants import MODEL_SHIP_TYPE
from tarav.l2.models.records import ModelEditionRecord
from tarav.l2.models.records import ModelShipRecord
from tarav.l2.unsorted.constants import NAMESPACE_CLASS
from pathlib import Path
from tarav.l2.unsorted.constants import SCHEMA_VERSION
from tarav.l2.unsorted.contracts import ShipDraftInterface
from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TaravObject
from tarav.l0.kernel import TypeRegistry
from tarav.l0.kernel import TypeShip
from tarav.l2.unsorted.identity import UNSORTED_WORKFLOW_SHIP
from tarav.l2.unsorted.constants import USER_TOUCHED_CHATLAS_INDEX
from tarav.l0.kernel import UnknownRecordType
from tarav.l2.unsorted.records import UserTouchedAnnotation
from tarav.l2.unsorted.primitives import _array
from tarav.l2.unsorted.capture import _authorization_coverage
from tarav.l2.unsorted.io import _commit_paths
from tarav.l2.unsorted.primitives import _edition_id
from tarav.l2.lines.records import _line_annotation_editions
from tarav.l2.unsorted.primitives import _object
from tarav.l2.unsorted.io import _read_json
from tarav.l2.unsorted.primitives import _record_is
from tarav.l2.unsorted.primitives import _record_is_any
from tarav.l2.unsorted.primitives import _record_type_reference
from tarav.l2.unsorted.io import _run_git
from tarav.l2.unsorted.primitives import _semantic_record
from tarav.l2.unsorted.records import _sort_annotations
from tarav.l2.unsorted.primitives import _string
from tarav.l2.unsorted.primitives import _timestamp
from tarav.l2.unsorted.primitives import _uuid
from tarav.l2.unsorted.primitives import _validate_editions
from tarav.l0._core.persistence import atomic_write_json
from tarav.l1.project.config import ProjectConfig
from dataclasses import dataclass
from tarav.l2.unsorted.registry import default_diagram_annotation_type_registry
from tarav.l2.lines.types import default_diagram_object_types
from tarav.l2.unsorted.registry import default_diagram_ship_type_registry
from tarav.l0.kernel import entity
from pydantic import field_validator
from uuid import uuid4
from typing import TYPE_CHECKING
from tarav.l0.kernel import LoadedRecord

if TYPE_CHECKING:
    from tarav.l2.unsorted.contracts import AnnotationDraftInterface
    from typing import Any
    from pydantic import BaseModel
    from tarav.l2.unsorted.capture import CaptureManifest
    from tarav.l2.unsorted.evidence import ChatlasEvidence
    from tarav.l2.lines.references import DiagramArgumentReferenceInterface
    from tarav.l2.lines.block import DiagramBlock
    from tarav.l2.lines.collection import DiagramCollection
    from tarav.l2.lines.line import DiagramLineShip
    from tarav.l2.lines.types import DiagramObjectTypeRegistry
    from tarav.l2.lines.projection import DiagramProjection
    from collections.abc import Iterable
    from tarav.l2.unsorted.constants import JsonObject
    from collections.abc import Mapping
    from tarav.l2.unsorted.records import TypedAnnotation
    from tarav.l2.unsorted.records import TypedShip

@dataclass(frozen=True, slots=True)
class DiagramNamespace:
    root: Path
    id: str
    name: str
    allowed_ship_types: tuple[str, ...]
    allowed_annotation_types: tuple[str, ...]
    allowed_block_types: tuple[str, ...] = ()
    allowed_collection_types: tuple[str, ...] = ()
    require_block_type: bool = False

    @property
    def ships_root(self) -> Path:
        return self.root / "ships"

    @property
    def annotations_root(self) -> Path:
        return self.root / "annotations"

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        name: str,
        namespace_id: str | None = None,
        allowed_ship_types: Iterable[str] = (),
        allowed_annotation_types: Iterable[str] = (),
        allowed_block_types: Iterable[str] = (),
        allowed_collection_types: Iterable[str] = (),
        require_block_type: bool = False,
    ) -> DiagramNamespace:
        resolved = root.expanduser().resolve()
        if resolved.exists() and any(resolved.iterdir()):
            return cls.open(resolved)
        resolved.mkdir(parents=True, exist_ok=True)
        (resolved / "ships").mkdir()
        (resolved / "annotations").mkdir()
        _run_git(resolved, "init", "-q")
        atomic_write_json(
            resolved / "namespace.json",
            {
                "class": NAMESPACE_CLASS,
                "schema_version": SCHEMA_VERSION,
                "id": namespace_id or str(uuid4()),
                "name": name,
                "allowed_ship_types": list(allowed_ship_types),
                "allowed_annotation_types": list(allowed_annotation_types),
                "allowed_block_types": list(allowed_block_types),
                "allowed_collection_types": list(allowed_collection_types),
                "require_block_type": require_block_type,
            },
        )
        _commit_paths(
            resolved,
            (Path("namespace.json"),),
            message="diagram(namespace): initialize",
        )
        return cls.open(resolved)

    @classmethod
    def create_user_touched_chatlas_index(cls, root: Path) -> DiagramNamespace:
        return cls.create(
            root,
            name=USER_TOUCHED_CHATLAS_INDEX,
            allowed_ship_types=CHATLAS_INDEX_SHIP_TYPES,
            allowed_annotation_types=CHATLAS_INDEX_ANNOTATION_TYPES,
            allowed_block_types=(
                DIAGRAM_BLOCK_OBJECT_TYPE,
                DESIGN_BLOCK_OBJECT_TYPE,
                IMPL_REQ_BLOCK_OBJECT_TYPE,
                ISSUE_BLOCK_OBJECT_TYPE,
            ),
            allowed_collection_types=(
                DIAGRAM_COLLECTION_OBJECT_TYPE,
                IMPL_REQ_COLLECTION_OBJECT_TYPE,
            ),
            require_block_type=True,
        )

    @classmethod
    def create_diagram_attic(cls, root: Path) -> DiagramNamespace:
        return cls.create(
            root,
            name=DIAGRAM_ATTIC,
            allowed_ship_types=CHATLAS_INDEX_SHIP_TYPES,
            allowed_annotation_types=CHATLAS_INDEX_ANNOTATION_TYPES,
            allowed_block_types=(
                DIAGRAM_BLOCK_OBJECT_TYPE,
                DESIGN_BLOCK_OBJECT_TYPE,
                IMPL_REQ_BLOCK_OBJECT_TYPE,
                ISSUE_BLOCK_OBJECT_TYPE,
            ),
            allowed_collection_types=(
                DIAGRAM_COLLECTION_OBJECT_TYPE,
                IMPL_REQ_COLLECTION_OBJECT_TYPE,
            ),
            require_block_type=True,
        )

    @classmethod
    def open(cls, root: Path) -> DiagramNamespace:
        resolved = root.expanduser().resolve()
        if (
            not (resolved / ".git").is_dir()
            or not (resolved / "ships").is_dir()
            or not (resolved / "annotations").is_dir()
        ):
            raise DiagramError(f"Diagram Namespace repository is invalid: {resolved}")
        data = _read_json(resolved / "namespace.json")
        if (
            data.get("class") != NAMESPACE_CLASS
            or data.get("schema_version") != SCHEMA_VERSION
        ):
            raise DiagramError(f"Diagram Namespace definition is invalid: {resolved}")
        name = _string(data.get("name"), field="Namespace.name")
        default_block_types = (
            (
                DIAGRAM_BLOCK_OBJECT_TYPE,
                DESIGN_BLOCK_OBJECT_TYPE,
                IMPL_REQ_BLOCK_OBJECT_TYPE,
                ISSUE_BLOCK_OBJECT_TYPE,
            )
            if name in CHATLAS_INDEX_NAMESPACES
            else ()
        )
        default_collection_types = (
            (DIAGRAM_COLLECTION_OBJECT_TYPE, IMPL_REQ_COLLECTION_OBJECT_TYPE)
            if name in CHATLAS_INDEX_NAMESPACES
            else ()
        )
        return cls(
            resolved,
            _uuid(data.get("id"), field="Namespace.id"),
            name,
            tuple(
                _string(item, field="allowed_ship_types[]")
                for item in _array(
                    data.get("allowed_ship_types", []), field="allowed_ship_types"
                )
            ),
            tuple(
                _string(item, field="allowed_annotation_types[]")
                for item in _array(
                    data.get("allowed_annotation_types", []),
                    field="allowed_annotation_types",
                )
            ),
            tuple(
                _string(item, field="allowed_block_types[]")
                for item in _array(
                    data.get("allowed_block_types") or list(default_block_types),
                    field="allowed_block_types",
                )
            ),
            tuple(
                _string(item, field="allowed_collection_types[]")
                for item in _array(
                    data.get("allowed_collection_types")
                    or list(default_collection_types),
                    field="allowed_collection_types",
                )
            ),
            (
                bool(data["require_block_type"])
                if data.get("require_block_type") is not None
                else name in CHATLAS_INDEX_NAMESPACES
            ),
        )

    def object_types(self) -> DiagramObjectTypeRegistry:
        return default_diagram_object_types()

    def ship(self, ship_id: str) -> DiagramShip:
        ship_id = _uuid(ship_id, field="Ship.id")
        path = self.ships_root / f"{ship_id}.json"
        if not path.is_file():
            raise DiagramError(f"Diagram Ship not found: {ship_id}")
        return DiagramShip(ship_id, self, _read_json(path))

    def ships(self) -> tuple[DiagramShip, ...]:
        return tuple(
            DiagramShip(path.stem, self, _read_json(path))
            for path in sorted(self.ships_root.glob("*.json"))
        )

    def specialize_ship(self, ship: DiagramShip) -> TypedShip:
        try:
            ship_class = default_diagram_ship_type_registry().resolve(ship.record)
        except UnknownRecordType:
            raise DiagramShipSpecializationError(
                f"Ship type is not registered in Namespace {self.name}: {ship.type}"
            ) from None
        try:
            return ship_class(ship)
        except DiagramModelError as exc:
            raise DiagramShipSpecializationError(
                f"Ship {ship.id} cannot be specialized as {ship.type}: {exc}"
            ) from exc

    def editions(self) -> tuple[DiagramAnnotation, ...]:
        """Return Ship editions through the legacy projection adapter."""

        annotations: list[DiagramAnnotation] = []
        for ship in self.ships():
            try:
                annotations.extend(ship.specialize().edition_annotations())
            except DiagramShipSpecializationError:
                continue
        return tuple(annotations)

    def _projection_records(self) -> tuple[DiagramAnnotation, ...]:
        return _sort_annotations((*self.editions(), *self.annotations()))

    def standalone_annotations(self) -> tuple[DiagramAnnotation, ...]:
        return tuple(
            DiagramAnnotation(path.stem, self, _read_json(path))
            for path in sorted(self.annotations_root.glob("*.json"))
        )

    def annotation(self, annotation_id: str) -> DiagramAnnotation:
        annotation_id = _uuid(annotation_id, field="Annotation.id")
        path = self.annotations_root / f"{annotation_id}.json"
        if path.is_file():
            return DiagramAnnotation(annotation_id, self, _read_json(path))
        raise DiagramError(f"Diagram Annotation not found: {annotation_id}")

    def edition(self, edition_id: str) -> DiagramAnnotation:
        """Resolve one Ship edition through the projection adapter."""

        edition_id = _uuid(edition_id, field="Ship.Edition.id")
        matches = tuple(item for item in self.editions() if item.id == edition_id)
        if len(matches) == 1:
            return matches[0]
        raise DiagramError(f"Diagram Ship edition not found: {edition_id}")

    def annotations(self) -> tuple[DiagramAnnotation, ...]:
        """Return claims stored in the Namespace's Annotation collection."""

        return _sort_annotations(self.standalone_annotations())

    def annotations_for_argument(self, identity: str) -> tuple[DiagramAnnotation, ...]:
        """Return Line.Annotations whose retained history names one identity."""

        target = _uuid(identity, field="Argument.Reference.id")
        result: list[DiagramAnnotation] = []
        for annotation in self.annotations():
            if annotation.type != LINE_ANNOTATION_TYPE:
                continue
            try:
                typed = annotation.specialize()
            except DiagramAnnotationSpecializationError:
                continue
            if isinstance(typed, LineAnnotationRecord) and typed.references(target):
                result.append(annotation)
        return tuple(result)

    def resolves_argument(self, reference: DiagramArgumentReferenceInterface) -> bool:
        """Resolve a local Argument.Reference without interpreting its relation."""

        if reference.namespace_id != self.id:
            return False
        try:
            if reference.kind == "ship":
                self.ship(reference.id)
                return True
            if reference.kind == "annotation":
                self.annotation(reference.id)
                return True
            self.edition(reference.id)
            return True
        except DiagramError:
            if reference.kind != "edition":
                return False
            return any(
                annotation.type == LINE_ANNOTATION_TYPE
                and any(
                    _edition_id(edition) == reference.id
                    for edition in _line_annotation_editions(annotation.record)
                )
                for annotation in self.annotations()
            )

    def assertions_for(self, annotation: DiagramAnnotation) -> tuple[JsonObject, ...]:
        if (
            self.name not in CHATLAS_INDEX_NAMESPACES
            and annotation.type != LINE_ANNOTATION_TYPE
        ):
            return ()
        typed = self.specialize(annotation)
        if isinstance(typed, ModelEditionRecord):
            return typed.type_assertions()
        assertions: tuple[JsonObject, ...] = (
            {"type": "Semantic.Record.Representation.Assertion"},
        )
        if isinstance(typed, UserTouchedAnnotation) or (
            isinstance(typed, LineAnnotationRecord) and typed.support
        ):
            assertions += ({"type": "User.Touch.Support.Assertion"},)
        return (*assertions, *typed.type_assertions())

    def assertion_engine(
        self, *, evidence: ChatlasEvidence | None = None
    ) -> AssertionEngine:
        return AssertionEngine(evidence=evidence)

    def specialize(self, annotation: DiagramAnnotation) -> TypedAnnotation:
        registry = default_diagram_annotation_type_registry(
            include_chatlas_index_types=self.name in CHATLAS_INDEX_NAMESPACES
        )
        try:
            annotation_class = registry.resolve(annotation.record)
        except UnknownRecordType:
            raise DiagramAnnotationSpecializationError(
                f"Annotation type is not registered in Namespace {self.name}: {annotation.type}"
            ) from None
        try:
            return annotation_class(annotation)
        except DiagramModelError as exc:
            raise DiagramAnnotationSpecializationError(
                f"Annotation {annotation.id} cannot be specialized as {annotation.type}: {exc}"
            ) from exc

    def pois(
        self,
        annotation: DiagramAnnotation,
        *,
        path: str,
        evidence: ChatlasEvidence | None = None,
    ) -> tuple[DiagramPOI, ...]:
        pois: list[DiagramPOI] = []
        built_in_chatlas_types = set(
            (*CHATLAS_INDEX_EDITION_TYPES, *CHATLAS_INDEX_ANNOTATION_TYPES)
        )
        allowed = annotation.type in self.allowed_annotation_types or (
            self.name in CHATLAS_INDEX_NAMESPACES
            and annotation.type in built_in_chatlas_types
        )
        if self.allowed_annotation_types and not allowed:
            pois.append(
                diagram_pois.AnnotationAnnotationTypeNotAllowed(path=f'{path}.type', message=f'Namespace {self.name} does not allow Annotation type {annotation.type}.')
            )
        try:
            typed = self.specialize(annotation)
        except DiagramAnnotationSpecializationError as exc:
            pois.append(
                diagram_pois.AnnotationAnnotationSpecializationUnavailable(path=f'{path}.type', message=str(exc), evidence={"error": str(exc)})
            )
            return tuple(pois)
        if isinstance(typed, UserTouchedAnnotation):
            if not typed.support:
                pois.append(
                    diagram_pois.AnnotationEmptySupportSet(path=f'{path}.support', message='Annotation has no rooted User.Turn support.')
                )
            if evidence is not None:
                pois.extend(evidence.check(typed, path=path))
            pois.append(
                diagram_pois.AnnotationArchiveGroundingUnassessable(path=path, message='Chatlas-to-Archive grounding is not yet mechanically assessable.')
            )
        pois.extend(typed.type_pois(path=path, evidence=evidence))
        assessment_path = (
            f"{path}.editions[-1]" if isinstance(typed, LineAnnotationRecord) else path
        )
        assessment = self.assertion_engine(evidence=evidence).assess(
            typed, path=assessment_path
        )
        pois.extend(assessment.pois)
        if assessment.standing == "UnAsserted":
            pois.append(
                diagram_pois.AnnotationSemanticRecordUnasserted(path=path, message='The semantic record is missing one or more required Assertion scores.')
            )
        return tuple(pois)

    def append(
        self,
        drafts: Iterable[ShipDraftInterface | AnnotationDraftInterface],
        *,
        pois: Iterable[DiagramPOI] = (),
        message: str = "diagram: append annotations",
        commit: bool = True,
    ) -> CaptureReceipt:
        ship_drafts: list[ShipDraftInterface] = []
        annotation_drafts: list[AnnotationDraftInterface] = []
        for draft in drafts:
            if isinstance(draft, ShipDraftInterface):
                ship_drafts.append(draft)
            else:
                annotation_drafts.append(draft)
        return self._write_records(
            ship_drafts,
            annotation_drafts,
            pois=pois,
            message=message,
            commit=commit,
        )

    def _write_records(
        self,
        ships: Iterable[ShipDraftInterface],
        annotations: Iterable[AnnotationDraftInterface],
        *,
        pois: Iterable[DiagramPOI] = (),
        message: str,
        commit: bool,
    ) -> CaptureReceipt:
        ships = tuple(ships)
        annotations = tuple(annotations)
        authorization_coverage = _authorization_coverage(ships, annotations)
        base_commit = _run_git(self.root, "rev-parse", "HEAD")
        created: list[str] = []
        existing: list[str] = []
        created_ships: list[str] = []
        updated_ships: list[str] = []
        created_editions: list[str] = []
        existing_editions: list[str] = []
        created_annotations: list[str] = []
        existing_annotations: list[str] = []
        pending: dict[Path, JsonObject] = {}
        loaded_ships: dict[str, JsonObject | None] = {}
        for draft in ships:
            path = self.ships_root / f"{draft.id}.json"
            current = loaded_ships.get(draft.id)
            if draft.id not in loaded_ships:
                current = _read_json(path) if path.exists() else None
            merged, added, repeated = _merge_ship_record(
                draft.id,
                current,
                draft.record,
            )
            loaded_ships[draft.id] = merged
            created.extend(added)
            existing.extend(repeated)
            created_editions.extend(added)
            existing_editions.extend(repeated)
            if current is None:
                created_ships.append(draft.id)
            elif added:
                updated_ships.append(draft.id)
            if current is None or merged != current:
                pending[path] = merged

        claimed: dict[str, JsonObject] = {}
        for draft in annotations:
            if _record_is_any(draft.record, CHATLAS_INDEX_EDITION_RECORD_TYPES):
                raise DiagramError(
                    "Diagram Ship editions cannot be stored in annotations/: "
                    f"{draft.id}"
                )
            if draft.id in claimed:
                if claimed[draft.id] != draft.record:
                    raise DiagramError(
                        f"Diagram Annotation identity cannot be rebound: {draft.id}"
                    )
                continue
            claimed[draft.id] = draft.record
            path = self.annotations_root / f"{draft.id}.json"
            if _record_is(draft.record, LineAnnotationRecord):
                current = _read_json(path) if path.exists() else None
                merged, added, repeated = _merge_line_annotation_record(
                    draft.id,
                    current,
                    draft.record,
                )
                created.extend(added)
                existing.extend(repeated)
                created_editions.extend(added)
                existing_editions.extend(repeated)
                if current is None:
                    created.append(draft.id)
                    created_annotations.append(draft.id)
                else:
                    existing.append(draft.id)
                    existing_annotations.append(draft.id)
                if current is None or merged != current:
                    pending[path] = merged
                continue
            if path.exists():
                if _semantic_record(_read_json(path)) != _semantic_record(draft.record):
                    raise DiagramError(
                        f"Diagram Annotation identity cannot be rebound: {draft.id}"
                    )
                existing.append(draft.id)
                existing_annotations.append(draft.id)
            else:
                pending[path] = {**draft.record, "recorded_at": _timestamp()}
                created.append(draft.id)
                created_annotations.append(draft.id)
        for path, record in pending.items():
            atomic_write_json(path, record, ensure_ascii=False)
        committed = bool(pending) and commit
        if committed:
            _commit_paths(
                self.root,
                (path.relative_to(self.root) for path in pending),
                message=message,
            )
        return CaptureReceipt.create(
            self.id,
            tuple(created),
            tuple(existing),
            tuple(pois),
            committed,
            base_commit,
            _run_git(self.root, "rev-parse", "HEAD") if committed else None,
            tuple(dict.fromkeys(created_ships)),
            tuple(dict.fromkeys(updated_ships)),
            tuple(created_editions),
            tuple(existing_editions),
            tuple(created_annotations),
            tuple(existing_annotations),
            authorization_coverage,
        )

    def create_model(
        self, *, model_ship: str | None = None, label: str | None = None
    ) -> Model:
        from tarav.l2.models.errors import require_models
        require_models()
        ship = model_ship or str(uuid4())
        edition_id = str(uuid4())
        draft = ShipDraftInterface.from_record(
            ship,
            {
                "type": MODEL_SHIP_TYPE,
                "editions": [
                    {
                        "id": edition_id,
                        "data": {"label": label} if label else {},
                    }
                ],
            },
        )
        self._write_records(
            (draft,),
            (),
            message="diagram(model): create",
            commit=True,
        )
        return Model(ship, self, edition_id)

    def model(self, model_ship: str) -> Model:
        from tarav.l2.models.errors import require_models
        require_models()
        ship = _uuid(model_ship, field="Model.ship")
        try:
            typed = self.ship(ship).specialize()
        except (DiagramError, DiagramShipSpecializationError) as exc:
            raise DiagramError(
                f"Diagram Model does not resolve uniquely in Namespace {self.name}: {ship}"
            ) from exc
        if not isinstance(typed, ModelShipRecord) or not typed.editions:
            raise DiagramError(
                f"Diagram Model does not resolve uniquely in Namespace {self.name}: {ship}"
            )
        return Model(ship, self, _edition_id(typed.editions[-1]))

    def models(self) -> tuple[Model, ...]:
        from tarav.l2.models.errors import require_models
        require_models()
        result: list[Model] = []
        for ship in self.ships():
            try:
                typed = ship.specialize()
            except DiagramShipSpecializationError:
                continue
            if isinstance(typed, ModelShipRecord) and typed.editions:
                result.append(
                    Model(ship.id, self, _edition_id(typed.editions[-1]))
                )
        return tuple(result)

    def apply(
        self,
        manifest: CaptureManifest,
        *,
        evidence: ChatlasEvidence | None = None,
        commit: bool = True,
    ) -> CaptureReceipt:
        from tarav.l2.models.errors import require_models
        require_models()
        self.model(manifest.model_ship)
        ship_drafts = list(manifest.ship_drafts)
        annotation_drafts = list(manifest.annotations)
        count = len(ship_drafts) + len(annotation_drafts)
        return self._write_records(
            ship_drafts,
            annotation_drafts,
            pois=manifest.check(self, evidence=evidence),
            message=f"diagram(capture): apply {count} record(s)",
            commit=commit,
        )

    def model_annotations(self, model_ship: str) -> tuple[DiagramAnnotation, ...]:
        """Return projection inputs for one Model, including Ship editions."""

        ship = _uuid(model_ship, field="Model.ship")
        direct = tuple(
            item
            for item in self._projection_records()
            if item.type != MODEL_EDITION_TYPE
            if (
                isinstance(item.record.get("location"), dict)
                and item.record["location"].get("model_ship") == ship
            )
            or item.record.get("model_ship") == ship
        )
        return self._with_line_gate_annotations(direct)

    def project(
        self,
        model_ship: str,
        *,
        extra: Iterable[DiagramAnnotation] = (),
        include_collection_content: bool = False,
    ) -> DiagramProjection:
        from tarav.l2.models.errors import require_models
        require_models()
        ship = _uuid(model_ship, field="Model.ship")
        combined = {
            item.id: item for item in (*self.model_annotations(ship), *tuple(extra))
        }
        typed: list[TypedAnnotation] = []
        # Existing records are already ordered by their retained timestamps.
        # Preserve ``extra`` order for new Ships so a Draft's edition order is
        # not accidentally replaced by UUID lexical order.
        for annotation in combined.values():
            try:
                specialized = self.specialize(annotation)
            except DiagramAnnotationSpecializationError:
                continue
            try:
                location = specialized.model_location()
            except (DiagramError, DiagramModelError):
                location = None
            if location is None or location[0] == ship:
                typed.append(specialized)
        builder = DiagramProjectionBuilder(
            self,
            ship,
            typed,
            include_collection_content=include_collection_content,
        )
        for annotation in typed:
            annotation.contribute(builder)
        return builder.build()

    def block_annotations(self, block_ship: str) -> tuple[DiagramAnnotation, ...]:
        ship = _uuid(block_ship, field="Block.ship")
        direct = tuple(
            item
            for item in self._projection_records()
            if isinstance(item.record.get("location"), dict)
            and item.record["location"].get("block_ship") == ship
        )
        related = self.annotations_for_argument(ship)
        return self._with_line_gate_annotations(_sort_annotations((*direct, *related)))

    def _with_line_gate_annotations(
        self, direct: tuple[DiagramAnnotation, ...]
    ) -> tuple[DiagramAnnotation, ...]:
        direct_ids = {item.id for item in direct}
        gates = tuple(
            item
            for item in self.annotations()
            if item.type == LINE_GATE_ANNOTATION_TYPE
            and item.record.get("target_edition") in direct_ids
        )
        return (*direct, *gates)

    def line(self, line_ship: str) -> tuple[TypedAnnotation, ...]:
        ship = _uuid(line_ship, field="Line.ship")
        result: list[TypedAnnotation] = []
        for annotation in self._projection_records():
            if annotation.type in (
                LINE_EDITION_TYPE,
                LINE_TYPE_ANNOTATION_TYPE,
                LINE_SUPPORT_ANNOTATION_TYPE,
                LINE_GATE_ANNOTATION_TYPE,
            ):
                typed = self.specialize(annotation)
                if (
                    isinstance(
                        typed,
                        (
                            LineEditionRecord,
                            LineTypeAnnotation,
                            LineSupportAnnotation,
                            LineGateAnnotation,
                        ),
                    )
                    and typed.location.line_ship == ship
                ):
                    result.append(typed)
        return tuple(result)

    def line_review(
        self,
        line_ship: str,
        *,
        evidence: ChatlasEvidence | None,
        assertion_engine: AssertionEngine | None = None,
    ) -> LineReview:
        ship = _uuid(line_ship, field="Line.ship")
        annotations = self.line(ship)
        if not any(isinstance(item, LineEditionRecord) for item in annotations):
            raise DiagramError(f"Diagram Line not found: {ship}")
        engine = assertion_engine or self.assertion_engine(evidence=evidence)
        assessments = tuple(
            gate_assessment
            for item in annotations
            if isinstance(item, (LineEditionRecord, LineGateAnnotation))
            for gate_assessment in engine.assess(item).gate_assessments
        )
        pois = tuple(
            poi for assessment in assessments for poi in assessment.pois
        )
        reviewed = any(item.standing == "Passed" for item in assessments)
        if not reviewed:
            pois = (
                *pois,
                diagram_pois.LineUnreviewed(path=f'line.{ship}', message='Line ship has no Annotation with a passing Verbatim.Gate.'),
            )
        return LineReview(
            ship,
            "Reviewed" if reviewed else "Unreviewed",
            assessments,
            pois,
        )


class DiagramConfiguration(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('16cf8e4f-5a1d-4a8e-9954-e30375c0d554'),
            name=DIAGRAM_CONFIG_TYPE,
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal[DIAGRAM_CONFIG_TYPE]
        schema_version: Literal[CONFIG_SCHEMA_VERSION]
        namespace_locations: list[str]
        default_namespace_id: str | None

        @field_validator("default_namespace_id")
        @classmethod
        def validate_default_namespace(cls, value: str | None) -> str | None:
            return (
                _uuid(value, field="default_namespace_id")
                if value is not None
                else None
            )

    @classmethod
    def _from_record(cls, loaded: LoadedRecord) -> DiagramConfiguration:
        result = super()._from_record(loaded)
        result._namespace_locations = tuple(
            Path(item).expanduser().resolve()
            for item in loaded.data.namespace_locations
        )
        result._default_namespace_id = loaded.data.default_namespace_id
        return result

    @property
    def path(self) -> Path:
        if self.source is None:
            raise DiagramError("Diagram.Configuration has no retained source")
        return self.source

    @property
    def namespace_locations(self) -> tuple[Path, ...]:
        return self._namespace_locations

    @property
    def default_namespace_id(self) -> str | None:
        return self._default_namespace_id

    @staticmethod
    def default_path() -> Path:
        return (Path.home() / ".tarav" / "diagram.json").resolve()

    @classmethod
    def load(
        cls, path: Path | None = None, *, create: bool = False
    ) -> DiagramConfiguration:
        resolved = (path or cls.default_path()).expanduser().resolve()
        if not resolved.exists():
            if not create:
                raise DiagramError(f"Diagram configuration not found: {resolved}")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                resolved,
                {
                    "type": entity(cls).name,
                    "schema_version": CONFIG_SCHEMA_VERSION,
                    "namespace_locations": [],
                    "default_namespace_id": None,
                },
            )
        data = _read_json(resolved)
        registry = TypeRegistry(TaravObject, (cls,))
        if registry.resolve(data) is not cls:
            raise DiagramError(f"Diagram configuration is invalid: {resolved}")
        result = cls.records.from_record(data)
        result.source = resolved
        return result

    def mount(
        self, namespace: DiagramNamespace, *, default: bool = False
    ) -> DiagramConfiguration:
        locations = list(self.namespace_locations)
        if namespace.root not in locations:
            locations.append(namespace.root)
        default_id = namespace.id if default else self.default_namespace_id
        atomic_write_json(
            self.path,
            {
                "type": entity(type(self)).name,
                "schema_version": CONFIG_SCHEMA_VERSION,
                "namespace_locations": [str(item) for item in locations],
                "default_namespace_id": default_id,
            },
        )
        return DiagramConfiguration.load(self.path)

    def diagram(self) -> Diagram:
        return Diagram(
            tuple(DiagramNamespace.open(path) for path in self.namespace_locations),
            self.default_namespace_id,
        )


@dataclass(frozen=True, slots=True)
class Diagram:
    namespaces: tuple[DiagramNamespace, ...]
    default_namespace_id: str | None = None

    def namespace(self, selector: str | None = None) -> DiagramNamespace:
        selector = selector or self.default_namespace_id
        if selector is None and len(self.namespaces) == 1:
            return self.namespaces[0]
        matches = [item for item in self.namespaces if selector in (item.id, item.name)]
        if len(matches) != 1:
            raise DiagramError(
                f"Diagram Namespace does not resolve uniquely: {selector}"
            )
        return matches[0]

    def assertion_engine(
        self, *, evidence: ChatlasEvidence | None = None
    ) -> AssertionEngine:
        return AssertionEngine(evidence=evidence)

    def object_type_definition_pois(
        self, registry: DiagramObjectTypeRegistry | None = None
    ) -> tuple[DiagramPOI, ...]:
        active_registry = registry or default_diagram_object_types()
        return active_registry.definition_pois(self.projected_block)

    def annotation(
        self, annotation_id: str, *, namespace: str | None = None
    ) -> DiagramAnnotation:
        if namespace:
            return self.namespace(namespace).annotation(annotation_id)
        matches: list[DiagramAnnotation] = []
        for space in self.namespaces:
            try:
                matches.append(space.annotation(annotation_id))
            except DiagramError:
                pass
        if len(matches) != 1:
            raise DiagramError(
                f"Diagram Annotation does not resolve uniquely: {annotation_id}"
            )
        return matches[0]

    def annotations_for_argument(
        self, identity: str, *, namespace: str | None = None
    ) -> tuple[DiagramAnnotation, ...]:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        return tuple(
            annotation
            for space in spaces
            for annotation in space.annotations_for_argument(identity)
        )

    def edition(
        self, edition_id: str, *, namespace: str | None = None
    ) -> DiagramAnnotation:
        if namespace:
            return self.namespace(namespace).edition(edition_id)
        matches: list[DiagramAnnotation] = []
        for space in self.namespaces:
            try:
                matches.append(space.edition(edition_id))
            except DiagramError:
                pass
        if len(matches) != 1:
            raise DiagramError(
                f"Diagram Ship edition does not resolve uniquely: {edition_id}"
            )
        return matches[0]

    def ship(self, ship_id: str, *, namespace: str | None = None) -> DiagramShip:
        if namespace:
            return self.namespace(namespace).ship(ship_id)
        matches = [
            space.ship(ship_id)
            for space in self.namespaces
            if (space.ships_root / f"{ship_id}.json").is_file()
        ]
        if len(matches) != 1:
            raise DiagramError(f"Diagram Ship does not resolve uniquely: {ship_id}")
        return matches[0]

    def model(self, model_ship: str) -> Model:
        from tarav.l2.models.errors import require_models
        require_models()
        matches: list[Model] = []
        for space in self.namespaces:
            if not (space.ships_root / f"{model_ship}.json").is_file():
                continue
            try:
                matches.append(space.model(model_ship))
            except DiagramError:
                pass
        if len(matches) != 1:
            raise DiagramError(f"Diagram Model does not resolve uniquely: {model_ship}")
        return matches[0]

    def models(self, *, namespace: str | None = None) -> tuple[Model, ...]:
        from tarav.l2.models.errors import require_models
        require_models()
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        return tuple(model for space in spaces for model in space.models())

    def apply(
        self,
        manifest: CaptureManifest,
        *,
        evidence: ChatlasEvidence | None = None,
        commit: bool = True,
    ) -> CaptureReceipt:
        from tarav.l2.models.errors import require_models
        require_models()
        return self.model(manifest.model_ship).namespace.apply(
            manifest, evidence=evidence, commit=commit
        )

    def line(
        self, line_ship: str, *, namespace: str | None = None
    ) -> tuple[TypedAnnotation, ...]:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        return tuple(item for space in spaces for item in space.line(line_ship))

    def projected_line(
        self, line_ship: str, *, namespace: str | None = None
    ) -> DiagramLineShip:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        matches: list[DiagramLineShip] = []
        for space in spaces:
            for model in space.models():
                try:
                    matches.append(model.project().line(line_ship))
                except DiagramError:
                    pass
        if len(matches) != 1:
            raise DiagramError(f"Diagram Line does not resolve uniquely: {line_ship}")
        return matches[0]

    def block_annotations(
        self, block_ship: str, *, namespace: str | None = None
    ) -> tuple[DiagramAnnotation, ...]:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        matches = tuple(
            (space, space.block_annotations(block_ship)) for space in spaces
        )
        populated = tuple((space, values) for space, values in matches if values)
        if len(populated) != 1:
            raise DiagramError(f"Diagram Block does not resolve uniquely: {block_ship}")
        return populated[0][1]

    def projected_block(
        self,
        block_ship: str,
        *,
        namespace: str | None = None,
        include_collection_content: bool = False,
    ) -> DiagramBlock:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        matches: list[DiagramBlock] = []
        for space in spaces:
            for model in space.models():
                try:
                    matches.append(
                        model.project(
                            include_collection_content=include_collection_content
                        ).block(block_ship)
                    )
                except DiagramError:
                    pass
        if len(matches) != 1:
            raise DiagramError(f"Diagram Block does not resolve uniquely: {block_ship}")
        return matches[0]

    def projected_collection(
        self, collection_ship: str, *, namespace: str | None = None
    ) -> DiagramCollection:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        matches: list[DiagramCollection] = []
        for space in spaces:
            for model in space.models():
                try:
                    matches.append(model.project().collection(collection_ship))
                except DiagramError:
                    pass
        if len(matches) != 1:
            raise DiagramError(
                f"Diagram Collection does not resolve uniquely: {collection_ship}"
            )
        return matches[0]

    def line_review(
        self,
        line_ship: str,
        *,
        namespace: str | None = None,
        evidence: ChatlasEvidence | None,
    ) -> LineReview:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        matches = []
        for space in spaces:
            if any(
                isinstance(item, LineEditionRecord) for item in space.line(line_ship)
            ):
                matches.append(space)
        if len(matches) != 1:
            raise DiagramError(f"Diagram Line does not resolve uniquely: {line_ship}")
        return matches[0].line_review(
            line_ship,
            evidence=evidence,
            assertion_engine=self.assertion_engine(evidence=evidence),
        )

    def ensure_project_model(self, project_root: Path) -> Model:
        from tarav.l2.models.errors import require_models
        require_models()
        config = ProjectConfig(project_root)
        setting = config.section("diagram", DiagramConfig) or DiagramConfig()
        if setting.main_model is not None:
            return self.model(setting.main_model)
        namespace = (
            self.namespace(USER_TOUCHED_CHATLAS_INDEX)
            if any(item.name == USER_TOUCHED_CHATLAS_INDEX for item in self.namespaces)
            else self.namespace()
        )
        model = namespace.create_model(label=project_root.name)
        config.write_section("diagram", setting.model_copy(update={"main_model": model.ship}))
        return model

    def project_model(self, project_root: Path) -> Model:
        from tarav.l2.models.errors import require_models
        require_models()
        setting = ProjectConfig(project_root).section("diagram", DiagramConfig)
        if setting is None or setting.main_model is None:
            raise DiagramError(
                f"Project has no Diagram main Model: {project_root.expanduser().resolve()}"
            )
        return self.model(setting.main_model)

    def set_project_main_model(
        self, project_root: Path, model_ship: str
    ) -> Model:
        from tarav.l2.models.errors import require_models
        require_models()
        """Point one Project at an existing Model without implying ownership."""
        model = self.model(model_ship)
        config = ProjectConfig(project_root)
        setting = config.section("diagram", DiagramConfig) or DiagramConfig()
        config.write_section("diagram", setting.model_copy(update={"main_model": model.ship}))
        return model


class DiagramConfig(BaseModel):
    """The `diagram` section of a Project's config: its main Model and named Models."""

    model_config = ConfigDict(strict=True, extra="forbid")
    main_model: str | None = None
    models: dict[str, str] = {}


def _merge_line_annotation_record(
    annotation_id: str,
    current: JsonObject | None,
    incoming: Mapping[str, Any],
) -> tuple[JsonObject, tuple[str, ...], tuple[str, ...]]:
    """Append Line.Annotation editions while keeping its address stable."""

    _uuid(annotation_id, field="Annotation.id")
    proposed = dict(incoming)
    if not _record_is(proposed, LineAnnotationRecord):
        raise DiagramModelError("not a Line.Annotation record")
    proposed_editions = tuple(
        _object(item, field="Line.Annotation.editions[]")
        for item in _array(
            proposed.pop("editions", []), field="Line.Annotation.editions"
        )
    )
    _validate_editions(proposed_editions, field="Line.Annotation.editions")
    proposed_base = _semantic_record(proposed)
    now = _timestamp()
    if current is None:
        merged = {**proposed_base, "recorded_at": now, "editions": []}
        known_editions: dict[str, JsonObject] = {}
    else:
        current_base = _semantic_record(
            {key: value for key, value in current.items() if key != "editions"}
        )
        if current_base != proposed_base:
            raise DiagramError(
                f"Diagram Annotation identity cannot be rebound: {annotation_id}"
            )
        merged = dict(current)
        known_editions = {
            _edition_id(edition): edition
            for edition in _line_annotation_editions(current)
        }
    added: list[str] = []
    repeated: list[str] = []
    editions = list(known_editions.values())
    for edition in proposed_editions:
        edition_id = _edition_id(edition)
        prior = known_editions.get(edition_id)
        if prior is not None:
            if _semantic_record(prior) != _semantic_record(edition):
                raise DiagramError(
                    "Diagram Annotation edition identity cannot be rebound: "
                    f"{edition_id}"
                )
            repeated.append(edition_id)
            continue
        retained = dict(edition)
        retained.setdefault("recorded_at", now)
        editions.append(retained)
        known_editions[edition_id] = retained
        added.append(edition_id)
    merged["editions"] = editions
    if current is not None and added:
        merged["updated_at"] = now
    return merged, tuple(added), tuple(repeated)


def _merge_ship_record(
    ship_id: str,
    current: JsonObject | None,
    incoming: Mapping[str, Any],
) -> tuple[JsonObject, tuple[str, ...], tuple[str, ...]]:
    _uuid(ship_id, field="Ship.id")
    proposed = dict(incoming)
    _record_type_reference(proposed, field="Ship")
    proposed_editions = tuple(
        _object(item, field="Ship.editions[]")
        for item in _array(proposed.pop("editions", []), field="Ship.editions")
    )
    _validate_editions(proposed_editions, field="Ship.editions")
    proposed_base = _semantic_record(proposed)
    now = _timestamp()
    if current is None:
        merged = {**proposed_base, "recorded_at": now, "editions": []}
        known_editions: dict[str, JsonObject] = {}
    else:
        current_base = _semantic_record(
            {key: value for key, value in current.items() if key != "editions"}
        )
        if current_base != proposed_base:
            raise DiagramError(f"Diagram Ship identity cannot be rebound: {ship_id}")
        merged = dict(current)
        known_editions = {
            _edition_id(edition): edition
            for item in _array(current.get("editions", []), field="Ship.editions")
            for edition in (_object(item, field="Ship.editions[]"),)
        }
    added: list[str] = []
    repeated: list[str] = []
    editions = list(known_editions.values())
    for edition in proposed_editions:
        edition_id = _edition_id(edition)
        prior = known_editions.get(edition_id)
        if prior is not None:
            if _semantic_record(prior) != _semantic_record(edition):
                raise DiagramError(
                    f"Diagram Ship edition identity cannot be rebound: {edition_id}"
                )
            repeated.append(edition_id)
            continue
        retained = dict(edition)
        retained.setdefault("recorded_at", now)
        editions.append(retained)
        known_editions[edition_id] = retained
        added.append(edition_id)
    merged["editions"] = editions
    if current is not None and added:
        merged["updated_at"] = now
    return merged, tuple(added), tuple(repeated)
