"""The running Python environment's explicit external Type bindings."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Literal, Self


from .identity import KERNEL_WORKFLOW_SHIP, TypeShip
from .records import TaravClass, TaravObject, entity
from .loading import LoadedRecord


class EnvironmentTypeError(ValueError):
    """An external Type binding cannot resolve to a TaravObject class."""


class TaravEnvironment(TaravObject):
    """Mutable trusted bindings resolved in this process's installed packages.

    A binding is code-side configuration, never a path read from a Record.
    Rebinding or removing one takes effect on the next registry resolution.
    Python's normal module cache still governs edits to an already imported
    package; changing installed code requires a new process.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("62a7e915-43a1-4d0d-b79e-4019d8e37150"),
            name="Tarav.Environment",
            workflow=KERNEL_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        type: Literal["Tarav.Environment"]

    def __init__(self) -> None:
        super().__init__()
        self._bindings: dict[str, type[TaravObject] | str] = {}
        self._resolved: dict[str, type[TaravObject]] = {}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord) -> Self:
        return cls()

    @property
    def executable(self) -> Path:
        return Path(sys.executable)

    @property
    def prefix(self) -> Path:
        return Path(sys.prefix)

    def bind_type(self, name: str, target: type[TaravObject] | str) -> None:
        """Set one explicit binding; a replacement takes effect immediately."""

        if not isinstance(name, str) or not name:
            raise ValueError("External Type name must be a non-empty string")
        if isinstance(target, str):
            module, separator, attribute = target.partition(":")
            if (
                not separator
                or not module
                or any(not part.isidentifier() for part in module.split("."))
                or not attribute.isidentifier()
            ):
                raise ValueError("Class path must be package.module:Class")
        elif not isinstance(target, type) or not issubclass(target, TaravObject):
            raise TypeError("External Type target must be a TaravObject class or path")
        self._bindings[name] = target
        self._resolved.pop(name, None)

    def unbind_type(self, name: str) -> None:
        del self._bindings[name]
        self._resolved.pop(name, None)

    def has_type(self, name: str) -> bool:
        return name in self._bindings

    @property
    def loaded_types(self) -> tuple[type[TaravObject], ...]:
        return tuple(self._resolved.values())

    @property
    def loaded_names(self) -> tuple[str, ...]:
        return tuple(self._resolved)

    def resolve_type(self, name: str) -> type[TaravObject]:
        """Import one bound class through Python's current installed environment."""

        if name in self._resolved:
            return self._resolved[name]
        target = self._bindings[name]
        if isinstance(target, str):
            module_name, _, attribute = target.partition(":")
            try:
                target = getattr(importlib.import_module(module_name), attribute)
            except (ImportError, AttributeError) as exc:
                raise EnvironmentTypeError(
                    f"Cannot import external Type {name} from {self._bindings[name]}"
                ) from exc
        if not isinstance(target, type) or not issubclass(target, TaravObject):
            raise EnvironmentTypeError(
                f"External Type {name} is not a TaravObject class"
            )
        if entity(target).name != name:
            raise EnvironmentTypeError(
                f"External Type binding {name} resolves to {entity(target).name}"
            )
        self._resolved[name] = target
        return target


__all__ = ["EnvironmentTypeError", "TaravEnvironment"]
