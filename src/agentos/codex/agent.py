from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from agentos._core.errors import CliError
from agentos.codex.session import (
    CodexSession,
    CodexSessionRef,
    discover_codex_session_refs,
    load_codex_session,
)
from agentos.codex.linking import link_codex_auth_for_account, load_codex_mux_config


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

    def account_stats(self, request: AccountStatsRequest) -> dict[str, object]:
        from agentos.codex.accounts import codex_account_stats

        return codex_account_stats(
            self,
            AccountStatsRequest(
                refresh_usage=request.refresh_usage,
                config=account_stats_config_for_provider(request, self.provider),
            ),
        )

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        command = self._run_command(request)
        env_overrides = self._run_env_overrides()
        self._account_link_lines(request, mutate=True)
        return execute_agent_run_command(
            command,
            cwd=request.cwd,
            env_overrides=env_overrides,
        )

    def run_dry(self, request: AgentRunRequest) -> AgentRunDryResult:
        command = self._run_command(request)
        env_overrides = self._run_env_overrides()
        lines = [
            *self._account_link_lines(request, mutate=False),
            format_agent_run_command(command, env_overrides=env_overrides),
        ]
        return AgentRunDryResult(lines=tuple(lines))

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
            env_overrides[CODEX_HOME_ENV_VAR] = str(self.home)
        return env_overrides

    def _account_link_lines(self, request: AgentRunRequest, *, mutate: bool) -> tuple[str, ...]:
        if request.account is None:
            return ()
        if self.home is None:
            raise CliError("--account for provider codex requires a configured or explicit --home")
        source_auth, destination_auth = link_codex_auth_for_account(
            request.account,
            codex_home=self.home,
            config=load_codex_mux_config(),
            mutate=mutate,
        )
        if mutate:
            return ()
        return (f"link {destination_auth} -> {source_auth}",)

__all__ = ["CodexAgent"]
