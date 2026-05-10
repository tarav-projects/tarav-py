from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.gemini.session import (
    GeminiSession,
    GeminiSessionRef,
    discover_gemini_session_refs,
    load_gemini_session,
)


GEMINI_PROVIDER = "gemini-cli"


@dataclass(frozen=True)
class GeminiAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> GeminiAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=GEMINI_PROVIDER,
                agent_name="Gemini.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return GEMINI_PROVIDER

    def discover_session_refs(self) -> tuple[GeminiSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_gemini_session_refs(targets=direct_targets)

    def load_session(self, session_ref: GeminiSessionRef) -> GeminiSession:
        return load_gemini_session(session_ref)



__all__ = ["GeminiAgent"]
