from __future__ import annotations

from hashlib import sha256
import json


_SESSION_IDENTITY_SCHEMA = "tarav.chatlas.session-identity.v1"


def session_identity_hash(*, provider: str, instance: str, session_id: str) -> str:
    payload = {
        "schema": _SESSION_IDENTITY_SCHEMA,
        "provider": provider,
        "instance": instance,
        "session_id": session_id,
    }
    body = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(body.encode("utf-8")).hexdigest()


__all__ = ["session_identity_hash"]
