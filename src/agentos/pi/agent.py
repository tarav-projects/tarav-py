from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.pi.session import (
    PiSession,
    PiSessionRef,
    discover_pi_session_refs,
    load_pi_session,
)


PI_PROVIDER = "pi"


@dataclass(frozen=True)
class PiAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> PiAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=PI_PROVIDER,
                agent_name="Pi.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return PI_PROVIDER

    def discover_session_refs(self) -> tuple[PiSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_pi_session_refs(targets=direct_targets)

    def load_session(self, session_ref: PiSessionRef) -> PiSession:
        return load_pi_session(session_ref)



__all__ = ["PiAgent"]
