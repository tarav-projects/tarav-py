"""Shared agent configuration models and canonical provider specifications."""

from __future__ import annotations

from dataclasses import dataclass

from tarav.l1.agent.providers.homes import home_provider_for_name
from tarav.l1.agent.providers import ProviderFamily, ProviderHomeSpec


AGENT_ACCOUNT_POLICY_PROFILE_DEFAULT = "profile-default"
AGENT_ACCOUNT_POLICY_HOME_CURRENT = "home-current"
AGENT_ACCOUNT_POLICIES = (
    AGENT_ACCOUNT_POLICY_PROFILE_DEFAULT,
    AGENT_ACCOUNT_POLICY_HOME_CURRENT,
)


@dataclass(frozen=True)
class ChatProviderSpec:
    provider_family: ProviderFamily
    home_spec: ProviderHomeSpec
    supports_session_discovery: bool = True

    @property
    def family(self) -> str:
        return self.provider_family.family


_CANONICAL_CHAT_PROVIDER_SPECS: tuple[ChatProviderSpec, ...] = ()


def _agent_default_run_args(family_name: str) -> tuple[str, ...]:
    if family_name == "codex":
        return ("--dangerously-bypass-approvals-and-sandbox",)
    if family_name == "copilot-cli":
        return ("--allow-all-tools", "--no-ask-user")
    return ()


def _agent_default_model(family_name: str) -> str | None:
    return None


def _agent_default_ping_model(family_name: str) -> str | None:
    if family_name == "claude-code":
        return "haiku"
    if family_name == "codex":
        # tarav.breadcrumb 80e2a23a4469
        return "gpt-6-luna"
    return None


def canonical_chat_provider_specs() -> tuple[ChatProviderSpec, ...]:
    return _CANONICAL_CHAT_PROVIDER_SPECS


def canonical_chat_provider_spec_for_name(family_name: str) -> ChatProviderSpec | None:
    for provider_spec in _CANONICAL_CHAT_PROVIDER_SPECS:
        if provider_spec.family == family_name:
            return provider_spec
    return None


def _chat_provider_spec(
    family_name: str,
    *,
    supports_session_discovery: bool = True,
) -> ChatProviderSpec:
    home_provider = home_provider_for_name(family_name)
    if home_provider is None:
        raise ValueError(f"unknown provider family: {family_name}")
    return ChatProviderSpec(
        provider_family=home_provider.provider_family,
        home_spec=home_provider.home_spec,
        supports_session_discovery=supports_session_discovery,
    )


_CANONICAL_CHAT_PROVIDER_SPECS = (
    _chat_provider_spec("copilot-cli"),
    _chat_provider_spec("codex"),
    _chat_provider_spec("claude-code"),
)


@dataclass(frozen=True)
class AgentConfigSource:
    object_path: tuple[str, ...]
    field_prefix: str


AGENT_PROFILE_CONFIG_SOURCE = AgentConfigSource(
    object_path=(),
    field_prefix="agent.profiles",
)

AGENT_PROVIDER_CONFIG_OBJECT_PATH = ("agent", "providers")
AGENT_PROVIDER_CONFIG_FIELD_PREFIX = "agent.providers"


@dataclass(frozen=True)
class AgentProviderConfig:
    cli_command: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentConfigEntry:
    field_prefix: str
    index: int
    raw_profile: dict[str, object]

    def item_path(self) -> str:
        return f"{self.field_prefix}[{self.index}]"

    def field_name(self, field: str) -> str:
        return f"{self.item_path()}.{field}"
