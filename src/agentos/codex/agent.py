from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
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
from agentos.codex.session import (
    CodexSession,
    CodexSessionRef,
    discover_codex_session_refs,
    find_codex_session_ref_by_id,
    load_codex_session,
)
from agentos.codex.account_status import _codex_account_status_impl


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
        if base_result.exit_code == 0 and command_config.credential_success_source is not None:
            self._refresh_auth_after_successful_run(
                command_config,
                source=command_config.credential_success_source,
                start_path=start_path,
            )
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

    def _refresh_auth_after_successful_run(
        self,
        command_config: AgentCommandConfig,
        *,
        source: str,
        start_path: Path,
    ) -> None:
        if self.home is None:
            return
        account = _normalized_account(command_config.account) or _agent_account(self)
        if account is None:
            status = _safe_inspect_codex_home(self.home)
            account = _active_home_account(status) if status is not None else None
        if account is None:
            return
        try:
            from agentos.codex.account_registry import promote_verified_codex_auth_from_home

            promote_verified_codex_auth_from_home(
                home=self.home,
                account=account,
                source=source,
                start_path=start_path,
            )
        except Exception:
            return


def prepare_codex_run(
    agent: CodexAgent,
    *,
    command_config: AgentCommandConfig,
    start_path: Path,
    dry_run: bool,
    source: str,
) -> tuple[str, ...]:
    # No auto-materialization: the run uses the home as-is. The only path that
    # writes a home is the explicit `agentos agent accounts materialize`
    # (`Capture.Over.Materialization`). The home-current policy still validates
    # that the home auth is usable and account-allowed (fail-fast, no mutation).
    if agent.home is None:
        return ()
    if command_config.account is None and agent.account_policy == "home-current":
        from agentos.codex.account_registry import inspect_codex_account_home

        status = inspect_codex_account_home(home=agent.home)
        _validate_home_current_codex_run(agent=agent, status=status)
    return ()


def _validate_home_current_codex_run(
    *,
    agent: CodexAgent,
    status: dict[str, object],
) -> None:
    classification = _status_classification(status)
    if classification == "missing":
        raise CliError(
            f"current codex home auth is missing for profile {agent.profile_id or '<default>'}"
        )
    if classification == "broken":
        error = _payload_string(status, "error")
        suffix = f": {error}" if error is not None else ""
        raise CliError(
            f"current codex home auth is broken for profile {agent.profile_id or '<default>'}{suffix}"
        )
    if classification == "unknown":
        raise CliError(
            f"current codex home auth is unknown for profile {agent.profile_id or '<default>'}"
        )

    account = _recognized_home_current_account(status)
    if account is None:
        raise CliError(
            f"current codex home auth is ambiguous for profile {agent.profile_id or '<default>'}"
        )
    _check_home_current_account_allowed(agent, account)


def _recognized_home_current_account(status: dict[str, object]) -> str | None:
    active_account = _active_home_account(status)
    if active_account is not None:
        return active_account
    classification = _status_classification(status)
    if classification not in {"registered", "known-account-new-hash"}:
        return None
    matches = status.get("account_registry_matches")
    if not isinstance(matches, list):
        return None
    accounts = sorted(
        account
        for record in matches
        if isinstance(record, dict)
        and (account := _payload_string(record, "account")) is not None
    )
    if len(accounts) == 1:
        return accounts[0]
    return None


def _check_home_current_account_allowed(agent: CodexAgent, account: str) -> None:
    allowed_accounts = sorted(
        allowed.account
        for allowed in agent.accounts
        if allowed.provider == agent.provider
    )
    if allowed_accounts and account not in allowed_accounts:
        raise CliError(
            f"current codex home auth account {account} is not allowed by profile "
            f"{agent.profile_id or '<default>'}"
        )


def _safe_inspect_codex_home(home: Path) -> dict[str, object] | None:
    try:
        from agentos.codex.account_registry import inspect_codex_account_home

        return inspect_codex_account_home(home=home)
    except Exception:
        return None


def _payload_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _active_home_account(status: dict[str, object]) -> str | None:
    if _status_classification(status) != "matching-active":
        return None
    matches = status.get("account_registry_matches")
    auth = status.get("auth")
    if not isinstance(matches, list) or not isinstance(auth, dict):
        return None
    artifact_id = _payload_string(auth, "artifact_id")
    accounts = sorted(
        account
        for record in matches
        if isinstance(record, dict)
        and record.get("active_artifact_id") == artifact_id
        and (account := _payload_string(record, "account")) is not None
    )
    if len(accounts) == 1:
        return accounts[0]
    return None


def _status_classification(status: dict[str, object]) -> str | None:
    value = status.get("classification")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _normalized_account(account: str | None) -> str | None:
    if account is None:
        return None
    normalized = account.strip()
    return normalized or None


def _agent_account(agent: CodexAgent) -> str | None:
    if agent.account is None:
        return None
    if agent.account.provider != agent.provider:
        return None
    return _normalized_account(agent.account.account)


def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["CodexAgent", "validate_profile"]
