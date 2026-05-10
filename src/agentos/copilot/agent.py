from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    AgentRunDryResult,
    AgentRunRequest,
    AgentRunResult,
    agent_base_kwargs_for_provider,
    agent_session_paths,
    execute_agent_run_command,
    format_agent_run_command,
)
from agentos.agent.account_runtime import AccountStatsRequest
from agentos._core.errors import CliError
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

    def collect_account_stats(self, request: AccountStatsRequest) -> dict[str, object]:
        from agentos.copilot.accounts import collect_copilot_account_stats

        return collect_copilot_account_stats(self, request)

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        return execute_agent_run_command(
            self._run_command(request),
            cwd=request.cwd,
            env_overrides=dict(self.env),
        )

    def run_dry(self, request: AgentRunRequest) -> AgentRunDryResult:
        if request.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        command = self._run_command(request)
        return AgentRunDryResult(
            lines=(format_agent_run_command(command, env_overrides=dict(self.env)),)
        )

    def _run_command(self, request: AgentRunRequest) -> tuple[str, ...]:
        if not self.cli_command:
            raise CliError(
                f"agent {self.instance_id or '<default>'} for provider {self.provider} has no cli_command"
            )
        command = [*self.cli_command, *self.run_args]
        effective_model = request.model or self.default_model
        if effective_model is not None:
            if self.model_flag is None:
                raise CliError(
                    f"agent {self.instance_id or '<default>'} for provider {self.provider} does not define model_flag"
                )
            command.extend([self.model_flag, effective_model])
        if self.prompt_flag is None:
            command.append(request.prompt)
        else:
            command.extend([self.prompt_flag, request.prompt])
        return tuple(command)


__all__ = ["CopilotAgent"]
