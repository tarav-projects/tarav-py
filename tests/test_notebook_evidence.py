"""Support and review are independent retained claims about exact Line states."""

from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship, entity
from tarav.l1.chatlas.references import ChatlasTurnReference
from tarav.l1.grounding import SubjectState, SupportMember, SupportSet
from tarav.l1.lines import Block
from tarav.l1.notebook import Notebook
from tarav.l1.notebook.evidence import NotebookLine, ReviewedLine, ReviewedBlock, SupportedBlock
from tarav.l1.review import VerbatimReview
from tarav.l3.runtime import create_runtime
from tarav.l2.notebook_capture import NotebookCapture, line_state


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
    state = SubjectState(line.id, entity(type(line)).id, {"text": line.text})
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
    notebook = Notebook(tmp_path / "notebook", records=runtime.records).create()
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
    support = SupportSet(id=ship(), subject=state)
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
    from tarav.l1.chatlas import references
    from tarav.l1.chatlas.normal_model.records import ChatTurn, ChatMessage

    turns, messages = [], []

    def add(side, text):
        index = len(turns) + 1
        address, digest = f"{index:064x}", f"{index + 100:064x}"
        msg = ChatMessage.records.record_example()
        msg.update(message_address=address, message_hash=digest, side=side, text=text)
        turn = ChatTurn.records.record_example()
        turn.update(turn_address=address, turn_hash=digest, side=side,
                    message_refs=[{"message_address": address, "message_hash": digest}])
        turns.append(turn)
        messages.append(msg)
        return ChatlasTurnReference.records.from_record({
            "type": "Tarav.Chatlas.Reference.Turn", "locator": {
                "session_identity": "1" * 64, "turn_address": address, "turn_hash": digest}})

    monkeypatch.setattr(references, "provide_normal_model", lambda **kw: {
        "turns": turns, "messages": messages})
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
    before = [line_state(first), line_state(second)]
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
