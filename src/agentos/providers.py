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
    slot: str | None = None

    def identity_key(self) -> tuple[str, str | None, str]:
        return (self.role, self.slot, str(self.path))

    def summary(self) -> dict[str, str]:
        payload = {
            "role": self.role,
            "path": str(self.path),
        }
        if self.slot is not None:
            payload["slot"] = self.slot
        return payload


@dataclass(frozen=True)
class ProviderHomeSlot:
    key: str
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
            raise ValueError(f"provider slot {self.key} direct anchor roles must match direct relpaths")
        if len(sqlite_roles) != len(self.sqlite_db_relpaths):
            raise ValueError(f"provider slot {self.key} sqlite anchor roles must match sqlite db relpaths")

        anchors = [
            ProviderHomeAnchor(
                role=role,
                path=_join_provider_home(home, relpath),
                slot=self.key,
            )
            for role, relpath in zip(direct_roles, self.direct_relpaths, strict=True)
        ]
        anchors.extend(
            ProviderHomeAnchor(
                role=role,
                path=_join_provider_home(home, relpath),
                slot=self.key,
            )
            for role, relpath in zip(sqlite_roles, self.sqlite_db_relpaths, strict=True)
        )
        return tuple(anchors)

    def supports_session_discovery(self) -> bool:
        return bool(self.direct_relpaths or self.sqlite_db_relpaths)


@dataclass(frozen=True)
class ProviderFamilySpec:
    provider_family: ProviderFamily
    home_slots: tuple[ProviderHomeSlot, ...]

    @property
    def family(self) -> str:
        return self.provider_family.family


_CANONICAL_PROVIDER_FAMILIES = tuple(
    ProviderFamily(family=family_name)
    for family_name in (
        "agents",
        "claude-code",
        "codex",
        "copilot-cli",
        "gemini-cli",
        "opencode",
        "pi",
        "openclaw",
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
        home_slots=(
            ProviderHomeSlot(
                key="home",
                default_home="~/.copilot",
                direct_relpaths=("session-state",),
                direct_anchor_roles=("session_state_root",),
            ),
        ),
    ),
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("gemini-cli"),
        home_slots=(
            ProviderHomeSlot(
                key="home",
                default_home="~/.gemini",
                direct_relpaths=("tmp", "history"),
                direct_anchor_roles=("tmp_root", "history_root"),
            ),
        ),
    ),
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("codex"),
        home_slots=(
            ProviderHomeSlot(
                key="home",
                default_home="~/.codex",
                direct_relpaths=("sessions", "archived_sessions", "session_index.jsonl"),
                direct_anchor_roles=("sessions_root", "archive_root", "session_index"),
            ),
        ),
    ),
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("claude-code"),
        home_slots=(
            ProviderHomeSlot(
                key="cli",
                default_home="~/.claude",
                direct_relpaths=("projects",),
                grep_relpaths=("",),
                direct_anchor_roles=("projects_root",),
            ),
            ProviderHomeSlot(
                key="desktop",
                default_home="~/Library/Application Support/Claude",
                direct_relpaths=("claude-code-sessions",),
                grep_relpaths=("claude-code-sessions",),
                direct_anchor_roles=("desktop_sessions_root",),
            ),
        ),
    ),
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("opencode"),
        home_slots=(
            ProviderHomeSlot(
                key="home",
                default_home="~/.local/share/opencode",
                direct_relpaths=("storage/session_diff",),
                grep_relpaths=("storage", "log"),
                sqlite_db_relpaths=("opencode.db",),
                direct_anchor_roles=("session_diff_root",),
                sqlite_db_anchor_roles=("sqlite_db",),
            ),
        ),
    ),
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("pi"),
        home_slots=(
            ProviderHomeSlot(
                key="home",
                default_home="~/.pi/agent",
                direct_relpaths=("sessions",),
                direct_anchor_roles=("sessions_root",),
            ),
        ),
    ),
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("openclaw"),
        home_slots=(
            ProviderHomeSlot(
                key="home",
                default_home="~/.openclaw",
                direct_relpaths=("agents",),
                direct_anchor_roles=("agents_root",),
            ),
        ),
    ),
    ProviderFamilySpec(
        provider_family=require_canonical_provider_family("agents"),
        home_slots=(
            ProviderHomeSlot(
                key="home",
                default_home="~/.agents",
            ),
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
    "ProviderHomeSlot",
    "require_canonical_provider_family",
    "require_canonical_provider_spec",
]
