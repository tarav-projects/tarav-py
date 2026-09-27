from __future__ import annotations

from pathlib import Path
from typing import Any

from tarav.l0._core.errors import CliError
from tarav.chatlas.index_store import load_chatlas_session_index_rows


def resolve_session_index_row(
    *,
    identity_hash: str | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    instance: str | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, Any]:
    if identity_hash is None and session_id is None:
        raise CliError("session resolution requires --identity-hash or --session-id")

    index = load_chatlas_session_index_rows(
        chatlas_root=chatlas_root,
        identity_hash=identity_hash,
        providers=(provider,) if provider is not None else None,
    )
    matches = [
        row
        for row in index.rows
        if _matches(
            row,
            identity_hash=identity_hash,
            session_id=session_id,
            provider=provider,
            instance=instance,
        )
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise CliError("no indexed Chatlas session matched the exact reference")
    raise CliError("multiple indexed Chatlas sessions matched the exact reference")


def _matches(
    row: dict[str, Any],
    *,
    identity_hash: str | None,
    session_id: str | None,
    provider: str | None,
    instance: str | None,
) -> bool:
    return all(
        (
            identity_hash is None or row.get("identity_hash") == identity_hash,
            session_id is None or row.get("session_id") == session_id,
            provider is None or row.get("provider") == provider,
            instance is None or row.get("instance") == instance,
        )
    )


__all__ = ["resolve_session_index_row"]
