"""Identified, recursively scoped homes for Lines."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from tarav.l0.kernel import LoadedRecord, Ship, TaravClass, TaravEntity, TypeShip

from .identity import LINES_WORKFLOW_SHIP

if TYPE_CHECKING:
    from . import Line


class Block(TaravEntity):
    """A Line context whose parent adds inherited interpretive context."""

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
        parent_ship: Ship | None = None
        line_ships: list[Ship]
        child_ships: list[Ship]

    class Records(TaravEntity.Records):
        def record_example(self):
            return {
                **super().record_example(),
                "id": "fb635d26-cf6a-4ac8-879c-0dceff4715ad",
                "topic": "Library borrowing",
                "parent_ship": None,
                "line_ships": [],
                "child_ships": [],
            }

    def __init__(
        self,
        *,
        id: Ship,
        topic: str,
        parent: "Block | None" = None,
        lines: Iterable["Line"] = (),
        children: Iterable["Block"] = (),
    ):
        super().__init__(id)
        self.topic = topic
        if parent is not None and not isinstance(parent, Block):
            raise TypeError("Block parent must be a Block")
        if parent is self or (parent is not None and parent.id == self.id):
            raise ValueError("A Block cannot parent itself")
        self._parent_ship = parent.id if parent is not None else None
        self._parent = parent
        self._lines = self._validated_lines(lines)
        self._line_ships = tuple(line.id for line in self._lines)
        self._children = self._validated_children(children)
        self._child_ships = tuple(child.id for child in self._children)

    @property
    def topic(self) -> str:
        return self._topic

    @topic.setter
    def topic(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Block topic must be non-empty text")
        self._topic = value

    @property
    def parent_ship(self) -> Ship | None:
        return self._parent_ship

    @property
    def parent(self) -> "Block | None":
        if self._parent_ship is not None and self._parent is None:
            raise LookupError(f"Unresolved Block parent: {self._parent_ship}")
        return self._parent

    def bind_parent(self, parent: "Block") -> None:
        """Resolve the retained parent identity without changing it."""
        if not isinstance(parent, Block):
            raise TypeError("Block parent must be a Block")
        if parent.id != self._parent_ship:
            raise ValueError("Parent identity does not match the retained Block parent")
        current = parent
        seen = {self.id}
        while current is not None:
            if current.id in seen:
                raise ValueError("Block parent cycle")
            seen.add(current.id)
            current = current._parent
        self._parent = parent

    def ancestors(self) -> tuple["Block", ...]:
        """Return the direct parent first; reject cycles instead of looping."""
        result = []
        seen = {self.id}
        current = self.parent
        while current is not None:
            if current.id in seen:
                raise ValueError("Block parent cycle")
            seen.add(current.id)
            result.append(current)
            current = current.parent
        return tuple(result)

    @property
    def line_ships(self) -> tuple[Ship, ...]:
        return self._line_ships

    @property
    def lines(self) -> tuple["Line", ...]:
        if self._lines is None:
            raise LookupError("Block Lines have not been resolved")
        return self._lines

    @property
    def child_ships(self) -> tuple[Ship, ...]:
        return self._child_ships

    @property
    def children(self) -> tuple["Block", ...]:
        if self._children is None:
            raise LookupError("Block children have not been resolved")
        return self._children

    def append(self, line: "Line") -> None:
        """Add a Line authored in this Block."""
        self._lines = self._validated_lines((*self.lines, line))
        self._line_ships = tuple(item.id for item in self._lines)

    def bind_lines(self, lines: Iterable["Line"]) -> None:
        values = self._validated_lines(lines)
        if tuple(line.id for line in values) != self._line_ships:
            raise ValueError("Lines do not match the retained Block order")
        self._lines = values

    def append_child(self, child: "Block") -> None:
        self._children = self._validated_children((*self.children, child))
        self._child_ships = tuple(item.id for item in self._children)

    def bind_children(self, children: Iterable["Block"]) -> None:
        values = self._validated_children(children)
        if tuple(child.id for child in values) != self._child_ships:
            raise ValueError("Children do not match the retained Block order")
        self._children = values

    def _validated_lines(self, lines: Iterable["Line"]) -> tuple["Line", ...]:
        from . import Line

        values = tuple(lines)
        if any(not isinstance(line, Line) for line in values):
            raise TypeError("Block members must be Lines")
        if len({line.id for line in values}) != len(values):
            raise ValueError("A Line cannot appear twice in one Block")
        if any(line.scope_ship != self.id for line in values):
            raise ValueError("Line scope must be this Block")
        return values

    def _validated_children(self, children: Iterable["Block"]) -> tuple["Block", ...]:
        values = tuple(children)
        if any(not isinstance(child, Block) for child in values):
            raise TypeError("Block children must be Blocks")
        if len({child.id for child in values}) != len(values):
            raise ValueError("A child Block cannot appear twice")
        if any(child.id == self.id or child.parent_ship != self.id for child in values):
            raise ValueError("Child parent must be this Block")
        return values

    def _to_record(self):
        return {
            **super()._to_record(),
            "topic": self.topic,
            "parent_ship": str(self.parent_ship) if self.parent_ship else None,
            "line_ships": [str(ship) for ship in self.line_ships],
            "child_ships": [str(ship) for ship in self.child_ships],
        }

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        obj = cls.__new__(cls)
        TaravEntity.__init__(obj, loaded.data.id)
        obj.topic = loaded.data.topic
        obj._parent_ship = loaded.data.parent_ship
        obj._parent = None
        obj._line_ships = tuple(loaded.data.line_ships)
        obj._lines = () if not obj._line_ships else None
        obj._child_ships = tuple(loaded.data.child_ships)
        obj._children = () if not obj._child_ships else None
        return obj

    def ships(self):
        parent = (self.parent_ship,) if self.parent_ship is not None else ()
        return (*super().ships(), *parent, *self.line_ships, *self.child_ships)
