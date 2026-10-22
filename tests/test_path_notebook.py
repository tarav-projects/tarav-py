"""Registered Ships anchor notes; Notebook ancestry bounds their interpretation."""
# tarav.breadcrumb 68394b3d88f6

import json
from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship, entity
from tarav.l1.lines import Block, Line
from tarav.l1.notebook import Notebook as Storage
from tarav.l1.path_registry import JSONView, PathRegistry
from tarav.l2.notebook import PathNotebook, SchemaBlock, PathBlock, ProjectBlock
from tarav.l2.notebook_capture import line_state
from tarav.l2.project import Project
from tarav.l3.runtime import create_runtime


def ship():
    return Ship(uuid4())


@pytest.fixture
def setup(tmp_path):
    storage = Storage(tmp_path / "notebook", records=create_runtime().records)
    project = Project(id=ship(), created_at="2026-10-22T00:00:00Z", project_name="Paths")
    registry = PathRegistry(project.id)
    view = JSONView(entity(Line).id, "record", Line.view_schemas()["record"])
    registry.enroll(view)
    book = project.notebook(notebook=storage).create().paths
    return storage, project, registry, view, book


def entry(registry, view, path):
    result, = registry.at(view.id, path)
    return result


def hashes(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def test_project_selects_nested_path_notebook_without_writing_then_explicitly_adds_it(tmp_path):
    storage = Storage(tmp_path / "notebook", records=create_runtime().records)
    project = Project(id=ship(), created_at="2026-10-22T00:00:00Z", project_name="Existing")
    selected = project.paths.notebook(notebook=storage)
    assert isinstance(selected, PathNotebook)
    assert isinstance(selected.parent, ProjectBlock)
    assert selected.parent.project_ship == project.id
    assert not storage.root.exists()
    # Simulate an existing notebook with an edited, minimal layout.
    root = ProjectBlock(id=selected.parent.id, project_ship=project.id, storage=storage)
    root.append(Line(id=ship(), text="Keep the existing project notes.", scope=root))
    storage.create().save_tree(root)
    original_line = storage.store.path(str(root.contents[0].id)).read_bytes()
    before = hashes(storage.root)
    assert project.paths.notebook(notebook=storage).parent_ship == root.id
    assert hashes(storage.root) == before
    loaded = project.paths.notebook(notebook=storage).create()
    persisted = storage.load(root.id)
    assert persisted.content_ships == (root.contents[0].id, loaded.id)
    assert loaded.parent_ship == root.id
    assert storage.store.path(str(root.contents[0].id)).read_bytes() == original_line
    before = hashes(storage.root)
    assert persisted.create().paths.id == loaded.id
    assert hashes(storage.root) == before


def test_schema_and_parent_notes_are_context_and_links_round_trip(setup):
    storage, _, registry, view, book = setup
    target = entry(registry, view, "/properties/text")
    before = hashes(storage.root)
    leaf = book.add_path(registry, target.id)
    assert hashes(storage.root) == before  # explicit save owns persistence
    ancestors = leaf.ancestors()
    assert [type(obj) for obj in ancestors[:4]] == [PathBlock, PathBlock, SchemaBlock, PathNotebook]
    schema = book.schema(registry, view.id)
    parents = [schema, ancestors[1], ancestors[0], leaf]
    for block, text in zip(parents, ["Schema context", "Root context", "Properties context", "Text note"]):
        block.append(Line(id=ship(), text=text, scope=block))
    book.save()
    restored = storage.load(leaf.id)
    assert restored.path_ship == target.id
    assert registry.id in book.ships()
    assert view.id in schema.ships()
    assert target.id in restored.ships()
    note = restored.contents[0]
    state = line_state(note)
    context_text = [line["text"] for block in state.typed.payload["context"] for line in block["lines"]]
    assert context_text[-3:] == ["Schema context", "Root context", "Properties context"]
    assert note.scope is restored
    reopened = storage.load(book.id)
    assert reopened.path(registry, target.id).id == leaf.id
    before = hashes(storage.root)
    assert reopened.label(registry, target.id) == "/properties/text"
    assert reopened.schema(registry, view.id).schema_ship == view.id
    assert hashes(storage.root) == before
    assert "attachments" not in json.dumps(registry.records.to_record())


def test_create_preserves_notes_prepared_before_the_parent_is_persisted(tmp_path):
    storage = Storage(tmp_path / "notebook", records=create_runtime().records)
    project = Project(id=ship(), created_at="2026-10-22T00:00:00Z", project_name="Prepared")
    registry = PathRegistry(project.id)
    view = JSONView(entity(Line).id, "record", Line.view_schemas()["record"])
    registry.enroll(view)
    book = project.paths.notebook(notebook=storage)
    target = entry(registry, view, "/properties/text")
    leaf = book.add_path(registry, target.id)
    note = Line(id=ship(), text="Retain these prepared notes.", scope=leaf)
    leaf.append(note)
    created = book.create()
    assert created.path(registry, target.id).contents[0].text == "Retain these prepared notes."
    assert storage.load(note.id).scope.id == leaf.id


@pytest.mark.parametrize("pointer,expected", [
    ("", [""]),
    ("/a~1b/~0/0", ["/a~1b/~0/0", "/a~1b/~0", "/a~1b", ""]),
    ("/a~1b/~0/1", ["/a~1b/~0/1", "/a~1b/~0", "/a~1b", ""]),
    ("/", ["/", ""]),
])
def test_pointer_parents_use_exact_tokens_not_decoded_slashes(setup, pointer, expected):
    _, _, registry, _, book = setup
    view = JSONView(entity(Block).id, "custom", {"a/b": {"~": [1, 2]}, "": 3})
    registry.enroll(view)
    target = entry(registry, view, pointer)
    block = book.add_path(registry, target.id)
    path_blocks = [block, *(p for p in block.ancestors() if isinstance(p, PathBlock))]
    assert [registry.entry(b.path_ship).typed.path for b in path_blocks] == expected
    assert book.label(registry, target.id) == pointer


def test_missing_ambiguous_and_retired_paths_do_not_create_notes(setup):
    _, _, registry, view, book = setup
    target = entry(registry, view, "/properties/text")
    before = book.records.to_record()
    with pytest.raises(LookupError):
        book.path(registry, target.id)
    registry.add(view.id, "/properties")
    with pytest.raises(LookupError, match="ancestry"):
        book.add_path(registry, target.id)
    assert book.records.to_record() == before
    registry.retire(target.id)
    with pytest.raises(ValueError, match="retired"):
        book.add_path(registry, target.id)
    with pytest.raises(ValueError, match="different registry"):
        book.add_schema(PathRegistry(ship()), view.id)


def test_path_rename_preserves_notes_but_new_parent_requires_explicit_maintenance(setup):
    storage, _, registry, view, book = setup
    target = entry(registry, view, "/properties/text")
    leaf = book.add_path(registry, target.id)
    note = Line(id=ship(), text="The wording of the statement.", scope=leaf)
    leaf.append(note)
    book.save()
    registry.declare(target.id, "/properties/wording")
    assert book.path(registry, target.id).id == leaf.id
    assert book.label(registry, target.id) == "/properties/wording"
    registry.add(view.id, "/other")
    registry.declare(target.id, "/other/wording")
    before = hashes(storage.root), tuple(obj.id for obj in book.walk())
    with pytest.raises(ValueError, match="ancestry changed"):
        book.path(registry, target.id)
    with pytest.raises(ValueError, match="ancestry changed"):
        book.add_path(registry, target.id)
    assert (hashes(storage.root), tuple(obj.id for obj in book.walk())) == before
    assert storage.load(note.id).text == note.text  # historical context stays readable


def test_typed_note_blocks_reject_unlinked_block_children(setup):
    _, _, registry, view, book = setup
    schema = book.add_schema(registry, view.id)
    with pytest.raises(TypeError, match="SchemaBlocks"):
        book.append(Block(id=ship(), parent=book))
    with pytest.raises(TypeError, match="PathBlocks"):
        schema.append(Block(id=ship(), parent=schema))
