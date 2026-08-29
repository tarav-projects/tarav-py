from __future__ import annotations

from pathlib import Path

from tarav._core.data_root import default_tarav_data_root


CHATLAS_DIRNAME = "chatlas"
SESSION_INDEX_ROOT = Path("index") / "sessions"
SESSION_INDEX_DERIVATIONS_CACHE_DIR = Path("cache") / "session-index-derivations-v2"


def default_chatlas_root() -> Path:
    return default_tarav_data_root() / CHATLAS_DIRNAME


__all__ = [
    "CHATLAS_DIRNAME",
    "SESSION_INDEX_DERIVATIONS_CACHE_DIR",
    "SESSION_INDEX_ROOT",
    "default_chatlas_root",
]
