"""Natural-language statements interpreted within identified Blocks."""

import re

from pydantic import Field

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip
from .workflow import LinesWorkflow
from .identity import LINES_WORKFLOW_SHIP
from .block import Block
from tarav.l0.kernel import LoadedRecord
from .predicates import SCOPE, TEXT


# tarav.breadcrumb 72c9de0ef660
# tarav.breadcrumb 0856c8045fb9
class Line(TaravEntity):
    """One statement interpreted within exactly one authoring Block."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("837b7bbb-f7ea-4456-ab76-3d0dbda7fdc5"),
                          name="Tarav.Lines.Line", workflow=LINES_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        text: str
        scope_ship: Ship

    class Records(TaravEntity.Records):
        def record_example(self):
            return {**super().record_example(),
                    "id": "93d415af-e04b-4e2b-a7c6-ea6514c6827b",
                    "text": "It is red.",
                    "scope_ship": "611a6454-f1c7-4647-8944-a6c6fd643119"}

    # tarav.breadcrumb f3ba79fc2a57
    class Context(TaravEntity.Context):
        def _obj_context_hook(self, cxt):
            super()._obj_context_hook(cxt)
            cxt.triplets.extend(((self.obj, TEXT, self.obj.text),
                                 (self.obj, SCOPE, self.obj.scope)))


    def __init__(self, *, id: Ship, text: str, scope: Block):
        super().__init__(id)
        if not isinstance(scope, Block):
            raise TypeError("Line scope must be a Block")
        self.text = text
        self._scope_ship = scope.id
        self._scope = scope

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        if not isinstance(value, str):
            raise TypeError("text must be a string")
        self._text = value

    @property
    def scope(self):
        if self._scope is None:
            raise LookupError(f"Unresolved Line scope: {self._scope_ship}")
        return self._scope

    @property
    def scope_ship(self):
        return self._scope_ship

    def bind_scope(self, scope: Block):
        """Resolve the retained edge without changing its semantic identity."""
        if not isinstance(scope, Block):
            raise TypeError("Line scope must be a Block")
        if scope.id != self._scope_ship:
            raise ValueError("scope identity does not match the retained scope")
        self._scope = scope

    def _to_record(self):
        return {**super()._to_record(), "text": self.text,
                "scope_ship": str(self.scope_ship)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        obj = cls.__new__(cls)
        TaravEntity.__init__(obj, loaded.data.id)
        obj.text = loaded.data.text
        obj._scope_ship = loaded.data.scope_ship
        obj._scope = None
        return obj

    def ships(self):
        return (*super().ships(), self.scope_ship)

_BLOCK_TITLE_PATTERN = r"^[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+$"


class BlockTitle(Line):
    """A Block's citable dotted label, carried as one of its Lines.

    At least two capitalized alphanumeric segments are required. Dots join
    words, without declaring ancestry or replacing the Block's Ship identity.
    """

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("33d92043-9994-4424-b52a-0b8530cddb47"),
            name="Tarav.Lines.BlockTitle",
            workflow=LINES_WORKFLOW_SHIP,
        )

    class RecordInterface(Line.RecordInterface):
        text: str = Field(pattern=_BLOCK_TITLE_PATTERN)

    class Records(Line.Records):
        def record_example(self):
            return {**super().record_example(), "text": "Kernel.Writing"}

    @Line.text.setter
    def text(self, value):
        if not isinstance(value, str):
            raise TypeError("BlockTitle text must be a string")
        if re.fullmatch(_BLOCK_TITLE_PATTERN, value) is None:
            raise ValueError(
                "BlockTitle requires at least two capitalized alphanumeric "
                "segments separated by dots, e.g. Kernel.Writing"
            )
        self._text = value


__all__ = ["Block", "BlockTitle", "Line", "LinesWorkflow"]
