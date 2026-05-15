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
    AgentRunConfig,
    AgentRunDryResult,
    AgentRunResult,
    build_agent_command_argv,
    execute_agent_command,
    format_agent_command,
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
            env_overrides=self._run_env_overrides(),
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

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CLAUDE_CONFIG_DIR_ENV_VAR] = str(self.home)
        return env_overrides

    def _run_config_with_timeout(self, run_config: AgentRunConfig) -> AgentRunConfig:
        if run_config.timeout_sec is not None or self.timeout_sec is None:
            return run_config
        return AgentRunConfig(
            cwd=run_config.cwd,
            process_mode=run_config.process_mode,
            timeout_sec=self.timeout_sec,
        )


__all__ = ["ClaudeAgent"]
