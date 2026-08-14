# $kw: ^agentos-provider-adapters --from Agent.Navigable.Codebase --note [DF] provider specs and concrete harness adapters are discoverable beneath one agent-owned namespace --supp ^c20260811-62u
"""Canonical provider specifications and concrete agent harness adapters."""

from .specs import (
    ProviderFamily,
    ProviderFamilySpec,
    ProviderHomeAnchor,
    ProviderHomeSpec,
    canonical_provider_families,
    canonical_provider_family_for_name,
    canonical_provider_specs,
    canonical_provider_spec_for_name,
    require_canonical_provider_family,
    require_canonical_provider_spec,
)

__all__ = [
    "ProviderFamily",
    "ProviderFamilySpec",
    "ProviderHomeAnchor",
    "ProviderHomeSpec",
    "canonical_provider_families",
    "canonical_provider_family_for_name",
    "canonical_provider_specs",
    "canonical_provider_spec_for_name",
    "require_canonical_provider_family",
    "require_canonical_provider_spec",
]
