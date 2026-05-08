from __future__ import annotations


OPENCODE_CHATLAS_DEFAULT_INCLUDES = (
    "opencode.db",
    "opencode.db-wal",
    "storage/session_diff/*.json",
    "tool-output/tool_*",
)

OPENCODE_CHATLAS_DEFAULT_EXCLUDES = (
    "auth.json",
    "log/",
    "snapshot/",
    "opencode.db-shm",
    "storage/migration",
    "bin/",
)


__all__ = [
    "OPENCODE_CHATLAS_DEFAULT_EXCLUDES",
    "OPENCODE_CHATLAS_DEFAULT_INCLUDES",
]
