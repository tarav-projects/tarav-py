from __future__ import annotations

import hashlib

import pytest

from agentos.chatlas.session_model._hashes import (
    _canonical_json_bytes,
    _canonical_json_text,
    _hash_json_payload,
    _session_content_hash,
    _session_identity_hash,
    _sha256_digest,
)


def test_chatlas_session_hash_canonical_json_is_stable_for_key_order() -> None:
    left = {
        "schema": "agentos.chatlas.session_identity.v1",
        "provider_session_id": "session-1",
        "provider": "codex",
    }
    right = {
        "provider": "codex",
        "provider_session_id": "session-1",
        "schema": "agentos.chatlas.session_identity.v1",
    }

    assert _canonical_json_text(left) == _canonical_json_text(right)
    assert _canonical_json_bytes(left) == _canonical_json_bytes(right)
    assert _hash_json_payload(left) == _hash_json_payload(right)


def test_chatlas_session_hash_canonical_json_uses_compact_utf8() -> None:
    payload = {
        "schema": "agentos.chatlas.session_identity.v1",
        "provider": "claude-code",
        "provider_session_id": "sesion-\u00f1",
    }

    assert (
        _canonical_json_text(payload)
        == (
            '{"provider":"claude-code","provider_session_id":"sesion-\u00f1",'
            '"schema":"agentos.chatlas.session_identity.v1"}'
        )
    )
    assert _canonical_json_bytes(payload) == _canonical_json_text(payload).encode(
        "utf-8"
    )


def test_chatlas_session_hash_digest_format_is_sha256_prefixed() -> None:
    data = b'{"provider":"codex","provider_session_id":"session-1"}'

    assert _sha256_digest(data) == f"sha256:{hashlib.sha256(data).hexdigest()}"


def test_chatlas_session_hash_payload_rejects_non_json_numbers() -> None:
    with pytest.raises(ValueError):
        _hash_json_payload({"bad": float("nan")})


def test_chatlas_session_identity_hash_ignores_provider_instance() -> None:
    first = _session_identity_hash(
        provider="codex",
        provider_session_id="session-1",
    )
    second = _hash_json_payload(
        {
            "schema": "agentos.chatlas.session_identity.v1",
            "provider": "codex",
            "provider_session_id": "session-1",
        }
    )

    assert first == second


def test_chatlas_session_content_hash_tracks_events_only() -> None:
    events = [
        {
            "event_id": "event-1",
            "sequence": 1,
            "kind": "message",
            "payload": {"role": "user", "content": "hello"},
        }
    ]

    original = _session_content_hash(events=events)
    changed = _session_content_hash(
        events=[
            {
                "event_id": "event-1",
                "sequence": 1,
                "kind": "message",
                "payload": {"role": "user", "content": "changed"},
            }
        ]
    )

    assert original != changed
