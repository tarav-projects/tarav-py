from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CODEX_PROVIDER = "codex"


@dataclass(frozen=True)
class CodexAgentAccounts:
    instance_id: str
    label: str
    cli_command: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    timeout_sec: int
    live_usage_refresh: bool
    usage_progression_limit: str | None = None

    @classmethod
    def from_account_context(cls, context: Any) -> CodexAgentAccounts:
        if context.provider != CODEX_PROVIDER:
            raise ValueError(f"cannot build Codex.Agent.Accounts from provider {context.provider}")
        return cls(
            instance_id=context.instance_id,
            label=context.label,
            cli_command=context.cli_command,
            env=context.env,
            timeout_sec=context.timeout_sec,
            live_usage_refresh=context.live_usage_refresh,
            usage_progression_limit=context.usage_progression_limit,
        )

    @property
    def provider(self) -> str:
        return CODEX_PROVIDER

    def env_mapping(self) -> dict[str, str]:
        return dict(self.env)


__all__ = [
    "CodexAgentAccounts",
]
