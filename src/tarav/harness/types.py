"""Schema-neutral Tarav Type roles and explicit trusted registration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import ClassVar, Generic, TypeVar


class TaravType:
    """Semantic participation in Tarav's typed mechanics."""


class TaravRecordType(TaravType):
    """Python behavior selected by a Tarav Record's top-level ``type``."""

    type_name: ClassVar[str]


class TaravAssertion(TaravType):
    """Semantic role for an auditable Tarav Assertion."""


class TaravPOIInstance(TaravType):
    """Semantic role for a Tarav point-of-interest instance."""


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
        if type_name in self._types:
            raise DuplicateTypeRegistration(
                f"Tarav Type is already registered: {type_name}"
            )
        self._types[type_name] = record_type

    def resolve_type(self, type_name: str) -> type[RecordTypeT]:
        if not isinstance(type_name, str) or not type_name:
            raise InvalidRecordType("Record.type must be a non-empty string")
        try:
            return self._types[type_name]
        except KeyError as exc:
            raise UnknownRecordType(
                f"Tarav Record Type is not registered: {type_name}"
            ) from exc

    def resolve(self, record: Mapping[str, object]) -> type[RecordTypeT]:
        """Resolve one Record without interpreting application-owned fields."""

        type_name = record.get("type")
        if not isinstance(type_name, str) or not type_name:
            raise InvalidRecordType("Record.type must be a non-empty string")
        return self.resolve_type(type_name)

    def types(self) -> tuple[type[RecordTypeT], ...]:
        return tuple(self._types.values())
