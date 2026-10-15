"""The experiment uses the existing Record and ownership boundaries."""

import json

import pytest
from pydantic import ValidationError

from tarav.l0.kernel import Ship, TaravObject, TypeRegistry, entity
from tarav.l1._future import FUTURE_WORKFLOW_SHIP, _FutureWorkflow, future
from tarav.l1._future.conversations import (
    AUTHOR, RECORD_TYPES, Annotation, Conversation, UserTurn,
)
from tarav.l1.records.registry import RecordRegistry


CHAT = Ship("c66bf4c8-0835-41f2-95bf-a6d10d07a01b")
TURN = Ship("0d141504-f49a-47d1-867c-7be5c6673922")


def test_workflow_owned_json_records_reload_through_normal_registry(tmp_path):
    records = TypeRegistry(TaravObject, RECORD_TYPES)
    store = RecordRegistry(tmp_path, records).for_workflow(_FutureWorkflow).create()
    original = UserTurn(TURN, CHAT, "alice", "Synthetic example message.")
    path = store.insert(str(TURN), original)
    assert path.parent.parent.name == str(FUTURE_WORKFLOW_SHIP)
    assert json.loads(path.read_text()) == {
        "type": "Tarav.Future.UserTurn", "id": str(TURN),
        "conversation": str(CHAT), "author": "alice", "text": "Synthetic example message.",
    }
    loaded = store.load(str(TURN))
    assert type(loaded) is UserTurn
    assert loaded.id == TURN
    assert loaded.read_text() == "Synthetic example message."
    assert loaded.records.to_record() == original.records.to_record()
    for cls in RECORD_TYPES:
        assert entity(cls).workflow_ship == FUTURE_WORKFLOW_SHIP


def test_experimental_records_keep_pydantic_validation():
    with pytest.raises(ValidationError):
        UserTurn.records.from_record({
            "type": "Tarav.Future.UserTurn", "id": str(TURN),
            "conversation": str(CHAT), "author": "alice", "text": 123,
        })
    with pytest.raises(ValidationError):
        Conversation.records.from_record({
            "type": "Tarav.Future.Conversation", "id": str(CHAT),
            "title": "Example", "turns": [], "unexpected": True,
        })


def test_member_identity_and_record_survive_a_path_rename():
    member = type(AUTHOR).records.from_record(AUTHOR.records.to_record())
    member.path = "speaker"
    assert member.id == AUTHOR.id
    assert member.records.to_record()["path"] == "speaker"
    assert member.owner == entity(UserTurn).id


def test_namespace_and_wrapper_bind_the_original_object():
    obj = Annotation(Ship("2c7ce946-1892-45e9-a270-d91c4be4c064"), TURN, "Synthetic note.")
    assert obj._future.obj is obj
    assert Annotation._future.obj is Annotation
    assert future(obj).obj is obj
    assert future(TaravObject).obj is TaravObject
    assert [node.path for node in UserTurn.Context(UserTurn).model_nodes()] == [
        "conversation", "author", "text", "read_text",
    ]
