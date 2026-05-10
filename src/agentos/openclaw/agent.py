from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos.providers import ProviderHomeAnchor
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.primitives import (
    AgentConfig,
    agent_session_paths,
    AgentRunCommand,
    resolve_terminal_agent_run,
)
from agentos.openclaw.session import (
    OpenclawSession,
    OpenclawSessionRef,
    discover_openclaw_session_refs,
    load_openclaw_session,
)


OPENCLAW_PROVIDER = "openclaw"


@dataclass(frozen=True)
class OpenclawAgent:
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

    @classmethod
    def from_config(cls, config: AgentConfig) -> OpenclawAgent:
        if config.provider != OPENCLAW_PROVIDER:
            raise CliError(f"cannot build OpenClaw.Agent from provider {config.provider}")
        return cls(
            instance_id=config.instance_id,
            label=config.label,
            homes=config.homes,
            cli_command=config.cli_command,
            run_args=config.run_args,
            env=config.env,
            timeout_sec=config.timeout_sec,
            default_model=config.default_model,
            model_flag=config.model_flag,
            prompt_flag=config.prompt_flag,
            is_default=config.is_default,
            fingerprint=config.fingerprint,
            direct_targets=config.direct_targets,
            grep_targets=config.grep_targets,
            sqlite_db_paths=config.sqlite_db_paths,
            identity_anchors=config.identity_anchors,
            chatlas_includes=config.chatlas_includes,
            chatlas_excludes=config.chatlas_excludes,
            account_live_usage_refresh=config.account_live_usage_refresh,
            account_usage_progression_limit=config.account_usage_progression_limit,
        )

    @property
    def provider(self) -> str:
        return OPENCLAW_PROVIDER

    def resolve_run(self, *, prompt: str, model: str | None = None) -> AgentRunCommand:
        return resolve_terminal_agent_run(self, prompt=prompt, model=model)

    def discover_session_refs(self) -> tuple[OpenclawSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_openclaw_session_refs(targets=direct_targets)

    def load_session(self, session_ref: OpenclawSessionRef) -> OpenclawSession:
        return load_openclaw_session(session_ref)

    def summary(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"provider": self.provider, "is_default": self.is_default}
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


__all__ = ["OpenclawAgent"]
