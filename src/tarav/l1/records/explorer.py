"""A route through contributed Record sources, independent of their storage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from tarav.l0.kernel import (
    Explorer, ExplorerEntry, ExplorerFolder, TaravClass, TaravObject, TypeShip,
)

from .identity import RECORDS_WORKFLOW_SHIP


class RecordsNavigationError(RuntimeError):
    """A source could not supply the requested navigation value."""


class RecordsEntry(ExplorerEntry):
    """One occurrence in a Record source, including a source root."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("4ee0d713-bc43-4957-a21c-27927f811ac2"),
            name="Tarav.Records.Entry",
            workflow=RECORDS_WORKFLOW_SHIP,
        )

    def __init__(self, service: object, parent: str, name: str, kind: str) -> None:
        super().__init__()
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("Record entry name must be one path segment")
        self.service = service
        self.parent = parent
        self._name = name
        self.kind = kind

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> str:
        return f"{self.parent.rstrip('/')}/{self.name}"

    @property
    def navigable(self) -> bool:
        return self.kind in {"provider", "collection", "directory-record"}

    def folder(self) -> RecordsFolder:
        if not self.navigable:
            raise NotADirectoryError(self.path)
        return RecordsFolder(self.service, self.path)

    def open(self) -> TaravObject:
        if self.kind in {"provider", "collection"}:
            return self.folder()
        result = self.service.load(self.path)
        if not result.ok:
            raise RecordsNavigationError(result.pois[0].message)
        return result.value


class RecordsFolder(ExplorerFolder):
    """A navigable projection over one source address."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("2639cc6e-9378-4dc5-a5cd-4c48dfd4da40"),
            name="Tarav.Records.Folder",
            workflow=RECORDS_WORKFLOW_SHIP,
        )

    def __init__(self, service: object, path: str) -> None:
        super().__init__()
        self.service = service
        self.path = path

    def ls(self) -> tuple[RecordsEntry, ...]:
        result = self.service.list(self.path)
        if not result.ok:
            raise RecordsNavigationError(result.pois[0].message)
        return tuple(
            RecordsEntry(self.service, self.path, entry.name, entry.kind)
            for entry in result.value
        )

    def get(self, name: str) -> RecordsEntry:
        if not isinstance(name, str):
            raise TypeError("Record entry name must be a string")
        for entry in self.ls():
            if entry.name == name:
                return entry
        raise KeyError(name)


class RecordsRoot(RecordsFolder):
    """The source mounts visible to this Records service."""
    # tarav.breadcrumb b020facda37fee75c0e6d0f365a79e2489617fdc80f08911e1593d447dc53bf6

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("9b6c1160-d015-49ca-a221-08ad7ca10205"),
            name="Tarav.Records.Root",
            workflow=RECORDS_WORKFLOW_SHIP,
        )

    def __init__(self, service: object) -> None:
        super().__init__(service, "/")


@dataclass(frozen=True)
class RecordsLocation:
    folder: RecordsFolder
    parent: RecordsLocation | None = None


class RecordsExplorer(Explorer[RecordsLocation]):
    """Filesystem-like route through Record sources, with visit history."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("30009c5f-2d57-4d74-a4de-af12d812b3ec"),
            name="Tarav.Records.Explorer",
            workflow=RECORDS_WORKFLOW_SHIP,
        )

    def __init__(self, service: object) -> None:
        super().__init__(RecordsLocation(RecordsRoot(service)))

    def ls(self) -> tuple[RecordsEntry, ...]:
        return self.current.folder.ls()

    def get(self, key: str | int) -> RecordsEntry:
        return self._select(self.current.folder, key)

    def cd(self, key: str | int) -> Self:
        if not isinstance(key, str):
            raise TypeError("Records path requires a string")
        if "/" in key and key != "/":
            previous = self.current, list(self._back_stack), list(self._forward_stack)
            try:
                if key.startswith("/"):
                    self.cd("/")
                for part in key.split("/"):
                    if part:
                        self.cd(part)
            except Exception:
                self._current, self._back_stack, self._forward_stack = previous
                raise
            return self
        if key == "/":
            root = self.current
            while root.parent is not None:
                root = root.parent
            if root is not self.current:
                self._visit(root)
            return self
        if key == ".":
            return self
        if key == "..":
            if self.current.parent is not None:
                self._visit(self.current.parent)
            return self
        entry = self.get(key)
        self._visit(RecordsLocation(entry.folder(), self.current))
        return self

    def pwd(self) -> str:
        return self.current.folder.path


__all__ = [
    "RecordsEntry", "RecordsExplorer", "RecordsFolder", "RecordsLocation",
    "RecordsNavigationError", "RecordsRoot",
]
