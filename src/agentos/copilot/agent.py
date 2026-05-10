from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.copilot.session import (
    CopilotSession,
    CopilotSessionRef,
    discover_copilot_session_refs,
    load_copilot_session,
)


COPILOT_PROVIDER = "copilot-cli"


@dataclass(frozen=True)
class CopilotAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> CopilotAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=COPILOT_PROVIDER,
                agent_name="Copilot.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return COPILOT_PROVIDER

    def discover_session_refs(self) -> tuple[CopilotSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_copilot_session_refs(targets=direct_targets)

    def load_session(self, session_ref: CopilotSessionRef) -> CopilotSession:
        return load_copilot_session(session_ref)



__all__ = ["CopilotAgent"]
