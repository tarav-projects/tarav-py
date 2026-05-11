from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentLinkRequest:
    provider: str
    home: Path
    account: str


@dataclass(frozen=True)
class AgentLinkResult:
    exit_code: int = 0


@dataclass(frozen=True)
class AgentLinkDryResult:
    lines: tuple[str, ...]


__all__ = [
    "AgentLinkDryResult",
    "AgentLinkRequest",
    "AgentLinkResult",
]
