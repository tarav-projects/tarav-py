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
    execute_agent_run_command,
    format_agent_run_command,
)
from agentos._core.errors import CliError
from agentos.pi.session import (
    PiSession,
    PiSessionRef,
    discover_pi_session_refs,
    load_pi_session,
)


PI_PROVIDER = "pi"


@dataclass(frozen=True)
class PiAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> PiAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=PI_PROVIDER,
                agent_name="Pi.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return PI_PROVIDER

    def discover_session_refs(self) -> tuple[PiSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_pi_session_refs(targets=direct_targets)

    def load_session(self, session_ref: PiSessionRef) -> PiSession:
        return load_pi_session(session_ref)

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



__all__ = ["PiAgent"]
