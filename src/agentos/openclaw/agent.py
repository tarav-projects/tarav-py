from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.openclaw.session import (
    OpenclawSession,
    OpenclawSessionRef,
    discover_openclaw_session_refs,
    load_openclaw_session,
)


OPENCLAW_PROVIDER = "openclaw"


@dataclass(frozen=True)
class OpenclawAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> OpenclawAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=OPENCLAW_PROVIDER,
                agent_name="OpenClaw.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return OPENCLAW_PROVIDER

    def discover_session_refs(self) -> tuple[OpenclawSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_openclaw_session_refs(targets=direct_targets)

    def load_session(self, session_ref: OpenclawSessionRef) -> OpenclawSession:
        return load_openclaw_session(session_ref)



def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["OpenclawAgent", "validate_profile"]
