# $kw: ^event-pattern-paths --from Chatlas.Query.Surface --note [EX] the SQLite event index is a disposable derived surface under the Chatlas dataset root ^c20260725-38u
from __future__ import annotations

from pathlib import Path


CHATLAS_DIRNAME = "chatlas"
CHAT_INDEX_SURFACES_ROOT = Path("session-index")
EVENT_QUERY_INDEX_PATH = Path("derived") / "event-pattern" / "events.sqlite3"
SESSION_INDEX_ROOT = Path("index") / "sessions"
SESSION_INDEX_DERIVATIONS_CACHE_DIR = Path("cache") / "session-index-derivations-v2"
CHATLAS_WORKSPACE_ROOT = Path("workspace")
INDEX_LINE_MANIFEST_ROOT = CHATLAS_WORKSPACE_ROOT / "index-line-manifests"


def default_chatlas_root() -> Path:
    return Path.home().expanduser().resolve() / "Documents" / CHATLAS_DIRNAME


__all__ = [
    "CHATLAS_DIRNAME",
    "CHAT_INDEX_SURFACES_ROOT",
    "CHATLAS_WORKSPACE_ROOT",
    "EVENT_QUERY_INDEX_PATH",
    "INDEX_LINE_MANIFEST_ROOT",
    "SESSION_INDEX_DERIVATIONS_CACHE_DIR",
    "SESSION_INDEX_ROOT",
    "default_chatlas_root",
]
