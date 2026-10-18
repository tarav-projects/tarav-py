"""Ship identity primitives shared by Tarav applications."""

from __future__ import annotations

from uuid import UUID

from pydantic_core import core_schema


class ShipIdentityError(ValueError):
    """A value cannot be interpreted as a Ship identity."""


def _ship_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError as exc:
            raise ShipIdentityError(f"Ship UUID is malformed: {value!r}") from exc
    raise ShipIdentityError(f"Ship UUID must be a UUID or UUID string: {value!r}")


class Ship:
    """A semantic point addressed by one UUID.

    A Ship UUID is semantically void beyond identity; the attaching class,
    Record, or field supplies its meaning. Specialized Ship classes may add
    behavior, so identity comparison deliberately ignores the concrete class.
    """

    __slots__ = ("_uuid",)

    def __init__(self, uuid: UUID | str) -> None:
        self._uuid = _ship_uuid(uuid)

    @property
    def uuid(self) -> UUID:
        return self._uuid

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Ship):
            return NotImplemented
        return self._uuid == other._uuid

    def __hash__(self) -> int:
        return hash(self._uuid)

    def __str__(self) -> str:
        return str(self._uuid)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self._uuid)!r})"

    # tarav.breadcrumb c58277426e85
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: object,
        _handler: object,
    ) -> core_schema.CoreSchema:
        """Parse UUID strings into Ships while retaining JSON string storage."""

        from_string = core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(strict=True),
        )
        return core_schema.json_or_python_schema(
            json_schema=from_string,
            python_schema=core_schema.union_schema(
                [core_schema.is_instance_schema(cls), from_string]
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                str,
                return_schema=core_schema.str_schema(),
                when_used="json",
            ),
        )


class TypeShip(Ship):
    """The durable identity of one Tarav Record Type.

    The Ship persists while the Type's human-facing label and Python
    implementation evolve across system editions.
    """


class WorkflowShip(Ship):
    """The durable identity of one Tarav Workflow entity."""


KERNEL_WORKFLOW_SHIP = WorkflowShip("5a90530b-2307-4c64-a763-41517d559624")
TYPE_WORKFLOW_SHIP = WorkflowShip("ab3c33a8-56ce-4509-b276-b2974f98d41e")
