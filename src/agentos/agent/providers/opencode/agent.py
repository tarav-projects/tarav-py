# $kw: ^agentos-provider-opencode-agent --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentConfig,
    adapter_kwargs_from_config,
    agent_session_paths,
)
from agentos.agent.providers.opencode.session import (
    OpencodeSession,
    OpencodeSessionRef,
    discover_opencode_session_refs,
    load_opencode_session,
)


OPENCODE_PROVIDER = "opencode"


@dataclass(frozen=True)
class OpencodeAgent(AgentConfig):
    provider: str = OPENCODE_PROVIDER

    @classmethod
    def from_config(cls, config: AgentConfig) -> OpencodeAgent:
        return cls(
            **adapter_kwargs_from_config(
                config,
                provider=OPENCODE_PROVIDER,
                agent_name="OpenCode.Agent",
            )
        )

    def discover_session_refs(self) -> tuple[OpencodeSessionRef, ...]:
        direct_targets, sqlite_db_paths = agent_session_paths(self)
        return discover_opencode_session_refs(
            targets=direct_targets,
            sqlite_db_paths=sqlite_db_paths,
        )

    def load_session(self, session_ref: OpencodeSessionRef) -> OpencodeSession:
        return load_opencode_session(session_ref)



def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["OpencodeAgent", "validate_profile"]
