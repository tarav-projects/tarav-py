"""Support and review are independent retained claims about exact Line states."""

from uuid import uuid4
import json
import subprocess

import pytest

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l1.chatlas.references import ChatlasTurnReference
from tarav.l1.grounding import SubjectState, SupportMember, SupportSet
from tarav.l1.lines import Block
from tarav.l1.notebook import Notebook
from tarav.l2.notebook_references import NotebookStateReference
from tarav.l1.notebook.evidence import (
    NotebookLine, ReviewedBlockTitle, ReviewedLine, ReviewedBlock, SupportedBlock,
)
from tarav.l1.review import VerbatimReview
from tarav.l3.runtime import create_runtime
from tarav.l2.notebook_capture import NotebookCapture, NotebookReviewFrame, line_state


def ship():
    return Ship(uuid4())


def ref(address="a", identity="1", digest="b"):
    return ChatlasTurnReference.records.from_record({
        "type": "Tarav.Chatlas.Reference.Turn", "locator": {
            "session_identity": identity * 64, "turn_address": address * 64,
            "turn_hash": digest * 64,
        }})


# tarav.breadcrumb fff2503929ae
def test_evidence_records_roundtrip_and_keep_support_separate_from_review(tmp_path):
    runtime = create_runtime()
    block = Block(id=ship())
    line = NotebookLine(id=ship(), text="Preserve evidence.", scope=block)
    block.append(line)
    notebook = Notebook(tmp_path / "notebook", records=runtime.records).create()
    notebook.save_tree(block)
    state = NotebookCapture(notebook).pin(line)
    member = SupportMember(ref(), neighborhood=(ref("c"),))
    support = SupportSet(id=ship(), subject=state, members=(member,), producer=ref("d"))
    review = VerbatimReview(id=ship(), destination=block.id, operation="review",
                            after=(state,), token="review:one", proposal=ref("d"), approval=ref("e"))
    line.support_ships.append(support.id)
    line.review_ships.append(review.id)
    for obj in (state, member, support, review):
        record = obj.records.to_record()
        loaded = runtime.records.from_record(record)
        assert type(loaded) is type(obj)
        assert loaded.records.to_record() == record
    notebook.save_tree(block)
    loaded = notebook.load(line.id)
    assert type(loaded) is NotebookLine
    assert loaded.text == "Preserve evidence."
    assert loaded.support_ships == [support.id]
    assert loaded.review_ships == [review.id]
    assert loaded.scope.contents[0] is loaded
    assert ReviewedLine.requires_review and not NotebookLine.requires_review


def test_evidence_state_digest_detects_tampering_and_empty_support_remains_recordable():
    state = SubjectState(ship(), entity(NotebookLine).id, {"text": "Original."})
    reference = NotebookStateReference.records.from_record(NotebookStateReference.records.record_example())
    support = SupportSet(id=ship(), subject=reference)
    assert support.records.to_record()["members"] == []
    record = state.records.to_record()
    record["payload"]["text"] = "Changed."
    with pytest.raises(ValueError, match="digest"):
        SubjectState.records.from_record(record)
    with pytest.raises(ValueError, match="after states"):
        VerbatimReview(id=ship(), destination=ship(), operation="review", token="t",
                       proposal=ref(), approval=ref("c"))


@pytest.fixture
def chat(monkeypatch):
    """Actual Normal Model reference resolution over fixed turn/message records."""
    # tarav.breadcrumb a0df24b63a6c
    from tarav.l1.chatlas import references
    from tarav.l1.chatlas.normal_model.records import ChatTurn, ChatMessage

    turns, messages, events = [], [], []

    def add(side, text):
        index = len(turns) + 1
        address, digest = f"{index:064x}", f"{index + 100:064x}"
        msg = ChatMessage.records.record_example()
        msg.update(message_address=address, message_hash=digest, side=side, text=text)
        turn = ChatTurn.records.record_example()
        turn.update(turn_address=address, turn_hash=digest, side=side,
                    event_refs=[{"event_address": address, "event_hash": digest}],
                    message_refs=[{"message_address": address, "message_hash": digest}])
        events.append({"event_address": address, "started_at": f"2026-10-22T00:00:{index:02d}Z"})
        turns.append(turn)
        messages.append(msg)
        return ChatlasTurnReference.records.from_record({
            "type": "Tarav.Chatlas.Reference.Turn", "locator": {
                "session_identity": "1" * 64, "turn_address": address, "turn_hash": digest}})

    monkeypatch.setattr(references, "provide_normal_model", lambda **kw: {
        "turns": turns, "messages": messages, "events": events})
    return add, turns


def capture_setup(tmp_path, block_type=SupportedBlock):
    runtime = create_runtime()
    notebook = Notebook(tmp_path / "notebook", records=runtime.records).create()
    block = block_type(id=ship())
    notebook.save_tree(block)
    return NotebookCapture(notebook, evidence_root=tmp_path / "evidence").create(), block


def test_support_capture_reload_and_change_preserves_the_old_claim(tmp_path, chat):
    add, turns = chat
    user = add("user", "Keep evidence separate from review.")
    agent = add("agent", "I will capture that.")
    capture, block = capture_setup(tmp_path)
    line = capture.capture(block, "Keep evidence separate from review.",
                           members=(SupportMember(user),), producer=agent)
    original_support = capture.support_records(line)[0].records.to_record()
    assert capture.inspect(line)["support"] == ()
    assert capture.inspect(line)["review"] == ()
    line.text = "Retain evidence independently of review."
    capture.notebook.save(line)
    assert capture.inspect(line)["support"][0].kind == "Stale"
    assert capture.support_records(line)[0].records.to_record() == original_support
    capture.attach_support(line, (SupportMember(user),), producer=agent)
    loaded = capture.notebook.load(line.id)
    assert capture.inspect(loaded)["support"] == ()
    assert len(loaded.support_ships) == 2
    turns[0]["turn_hash"] = "f" * 64
    assert capture.inspect(loaded)["support"][0].kind == "Invalid"


def test_support_missing_wrong_role_and_unavailable_are_detected_without_blocking_save(tmp_path, chat):
    add, turns = chat
    agent = add("agent", "Agent-generated source.")
    capture, block = capture_setup(tmp_path)
    line = capture.capture(block, "No substantive support yet.")
    assert capture.notebook.load(line.id).text == "No substantive support yet."
    assert capture.inspect(line)["support"][0].kind == "Missing"
    capture.attach_support(line, (SupportMember(agent),), producer=agent)
    assert capture.inspect(line)["support"][0].kind == "Invalid"
    turns.clear()
    assert capture.inspect(line)["support"][0].kind == "Unavailable"


def make_review(capture, block, lines, add, *, text=None, approval=None, operation="review", before=()):
    rendered = capture.propose_review(lines, destination=block, token="review:one",
                                      operation=operation, before=before)
    proposal = add("agent", rendered if text is None else text + "\nreview:one")
    user = add("user", approval or "::approve review:one")
    return capture.record_review(lines, destination=block, operation=operation,
                                  before=before, token="review:one", proposal=proposal, approval=user)


def test_review_is_independent_and_bounded_and_detects_ancestor_context_changes(tmp_path, chat):
    add, _ = chat
    capture, block = capture_setup(tmp_path, ReviewedBlock)
    child = SupportedBlock(id=ship(), parent=block)
    block.append(child)
    capture.notebook.save_tree(block)
    line = capture.capture(child, "Reviewed wording.")
    assert capture.inspect(line)["review"][0].kind == "Missing"
    review = make_review(capture, block, [line], add)
    assert capture.complete_review(review).id == review.id
    assert capture.inspect(line)["review"] == ()
    assert capture.inspect(line)["support"][0].kind == "Missing"
    context = NotebookLine(id=ship(), text="A new interpretive context.", scope=block)
    block.append(context)
    capture.notebook.save_tree(block)
    assert capture.inspect(line)["review"][0].kind == "Stale"
    with pytest.raises(ValueError, match="state changed"):
        capture.complete_review(review)
    make_review(capture, block, [line], add)
    assert capture.inspect(line)["review"] == ()
    assert len(capture.notebook.load(line.id).review_ships) == 2


@pytest.mark.parametrize("problem", ["token", "wording", "destination", "role", "order"])
def test_review_protocol_failures_are_retained_but_cannot_complete(tmp_path, chat, problem):
    add, _ = chat
    capture, block = capture_setup(tmp_path, ReviewedBlock)
    line = capture.capture(block, "Exact Case matters.")
    text = capture.propose_review([line], destination=block, token="review:one")
    if problem == "wording":
        text = text.replace("Exact Case", "exact case")
    if problem == "destination":
        text = text.replace(str(block.id), str(ship()))
    early = add("user", "::approve review:one") if problem == "order" else None
    proposal = add("user" if problem == "role" else "agent", text + "\nreview:one")
    approval = early or add("user", "::approve another-token" if problem == "token" else "::approve review:one")
    review = capture.record_review([line], destination=block, token="review:one",
                                    proposal=proposal, approval=approval)
    assert capture.reviews.load(str(review.id)).id == review.id
    assert capture.inspect(line)["review"][0].kind == "Invalid"
    with pytest.raises(ValueError, match="not complete"):
        capture.complete_review(review)


def test_bounded_multi_line_modify_and_removal_review(tmp_path, chat):
    add, _ = chat
    capture, block = capture_setup(tmp_path)
    first = capture.capture(block, "Original first.")
    second = capture.capture(block, "Original second.")
    before = [capture.pin(first), capture.pin(second)]
    first.text, second.text = "New first.", "New second."
    capture.notebook.save_tree(block)
    review = make_review(capture, block, [first, second], add, operation="modify", before=before)
    assert capture.complete_review(review).id == review.id
    assert capture.inspect(first)["review"] == capture.inspect(second)["review"] == ()
    removed = make_review(capture, block, [], add, operation="remove", before=[line_state(first)])
    with pytest.raises(ValueError, match="still present"):
        capture.complete_review(removed)
    # Capture records the explicit operation; ordinary Block editing remains separate.
    block = SupportedBlock(id=block.id, contents=(second,))
    second.bind_scope(block)
    capture.notebook.save_tree(block)
    assert capture.complete_review(removed).id == removed.id
    assert capture.inspect(second)["review"][0].kind == "Stale"


def test_read_only_capture_selection_does_not_provision_and_state_is_a_snapshot(tmp_path):
    runtime = create_runtime()
    notebook = Notebook(tmp_path / "absent", records=runtime.records)
    NotebookCapture(notebook, evidence_root=tmp_path / "absent-evidence")
    assert not notebook.root.exists() and not (tmp_path / "absent-evidence").exists()
    payload = {"text": "Original.", "context": [{"text": "Old context."}]}
    state = SubjectState(ship(), entity(NotebookLine).id, payload)
    payload["context"][0]["text"] = "New context."
    assert state.typed.payload["context"][0]["text"] == "Old context."


def test_capture_cannot_reuse_an_existing_ship_under_another_block(tmp_path):
    capture, block = capture_setup(tmp_path)
    line = capture.capture(block, "Original statement.")
    other = SupportedBlock(id=ship())
    capture.notebook.save_tree(other)
    with pytest.raises(FileExistsError, match="already exists"):
        capture.capture(other, "Another statement.", id=line.id)
    assert other.contents == ()
    assert capture.notebook.load(line.id).scope.id == block.id


def test_review_binds_context_as_presented_not_only_the_words(tmp_path, chat):
    add, _ = chat
    capture, block = capture_setup(tmp_path, ReviewedBlock)
    line = capture.capture(block, "Unchanged words.")
    presentation = capture.propose_review([line], destination=block, token="review:context")
    proposal = add("agent", presentation)
    context = NotebookLine(id=ship(), text="A different interpretation now applies.", scope=block)
    block.append(context)
    capture.notebook.save_tree(block)
    approval = add("user", "::approve review:context")
    # A late attachment cannot reinterpret an earlier approval under a new context.
    review = capture.record_review([line], destination=block, proposal=proposal, approval=approval,
                                    token="review:context")
    assert capture.review_problems(review)[0].kind == "Invalid"
    with pytest.raises(ValueError, match="not complete"):
        capture.complete_review(review)


def frame_setup(tmp_path):
    capture, parent = capture_setup(tmp_path)
    block = Block(id=ship(), parent=parent)
    parent.append(block)
    title = ReviewedBlockTitle(id=ship(), text="Review.Frame", scope=block)
    line = ReviewedLine(id=ship(), text="Approval accepts the presented wording.", scope=block)
    block.append(title)
    block.append(line)
    capture.notebook.save_tree(parent)
    return capture, parent, block, (title, line)


def test_markdown_review_frame_lands_exact_wording_and_retains_independent_support(tmp_path, chat):
    add, _ = chat
    capture, parent, block, lines = frame_setup(tmp_path)
    root = add("user", "Use Review.Frame; approval accepts the presented wording.")
    proposal = add("agent", "**Add to:** Example Project → Discussion.\n\n"
                   "## Review.Frame\n\n- Approval accepts the presented wording.\n\n"
                   "```text\n::approve review:frame\n```")
    approval = add("user", "::approve review:frame")
    review = capture.record_review(
        lines, destination=parent, operation="add", frame_location="Example Project → Discussion.",
        token="review:frame", proposal=proposal, approval=approval,
    )
    assert isinstance(review, NotebookReviewFrame)
    assert capture.complete_review(review).id == review.id
    restored = capture.reviews.load(str(review.id))
    assert type(restored) is NotebookReviewFrame
    assert restored.presentation() == review.presentation()
    for line in lines:
        assert capture.inspect(line)["review"] == ()
        assert capture.inspect(line)["support"][0].kind == "Missing"
        capture.attach_support(line, (SupportMember(root),), producer=proposal)
        assert capture.inspect(line)["support"] == ()
    loaded_title = capture.notebook.load(lines[0].id)
    assert isinstance(loaded_title, ReviewedBlockTitle)
    with pytest.raises(ValueError):
        loaded_title.text = "ordinary prose"
    block.append(NotebookLine(id=ship(), text="A changed authoring context.", scope=block))
    capture.notebook.save_tree(block)
    assert capture.inspect(lines[1])["review"][0].kind == "Stale"


@pytest.mark.parametrize("problem", ["wording", "location", "token", "role", "order"])
def test_markdown_review_frame_does_not_accept_other_content_or_approval(tmp_path, chat, problem):
    add, _ = chat
    capture, parent, _, lines = frame_setup(tmp_path)
    text = "**Add to:** Example.\n\n## Review.Frame\n\n- Approval accepts the presented wording."
    if problem == "wording":
        text = text.replace("accepts", "rejects")
    if problem == "location":
        text = text.replace("Example.", "Another.")
    early = add("user", "::approve review:frame") if problem == "order" else None
    proposal = add("user" if problem == "role" else "agent", text + "\n::approve review:frame")
    approval = early or add("user", "::approve wrong" if problem == "token" else "::approve review:frame")
    review = capture.record_review(
        lines, destination=parent, operation="add", frame_location="Example.",
        token="review:frame", proposal=proposal, approval=approval,
    )
    assert capture.review_problems(review)[0].kind == "Invalid"


def test_markdown_review_frame_rejects_hidden_or_reordered_lines_and_wrong_destination(tmp_path, chat):
    add, _ = chat
    capture, parent, block, lines = frame_setup(tmp_path)
    proposal, approval = add("agent", "Pending proposal"), add("user", "::approve review:frame")
    for states, destination in ((lines[:1], parent), (tuple(reversed(lines)), parent), (lines, block)):
        with pytest.raises(ValueError):
            review = NotebookReviewFrame(
                id=ship(), destination=destination.id, block_ship=block.id, location="Example.",
                after=[capture.pin(line) for line in states], token="review:frame",
                proposal=proposal, approval=approval,
            )
            review.presentation()


def test_git_subjects_preserve_context_without_embedding_it_and_ignore_unrelated_commits(tmp_path, chat):
    from tarav.l1.grounding import resolve_subject

    add, _ = chat
    capture, block = capture_setup(tmp_path)
    user = add("user", "Use Git to preserve the capture context.")
    producer = add("agent", "Capturing the principle.")
    line = capture.capture(block, "Preserve capture context in Git.",
                           members=(SupportMember(user),), producer=producer)
    support, = capture.support_records(line)
    subject = support.records.to_record()["subject"]
    assert set(subject) == {"type", "locator"}
    assert set(subject["locator"]) == {"registry", "doi", "commit", "tree", "change_id", "path"}
    assert len(subject["locator"]["commit"]) == 40
    assert subject["locator"]["path"] == f"records/{line.id}.json"
    original = resolve_subject(support.typed.subject)
    child = Block(id=ship(), parent=block)
    block.append(child)
    capture.notebook.save_tree(block)
    assert capture.checkpoint() != subject["locator"]["commit"]
    assert capture.inspect(line)["support"] == ()
    context = NotebookLine(id=ship(), text="A new interpretation.", scope=block)
    block.append(context)
    capture.notebook.save_tree(block)
    assert capture.inspect(line)["support"][0].kind == "Stale"
    assert resolve_subject(support.typed.subject).digest == original.digest
    assert resolve_subject(support.typed.subject).payload == original.payload
    bad = support.records.to_record()
    bad["subject"]["locator"]["commit"] = "f" * 40
    capture.supports.replace(str(support.id), SupportSet.records.from_record(bad))
    # Missing original hashes can recover through the matching Change-ID/tree.
    assert capture.inspect(line)["support"][0].kind == "Stale"
    bad["subject"]["locator"]["tree"] = "f" * 40
    capture.supports.replace(str(support.id), SupportSet.records.from_record(bad))
    assert capture.inspect(line)["support"][0].kind == "Unavailable"


def test_git_review_records_resolve_exact_wording_and_reject_moving_revisions(tmp_path, chat):
    from tarav.l1.grounding import resolve_subject

    add, _ = chat
    capture, block = capture_setup(tmp_path)
    line = capture.capture(block, "Pin the reviewed wording.")
    review = make_review(capture, block, [line], add)
    after = review.records.to_record()["after"][0]
    assert set(after) == {"type", "locator"}
    assert resolve_subject(review.typed.after[0]).payload["text"] == line.text
    assert capture.complete_review(review).id == review.id
    original = NotebookStateReference.records.from_record(after)
    later = capture.pin(line, commit=capture.checkpoint())
    repeated = VerbatimReview(id=ship(), destination=block.id, operation="review",
                              after=[original, later], token="review:repeated",
                              proposal=ref(), approval=ref("c"))
    with pytest.raises(ValueError, match="repeat a Ship"):
        repeated.presentation()
    after["locator"]["commit"] = "HEAD"
    with pytest.raises(ValueError, match="pattern"):
        NotebookStateReference.records.from_record(after)


def _git(root, *args, input=None):
    return subprocess.run(["git", "-C", str(root), *args], input=input, text=True,
                          capture_output=True, check=True).stdout.strip()


class SpecializedEvidenceLine(NotebookLine):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("86da3bc2-a7f8-426e-9ecb-2c20474d251d"),
                          name="Test.Notebook.SpecializedEvidenceLine")


def test_state_reference_uses_its_bound_record_registry(tmp_path):
    runtime = create_runtime(record_types=(SpecializedEvidenceLine,))
    block = Block(id=ship())
    line = SpecializedEvidenceLine(id=ship(), text="A specialized statement.", scope=block)
    block.append(line)
    storage = Notebook(tmp_path / "specialized", records=runtime.records).create()
    storage.save_tree(block)
    reference = NotebookCapture(storage).pin(line)
    create_runtime()  # The process default has no registration for this Line subtype.
    loaded = runtime.records.from_record(reference.records.to_record())
    result = loaded.resolve()
    assert result.ok
    assert result.target["state"].typed.subject_type == entity(SpecializedEvidenceLine).id
    assert result.target["state"].typed.payload["text"] == "A specialized statement."


def test_notebook_state_follows_maintained_repository_location_without_writes(tmp_path):
    # tarav.breadcrumb ad096e6987e7
    from tarav.l1.archive import Archive
    from tarav.l1.archive.model import LocalLocator

    capture, block = capture_setup(tmp_path)
    line = capture.capture(block, "Keep the original context.")
    reference = capture.pin(line)
    expected = reference.resolve().target["state"].typed.digest
    root = capture.notebook.root
    moved = tmp_path / "relocated"
    root.rename(moved)
    assert not reference.resolve().ok
    archive = Archive.open(reference.locator["registry"])
    doi = archive.read(reference.locator["doi"])
    doi.locators = [LocalLocator(moved)]
    archive.update(doi)
    before = {str(p.relative_to(moved)): p.read_bytes() for p in moved.rglob('*') if p.is_file()}
    resolved = reference.resolve()
    assert resolved.ok and resolved.target["state"].typed.digest == expected
    assert resolved.target["repository"] == str(moved)
    assert before == {str(p.relative_to(moved)): p.read_bytes() for p in moved.rglob('*') if p.is_file()}


@pytest.mark.parametrize("changed", [False, True])
def test_notebook_state_recovers_only_matching_tree_after_rewrite(tmp_path, changed):
    capture, block = capture_setup(tmp_path)
    line = capture.capture(block, "Original wording.")
    reference = capture.pin(line)
    original = reference.resolve().target["state"].typed.digest
    coordinate = reference.locator.copy()
    root = capture.notebook.root
    if changed:
        path = capture.notebook.store.path(str(line.id))
        data = json.loads(path.read_text())
        data["text"] = "Different wording."
        path.write_text(json.dumps(data))
        _git(root, "add", "records")
        tree = _git(root, "write-tree")
    else:
        tree = coordinate["tree"]
    commit = _git(root, "commit-tree", tree,
                  input=f"Rewritten\n\ntarav-change: {coordinate['change_id']}\n")
    branch = _git(root, "symbolic-ref", "HEAD")
    _git(root, "update-ref", branch, commit)
    _git(root, "reflog", "expire", "--expire=now", "--all")
    _git(root, "gc", "--prune=now")
    result = reference.resolve()
    if changed:
        assert not result.ok and "matches" in result.message
    else:
        assert result.ok and result.target["recovered"] is True
        assert result.target["commit"] == commit
        assert result.target["state"].typed.digest == original
    assert reference.locator == coordinate


def test_evidence_writes_commit_all_three_stores_and_keep_distinct_witnesses(tmp_path, chat):
    from tarav.l1.git.hooks import GitConfig
    from tarav.l1.git.witness import ChangeWitnesses
    from tarav.l1.project.config import ProjectConfig

    add, _ = chat
    capture, block = capture_setup(tmp_path)
    user = add("user", "Preserve the wording.")
    producer = add("agent", "Capture it.")
    line = capture.capture(block, "Preserve the wording.",
                           members=[SupportMember(user)], producer=producer)
    review = make_review(capture, block, [line], add)
    assert capture.complete_review(review).id == review.id
    identities = []
    for store in [capture.notebook.store, capture.supports, capture.reviews]:
        config = ProjectConfig(store.root).section("git", GitConfig)
        identities.append(config.repository)
        assert _git(store.root, "status", "--porcelain") == ""
        assert "tarav-change:" in _git(store.root, "show", "-s", "--format=%B", "HEAD")
        branch = _git(store.root, "symbolic-ref", "--short", "HEAD")
        witness = ChangeWitnesses().get(config.repository, branch)
        assert witness.changes == (store.root / ".tarav/changes").read_text().splitlines()
    assert len(set(identities)) == 3
