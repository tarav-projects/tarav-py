"""Notebook Types opt into support and optional review without changing base Lines."""

from typing import ClassVar

from pydantic import Field

from tarav.l0.kernel import Ship, TaravClass, TypeShip
from tarav.l1.lines import Block, BlockTitle, Line
from .workflow import NOTEBOOK_WORKFLOW_SHIP


# tarav.breadcrumb b708a75bf77a
class NotebookLine(Line):
    requires_support: ClassVar[bool] = True
    requires_review: ClassVar[bool] = False

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("6a1ed2e9-dba0-4cac-b146-0559cfce812f"),
                          name="Tarav.Notebook.Line", workflow=NOTEBOOK_WORKFLOW_SHIP)

    class RecordInterface(Line.RecordInterface):
        support_ships: list[Ship] = Field(default_factory=list)
        review_ships: list[Ship] = Field(default_factory=list)

    class Records(Line.Records):
        def record_example(self):
            return {**super().record_example(), "support_ships": [], "review_ships": []}

    def __init__(self, *, id, text, scope, support_ships=(), review_ships=()):
        super().__init__(id=id, text=text, scope=scope)
        self.support_ships = list(map(Ship, map(str, support_ships)))
        self.review_ships = list(map(Ship, map(str, review_ships)))

    def _to_record(self):
        return {**super()._to_record(), "support_ships": list(map(str, self.support_ships)),
                "review_ships": list(map(str, self.review_ships))}

    @classmethod
    def _from_record(cls, loaded):
        obj = super()._from_record(loaded)
        obj.support_ships = list(loaded.data.support_ships)
        obj.review_ships = list(loaded.data.review_ships)
        return obj

    def ships(self):
        return (*super().ships(), *self.support_ships, *self.review_ships)


class ReviewedLine(NotebookLine):
    requires_review: ClassVar[bool] = True

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("f40b2d87-e75a-4761-bab6-1ac5f8c22121"),
                          name="Tarav.Notebook.ReviewedLine", workflow=NOTEBOOK_WORKFLOW_SHIP)


class ReviewedBlockTitle(BlockTitle, ReviewedLine):
    """A dotted title with the same support and review obligations as its Lines."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("655a4592-4d19-4c2c-b052-6b885413f6e0"),
                          name="Tarav.Notebook.ReviewedBlockTitle", workflow=NOTEBOOK_WORKFLOW_SHIP)

    class RecordInterface(BlockTitle.RecordInterface, ReviewedLine.RecordInterface):
        pass

    class Records(BlockTitle.Records, ReviewedLine.Records):
        def record_example(self):
            return {**super().record_example(), "text": "Kernel.Writing"}


class SupportedBlock(Block):
    requires_support: ClassVar[bool] = True
    requires_review: ClassVar[bool] = False

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("219ac83a-56a7-4c83-a125-1fce136c5bc2"),
                          name="Tarav.Notebook.SupportedBlock", workflow=NOTEBOOK_WORKFLOW_SHIP)


class ReviewedBlock(SupportedBlock):
    requires_review: ClassVar[bool] = True

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("8f6804c8-de94-4d61-ac98-bd6176569a0c"),
                          name="Tarav.Notebook.ReviewedBlock", workflow=NOTEBOOK_WORKFLOW_SHIP)


NOTEBOOK_EVIDENCE_TYPES = (NotebookLine, ReviewedLine, ReviewedBlockTitle, SupportedBlock, ReviewedBlock)
