from tarav.runtime import create_runtime


def test_registered_runtime_objects_round_trip_their_json_examples() -> None:
    registry = create_runtime().records

    for object_type in registry.record_types:
        example = object_type.json_example()
        first = registry.from_json(example)
        encoded = first.to_json()
        assert encoded == example, object_type.__name__
        second = registry.from_json(encoded)

        assert type(first) is object_type, object_type.__name__
        assert type(second) is object_type, object_type.__name__
        assert second.to_json() == encoded, object_type.__name__
