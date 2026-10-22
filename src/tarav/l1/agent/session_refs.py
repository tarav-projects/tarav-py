from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarav.l1.agent.primitives import SessionSource
from tarav.l1.agent.providers.claude_code.session import ClaudeSessionRef
from tarav.l1.agent.providers.codex.session import CodexSessionRef
from tarav.l1.agent.providers.copilot_cli.session import CopilotSessionRef


ProviderSessionRef = (
    ClaudeSessionRef
    | CodexSessionRef
    | CopilotSessionRef
)


def _build_path_finding(
    *,
    provider: str,
    path: Path,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "strategy": "path",
        "match_kind": "directory" if path.is_dir() else "file",
        "path": str(path),
    }


@dataclass(frozen=True)
class BackingArtifact:
    role: str
    path: Path
    storage_kind: str | None = None
    locator: dict[str, Any] | None = None

    @classmethod
    def from_source(cls, source: SessionSource) -> "BackingArtifact":
        return cls(
            role=source.role,
            path=source.path,
            storage_kind=source.storage_kind,
            locator=source.locator,
        )

    def normalized_storage_kind(self) -> str:
        if self.storage_kind is not None:
            return self.storage_kind
        if self.path.is_dir():
            return "directory"
        return "file"

    def summary(self, *, extractable: bool) -> dict[str, Any]:
        return {
            "role": self.role,
            "storage_kind": self.normalized_storage_kind(),
            "path": str(self.path),
            "locator": self.locator,
            "extractable": extractable,
        }


def backing_artifacts_from_sources(sources: tuple[SessionSource, ...]) -> tuple[BackingArtifact, ...]:
    return tuple(
        BackingArtifact.from_source(source)
        for source in sources
    )


__all__ = [
    "BackingArtifact",
    "ProviderSessionRef",
    "_build_path_finding",
    "backing_artifacts_from_sources",
]
