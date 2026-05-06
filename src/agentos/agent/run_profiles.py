from __future__ import annotations

from dataclasses import dataclass

from agentos.providers import ProviderFamily, canonical_provider_families


@dataclass(frozen=True)
class AgentRunProvider:
    provider_family: ProviderFamily
    default_cli_command: tuple[str, ...] = ()
    default_run_args: tuple[str, ...] = ()
    default_model: str | None = None
    default_model_flag: str | None = None
    default_prompt_flag: str | None = None

    @property
    def family(self) -> str:
        return self.provider_family.family

    @property
    def supports_default_run_profile(self) -> bool:
        return bool(self.default_cli_command)


def supported_agent_run_providers() -> tuple[AgentRunProvider, ...]:
    return tuple(
        AgentRunProvider(
            provider_family=provider_family,
            default_cli_command=provider_family_default_cli_command(provider_family.family),
            default_run_args=provider_family_default_run_args(provider_family.family),
            default_model=provider_family_default_model(provider_family.family),
            default_model_flag=provider_family_default_model_flag(provider_family.family),
            default_prompt_flag=provider_family_default_prompt_flag(provider_family.family),
        )
        for provider_family in canonical_provider_families()
    )


def agent_run_provider_for_name(family_name: str) -> AgentRunProvider | None:
    for provider in supported_agent_run_providers():
        if provider.family == family_name:
            return provider
    return None


def provider_family_default_cli_command(family_name: str) -> tuple[str, ...]:
    if family_name == "codex":
        return ("codex",)
    if family_name == "copilot-cli":
        return ("copilot",)
    if family_name == "pi":
        return ("pi",)
    return ()


def provider_family_default_run_args(family_name: str) -> tuple[str, ...]:
    if family_name == "codex":
        return ("exec", "--dangerously-bypass-approvals-and-sandbox")
    if family_name == "copilot-cli":
        return ("--allow-all-tools", "--no-ask-user")
    if family_name == "opencode":
        return ("run",)
    return ()


def provider_family_default_model(family_name: str) -> str | None:
    if family_name == "codex":
        return "gpt-5.4"
    return None


def provider_family_default_model_flag(family_name: str) -> str | None:
    if family_name == "codex":
        return "--model"
    if family_name == "copilot-cli":
        return "--model"
    if family_name == "opencode":
        return "--model"
    if family_name == "pi":
        return "--model"
    return None


def provider_family_default_prompt_flag(family_name: str) -> str | None:
    if family_name == "copilot-cli":
        return "-p"
    if family_name == "pi":
        return "-p"
    return None


__all__ = [
    "agent_run_provider_for_name",
    "AgentRunProvider",
    "provider_family_default_cli_command",
    "provider_family_default_model",
    "provider_family_default_model_flag",
    "provider_family_default_prompt_flag",
    "provider_family_default_run_args",
    "supported_agent_run_providers",
]
