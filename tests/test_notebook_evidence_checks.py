"""Notebook evidence uses real Project checks and the normal action lifecycle."""

from tarav.l1.actions import CLOSED, RUNNING
from tarav.l1.actions.pois import GONE
from tarav.l1.grounding import SupportMember
from tarav.l1.lines import Line
from tarav.l1.notebook import Notebook
from tarav.l1.notebook.evidence import ReviewedBlock, SupportedBlock
from tarav.l1.references import FileReference
from tarav.l2.notebook_capture import NotebookCapture
from tarav.l2.notebook_checks import (
    ReviewMissing, SupportMissing, SupportUnavailable,
)
# tarav.breadcrumb 50bb7c995b54
from tarav.l2.project.notebook_checks import ProjectNotebookSuite
from tarav.l2.project import Project
from test_actions_workflow import registry as registry_fixture
from test_notebook_evidence import chat as chat_fixture, make_review, ship
from test_project_dev import _project

registry = registry_fixture
chat = chat_fixture


def setup_project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    project = _project(root, Project)
    notebook = Notebook()
    binding = project.notebook(notebook=notebook)
    binding.create()
    model = binding.model
    block = ReviewedBlock(id=ship(), parent=model)
    model.append(block)
    notebook.save_tree(model)
    capture = NotebookCapture(notebook).create()
    return project, capture, block


# tarav.breadcrumb a0e72b13bc2d
def test_project_review_action_closes_only_after_valid_current_evidence(tmp_path, registry, chat):
    add, _ = chat
    project, capture, block = setup_project(tmp_path)
    source = add("user", "Retain support separately from review.")
    producer = add("agent", "Capturing the supported statement.")
    line = capture.capture(block, "Retain support separately from review.",
                           members=[SupportMember(source)], producer=producer)
    initial = project.status()
    missing = [p for p in initial.checks.pois() if isinstance(p, ReviewMissing)]
    assert len(missing) == 1
    action = project.actions.of(missing[0])
    assert action.state == RUNNING
    assert not [p for p in initial.checks.pois() if isinstance(p, SupportMissing)]
    make_review(capture, block, [line], add)
    after = project.status()
    assert not [p for p in after.checks.pois() if isinstance(p, ReviewMissing)]
    closed = project.actions.of(missing[0])
    assert closed.state == CLOSED and closed.exit == GONE
    assert not capture.inspect(capture.notebook.load(line.id))["review"]


def test_unavailable_evidence_is_incomplete_and_does_not_close_existing_action(tmp_path, registry, chat):
    add, turns = chat
    project, capture, block = setup_project(tmp_path)
    line = capture.capture(block, "Awaiting support and review.")
    initial = project.status()
    missing = next(p for p in initial.checks.pois() if isinstance(p, SupportMissing))
    source, producer = add("user", "Discussed content."), add("agent", "Capture.")
    capture.attach_support(line, [SupportMember(source)], producer=producer)
    turns.clear()
    suite = ProjectNotebookSuite(project, notebook=capture.notebook).run()
    assert not suite.complete
    assert any(isinstance(p, SupportUnavailable) for p in suite.pois())
    project.actions.update(suite)
    assert project.actions.of(missing).state == RUNNING


def test_legacy_plain_lines_are_only_checked_under_explicit_requirements(tmp_path, registry):
    project, capture, block = setup_project(tmp_path)
    plain = Line(id=ship(), text="Existing wording, no fabricated evidence.", scope=block)
    block.append(plain)
    capture.notebook.save_tree(block)
    before = capture.notebook.store.path(str(plain.id)).read_bytes()
    run = ProjectNotebookSuite(project, notebook=capture.notebook).run()
    assert {type(p) for p in run.pois()} == {SupportMissing, ReviewMissing}
    assert capture.notebook.store.path(str(plain.id)).read_bytes() == before
    assert type(capture.notebook.load(plain.id)) is Line


def test_absent_project_notebook_stays_absent(tmp_path, registry):
    root = tmp_path / "project"
    root.mkdir()
    project = _project(root, Project)
    capture = NotebookCapture(Notebook())
    assert not capture.notebook.root.exists()
    run = ProjectNotebookSuite(project, notebook=capture.notebook).run()
    assert run.complete and run.pois() == ()
    assert not capture.notebook.root.exists()


def test_other_source_types_require_explicit_authorization(tmp_path, registry, chat):
    add, _ = chat
    project, capture, block = setup_project(tmp_path)
    path = tmp_path / "authorized.md"
    path.write_text("An explicitly selected User-touched source.")
    source = FileReference(path)
    producer = add("agent", "Capturing authorized source material.")
    line = capture.capture(block, "Authorized source material.",
                           members=[SupportMember(source)], producer=producer)
    assert capture.inspect(line)["support"][0].kind == "Invalid"
    permitted = NotebookCapture(capture.notebook, authorized_sources=(FileReference,))
    assert permitted.inspect(line)["support"] == ()


def test_review_requirement_cannot_be_weakened_by_a_child_type(tmp_path, registry):
    project, capture, parent = setup_project(tmp_path)
    child = SupportedBlock(id=ship(), parent=parent)
    parent.append(child)
    capture.notebook.save_tree(parent)
    line = capture.capture(child, "Still subject to the parent's review requirement.")
    assert capture.inspect(line)["review"][0].kind == "Missing"
