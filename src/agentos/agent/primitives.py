from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRunRequest:
    prompt: str
    model: str | None = None


@dataclass(frozen=True)
class ResolvedAgentRun:
    provider: str
    instance_id: str | None
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...]

    def env_mapping(self) -> dict[str, str]:
        return dict(self.env)


__all__ = [
    "AgentRunRequest",
    "ResolvedAgentRun",
]
