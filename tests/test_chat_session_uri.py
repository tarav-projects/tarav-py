from __future__ import annotations

from tarav.l1.agent.sessions import _parse_chat_session_uri, current_chat_session_uri
from tarav.l1.chatlas.index_writer import _dedupe_versions, plain_index_version

LEGACY = "agentos://chat-session/codex/46626a3c/019fbfbd-6fa3"
CURRENT = "tarav://chat-session/codex/46626a3c/019fbfbd-6fa3"


def test_legacy_uris_are_rewritten_to_the_tarav_scheme() -> None:
    assert current_chat_session_uri(LEGACY) == CURRENT
    assert current_chat_session_uri(CURRENT) == CURRENT
    assert current_chat_session_uri("https://example.org/x") == "https://example.org/x"


def test_both_schemes_parse_to_the_same_session_query() -> None:
    current = _parse_chat_session_uri(CURRENT)

    assert current is not None
    assert (current.provider_family, current.adapter_fingerprint_prefix, current.session_id) == (
        "codex", "46626a3c", "019fbfbd-6fa3"
    )
    assert _parse_chat_session_uri(LEGACY) == current
    assert _parse_chat_session_uri("other://chat-session/codex/a/b") is None


def test_an_index_version_differing_only_by_scheme_is_one_version() -> None:
    row = {"identity_hash": "a" * 64, "session_id": "019fbfbd-6fa3", "uri": LEGACY}

    assert plain_index_version(row)["uri"] == CURRENT
    assert _dedupe_versions([row, {**row, "uri": CURRENT}]) == [{**row, "uri": CURRENT}]
