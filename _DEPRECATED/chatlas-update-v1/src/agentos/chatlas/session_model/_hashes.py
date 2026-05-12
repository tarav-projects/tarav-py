from __future__ import annotations

import hashlib
import json
from typing import Any

_HASH_ALGORITHM = "sha256"
_SESSION_CONTENT_HASH_SCHEMA = "agentos.chatlas.session_content.v1"
_SESSION_IDENTITY_HASH_SCHEMA = "agentos.chatlas.session_identity.v1"


def _canonical_json_text(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonical_json_bytes(value: Any) -> bytes:
    return _canonical_json_text(value).encode("utf-8")


def _sha256_digest(data: bytes) -> str:
    return f"{_HASH_ALGORITHM}:{hashlib.sha256(data).hexdigest()}"


def _hash_json_payload(payload: Any) -> str:
    return _sha256_digest(_canonical_json_bytes(payload))


def _session_identity_hash(
    *,
    provider: str,
    provider_session_id: str,
) -> str:
    return _hash_json_payload(
        {
            "schema": _SESSION_IDENTITY_HASH_SCHEMA,
            "provider": provider,
            "provider_session_id": provider_session_id,
        }
    )


def _session_content_hash(*, events: list[dict[str, object]]) -> str:
    return _hash_json_payload(
        {
            "schema": _SESSION_CONTENT_HASH_SCHEMA,
            "events": events,
        }
    )
