import json
from pathlib import Path

from tarav.harness import FileRecord, TypeShip
from tarav.harness import types


class ExampleRecord(FileRecord):
    type_name = "Test.Help"
    type_ship = TypeShip("3c49ad52-6308-477a-a08e-5f2c0f4539e0")


def test_help_finds_concrete_class_from_class_and_instance(capsys):
    info = ExampleRecord.help()
    assert info == ExampleRecord({}).help()
    assert info["class"] == f"{__name__}.ExampleRecord"
    assert info["source_path"] == str(Path(__file__).resolve())
    line = Path(info["source_path"]).read_text().splitlines()[info["source_line"] - 1]
    assert line == "class ExampleRecord(FileRecord):"
    assert info["hints"] == {}
    assert "unavailable" not in info
    json.dumps(info)
    assert capsys.readouterr().out == ""


def test_help_reports_missing_source(monkeypatch):
    monkeypatch.setattr(types.inspect, "getsourcefile", lambda cls: None)
    info = ExampleRecord.help()
    assert info["source_path"] is None
    assert info["source_line"] is None
    assert set(info["hints"]["unavailable"]) == {"source_path", "source_line"}


def test_help_keeps_path_when_line_unavailable(monkeypatch):
    def unavailable(cls):
        raise OSError("Class definition unavailable")

    monkeypatch.setattr(types.inspect, "getsourcelines", unavailable)
    info = ExampleRecord.help()
    assert info["source_path"] == str(Path(__file__).resolve())
    assert info["source_line"] is None
    assert info["hints"]["unavailable"] == {"source_line": "Class definition unavailable"}


def test_class_can_extend_default_help():
    class Extended(ExampleRecord):
        type_ship = TypeShip("6da586d9-e48b-4d73-a489-8ea6fe67a991")

        @classmethod
        def help(cls):
            return {**super().help(), "documentation": ["docs/example.md"]}

    assert Extended({}).help()["documentation"] == ["docs/example.md"]
