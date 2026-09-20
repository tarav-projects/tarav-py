from __future__ import annotations

import json

import pytest

from tarav.chatlas.query import ChatlasQuery, ChatlasQueryResult, ChatlasTurnFinding
from tarav.chatlas.rendering import (
    DEFAULT_CHATLAS_RENDERER,
    INLINED_CAPTURE_MARKDOWN_RENDERER,
    TURN_LEDGER_RENDERER,
    ChatlasRenderer,
    ChatlasRendererRegistry,
    ChatlasRenderError,
    renderer,
)


def _result(
    *texts: str, started_at: str | None = "2026-09-05T09:27:11-04:00"
) -> ChatlasQueryResult:
    turn_hash = "a" * 64
    messages = tuple(
        {
            "type": "Chat.Message",
            "message_address": f"{index + 1:064x}",
            "message_hash": f"{index + 101:064x}",
            "side": "user",
            "text": text,
        }
        for index, text in enumerate(texts)
    )
    finding = ChatlasTurnFinding(
        turn_hash[:8],
        {
            "type": "Chat.Turn",
            "turn_address": "b" * 64,
            "turn_hash": turn_hash,
            "side": "user",
            "message_refs": [],
        },
        messages,
        started_at,
    )
    return ChatlasQueryResult(
        ChatlasQuery(turn_hash_prefixes=(turn_hash[:8],)),
        {
            "provider": "codex",
            "session_id": "session-one",
            "identity_hash": "c" * 64,
        },
        (finding,),
    )


def test_default_renderer_presents_every_message_in_one_turn() -> None:
    rendered = renderer(DEFAULT_CHATLAS_RENDERER).render(
        _result("first message", "second message")
    )

    assert rendered.media_type == "text/markdown"
    assert rendered.content == (
        "## User Turn `aaaaaaaa`\n\nfirst message\n\nsecond message"
    )
    assert "class" not in rendered.to_dict()["query_result"]


def test_renderer_registry_accepts_an_opaque_fully_qualified_name() -> None:
    registry = ChatlasRendererRegistry()
    custom = ChatlasRenderer(
        "workflow.phd.context.renderer",
        "text/plain",
        "Test renderer.",
        lambda result, options: f"{options['label']}:{len(result.findings)}",
    )

    registry.register(custom)

    assert (
        registry.renderer(custom.name)
        .render(_result("message"), options={"label": "selected"})
        .content
        == "selected:1"
    )


def test_renderer_registry_rejects_duplicate_and_unknown_names() -> None:
    registry = ChatlasRendererRegistry()
    custom = ChatlasRenderer("workflow.test.renderer", "text/plain", "", lambda *_: "")
    registry.register(custom)

    with pytest.raises(ChatlasRenderError, match="already registered"):
        registry.register(custom)
    with pytest.raises(ChatlasRenderError, match="not found"):
        registry.renderer("workflow.missing.renderer")


def test_render_result_json_retains_renderer_and_structured_findings() -> None:
    payload = renderer(DEFAULT_CHATLAS_RENDERER).render(_result("message")).to_dict()

    assert json.loads(json.dumps(payload))["renderer"] == DEFAULT_CHATLAS_RENDERER
    assert payload["query_result"]["findings"][0]["messages"][0]["text"] == "message"


def test_inlined_capture_markdown_renderer_derives_the_alias_from_the_session() -> None:
    rendered = renderer(INLINED_CAPTURE_MARKDOWN_RENDERER).render(_result("message"))

    assert rendered.media_type == "text/markdown"
    assert rendered.content == "<!-- tarav.context cccccccc:aaaaaaaaaaaaaaaa -->"


def test_inlined_capture_markdown_renderer_accepts_no_options() -> None:
    with pytest.raises(ChatlasRenderError, match="accepts no Renderer options"):
        renderer(INLINED_CAPTURE_MARKDOWN_RENDERER).render(
            _result("message"), options={"session-alias": "phd"}
        )


def test_inlined_capture_markdown_renderer_requires_a_session_identity_hash() -> None:
    result = _result("message")
    result.session["identity_hash"] = "not-a-hash"

    with pytest.raises(ChatlasRenderError, match="identity hash"):
        renderer(INLINED_CAPTURE_MARKDOWN_RENDERER).render(result)


def test_inlined_capture_markdown_renderer_rejects_agent_turns() -> None:
    result = _result("message")
    result.findings[0].turn["side"] = "agent"

    with pytest.raises(ChatlasRenderError, match="User Turns"):
        renderer(INLINED_CAPTURE_MARKDOWN_RENDERER).render(result)


def test_turn_ledger_renderer_compacts_message_text() -> None:
    rendered = renderer(TURN_LEDGER_RENDERER).render(
        _result("first\nmessage", "second message")
    )

    assert rendered.media_type == "text/plain"
    assert rendered.content == (
        "2026-09-05 13:27Z  aaaaaaaa  user   first message second message"
    )


def test_turn_ledger_renderer_marks_an_unavailable_time() -> None:
    rendered = renderer(TURN_LEDGER_RENDERER).render(
        _result("message", started_at=None)
    )

    assert rendered.content == "-  aaaaaaaa  user   message"
