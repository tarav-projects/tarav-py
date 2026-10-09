"""Settings as a capability: a declared, checked place for an object's controls.

A Type that needs configuration extends `SettingsProvider` and declares a
nested `SettingsInterface`. Its objects then have a bound `.settings`. The
capability only says where settings live; how a workflow uses, combines or
locks the values it reads is that workflow's business. Settings are controls
on how an object operates, never the data the object represents.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import ClassVar, Self

from pydantic import BaseModel, ValidationError

from tarav.l0.kernel import (
    FileRecord,
    NamespaceBase,
    TaravClass,
    TaravObject,
    TaravType,
    TaravTypeDeclarationError,
    TaravWorkflow,
    TypeRegistry,
    TypeShip,
    WorkflowShip,
    current_records,
    entity,
)

SETTINGS_WORKFLOW_SHIP = WorkflowShip("07c04e06-a861-4ecf-b07d-ab4a03cf75ce")
_STATE = "_settings_state"


# tarav.breadcrumb 808882a33ca3fc19336d38801b8a42d73e8eaae3322de8fe307cc7e1a986c8b3
class SettingsWorkflow(TaravWorkflow):
    workflow_name = "settings"
    constitution = "Give capabilities one declared, checked place for their controls."

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ce2da9a2-c230-4007-b635-df9a99ec40ed"),
                          name="Tarav.Workflow.Settings", workflow=SETTINGS_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return SETTINGS_WORKFLOW_SHIP


class SettingsError(ValueError):
    """A setting was addressed or written in a way its Type does not declare."""


def _partition_name(partition: type | str) -> str:
    return partition if isinstance(partition, str) else entity(partition).name


# tarav.breadcrumb 9d1c5048aa7cba67b04943a323fb8aa3a4e0ff49fc0cbc0d4df919d892a0ef12
class SettingsValues(FileRecord):
    """Values for one or more partitions, as passed at construction or loaded from a file."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f1753515-1796-4d89-b1e5-606c16aaeec7"),
                          name="Tarav.Settings.Values", workflow=SETTINGS_WORKFLOW_SHIP)

    class RecordInterface(FileRecord.RecordInterface):
        partitions: dict[str, dict[str, object]]

    def __init__(self, partitions: Mapping[str, Mapping[str, object]] | None = None) -> None:
        super().__init__()
        self.partitions = {name: dict(values) for name, values in (partitions or {}).items()}

    @classmethod
    def of(cls, partition: type | str, **values: object) -> Self:
        """Values for one partition, named by its declaring Type."""
        return cls({_partition_name(partition): values})

    @classmethod
    def from_path(cls, *, path: str | Path,
                  registry: TypeRegistry[TaravObject] | None = None) -> Self:
        """Load retained values through the record registry; no second loader."""
        if registry is None:
            try:
                registry = current_records()
            except RuntimeError:
                registry = TypeRegistry(TaravObject, (cls,))
        return registry.load(path, expected_type=cls)

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(record_data.partitions)

    def _to_record(self) -> Mapping[str, object]:
        return {"type": entity(type(self)).name, "partitions": deepcopy(self.partitions)}

    class Records(FileRecord.Records):
        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name,
                    "partitions": {"Tarav.Example.Type": {"enabled": True}}}


class SettingsReport(FileRecord):
    """An object's settings, or a Type's template, exposed as a Context value."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bd31e274-2aba-46f3-89f5-b4dbd6146ffc"),
                          name="Tarav.Settings.Report", workflow=SETTINGS_WORKFLOW_SHIP)


def _report(value: object) -> SettingsReport:
    return SettingsReport.records.from_record(
        {"type": entity(SettingsReport).name, "value": deepcopy(value)})


def _template(interface: type[BaseModel]) -> dict[str, dict[str, object]]:
    return {
        key: {"type": getattr(field.annotation, "__name__", str(field.annotation)),
              "default": deepcopy(field.default), "description": field.description or ""}
        for key, field in interface.model_fields.items()
    }


# tarav.breadcrumb 8cc10c10b66ee1d4a052a8dba96a6a6b81d7a76d602e74190348eae42592b913
class SettingsProvider(TaravType):
    """Capability: objects of an extending Type have a bound `.settings`.

    A Type declares its own partition as a nested pydantic `SettingsInterface`
    whose fields all have defaults, and lists in `settings_include` the Types
    whose partitions it also wants. Both are read from the class itself:
    a parent's settings are included only by saying so.
    """

    settings_include: ClassVar[tuple[type["SettingsProvider"], ...]] = ()

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("dddd2b80-88e9-4a87-8f4a-69f75610b5a0"),
                          name="Tarav.Settings.Provider", workflow=SETTINGS_WORKFLOW_SHIP)

    # tarav.breadcrumb dd7ed41d200933245f90a2ac1b1f19ce88940114e6400ce41dfa140634208220
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        interface = cls.__dict__.get("SettingsInterface")
        if interface is not None:
            if not isinstance(interface, type) or not issubclass(interface, BaseModel):
                raise TaravTypeDeclarationError(
                    f"{cls.__name__}.SettingsInterface must be a pydantic model")
            required = [key for key, field in interface.model_fields.items()
                        if field.is_required()]
            if required:
                raise TaravTypeDeclarationError(
                    f"{cls.__name__} settings need defaults: {', '.join(required)}")
        for included in cls.__dict__.get("settings_include", ()):
            if not isinstance(included, type) or not issubclass(included, SettingsProvider):
                raise TaravTypeDeclarationError(
                    f"{cls.__name__}.settings_include must list SettingsProvider Types")

    @classmethod
    def settings_partitions(cls) -> dict[str, type[BaseModel]]:
        """This Type's own partition and the ones it explicitly includes."""
        result: dict[str, type[BaseModel]] = {}
        interface = cls.__dict__.get("SettingsInterface")
        if interface is not None:
            result[entity(cls).name] = interface
        for included in cls.__dict__.get("settings_include", ()):
            for name, other in included.settings_partitions().items():
                result.setdefault(name, other)
        return result

    @classmethod
    def class_context(cls, builder: object) -> None:
        super().class_context(builder)
        if cls.settings_partitions():
            builder.add("settings-template",
                        description="The settings this Type declares or includes.",
                        opener=lambda: _report({name: _template(interface) for name, interface
                                                in cls.settings_partitions().items()}))

    # tarav.breadcrumb 0d26ccdceb3f246057aa2822a58dcfea867c57759d7df38c6c7ae39d76b793a5
    class Settings(NamespaceBase["SettingsProvider"]):
        """Read and write an object's settings against its declared template."""

        def _partitions(self) -> dict[str, type[BaseModel]]:
            return type(self.obj).settings_partitions()

        def _state(self) -> dict[str, dict[str, tuple[object, str]]]:
            return self.obj.__dict__.setdefault(_STATE, {})

        def _locate(self, key: str, partition: type | str | None) -> tuple[str, type[BaseModel]]:
            partitions = self._partitions()
            host = type(self.obj).__name__
            if partition is not None:
                name = _partition_name(partition)
                if name not in partitions:
                    raise SettingsError(
                        f"{host} has no settings partition {name}; a Type includes another "
                        "Type's settings by listing it in settings_include")
                candidates = [name]
            else:
                candidates = [name for name, interface in partitions.items()
                              if key in interface.model_fields]
                if len(candidates) > 1:
                    raise SettingsError(
                        f"Setting {key!r} of {host} is declared by several partitions "
                        f"({', '.join(candidates)}); name one with partition=")
            if not candidates or key not in partitions[candidates[0]].model_fields:
                known = sorted(k for interface in partitions.values() for k in interface.model_fields)
                raise SettingsError(
                    f"{host} declares no setting {key!r}; known settings: {', '.join(known) or 'none'}")
            return candidates[0], partitions[candidates[0]]

        def get(self, key: str, *, partition: type | str | None = None) -> object:
            name, interface = self._locate(key, partition)
            stored = self._state().get(name, {})
            if key in stored:
                return deepcopy(stored[key][0])
            return deepcopy(interface.model_fields[key].default)

        def origin(self, key: str, *, partition: type | str | None = None) -> str:
            """Where the current value came from: default, construction, runtime, or file:<path>."""
            name, _ = self._locate(key, partition)
            stored = self._state().get(name, {})
            return stored[key][1] if key in stored else "default"

        def set(self, key: str, *, value: object, partition: type | str | None = None,
                origin: str = "runtime") -> None:
            name, interface = self._locate(key, partition)
            current = {k: v for k, (v, _) in self._state().get(name, {}).items()}
            try:
                interface.model_validate({**current, key: value}, strict=True)
            except ValidationError as exc:
                detail = "; ".join(error["msg"] for error in exc.errors())
                raise SettingsError(
                    f"Setting {key!r} of {type(self.obj).__name__} rejects {value!r}: {detail}"
                ) from exc
            self._state().setdefault(name, {})[key] = (deepcopy(value), origin)

        def apply(self, *, values: SettingsValues | None, origin: str = "construction") -> None:
            """Write every value of a settings object, checked like individual writes."""
            if values is None:
                return
            if not isinstance(values, SettingsValues):
                raise SettingsError("settings must be a SettingsValues object")
            for name, entries in values.partitions.items():
                for key, value in entries.items():
                    self.set(key, value=value, partition=name, origin=origin)

        def describe(self) -> dict[str, dict[str, dict[str, object]]]:
            """Every partition, key, current value and origin, with its declaration."""
            return {
                name: {key: {"value": self.get(key, partition=name),
                             "origin": self.origin(key, partition=name), **declared}
                       for key, declared in _template(interface).items()}
                for name, interface in self._partitions().items()
            }

    @property
    def settings(self) -> Settings:
        return type(self).Settings(self)


def contribute_settings(subject: object, builder: object) -> None:
    """Context contributor: an object with settings gains a `settings` entry."""
    if (isinstance(subject, SettingsProvider) and not isinstance(subject, type)
            and type(subject).settings_partitions()):
        builder.add("settings",
                    description="This object's settings: partitions, values and origins.",
                    opener=lambda: _report(subject.settings.describe()))


SETTINGS_RECORD_TYPES = (SettingsValues, SettingsReport)

__all__ = [
    "SETTINGS_RECORD_TYPES",
    "SETTINGS_WORKFLOW_SHIP",
    "SettingsError",
    "SettingsProvider",
    "SettingsReport",
    "SettingsValues",
    "SettingsWorkflow",
    "contribute_settings",
]
