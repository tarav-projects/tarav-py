from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.agent.run_runtime import (
    AgentCommand,
    AgentCommandConfig,
    AgentRunConfig,
    AgentRunDryResult,
    AgentRunResult,
    build_agent_command_argv,
    execute_agent_command,
    format_agent_command,
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

    def build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        if command_config.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        return AgentCommand(
            argv=build_agent_command_argv(
                command_config,
                instance_id=self.instance_id,
                provider=self.provider,
                cli_command=self.cli_command,
                run_args=self.run_args,
                default_model=self.default_model,
                model_flag=self.model_flag,
                prompt_flag=self.prompt_flag,
            ),
            env_overrides=dict(self.env),
        )

    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult:
        return execute_agent_command(
            self.build_command(command_config),
            run_config=self._run_config_with_timeout(run_config),
        )

    def run_dry(self, command_config: AgentCommandConfig) -> AgentRunDryResult:
        command = self.build_command(command_config)
        return AgentRunDryResult(
            lines=(*command.setup_lines, format_agent_command(command)),
        )

    def _run_config_with_timeout(self, run_config: AgentRunConfig) -> AgentRunConfig:
        if run_config.timeout_sec is not None or self.timeout_sec is None:
            return run_config
        return AgentRunConfig(
            cwd=run_config.cwd,
            process_mode=run_config.process_mode,
            timeout_sec=self.timeout_sec,
        )


__all__ = ["CopilotAgent"]
