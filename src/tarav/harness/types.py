"""Schema-neutral Tarav Type roles and explicit trusted registration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar
from uuid import UUID

from .ships import ShipIdentityError, ShipOccurrence, TypeShip


class TaravType:
    """Semantic participation in Tarav's typed mechanics."""


class RecordTypeDeclarationError(TypeError):
    """A Record Type subclass does not declare the identity Tarav requires."""


class TaravRecordType(TaravType):
    """Python behavior selected by a Tarav Record's top-level ``type``.

    ``type_ship`` is the Type's durable identity and ``type_name`` its current
    human-facing label. Every subclass, including intermediate bases, declares
    its own Ship: inheriting one would make two Types share an identity.
    """

    type_name: ClassVar[str]
    type_ship: ClassVar[TypeShip]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
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
        return reference.name == getattr(cls, "type_name", None)

    def ship_occurrences(self) -> tuple[ShipOccurrence, ...]:
        """Return the Ships this Record carries, path by path.

        The default exposes only the Record Type Ship. An application class
        opts into cargo Ships by returning concrete ``Ship`` instances; Harness
        never infers a Ship by scanning UUID-shaped values.
        """

        return (ShipOccurrence("type.id", type(self).type_ship),)


class TaravAssertion(TaravType):
    """Semantic role for an auditable Tarav Assertion."""


class TaravPOIInstance(TaravType):
    """Semantic role for a Tarav point-of-interest instance."""


@dataclass(frozen=True, slots=True)
class RecordTypeReference:
    """One retained ``Record.type``, in structural or legacy label form.

    The Type Ship is authoritative for resolution so a known Type keeps
    resolving after its human-facing label is renamed. A retained label with no
    Ship remains readable; the components that are absent, unknown, or
    inconsistent are reported rather than guessed.
    """

    ship: TypeShip | None = None
    name: str | None = None

    @classmethod
    def parse(cls, value: object) -> RecordTypeReference:
        if isinstance(value, str):
            return cls(None, value or None)
        if isinstance(value, Mapping):
            return cls(cls._ship(value.get("id")), cls._name(value.get("name")))
        return cls()

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> RecordTypeReference:
        return cls.parse(record.get("type"))

    @staticmethod
    def _ship(value: object) -> TypeShip | None:
        if value is None:
            return None
        try:
            return TypeShip(value)  # type: ignore[arg-type]
        except ShipIdentityError:
            return None

    @staticmethod
    def _name(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    def describe(self) -> str:
        if self.ship is not None and self.name is not None:
            return f"{self.name} ({self.ship})"
        return self.name or (str(self.ship) if self.ship else "<missing>")


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


RecordTypeT = TypeVar("RecordTypeT", bound=TaravRecordType)


class TypeRegistry(Generic[RecordTypeT]):
    """Exact Record ``type`` to trusted Python class dispatch.

    The registry knows no application schema beyond the top-level ``type``
    field. Registration is explicit: Record data never names an import path or
    causes code to be loaded dynamically.
    """

    def __init__(
        self,
        base_type: type[RecordTypeT],
        record_types: Iterable[type[RecordTypeT]] = (),
    ) -> None:
        if not issubclass(base_type, TaravRecordType):
            raise TypeRegistrationError(
                "TypeRegistry base must be a TaravRecordType subclass"
            )
        self._base_type = base_type
        self._types: dict[str, type[RecordTypeT]] = {}
        self._ships: dict[UUID, type[RecordTypeT]] = {}
        for record_type in record_types:
            self.register(record_type)

    @property
    def base_type(self) -> type[RecordTypeT]:
        return self._base_type

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
        if reference.name is not None:
            return self.resolve_type(reference.name)
        raise InvalidRecordType(
            "Record.type must be a Type name or a {id, name} reference"
        )

    def resolve(self, record: Mapping[str, object]) -> type[RecordTypeT]:
        """Resolve one Record without interpreting application-owned fields."""

        return self.resolve_reference(RecordTypeReference.from_record(record))

    def reference_findings(
        self, reference: RecordTypeReference, *, field: str = "type"
    ) -> tuple[TypeReferenceFinding, ...]:
        """Report what is absent, unknown, or inconsistent in one reference."""

        if reference.ship is None and reference.name is None:
            return (
                TypeReferenceFinding(
                    "record-type-component-missing",
                    field,
                    "Record.type carries no Type Ship and no Type name.",
                ),
            )
        if reference.ship is None:
            if reference.name in self._types:
                return ()
            return (
                TypeReferenceFinding(
                    "record-type-name-unknown",
                    f"{field}.name",
                    f"Record Type name is not registered: {reference.name}.",
                ),
            )
        registered = self._ships.get(reference.ship.uuid)
        if registered is None:
            return (
                TypeReferenceFinding(
                    "record-type-ship-unknown",
                    f"{field}.id",
                    f"Record Type Ship is not registered: {reference.ship}.",
                ),
            )
        if reference.name is None:
            return (
                TypeReferenceFinding(
                    "record-type-component-missing",
                    f"{field}.name",
                    (
                        "Record.type carries no human-facing name for Type Ship "
                        f"{reference.ship}."
                    ),
                ),
            )
        if reference.name != registered.type_name:
            return (
                TypeReferenceFinding(
                    "record-type-name-conflict",
                    f"{field}.name",
                    (
                        f"Record Type Ship {reference.ship} resolves to "
                        f"{registered.type_name}, not {reference.name}."
                    ),
                ),
            )
        return ()

    def types(self) -> tuple[type[RecordTypeT], ...]:
        return tuple(self._types.values())
