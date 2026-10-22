"""Shared formats remain valid through Python and Record boundaries."""
# tarav.breadcrumb d945874539c1

import json
import re

import pytest
from pydantic import TypeAdapter, ValidationError

from tarav.l0.label_formats import DottedFormat, Label
from tarav.l0.kernel import TaravClass, TaravObject, TypeShip


@pytest.mark.parametrize("text", ["Kernel.Writing", "HTTP.API", "Model2.Design",
                                  "", "/", "/properties/text", "/a~1b/~0", "/日本語/0"])
def test_label_accepts_supported_formats_without_rewriting(text):
    label = Label(text)
    assert isinstance(label, str)
    assert str(label) == text
    adapter = TypeAdapter(Label)
    assert adapter.dump_json(label) == json.dumps(text, ensure_ascii=False).encode()
    assert type(adapter.validate_json(adapter.dump_json(label))) is Label


@pytest.mark.parametrize("text", ["Kernel", "ordinary prose", "kernel.Writing",
                                  "Kernel..Writing", "Kernel/Writing", "/bad~2", "/bad~"])
def test_label_rejects_invalid_python_and_json(text):
    with pytest.raises(ValueError):
        Label(text)
    with pytest.raises(ValidationError):
        TypeAdapter(Label).validate_json(json.dumps(text))


def test_specialized_label_restricts_formats_at_all_boundaries():
    class DottedLabel(Label):
        formats = (DottedFormat,)
    assert DottedLabel("Kernel.Writing") == "Kernel.Writing"
    with pytest.raises(ValueError):
        DottedLabel("/properties/text")
    with pytest.raises(ValidationError):
        TypeAdapter(DottedLabel).validate_python(Label("/properties/text"))
    assert len(TypeAdapter(DottedLabel).json_schema()["anyOf"]) == 1
    with pytest.raises(TypeError):
        Label(12)


def test_schema_describes_both_formats_and_root_pointer():
    choices = TypeAdapter(Label).json_schema()["anyOf"]
    def matches(text):
        return any(re.search(choice["pattern"], text) for choice in choices)
    assert matches("Kernel.Writing")
    assert matches("/properties/text")
    assert matches("")
    assert not matches("Kernel.Writing\n")
    assert not matches("/bad~2")
    assert not matches("ordinary prose")


def test_type_labels_share_validation_in_construction_and_records():
    identity = TypeShip("4e694a27-9991-4323-a50b-221b83cd364b")
    for name in ("Example.Type", "/properties/type"):
        cls = TaravClass(target=TaravObject, id=identity, name=name)
        assert isinstance(cls.name, Label)
        record = cls.records.to_record()
        restored = TaravClass.records.from_record(record)
        assert isinstance(restored.name, Label)
        assert restored.name == name
    with pytest.raises(ValueError):
        TaravClass(target=TaravObject, id=identity, name="ordinary prose")
    with pytest.raises(ValidationError):
        TaravClass.records.from_record({**record, "name": "ordinary prose"})
    with pytest.raises(ValidationError):
        TaravClass.records.from_record({**record, "name": ""})
