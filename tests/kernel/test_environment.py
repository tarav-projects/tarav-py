from __future__ import annotations

import importlib
import json
import sys

import pytest

from tarav.l0.kernel import (
    TaravEnvironment,
    TaravObject,
    TypeRegistry,
    TypeRegistrationError,
    UnknownRecordType,
)
from tarav.l3.runtime import create_runtime


def test_runtime_lazily_loads_an_external_class_from_its_environment(
    tmp_path, monkeypatch
) -> None:
    package = tmp_path / "external_example"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "records.py").write_text(
        "from tarav.l0.kernel import TaravClass, TaravEntity, TypeShip\n"
        "class ExternalNote(TaravEntity):\n"
        "    @classmethod\n"
        "    def class_entity(cls):\n"
        "        return TaravClass(target=cls, "
        "id=TypeShip('499d13aa-07d2-439b-ad37-332eaa102ea0'), "
        "name='External.Note')\n"
        "class ReplacementNote(TaravEntity):\n"
        "    @classmethod\n"
        "    def class_entity(cls):\n"
        "        return TaravClass(target=cls, "
        "id=TypeShip('10f4d0d0-5155-48e3-b2c4-c1352a78c427'), "
        "name='External.Note')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "external_example.records", raising=False)
    monkeypatch.delitem(sys.modules, "external_example", raising=False)
    path = tmp_path / "note.json"
    path.write_text(
        json.dumps(
            {
                "type": {
                    "uuid": "499d13aa-07d2-439b-ad37-332eaa102ea0",
                    "label": "External.Note",
                },
                "id": "f78d603b-02d5-41a1-a43a-2af6a998842a",
            }
        )
    )
    environment = TaravEnvironment()
    runtime = create_runtime(environment=environment)

    with pytest.raises(UnknownRecordType):
        runtime.load_object(path)
    assert "external_example.records" not in sys.modules

    environment.bind_type("External.Note", "external_example.records:ExternalNote")
    assert "external_example.records" not in sys.modules
    loaded = runtime.load_object(path)
    assert type(loaded).__name__ == "ExternalNote"
    assert loaded.source == path
    assert "external_example.records" in sys.modules
    assert type(loaded) in runtime.records.record_types
    assert registry_findings(runtime, path) == ()

    replacement = importlib.import_module("external_example.records").ReplacementNote
    environment.bind_type("External.Note", replacement)
    assert registry_findings(runtime, path)[0].code == "record-type-ship-unknown"
    with pytest.raises(UnknownRecordType):
        runtime.load_object(path)
    path.write_text(
        json.dumps(
            {
                "type": {
                    "uuid": "10f4d0d0-5155-48e3-b2c4-c1352a78c427",
                    "label": "External.Note",
                },
                "id": "f78d603b-02d5-41a1-a43a-2af6a998842a",
            }
        )
    )
    assert type(runtime.load_object(path)) is replacement
    environment.unbind_type("External.Note")
    with pytest.raises(UnknownRecordType):
        runtime.load_object(path)


def registry_findings(runtime, path):
    return runtime.records.record_findings(json.loads(path.read_text()))


def test_external_paths_are_explicit_and_checked_before_dispatch() -> None:
    environment = TaravEnvironment()
    registry = TypeRegistry(TaravObject, environment=environment)

    with pytest.raises(UnknownRecordType):
        registry.from_record({"type": "os:path"})
    with pytest.raises(ValueError, match="package.module:Class"):
        environment.bind_type("External.Note", "os.path")
    environment.bind_type("External.Note", "os:path")
    with pytest.raises(TypeRegistrationError, match="not a TaravObject"):
        registry.from_record({"type": "External.Note"})


def test_environment_is_a_runtime_object_with_a_record_projection() -> None:
    environment = TaravEnvironment()
    runtime = create_runtime(environment=environment)

    assert runtime.environment is environment
    assert environment.records.to_record() == {"type": "Tarav.Environment"}
    assert environment.executable.is_file()
    assert runtime.records.from_record(environment.records.to_record()).records.to_record() == (
        environment.records.to_record()
    )
