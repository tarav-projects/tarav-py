from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship, TaravClass, TypeShip
from tarav.l1.context import ContextExplorer
from tarav.l1.lines import Block, Line


def make_line():
    scope = Block(id=Ship(str(uuid4())))
    return Line(id=Ship(str(uuid4())), text="It is red.", scope=scope)


# tarav.breadcrumb 46d4a791578f
def test_mixed_block_order_and_binding():
    block = Block(id=Ship(str(uuid4())))
    color = Line(id=Ship(str(uuid4())), text="It is red.", scope=block)
    child = Block(id=Ship(str(uuid4())), parent=block)
    finish = Line(id=Ship(str(uuid4())), text="The finish is matte.", scope=block)
    block.append(color)
    block.append(child)
    block.append(finish)

    assert block.contents == (color, child, finish)
    assert block.content_ships == (color.id, child.id, finish.id)
    assert tuple(item for item in block.contents if isinstance(item, Line)) == (color, finish)
    assert tuple(item for item in block.contents if isinstance(item, Block)) == (child,)
    assert finish.scope is block
    assert block.ships()[-3:] == block.content_ships
    assert Block(id=block.id, contents=(color, child, finish)).contents == block.contents

    restored = Block.records.from_record(block.records.to_record())
    assert restored.records.to_record() == block.records.to_record()
    with pytest.raises(LookupError):
        _ = restored.contents
    with pytest.raises(ValueError):
        restored.bind_contents((color, finish, child))
    restored.bind_contents((color, child, finish))
    assert restored.contents == block.contents


# tarav.breadcrumb c83d9674f181
def test_block_meaning_can_be_expressed_as_a_line():
    block = Block(id=Ship(str(uuid4())))
    assert block.contents == ()
    topic = Line(id=Ship(str(uuid4())), text="This Block describes the car.", scope=block)
    block.append(topic)
    assert topic.scope is block
    assert block.records.to_record()["content_ships"] == [str(topic.id)]
    assert "topic" not in block.records.to_record()


def test_block_rejects_invalid_membership():
    block = Block(id=Ship(str(uuid4())))
    line = Line(id=Ship(str(uuid4())), text="A detail.", scope=block)
    with pytest.raises(TypeError):
        block.append("not a Line")
    with pytest.raises(ValueError):
        block.bind_contents((line,))
    block.append(line)
    with pytest.raises(ValueError):
        block.append(line)
    with pytest.raises(ValueError):
        block.append(make_line())
    with pytest.raises(ValueError):
        block.append(Block(id=line.id, parent=block))


def test_line_roundtrip_and_binding():
    line = make_line()
    restored = Line.records.from_record(line.records.to_record())
    assert restored.records.to_record() == line.records.to_record()
    with pytest.raises(LookupError):
        _ = restored.scope
    with pytest.raises(ValueError):
        restored.bind_scope(Block(id=Ship(str(uuid4()))))
    restored.bind_scope(line.scope)
    assert restored.scope is line.scope
    identity = restored.id
    restored.text = "It is blue."
    assert restored.id == identity
    assert restored.scope is line.scope


# tarav.breadcrumb 00f321d0811b
def test_recursive_block_context():
    root = Block(id=Ship(str(uuid4())))
    child = Block(id=Ship(str(uuid4())), parent=root)
    leaf = Block(id=Ship(str(uuid4())), parent=child)
    root.append(child)
    child.append(leaf)
    line = Line(id=Ship(str(uuid4())), text="It returns a result.", scope=leaf)
    leaf.append(line)
    assert line.scope is leaf
    assert leaf.ancestors() == (child, root)
    assert root.contents == (child,)
    assert child.content_ships == (leaf.id,)
    assert Block.records.from_record(leaf.records.to_record()).parent_ship == child.id
    restored = Block.records.from_record(root.records.to_record())
    with pytest.raises(LookupError):
        _ = restored.contents
    restored.bind_contents((child,))
    assert restored.contents == (child,)


def test_scope_must_be_a_block():
    block = Block(id=Ship(str(uuid4())))
    line = Line(id=Ship(str(uuid4())), text="A statement.", scope=block)
    with pytest.raises(TypeError):
        Line(id=Ship(str(uuid4())), text="x", scope="not an entity")
    with pytest.raises(TypeError):
        Line(id=Ship(str(uuid4())), text="x", scope=line)


def test_block_parent_cycles_and_conflicts_are_rejected():
    root = Block(id=Ship(str(uuid4())))
    child = Block(id=Ship(str(uuid4())), parent=root)
    with pytest.raises(ValueError):
        root.bind_parent(child)
    with pytest.raises(ValueError):
        root.append(Block(id=Ship(str(uuid4()))))
    with pytest.raises(ValueError):
        child.append(root)
    root.append(child)
    with pytest.raises(ValueError):
        root.append(child)


def test_loaded_parent_can_bind_before_its_own_parent():
    root = Block(id=Ship(str(uuid4())))
    middle = Block(id=Ship(str(uuid4())), parent=root)
    leaf = Block(id=Ship(str(uuid4())), parent=middle)
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

    block = SpecBlock(id=Ship(str(uuid4())))
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
