from __future__ import annotations

from copy import deepcopy
import gc
from pathlib import Path
import weakref

from tarav.chatlas2.anchory import (
    CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA,
    CHATLAS2_NAMESPACE,
    chatlas2_anchory_batch_preview,
    chatlas2_anchory_batch_register,
    chatlas2_anchory_preview,
    chatlas2_anchory_register,
    chatlas2_anchory_resolve,
    format_support_member_ref,
)
from tarav.chatlas2.message_ref import compute_chat_message_hash
from tarav.chatlas2.messages import chat_message_support_member


def _model() -> dict[str, object]:
    event = {
        "class": "User.Event",
        "event_address": "a" * 64,
        "event_hash": "b" * 64,
        "started_at": "2026-08-16T00:00:01Z",
    }
    message = {
        "class": "Chat.Message",
        "message_address": "c" * 64,
        "side": "user",
        "text": "Raw.Model.Version names should be arbitrary",
        "event_refs": [
            {
                "event_address": event["event_address"],
                "event_hash": event["event_hash"],
            }
        ],
    }
    message["message_hash"] = compute_chat_message_hash(message)
    return {
        "session": {"identity_hash": "d" * 64},
        "events": [event],
        "annotations": {"chat_messages": [message]},
    }


def _member_ref(model: dict[str, object]) -> str:
    message = model["annotations"]["chat_messages"][0]
    return format_support_member_ref(chat_message_support_member(model, message))


def test_preview_register_resolve_and_repeat_are_idempotent(tmp_path: Path) -> None:
    model = _model()
    member_ref = _member_ref(model)
    def load(_identity: str) -> dict[str, object]:
        return model
    line = "- [DF] Raw.Model.Version identifiers are opaque arbitrary names."

    preview = chatlas2_anchory_preview(
        members=(member_ref,),
        line_content=line,
        chatlas_root=tmp_path,
        model_loader=load,
    )
    assert preview["action"] == "mint"
    assert preview["record"]["relationships"]["support"]["members"] == [
        chat_message_support_member(
            model, model["annotations"]["chat_messages"][0]
        )
    ]

    first = chatlas2_anchory_register(
        members=(member_ref,),
        line_content=line,
        chatlas_root=tmp_path,
        model_loader=load,
    )
    second = chatlas2_anchory_register(
        members=(member_ref,),
        line_content=line,
        chatlas_root=tmp_path,
        model_loader=load,
    )
    assert first["action"] == "minted"
    assert second["action"] == "reused"
    assert first["anchor"] == second["anchor"]
    assert first["anchor"].startswith("d20260816-")
    assert first["record"]["schema"] == CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA
    assert first["namespace"] == CHATLAS2_NAMESPACE

    resolved = chatlas2_anchory_resolve(
        first["anchor"],
        chatlas_root=tmp_path,
        model_loader=load,
        radius=1,
    )
    assert resolved["members"][0]["standing"] == "MATCHED"
    assert resolved["members"][0]["text"] == (
        "Raw.Model.Version names should be arbitrary"
    )
    assert resolved["members"][0]["at_matches"] is True


def test_support_at_is_diagnostic_not_reference_identity(tmp_path: Path) -> None:
    model = _model()
    member_ref = _member_ref(model)
    line = "- [DF] Diagnostic time is redundant evidence."
    registered = chatlas2_anchory_register(
        members=(member_ref,),
        line_content=line,
        chatlas_root=tmp_path,
        model_loader=lambda _identity: model,
    )
    retimed = deepcopy(model)
    retimed["events"][0]["started_at"] = "2026-08-16T00:00:09Z"

    resolved = chatlas2_anchory_resolve(
        registered["anchor"],
        chatlas_root=tmp_path,
        model_loader=lambda _identity: retimed,
    )
    assert resolved["members"][0]["standing"] == "MATCHED"
    assert resolved["members"][0]["at_matches"] is False
    assert resolved["members"][0]["current_at"] == "2026-08-16T00:00:09Z"


def test_batch_preview_and_register_reuse_duplicate_meaning(tmp_path: Path) -> None:
    model = _model()
    member_ref = _member_ref(model)
    items = [
        {
            "client_id": "one",
            "line_content": "- [DF] One line.",
            "members": [member_ref],
        },
        {
            "client_id": "two",
            "line_content": "- [DF] One line.",
            "members": [member_ref],
        },
    ]
    def load(_identity: str) -> dict[str, object]:
        return model

    preview = chatlas2_anchory_batch_preview(
        items=items, chatlas_root=tmp_path, model_loader=load
    )
    assert preview["mint_count"] == 1
    assert preview["reuse_count"] == 1

    first = chatlas2_anchory_batch_register(
        items=items, chatlas_root=tmp_path, model_loader=load
    )
    assert first["minted_count"] == 1
    assert first["reused_count"] == 1
    assert first["items"][0]["anchor"] == first["items"][1]["anchor"]

    repeated = chatlas2_anchory_batch_register(
        items=items, chatlas_root=tmp_path, model_loader=load
    )
    assert repeated["minted_count"] == 0
    assert repeated["reused_count"] == 2


def test_multi_session_projection_releases_each_model_before_loading_next(
    tmp_path: Path,
) -> None:
    first = _model()
    second = deepcopy(first)
    second["session"]["identity_hash"] = "e" * 64
    second_event = second["events"][0]
    second_event["event_address"] = "1" * 64
    second_message = second["annotations"]["chat_messages"][0]
    second_message["message_address"] = "2" * 64
    second_message["event_refs"] = [
        {
            "event_address": second_event["event_address"],
            "event_hash": second_event["event_hash"],
        }
    ]
    second_message["message_hash"] = compute_chat_message_hash(second_message)
    templates = {
        first["session"]["identity_hash"]: first,
        second["session"]["identity_hash"]: second,
    }
    alive: list[weakref.ReferenceType[dict[str, object]]] = []

    class WeakModel(dict[str, object]):
        pass

    def load(identity: str) -> dict[str, object]:
        gc.collect()
        assert not any(reference() is not None for reference in alive)
        model = WeakModel(deepcopy(templates[identity]))
        alive.append(weakref.ref(model))
        return model

    preview = chatlas2_anchory_preview(
        members=(_member_ref(first), _member_ref(second)),
        line_content="- [DF] Two sessions can support one line.",
        chatlas_root=tmp_path,
        model_loader=load,
    )

    assert preview["action"] == "mint"
    assert len(preview["members"]) == 2
