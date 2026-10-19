from uuid import uuid4

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l1.lines import Line
from tarav.l1.notebook import Notebook, NotebookWorkflow
# tarav.breadcrumb 2be65786dd7c
from tarav.l1.notebook.blocks import (
    ArchiveBlock, DiscussionBlock, ModelBlock, ProjectBlock,
)
from tarav.l2.project import Project
from tarav.l3.runtime import create_runtime


def project(tmp_path, name):
    return Project(id=Ship(uuid4()), created_at="2026-10-19T00:00:00Z", project_name=name)


def test_project_notebook_creates_siblings_once_and_keeps_edits(tmp_path):
    notebook = Notebook(tmp_path / "notebook", records=create_runtime().records)
    p = project(tmp_path, "Tarav")
    binding = p.notebook(notebook=notebook)
    assert not notebook.root.exists()
    root = binding.create()
    assert isinstance(root, ProjectBlock)
    assert root.project_ship == p.id
    branches = [x for x in root.contents if not isinstance(x, Line)]
    assert [type(x) for x in branches] == [DiscussionBlock, ModelBlock, ArchiveBlock]
    assert all(x.parent is root for x in branches)
    assert "no implementation" in binding.discussion.contents[0].text
    assert "current" in binding.model.contents[0].text
    assert "Historical" in binding.archive.contents[0].text
    note = Line(id=Ship(uuid4()), text="Keep this discussion.", scope=binding.discussion)
    discussion = note.scope
    discussion.append(note)
    notebook.save_tree(discussion)
    binding.create()
    assert binding.discussion.contents[-1].text == "Keep this discussion."
    assert p.notebook(notebook=notebook).root.id == root.id
    other = project(tmp_path, "Other").notebook(notebook=notebook)
    assert other.create().id != root.id
    assert all(line.text != "Keep this discussion."
               for line in other.discussion.contents)


def test_project_type_can_choose_a_layout(tmp_path):
    class DiscussionProject(Project):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("bfb52d7d-0fef-432b-b72a-09c9ce707327"),
                              name="Test.DiscussionProject")

        def notebook_layout(self):
            return (DiscussionBlock,)

    notebook = Notebook(tmp_path / "notebook", records=create_runtime().records)
    p = DiscussionProject(id=Ship(uuid4()), created_at="2026-10-19T00:00:00Z",
                          project_name="A project")
    root = p.notebook(notebook=notebook).create()
    assert [type(x) for x in root.contents if not isinstance(x, Line)] == [DiscussionBlock]


def test_notebook_types_are_registered_without_project_dependency(tmp_path):
    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.Notebook") is NotebookWorkflow
    for cls in (Notebook, ProjectBlock, DiscussionBlock, ModelBlock, ArchiveBlock):
        assert runtime.records.resolve_ship(entity(cls).id) is cls
        assert entity(cls).workflow is NotebookWorkflow()
