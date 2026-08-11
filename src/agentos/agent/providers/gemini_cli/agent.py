# $kw: ^agentos-provider-gemini-cli-agent --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentConfig,
    adapter_kwargs_from_config,
    agent_session_paths,
)
from agentos.agent.providers.gemini_cli.session import (
    GeminiSession,
    GeminiSessionRef,
    discover_gemini_session_refs,
    load_gemini_session,
)


GEMINI_PROVIDER = "gemini-cli"


@dataclass(frozen=True)
class GeminiAgent(AgentConfig):
    provider: str = GEMINI_PROVIDER

    @classmethod
    def from_config(cls, config: AgentConfig) -> GeminiAgent:
        return cls(
            **adapter_kwargs_from_config(
                config,
                provider=GEMINI_PROVIDER,
                agent_name="Gemini.Agent",
            )
        )

    def discover_session_refs(self) -> tuple[GeminiSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_gemini_session_refs(targets=direct_targets)

    def load_session(self, session_ref: GeminiSessionRef) -> GeminiSession:
        return load_gemini_session(session_ref)



def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["GeminiAgent", "validate_profile"]
