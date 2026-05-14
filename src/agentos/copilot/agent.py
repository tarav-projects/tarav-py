from __future__ import annotations

from dataclasses import dataclass

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


__all__ = ["CopilotAgent"]
