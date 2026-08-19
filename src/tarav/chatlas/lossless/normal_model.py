# $kw: ^chatlas2-normal-model-provider --from Normalization.Pipeline::Chatlas.Session.Model --note [CT] consumers request Normal Model content through one cache-transparent provider while direct raw-attached computation remains an explicit diagnostic path --supp ^d20260816-17u
from __future__ import annotations

from pathlib import Path

from .cache import (
    NormalModelCacheReader,
    materialize_normal_model_cache,
    open_or_materialize_normal_model_cache,
)
from .model import JsonObject
from .pipeline import build_normal_model


def provide_normal_model_reader(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    chatlas_root: Path | None = None,
    refresh: bool = False,
) -> NormalModelCacheReader:
    """Return stream-readable compact content, rebuilding it when required."""
    provider = (
        materialize_normal_model_cache
        if refresh
        else open_or_materialize_normal_model_cache
    )
    return provider(
        session_id=session_id,
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
    )


def provide_normal_model(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    chatlas_root: Path | None = None,
    refresh: bool = False,
) -> JsonObject:
    """Return a complete compact model through the canonical cached path."""
    return provide_normal_model_reader(
        session_id=session_id,
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
        refresh=refresh,
    ).load_normal_model()


def compute_normal_model(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    chatlas_root: Path | None = None,
    include_raw: bool = False,
) -> JsonObject:
    """Compute directly for diagnostics without reading or writing the cache."""
    return build_normal_model(
        session_id=session_id,
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
        include_raw=include_raw,
    )


__all__ = [
    "compute_normal_model",
    "provide_normal_model",
    "provide_normal_model_reader",
]
