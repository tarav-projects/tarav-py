from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship
from tarav.l1.lines import Block, LabelLine, Line
# tarav.breadcrumb 0cd3554e126a
# tarav.breadcrumb cc9b00e6c4cc
from tarav.l1.notebook import Notebook
from tarav.l3.runtime import create_runtime


def test_block_title_persists_as_a_line_and_validates_edits(tmp_path):
    notebook = Notebook(tmp_path / "notebook", records=create_runtime().records).create()
    block = Block(id=Ship(uuid4()))
    title = LabelLine(id=Ship(uuid4()), text="Kernel.Writing", scope=block)
    block.append(title)
    notebook.save_tree(block)

    loaded = notebook.load(block.id)
    restored = loaded.contents[0]
    assert isinstance(restored, LabelLine)
    assert isinstance(restored, Line)
    assert restored.scope is loaded
    assert restored.id == title.id
    restored.text = "Semantic.Independence.And.Integration"
    notebook.save(restored)
    assert notebook.load(title.id).text == restored.text
    with pytest.raises(ValueError):
        restored.text = "An ordinary sentence"
    assert restored.text == "Semantic.Independence.And.Integration"


@pytest.mark.parametrize("text", ["Kernel.Writing", "HTTP.API", "Model2.Design",
                                  "", "/properties/text", "/a~1b/~0", "/"])
def test_block_title_accepts_dotted_labels(text):
    title = LabelLine(id=Ship(uuid4()), text=text, scope=Block(id=Ship(uuid4())))
    assert title.text == text
    assert LabelLine.records.from_record(title.records.to_record()).text == text


@pytest.mark.parametrize("text", [
    "Kernel", "Kernel Writing", "kernel.Writing", "Kernel.writing",
    ".Kernel.Writing", "Kernel.Writing.", "Kernel..Writing", "Kernel/Writing",
    "Kernel::Writing", " Kernel.Writing", "Kernel.Writing\n",
])
def test_block_title_rejects_invalid_construction_and_records(text):
    from pydantic import ValidationError

    block = Block(id=Ship(uuid4()))
    with pytest.raises(ValueError):
        LabelLine(id=Ship(uuid4()), text=text, scope=block)
    title = LabelLine(id=Ship(uuid4()), text="Kernel.Writing", scope=block)
    record = {**title.records.to_record(), "text": text}
    with pytest.raises((ValueError, ValidationError)):
        LabelLine.records.from_record(record)


def test_selection_and_missing_load_do_not_create_storage(tmp_path):
    runtime = create_runtime()
    notebook = Notebook(tmp_path / "notebook", records=runtime.records)
    assert notebook.ids() == ()
    with pytest.raises(FileNotFoundError):
        notebook.load(Ship(uuid4()))
    assert not notebook.root.exists()


def test_nested_records_reload_with_one_identity_and_mixed_order(tmp_path):
    notebook = Notebook(tmp_path / "notebook", records=create_runtime().records).create()
    root = Block(id=Ship(uuid4()))
    first = Line(id=Ship(uuid4()), text="This concerns the car.", scope=root)
    child = Block(id=Ship(uuid4()), parent=root)
    detail = Line(id=Ship(uuid4()), text="It is red.", scope=child)
    child.append(detail)
    last = Line(id=Ship(uuid4()), text="Its finish is matte.", scope=root)
    for item in (first, child, last):
        root.append(item)
    notebook.save_tree(root)
    notebook.commit("Capture the car")

    reopened = Notebook(notebook.root, records=create_runtime().records)
    loaded = reopened.load(root.id)
    assert loaded.content_ships == (first.id, child.id, last.id)
    assert loaded.contents[1].parent is loaded
    assert loaded.contents[1].contents[0].scope is loaded.contents[1]
    assert reopened.load(detail.id).scope.ancestors()[0].id == root.id
    assert set(reopened.ids()) == {root.id, first.id, child.id, detail.id, last.id}
    restored = reopened.load(detail.id)
    restored.text = "It is blue."
    reopened.save(restored)
    assert reopened.load(detail.id).text == "It is blue."
    assert reopened.load(detail.id).id == detail.id


def test_missing_and_rebound_records_are_not_silently_repaired(tmp_path):
    notebook = Notebook(tmp_path / "notebook", records=create_runtime().records).create()
    root = Block(id=Ship(uuid4()))
    line = Line(id=Ship(uuid4()), text="A thought.", scope=root)
    root.append(line)
    notebook.save(root)
    with pytest.raises(FileNotFoundError):
        notebook.load(root.id)
    notebook.save(line)
    with pytest.raises(ValueError):
        notebook.save(Block(id=line.id))
    assert notebook.load(line.id).text == "A thought."
