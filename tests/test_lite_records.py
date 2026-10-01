from dataclasses import dataclass
from datetime import date, datetime, timezone

import pytest

from tarav.l0.kernel import (
    LiteRecord,
    LiteRecordSerializer,
    Ship,
    TaravObject,
)


@dataclass
class Coordinate:
    x: int
    y: int


def test_lite_record_canonical_value_contract():
    source = {
        "nested": {"b": 2, "a": [1, "one"]},
        "date": date(2026, 10, 1),
        "datetime": datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc),
        "ship": Ship("e5ff87ed-c382-49c8-855e-e04191dcf4c8"),
        "type": TaravObject,
        "$tarav.lite": "ordinary caller data",
        "coordinate": Coordinate(2, 3),
    }
    serializer = LiteRecordSerializer(
        "example.coordinate",
        Coordinate,
        lambda value: {"x": value.x, "y": value.y},
    )
    first = LiteRecord(source, serializers=(serializer,))
    second = LiteRecord(
        {key: source[key] for key in reversed(source)}, serializers=(serializer,)
    )

    source["nested"]["a"].append("later mutation")
    assert first.canonical == second.canonical
    assert LiteRecord.from_json_value(first.to_json_value()).canonical == first.canonical
    assert "later mutation" not in first.canonical
    assert LiteRecord({"value": [1, 2]}).canonical != LiteRecord(
        {"value": [2, 1]}
    ).canonical
    assert LiteRecord({"value": Ship("e5ff87ed-c382-49c8-855e-e04191dcf4c8")}).canonical != LiteRecord(
        {"value": "e5ff87ed-c382-49c8-855e-e04191dcf4c8"}
    ).canonical


def test_lite_record_rejects_values_without_declared_encoding():
    for value in ({"value": object()}, {"value": float("nan")}, {1: "value"}):
        with pytest.raises((TypeError, ValueError)):
            LiteRecord(value)

    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="cycles"):
        LiteRecord({"value": cycle})
