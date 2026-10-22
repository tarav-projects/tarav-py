"""provider home projections."""

from __future__ import annotations

from dataclasses import dataclass

from tarav.l1.agent.providers.specs import (
    ProviderFamily,
    ProviderHomeSpec,
    canonical_provider_specs,
)


@dataclass(frozen=True)
class HomeProvider:
    provider_family: ProviderFamily
    home_spec: ProviderHomeSpec

    @property
    def family(self) -> str:
        return self.provider_family.family

    @property
    def supports_session_discovery(self) -> bool:
        return self.home_spec.supports_session_discovery()


def supported_home_providers() -> tuple[HomeProvider, ...]:
    return tuple(
        HomeProvider(
            provider_family=provider_spec.provider_family,
            home_spec=provider_spec.home_spec,
        )
        for provider_spec in canonical_provider_specs()
    )


def home_provider_for_name(family_name: str) -> HomeProvider | None:
    for provider in supported_home_providers():
        if provider.family == family_name:
            return provider
    return None


__all__ = [
    "HomeProvider",
    "home_provider_for_name",
    "supported_home_providers",
]
