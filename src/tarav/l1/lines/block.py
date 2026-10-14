"""A named topic with an ordered collection of Lines."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip
from tarav.l1.context import ContextList

from .identity import LINES_WORKFLOW_SHIP

if TYPE_CHECKING:
    from . import Line


class Block(TaravEntity):
    """Group Lines by topic without changing any Line's interpretive scope."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("8219da69-cb28-439a-813a-a42425acd709"),
            name="Tarav.Lines.Block",
            workflow=LINES_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        topic: str
        line_ships: list[Ship]

    class Records(TaravEntity.Records):
        def record_example(self):
            return {
                **super().record_example(),
                "id": "fb635d26-cf6a-4ac8-879c-0dceff4715ad",
                "topic": "Library borrowing",
                "line_ships": [],
            }


    def __init__(self, *, id: Ship, topic: str, lines: Iterable["Line"] = ()):
        super().__init__(id)
        self.topic = topic
        self._lines = self._validated_lines(lines)
        self._line_ships = tuple(line.id for line in self._lines)

    @property
    def topic(self) -> str:
        return self._topic

    @topic.setter
    def topic(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Block topic must be non-empty text")
        self._topic = value

    @property
    def line_ships(self) -> tuple[Ship, ...]:
        return self._line_ships

    @property
    def lines(self) -> tuple["Line", ...]:
        if self._lines is None:
            raise LookupError("Block Lines have not been resolved")
        return self._lines

    def append(self, line: "Line") -> None:
        """Add a Line to this Block; its scope remains unchanged."""
        self._lines = self._validated_lines((*self.lines, line))
        self._line_ships = tuple(item.id for item in self._lines)

    def bind_lines(self, lines: Iterable["Line"]) -> None:
        """Resolve retained membership without changing the ordered relationship."""
        values = self._validated_lines(lines)
        if tuple(line.id for line in values) != self._line_ships:
            raise ValueError("Lines do not match the retained Block order")
        self._lines = values

    @staticmethod
    def _validated_lines(lines: Iterable["Line"]) -> tuple["Line", ...]:
        from . import Line

        values = tuple(lines)
        if any(not isinstance(line, Line) for line in values):
            raise TypeError("Block members must be Lines")
        if len({line.id for line in values}) != len(values):
            raise ValueError("A Line cannot appear twice in one Block")
        return values

    def _to_record(self):
        return {
            **super()._to_record(),
            "topic": self.topic,
            "line_ships": [str(ship) for ship in self.line_ships],
        }

    @classmethod
    def _from_record(cls, record_data):
        obj = cls.__new__(cls)
        TaravEntity.__init__(obj, record_data.id)
        obj.topic = record_data.topic
        obj._line_ships = tuple(record_data.line_ships)
        obj._lines = () if not obj._line_ships else None
        return obj

    def ships(self):
        return (*super().ships(), *self.line_ships)

    def obj_context(self, builder):
        super().obj_context(builder)

        def populate_lines(lines_builder):
            for index, line in enumerate(self.lines):
                lines_builder.add(index, opener=lambda line=line: line)

        builder.add("lines", opener=lambda: ContextList(self, populate_lines))
