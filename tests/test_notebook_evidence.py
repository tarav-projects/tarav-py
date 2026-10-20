"""Support and review are independent retained claims about exact Line states."""

from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship, entity
from tarav.l1.chatlas.references import ChatlasTurnReference
from tarav.l1.grounding import SubjectState, SupportMember, SupportSet
from tarav.l1.lines import Block
from tarav.l1.notebook import Notebook
from tarav.l1.notebook.evidence import NotebookLine, ReviewedLine
from tarav.l1.review import VerbatimReview
from tarav.l3.runtime import create_runtime


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
