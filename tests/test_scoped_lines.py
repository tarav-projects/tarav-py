from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship, TaravEntity
from tarav.l1.context import ContextView, ContextExplorer, explore
from tarav.l1.lines import Block, Line, LineScope


def make_line():
    scope = TaravEntity(Ship(str(uuid4())))
    return Line(id=Ship(str(uuid4())), text="It is red.", scope=scope)


def test_block_topic_order_and_binding():
    block = Block(id=Ship(str(uuid4())), topic="The car")
    color = Line(id=Ship(str(uuid4())), text="It is red.", scope=block)
    finish = Line(id=Ship(str(uuid4())), text="The finish is matte.", scope=color)
    block.append(color)
    block.append(finish)

    assert block.lines == (color, finish)
    assert block.line_ships == (color.id, finish.id)
    assert finish.scope is color  # Block membership does not assign scope.
    assert block.ships()[-2:] == block.line_ships

    restored = Block.records.from_record(block.records.to_record())
    assert restored.records.to_record() == block.records.to_record()
    with pytest.raises(LookupError):
        _ = restored.lines
    with pytest.raises(ValueError):
        restored.bind_lines((finish, color))
    restored.bind_lines((color, finish))
    assert restored.lines == block.lines
    assert explore(restored).open("lines").open(1) is finish


def test_block_rejects_invalid_membership():
    block = Block(id=Ship(str(uuid4())), topic="A topic")
    line = make_line()
    with pytest.raises(ValueError):
        Block(id=Ship(str(uuid4())), topic=" ")
    with pytest.raises(TypeError):
        block.append("not a Line")
    with pytest.raises(ValueError):
        block.bind_lines((line,))
    block.append(line)
    with pytest.raises(ValueError):
        block.append(line)


def test_line_roundtrip_and_binding():
    line = make_line()
    restored = Line.records.from_record(line.records.to_record())
    assert restored.records.to_record() == line.records.to_record()
    with pytest.raises(LookupError):
        _ = restored.scope
    with pytest.raises(ValueError):
        restored.bind_scope(TaravEntity(Ship(str(uuid4()))))
    restored.bind_scope(line.scope)
    assert restored.scope is line.scope
    identity = restored.id
    restored.text = "It is blue."
    assert restored.id == identity
    assert restored.scope is line.scope


def test_nested_scope_and_typed_view():
    line = make_line()
    detail = Line(id=Ship(str(uuid4())), text="The finish is matte.", scope=line)
    before = detail.records.to_record()
    view = explore(detail, views=(LineScope,))
    assert isinstance(view, LineScope)
    assert view.scope is line
    assert view.open("scope") is line
    assert detail.records.to_record() == before
    assert isinstance(explore(detail), ContextExplorer)
    with pytest.raises(TypeError):
        explore(detail, views=(ContextView,))
    with pytest.raises(TypeError):
        explore(line.scope, views=(LineScope,))
    with pytest.raises(TypeError):
        Line(id=Ship(str(uuid4())), text="x", scope="not an entity")


def test_scope_cycles_are_serialized_as_edges():
    identity = Ship(str(uuid4()))
    line = Line.records.from_record({"id": str(identity), "text": "self scoped",
                             "scope_ship": str(identity)})
    line.bind_scope(line)
    assert line.scope is line
    assert line.records.to_record()['scope_ship'] == str(identity)


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
    assert line.context(views=(LineScope,)).scope is line.scope
    assert isinstance(line.context(), ContextExplorer)
    assert get_runtime().records is not None


def test_models_fail_before_side_effects(tmp_path):
    from tarav.l2.models.model import Model
    from tarav.l2.models.errors import ToImplementError
    from tarav.l2.project.models import ProjectModels
    from tarav.l2.unsorted.storage import DiagramNamespace

    with pytest.raises(ToImplementError):
        Model("anything", None, "edition")
    with pytest.raises(ToImplementError):
        ProjectModels(None)
    namespace = object.__new__(DiagramNamespace)
    with pytest.raises(ToImplementError):
        namespace.create_model()
    assert list(tmp_path.iterdir()) == []


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
