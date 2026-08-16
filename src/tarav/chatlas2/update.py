# $kw: ^chatlas2-update --from Chatlas.Update.Pipeline --from Scan.Scope --from Raw.Archive --from Chatlas.Session.Index --note [CT] explicit Chatlas2 freshness performs one structural Provider.Home-to-archive/index delta pass before consumer reads and leaves Normal Model cache reconstruction to the canonical provider --supp ^d20260816-43u
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarav._core.errors import CliError
from tarav.chatlas.core import chatlas_update
from tarav.chatlas.index_query import select_one_chatlas_index_row

from .query import SUPPORTED_QUERY_PROVIDERS


@dataclass(frozen=True, slots=True)
class Chatlas2UpdateScope:
    providers: tuple[str, ...]
    session_ids: tuple[str, ...] = ()
    chatlas_root: Path | None = None


def chatlas2_update_scope(args: argparse.Namespace) -> Chatlas2UpdateScope:
    providers = _selected_providers(getattr(args, "providers", None))
    chatlas_root_value = getattr(args, "chatlas_root", None)
    chatlas_root = Path(chatlas_root_value) if chatlas_root_value else None
    session_id = getattr(args, "session_id", None)
    if isinstance(session_id, str) and session_id:
        return Chatlas2UpdateScope(
            providers=providers,
            session_ids=(session_id,),
            chatlas_root=chatlas_root,
        )
    identity_hash = getattr(args, "identity_hash", None)
    if isinstance(identity_hash, str) and identity_hash:
        resolved = _resolve_identity_scope(
            identity_hash,
            providers=providers,
            chatlas_root=chatlas_root,
        )
        if resolved is not None:
            return resolved
    return Chatlas2UpdateScope(providers=providers, chatlas_root=chatlas_root)


def update_chatlas2(
    scope: Chatlas2UpdateScope,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    return chatlas_update(
        providers=scope.providers,
        session_ids=scope.session_ids,
        chatlas_root=scope.chatlas_root,
        progress=progress,
    )


def _selected_providers(value: Any) -> tuple[str, ...]:
    if value is None:
        return SUPPORTED_QUERY_PROVIDERS
    providers = tuple(dict.fromkeys(str(provider) for provider in value))
    unsupported = sorted(set(providers) - set(SUPPORTED_QUERY_PROVIDERS))
    if unsupported:
        raise CliError(
            "Chatlas2 update supports only Codex and Claude Code providers"
        )
    return providers


def _resolve_identity_scope(
    identity_hash: str,
    *,
    providers: tuple[str, ...],
    chatlas_root: Path | None,
) -> Chatlas2UpdateScope | None:
    try:
        row = select_one_chatlas_index_row(
            command="chatlas2 --update",
            identity_hash=identity_hash,
            providers=providers,
            chatlas_root=chatlas_root,
        )
    except CliError:
        return None
    provider = row.get("provider")
    session_id = row.get("session_id")
    if not isinstance(provider, str) or provider not in providers:
        return None
    if not isinstance(session_id, str) or not session_id:
        return None
    return Chatlas2UpdateScope(
        providers=(provider,),
        session_ids=(session_id,),
        chatlas_root=chatlas_root,
    )


__all__ = [
    "Chatlas2UpdateScope",
    "chatlas2_update_scope",
    "update_chatlas2",
]
