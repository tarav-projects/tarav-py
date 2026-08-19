from __future__ import annotations

from copy import deepcopy
import gc
from pathlib import Path
import weakref

import pytest

from tarav._core.errors import CliError
from tarav.chatlas.lossless import anchory
from tarav.chatlas.lossless.anchory import (
    CHATLAS2_MESSAGE_SUPPORT_SCHEMA,
    CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA,
    CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1,
    CHATLAS2_NAMESPACE,
    lossless_anchory_depot,
    lossless_message_support_register,
    lossless_anchory_batch_preview,
    lossless_anchory_batch_register,
    lossless_anchory_preview,
    lossless_anchory_register,
    lossless_anchory_resolve,
    format_support_member_ref,
)
from tarav.index_model import (
    INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
    index_line_anchor_triplet_hash,
)
from tarav.chatlas.lossless.message_ref import compute_chat_message_hash
from tarav.chatlas.lossless.messages import chat_message_support_member


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


def _review_model() -> dict[str, object]:
    model = _model()
    events = model["events"]
    messages = model["annotations"]["chat_messages"]
    events[0]["started_at"] = "2026-08-16T00:00:01Z"
    messages[0]["text"] = "The line should describe the grounding boundary."
    messages[0]["message_hash"] = compute_chat_message_hash(messages[0])
    for index, (side, text) in enumerate(
        (
            (
                "agent",
                "After · Verbatim:\n- [DC] Grounding remains a consumer concern.\n"
                "Approval: ::approve idx-edition:test",
            ),
            ("user", "::approve idx-edition:test"),
        ),
        start=2,
    ):
        event = {
            "class": "Agent.Event" if side == "agent" else "User.Event",
            "event_address": f"{index}" * 64,
            "event_hash": f"{index + 3}" * 64,
            "started_at": f"2026-08-16T00:00:0{index}Z",
        }
        message = {
            "class": "Chat.Message",
            "message_address": f"{index + 5}" * 64,
            "side": side,
            "text": text,
            "event_refs": [
                {
                    "event_address": event["event_address"],
                    "event_hash": event["event_hash"],
                }
            ],
        }
        message["message_hash"] = compute_chat_message_hash(message)
        events.append(event)
        messages.append(message)
    return model


def _message_ref(model: dict[str, object], index: int) -> str:
    message = model["annotations"]["chat_messages"][index]
    return format_support_member_ref(chat_message_support_member(model, message))


def test_preview_register_resolve_and_repeat_are_idempotent(tmp_path: Path) -> None:
    model = _model()
    member_ref = _member_ref(model)
    def load(_identity: str) -> dict[str, object]:
        return model
    line = "- [DF] Raw.Model.Version identifiers are opaque arbitrary names."

    preview = lossless_anchory_preview(
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

    first = lossless_anchory_register(
        members=(member_ref,),
        line_content=line,
        chatlas_root=tmp_path,
        model_loader=load,
    )
    second = lossless_anchory_register(
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

    resolved = lossless_anchory_resolve(
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


def test_v2_preview_can_scan_existing_v1_line_dossiers(tmp_path: Path) -> None:
    model = _model()
    old_anchor = "d20260816-1u"
    old_line = "- [DF] Existing v1 line."
    lossless_anchory_depot(tmp_path).register(
        {
            "app": "chatlas2",
            "schema": CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1,
            "attachment": {
                "canonical_schema": INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
                "triplet_hash": index_line_anchor_triplet_hash(old_line, old_anchor),
            },
            "relationships": {
                "support": {
                    "members": [
                        chat_message_support_member(
                            model, model["annotations"]["chat_messages"][0]
                        )
                    ]
                }
            },
        },
        anchor=old_anchor,
        namespace=CHATLAS2_NAMESPACE,
    )

    preview = lossless_anchory_preview(
        members=(_member_ref(model),),
        line_content="- [DF] New v2 line.",
        chatlas_root=tmp_path,
        model_loader=lambda _identity: model,
    )

    assert preview["action"] == "mint"
    assert preview["support_equivalent_anchors"] == [old_anchor]


def test_generic_message_support_anchor_has_no_line_attachment(tmp_path: Path) -> None:
    model = _model()
    result = lossless_message_support_register(
        members=(_member_ref(model),),
        chatlas_root=tmp_path,
        model_loader=lambda _identity: model,
    )

    assert result["action"] == "minted"
    assert result["record"] == {
        "app": "chatlas2",
        "schema": CHATLAS2_MESSAGE_SUPPORT_SCHEMA,
        "relationships": {
            "support": {
                "members": [
                    chat_message_support_member(
                        model, model["annotations"]["chat_messages"][0]
                    )
                ]
            }
        },
    }
    assert "attachment" not in result["record"]


def test_rich_line_dossier_keeps_support_gates_and_provenance_independent(
    tmp_path: Path,
) -> None:
    model = _review_model()
    result = lossless_anchory_register(
        members=(_message_ref(model, 0),),
        line_content="- [DC] Grounding remains a consumer concern.",
        gates={
            "tokenized_verbatim_approval": [
                {
                    "token": "idx-edition:test",
                    "proposal": _message_ref(model, 1),
                    "approval": _message_ref(model, 2),
                }
            ]
        },
        predecessors=("d20260816-1u",),
        issue_context=("Issue.I0001",),
        chatlas_root=tmp_path,
        model_loader=lambda _identity: model,
    )

    relationships = result["record"]["relationships"]
    assert set(relationships) == {"support", "gates", "provenance"}
    gate = relationships["gates"]["tokenized_verbatim_approval"][0]
    assert gate["token"] == "idx-edition:test"
    assert gate["proposal"]["message_address"] == (
        model["annotations"]["chat_messages"][1]["message_address"]
    )
    assert gate["approval"]["message_address"] == (
        model["annotations"]["chat_messages"][2]["message_address"]
    )
    assert relationships["provenance"] == {
        "predecessor_anchors": ["d20260816-1u"],
        "issue_context": ["Issue.I0001"],
    }


def test_gate_requires_agent_proposal_and_user_approval(tmp_path: Path) -> None:
    model = _review_model()
    with pytest.raises(CliError, match="proposal.*agent"):
        lossless_anchory_register(
            members=(_message_ref(model, 0),),
            line_content="- [DC] Grounding remains a consumer concern.",
            gates={
                "tokenized_verbatim_approval": [
                    {
                        "token": "idx-edition:test",
                        "proposal": _message_ref(model, 2),
                        "approval": _message_ref(model, 2),
                    }
                ]
            },
            chatlas_root=tmp_path,
            model_loader=lambda _identity: model,
        )


def test_support_at_is_diagnostic_not_reference_identity(tmp_path: Path) -> None:
    model = _model()
    member_ref = _member_ref(model)
    line = "- [DF] Diagnostic time is redundant evidence."
    registered = lossless_anchory_register(
        members=(member_ref,),
        line_content=line,
        chatlas_root=tmp_path,
        model_loader=lambda _identity: model,
    )
    retimed = deepcopy(model)
    retimed["events"][0]["started_at"] = "2026-08-16T00:00:09Z"

    resolved = lossless_anchory_resolve(
        registered["anchor"],
        chatlas_root=tmp_path,
        model_loader=lambda _identity: retimed,
    )
    assert resolved["members"][0]["standing"] == "MATCHED"
    assert resolved["members"][0]["at_matches"] is False
    assert resolved["members"][0]["current_at"] == "2026-08-16T00:00:09Z"


def test_default_model_source_is_the_canonical_provider(
    monkeypatch,
    tmp_path: Path,
) -> None:
    model = _model()
    calls: list[dict[str, object]] = []

    def provide(**kwargs) -> dict[str, object]:
        calls.append(kwargs)
        return model

    monkeypatch.setattr(anchory, "provide_normal_model", provide)

    preview = lossless_anchory_preview(
        members=(_member_ref(model),),
        line_content="- [DF] Anchory requests Normal Model content.",
        chatlas_root=tmp_path,
    )

    assert preview["action"] == "mint"
    assert calls == [
        {"identity_hash": "d" * 64, "chatlas_root": tmp_path},
        {"identity_hash": "d" * 64, "chatlas_root": tmp_path},
    ]


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

    preview = lossless_anchory_batch_preview(
        items=items, chatlas_root=tmp_path, model_loader=load
    )
    assert preview["mint_count"] == 1
    assert preview["reuse_count"] == 1

    first = lossless_anchory_batch_register(
        items=items, chatlas_root=tmp_path, model_loader=load
    )
    assert first["minted_count"] == 1
    assert first["reused_count"] == 1
    assert first["items"][0]["anchor"] == first["items"][1]["anchor"]

    repeated = lossless_anchory_batch_register(
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

    preview = lossless_anchory_preview(
        members=(_member_ref(first), _member_ref(second)),
        line_content="- [DF] Two sessions can support one line.",
        chatlas_root=tmp_path,
        model_loader=load,
    )

    assert preview["action"] == "mint"
    assert len(preview["members"]) == 2
