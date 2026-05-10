from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from agentos._core.errors import CliError
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
class AgentRunRequest:
    prompt: str
    model: str | None
    cwd: Path
    account: str | None = None


@dataclass(frozen=True)
class AgentRunResult:
    exit_code: int


@dataclass(frozen=True)
class AgentRunDryResult:
    lines: tuple[str, ...]


@dataclass(frozen=True)
class AgentConfig:
    provider: str
    instance_id: str | None = None
    label: str | None = None
    homes: tuple[tuple[str, Path], ...] = ()
    cli_command: tuple[str, ...] = ()
    run_args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    timeout_sec: int | None = None
    default_model: str | None = None
    model_flag: str | None = None
    prompt_flag: str | None = None
    is_default: bool = False
    fingerprint: str | None = None
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    identity_anchors: tuple[ProviderHomeAnchor, ...] = ()
    chatlas_includes: tuple[str, ...] = ()
    chatlas_excludes: tuple[str, ...] = ()
    account_live_usage_refresh: bool | None = None
    account_usage_progression_limit: str | None = None

    def computed_fingerprint(self) -> str:
        if self.fingerprint is not None:
            return self.fingerprint
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
            tuple((key, str(path)) for key, path in self.homes),
            tuple(str(path) for path in self.direct_targets),
            tuple(str(path) for path in self.grep_targets),
            tuple(str(path) for path in self.sqlite_db_paths),
            self.cli_command,
            self.run_args,
            self.env,
            self.timeout_sec,
            self.default_model,
            self.model_flag,
            self.prompt_flag,
            self.chatlas_includes,
            self.chatlas_excludes,
            self.account_live_usage_refresh,
            self.account_usage_progression_limit,
        )

    def uri_key(self) -> str:
        return quote(self.computed_fingerprint(), safe="")


@dataclass(frozen=True)
class AgentBase:
    instance_id: str | None = None
    label: str | None = None
    homes: tuple[tuple[str, Path], ...] = ()
    cli_command: tuple[str, ...] = ()
    run_args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    timeout_sec: int | None = None
    default_model: str | None = None
    model_flag: str | None = None
    prompt_flag: str | None = None
    is_default: bool = False
    fingerprint: str | None = None
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    identity_anchors: tuple[ProviderHomeAnchor, ...] = ()
    chatlas_includes: tuple[str, ...] = ()
    chatlas_excludes: tuple[str, ...] = ()
    account_live_usage_refresh: bool | None = None
    account_usage_progression_limit: str | None = None

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {"provider": self.provider, "is_default": self.is_default}
        if self.fingerprint is not None:
            payload["fingerprint"] = self.fingerprint
        if self.instance_id is not None:
            payload["instance_id"] = self.instance_id
        if self.label is not None:
            payload["label"] = self.label
        if self.homes:
            payload["homes"] = {key: str(path) for key, path in self.homes}
        if self.cli_command:
            payload["cli_command"] = list(self.cli_command)
        if self.run_args:
            payload["run_args"] = list(self.run_args)
        if self.env:
            payload["env"] = {key: value for key, value in self.env}
        if self.timeout_sec is not None:
            payload["timeout_sec"] = self.timeout_sec
        if self.default_model is not None:
            payload["default_model"] = self.default_model
        if self.model_flag is not None:
            payload["model_flag"] = self.model_flag
        if self.prompt_flag is not None:
            payload["prompt_flag"] = self.prompt_flag
        if self.direct_targets:
            payload["direct_targets"] = [str(path) for path in self.direct_targets]
        if self.grep_targets:
            payload["grep_targets"] = [str(path) for path in self.grep_targets]
        if self.sqlite_db_paths:
            payload["sqlite_db_paths"] = [str(path) for path in self.sqlite_db_paths]
        if self.identity_anchors:
            payload["identity_anchors"] = [anchor.summary() for anchor in self.identity_anchors]
        if self.chatlas_includes:
            payload["chatlas_includes"] = list(self.chatlas_includes)
        if self.chatlas_excludes:
            payload["chatlas_excludes"] = list(self.chatlas_excludes)
        if self.account_live_usage_refresh is not None:
            payload["account_live_usage_refresh"] = self.account_live_usage_refresh
        if self.account_usage_progression_limit is not None:
            payload["account_usage_progression_limit"] = self.account_usage_progression_limit
        return payload

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        raise CliError(
            f"agent {self.instance_id or '<default>'} for provider {self.provider} does not support run"
        )

    def run_dry(self, request: AgentRunRequest) -> AgentRunDryResult:
        raise CliError(
            f"agent {self.instance_id or '<default>'} for provider {self.provider} does not support run"
        )


def agent_base_kwargs_from_config(config: AgentConfig) -> dict[str, object]:
    return {
        "instance_id": config.instance_id,
        "label": config.label,
        "homes": config.homes,
        "cli_command": config.cli_command,
        "run_args": config.run_args,
        "env": config.env,
        "timeout_sec": config.timeout_sec,
        "default_model": config.default_model,
        "model_flag": config.model_flag,
        "prompt_flag": config.prompt_flag,
        "is_default": config.is_default,
        "fingerprint": config.fingerprint,
        "direct_targets": config.direct_targets,
        "grep_targets": config.grep_targets,
        "sqlite_db_paths": config.sqlite_db_paths,
        "identity_anchors": config.identity_anchors,
        "chatlas_includes": config.chatlas_includes,
        "chatlas_excludes": config.chatlas_excludes,
        "account_live_usage_refresh": config.account_live_usage_refresh,
        "account_usage_progression_limit": config.account_usage_progression_limit,
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
    homes: tuple[tuple[str, Path], ...]
    cli_command: tuple[str, ...]
    run_args: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    timeout_sec: int | None
    default_model: str | None
    model_flag: str | None
    prompt_flag: str | None
    is_default: bool
    fingerprint: str | None
    direct_targets: tuple[Path, ...]
    grep_targets: tuple[Path, ...]
    sqlite_db_paths: tuple[Path, ...]
    identity_anchors: tuple[ProviderHomeAnchor, ...]
    chatlas_includes: tuple[str, ...]
    chatlas_excludes: tuple[str, ...]
    account_live_usage_refresh: bool | None
    account_usage_progression_limit: str | None

    def summary(self) -> dict[str, object]: ...

    def run(self, request: AgentRunRequest) -> AgentRunResult: ...

    def run_dry(self, request: AgentRunRequest) -> AgentRunDryResult: ...


def provider_session_paths(
    provider: str,
    homes: tuple[tuple[str, Path], ...],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    direct_targets: list[Path] = []
    sqlite_db_paths: list[Path] = []
    provider_spec = require_canonical_provider_spec(provider)
    slots_by_key = {slot.key: slot for slot in provider_spec.home_slots}
    for key, home in homes:
        slot = slots_by_key.get(key)
        if slot is None:
            continue
        slot_direct_targets, _, slot_sqlite_db_paths = slot.build_paths(home=home)
        direct_targets.extend(slot_direct_targets)
        sqlite_db_paths.extend(slot_sqlite_db_paths)
    return tuple(direct_targets), tuple(sqlite_db_paths)


def agent_session_paths(agent: Agent) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    direct_targets, sqlite_db_paths = provider_session_paths(agent.provider, agent.homes)
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
        digest.update((anchor.slot or "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(anchor.path).encode("utf-8"))
    return digest.hexdigest()


def agent_fingerprint(agent: Agent) -> str:
    if agent.fingerprint is not None:
        return agent.fingerprint
    return agent_identity_fingerprint(
        provider=agent.provider,
        anchors=agent.identity_anchors,
        direct_targets=agent.direct_targets,
        sqlite_db_paths=agent.sqlite_db_paths,
    )


def agent_identity_key(agent: Agent) -> tuple[object, ...]:
    if agent.identity_anchors:
        return (
            agent.provider,
            tuple(anchor.identity_key() for anchor in agent.identity_anchors),
        )
    return (
        agent.provider,
        agent.instance_id,
        tuple((key, str(path)) for key, path in agent.homes),
        tuple(str(path) for path in agent.direct_targets),
        tuple(str(path) for path in agent.grep_targets),
        tuple(str(path) for path in agent.sqlite_db_paths),
        agent.cli_command,
        agent.run_args,
        agent.env,
        agent.timeout_sec,
        agent.default_model,
        agent.model_flag,
        agent.prompt_flag,
        agent.chatlas_includes,
        agent.chatlas_excludes,
        agent.account_live_usage_refresh,
        agent.account_usage_progression_limit,
    )


def agent_uri_key(agent: Agent) -> str:
    return quote(agent_fingerprint(agent), safe="")


def format_agent_run_command(
    command: tuple[str, ...],
    *,
    env_overrides: dict[str, str],
) -> str:
    if not env_overrides:
        return shlex.join(command)

    env_prefix = " ".join(
        f"{key}={shlex.quote(value)}"
        for key, value in sorted(env_overrides.items())
    )
    return f"{env_prefix} {shlex.join(command)}"


def execute_agent_run_command(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env_overrides: dict[str, str],
) -> AgentRunResult:
    env = os.environ.copy()
    env.update(env_overrides)
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CliError(f"agent executable not found: {exc.filename}") from exc
    return AgentRunResult(exit_code=int(result.returncode))


__all__ = [
    "Agent",
    "AgentBase",
    "AgentConfig",
    "AgentRunDryResult",
    "AgentRunRequest",
    "AgentRunResult",
    "SessionSource",
    "agent_base_kwargs_for_provider",
    "agent_base_kwargs_from_config",
    "agent_fingerprint",
    "agent_identity_fingerprint",
    "agent_identity_key",
    "agent_session_paths",
    "agent_uri_key",
    "execute_agent_run_command",
    "format_agent_run_command",
    "provider_session_paths",
]
