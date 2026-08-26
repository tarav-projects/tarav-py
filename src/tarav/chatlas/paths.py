from __future__ import annotations

from pathlib import Path


CHATLAS_DIRNAME = "chatlas"
SESSION_INDEX_ROOT = Path("index") / "sessions"
SESSION_INDEX_DERIVATIONS_CACHE_DIR = Path("cache") / "session-index-derivations-v2"


def default_chatlas_root() -> Path:
    return Path.home().expanduser().resolve() / "Documents" / CHATLAS_DIRNAME


__all__ = [
    "CHATLAS_DIRNAME",
    "SESSION_INDEX_DERIVATIONS_CACHE_DIR",
    "SESSION_INDEX_ROOT",
    "default_chatlas_root",
]
