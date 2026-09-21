from __future__ import annotations

from pathlib import Path

from tarav.chatlas.session_resolver import resolve_session_index_row

from tarav.chatlas.normal_model_cache import (
    provide_normal_model_from_row,
    provide_normal_model_reader_from_row,
)
from .model import ChatlasNormalModel, JsonObject
from .pipeline import build_normal_model_from_row


def provide_normal_model(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    provider: str | None = None,
    instance: str | None = None,
    chatlas_root: Path | None = None,
    refresh: bool = False,
) -> JsonObject:
    row = resolve_session_index_row(
        session_id=session_id,
        identity_hash=identity_hash,
        provider=provider,
        instance=instance,
        chatlas_root=chatlas_root,
    )
    return provide_normal_model_from_row(
        row,
        chatlas_root=chatlas_root,
        refresh=refresh,
    )


def provide_normal_model_reader(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    provider: str | None = None,
    instance: str | None = None,
    chatlas_root: Path | None = None,
    refresh: bool = False,
) -> ChatlasNormalModel:
    row = resolve_session_index_row(
        session_id=session_id,
        identity_hash=identity_hash,
        provider=provider,
        instance=instance,
        chatlas_root=chatlas_root,
    )
    return provide_normal_model_reader_from_row(
        row,
        chatlas_root=chatlas_root,
        refresh=refresh,
    )


def compute_normal_model(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    provider: str | None = None,
    instance: str | None = None,
    chatlas_root: Path | None = None,
    include_raw: bool = False,
) -> JsonObject:
    row = resolve_session_index_row(
        session_id=session_id,
        identity_hash=identity_hash,
        provider=provider,
        instance=instance,
        chatlas_root=chatlas_root,
    )
    return build_normal_model_from_row(row, include_raw=include_raw)


__all__ = [
    "compute_normal_model",
    "provide_normal_model",
    "provide_normal_model_reader",
]
