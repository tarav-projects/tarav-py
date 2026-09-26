from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from tarav.kernel import Ship, ShipIdentityError, TypeShip

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


def test_pydantic_parses_and_serializes_the_declared_ship_class() -> None:
    class ShipFields(BaseModel):
        model_config = ConfigDict(strict=True)

        ship: Ship
        type_ship: TypeShip

    fields = ShipFields.model_validate(
        {"ship": EXAMPLE, "type_ship": OTHER},
        strict=True,
    )

    assert type(fields.ship) is Ship
    assert type(fields.type_ship) is TypeShip
    assert fields.model_dump() == {
        "ship": Ship(EXAMPLE),
        "type_ship": TypeShip(OTHER),
    }
    assert fields.model_dump(mode="json") == {
        "ship": EXAMPLE,
        "type_ship": OTHER,
    }
    assert ShipFields.model_json_schema()["properties"]["ship"]["type"] == "string"


def test_pydantic_ship_fields_reject_malformed_and_wrong_specializations() -> None:
    class TypeShipField(BaseModel):
        model_config = ConfigDict(strict=True)

        ship: TypeShip

    with pytest.raises(ValidationError):
        TypeShipField.model_validate({"ship": "not-a-uuid"}, strict=True)
    with pytest.raises(ValidationError):
        TypeShipField.model_validate({"ship": Ship(EXAMPLE)}, strict=True)
