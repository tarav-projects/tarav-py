"""tarav.lines.types: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.unsorted.constants import DESIGN_BLOCK_OBJECT_TYPE
from tarav.unsorted.constants import DESIGN_BLOCK_TYPE_DEFINITION_BLOCK_SHIP
from tarav.unsorted.constants import DESIGN_LINE_CONSTRAINT_TYPE
from tarav.unsorted.constants import DESIGN_LINE_DECISION_TYPE
from tarav.unsorted.constants import DESIGN_LINE_DEFINITION_TYPE
from tarav.unsorted.constants import DESIGN_LINE_EXAMPLE_TYPE
from tarav.unsorted.constants import DESIGN_LINE_FREEDOM_TYPE
from tarav.unsorted.constants import DESIGN_LINE_PRINCIPLE_TYPE
from tarav.unsorted.constants import DESIGN_LINE_REJECTION_TYPE
from tarav.unsorted.constants import DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS
from tarav.unsorted.constants import DIAGRAM_BLOCK_OBJECT_TYPE
from tarav.unsorted.constants import DIAGRAM_BLOCK_TYPE_DEFINITION_BLOCK_SHIP
from tarav.unsorted.constants import DIAGRAM_COLLECTION_OBJECT_TYPE
from tarav.unsorted.constants import DIAGRAM_COLLECTION_TYPE_DEFINITION_BLOCK_SHIP
from tarav.unsorted.constants import DIAGRAM_LINE_OBJECT_TYPE
from tarav.lines.block import DesignBlock
from tarav.lines.line import DesignConstraintLineShip
from tarav.lines.line import DesignDecisionLineShip
from tarav.lines.line import DesignDefinitionLineShip
from tarav.lines.line import DesignExampleLineShip
from tarav.lines.line import DesignFreedomLineShip
from tarav.lines.line import DesignLineConstraint
from tarav.lines.line import DesignLineDecision
from tarav.lines.line import DesignLineDefinition
from tarav.lines.line import DesignLineExample
from tarav.lines.line import DesignLineFreedom
from tarav.lines.line import DesignLinePrinciple
from tarav.lines.line import DesignLineRejection
from tarav.lines.line import DesignPrincipleLineShip
from tarav.lines.line import DesignRejectionLineShip
from tarav.lines.block import DiagramBlock
from tarav.lines.collection import DiagramCollection
from tarav.unsorted.primitives import DiagramError
from tarav.lines.line import DiagramLineEdition
from tarav.lines.line import DiagramLineShip
from tarav.unsorted.contracts import Finding
from tarav.unsorted.constants import IMPL_REQ_BLOCK_OBJECT_TYPE
from tarav.unsorted.constants import IMPL_REQ_BLOCK_TYPE_DEFINITION_BLOCK_SHIP
from tarav.unsorted.constants import IMPL_REQ_COLLECTION_OBJECT_TYPE
from tarav.unsorted.constants import IMPL_REQ_COLLECTION_TYPE_DEFINITION_BLOCK_SHIP
from tarav.unsorted.constants import ISSUE_BLOCK_OBJECT_TYPE
from tarav.unsorted.constants import ISSUE_BLOCK_TYPE_DEFINITION_BLOCK_SHIP
from tarav.unsorted.constants import ISSUE_LINE_RESOLVE_TYPE
from tarav.unsorted.constants import ISSUE_LINE_RESOLVE_TYPE_DEFINITION_BLOCK_SHIP
from tarav.lines.block import ImplReqBlock
from tarav.lines.collection import ImplReqCollection
from tarav.lines.block import IssueBlock
from tarav.lines.line import IssueLineResolve
from tarav.lines.line import IssueResolveLineShip
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from tarav.unsorted.constants import JsonObject

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

    def definition_findings(
        self, resolve_block: Callable[[str], object]
    ) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for object_type in self.types():
            path = f"object_type.{object_type.id}.definition_block_ship"
            if object_type.definition_block_ship is None:
                findings.append(
                    Finding(
                        "object-type-definition-block-missing",
                        path,
                        f"Object.Type {object_type.id} has no Definition.Block.",
                    )
                )
                continue
            try:
                resolve_block(object_type.definition_block_ship)
            except DiagramError:
                findings.append(
                    Finding(
                        "object-type-definition-block-unresolved",
                        path,
                        (
                            f"Definition.Block does not resolve for Object.Type "
                            f"{object_type.id}: {object_type.definition_block_ship}."
                        ),
                    )
                )
        return tuple(findings)

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
