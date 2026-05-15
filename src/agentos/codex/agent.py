from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path

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
    AgentRunConfig,
    AgentRunDryResult,
    AgentRunResult,
    build_agent_command_argv,
    execute_agent_command,
    format_agent_command,
)
from agentos.codex.session import (
    CodexSession,
    CodexSessionRef,
    discover_codex_session_refs,
    load_codex_session,
)
from agentos.codex.account_status import codex_account_status


CODEX_PROVIDER = "codex"
CODEX_HOME_ENV_VAR = "CODEX_HOME"


@dataclass(frozen=True)
class CodexAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> CodexAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=CODEX_PROVIDER,
                agent_name="Codex.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return CODEX_PROVIDER

    def discover_session_refs(self) -> tuple[CodexSessionRef, ...]:
        return discover_codex_session_refs(targets=self.session_discovery_targets())

    def load_session(self, session_ref: CodexSessionRef) -> CodexSession:
        return load_codex_session(session_ref)

    def session_discovery_targets(self) -> tuple[Path, ...]:
        direct_targets, sqlite_db_paths = agent_session_paths(self)
        return direct_targets + sqlite_db_paths

    def build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        effective_config = self._codex_command_config(command_config)
        return AgentCommand(
            argv=build_agent_command_argv(
                effective_config,
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

    def account_status(
        self,
        *,
        refresh_usage: bool = False,
        methods: tuple[str, ...] | None = None,
        config: Mapping[str, object] | None = None,
    ) -> AccountStatus:
        return codex_account_status(
            self,
            refresh_usage=refresh_usage,
            methods=methods,
            config=config,
        )

    def _codex_command_config(self, command_config: AgentCommandConfig) -> AgentCommandConfig:
        if command_config.interaction_mode != "non_interactive":
            return command_config
        if command_config.prompt is None or command_config.argv:
            return command_config
        return AgentCommandConfig(
            prompt=None,
            argv=("exec", command_config.prompt),
            model=command_config.model,
            account=command_config.account,
            interaction_mode=command_config.interaction_mode,
        )

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CODEX_HOME_ENV_VAR] = str(self.home)
        return env_overrides

    def _run_config_with_timeout(self, run_config: AgentRunConfig) -> AgentRunConfig:
        if run_config.timeout_sec is not None or self.timeout_sec is None:
            return run_config
        return AgentRunConfig(
            cwd=run_config.cwd,
            process_mode=run_config.process_mode,
            timeout_sec=self.timeout_sec,
        )


__all__ = ["CodexAgent"]
