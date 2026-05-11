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
    execute_agent_run_command,
    format_agent_run_command,
)
from agentos.agent.account_runtime import AccountStatsRequest
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

    def homes_map(self) -> dict[str, Path]:
        return {key: path for key, path in self.homes}

    def discover_session_refs(self) -> tuple[CodexSessionRef, ...]:
        return discover_codex_session_refs(targets=self.session_discovery_targets())

    def load_session(self, session_ref: CodexSessionRef) -> CodexSession:
        return load_codex_session(session_ref)

    def session_discovery_targets(self) -> tuple[Path, ...]:
        direct_targets, sqlite_db_paths = agent_session_paths(self)
        return direct_targets + sqlite_db_paths

    def collect_account_stats(self, request: AccountStatsRequest) -> dict[str, object]:
        from agentos.codex.accounts import collect_codex_account_stats

        return collect_codex_account_stats(self, request)

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
        if not self.cli_command:
            raise CliError(
                f"agent {self.instance_id or '<default>'} for provider {self.provider} has no cli_command"
            )

        if request.argv:
            if request.model is not None:
                raise CliError("--model is not supported with raw provider arguments after --")
            return (*self.cli_command, *request.argv)

        if request.prompt is None:
            raise CliError("--prompt is required when no raw provider arguments are supplied")

        command = [*self.cli_command, *self.run_args]
        effective_model = request.model or self.default_model
        if effective_model is not None:
            if self.model_flag is None:
                raise CliError(
                    f"agent {self.instance_id or '<default>'} for provider {self.provider} does not define model_flag"
                )
            command.extend([self.model_flag, effective_model])
        command.append(request.prompt)
        return tuple(command)

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        codex_home = self._single_home()
        if codex_home is not None:
            env_overrides[CODEX_HOME_ENV_VAR] = str(codex_home)
        return env_overrides

    def _account_link_lines(self, request: AgentRunRequest, *, mutate: bool) -> tuple[str, ...]:
        if request.account is None:
            return ()
        codex_home = self._single_home()
        if codex_home is None:
            raise CliError("--account for provider codex requires a configured or explicit --home")
        source_auth, destination_auth = link_codex_auth_for_account(
            request.account,
            codex_home=codex_home,
            config=load_codex_mux_config(),
            mutate=mutate,
        )
        if mutate:
            return ()
        return (f"link {destination_auth} -> {source_auth}",)

    def _single_home(self) -> Path | None:
        if not self.homes:
            return None
        homes = self.homes_map()
        if "home" in homes:
            return homes["home"]
        if len(self.homes) == 1:
            return self.homes[0][1]
        return None

__all__ = ["CodexAgent"]
