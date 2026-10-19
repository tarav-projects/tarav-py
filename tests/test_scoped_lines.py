import json
from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship, TaravClass, TypeShip
from tarav.l1.context import ContextExplorer
from tarav.l1.lines import Block, Line


def make_line():
    scope = Block(id=Ship(str(uuid4())), topic="The car")
    return Line(id=Ship(str(uuid4())), text="It is red.", scope=scope)


def test_block_topic_order_and_binding():
    block = Block(id=Ship(str(uuid4())), topic="The car")
    color = Line(id=Ship(str(uuid4())), text="It is red.", scope=block)
    finish = Line(id=Ship(str(uuid4())), text="The finish is matte.", scope=block)
    block.append(color)
    block.append(finish)

    assert block.lines == (color, finish)
    assert block.line_ships == (color.id, finish.id)
    assert finish.scope is block
    assert block.ships()[-2:] == block.line_ships

    restored = Block.records.from_record(block.records.to_record())
    assert restored.records.to_record() == block.records.to_record()
    with pytest.raises(LookupError):
        _ = restored.lines
    with pytest.raises(ValueError):
        restored.bind_lines((finish, color))
    restored.bind_lines((color, finish))
    assert restored.lines == block.lines


def test_block_rejects_invalid_membership():
    block = Block(id=Ship(str(uuid4())), topic="A topic")
    line = Line(id=Ship(str(uuid4())), text="A detail.", scope=block)
    with pytest.raises(ValueError):
        Block(id=Ship(str(uuid4())), topic=" ")
    with pytest.raises(TypeError):
        block.append("not a Line")
    with pytest.raises(ValueError):
        block.bind_lines((line,))
    block.append(line)
    with pytest.raises(ValueError):
        block.append(line)
    with pytest.raises(ValueError):
        block.append(make_line())


def test_line_roundtrip_and_binding():
    line = make_line()
    restored = Line.records.from_record(line.records.to_record())
    assert restored.records.to_record() == line.records.to_record()
    with pytest.raises(LookupError):
        _ = restored.scope
    with pytest.raises(ValueError):
        restored.bind_scope(Block(id=Ship(str(uuid4())), topic="Other"))
    restored.bind_scope(line.scope)
    assert restored.scope is line.scope
    identity = restored.id
    restored.text = "It is blue."
    assert restored.id == identity
    assert restored.scope is line.scope


def test_recursive_block_context():
    root = Block(id=Ship(str(uuid4())), topic="Project")
    child = Block(id=Ship(str(uuid4())), topic="Class", parent=root)
    leaf = Block(id=Ship(str(uuid4())), topic="Method", parent=child)
    root.append_child(child)
    child.append_child(leaf)
    line = Line(id=Ship(str(uuid4())), text="It returns a result.", scope=leaf)
    leaf.append(line)
    assert line.scope is leaf
    assert leaf.ancestors() == (child, root)
    assert root.children == (child,)
    assert child.child_ships == (leaf.id,)
    assert Block.records.from_record(leaf.records.to_record()).parent_ship == child.id
    restored = Block.records.from_record(root.records.to_record())
    with pytest.raises(LookupError):
        _ = restored.children
    restored.bind_children((child,))
    assert restored.children == (child,)


def test_scope_must_be_a_block():
    block = Block(id=Ship(str(uuid4())), topic="Topic")
    line = Line(id=Ship(str(uuid4())), text="A statement.", scope=block)
    with pytest.raises(TypeError):
        Line(id=Ship(str(uuid4())), text="x", scope="not an entity")
    with pytest.raises(TypeError):
        Line(id=Ship(str(uuid4())), text="x", scope=line)


def test_block_parent_cycles_and_conflicts_are_rejected():
    root = Block(id=Ship(str(uuid4())), topic="Root")
    child = Block(id=Ship(str(uuid4())), topic="Child", parent=root)
    with pytest.raises(ValueError):
        root.bind_parent(child)
    with pytest.raises(ValueError):
        root.append_child(Block(id=Ship(str(uuid4())), topic="Other"))
    with pytest.raises(ValueError):
        child.append_child(root)
    root.append_child(child)
    with pytest.raises(ValueError):
        root.append_child(child)


def test_loaded_parent_can_bind_before_its_own_parent():
    root = Block(id=Ship(str(uuid4())), topic="Root")
    middle = Block(id=Ship(str(uuid4())), topic="Middle", parent=root)
    leaf = Block(id=Ship(str(uuid4())), topic="Leaf", parent=middle)
    restored_middle = Block.records.from_record(middle.records.to_record())
    restored_leaf = Block.records.from_record(leaf.records.to_record())
    restored_leaf.bind_parent(restored_middle)
    with pytest.raises(LookupError):
        restored_leaf.ancestors()
    restored_middle.bind_parent(root)
    assert restored_leaf.ancestors() == (restored_middle, root)


def test_block_subclass_is_a_distinct_type():
    class SpecBlock(Block):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip(str(uuid4())),
                              name="Test.SpecBlock")

    block = SpecBlock(id=Ship(str(uuid4())), topic="Current design")
    assert block.records.to_record()["type"] == "Test.SpecBlock"


def test_line_import_has_no_model_dependency():
    import subprocess
    import sys

    result = subprocess.run([sys.executable, '-c',
        'import sys; import tarav.l1.lines; '
        'assert not any(n.startswith(("tarav.l2.models", "tarav.l2.unsorted", '
        '"tarav.l3")) for n in sys.modules)'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_object_context_entry_point():
    from tarav.l3.runtime import get_runtime

    line = make_line()
    assert isinstance(line.context(), ContextExplorer)
    assert line.context().focus is line
    assert get_runtime().records is not None


def test_models_fail_before_side_effects(tmp_path):
    from tarav.l2.models.model import Model
    from tarav.l2.models.errors import ToImplementError
    from tarav.l2.project import Project
    from tarav.l2.unsorted.storage import DiagramNamespace

    root = tmp_path / "project"
    (root / ".tarav").mkdir(parents=True)
    (root / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": str(uuid4()),
        "created_at": "2026-10-16T00:00:00Z",
        "harness": {"environment": "env", "type": "tarav.l2.project:Project"}}))
    (root / ".tarav/config.json").write_text("{}")
    written = sorted(tmp_path.rglob("*"))

    with pytest.raises(ToImplementError):
        Model("anything", None, "edition")
    # A Project exposes its Models and lists their names without storage;
    # only resolving a Model fails.
    models = Project.from_path(root).models
    assert models.ls() == ()
    with pytest.raises(ToImplementError):
        models.main()
    namespace = object.__new__(DiagramNamespace)
    with pytest.raises(ToImplementError):
        namespace.create_model()
    assert sorted(tmp_path.rglob("*")) == written


@pytest.mark.parametrize('method,args,kwargs', [
    ('model', ('not-a-ship',), {}),
    ('models', (), {}),
    ('project_model', (None,), {}),
    ('ensure_project_model', (None,), {}),
])
def test_model_resolution_is_disabled_before_io(method, args, kwargs):
    from tarav.l2.models.errors import ToImplementError
    from tarav.l2.unsorted.storage import Diagram

    diagram = object.__new__(Diagram)
    with pytest.raises(ToImplementError):
        getattr(diagram, method)(*args, **kwargs)
