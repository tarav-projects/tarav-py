"""Record Type identity resolution and trusted Python class dispatch."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Generic, TypeVar, cast
from uuid import UUID

from .identity import ShipIdentityError, TypeShip
from .environment import EnvironmentTypeError, TaravEnvironment
from .records import TaravObject, _json_object, entity

TYPE_RESOLUTION_PATH: Final[tuple[tuple[str, ...], ...]] = (
    ("__tarav__", "type"),
    ("type",),
)
"""The single ordered sequence of literal key paths locating a Record's Type.

`__tarav__` is the reserved namespace an application uses when its own records
already give `type` a different meaning. The sequence is Kernel-owned:
applications, registries, Record families, and concrete Types cannot configure
it, so any Record's Type reference is found the same way everywhere.
"""

_MISSING = object()


def _traverse(record: Mapping[str, object], path: tuple[str, ...]) -> object:
    cursor: object = record
    for segment in path:
        if not isinstance(cursor, Mapping) or segment not in cursor:
            return _MISSING
        cursor = cursor[segment]
    return cursor


@dataclass(frozen=True, slots=True)
class RecordTypeLocation:
    """The Type.Resolution.PATH entry that supplied a Record's Type reference."""

    path: tuple[str, ...]
    value: object

    @property
    def field(self) -> str:
        return ".".join(self.path)


def locate_record_type(record: Mapping[str, object]) -> RecordTypeLocation | None:
    """Select the first `Type.Resolution.PATH` entry present in one Record.

    A path exists once every segment is present, even when the final value is
    null or empty. Existence alone selects: a present but unusable value fails
    at that path rather than falling through, so a malformed reference can
    never be shadowed by a later one.
    """

    for path in TYPE_RESOLUTION_PATH:
        value = _traverse(record, path)
        if value is not _MISSING:
            return RecordTypeLocation(path, value)
    return None


def _resolution_paths() -> str:
    return ", ".join(".".join(path) for path in TYPE_RESOLUTION_PATH)


@dataclass(frozen=True, slots=True)
class RecordTypeReference:
    """One retained ``Record.type``, in structural or legacy label form.

    The Type Ship is authoritative for resolution so a known Type keeps
    resolving after its human-facing label is renamed. A retained label with no
    Ship remains readable; the components that are absent, unknown, or
    inconsistent are reported rather than guessed.
    """

    ship: TypeShip | None = None
    label: str | None = None

    @classmethod
    def parse(cls, value: object) -> RecordTypeReference:
        if isinstance(value, str):
            return cls(None, value or None)
        if isinstance(value, Mapping):
            return cls(cls._ship(value.get("uuid")), cls._label(value.get("label")))
        return cls()

    @staticmethod
    def _ship(value: object) -> TypeShip | None:
        if value is None:
            return None
        try:
            return TypeShip(value)  # type: ignore[arg-type]
        except ShipIdentityError:
            return None

    @staticmethod
    def _label(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    def describe(self) -> str:
        if self.ship is not None and self.label is not None:
            return f"{self.label} ({self.ship})"
        return self.label or (str(self.ship) if self.ship else "<missing>")


@dataclass(frozen=True, slots=True)
# tarav.breadcrumb 8d46544023e1aece5d966c8221591fe88e7c9f95ae79bfd29ede11a5d3a5bf82
class TypeReferenceObservation:
    """One deterministic observation about a retained Type reference."""

    code: str
    field: str
    message: str


class TypeRegistrationError(ValueError):
    """The trusted Type registry cannot satisfy a registration or lookup."""


class DuplicateTypeRegistration(TypeRegistrationError):
    pass


class UnknownRecordType(TypeRegistrationError):
    pass


class InvalidRecordType(TypeRegistrationError):
    pass


RecordTypeT = TypeVar("RecordTypeT", bound=TaravObject)


class TypeRegistry(Generic[RecordTypeT]):
    """Exact retained Type reference to trusted Python class dispatch.

    The registry knows no application schema beyond the reference selected by
    ``Type.Resolution.PATH``. Registration is explicit: Record data never names
    an import path or causes code to be loaded dynamically.
    """

    def __init__(
        self,
        base_type: type[RecordTypeT],
        record_types: Iterable[type[RecordTypeT]] = (),
        *,
        environment: TaravEnvironment | None = None,
    ) -> None:
        if not issubclass(base_type, TaravObject):
            raise TypeRegistrationError(
                "TypeRegistry base must be a TaravObject subclass"
            )
        self._base_type = base_type
        self.environment = (
            environment if environment is not None else TaravEnvironment()
        )
        self._external_validator: Callable[[type[RecordTypeT]], None] | None = None
        self._types: dict[str, type[RecordTypeT]] = {}
        self._ships: dict[UUID, type[RecordTypeT]] = {}
        for record_type in record_types:
            self.register(record_type)

    @property
    def base_type(self) -> type[RecordTypeT]:
        return self._base_type

    @property
    def record_types(self) -> tuple[type[RecordTypeT], ...]:
        """Registered authority classes, in registration order."""
        return (
            *self._ships.values(),
            *(cast(type[RecordTypeT], item) for item in self.environment.loaded_types),
        )

    def validate_external_with(
        self, validator: Callable[[type[RecordTypeT]], None]
    ) -> None:
        """Apply a runtime-owned check when an external class is resolved."""

        self._external_validator = validator

    def load(
        self,
        path: str | Path,
        *,
        expected_type: type[RecordTypeT] | None = None,
        entry_paths: tuple[str, ...] | None = None,
    ) -> RecordTypeT:
        from .records import _load_record

        return _load_record(
            path, registry=self, expected_type=expected_type, entry_paths=entry_paths
        )

    def register(self, record_type: type[RecordTypeT]) -> None:
        if not issubclass(record_type, self._base_type):
            raise TypeRegistrationError(
                f"{record_type.__name__} is not a {self._base_type.__name__} subclass"
            )
        class_entity = entity(record_type)
        type_name = class_entity.name
        type_ship = class_entity.id
        if not isinstance(type_ship, TypeShip):
            raise TypeRegistrationError(
                f"{record_type.__name__} class Entity id must be a TypeShip"
            )
        if type_name in self._types:
            raise DuplicateTypeRegistration(
                f"Tarav Type name is already registered: {type_name}"
            )
        if self.environment.has_type(type_name):
            raise DuplicateTypeRegistration(
                f"Tarav Type name is bound in the environment: {type_name}"
            )
        if type_ship.uuid in self._ships:
            raise DuplicateTypeRegistration(
                f"Tarav Type Ship is already registered: {type_ship}"
            )
        self._types[type_name] = record_type
        self._ships[type_ship.uuid] = record_type

    def resolve_type(self, type_name: str) -> type[RecordTypeT]:
        if not isinstance(type_name, str) or not type_name:
            raise InvalidRecordType("Record.type must be a non-empty string")
        if type_name in self._types:
            if self.environment.has_type(type_name):
                raise DuplicateTypeRegistration(
                    f"Tarav Type name is also bound in the environment: {type_name}"
                )
            return self._types[type_name]
        if self.environment.has_type(type_name):
            try:
                target = self.environment.resolve_type(type_name)
            except EnvironmentTypeError as exc:
                raise TypeRegistrationError(str(exc)) from exc
            if not issubclass(target, self._base_type):
                raise TypeRegistrationError(
                    f"External Type {type_name} is not a {self._base_type.__name__}"
                )
            class_ship = entity(target).id
            if class_ship.uuid in self._ships:
                raise DuplicateTypeRegistration(
                    f"External Type Ship is already registered: {class_ship}"
                )
            for other in self.environment.loaded_types:
                if other is not target and entity(other).id == class_ship:
                    raise DuplicateTypeRegistration(
                        f"External Type Ship is already bound: {class_ship}"
                    )
            result = cast(type[RecordTypeT], target)
            if self._external_validator is not None:
                self._external_validator(result)
            return result
        raise UnknownRecordType(f"Tarav Record Type is not registered: {type_name}")

    def resolve_ship(self, type_ship: TypeShip) -> type[RecordTypeT]:
        if type_ship.uuid in self._ships:
            return self._ships[type_ship.uuid]
        for name in self.environment.loaded_names:
            target = self.resolve_type(name)
            if entity(target).id == type_ship:
                return target
        raise UnknownRecordType(
            f"Tarav Record Type Ship is not registered: {type_ship}"
        )

    def resolve_reference(self, reference: RecordTypeReference) -> type[RecordTypeT]:
        """Resolve one Type reference, preferring its authoritative Ship.

        A present Ship decides the Type on its own, so a renamed label never
        changes what a known Record resolves to. A label-only reference stays
        readable through the name index.
        """

        if reference.ship is not None:
            if reference.ship.uuid not in self._ships and reference.label is not None:
                if self.environment.has_type(reference.label):
                    target = self.resolve_type(reference.label)
                    if entity(target).id == reference.ship:
                        return target
            return self.resolve_ship(reference.ship)
        if reference.label is not None:
            return self.resolve_type(reference.label)
        raise InvalidRecordType(
            "Record.type must be a Type label or a {uuid, label} reference"
        )

    def resolve(self, record: Mapping[str, object]) -> type[RecordTypeT]:
        """Resolve one Record through `Type.Resolution.PATH`.

        Only the selected path is consulted, so an unusable reference reports
        the exact location that supplied it instead of resolving elsewhere.
        """

        location = locate_record_type(record)
        if location is None:
            raise InvalidRecordType(
                "Record carries no Type reference at any Type.Resolution.PATH "
                f"entry: {_resolution_paths()}"
            )
        reference = RecordTypeReference.parse(location.value)
        if reference.ship is None and reference.label is None:
            raise InvalidRecordType(
                f"{location.field} is not a Tarav Type reference: {location.value!r}"
            )
        try:
            return self.resolve_reference(reference)
        except UnknownRecordType as exc:
            raise UnknownRecordType(f"{exc} (at {location.field})") from None

    def from_record(self, value: object) -> RecordTypeT:
        """Resolve JSON and construct it through the selected semantic class."""

        record = _json_object(value)
        return self._construct(record, self.resolve(record))

    def _construct(
        self, record: Mapping[str, object], authority: type[RecordTypeT]
    ) -> RecordTypeT:
        """Construct with an already checked Type and bind nested Record loading."""

        # tarav.breadcrumb 468893297110bc212d846527957d628e8b9f195279e1411a7eb08e766a6c5d92
        result = authority.records.from_record(record)
        bind_loader = getattr(result, "_bind_record_loader", None)
        if bind_loader is not None:
            bind_loader(self.from_record)
        return result

    def record_observations(
        self, record: Mapping[str, object]
    ) -> tuple[TypeReferenceObservation, ...]:
        """Report what one Record's Type reference is missing or disagrees on."""

        location = locate_record_type(record)
        if location is None:
            return (
                TypeReferenceObservation(
                    "record-type-component-missing",
                    TYPE_RESOLUTION_PATH[-1][0],
                    "Record carries no Type reference at any "
                    f"Type.Resolution.PATH entry: {_resolution_paths()}.",
                ),
            )
        return self.reference_observations(
            RecordTypeReference.parse(location.value), field=location.field
        )

    def reference_observations(
        self, reference: RecordTypeReference, *, field: str = "type"
    ) -> tuple[TypeReferenceObservation, ...]:
        """Report what is absent, unknown, or inconsistent in one reference."""

        if reference.ship is None and reference.label is None:
            return (
                TypeReferenceObservation(
                    "record-type-component-missing",
                    field,
                    "Record.type carries no Type Ship and no Type label.",
                ),
            )
        if reference.ship is None:
            if reference.label in self._types or self.environment.has_type(
                reference.label
            ):
                return ()
            return (
                TypeReferenceObservation(
                    "record-type-label-unknown",
                    f"{field}.label",
                    f"Record Type label is not registered: {reference.label}.",
                ),
            )
        registered = self._ships.get(reference.ship.uuid)
        if registered is None and reference.label is not None:
            if self.environment.has_type(reference.label):
                try:
                    candidate = self.resolve_type(reference.label)
                    if entity(candidate).id == reference.ship:
                        registered = candidate
                except TypeRegistrationError:
                    pass
        if registered is None:
            return (
                TypeReferenceObservation(
                    "record-type-ship-unknown",
                    f"{field}.uuid",
                    f"Record Type Ship is not registered: {reference.ship}.",
                ),
            )
        if reference.label is None:
            return (
                TypeReferenceObservation(
                    "record-type-component-missing",
                    f"{field}.label",
                    (
                        "Record.type carries no human-facing label for Type Ship "
                        f"{reference.ship}."
                    ),
                ),
            )
        if reference.label != entity(registered).name:
            return (
                TypeReferenceObservation(
                    "record-type-label-conflict",
                    f"{field}.label",
                    (
                        f"Record Type Ship {reference.ship} resolves to "
                        f"{entity(registered).name}, not {reference.label}."
                    ),
                ),
            )
        return ()

    def types(self) -> tuple[type[RecordTypeT], ...]:
        return self.record_types
