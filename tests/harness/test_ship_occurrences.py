from __future__ import annotations

from dataclasses import dataclass

from tarav.harness import Ship, ShipOccurrence, TaravRecordType, TypeShip

TYPE_SHIP = "a1c4e6b8-2d3f-4051-9273-84a6b5c7d8e9"
CARGO = "b2d5f7c9-3e40-4162-8384-95b7c6d8e9f0"
UNRELATED = "c3e6a8da-4f51-4273-9495-a6c8d7e9f0a1"


class PlainRecord(TaravRecordType):
    type_ship = TypeShip(TYPE_SHIP)
    type_name = "Plain.Record"


@dataclass(frozen=True, slots=True)
class CarryingRecord(TaravRecordType):
    type_ship = TypeShip(TYPE_SHIP)
    type_name = "Carrying.Record"

    record: dict[str, object]

    def ship_occurrences(self) -> tuple[ShipOccurrence, ...]:
        cargo = self.record.get("subject_ship")
        return (
            *super(CarryingRecord, self).ship_occurrences(),
            *(
                (ShipOccurrence("subject_ship", Ship(str(cargo))),)
                if isinstance(cargo, str)
                else ()
            ),
        )


def test_the_default_surface_exposes_only_the_record_type_ship() -> None:
    assert PlainRecord().ship_occurrences() == (
        ShipOccurrence("type.id", TypeShip(TYPE_SHIP)),
    )


def test_an_application_class_opts_into_its_cargo_ships() -> None:
    carried = CarryingRecord({"subject_ship": CARGO, "note": UNRELATED})

    assert carried.ship_occurrences() == (
        ShipOccurrence("type.id", TypeShip(TYPE_SHIP)),
        ShipOccurrence("subject_ship", Ship(CARGO)),
    )


def test_uuid_shaped_data_is_never_promoted_to_a_ship() -> None:
    assert CarryingRecord({"note": UNRELATED}).ship_occurrences() == (
        ShipOccurrence("type.id", TypeShip(TYPE_SHIP)),
    )
