from __future__ import annotations

from tarav.l1.agent.config import canonical_chat_provider_specs
from tarav.l1.agent.providers import ProviderFamily


def supported_chatlas_provider_families() -> tuple[ProviderFamily, ...]:
    return tuple(
        provider_spec.provider_family
        for provider_spec in canonical_chat_provider_specs()
        if provider_spec.supports_session_discovery
    )


__all__ = ["supported_chatlas_provider_families"]
