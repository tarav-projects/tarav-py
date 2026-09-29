"""tarav.l2.lines.projection: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.l2.lines.records import BlockEditionRecord
from tarav.l2.lines.records import BlockTypeAnnotation
from tarav.l2.lines.records import CollectionEditionRecord
from tarav.l2.unsorted.constants import DIAGRAM_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import DIAGRAM_COLLECTION_OBJECT_TYPE
from tarav.l2.unsorted.constants import DIAGRAM_LINE_OBJECT_TYPE
from tarav.l2.lines.block import DiagramBlock
from tarav.l2.lines.collection import DiagramCollection
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l2.lines.collection import DiagramHostedEdition
from tarav.l2.unsorted.primitives import DiagramModelError
from tarav.l2.unsorted.contracts import Finding
from tarav.l2.lines.collection import ImplReqCollection
from tarav.l2.lines.records import LineEditionRecord
from tarav.l2.lines.records import LineTypeAnnotation
from tarav.l2.unsorted.contracts import _dedupe_findings
from tarav.l2.unsorted.primitives import _edition_id
from tarav.l2.unsorted.primitives import _optional_timestamp
from tarav.l2.unsorted.records import _sort_typed
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarav.l2.lines.references import DiagramArgumentReferenceInterface
    from tarav.l2.lines.types import DiagramBlockType
    from tarav.l2.lines.line import DiagramLineShip
    from tarav.l2.unsorted.storage import DiagramNamespace
    from collections.abc import Iterable
    from tarav.l2.unsorted.constants import JsonObject
    from tarav.l2.lines.records import LineGateAnnotation
    from tarav.l2.lines.records import LineSupportAnnotation
    from tarav.l2.unsorted.records import TypedAnnotation

@dataclass(frozen=True, slots=True)
class DiagramProjection:
    model_ship: str
    namespace_id: str
    blocks: tuple[DiagramBlock, ...]
    collections: tuple[DiagramCollection, ...]
    findings: tuple[Finding, ...]

    def block(self, block_ship: str) -> DiagramBlock:
        matches = tuple(item for item in self.blocks if item.ship == block_ship)
        if len(matches) != 1:
            raise DiagramError(f"Projected Block does not resolve: {block_ship}")
        return matches[0]

    def line(self, line_ship: str) -> DiagramLineShip:
        matches = tuple(
            line
            for block in self.blocks
            for line in block.lines
            if line.ship == line_ship
        )
        if len(matches) != 1:
            raise DiagramError(f"Projected Line does not resolve: {line_ship}")
        return matches[0]

    def collection(self, collection_ship: str) -> DiagramCollection:
        matches = tuple(
            item for item in self.collections if item.ship == collection_ship
        )
        if len(matches) != 1:
            raise DiagramError(
                f"Projected Collection does not resolve: {collection_ship}"
            )
        return matches[0]

    def child_collections(self, collection_ship: str) -> tuple[DiagramCollection, ...]:
        return tuple(
            item
            for item in self.collections
            if item.host is not None
            and item.host.kind == "collection"
            and item.host.id == collection_ship
        )

    def objects(
        self,
        *,
        kind: str | None = None,
        object_type: str | None = None,
        label: str | None = None,
    ) -> tuple[DiagramBlock | DiagramLineShip | DiagramCollection, ...]:
        """Return projected semantic objects matching exact composable filters."""

        if kind not in (None, "block", "line", "collection"):
            raise DiagramModelError(f"unsupported Diagram object kind: {kind}")
        selected: tuple[DiagramBlock | DiagramLineShip | DiagramCollection, ...] = (
            tuple(
                (
                    *(self.blocks if kind in (None, "block") else ()),
                    *(self.collections if kind in (None, "collection") else ()),
                    *(
                        tuple(line for block in self.blocks for line in block.lines)
                        if kind in (None, "line")
                        else ()
                    ),
                )
            )
        )
        if object_type is not None:
            selected = tuple(
                item for item in selected if item.object_type == object_type
            )
        if label is not None:
            selected = tuple(
                item
                for item in selected
                if isinstance(item, (DiagramBlock, DiagramCollection))
                and label in item.labels
            )
        return selected

    def to_dict(self) -> JsonObject:
        return {
            "model_ship": self.model_ship,
            "namespace_id": self.namespace_id,
            "blocks": [
                {
                    "ship": block.ship,
                    "object_type": block.object_type,
                    "labels": list(block.labels),
                    "lines": [
                        {
                            "ship": line.ship,
                            "object_type": line.object_type,
                            "type_history": list(line.type_ids),
                            "editions": [
                                item.id
                                for item in line.annotations
                                if isinstance(item, LineEditionRecord)
                            ],
                            "annotations": [
                                item.id
                                for item in line.annotations
                                if not isinstance(item, LineEditionRecord)
                            ],
                        }
                        for line in block.lines
                    ],
                    "editions": [
                        item.id
                        for item in block.annotations
                        if isinstance(item, BlockEditionRecord)
                    ],
                    "annotations": [
                        item.id
                        for item in block.annotations
                        if not isinstance(item, BlockEditionRecord)
                    ],
                }
                for block in self.blocks
            ],
            "collections": [
                {
                    "ship": collection.ship,
                    "object_type": collection.object_type,
                    "labels": list(collection.labels),
                    "host": (
                        collection.host.model_dump(mode="json")
                        if collection.host is not None
                        else None
                    ),
                    "hosted_editions": [
                        item.to_dict() for item in collection.hosted_editions
                    ],
                    "references": [
                        item.model_dump(mode="json") for item in collection.references
                    ],
                }
                for collection in self.collections
            ],
            "findings": [item.to_dict() for item in self.findings],
        }


class DiagramProjectionBuilder:
    """Canonical full projector over Ship editions and attached Annotations."""

    def __init__(
        self,
        namespace: DiagramNamespace,
        model_ship: str,
        annotations: Iterable[TypedAnnotation],
        *,
        include_collection_content: bool = False,
    ) -> None:
        self.namespace = namespace
        self.model_ship = model_ship
        self.registry = namespace.object_types()
        self.typed_by_id = {item.id: item for item in annotations}
        self.include_collection_content = include_collection_content
        self.block_annotations: dict[str, list[TypedAnnotation]] = {}
        self.line_annotations: dict[tuple[str, str], list[TypedAnnotation]] = {}
        self.collection_editions: dict[str, list[CollectionEditionRecord]] = {}
        self.findings: list[Finding] = []

    def add_collection_edition(self, edition: CollectionEditionRecord) -> None:
        self.collection_editions.setdefault(edition.collection_ship, []).append(edition)

    def add_block_annotation(
        self, annotation: BlockEditionRecord | BlockTypeAnnotation
    ) -> None:
        self.block_annotations.setdefault(annotation.location.block_ship, []).append(
            annotation
        )

    def add_line_annotation(
        self,
        annotation: LineEditionRecord | LineSupportAnnotation | LineTypeAnnotation,
    ) -> None:
        location = annotation.location
        self.line_annotations.setdefault(
            (location.block_ship, location.line_ship), []
        ).append(annotation)

    def add_line_gate_annotation(self, annotation: LineGateAnnotation) -> None:
        target = self.typed_by_id.get(annotation.target_edition_id)
        if target is None:
            try:
                target = self.namespace.edition(
                    annotation.target_edition_id
                ).specialize()
            except (DiagramError, DiagramModelError):
                target = None
        if not isinstance(target, LineEditionRecord):
            self.findings.append(
                Finding(
                    "line-gate-target-unresolved",
                    f"annotation.{annotation.id}.target_edition",
                    "Line Gate target does not resolve to a Line Edition.",
                )
            )
            return
        location = target.location
        self.line_annotations.setdefault(
            (location.block_ship, location.line_ship), []
        ).append(annotation)

    def build(self) -> DiagramProjection:
        block_ships = tuple(
            dict.fromkeys(
                (*self.block_annotations, *(key[0] for key in self.line_annotations))
            )
        )
        blocks = tuple(
            block for ship in block_ships if (block := self._block(ship)) is not None
        )
        collections = tuple(self._collection(ship) for ship in self.collection_editions)
        self.findings.extend(self._collection_cycle_findings(collections))
        findings = _dedupe_findings(
            (
                *self.findings,
                *(finding for block in blocks for finding in block.findings),
                *(
                    finding
                    for collection in collections
                    for finding in (
                        *collection.findings,
                        *collection.mechanical_findings(),
                    )
                ),
                *(
                    finding
                    for block in blocks
                    for line in block.lines
                    for finding in line.findings
                ),
            )
        )
        return DiagramProjection(
            self.model_ship, self.namespace.id, blocks, collections, findings
        )

    def _ordered_ship_editions(
        self, ship: str, editions: Iterable[TypedAnnotation]
    ) -> tuple[TypedAnnotation, ...]:
        retained = tuple(editions)
        try:
            ship_editions = self.namespace.ship(ship).specialize().editions
        except (DiagramError, DiagramModelError):
            return retained
        positions = {
            _edition_id(edition): index for index, edition in enumerate(ship_editions)
        }
        fallback = len(positions)
        return tuple(
            sorted(
                retained,
                key=lambda item: (positions.get(item.id, fallback), item.id),
            )
        )

    def _block(self, ship: str) -> DiagramBlock | None:
        annotations = _sort_typed(self.block_annotations.get(ship, ()))
        all_declarations = self._ordered_ship_editions(
            ship,
            (item for item in annotations if isinstance(item, BlockEditionRecord)),
        )
        declarations = tuple(
            item
            for item in all_declarations
            if self.include_collection_content or item.host.kind == "model"
        )
        if all_declarations and not declarations:
            return None
        annotations = (
            *declarations,
            *(item for item in annotations if not isinstance(item, BlockEditionRecord)),
        )
        type_annotations = tuple(
            item for item in annotations if isinstance(item, BlockTypeAnnotation)
        )
        findings: list[Finding] = []
        type_ids = tuple(
            dict.fromkeys(
                item.block_type
                for item in (*declarations, *type_annotations)
                if item.block_type is not None
            )
        )
        if not declarations:
            findings.append(
                Finding(
                    "block-declaration-missing",
                    f"block.{ship}",
                    "Lines name a Block Ship with no Block Edition.",
                )
            )
        if declarations and not type_ids and self.namespace.require_block_type:
            findings.append(
                Finding(
                    "block-type-missing",
                    f"block.{ship}",
                    "Block Editions do not retain a Block.Type.",
                )
            )
        selected_id = type_ids[-1] if type_ids else DIAGRAM_BLOCK_OBJECT_TYPE
        block_type = self.registry.block_type(selected_id)
        if block_type is None:
            findings.append(
                Finding(
                    "block-type-unknown",
                    f"block.{ship}.block_type",
                    f"Block.Type is not registered: {selected_id}.",
                )
            )
            block_type = self.registry.block_type(DIAGRAM_BLOCK_OBJECT_TYPE)
        if (
            type_ids
            and self.namespace.allowed_block_types
            and selected_id not in self.namespace.allowed_block_types
        ):
            findings.append(
                Finding(
                    "block-type-not-allowed",
                    f"block.{ship}.block_type",
                    f"Namespace {self.namespace.name} does not allow Block.Type {selected_id}.",
                )
            )
        assert block_type is not None
        lines = tuple(
            line
            for block_ship, line_ship in self.line_annotations
            if block_ship == ship
            if (line := self._line(ship, line_ship, block_type)) is not None
        )
        return block_type.block_class(
            ship,
            self.model_ship,
            annotations,
            lines,
            type_ids,
            tuple(findings),
        )

    def _line(
        self, block_ship: str, ship: str, block_type: DiagramBlockType
    ) -> DiagramLineShip | None:
        annotations = _sort_typed(self.line_annotations[(block_ship, ship)])
        all_wordings = self._ordered_ship_editions(
            ship,
            (item for item in annotations if isinstance(item, LineEditionRecord)),
        )
        wordings = tuple(
            item
            for item in all_wordings
            if self.include_collection_content or item.host.kind == "model"
        )
        if not wordings:
            if all_wordings and all_wordings[-1].host.kind == "collection":
                self.findings.append(self._staleness_finding(ship, all_wordings[-1]))
            return None
        if all_wordings[-1].id != wordings[-1].id:
            self.findings.append(self._staleness_finding(ship, all_wordings[-1]))
        annotations = (
            *wordings,
            *(item for item in annotations if not isinstance(item, LineEditionRecord)),
        )
        type_annotations = tuple(
            item for item in annotations if isinstance(item, LineTypeAnnotation)
        )
        findings: list[Finding] = []
        type_ids = tuple(
            dict.fromkeys(
                item.line_type
                for item in (*wordings, *type_annotations)
                if item.line_type is not None
            )
        )
        if not wordings:
            findings.append(
                Finding(
                    "line-wording-missing",
                    f"line.{ship}",
                    "Line records name a Line Ship with no wording Edition.",
                )
            )
        if wordings and not type_ids and block_type.require_line_type:
            findings.append(
                Finding(
                    "line-type-missing",
                    f"line.{ship}",
                    "Line Editions do not retain a Line.Type.",
                )
            )
        line_type = None
        if type_ids:
            selected_id = type_ids[-1]
            line_type = block_type.line_type(selected_id)
            if line_type is None:
                known = self.registry.line_type(selected_id)
                findings.append(
                    Finding(
                        (
                            "line-type-not-allowed-by-block"
                            if known
                            else "line-type-unknown"
                        ),
                        f"line.{ship}.line_type",
                        (
                            f"Block.Type {block_type.id} does not allow "
                            f"Line.Type {selected_id}."
                            if known
                            else f"Line.Type is not registered: {selected_id}."
                        ),
                    )
                )
        if line_type is None:
            line_type = self.registry.line_type(DIAGRAM_LINE_OBJECT_TYPE)
        assert line_type is not None
        editions = tuple(line_type.edition_class(item, line_type) for item in wordings)
        return line_type.ship_class(
            ship,
            block_ship,
            annotations,
            editions,
            type_ids,
            tuple(findings),
        )

    def _staleness_finding(self, ship: str, latest: LineEditionRecord) -> Finding:
        return Finding(
            "model-staleness",
            f"line.{ship}.edition.{latest.id}",
            (
                "Model.Staleness.POI: the newest known Line.Ship edition is "
                f"hosted outside the Model primary surface by {latest.host.id}."
            ),
        )

    def _collection(self, ship: str) -> DiagramCollection:
        editions = tuple(
            item
            for item in self._ordered_ship_editions(
                ship, self.collection_editions.get(ship, ())
            )
            if isinstance(item, CollectionEditionRecord)
        )
        findings: list[Finding] = []
        type_ids = tuple(dict.fromkeys(item.collection_type for item in editions))
        selected_id = type_ids[-1] if type_ids else DIAGRAM_COLLECTION_OBJECT_TYPE
        collection_type = self.registry.collection_type(selected_id)
        if collection_type is None:
            findings.append(
                Finding(
                    "collection-type-unknown",
                    f"collection.{ship}.collection_type",
                    f"Collection.Type is not registered: {selected_id}.",
                )
            )
            collection_type = self.registry.collection_type(
                DIAGRAM_COLLECTION_OBJECT_TYPE
            )
        assert collection_type is not None
        if (
            type_ids
            and self.namespace.allowed_collection_types
            and selected_id not in self.namespace.allowed_collection_types
        ):
            findings.append(
                Finding(
                    "collection-type-not-allowed",
                    f"collection.{ship}.collection_type",
                    (
                        f"Namespace {self.namespace.name} does not allow "
                        f"Collection.Type {selected_id}."
                    ),
                )
            )
        current = editions[-1] if editions else None
        if current is not None and current.host.kind == "model":
            if current.host.id != self.model_ship:
                findings.append(
                    Finding(
                        "collection-host-model-mismatch",
                        f"collection.{ship}.host",
                        "Collection host names a different Model.",
                    )
                )
        elif current is not None and current.host.id not in self.collection_editions:
            findings.append(
                Finding(
                    "collection-host-unresolved",
                    f"collection.{ship}.host",
                    "Parent Diagram.Collection does not resolve in this Model.",
                )
            )
        if current is not None:
            for index, reference in enumerate(current.references):
                if (
                    reference.namespace_id == self.namespace.id
                    and not self.namespace.resolves_argument(reference)
                    and not self._resolves_projection_reference(reference)
                ):
                    findings.append(
                        Finding(
                            "collection-reference-unresolved",
                            f"collection.{ship}.references[{index}]",
                            "Diagram.Collection reference does not resolve.",
                        )
                    )
        hosted = self._hosted_editions(ship)
        collection = collection_type.collection_class(
            ship,
            self.model_ship,
            editions,
            type_ids,
            hosted,
            tuple(findings),
        )
        if isinstance(collection, ImplReqCollection) and collection.state == "Closed":
            current = collection.current_edition
            closed_at = (
                _optional_timestamp(current.data.get("closed_at"))
                if current is not None
                else None
            )
            if closed_at is None and current is not None:
                closed_at = _optional_timestamp(current.to_record().get("recorded_at"))
            close_is_already_landed = (
                current is not None
                and current.to_record().get("recorded_at") is not None
            )
            for hosted_edition in hosted:
                typed = self.typed_by_id.get(hosted_edition.edition)
                recorded_at = (
                    _optional_timestamp(typed.to_record().get("recorded_at"))
                    if typed is not None
                    else None
                )
                if recorded_at is None and not close_is_already_landed:
                    continue
                if (
                    closed_at is not None
                    and recorded_at is not None
                    and recorded_at <= closed_at
                ):
                    continue
                findings.append(
                    Finding(
                        "impl-req-closed-write",
                        f"collection.{ship}.hosted.{hosted_edition.edition}",
                        "Normal capture added or revised content in a Closed Impl.Req.Collection.",
                    )
                )
            collection = collection_type.collection_class(
                ship,
                self.model_ship,
                editions,
                type_ids,
                hosted,
                tuple(findings),
            )
        return collection

    def _resolves_projection_reference(
        self, reference: DiagramArgumentReferenceInterface
    ) -> bool:
        if reference.kind in {"edition", "annotation"}:
            return reference.id in self.typed_by_id
        if reference.kind != "ship":
            return False
        for item in self.typed_by_id.values():
            if isinstance(item, LineEditionRecord):
                identities = (item.location.block_ship, item.location.line_ship)
            elif isinstance(item, BlockEditionRecord):
                identities = (item.location.block_ship,)
            elif isinstance(item, CollectionEditionRecord):
                identities = (item.collection_ship,)
            else:
                continue
            if reference.id in identities:
                return True
        return False

    def _hosted_editions(
        self, collection_ship: str
    ) -> tuple[DiagramHostedEdition, ...]:
        hosted: list[DiagramHostedEdition] = []
        for typed in self.typed_by_id.values():
            if not isinstance(
                typed, (BlockEditionRecord, LineEditionRecord, CollectionEditionRecord)
            ):
                continue
            if typed.host.kind != "collection" or typed.host.id != collection_ship:
                continue
            if isinstance(typed, BlockEditionRecord):
                kind, ship = "block", typed.location.block_ship
            elif isinstance(typed, LineEditionRecord):
                kind, ship = "line", typed.location.line_ship
            else:
                kind, ship = "collection", typed.collection_ship
            hosted.append(DiagramHostedEdition(kind, ship, typed.id))
        return tuple(hosted)

    def _collection_cycle_findings(
        self, collections: tuple[DiagramCollection, ...]
    ) -> tuple[Finding, ...]:
        parents = {
            item.ship: item.host.id
            for item in collections
            if item.host is not None and item.host.kind == "collection"
        }
        findings: list[Finding] = []
        for ship in parents:
            visited: set[str] = set()
            cursor = ship
            while cursor in parents:
                if cursor in visited:
                    findings.append(
                        Finding(
                            "collection-host-cycle",
                            f"collection.{ship}.host",
                            "Diagram.Collection hosting contains a cycle.",
                        )
                    )
                    break
                visited.add(cursor)
                cursor = parents[cursor]
        return _dedupe_findings(findings)
