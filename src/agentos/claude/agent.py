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
    AgentRunDryResult,
    AgentRunRequest,
    AgentRunResult,
    build_agent_run_command,
    execute_agent_run_command,
    format_agent_run_command,
)
from agentos.agent.account_runtime import AccountStatsRequest, account_stats_config_for_provider
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

    def account_stats(self, request: AccountStatsRequest) -> dict[str, object]:
        from agentos.claude.accounts import claude_account_stats

        return claude_account_stats(
            self,
            AccountStatsRequest(
                refresh_usage=request.refresh_usage,
                config=account_stats_config_for_provider(request, self.provider),
            ),
        )

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        return execute_agent_run_command(
            self._run_command(request),
            cwd=request.cwd,
            env_overrides=self._run_env_overrides(),
        )

    def run_dry(self, request: AgentRunRequest) -> AgentRunDryResult:
        if request.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        command = self._run_command(request)
        return AgentRunDryResult(
            lines=(format_agent_run_command(command, env_overrides=self._run_env_overrides()),)
        )

    def _run_command(self, request: AgentRunRequest) -> tuple[str, ...]:
        return build_agent_run_command(
            request,
            instance_id=self.instance_id,
            provider=self.provider,
            cli_command=self.cli_command,
            run_args=self.run_args,
            default_model=self.default_model,
            model_flag=self.model_flag,
            prompt_flag=self.prompt_flag,
        )

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CLAUDE_CONFIG_DIR_ENV_VAR] = str(self.home)
        return env_overrides


__all__ = ["ClaudeAgent"]
