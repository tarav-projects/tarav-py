from __future__ import annotations

from dataclasses import dataclass
from agentos._core.errors import CliError
from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.agent.run_runtime import (
    AgentCommand,
    AgentCommandConfig,
)
from agentos.claude.session import (
    ClaudeSession,
    ClaudeSessionRef,
    discover_claude_session_refs,
    load_claude_session,
)


CLAUDE_PROVIDER = "claude-code"
CLAUDE_CONFIG_DIR_ENV_VAR = "CLAUDE_CONFIG_DIR"


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

    def build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        if command_config.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        return self._build_command_with_env(
            command_config,
            env_overrides=self._run_env_overrides(),
        )

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CLAUDE_CONFIG_DIR_ENV_VAR] = str(self.home)
        return env_overrides


__all__ = ["ClaudeAgent"]
