from __future__ import annotations

from pathlib import Path

import pytest

from tarav.chatlas2.anchory import (
    CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1,
    CHATLAS2_NAMESPACE,
    chatlas2_anchory_depot,
    chatlas2_anchory_register,
    chatlas2_message_support_register,
    format_support_member_ref,
)
from tarav.chatlas2.grounding import (
    chatlas2_review_reference_resolver,
    chatlas2_support_reference_resolver,
)
from tarav.chatlas2.line_manifest import (
    create_chatlas2_line_relationship_projector,
)
from tarav.chatlas2.index_checks import grounding_provenance_check
from tarav.chatlas2.message_ref import compute_chat_message_hash
from tarav.chatlas2.messages import chat_message_support_member
from tarav.index.linter import build_linter_config, run_linter
from tarav.index_model import (
    INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
    index_line_anchor_triplet_hash,
)


def _model() -> dict[str, object]:
    events = []
    messages = []
    rows = (
        ("user", "Grounding is a consumer concern."),
        (
            "agent",
            "- [DC] Grounding remains a consumer concern.\n"
            "Approval: ::approve idx-edition:test",
        ),
        ("user", "::approve idx-edition:test"),
    )
    for index, (side, text) in enumerate(rows, start=1):
        event = {
            "class": "User.Event" if side == "user" else "Agent.Event",
            "event_address": f"{index}" * 64,
            "event_hash": f"{index + 3}" * 64,
            "started_at": f"2026-08-16T00:00:0{index}Z",
        }
        message = {
            "class": "Chat.Message",
            "message_address": f"{index + 6}" * 64,
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
    return {
        "session": {"identity_hash": "a" * 64},
        "events": events,
        "annotations": {"chat_messages": messages},
    }


def _ref(model: dict[str, object], index: int) -> str:
    message = model["annotations"]["chat_messages"][index]
    return format_support_member_ref(chat_message_support_member(model, message))


def _register(tmp_path: Path, model: dict[str, object]) -> str:
    result = chatlas2_anchory_register(
        members=(_ref(model, 0),),
        line_content="- [DC] Grounding remains a consumer concern.",
        gates={
            "tokenized_verbatim_approval": [
                {
                    "token": "idx-edition:test",
                    "proposal": _ref(model, 1),
                    "approval": _ref(model, 2),
                }
            ]
        },
        chatlas_root=tmp_path,
        model_loader=lambda _identity: model,
    )
    return str(result["anchor"])


def test_support_and_review_resolve_from_current_chat_messages(tmp_path: Path) -> None:
    model = _model()
    anchor = _register(tmp_path, model)
    support = chatlas2_support_reference_resolver(
        tmp_path, model_loader=lambda _identity: model
    )
    review = chatlas2_review_reference_resolver(
        tmp_path, model_loader=lambda _identity: model
    )

    assert support(anchor) is True
    assert review(anchor, "- [DC] Grounding remains a consumer concern.") is True
    assert review(anchor, "- [DC] A different decision.") is False


def test_generic_message_support_does_not_ground_an_index_line(tmp_path: Path) -> None:
    model = _model()
    anchor = chatlas2_message_support_register(
        members=(_ref(model, 0),),
        chatlas_root=tmp_path,
        model_loader=lambda _identity: model,
    )["anchor"]
    support = chatlas2_support_reference_resolver(
        tmp_path, model_loader=lambda _identity: model
    )

    assert support(anchor) is False


def test_grounding_linter_reads_existing_v1_line_dossier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    model = _model()
    anchor = "d20260816-1u"
    line = f"- [DC] Grounding remains a consumer concern. ^{anchor}"
    chatlas2_anchory_depot(tmp_path).register(
        {
            "app": "chatlas2",
            "schema": CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1,
            "attachment": {
                "canonical_schema": INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
                "triplet_hash": index_line_anchor_triplet_hash(line, anchor),
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
        anchor=anchor,
        namespace=CHATLAS2_NAMESPACE,
    )
    monkeypatch.setattr(
        "tarav.chatlas2.index_checks.provide_normal_model",
        lambda **_kwargs: model,
    )
    depot = tmp_path / "index"
    (depot / "design").mkdir(parents=True)
    (depot / "000-INDEX.md").write_text(
        "# Test Index\n\n## design\n\n- `design/100-design.md` — Test.Concept\n",
        encoding="utf-8",
    )
    (depot / "design" / "100-design.md").write_text(
        f"# Test.Concept\n\n{line}\n", encoding="utf-8"
    )
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(depot),), index_paths=(), appendix_paths=()
    )

    result = run_linter(
        config,
        raw_d,
        raw_i,
        raw_a,
        extra_checks=(grounding_provenance_check(tmp_path),),
    )

    assert not any(
        finding.code == "Index.Linter/Anchor.Turn.Missing"
        for finding in result.findings
    )


def test_stored_line_projection_uses_message_refs_without_loading_model(
    tmp_path: Path,
) -> None:
    model = _model()
    anchor = _register(tmp_path, model)
    projector = create_chatlas2_line_relationship_projector(
        chatlas_root=tmp_path,
        verification="stored",
        model_loader=lambda _identity: (_ for _ in ()).throw(
            AssertionError("stored projection must not load a model")
        ),
    )

    projection = projector(
        anchor, f"- [DC] Grounding remains a consumer concern. ^{anchor}"
    )

    support = projection["anchor"]["relationships"]["support"]["members"]
    assert support[0]["message"].startswith("a" * 64)
    assert support[0]["verification"] == "stored"
    assert projection["anchor"]["attachment"]["standing"] == "matched"
