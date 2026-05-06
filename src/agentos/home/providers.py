from __future__ import annotations

from dataclasses import dataclass

from agentos.providers import ProviderFamily, ProviderHomeSlot, canonical_provider_specs


@dataclass(frozen=True)
class HomeProvider:
    provider_family: ProviderFamily
    home_slots: tuple[ProviderHomeSlot, ...]

    @property
    def family(self) -> str:
        return self.provider_family.family

    def supported_home_keys(self) -> tuple[str, ...]:
        return tuple(slot.key for slot in self.home_slots)

    @property
    def supports_session_discovery(self) -> bool:
        return any(slot.supports_session_discovery() for slot in self.home_slots)


def supported_home_providers() -> tuple[HomeProvider, ...]:
    return tuple(
        HomeProvider(
            provider_family=provider_spec.provider_family,
            home_slots=provider_spec.home_slots,
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
