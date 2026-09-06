from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from tarav.diagram import (
    LINE_SHIP_TYPE,
    MODEL_SHIP_TYPE,
    CaptureManifest,
    DiagramModelError,
    DiagramNamespace,
    DiagramShipSpecializationError,
    LineShipRecord,
    ModelShipRecord,
    ShipDraft,
    default_diagram_annotation_type_registry,
    default_diagram_ship_type_registry,
)
from tarav.harness import RecordTypeReference, Ship, ShipOccurrence, TypeShip

REF = {
    "session_identity": "a" * 64,
    "turn_address": "b" * 64,
    "turn_hash": "c" * 64,
}


def _line_record(model_ship: str, block_ship: str, type_value: object) -> ShipDraft:
    return ShipDraft(
        str(uuid4()),
        {
            "type": type_value,
            "model_ship": model_ship,
            "block_ship": block_ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "producer": REF,
                    "support": [{"root": REF, "neighborhood": []}],
                    "data": {"text": "A Ship UUID is semantically void."},
                }
            ],
        },
    )


def test_every_diagram_record_type_declares_a_unique_type_ship() -> None:
    registries = (
        default_diagram_ship_type_registry(),
        default_diagram_annotation_type_registry(include_chatlas_index_types=True),
    )
    record_types = tuple(item for registry in registries for item in registry.types())
    ships = [item.type_ship for item in record_types]

    assert all(isinstance(ship, TypeShip) for ship in ships)
    assert len(set(ships)) == len(ships)


def test_structured_and_legacy_type_references_read_the_same_record(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    legacy = _line_record(model.ship, block_ship, LINE_SHIP_TYPE)
    structured = _line_record(
        model.ship,
        block_ship,
        {"id": str(LineShipRecord.type_ship.uuid), "name": LINE_SHIP_TYPE},
    )
    namespace.apply(CaptureManifest(model.ship, (legacy, structured)))

    for ship_id in (legacy.id, structured.id):
        ship = namespace.ship(ship_id)
        assert ship.type == LINE_SHIP_TYPE
        assert isinstance(ship.specialize(), LineShipRecord)


def test_a_known_type_ship_survives_label_drift(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    drifted = _line_record(
        model.ship,
        str(uuid4()),
        {"id": str(LineShipRecord.type_ship.uuid), "name": "Diagram.Line.Vessel"},
    )
    namespace.apply(CaptureManifest(model.ship, (drifted,)))

    ship = namespace.ship(drifted.id)
    assert ship.type == "Diagram.Line.Vessel"
    assert isinstance(ship.specialize(), LineShipRecord)
    assert (
        default_diagram_ship_type_registry()
        .reference_findings(ship.type_reference)[0]
        .code
        == "record-type-name-conflict"
    )


def test_an_unknown_type_ship_is_recoverable_rather_than_silently_rebound(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    unknown = _line_record(
        model.ship, str(uuid4()), {"id": str(uuid4()), "name": LINE_SHIP_TYPE}
    )
    namespace.apply(CaptureManifest(model.ship, (unknown,)))

    ship = namespace.ship(unknown.id)
    assert ship.type == LINE_SHIP_TYPE
    with pytest.raises(DiagramShipSpecializationError):
        ship.specialize()


def test_a_type_reference_without_a_usable_component_is_rejected(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")

    with pytest.raises(DiagramModelError):
        namespace.apply(
            CaptureManifest(
                model.ship, (_line_record(model.ship, str(uuid4()), {"name": ""}),)
            )
        )


def test_typed_records_expose_their_structural_ship_occurrences(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    line = _line_record(model.ship, block_ship, LINE_SHIP_TYPE)
    namespace.apply(CaptureManifest(model.ship, (line,)))

    assert namespace.ship(model.ship).specialize().ship_occurrences() == (
        ShipOccurrence("type.id", ModelShipRecord.type_ship),
        ShipOccurrence("id", Ship(model.ship)),
    )
    assert namespace.ship(line.id).specialize().ship_occurrences() == (
        ShipOccurrence("type.id", LineShipRecord.type_ship),
        ShipOccurrence("id", Ship(line.id)),
        ShipOccurrence("model_ship", Ship(model.ship)),
        ShipOccurrence("block_ship", Ship(block_ship)),
    )
    edition = namespace.edition(str(line.record["editions"][0]["id"])).specialize()
    assert edition.ship_occurrences()[1:] == (
        ShipOccurrence("location.model_ship", Ship(model.ship)),
        ShipOccurrence("location.block_ship", Ship(block_ship)),
        ShipOccurrence("location.line_ship", Ship(line.id)),
    )


def test_model_ship_type_reference_reads_as_a_parsed_reference(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")

    assert namespace.ship(model.ship).type_reference == RecordTypeReference(
        None, MODEL_SHIP_TYPE
    )
