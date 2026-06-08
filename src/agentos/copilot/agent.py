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
)
from agentos._core.errors import CliError
from agentos.agent.account_status import AccountStatus
from agentos.copilot.session import (
    CopilotSession,
    CopilotSessionRef,
    discover_copilot_session_refs,
    find_copilot_session_ref_by_id,
    load_copilot_session,
)
from agentos.copilot.account_status import _copilot_account_status_impl


COPILOT_PROVIDER = "copilot-cli"
COPILOT_HOME_ENV_VAR = "COPILOT_HOME"


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

    def find_session_ref_by_id(self, session_id: str) -> CopilotSessionRef | None:
        direct_targets, _ = agent_session_paths(self)
        return find_copilot_session_ref_by_id(targets=direct_targets, session_id=session_id)

    def load_session(self, session_ref: CopilotSessionRef) -> CopilotSession:
        return load_copilot_session(session_ref)

    def _build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        if command_config.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        return self._build_command_with_env(
            command_config,
            env_overrides=self._run_env_overrides(),
        )

    def account_status(
        self,
        *,
        record_usage: bool = True,
        fallback_to_usage_registry: bool = True,
    ) -> AccountStatus:
        return _copilot_account_status_impl(
            self,
            record_usage=record_usage,
            fallback_to_usage_registry=fallback_to_usage_registry,
        )

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[COPILOT_HOME_ENV_VAR] = str(self.home)
        return env_overrides


def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["CopilotAgent", "validate_profile"]
