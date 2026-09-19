from __future__ import annotations

from dataclasses import dataclass

from tarav.harness import Ship, TaravObject, TypeShip

TYPE_SHIP = "a1c4e6b8-2d3f-4051-9273-84a6b5c7d8e9"
CARGO = "b2d5f7c9-3e40-4162-8384-95b7c6d8e9f0"
UNRELATED = "c3e6a8da-4f51-4273-9495-a6c8d7e9f0a1"


class PlainRecord(TaravObject):
    type_ship = TypeShip(TYPE_SHIP)
    type_name = "Plain.Record"


@dataclass(frozen=True, slots=True)
class CarryingRecord(TaravObject):
    type_ship = TypeShip(TYPE_SHIP)
    type_name = "Carrying.Record"

    record: dict[str, object]

    def ships(self) -> tuple[Ship, ...]:
        subject = self.record.get("subject_ship")
        return (
            *super(CarryingRecord, self).ships(),
            *((Ship(str(subject)),) if isinstance(subject, str) else ()),
        )


def test_the_default_projection_exposes_only_the_record_type_ship() -> None:
    assert PlainRecord({}).ships() == (TypeShip(TYPE_SHIP),)


def test_a_subclass_extends_the_projection_with_ships_it_recognizes() -> None:
    carried = CarryingRecord({"subject_ship": CARGO, "note": UNRELATED})

    assert carried.ships() == (TypeShip(TYPE_SHIP), Ship(CARGO))


def test_uuid_shaped_data_is_never_promoted_to_a_ship() -> None:
    assert CarryingRecord({"note": UNRELATED}).ships() == (TypeShip(TYPE_SHIP),)


def test_the_projection_exposes_no_serialized_paths() -> None:
    ships = CarryingRecord({"subject_ship": CARGO}).ships()

    assert all(isinstance(item, Ship) for item in ships)
    assert not any(hasattr(item, "path") for item in ships)
