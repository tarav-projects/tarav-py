"""Ship identity primitives shared by Tarav applications."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


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


class TypeShip(Ship):
    """The durable identity of one Tarav Record Type.

    The Ship persists while the Type's human-facing label and Python
    implementation evolve across system editions.
    """


@dataclass(frozen=True, slots=True)
class ShipOccurrence:
    """One Record path paired with the concrete Ship instance found there."""

    path: str
    ship: Ship

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path:
            raise ShipIdentityError("Ship.Occurrence path must be a non-empty string")
        if not isinstance(self.ship, Ship):
            raise ShipIdentityError("Ship.Occurrence ship must be a Ship instance")
