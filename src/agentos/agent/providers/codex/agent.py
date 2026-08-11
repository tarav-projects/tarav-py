# $kw: ^agentos-provider-codex-agent --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos.agent.account_status import AccountStatus
from agentos.agent.primitives import (
    AgentConfig,
    RunnableMixin,
    adapter_kwargs_from_config,
    agent_session_paths,
)
from agentos.agent.run_runtime import (
    AgentCommand,
    AgentCommandConfig,
    AgentRunConfig,
    AgentRunDryResult,
    AgentRunResult,
    CODEX_HOME_ENV_VAR,
    execute_agent_command,
    format_agent_command,
)
from agentos.agent.run_prepare import AgentRunPrepareRequest, AgentRunPrepareResult
from agentos.agent.providers.codex.session import (
    CodexSession,
    CodexSessionRef,
    discover_codex_session_refs,
    find_codex_session_ref_by_id,
    load_codex_session,
)
from agentos.agent.providers.codex.account_status import _codex_account_status_impl


CODEX_PROVIDER = "codex"


@dataclass(frozen=True)
class CodexAgent(RunnableMixin, AgentConfig):
    provider: str = CODEX_PROVIDER

    @classmethod
    def from_config(cls, config: AgentConfig) -> CodexAgent:
        return cls(
            **adapter_kwargs_from_config(
                config,
                provider=CODEX_PROVIDER,
                agent_name="Codex.Agent",
            )
        )

    def discover_session_refs(self) -> tuple[CodexSessionRef, ...]:
        return discover_codex_session_refs(targets=self.session_discovery_targets())

    def find_session_ref_by_id(self, session_id: str) -> CodexSessionRef | None:
        return find_codex_session_ref_by_id(
            targets=self.session_discovery_targets(),
            session_id=session_id,
        )

    def load_session(self, session_ref: CodexSessionRef) -> CodexSession:
        return load_codex_session(session_ref)

    def session_discovery_targets(self) -> tuple[Path, ...]:
        direct_targets, sqlite_db_paths = agent_session_paths(self)
        return direct_targets + sqlite_db_paths

    def _build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        effective_config = self._codex_command_config(command_config)
        return self._build_command_with_env(
            effective_config,
            env_overrides=self._run_env_overrides(),
        )

    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult:
        self._check_account_scope(command_config)
        start_path = run_config.cwd
        prepare_result = self.prepare_run(
            AgentRunPrepareRequest(
                agent=self,
                command_config=command_config,
                start_path=start_path,
                dry_run=False,
                source="agent.run",
            )
        )
        for line in prepare_result.preamble_lines:
            print(line)
        command = self._build_command(command_config)
        base_result = execute_agent_command(command, run_config=self.resolve_run_config(run_config))
        return AgentRunResult(
            exit_code=base_result.exit_code,
            stdout=base_result.stdout,
            stderr=base_result.stderr,
            preamble_lines=prepare_result.preamble_lines,
        )

    def run_dry(self, command_config: AgentCommandConfig) -> AgentRunDryResult:
        self._check_account_scope(command_config)
        prepare_result = self.prepare_run(
            AgentRunPrepareRequest(
                agent=self,
                command_config=command_config,
                start_path=Path.cwd().resolve(),
                dry_run=True,
                source="agent.run",
            )
        )
        command = self._build_command(command_config)
        return AgentRunDryResult(
            lines=(*prepare_result.preamble_lines, *command.setup_lines, format_agent_command(command)),
        )

    def prepare_run(
        self,
        request: AgentRunPrepareRequest,
    ) -> AgentRunPrepareResult:
        preamble_lines = prepare_codex_run(
            self,
            command_config=request.command_config,
            start_path=request.start_path,
            dry_run=request.dry_run,
            source=request.source,
        )
        return AgentRunPrepareResult(preamble_lines=preamble_lines)

    def account_status(
        self,
        *,
        record_usage: bool = True,
        fallback_to_usage_registry: bool = True,
    ) -> AccountStatus:
        return _codex_account_status_impl(
            self,
            record_usage=record_usage,
            fallback_to_usage_registry=fallback_to_usage_registry,
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
            credential_success_source=command_config.credential_success_source,
        )

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CODEX_HOME_ENV_VAR] = str(self.home)
        return env_overrides

def prepare_codex_run(
    agent: CodexAgent,
    *,
    command_config: AgentCommandConfig,
    start_path: Path,
    dry_run: bool,
    source: str,
) -> tuple[str, ...]:
    # The run surface is disconnected from the account/auth credential system
    # (Impl.Req 658): the run launches against the home as-is. Account-scope is
    # still checked by `_check_account_scope` (profile config). Re-integrating a
    # home-current credential check on the new model is a later redesign.
    return ()


def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["CodexAgent", "validate_profile"]
