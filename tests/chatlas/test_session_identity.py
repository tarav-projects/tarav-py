from __future__ import annotations

from tarav.chatlas.session_identity import session_identity_hash


def test_session_identity_includes_provider_instance() -> None:
    first = session_identity_hash(
        provider="codex", instance="primary", session_id="same-native-id"
    )
    second = session_identity_hash(
        provider="codex", instance="secondary", session_id="same-native-id"
    )

    assert first != second
    assert len(first) == len(second) == 64
