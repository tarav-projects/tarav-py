from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


CODEX_CHATLAS_DEFAULT_INCLUDES = (
    "sessions/**/*.jsonl",
    "archived_sessions/**/*.jsonl",
    "session_index.jsonl",
    "history.jsonl",
    "AGENTS.md",
    "rules/*.rules",
)

CODEX_CHATLAS_DEFAULT_EXCLUDES = (
    "log/",
    "vendor_imports/",
    "worktrees/",
    "shell_snapshots/",
    "models_cache.json",
    "sqlite/",
    "tmp/",
    "auth.json",
    "skills",
)


@dataclass(frozen=True)
class CodexAgentChatlas:
    instance_id: str | None
    homes: tuple[tuple[str, Path], ...]
    includes: tuple[str, ...]
    excludes: tuple[str, ...]

    @classmethod
    def from_archive_config(cls, config: Any) -> CodexAgentChatlas:
        if config.family != "codex":
            raise ValueError(f"cannot build Codex.Agent.Chatlas from provider {config.family}")
        return cls(
            instance_id=config.instance_id,
            homes=config.homes,
            includes=_unique_strings(CODEX_CHATLAS_DEFAULT_INCLUDES + config.includes),
            excludes=_unique_strings(
                CODEX_CHATLAS_DEFAULT_EXCLUDES
                + config.excludes
                + _derived_codex_chatlas_excludes(config.homes)
            ),
        )


def _derived_codex_chatlas_excludes(
    homes: tuple[tuple[str, Path], ...],
) -> tuple[str, ...]:
    del homes
    return ("_auth*.json",)


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)


__all__ = [
    "CODEX_CHATLAS_DEFAULT_EXCLUDES",
    "CODEX_CHATLAS_DEFAULT_INCLUDES",
    "CodexAgentChatlas",
]
