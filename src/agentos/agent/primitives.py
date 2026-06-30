from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable
from urllib.parse import quote

if TYPE_CHECKING:
    from agentos.agent.ping import AgentPingResult
    from agentos.agent.profile_check import ProfileCheck

from agentos._core.errors import CliError
from agentos.agent.account_status import AccountStatus, AgentAccountContext
from agentos.agent.profile_scope import validate_account_override
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
from agentos.agent.run_prepare import (
    AgentRunPrepareRequest,
    AgentRunPrepareResult,
    empty_agent_run_prepare_result,
)
from agentos.providers import ProviderHomeAnchor
from agentos.providers import require_canonical_provider_spec

AgentConfigSelf = TypeVar("AgentConfigSelf", bound="AgentConfig")


@dataclass(frozen=True)
class SessionSource:
    role: str
    path: Path
    storage_kind: str | None = None
    locator: dict[str, object] | None = None

    def normalized_storage_kind(self) -> str:
        if self.storage_kind is not None:
            return self.storage_kind
        if self.path.is_dir():
            return "directory"
        return "file"

    def summary(self, *, extractable: bool) -> dict[str, object]:
        return {
            "role": self.role,
            "storage_kind": self.normalized_storage_kind(),
            "path": str(self.path),
            "locator": self.locator,
            "extractable": extractable,
        }


@dataclass(frozen=True)
class AgentPingConfig:
    enabled: bool = True
    prompt: str | None = "What is 423 + 322? Reply with only the number."
    argv: tuple[str, ...] = ()
    expected_number: int | None = 745
    model: str | None = None

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {"enabled": self.enabled}
        if self.prompt is not None:
            payload["prompt"] = self.prompt
        if self.argv:
            payload["argv"] = list(self.argv)
        if self.expected_number is not None:
            payload["expected_number"] = self.expected_number
        if self.model is not None:
            payload["model"] = self.model
        return payload


def default_agent_ping_config() -> AgentPingConfig:
    return AgentPingConfig()


@dataclass(frozen=True)
class AgentConfig:
    """Single field surface for every agent adapter.

    Provider adapters subclass this and override the ``provider`` default;
    capability behavior is added by ``RunnableMixin`` and provider methods,
    not by re-declaring these fields.
    """

    provider: str
    profile_id: str | None = None
    label: str | None = None
    home: Path | None = None
    homes: tuple[Path, ...] = ()
    cli_command: tuple[str, ...] = ()
    run_args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    account: AgentAccountContext | None = None
    accounts: tuple[AgentAccountContext, ...] = ()
    account_policy: str = "profile-default"
    timeout_sec: int | None = None
    default_model: str | None = None
    ping_config: AgentPingConfig = field(default_factory=default_agent_ping_config)
    is_default: bool = False
    fingerprint_override: str | None = None
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    identity_anchors: tuple[ProviderHomeAnchor, ...] = ()

    def fingerprint(self) -> str:
        if self.fingerprint_override is not None:
            return self.fingerprint_override
        return agent_identity_fingerprint(
            provider=self.provider,
            anchors=self.identity_anchors,
            direct_targets=self.direct_targets,
            sqlite_db_paths=self.sqlite_db_paths,
        )

    def identity_key(self) -> tuple[object, ...]:
        if self.identity_anchors:
            return (
                self.provider,
                tuple(anchor.identity_key() for anchor in self.identity_anchors),
            )
        return (
            self.provider,
            self.profile_id,
            str(self.home) if self.home is not None else None,
            tuple(str(home) for home in self.homes),
            tuple(str(path) for path in self.direct_targets),
            tuple(str(path) for path in self.grep_targets),
            tuple(str(path) for path in self.sqlite_db_paths),
            self.cli_command,
            self.run_args,
            self.env,
            self.account,
            self.accounts,
            self.account_policy,
            self.timeout_sec,
            self.default_model,
            self.ping_config,
        )

    def uri_key(self) -> str:
        return quote(self.fingerprint(), safe="")

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider": self.provider,
            "is_default": self.is_default,
        }
        if self.fingerprint_override is not None:
            payload["fingerprint"] = self.fingerprint_override
        if self.profile_id is not None:
            payload["profile_id"] = self.profile_id
        if self.label is not None:
            payload["label"] = self.label
        if self.home is not None:
            payload["home"] = str(self.home)
        if self.homes:
            payload["homes"] = [str(home) for home in self.homes]
        if self.cli_command:
            payload["cli_command"] = list(self.cli_command)
        if self.run_args:
            payload["run_args"] = list(self.run_args)
        if self.env:
            payload["env"] = {key: value for key, value in self.env}
        if self.account is not None:
            payload["account"] = self.account.summary()
        if self.accounts:
            payload["accounts"] = [account.summary() for account in self.accounts]
        if self.account_policy != "profile-default":
            payload["account_policy"] = self.account_policy
        if self.timeout_sec is not None:
            payload["timeout_sec"] = self.timeout_sec
        if self.default_model is not None:
            payload["default_model"] = self.default_model
        if self.ping_config != default_agent_ping_config():
            payload["ping"] = self.ping_config.summary()
        if self.direct_targets:
            payload["direct_targets"] = [str(path) for path in self.direct_targets]
        if self.grep_targets:
            payload["grep_targets"] = [str(path) for path in self.grep_targets]
        if self.sqlite_db_paths:
            payload["sqlite_db_paths"] = [str(path) for path in self.sqlite_db_paths]
        if self.identity_anchors:
            payload["identity_anchors"] = [
                anchor.summary() for anchor in self.identity_anchors
            ]
        return payload

    def with_session_discovery_paths(
        self: AgentConfigSelf,
        *,
        direct_targets: tuple[Path, ...],
        sqlite_db_paths: tuple[Path, ...],
    ) -> AgentConfigSelf:
        return replace(
            self,
            home=None,
            direct_targets=direct_targets,
            sqlite_db_paths=sqlite_db_paths,
        )


class RunnableMixin:
    """Run behavior shared by adapters that satisfy ``RunCapable``.

    Mixed into runnable provider adapters only. Each runnable adapter defines
    ``_build_command``; session-only adapters do not mix this in and therefore
    expose no ``run`` capability.
    """

    def _build_command_with_env(
        self,
        command_config: AgentCommandConfig,
        *,
        env_overrides: dict[str, str],
    ) -> AgentCommand:
        return AgentCommand(
            argv=build_agent_command_argv(
                command_config,
                provider=self.provider,
                cli_command=self.cli_command,
                run_args=self.run_args,
                default_model=self.default_model,
            ),
            env_overrides=env_overrides,
        )

    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult:
        self._check_account_scope(command_config)
        prepare_result = self.prepare_run(
            AgentRunPrepareRequest(
                agent=self,
                command_config=command_config,
                start_path=run_config.cwd,
                dry_run=False,
                source=command_config.credential_success_source or "agent.run",
            )
        )
        for line in prepare_result.preamble_lines:
            print(line)
        command = self._build_command(command_config)
        if prepare_result.env_overrides or prepare_result.env_display_overrides:
            from agentos.agent.run_runtime import agent_command_with_env_overrides

            command = agent_command_with_env_overrides(
                command,
                env_overrides=prepare_result.env_overrides,
                env_display_overrides=prepare_result.env_display_overrides,
            )
        result = execute_agent_command(
            command,
            run_config=self.resolve_run_config(run_config),
        )
        return AgentRunResult(
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
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
        if prepare_result.env_overrides or prepare_result.env_display_overrides:
            from agentos.agent.run_runtime import agent_command_with_env_overrides

            command = agent_command_with_env_overrides(
                command,
                env_overrides=prepare_result.env_overrides,
                env_display_overrides=prepare_result.env_display_overrides,
            )
        return AgentRunDryResult(
            lines=(*prepare_result.preamble_lines, *command.setup_lines, format_agent_command(command)),
        )

    def prepare_run(
        self,
        request: AgentRunPrepareRequest,
    ) -> AgentRunPrepareResult:
        return empty_agent_run_prepare_result()

    def _check_account_scope(self, command_config: AgentCommandConfig) -> None:
        validate_account_override(
            profile_id=self.profile_id or "<default>",
            allowed_accounts=self.accounts,
            account=command_config.account,
        )

    def resolve_run_config(self, run_config: AgentRunConfig) -> AgentRunConfig:
        if run_config.timeout_sec is not None or self.timeout_sec is None:
            return run_config
        return AgentRunConfig(
            cwd=run_config.cwd,
            process_mode=run_config.process_mode,
            timeout_sec=self.timeout_sec,
        )

    def ping(
        self,
        *,
        cwd: Path | None = None,
        model: str | None = None,
        account: str | None = None,
    ) -> AgentPingResult:
        # Local import avoids a cycle: `ping` imports this module for `RunCapable`.
        from agentos.agent.ping import _run_ping

        resolved_cwd = cwd if cwd is not None else Path.cwd().resolve()
        return _run_ping(self, cwd=resolved_cwd, model=model, account=account)

    def profile_check(self) -> ProfileCheck:
        # Local import avoids a cycle through account_status_report -> config.
        from agentos.agent.profile_check import _profile_check

        return _profile_check(self)


@runtime_checkable
class AgentAdapter(Protocol):
    """Smallest common adapter contract: identity and summary."""

    provider: str

    def fingerprint(self) -> str: ...

    def identity_key(self) -> tuple[object, ...]: ...

    def uri_key(self) -> str: ...

    def summary(self) -> dict[str, object]: ...


@runtime_checkable
class RunCapable(Protocol):
    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult: ...

    def run_dry(self, command_config: AgentCommandConfig) -> AgentRunDryResult: ...


@runtime_checkable
class PingCapable(Protocol):
    def ping(
        self,
        *,
        cwd: Path | None = ...,
        model: str | None = ...,
        account: str | None = ...,
    ) -> object: ...


@runtime_checkable
class ProfileCheckCapable(Protocol):
    def profile_check(self) -> object: ...


@runtime_checkable
class AccountStatusCapable(Protocol):
    def account_status(
        self,
        *,
        record_usage: bool = True,
        fallback_to_usage_registry: bool = True,
    ) -> AccountStatus: ...


@runtime_checkable
class SessionDiscoveryCapable(Protocol):
    def discover_session_refs(self) -> tuple[object, ...]: ...

    def load_session(self, session_ref: object) -> object: ...


def adapter_kwargs_from_config(
    config: AgentConfig,
    *,
    provider: str,
    agent_name: str,
) -> dict[str, object]:
    if config.provider != provider:
        raise CliError(f"cannot build {agent_name} from provider {config.provider}")
    return {f.name: getattr(config, f.name) for f in fields(AgentConfig)}


def provider_session_paths(
    provider: str,
    home: Path | None,
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    if home is None:
        return (), ()
    direct_targets: list[Path] = []
    sqlite_db_paths: list[Path] = []
    home_spec = require_canonical_provider_spec(provider).home_spec
    home_direct_targets, _, home_sqlite_db_paths = home_spec.build_paths(home=home)
    direct_targets.extend(home_direct_targets)
    sqlite_db_paths.extend(home_sqlite_db_paths)
    return tuple(direct_targets), tuple(sqlite_db_paths)


def agent_session_paths(agent: AgentConfig) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    direct_targets, sqlite_db_paths = provider_session_paths(agent.provider, agent.home)
    return (
        tuple(dict.fromkeys((*direct_targets, *agent.direct_targets))),
        tuple(dict.fromkeys((*sqlite_db_paths, *agent.sqlite_db_paths))),
    )


def agent_identity_fingerprint(
    *,
    provider: str,
    anchors: tuple[ProviderHomeAnchor, ...],
    direct_targets: tuple[Path, ...] = (),
    sqlite_db_paths: tuple[Path, ...] = (),
) -> str:
    digest = hashlib.sha256()
    digest.update(provider.encode("utf-8"))
    effective_anchors = anchors
    if not effective_anchors:
        effective_anchors = tuple(
            ProviderHomeAnchor(role=f"direct_target_{index + 1}", path=path)
            for index, path in enumerate(direct_targets)
        ) + tuple(
            ProviderHomeAnchor(role=f"sqlite_db_{index + 1}", path=path)
            for index, path in enumerate(sqlite_db_paths)
        )
    for anchor in effective_anchors:
        digest.update(b"\0")
        digest.update(anchor.role.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(anchor.path).encode("utf-8"))
    return digest.hexdigest()


__all__ = [
    "AccountStatusCapable",
    "AgentAccountContext",
    "AgentAdapter",
    "AgentConfig",
    "AgentPingConfig",
    "PingCapable",
    "ProfileCheckCapable",
    "RunCapable",
    "RunnableMixin",
    "SessionDiscoveryCapable",
    "SessionSource",
    "adapter_kwargs_from_config",
    "agent_identity_fingerprint",
    "default_agent_ping_config",
    "agent_session_paths",
    "provider_session_paths",
]
