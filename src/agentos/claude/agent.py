from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.agent.account_runtime import AccountStatsRequest
from agentos.claude.session import (
    ClaudeSession,
    ClaudeSessionRef,
    discover_claude_session_refs,
    load_claude_session,
)


CLAUDE_PROVIDER = "claude-code"


@dataclass(frozen=True)
class ClaudeAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> ClaudeAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=CLAUDE_PROVIDER,
                agent_name="Claude.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return CLAUDE_PROVIDER

    def discover_session_refs(self) -> tuple[ClaudeSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_claude_session_refs(targets=direct_targets)

    def load_session(self, session_ref: ClaudeSessionRef) -> ClaudeSession:
        return load_claude_session(session_ref)

    def collect_account_stats(self, request: AccountStatsRequest) -> dict[str, object]:
        from agentos.claude.accounts import collect_claude_account_stats

        return collect_claude_account_stats(self, request)


__all__ = ["ClaudeAgent"]
