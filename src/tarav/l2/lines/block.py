"""tarav.l2.lines.block: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

# tarav.breadcrumb 34fe781aec928e9ed7597e6e338c9dc21cae3b57d481abbd7d760061c9264a92

import tarav.l2.unsorted.pois as diagram_pois

from tarav.l2.lines.records import BlockEditionRecord
from tarav.l2.unsorted.pois import DiagramPOI
from tarav.l2.unsorted.contracts import IssueAssessment
from tarav.l2.lines.line import IssueResolveLineShip
from tarav.l2.lines.records import LineEditionRecord
from tarav.l2.lines.records import LineGateAnnotation
from tarav.l2.unsorted.contracts import _dedupe_pois
from tarav.l2.unsorted.contracts import _dedupe_object_assertions
from tarav.l2.unsorted.contracts import _object_assertions
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarav.l2.unsorted.assessment import AssertionEngine
    from tarav.l2.lines.line import DiagramLineShip
    from tarav.l2.unsorted.contracts import DiagramObjectAssertion
    from collections.abc import Iterable
    from tarav.l2.unsorted.records import TypedAnnotation

@dataclass(frozen=True, slots=True)
class DiagramBlock:
    ship: str
    model_ship: str
    annotations: tuple[TypedAnnotation, ...]
    lines: tuple[DiagramLineShip, ...]
    type_ids: tuple[str, ...]
    pois: tuple[DiagramPOI, ...]

    @property
    def object_type(self) -> str | None:
        return self.type_ids[-1] if self.type_ids else None

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(
            item.label
            for item in self.annotations
            if isinstance(item, BlockEditionRecord)
        )

    @property
    def current_label(self) -> str | None:
        labels = self.labels
        return labels[-1] if labels else None

    @property
    def editions(self) -> tuple[BlockEditionRecord, ...]:
        return tuple(
            item for item in self.annotations if isinstance(item, BlockEditionRecord)
        )

    @property
    def current_edition(self) -> BlockEditionRecord | None:
        editions = self.editions
        return editions[-1] if editions else None

    def assertions(self) -> tuple[DiagramObjectAssertion, ...]:
        return _dedupe_object_assertions(
            (
                *_object_assertions(self.annotations),
                *(assertion for line in self.lines for assertion in line.assertions()),
            )
        )

    def inlined_dependencies(self, labels: Iterable[str]) -> tuple[str, ...]:
        """Return exact known Block labels named by contained Line wordings."""

        own_labels = set(self.labels)
        return tuple(
            dict.fromkeys(
                label
                for line in self.lines
                for label in line.inlined_dependencies(labels)
                if label not in own_labels
            )
        )

    @classmethod
    def disclosure_ladder(cls) -> tuple[str, ...]:
        """Return the generic context disclosure levels owned by this Block type."""

        return ("collapsed", "lines", "support", "deep-support")

    def mechanical_pois(
        self, assertion_engine: AssertionEngine
    ) -> tuple[DiagramPOI, ...]:
        return ()


class DesignBlock(DiagramBlock):
    pass


class ImplReqBlock(DiagramBlock):
    pass


class IssueBlock(DiagramBlock):
    def assess(self, assertion_engine: AssertionEngine) -> IssueAssessment:
        resolution_lines = tuple(
            line for line in self.lines if isinstance(line, IssueResolveLineShip)
        )
        assessments = tuple(
            gate_assessment
            for line in resolution_lines
            for annotation in line.annotations
            if isinstance(annotation, (LineEditionRecord, LineGateAnnotation))
            for gate_assessment in assertion_engine.assess(annotation).gate_assessments
        )
        closed = any(item.standing == "Passed" for item in assessments)
        pois = tuple(
            poi for assessment in assessments for poi in assessment.pois
        )
        if not closed:
            pois = (
                *pois,
                diagram_pois.BlockIssueOpen(path=f'block.{self.ship}', message='Issue.Block has no reviewed Issue.Line.Resolve with a passing Verbatim.Gate.'),
            )
        return IssueAssessment(
            self.ship,
            "Closed" if closed else "Open",
            tuple(line.ship for line in resolution_lines),
            assessments,
            _dedupe_pois(pois),
        )

    def mechanical_pois(
        self, assertion_engine: AssertionEngine
    ) -> tuple[DiagramPOI, ...]:
        return self.assess(assertion_engine).pois
