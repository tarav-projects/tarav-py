"""Partial Type models: identified nodes with current Type-relative path labels."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal

from pydantic import ConfigDict, Field

from tarav.l0.kernel.identity import Ship, TypeShip
from tarav.l0.kernel.records import TaravClass, TaravEntity, TaravType, entity

from . import CONTEXT_WORKFLOW_SHIP, ContextBuilder, ContextFolder, ContextType


# tarav.context 473c89a0:7ef12f9536d4a790
class TypePath(TaravEntity, ContextType):
    """An identified semantic member whose current label is a Type-relative path.

    The path is descriptive data, never evaluated. Model membership supplies
    the owning Type; the Ship survives a rename and can carry its own Context.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("7def5a09-4f1f-477f-ac87-f5adc14548da"),
            name="Tarav.Context.TypePath", workflow=CONTEXT_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.Context.TypePath"]
        path: str = Field(min_length=1)

    def __init__(self, id: Ship, path: str) -> None:
        super().__init__(id)
        if not isinstance(path, str) or not path:
            raise ValueError("Type model path must be a nonempty string")
        self.path = path

    @classmethod
    def _from_record(cls, record_data):
        return cls(record_data.id, record_data.path)

    def _to_record(self):
        return {**super()._to_record(), "path": self.path}

    class Records(TaravEntity.Records):
        def record_example(self):
            return {
                "type": entity(self._owner).name,
                "id": "5d7f169e-9893-48b5-90f6-48161f570109",
                "path": "contains",
            }


ModelProvider = Callable[[type[TaravType]], Iterable[TypePath]]


# tarav.context 473c89a0:3fea6e90a968360c
class TypeModel(ContextFolder):
    """A read-only view rooted at a Type Ship, with entries keyed by Ship.

    Only declared nodes exist. ``nodes()`` lists members, ``root`` is the Type
    entity, and ``at(path)`` is a convenience lookup that rejects ambiguity.
    This computed view is not a retained model snapshot.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("92310af6-a627-4c2d-b48a-78144636809e"),
            name="Tarav.Context.TypeModel", workflow=CONTEXT_WORKFLOW_SHIP,
        )

    def __init__(self, subject: type[TaravType], nodes: Callable[[], Iterable[TypePath]]):
        if not isinstance(subject, type) or not issubclass(subject, TaravType):
            raise TypeError("Type models require a TaravType class")
        super().__init__(subject, self._populate)
        self.root = entity(subject)
        self._nodes = nodes

    def _populate(self, builder: ContextBuilder) -> None:
        builder.add(str(self.root.id), opener=lambda: self.root, description="Type root")
        found: dict[Ship, TypePath] = {}
        for node in self._nodes():
            if not isinstance(node, TypePath):
                raise TypeError("Type model providers must return TypePath entities")
            if node.id == self.root.id:
                raise ValueError("A member cannot reuse its Type root's Ship")
            previous = found.get(node.id)
            if previous is not None:
                if previous.records.to_record() != node.records.to_record():
                    raise ValueError(f"Conflicting Type model declarations for {node.id}")
                continue
            found[node.id] = node
            builder.add(str(node.id), opener=lambda node=node: node, description=node.path)

    def nodes(self) -> tuple[TypePath, ...]:
        """Return declared members, excluding the existing Type root."""
        return tuple(entry.open() for entry in self.ls()[1:])

    def at(self, path: str) -> TypePath | TaravClass:
        """Select a current path label; the empty path denotes the Type root."""
        if not isinstance(path, str):
            raise TypeError("Type model path must be a string")
        if path == "":
            return self.root
        matches = [node for node in self.nodes() if node.path == path]
        if not matches:
            raise KeyError(path)
        if len(matches) > 1:
            raise ValueError(f"Ambiguous Type model path: {path}")
        return matches[0]
