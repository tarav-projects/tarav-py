"""Schema-neutral Tarav Type roles and explicit trusted registration."""

from __future__ import annotations

import inspect
import json
import math
from copy import deepcopy
from pathlib import Path
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import BinaryIO, ClassVar, Final, Generic, Self, TextIO, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .ships import Ship, ShipIdentityError, TypeShip


class TaravType:
    """Semantic participation in Tarav's typed mechanics."""


class RecordTypeDeclarationError(TypeError):
    """A Record Type subclass does not declare the identity Tarav requires."""


class InvalidRecordJSON(ValueError):
    """Loaded JSON is not a root Record object."""


class RecordTypeMismatch(TypeError):
    """A requested Record class does not specialize the registered authority."""


JsonFile = TextIO | BinaryIO


class TaravObject(TaravType):
    """Semantic Python object with a typed JSON representation.

    ``type_ship`` is the Type's durable identity and ``type_name`` its current
    human-facing label. Every subclass, including intermediate bases, declares
    its own Ship: inheriting one would make two Types share an identity.
    """

    type_name: ClassVar[str]
    type_ship: ClassVar[TypeShip]

    class RecordInterface(BaseModel):
        """Minimal open record contract; subclasses declare their own fields."""

        model_config = ConfigDict(strict=True, extra="allow")

    @classmethod
    def preserves_parent_record_interface(cls) -> bool:
        """Whether all direct Tarav parents' interfaces are inherited."""
        return all(
            isrecordsubclass(cls, parent)
            for parent in cls.__bases__
            if issubclass(parent, TaravObject)
        )

    @classmethod
    def validate_record(cls, value: object) -> BaseModel:
        """Validate without accepting transformations of supplied JSON data."""
        record = _json_object(value)
        model = cls.RecordInterface.model_validate(deepcopy(record), strict=True)
        represented = model.model_dump(mode="json", exclude_unset=True, by_alias=True)
        if json.dumps(represented, sort_keys=True) != json.dumps(record, sort_keys=True):
            raise InvalidRecordJSON("RecordInterface must not transform or discard supplied data")
        return model

    @property
    def record_data(self) -> BaseModel:
        """Fresh validated typed view; editing this view does not edit the record."""
        return type(self).validate_record(self.record)

    def __init__(self, record: Mapping[str, object]) -> None:
        if type(self) is TaravObject:
            raise TypeError("TaravObject is not an opaque JSON wrapper")
        self.record = dict(record)
        self.source: Path | None = None

    @classmethod
    def from_json(cls, value: object) -> Self:
        """Construct this semantic class from one JSON-compatible object."""

        if cls is TaravObject:
            raise TypeError("TaravObject is not an opaque JSON wrapper")
        record = _json_object(value)
        cls.validate_record(record)
        return cls(record)

    def to_json(self) -> dict[str, object]:
        """Return a detached JSON-compatible representation of this object."""

        type(self).validate_record(self.record)
        return _json_object(self.record)

    @classmethod
    def json_example(cls) -> dict[str, object]:
        """Return a minimal storage-independent representation for this Type."""

        return {"type": cls.type_name}

    @classmethod
    def help(cls) -> dict[str, object]:
        """Return mechanical context for this class, without loading a Record.

        Subclasses may extend this information with documentation, skills, or
        other context entry points. Missing source information stays explicit;
        this method never generates explanatory content or prints output.
        ``source_path`` describes code, not an instance's retained ``source``.
        """
        result: dict[str, object] = {
            "class": f"{cls.__module__}.{cls.__qualname__}",
            "source_path": None,
            "source_line": None,
            "hints": {},
        }
        unavailable: dict[str, str] = {}
        result["hints"] = {"unavailable": unavailable}
        try:
            filename = inspect.getsourcefile(cls)
            if filename is None:
                raise OSError("Python could not locate a source file")
            path = Path(filename).resolve(strict=True)
            if not path.is_file():
                raise OSError("Source path is not a file")
            result["source_path"] = str(path)
        except (OSError, TypeError, ValueError) as exc:
            unavailable["source_path"] = str(exc)
            unavailable["source_line"] = "Source file unavailable"
            return result
        try:
            _, line = inspect.getsourcelines(cls)
            result["source_line"] = line
        except (OSError, TypeError, ValueError) as exc:
            unavailable["source_line"] = str(exc)
        if not unavailable:
            result["hints"] = {}
        return result

    @classmethod
    def load(cls, path: str | Path, *, registry: TypeRegistry[TaravObject]) -> Self:
        """Load a retained representation through its registered authority."""
        from .records import load_record

        return load_record(path, registry=registry, record_class=cls)

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not isinstance(cls.RecordInterface, type) or not issubclass(cls.RecordInterface, BaseModel):
            raise RecordTypeDeclarationError("RecordInterface must be a Pydantic BaseModel class")
        declared = cls.__dict__.get("type_ship")
        if declared is None:
            raise RecordTypeDeclarationError(
                f"{cls.__name__} must declare a class-local type_ship"
            )
        if not isinstance(declared, TypeShip):
            raise RecordTypeDeclarationError(
                f"{cls.__name__}.type_ship must be a TypeShip instance"
            )

    @classmethod
    def matches(cls, reference: RecordTypeReference) -> bool:
        """Whether one retained Type reference designates this class.

        The Ship decides when it is present, so a Record whose label drifted
        still specializes as the Type its Ship identifies.
        """

        if reference.ship is not None:
            return reference.ship == cls.type_ship
        return reference.label == getattr(cls, "type_name", None)

    def ships(self) -> tuple[Ship, ...]:
        """Return the Ships this Record semantically recognizes.

        The default exposes only the Record Type Ship. A subclass extends the
        projection with the Ships its own semantics recognize, returning
        concrete ``Ship`` instances; Harness never infers a Ship by scanning
        UUID-shaped values, and the projection exposes no serialized paths.
        """

        return (type(self).type_ship,)

    @classmethod
    def json_load(
        cls,
        file: JsonFile,
        *,
        registry: TypeRegistry[TaravObject],
    ) -> Self:
        """Load one Record as this registered class or a deliberate subclass."""

        record = _json_load_record(file)
        registered_class = registry.resolve(record)
        if not issubclass(cls, registered_class):
            raise RecordTypeMismatch(
                f"{cls.__name__} does not specialize registered Record class "
                f"{registered_class.__name__}"
            )
        return cls.from_json(record)


def _tarav_object_class(value: object, *, argument: str) -> type[TaravObject]:
    if not isinstance(value, type) or not issubclass(value, TaravObject):
        raise TypeError(f"{argument} must be a TaravObject class")
    return value


def issubrecord(subtype: object, supertype: object) -> bool:
    """Whether two Tarav classes have the declared RecordInterface relationship."""

    sub_class = _tarav_object_class(subtype, argument="subtype")
    super_class = _tarav_object_class(supertype, argument="supertype")
    return issubclass(
        sub_class.RecordInterface,
        super_class.RecordInterface,
    )


def isrecordsubclass(subtype: object, supertype: object) -> bool:
    """Whether behavioral and RecordInterface inheritance both hold."""

    sub_class = _tarav_object_class(subtype, argument="subtype")
    super_class = _tarav_object_class(supertype, argument="supertype")
    return issubclass(sub_class, super_class) and issubrecord(sub_class, super_class)


class TaravAssertion(TaravType):
    """Semantic role for an auditable Tarav Assertion."""


class TaravPOIInstance(TaravType):
    """Semantic role for a Tarav point-of-interest instance."""


TYPE_RESOLUTION_PATH: Final[tuple[tuple[str, ...], ...]] = (
    ("__tarav__", "type"),
    ("type",),
)
"""The single ordered sequence of literal key paths locating a Record's Type.

`__tarav__` is the reserved namespace an application uses when its own records
already give `type` a different meaning. The sequence is Harness-owned:
applications, registries, Record families, and concrete Types cannot configure
it, so any Record's Type reference is found the same way everywhere.
"""

_MISSING = object()


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidRecordJSON("Tarav JSON root must be an object")
    def copy_json(item):
        if item is None or type(item) in (str, bool, int):
            return item
        if type(item) is float and math.isfinite(item):
            return item
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise InvalidRecordJSON("JSON object keys must be strings")
            return {key: copy_json(child) for key, child in item.items()}
        if type(item) is list:
            return [copy_json(child) for child in item]
        raise InvalidRecordJSON(f"Not a JSON value: {type(item).__name__}")

    try:
        return copy_json(value)
    except RecursionError as exc:
        raise InvalidRecordJSON("JSON representation must not contain cycles") from exc


def _json_load_record(file: JsonFile) -> dict[str, object]:
    value = json.load(file)
    if not isinstance(value, Mapping):
        raise InvalidRecordJSON("Tarav JSON root must be an object")
    return _json_object(value)


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
class TypeReferenceFinding:
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
    ) -> None:
        if not issubclass(base_type, TaravObject):
            raise TypeRegistrationError(
                "TypeRegistry base must be a TaravObject subclass"
            )
        self._base_type = base_type
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
        return tuple(self._ships.values())

    def load(self, path: str | Path) -> RecordTypeT:
        from .records import load_record

        return load_record(path, registry=self)

    def register(self, record_type: type[RecordTypeT]) -> None:
        if not issubclass(record_type, self._base_type):
            raise TypeRegistrationError(
                f"{record_type.__name__} is not a {self._base_type.__name__} subclass"
            )
        type_name = getattr(record_type, "type_name", None)
        if not isinstance(type_name, str) or not type_name:
            raise TypeRegistrationError(
                f"{record_type.__name__}.type_name must be a non-empty string"
            )
        type_ship = getattr(record_type, "type_ship", None)
        if not isinstance(type_ship, TypeShip):
            raise TypeRegistrationError(
                f"{record_type.__name__}.type_ship must be a TypeShip instance"
            )
        if type_name in self._types:
            raise DuplicateTypeRegistration(
                f"Tarav Type name is already registered: {type_name}"
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
        try:
            return self._types[type_name]
        except KeyError as exc:
            raise UnknownRecordType(
                f"Tarav Record Type is not registered: {type_name}"
            ) from exc

    def resolve_ship(self, type_ship: TypeShip) -> type[RecordTypeT]:
        try:
            return self._ships[type_ship.uuid]
        except KeyError as exc:
            raise UnknownRecordType(
                f"Tarav Record Type Ship is not registered: {type_ship}"
            ) from exc

    def resolve_reference(self, reference: RecordTypeReference) -> type[RecordTypeT]:
        """Resolve one Type reference, preferring its authoritative Ship.

        A present Ship decides the Type on its own, so a renamed label never
        changes what a known Record resolves to. A label-only reference stays
        readable through the name index.
        """

        if reference.ship is not None:
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

    def json_load(self, file: JsonFile) -> RecordTypeT:
        """Load one JSON Record as an instance of its exact registered class."""

        return self.from_json(_json_load_record(file))

    def from_json(self, value: object) -> RecordTypeT:
        """Resolve JSON and construct it through the selected semantic class."""

        record = _json_object(value)
        return self.resolve(record).from_json(record)

    def record_findings(
        self, record: Mapping[str, object]
    ) -> tuple[TypeReferenceFinding, ...]:
        """Report what one Record's Type reference is missing or disagrees on."""

        location = locate_record_type(record)
        if location is None:
            return (
                TypeReferenceFinding(
                    "record-type-component-missing",
                    TYPE_RESOLUTION_PATH[-1][0],
                    "Record carries no Type reference at any "
                    f"Type.Resolution.PATH entry: {_resolution_paths()}.",
                ),
            )
        return self.reference_findings(
            RecordTypeReference.parse(location.value), field=location.field
        )

    def reference_findings(
        self, reference: RecordTypeReference, *, field: str = "type"
    ) -> tuple[TypeReferenceFinding, ...]:
        """Report what is absent, unknown, or inconsistent in one reference."""

        if reference.ship is None and reference.label is None:
            return (
                TypeReferenceFinding(
                    "record-type-component-missing",
                    field,
                    "Record.type carries no Type Ship and no Type label.",
                ),
            )
        if reference.ship is None:
            if reference.label in self._types:
                return ()
            return (
                TypeReferenceFinding(
                    "record-type-label-unknown",
                    f"{field}.label",
                    f"Record Type label is not registered: {reference.label}.",
                ),
            )
        registered = self._ships.get(reference.ship.uuid)
        if registered is None:
            return (
                TypeReferenceFinding(
                    "record-type-ship-unknown",
                    f"{field}.uuid",
                    f"Record Type Ship is not registered: {reference.ship}.",
                ),
            )
        if reference.label is None:
            return (
                TypeReferenceFinding(
                    "record-type-component-missing",
                    f"{field}.label",
                    (
                        "Record.type carries no human-facing label for Type Ship "
                        f"{reference.ship}."
                    ),
                ),
            )
        if reference.label != registered.type_name:
            return (
                TypeReferenceFinding(
                    "record-type-label-conflict",
                    f"{field}.label",
                    (
                        f"Record Type Ship {reference.ship} resolves to "
                        f"{registered.type_name}, not {reference.label}."
                    ),
                ),
            )
        return ()

    def types(self) -> tuple[type[RecordTypeT], ...]:
        return tuple(self._types.values())
