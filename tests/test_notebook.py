from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship
from tarav.l1.lines import Block, Line
# tarav.breadcrumb cc9b00e6c4cc
from tarav.l1.notebook import Notebook
from tarav.l3.runtime import create_runtime


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
