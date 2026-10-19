"""Identified, recursively scoped homes for Lines."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from tarav.l0.kernel import LoadedRecord, Ship, TaravClass, TaravEntity, TypeShip

from .identity import LINES_WORKFLOW_SHIP

if TYPE_CHECKING:
    from . import Line


# tarav.breadcrumb 80b50b40f0e3
# tarav.breadcrumb f64191c3c729
# tarav.breadcrumb e7b8672cb2df
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
        parent_ship: Ship | None = None
        content_ships: list[Ship]

    class Records(TaravEntity.Records):
        def record_example(self):
            return {
                **super().record_example(),
                "id": "fb635d26-cf6a-4ac8-879c-0dceff4715ad",
                "parent_ship": None,
                "content_ships": [],
            }

    def __init__(
        self,
        *,
        id: Ship,
        parent: "Block | None" = None,
        contents: Iterable["Line | Block"] = (),
    ):
        super().__init__(id)
        if parent is not None and not isinstance(parent, Block):
            raise TypeError("Block parent must be a Block")
        if parent is self or (parent is not None and parent.id == self.id):
            raise ValueError("A Block cannot parent itself")
        self._parent_ship = parent.id if parent is not None else None
        self._parent = parent
        self._contents = self._validated_contents(contents)
        self._content_ships = tuple(item.id for item in self._contents)

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
    def content_ships(self) -> tuple[Ship, ...]:
        return self._content_ships

    @property
    def contents(self) -> tuple["Line | Block", ...]:
        if self._contents is None:
            raise LookupError("Block contents have not been resolved")
        return self._contents

    def append(self, item: "Line | Block") -> None:
        """Append a Line or nested Block without changing its authoring context."""
        self._contents = self._validated_contents((*self.contents, item))
        self._content_ships = tuple(value.id for value in self._contents)

    def bind_contents(self, contents: Iterable["Line | Block"]) -> None:
        """Resolve the retained members in their exact mixed order."""
        values = self._validated_contents(contents)
        if tuple(item.id for item in values) != self._content_ships:
            raise ValueError("Contents do not match the retained Block order")
        self._contents = values

    def _validated_contents(
        self, contents: Iterable["Line | Block"]
    ) -> tuple["Line | Block", ...]:
        from . import Line

        values = tuple(contents)
        if any(not isinstance(item, (Line, Block)) for item in values):
            raise TypeError("Block contents must be Lines or Blocks")
        if len({item.id for item in values}) != len(values):
            raise ValueError("A member cannot appear twice in one Block")
        for item in values:
            if isinstance(item, Line):
                if item.scope_ship != self.id:
                    raise ValueError("Line scope must be this Block")
            elif item.id == self.id or item.parent_ship != self.id:
                raise ValueError("Child parent must be this Block")
        return values

    def _to_record(self):
        return {
            **super()._to_record(),
            "parent_ship": str(self.parent_ship) if self.parent_ship else None,
            "content_ships": [str(ship) for ship in self.content_ships],
        }

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        obj = cls.__new__(cls)
        TaravEntity.__init__(obj, loaded.data.id)
        obj._parent_ship = loaded.data.parent_ship
        obj._parent = None
        obj._content_ships = tuple(loaded.data.content_ships)
        obj._contents = () if not obj._content_ships else None
        return obj

    def ships(self):
        parent = (self.parent_ship,) if self.parent_ship is not None else ()
        return (*super().ships(), *parent, *self.content_ships)
