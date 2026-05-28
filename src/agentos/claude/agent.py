from __future__ import annotations

from dataclasses import dataclass
from agentos._core.errors import CliError
from agentos.agent.account_status import AccountStatus
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
    find_claude_session_ref_by_id,
    load_claude_session,
)
from agentos.claude.account_status import _claude_account_status_impl


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

    def find_session_ref_by_id(self, session_id: str) -> ClaudeSessionRef | None:
        direct_targets, _ = agent_session_paths(self)
        return find_claude_session_ref_by_id(targets=direct_targets, session_id=session_id)

    def load_session(self, session_ref: ClaudeSessionRef) -> ClaudeSession:
        return load_claude_session(session_ref)

    def build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        if command_config.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        effective_config = self._claude_command_config(command_config)
        return self._build_command_with_env(
            effective_config,
            env_overrides=self._run_env_overrides(),
        )

    def _claude_command_config(self, command_config: AgentCommandConfig) -> AgentCommandConfig:
        if command_config.interaction_mode != "non_interactive":
            return command_config
        extra_argv = ("--dangerously-skip-permissions",)
        return AgentCommandConfig(
            prompt=command_config.prompt,
            argv=extra_argv + command_config.argv,
            model=command_config.model,
            account=command_config.account,
            interaction_mode=command_config.interaction_mode,
        )

    def account_status(
        self,
        *,
        record_usage: bool = True,
        fallback_to_usage_registry: bool = True,
    ) -> AccountStatus:
        return _claude_account_status_impl(
            self,
            record_usage=record_usage,
            fallback_to_usage_registry=fallback_to_usage_registry,
        )

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CLAUDE_CONFIG_DIR_ENV_VAR] = str(self.home)
        return env_overrides


__all__ = ["ClaudeAgent"]
