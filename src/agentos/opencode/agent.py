from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.opencode.session import (
    OpencodeSession,
    OpencodeSessionRef,
    discover_opencode_session_refs,
    load_opencode_session,
)


OPENCODE_PROVIDER = "opencode"


@dataclass(frozen=True)
class OpencodeAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> OpencodeAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=OPENCODE_PROVIDER,
                agent_name="OpenCode.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return OPENCODE_PROVIDER

    def discover_session_refs(self) -> tuple[OpencodeSessionRef, ...]:
        direct_targets, sqlite_db_paths = agent_session_paths(self)
        return discover_opencode_session_refs(
            targets=direct_targets,
            sqlite_db_paths=sqlite_db_paths,
        )

    def load_session(self, session_ref: OpencodeSessionRef) -> OpencodeSession:
        return load_opencode_session(session_ref)



__all__ = ["OpencodeAgent"]
