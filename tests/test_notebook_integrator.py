"""Notebook is the typed, scoped integration surface over the existing workflows."""
import hashlib

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.lines import Block, Line
from tarav.l1.notebook import Notebook as Storage
from tarav.l1.notebook.evidence import NotebookLine
from tarav.l2.notebook import Notebook, ProjectBlock, ModelBlock, TaravNotebook
from tarav.l2.notebook_capture import NotebookCapture
from tarav.l2.notebook_checks import SupportMissing, ReviewMissing
from tarav.l2.project import Project
from tarav.l2.project.notebook import project_notebook_ship
from tarav.l3.runtime import create_runtime
from test_notebook_evidence import chat as chat_fixture, ship

chat = chat_fixture


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


def project(name):
    return Project(id=ship(), created_at="2026-10-20T00:00:00Z", project_name=name)


# tarav.breadcrumb 76c2d409860a
def test_new_projects_share_a_typed_global_notebook_and_read_without_writing(tmp_path):
    storage = Storage(tmp_path / "notebook", records=create_runtime().records)
    first = project("First").notebook(notebook=storage)
    assert isinstance(first, Notebook) and isinstance(first, Block)
    assert not first.exists and not storage.root.exists()
    first = first.create()
    assert isinstance(first.parent, TaravNotebook)
    assert isinstance(first.model, Notebook)
    second = project("Second").notebook(notebook=storage).create()
    root = TaravNotebook.open(storage)
    assert [item.id for item in root.contents] == [first.id, second.id]
    assert first.parent_ship == second.parent_ship == root.id
    before = hashes(storage.root)
    loaded = storage.load(first.id)
    assert loaded.storage is storage
    assert loaded.model.storage is storage
    assert loaded.records.to_record() == first.records.to_record()
    assert hashes(storage.root) == before
    with pytest.raises(ValueError, match="different Notebook Type"):
        Notebook(id=loaded.contents[0].id, storage=storage).create()
    assert hashes(storage.root) == before


def test_existing_project_records_keep_identity_shape_parent_and_edited_layout(tmp_path):
    storage = Storage(tmp_path / "notebook", records=create_runtime().records).create()
    p = project("Existing")
    root = ProjectBlock(id=project_notebook_ship(p), project_ship=p.id, storage=storage)
    root.append(Line(id=ship(), text="Keep this root without predefined chapters.", scope=root))
    storage.save_tree(root)
    record = root.records.to_record()
    before = hashes(storage.root)
    loaded = p.notebook(notebook=storage).create()
    assert loaded.records.to_record() == record
    assert loaded.parent is None
    assert not TaravNotebook.open(storage).exists
    assert hashes(storage.root) == before


def test_notebook_coordinates_one_root_sets_review_and_current_state(tmp_path, chat):
    add, _ = chat
    storage = Storage(tmp_path / "notebook", records=create_runtime().records)
    book = ModelBlock(id=ship(), storage=storage).create()
    user = add("user", "Keep support and review independent.")
    neighbor = add("agent", "That permits a supported unreviewed path.")
    other_user = add("user", "Yes, and preserve earlier evidence.")
    producer = add("agent", "Capturing this agreement.")
    line = book.capture("Keep support and review independent.", root=user,
                        neighborhood=(neighbor,), producer=producer, reviewed=True)
    support, = book.evidence.support_records(line)
    assert len(support.typed.members) == 1
    assert support.typed.members[0].source.model_dump(mode="json", exclude_unset=True) == user.records.to_record()
    assert len(support.typed.members[0].neighborhood) == 1
    book.support(line, root=other_user, producer=producer)
    assert len(book.evidence.support_records(line)) == 2
    report = book.inspect(line)
    assert report["support"] == ()
    assert report["review"][0].kind == "Missing"
    proposal = add("agent", book.propose_review([line], token="notebook:one"))
    approval = add("user", "::approve notebook:one")
    review = book.record_review([line], proposal=proposal, approval=approval, token="notebook:one")
    assert book.complete_review(review).id == review.id
    assert book.inspect(storage.load(line.id))["review"] == ()
    line.text = "Preserve evidence independently of review."
    book.save()
    assert book.inspect(line)["support"][0].kind == "Stale"
    assert book.inspect(line)["review"][0].kind == "Stale"
    outside = Notebook(id=ship(), storage=storage).create()
    before = hashes(storage.root)
    with pytest.raises(ValueError, match="outside"):
        outside.support(line, root=user, producer=producer)
    with pytest.raises(ValueError, match="outside"):
        outside.propose_review([line], token="notebook:outside")
    with pytest.raises(ValueError, match="outside"):
        outside.complete_review(review)
    assert hashes(storage.root) == before
    wrong_root = outside.capture("Retain even incomplete evidence.", root=producer, producer=producer)
    assert storage.load(wrong_root.id).text == "Retain even incomplete evidence."
    assert outside.inspect(wrong_root)["support"][0].kind == "Invalid"


class EvidenceNotebook(Notebook):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("978c7db8-0754-4ba0-8479-dc0f09957c34"),
                          name="Test.Notebook.Evidence")

    @property
    def evidence(self):
        return NotebookCapture(self.storage, evidence_root=self.storage.root.parent / str(self.id))


def test_parent_routes_review_to_destination_notebook_evidence(tmp_path, chat):
    add, _ = chat
    storage = Storage(tmp_path / "notebook", records=create_runtime(record_types=(EvidenceNotebook,)).records)
    parent = Notebook(id=ship(), storage=storage)
    child = EvidenceNotebook(id=ship(), parent=parent)
    parent.append(child)
    parent = parent.create()
    child, = parent.contents
    user = add("user", "Nested notebooks can specialize evidence storage.")
    producer = add("agent", "Capturing nested evidence.")
    line = parent.capture("Keep evidence with the owning Notebook.", block=child,
                          root=user, producer=producer, reviewed=True)
    proposal = add("agent", parent.propose_review([line], destination=child, token="nested:review"))
    approval = add("user", "::approve nested:review")
    review = parent.record_review([line], destination=child, proposal=proposal,
                                  approval=approval, token="nested:review")
    assert child.evidence.reviews.load(str(review.id)).id == review.id
    assert parent.complete_review(review).id == review.id
    assert parent.inspect(line)["review"] == ()
    with pytest.raises(TypeError, match="Block"):
        parent.propose_review([line], destination=line, token="invalid:destination")


class GuardedNotebook(Notebook):
    requires_support = True
    requires_review = True

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("2c58d4af-b010-4657-a0d1-3cd036e8fe02"),
                          name="Test.Notebook.Guarded")


class WordingCheck(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("8d3c7c78-c411-4d70-9aca-02abe8566650"),
                          name="Test.Notebook.Wording.Check")

    def __init__(self, book):
        super().__init__()
        self.book = book

    def _run(self):
        unresolved = any(line.text == "Unresolved wording" for line in self.book.local_lines())
        pois = (CheckPOI(self, "Unresolved wording", situation={"notebook": str(self.book.id)}),) if unresolved else ()
        return CheckResult(self, status="completed", pois=pois)


class WordingNotebook(Notebook):
    requires_review = False

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("d2c916f7-7b71-44cb-838d-2d31de5e437b"),
                          name="Test.Notebook.Wording")

    class Checks(Notebook.Checks):
        def suite(self):
            return CheckSuite([super().suite(), WordingCheck(self.obj)])


def test_nested_notebook_checks_inherit_policy_and_include_extensions_once(tmp_path):
    runtime = create_runtime(record_types=(GuardedNotebook, WordingNotebook))
    storage = Storage(tmp_path / "notebook", records=runtime.records)
    book = GuardedNotebook(id=ship(), storage=storage)
    group = Block(id=ship(), parent=book)
    child = WordingNotebook(id=ship(), parent=group)
    child.append(NotebookLine(id=ship(), text="Unresolved wording", scope=child))
    group.append(child)
    book.append(group)
    book = book.create()
    before = hashes(storage.root)
    run = book.checks.run()
    assert run.complete, [(r.status, r.reason, [p.records.to_record() for p in r.pois()]) for r in run.results]
    assert len([p for p in run.pois() if isinstance(p, SupportMissing)]) == 1
    assert len([p for p in run.pois() if isinstance(p, ReviewMissing)]) == 1
    assert [p.message for p in run.pois() if type(p) is CheckPOI] == ["Unresolved wording"]
    assert hashes(storage.root) == before
