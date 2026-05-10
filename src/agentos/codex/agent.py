from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.codex.session import (
    CodexSession,
    CodexSessionRef,
    discover_codex_session_refs,
    load_codex_session,
)


CODEX_PROVIDER = "codex"


@dataclass(frozen=True)
class CodexAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> CodexAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=CODEX_PROVIDER,
                agent_name="Codex.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return CODEX_PROVIDER

    def homes_map(self) -> dict[str, Path]:
        return {key: path for key, path in self.homes}

    def discover_session_refs(self) -> tuple[CodexSessionRef, ...]:
        return discover_codex_session_refs(targets=self.session_discovery_targets())

    def load_session(self, session_ref: CodexSessionRef) -> CodexSession:
        return load_codex_session(session_ref)

    def session_discovery_targets(self) -> tuple[Path, ...]:
        direct_targets, sqlite_db_paths = agent_session_paths(self)
        return direct_targets + sqlite_db_paths

__all__ = ["CodexAgent"]
