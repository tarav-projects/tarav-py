import json
from pathlib import Path
from typing import Literal, Self

import pytest
from pydantic import BaseModel, ValidationError

from tarav.l0.kernel import (
    FileRecord,
    LoadedRecord,
    RecordLoadingConfig,
    TaravClass,
    TaravObject,
    TypeRegistry,
    TypeShip,
    entity,
)


class Point(BaseModel):
    x: int
    y: int


class Shape(TaravObject):
    """A Type whose builder sees only what the loading workflow gives it."""

    seen: list[LoadedRecord] = []

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0b7d5f62-2a43-4c1e-9b8f-5d6e7a8c9b01"),
                          name="Test.Loading.Shape")

    class RecordInterface(TaravObject.RecordInterface):
        type: Literal["Test.Loading.Shape"]
        origin: Point

    def __init__(self, origin: Point) -> None:
        super().__init__()
        self.origin = origin

    @classmethod
    def _from_record(cls, loaded: LoadedRecord) -> Self:
        cls.seen.append(loaded)
        return cls(loaded.data.origin)

    def _to_record(self) -> dict[str, object]:
        return {"type": entity(type(self)).name, "origin": self.origin.model_dump()}


class Stored(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6c1e8a3d-4f2b-4d7a-a9c0-3e5b8f1d2c47"),
                          name="Test.Loading.Stored")

    class RecordInterface(FileRecord.RecordInterface):
        type: Literal["Test.Loading.Stored"]


@pytest.fixture
def registry() -> TypeRegistry:
    Shape.seen.clear()
    return TypeRegistry(TaravObject, (Shape, Stored))


def _write(tmp_path: Path, record: dict) -> Path:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_a_builder_receives_the_parsed_data_and_the_loading_metadata(
    registry: TypeRegistry, tmp_path: Path
) -> None:
    path = _write(tmp_path, {"type": "Test.Loading.Shape", "origin": {"x": 1, "y": 2}})

    shape = registry.load(path)

    (loaded,) = Shape.seen
    assert isinstance(loaded.data, Shape.RecordInterface)
    assert shape.origin is loaded.data.origin
    assert loaded.metadata.source == path
    assert shape.source is None
    assert not hasattr(shape, "loaded")


def test_only_types_that_keep_their_source_get_it(registry: TypeRegistry, tmp_path: Path) -> None:
    path = _write(tmp_path, {"type": "Test.Loading.Stored"})

    assert registry.load(path).source == path
    no_source = RecordLoadingConfig(source=False)
    assert registry.load(path, config=no_source).source is None


def test_the_internal_path_returns_how_far_a_failed_load_got(
    registry: TypeRegistry, tmp_path: Path
) -> None:
    path = _write(tmp_path, {"type": "Test.Loading.Shape", "origin": {"x": "one", "y": 2}})

    context = registry.load_context(path)

    assert context.stage == "parse"
    assert context.record_type is Shape
    assert context.record == {"type": "Test.Loading.Shape", "origin": {"x": "one", "y": 2}}
    assert isinstance(context.error, ValidationError)
    assert context.instance is None and Shape.seen == []


def test_the_public_path_raises_the_original_error_with_where_it_stopped(
    registry: TypeRegistry, tmp_path: Path
) -> None:
    path = _write(tmp_path, {"type": "Test.Loading.Shape", "origin": {"x": "one", "y": 2}})

    with pytest.raises(ValidationError) as caught:
        registry.load(path)

    assert f"Record loading stopped at 'parse' for {path}" in caught.value.__notes__
    with pytest.raises(ValidationError):
        Shape.records.from_record({"type": "Test.Loading.Shape", "origin": {}})
