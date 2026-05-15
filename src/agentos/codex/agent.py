from __future__ import annotations

from dataclasses import dataclass
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
)
from agentos.codex.session import (
    CodexSession,
    CodexSessionRef,
    discover_codex_session_refs,
    load_codex_session,
)
from agentos.codex.account_status import _codex_account_status_impl


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
        return self._build_command_with_env(
            effective_config,
            env_overrides=self._run_env_overrides(),
        )

    def account_status(
        self,
        *,
        record_usage: bool = True,
    ) -> AccountStatus:
        return _codex_account_status_impl(self, record_usage=record_usage)

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


__all__ = ["CodexAgent"]
