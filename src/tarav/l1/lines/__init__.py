"""Scoped natural-language statements, independent of Models."""

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip
from .workflow import LinesWorkflow
from .identity import LINES_WORKFLOW_SHIP
from .block import Block
from tarav.l0.kernel import LoadedRecord


class Line(TaravEntity):
    """One statement interpreted within exactly one entity scope."""

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


    def __init__(self, *, id: Ship, text: str, scope: TaravEntity):
        super().__init__(id)
        if not isinstance(scope, TaravEntity):
            raise TypeError("scope must be a TaravEntity")
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

    def bind_scope(self, scope: TaravEntity):
        """Resolve the retained edge without changing its semantic identity."""
        if not isinstance(scope, TaravEntity):
            raise TypeError("scope must be a TaravEntity")
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

__all__ = ["Block", "Line", "LinesWorkflow"]
