"""tarav.l2.lines.line: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.l2.unsorted.contracts import _object_assertions
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarav.l2.lines.types import DiagramLineType
    from tarav.l2.unsorted.contracts import DiagramObjectAssertion
    from tarav.l2.unsorted.contracts import Finding
    from collections.abc import Iterable
    from tarav.l2.lines.records import LineEditionRecord
    from tarav.l2.unsorted.records import TypedAnnotation

@dataclass(frozen=True, slots=True)
class DiagramLineEdition:
    annotation: LineEditionRecord
    object_type: DiagramLineType

    @property
    def text(self) -> str:
        return self.annotation.text


class DesignLineDefinition(DiagramLineEdition):
    pass


class DesignLineDecision(DiagramLineEdition):
    pass


class DesignLineConstraint(DiagramLineEdition):
    pass


class DesignLineRejection(DiagramLineEdition):
    pass


class DesignLinePrinciple(DiagramLineEdition):
    pass


class DesignLineFreedom(DiagramLineEdition):
    pass


class DesignLineExample(DiagramLineEdition):
    pass


class IssueLineResolve(DiagramLineEdition):
    pass


@dataclass(frozen=True, slots=True)
class DiagramLineShip:
    ship: str
    block_ship: str
    annotations: tuple[TypedAnnotation, ...]
    editions: tuple[DiagramLineEdition, ...]
    type_ids: tuple[str, ...]
    findings: tuple[Finding, ...]

    @property
    def object_type(self) -> str | None:
        return self.type_ids[-1] if self.type_ids else None

    @property
    def current_edition(self) -> DiagramLineEdition | None:
        return self.editions[-1] if self.editions else None

    def assertions(self) -> tuple[DiagramObjectAssertion, ...]:
        return _object_assertions(self.annotations)

    def inlined_dependencies(self, labels: Iterable[str]) -> tuple[str, ...]:
        """Return exact known Block labels named by any retained wording."""

        current = self.current_edition
        texts = (current.text,) if current is not None else ()
        return tuple(
            label
            for label in labels
            if any(
                re.search(rf"(?<![\w.]){re.escape(label)}(?![\w.])", text)
                for text in texts
            )
        )


class DesignLineShip(DiagramLineShip):
    pass


class DesignDefinitionLineShip(DesignLineShip):
    pass


class DesignDecisionLineShip(DesignLineShip):
    pass


class DesignConstraintLineShip(DesignLineShip):
    pass


class DesignRejectionLineShip(DesignLineShip):
    pass


class DesignPrincipleLineShip(DesignLineShip):
    pass


class DesignFreedomLineShip(DesignLineShip):
    pass


class DesignExampleLineShip(DesignLineShip):
    pass


class IssueResolveLineShip(DiagramLineShip):
    pass
