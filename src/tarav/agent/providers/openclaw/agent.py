# $kw: ^agentos-provider-openclaw-agent --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

from dataclasses import dataclass

from tarav.agent.primitives import (
    AgentConfig,
    adapter_kwargs_from_config,
    agent_session_paths,
)
from tarav.agent.providers.openclaw.session import (
    OpenclawSession,
    OpenclawSessionRef,
    discover_openclaw_session_refs,
    load_openclaw_session,
)


OPENCLAW_PROVIDER = "openclaw"


@dataclass(frozen=True)
class OpenclawAgent(AgentConfig):
    provider: str = OPENCLAW_PROVIDER

    @classmethod
    def from_config(cls, config: AgentConfig) -> OpenclawAgent:
        return cls(
            **adapter_kwargs_from_config(
                config,
                provider=OPENCLAW_PROVIDER,
                agent_name="OpenClaw.Agent",
            )
        )

    def discover_session_refs(self) -> tuple[OpenclawSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_openclaw_session_refs(targets=direct_targets)

    def load_session(self, session_ref: OpenclawSessionRef) -> OpenclawSession:
        return load_openclaw_session(session_ref)



def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["OpenclawAgent", "validate_profile"]
