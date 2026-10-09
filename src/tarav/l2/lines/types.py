"""tarav.l2.lines.types: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

# tarav.breadcrumb 7c4699968f14f11ef881b62e25ccbef118f4c2168443dbf3c812ed4b173f4cbf

import tarav.l2.unsorted.pois as diagram_pois

from tarav.l2.unsorted.constants import DESIGN_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import DESIGN_BLOCK_TYPE_DEFINITION_BLOCK_SHIP
from tarav.l2.unsorted.constants import DESIGN_LINE_CONSTRAINT_TYPE
from tarav.l2.unsorted.constants import DESIGN_LINE_DECISION_TYPE
from tarav.l2.unsorted.constants import DESIGN_LINE_DEFINITION_TYPE
from tarav.l2.unsorted.constants import DESIGN_LINE_EXAMPLE_TYPE
from tarav.l2.unsorted.constants import DESIGN_LINE_FREEDOM_TYPE
from tarav.l2.unsorted.constants import DESIGN_LINE_PRINCIPLE_TYPE
from tarav.l2.unsorted.constants import DESIGN_LINE_REJECTION_TYPE
from tarav.l2.unsorted.constants import DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS
from tarav.l2.unsorted.constants import DIAGRAM_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import DIAGRAM_BLOCK_TYPE_DEFINITION_BLOCK_SHIP
from tarav.l2.unsorted.constants import DIAGRAM_COLLECTION_OBJECT_TYPE
from tarav.l2.unsorted.constants import DIAGRAM_COLLECTION_TYPE_DEFINITION_BLOCK_SHIP
from tarav.l2.unsorted.constants import DIAGRAM_LINE_OBJECT_TYPE
from tarav.l2.lines.block import DesignBlock
from tarav.l2.lines.line import DesignConstraintLineShip
from tarav.l2.lines.line import DesignDecisionLineShip
from tarav.l2.lines.line import DesignDefinitionLineShip
from tarav.l2.lines.line import DesignExampleLineShip
from tarav.l2.lines.line import DesignFreedomLineShip
from tarav.l2.lines.line import DesignLineConstraint
from tarav.l2.lines.line import DesignLineDecision
from tarav.l2.lines.line import DesignLineDefinition
from tarav.l2.lines.line import DesignLineExample
from tarav.l2.lines.line import DesignLineFreedom
from tarav.l2.lines.line import DesignLinePrinciple
from tarav.l2.lines.line import DesignLineRejection
from tarav.l2.lines.line import DesignPrincipleLineShip
from tarav.l2.lines.line import DesignRejectionLineShip
from tarav.l2.lines.block import DiagramBlock
from tarav.l2.lines.collection import DiagramCollection
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l2.lines.line import DiagramLineEdition
from tarav.l2.lines.line import DiagramLineShip
from tarav.l2.unsorted.pois import DiagramPOI
from tarav.l2.unsorted.constants import IMPL_REQ_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import IMPL_REQ_BLOCK_TYPE_DEFINITION_BLOCK_SHIP
from tarav.l2.unsorted.constants import IMPL_REQ_COLLECTION_OBJECT_TYPE
from tarav.l2.unsorted.constants import IMPL_REQ_COLLECTION_TYPE_DEFINITION_BLOCK_SHIP
from tarav.l2.unsorted.constants import ISSUE_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import ISSUE_BLOCK_TYPE_DEFINITION_BLOCK_SHIP
from tarav.l2.unsorted.constants import ISSUE_LINE_RESOLVE_TYPE
from tarav.l2.unsorted.constants import ISSUE_LINE_RESOLVE_TYPE_DEFINITION_BLOCK_SHIP
from tarav.l2.lines.block import ImplReqBlock
from tarav.l2.lines.collection import ImplReqCollection
from tarav.l2.lines.block import IssueBlock
from tarav.l2.lines.line import IssueLineResolve
from tarav.l2.lines.line import IssueResolveLineShip
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from tarav.l2.unsorted.constants import JsonObject

@dataclass(frozen=True, slots=True)
class DiagramLineType:
    id: str
    short_code: str
    edition_class: type[DiagramLineEdition]
    ship_class: type[DiagramLineShip]
    definition_block_ship: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "short_code": self.short_code,
            "edition_class": self.edition_class.__name__,
            "ship_class": self.ship_class.__name__,
            "definition_block_ship": self.definition_block_ship,
        }


@dataclass(frozen=True, slots=True)
class DiagramBlockType:
    id: str
    block_class: type[DiagramBlock]
    line_types: tuple[DiagramLineType, ...]
    require_line_type: bool = True
    definition_block_ship: str | None = None

    def line_type(self, type_id: str) -> DiagramLineType | None:
        return next((item for item in self.line_types if item.id == type_id), None)

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "class": self.block_class.__name__,
            "definition_block_ship": self.definition_block_ship,
            "require_line_type": self.require_line_type,
            "line_types": [item.to_dict() for item in self.line_types],
        }


@dataclass(frozen=True, slots=True)
class DiagramCollectionType:
    id: str
    collection_class: type[DiagramCollection]
    definition_block_ship: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "class": self.collection_class.__name__,
            "definition_block_ship": self.definition_block_ship,
        }


@dataclass(frozen=True, slots=True)
class DiagramObjectTypeRegistry:
    block_types: tuple[DiagramBlockType, ...]
    collection_types: tuple[DiagramCollectionType, ...] = ()

    def block_type(self, type_id: str) -> DiagramBlockType | None:
        return next((item for item in self.block_types if item.id == type_id), None)

    def line_type(self, type_id: str) -> DiagramLineType | None:
        return next(
            (
                line_type
                for block_type in self.block_types
                for line_type in block_type.line_types
                if line_type.id == type_id
            ),
            None,
        )

    def collection_type(self, type_id: str) -> DiagramCollectionType | None:
        return next(
            (item for item in self.collection_types if item.id == type_id), None
        )

    def types(self) -> tuple[DiagramBlockType | DiagramLineType, ...]:
        return tuple(
            dict.fromkeys(
                (
                    *self.block_types,
                    *self.collection_types,
                    *(
                        line_type
                        for block_type in self.block_types
                        for line_type in block_type.line_types
                    ),
                )
            )
        )

    def definition_pois(
        self, resolve_block: Callable[[str], object]
    ) -> tuple[DiagramPOI, ...]:
        pois: list[DiagramPOI] = []
        for object_type in self.types():
            path = f"object_type.{object_type.id}.definition_block_ship"
            if object_type.definition_block_ship is None:
                pois.append(
                    diagram_pois.ObjectTypeDefinitionBlockMissing(path=path, message=f'Object.Type {object_type.id} has no Definition.Block.')
                )
                continue
            try:
                resolve_block(object_type.definition_block_ship)
            except DiagramError:
                pois.append(
                    diagram_pois.ObjectTypeDefinitionBlockUnresolved(path=path, message=f'Definition.Block does not resolve for Object.Type {object_type.id}: {object_type.definition_block_ship}.')
                )
        return tuple(pois)

    def to_dict(self) -> JsonObject:
        return {
            "block_types": [item.to_dict() for item in self.block_types],
            "collection_types": [item.to_dict() for item in self.collection_types],
        }


def default_diagram_object_types() -> DiagramObjectTypeRegistry:
    generic_line = DiagramLineType(
        DIAGRAM_LINE_OBJECT_TYPE,
        "",
        DiagramLineEdition,
        DiagramLineShip,
        DIAGRAM_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
    )
    design_lines = (
        DiagramLineType(
            DESIGN_LINE_DEFINITION_TYPE,
            "DF",
            DesignLineDefinition,
            DesignDefinitionLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_DEFINITION_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_DECISION_TYPE,
            "DC",
            DesignLineDecision,
            DesignDecisionLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_DECISION_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_CONSTRAINT_TYPE,
            "CT",
            DesignLineConstraint,
            DesignConstraintLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_CONSTRAINT_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_REJECTION_TYPE,
            "RJ",
            DesignLineRejection,
            DesignRejectionLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_REJECTION_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_PRINCIPLE_TYPE,
            "PR",
            DesignLinePrinciple,
            DesignPrincipleLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_PRINCIPLE_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_FREEDOM_TYPE,
            "FR",
            DesignLineFreedom,
            DesignFreedomLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_FREEDOM_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_EXAMPLE_TYPE,
            "EX",
            DesignLineExample,
            DesignExampleLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_EXAMPLE_TYPE],
        ),
    )
    issue_resolve = DiagramLineType(
        ISSUE_LINE_RESOLVE_TYPE,
        "RESOLVE",
        IssueLineResolve,
        IssueResolveLineShip,
        ISSUE_LINE_RESOLVE_TYPE_DEFINITION_BLOCK_SHIP,
    )
    return DiagramObjectTypeRegistry(
        (
            DiagramBlockType(
                DIAGRAM_BLOCK_OBJECT_TYPE,
                DiagramBlock,
                (generic_line,),
                definition_block_ship=DIAGRAM_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
            ),
            DiagramBlockType(
                DESIGN_BLOCK_OBJECT_TYPE,
                DesignBlock,
                design_lines,
                definition_block_ship=DESIGN_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
            ),
            DiagramBlockType(
                IMPL_REQ_BLOCK_OBJECT_TYPE,
                ImplReqBlock,
                design_lines,
                definition_block_ship=IMPL_REQ_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
            ),
            DiagramBlockType(
                ISSUE_BLOCK_OBJECT_TYPE,
                IssueBlock,
                (*design_lines, issue_resolve),
                definition_block_ship=ISSUE_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
            ),
        ),
        (
            DiagramCollectionType(
                DIAGRAM_COLLECTION_OBJECT_TYPE,
                DiagramCollection,
                definition_block_ship=DIAGRAM_COLLECTION_TYPE_DEFINITION_BLOCK_SHIP,
            ),
            DiagramCollectionType(
                IMPL_REQ_COLLECTION_OBJECT_TYPE,
                ImplReqCollection,
                definition_block_ship=IMPL_REQ_COLLECTION_TYPE_DEFINITION_BLOCK_SHIP,
            ),
        ),
    )
