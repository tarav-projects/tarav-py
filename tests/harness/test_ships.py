from __future__ import annotations

from uuid import UUID

import pytest

from tarav.harness import Ship, ShipIdentityError, TypeShip

EXAMPLE = "3f7f6f7c-8d5c-4f1a-9c4e-1c0d3b2a5e6f"
OTHER = "9a1d2c3b-4e5f-4a6b-8c7d-0e1f2a3b4c5d"


def test_ship_accepts_uuid_objects_and_strings_and_rejects_other_values() -> None:
    assert Ship(UUID(EXAMPLE)).uuid == UUID(EXAMPLE)
    assert Ship(EXAMPLE).uuid == UUID(EXAMPLE)

    with pytest.raises(ShipIdentityError):
        Ship("not-a-uuid")
    with pytest.raises(ShipIdentityError):
        Ship(7)  # type: ignore[arg-type]


def test_ship_identity_is_uuid_only_across_specialized_classes() -> None:
    class RoleShip(Ship):
        def role(self) -> str:
            return "role"

    generic = Ship(EXAMPLE)
    typed = TypeShip(EXAMPLE)
    specialized = RoleShip(EXAMPLE)

    assert generic == typed == specialized
    assert len({generic, typed, specialized}) == 1
    assert specialized.role() == "role"
    assert generic != Ship(OTHER)
    assert generic != EXAMPLE
