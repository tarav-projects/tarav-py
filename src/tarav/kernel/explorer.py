"""Shared contracts for opening entries and exploring named or indexed values."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Self, TypeVar

from .identity import TypeShip
from .records import TaravClass, TaravObject, TaravType


class ExplorerEntry(TaravObject, ABC):
    """One graph placement whose value can be opened without navigation."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("a43238b6-83a8-4bdc-9e36-89fec2240d0d"),
            name="Tarav.Explorer.Entry",
        )

    @property
    @abstractmethod
    def name(self) -> str:
        """A display name for this occurrence, including positional entries."""

    @abstractmethod
    def open(self) -> TaravObject:
        """Return this entry's value without moving an explorer."""


class ExplorerFolder(TaravObject, ABC):
    """A navigable value whose entries are addressed by ordinary names."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("9bf5ce56-2465-41c6-8eb7-1993415fef1e"),
            name="Tarav.Explorer.Folder",
        )

    @abstractmethod
    def ls(self) -> tuple[ExplorerEntry, ...]:
        """List entries without opening their values or moving an explorer."""

    @abstractmethod
    def get(self, name: str) -> ExplorerEntry:
        """Select one named entry without opening its value."""

    def open(self, name: str) -> TaravObject:
        """Open one value without moving an explorer."""

        return self.get(name).open()


class ExplorerList(TaravObject, ABC):
    """A navigable value whose entries are addressed by integer positions."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("ac97bc0d-f055-4d25-bc62-485beae9307b"),
            name="Tarav.Explorer.List",
        )

    @abstractmethod
    def ls(self) -> tuple[ExplorerEntry, ...]:
        """List entries without opening their values or moving an explorer."""

    @abstractmethod
    def get(self, index: int) -> ExplorerEntry:
        """Select one positional entry without opening its value."""

    def open(self, index: int) -> TaravObject:
        """Open one value without moving an explorer."""

        return self.get(index).open()


LocationT = TypeVar("LocationT")


class Explorer(TaravType, ABC, Generic[LocationT]):
    """A route through one graph, with history separate from graph parents."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("03920556-6161-4866-bf7d-eb79d9346b07"),
            name="Tarav.Explorer",
        )

    def __init__(self, current: LocationT) -> None:
        self._current = current
        self._back_stack: list[LocationT] = []
        self._forward_stack: list[LocationT] = []

    @property
    def current(self) -> LocationT:
        return self._current

    @staticmethod
    def _container(value: TaravObject) -> ExplorerFolder | ExplorerList:
        """Check capability independently of workflow membership."""
        if not isinstance(value, (ExplorerFolder, ExplorerList)):
            raise NotADirectoryError(type(value).__name__)
        return value

    @classmethod
    def _select(cls, value: TaravObject, key: str | int) -> ExplorerEntry:
        container = cls._container(value)
        expected = str if isinstance(container, ExplorerFolder) else int
        if type(key) is not expected:
            raise TypeError(f"Explorer key must be {expected.__name__}")
        return container.get(key)

    def _visit(self, location: LocationT) -> None:
        self._back_stack.append(self._current)
        self._current = location
        self._forward_stack.clear()

    def _resume(self, location: LocationT, history: tuple[LocationT, ...]) -> None:
        """Resume at a captured occurrence after an entry was held elsewhere."""

        self._current = location
        self._back_stack = list(history)
        self._forward_stack.clear()

    def back(self) -> Self:
        """Retrace one visit; this does not follow a graph parent."""

        if self._back_stack:
            self._forward_stack.append(self._current)
            self._current = self._back_stack.pop()
        return self

    def forward(self) -> Self:
        """Revisit a location undone by back()."""

        if self._forward_stack:
            self._back_stack.append(self._current)
            self._current = self._forward_stack.pop()
        return self

    @abstractmethod
    def ls(self) -> tuple[ExplorerEntry, ...]:
        """List entries at the current location without moving."""

    @abstractmethod
    def get(self, key: str | int) -> ExplorerEntry:
        """Select one entry at the current location without moving."""

    def open(self, key: str | int) -> TaravObject:
        """Open an entry's value without changing navigation history."""

        return self.get(key).open()

    @abstractmethod
    def cd(self, key: str | int) -> Self:
        """Visit a graph-specific navigable location."""

    @abstractmethod
    def pwd(self) -> str:
        """Describe the current route, not a globally stable identity."""


__all__ = ["Explorer", "ExplorerEntry", "ExplorerFolder", "ExplorerList"]
