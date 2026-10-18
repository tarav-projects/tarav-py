# $kw: ^agentos-provider-specs --from Agent.Navigable.Codebase --note [DF] canonical provider identities and home layouts belong to the agent subsystem --supp ^c20260811-62u
"""canonical provider specifications."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderFamily:
    family: str


@dataclass(frozen=True)
class ProviderHomeAnchor:
    role: str
    path: Path

    def identity_key(self) -> tuple[str, str]:
        return (self.role, str(self.path))

    def summary(self) -> dict[str, str]:
        return {
            "role": self.role,
            "path": str(self.path),
        }


@dataclass(frozen=True)
class ProviderHomeSpec:
    default_home: str
    direct_relpaths: tuple[str, ...] = ()
    grep_relpaths: tuple[str, ...] = ()
    sqlite_db_relpaths: tuple[str, ...] = ()
    direct_anchor_roles: tuple[str, ...] = ()
    sqlite_db_anchor_roles: tuple[str, ...] = ()

    def build_paths(self, *, home: Path) -> tuple[tuple[Path, ...], tuple[Path, ...], tuple[Path, ...]]:
        return (
            tuple(_join_provider_home(home, relpath) for relpath in self.direct_relpaths),
            tuple(_join_provider_home(home, relpath) for relpath in self.grep_relpaths),
            tuple(_join_provider_home(home, relpath) for relpath in self.sqlite_db_relpaths),
        )

    def build_anchors(self, *, home: Path) -> tuple[ProviderHomeAnchor, ...]:
        direct_roles = self.direct_anchor_roles or tuple(
            f"direct_target_{index + 1}" for index, _ in enumerate(self.direct_relpaths)
        )
        sqlite_roles = self.sqlite_db_anchor_roles or tuple(
            f"sqlite_db_{index + 1}" for index, _ in enumerate(self.sqlite_db_relpaths)
        )
        if len(direct_roles) != len(self.direct_relpaths):
            raise ValueError("provider home direct anchor roles must match direct relpaths")
        if len(sqlite_roles) != len(self.sqlite_db_relpaths):
            raise ValueError("provider home sqlite anchor roles must match sqlite db relpaths")

        anchors = [
            ProviderHomeAnchor(
                role=role,
                path=_join_provider_home(home, relpath),
            )
            for role, relpath in zip(direct_roles, self.direct_relpaths, strict=True)
        ]
        anchors.extend(
            ProviderHomeAnchor(
                role=role,
                path=_join_provider_home(home, relpath),
            )
            for role, relpath in zip(sqlite_roles, self.sqlite_db_relpaths, strict=True)
        )
        return tuple(anchors)

    def supports_session_discovery(self) -> bool:
        return bool(self.direct_relpaths or self.sqlite_db_relpaths)


@dataclass(frozen=True)
class ProviderFamilySpec:
    provider_family: ProviderFamily
    home_spec: ProviderHomeSpec

    @property
    def family(self) -> str:
        return self.provider_family.family


# tarav.breadcrumb 85f1bf9a6372
_CANONICAL_PROVIDER_FAMILIES = tuple(
    ProviderFamily(family=family_name)
    for family_name in (
        "claude-code",
        "codex",
        "copilot-cli",
    )
)
_CANONICAL_PROVIDER_FAMILIES_BY_NAME = {
    provider_family.family: provider_family
    for provider_family in _CANONICAL_PROVIDER_FAMILIES
}


def canonical_provider_families() -> tuple[ProviderFamily, ...]:
    return _CANONICAL_PROVIDER_FAMILIES


def canonical_provider_family_for_name(family_name: str) -> ProviderFamily | None:
    return _CANONICAL_PROVIDER_FAMILIES_BY_NAME.get(family_name)


def require_canonical_provider_family(family_name: str) -> ProviderFamily:
    provider_family = canonical_provider_family_for_name(family_name)
    if provider_family is None:
        raise ValueError(f"unknown provider family: {family_name}")
    return provider_family


_CANONICAL_PROVIDER_SPECS = (
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("copilot-cli"),
        home_spec=ProviderHomeSpec(
            default_home="~/.copilot",
            direct_relpaths=("session-state",),
            direct_anchor_roles=("session_state_root",),
        ),
    ),
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("codex"),
        home_spec=ProviderHomeSpec(
            default_home="~/.codex",
            direct_relpaths=("sessions", "archived_sessions", "session_index.jsonl"),
            direct_anchor_roles=("sessions_root", "archive_root", "session_index"),
        ),
    ),
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("claude-code"),
        home_spec=ProviderHomeSpec(
            default_home="~/.claude",
            direct_relpaths=("projects",),
            grep_relpaths=("",),
            direct_anchor_roles=("projects_root",),
        ),
    ),
)
_CANONICAL_PROVIDER_SPECS_BY_NAME = {
    provider_spec.family: provider_spec
    for provider_spec in _CANONICAL_PROVIDER_SPECS
}


def canonical_provider_specs() -> tuple[ProviderFamilySpec, ...]:
    return _CANONICAL_PROVIDER_SPECS


def canonical_provider_spec_for_name(family_name: str) -> ProviderFamilySpec | None:
    return _CANONICAL_PROVIDER_SPECS_BY_NAME.get(family_name)


def require_canonical_provider_spec(family_name: str) -> ProviderFamilySpec:
    provider_spec = canonical_provider_spec_for_name(family_name)
    if provider_spec is None:
        raise ValueError(f"unknown provider family: {family_name}")
    return provider_spec


def _join_provider_home(home: Path, relpath: str) -> Path:
    if not relpath:
        return home
    return home / relpath


__all__ = [
    "canonical_provider_families",
    "canonical_provider_family_for_name",
    "canonical_provider_specs",
    "canonical_provider_spec_for_name",
    "ProviderFamily",
    "ProviderFamilySpec",
    "ProviderHomeAnchor",
    "ProviderHomeSpec",
    "require_canonical_provider_family",
    "require_canonical_provider_spec",
]
