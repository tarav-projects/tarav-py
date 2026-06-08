from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from agentos._core.errors import CliError
from agentos.agent.account_status import AccountStatus, AgentAccountContext
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
from agentos.providers import ProviderHomeAnchor
from agentos.providers import require_canonical_provider_spec


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
    provider: str
    instance_id: str | None = None
    label: str | None = None
    home: Path | None = None
    cli_command: tuple[str, ...] = ()
    run_args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    account: AgentAccountContext | None = None
    account_policy: str = "open"
    timeout_sec: int | None = None
    default_model: str | None = None
    model_flag: str | None = None
    prompt_flag: str | None = None
    ping: AgentPingConfig = field(default_factory=default_agent_ping_config)
    is_default: bool = False
    fingerprint_override: str | None = None
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    identity_anchors: tuple[ProviderHomeAnchor, ...] = ()
    chatlas_includes: tuple[str, ...] = ()
    chatlas_excludes: tuple[str, ...] = ()

    def computed_fingerprint(self) -> str:
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
            self.instance_id,
            str(self.home) if self.home is not None else None,
            tuple(str(path) for path in self.direct_targets),
            tuple(str(path) for path in self.grep_targets),
            tuple(str(path) for path in self.sqlite_db_paths),
            self.cli_command,
            self.run_args,
            self.env,
            self.account,
            self.timeout_sec,
            self.default_model,
            self.model_flag,
            self.prompt_flag,
            self.ping,
            self.chatlas_includes,
            self.chatlas_excludes,
        )

    def uri_key(self) -> str:
        return quote(self.computed_fingerprint(), safe="")


@dataclass(frozen=True)
class AgentBase:
    instance_id: str | None = None
    label: str | None = None
    home: Path | None = None
    cli_command: tuple[str, ...] = ()
    run_args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    account: AgentAccountContext | None = None
    account_policy: str = "open"
    timeout_sec: int | None = None
    default_model: str | None = None
    model_flag: str | None = None
    prompt_flag: str | None = None
    ping: AgentPingConfig = field(default_factory=default_agent_ping_config)
    is_default: bool = False
    fingerprint_override: str | None = None
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    identity_anchors: tuple[ProviderHomeAnchor, ...] = ()
    chatlas_includes: tuple[str, ...] = ()
    chatlas_excludes: tuple[str, ...] = ()

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider": self.provider,
            "is_default": self.is_default,
        }
        if self.fingerprint_override is not None:
            payload["fingerprint"] = self.fingerprint_override
        if self.instance_id is not None:
            payload["instance_id"] = self.instance_id
        if self.label is not None:
            payload["label"] = self.label
        if self.home is not None:
            payload["home"] = str(self.home)
        if self.cli_command:
            payload["cli_command"] = list(self.cli_command)
        if self.run_args:
            payload["run_args"] = list(self.run_args)
        if self.env:
            payload["env"] = {key: value for key, value in self.env}
        if self.account is not None:
            payload["account"] = self.account.summary()
        if self.account_policy != "open":
            payload["account_policy"] = self.account_policy
        if self.timeout_sec is not None:
            payload["timeout_sec"] = self.timeout_sec
        if self.default_model is not None:
            payload["default_model"] = self.default_model
        if self.model_flag is not None:
            payload["model_flag"] = self.model_flag
        if self.prompt_flag is not None:
            payload["prompt_flag"] = self.prompt_flag
        if self.ping != default_agent_ping_config():
            payload["ping"] = self.ping.summary()
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
        if self.chatlas_includes:
            payload["chatlas_includes"] = list(self.chatlas_includes)
        if self.chatlas_excludes:
            payload["chatlas_excludes"] = list(self.chatlas_excludes)
        return payload

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
            self.instance_id,
            str(self.home) if self.home is not None else None,
            tuple(str(path) for path in self.direct_targets),
            tuple(str(path) for path in self.grep_targets),
            tuple(str(path) for path in self.sqlite_db_paths),
            self.cli_command,
            self.run_args,
            self.env,
            self.account,
            self.timeout_sec,
            self.default_model,
            self.model_flag,
            self.prompt_flag,
            self.ping,
            self.chatlas_includes,
            self.chatlas_excludes,
        )

    def uri_key(self) -> str:
        return quote(self.fingerprint(), safe="")

    def _build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        # Providers that do not support run must not override this — the raise is intentional.
        raise CliError(
            f"agent {self.instance_id or '<default>'} for provider {self.provider} does not support run"
        )

    def _build_command_with_env(
        self,
        command_config: AgentCommandConfig,
        *,
        env_overrides: dict[str, str],
    ) -> AgentCommand:
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
            env_overrides=env_overrides,
        )

    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult:
        self._check_account_policy(command_config)
        return execute_agent_command(
            self._build_command(command_config),
            run_config=self.resolve_run_config(run_config),
        )

    def run_dry(self, command_config: AgentCommandConfig) -> AgentRunDryResult:
        self._check_account_policy(command_config)
        command = self._build_command(command_config)
        return AgentRunDryResult(
            lines=(*command.setup_lines, format_agent_command(command)),
        )

    def _check_account_policy(self, command_config: AgentCommandConfig) -> None:
        if self.account_policy != "locked":
            return
        override = command_config.account.strip() if isinstance(command_config.account, str) else None
        if not override:
            return
        profile_id = self.instance_id or "<default>"
        bound = self.account.account if self.account is not None else None
        if bound is None:
            raise CliError(
                f"profile {profile_id} forbids --account override (no account bound)"
            )
        if override != bound:
            raise CliError(
                f"profile {profile_id} is locked to account {bound}; "
                f"cannot use --account {override}"
            )

    def resolve_run_config(self, run_config: AgentRunConfig) -> AgentRunConfig:
        if run_config.timeout_sec is not None or self.timeout_sec is None:
            return run_config
        return AgentRunConfig(
            cwd=run_config.cwd,
            process_mode=run_config.process_mode,
            timeout_sec=self.timeout_sec,
        )

    def account_status(
        self,
        *,
        record_usage: bool = True,
        fallback_to_usage_registry: bool = True,
    ) -> AccountStatus:
        del record_usage, fallback_to_usage_registry
        raise CliError(
            f"agent {self.instance_id or '<default>'} for provider {self.provider} "
            "does not support account_status"
        )


def agent_base_kwargs_from_config(config: AgentConfig) -> dict[str, object]:
    return {
        "instance_id": config.instance_id,
        "label": config.label,
        "home": config.home,
        "cli_command": config.cli_command,
        "run_args": config.run_args,
        "env": config.env,
        "account": config.account,
        "account_policy": config.account_policy,
        "timeout_sec": config.timeout_sec,
        "default_model": config.default_model,
        "model_flag": config.model_flag,
        "prompt_flag": config.prompt_flag,
        "ping": config.ping,
        "is_default": config.is_default,
        "fingerprint_override": config.fingerprint_override,
        "direct_targets": config.direct_targets,
        "grep_targets": config.grep_targets,
        "sqlite_db_paths": config.sqlite_db_paths,
        "identity_anchors": config.identity_anchors,
        "chatlas_includes": config.chatlas_includes,
        "chatlas_excludes": config.chatlas_excludes,
    }


def agent_base_kwargs_for_provider(
    config: AgentConfig,
    *,
    provider: str,
    agent_name: str,
) -> dict[str, object]:
    if config.provider != provider:
        raise CliError(f"cannot build {agent_name} from provider {config.provider}")
    return agent_base_kwargs_from_config(config)


class Agent(Protocol):
    provider: str
    instance_id: str | None
    label: str | None
    home: Path | None
    cli_command: tuple[str, ...]
    run_args: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    account: AgentAccountContext | None
    account_policy: str
    timeout_sec: int | None
    default_model: str | None
    model_flag: str | None
    prompt_flag: str | None
    ping: AgentPingConfig
    is_default: bool
    fingerprint_override: str | None
    direct_targets: tuple[Path, ...]
    grep_targets: tuple[Path, ...]
    sqlite_db_paths: tuple[Path, ...]
    identity_anchors: tuple[ProviderHomeAnchor, ...]
    chatlas_includes: tuple[str, ...]
    chatlas_excludes: tuple[str, ...]

    def summary(self) -> dict[str, object]: ...

    def fingerprint(self) -> str: ...

    def identity_key(self) -> tuple[object, ...]: ...

    def uri_key(self) -> str: ...

    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult: ...

    def run_dry(self, command_config: AgentCommandConfig) -> AgentRunDryResult: ...

    def account_status(
        self,
        *,
        record_usage: bool = True,
        fallback_to_usage_registry: bool = True,
    ) -> AccountStatus: ...


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


def agent_session_paths(agent: Agent) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
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
    "Agent",
    "AgentAccountContext",
    "AgentBase",
    "AgentConfig",
    "AgentPingConfig",
    "SessionSource",
    "agent_base_kwargs_for_provider",
    "agent_base_kwargs_from_config",
    "agent_identity_fingerprint",
    "default_agent_ping_config",
    "agent_session_paths",
    "provider_session_paths",
]
