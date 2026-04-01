from __future__ import annotations

import glob
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from agentos._core.errors import CliError
from agentos._core.scan import DEFAULT_SCAN_EXCLUDES
from agentos.chat.providers import (
    ProviderFamily,
    ProviderInstanceConfigEntry,
    ProviderInstanceConfigSource,
    load_provider_instance_config_entries,
    require_canonical_provider_family,
)
from agentos.chat.sessions import (
    BackingArtifact,
    ChatSession,
    ClaudeCodeSessionSource,
    CodexSessionSource,
    CopilotCliSessionSource,
    GeminiCliSessionSource,
    OpenclawSessionSource,
    OpencodeSessionSource,
    ProviderInstance,
    ProviderInstanceAnchor,
    SessionSource,
    coerce_timestamp,
    safe_path_mtime,
)

TEXT_FILE_SUFFIXES = {
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
}
MAX_GREP_FILE_BYTES = 5 * 1024 * 1024
SESSION_SORT_CHOICES = {"lexical", "newest", "oldest"}
_SESSION_PROVIDER_INSTANCE_CONFIG_SOURCE = ProviderInstanceConfigSource(
    object_path=("chat", "session", "provider_instances"),
    field_prefix="chat.session.provider_instances",
)


@dataclass(frozen=True)
class ProviderHomeSlot:
    key: str
    default_home: str
    direct_relpaths: tuple[str, ...]
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

    def build_anchors(self, *, home: Path) -> tuple[ProviderInstanceAnchor, ...]:
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
            ProviderInstanceAnchor(
                role=role,
                path=_join_provider_home(home, relpath),
                slot=self.key,
            )
            for role, relpath in zip(direct_roles, self.direct_relpaths, strict=True)
        ]
        anchors.extend(
            ProviderInstanceAnchor(
                role=role,
                path=_join_provider_home(home, relpath),
                slot=self.key,
            )
            for role, relpath in zip(sqlite_roles, self.sqlite_db_relpaths, strict=True)
        )
        return tuple(anchors)


@dataclass(frozen=True)
class SessionProviderHandler:
    provider_family: ProviderFamily
    home_slots: tuple[ProviderHomeSlot, ...]
    discover_sources: Callable[[SessionProviderContext], list[SessionSource]]
    find_sources: Callable[[SessionProviderContext, str], list[SessionSource]]
    build_source_stats: Callable[[SessionSource], dict[str, Any]]

    @property
    def family(self) -> str:
        return self.provider_family.family

    def supported_home_keys(self) -> tuple[str, ...]:
        return tuple(slot.key for slot in self.home_slots)

    def discover_sessions(self, context: SessionProviderContext) -> list[ChatSession]:
        return _wrap_session_sources(self.discover_sources(context))

    def find_sessions(
        self,
        context: SessionProviderContext,
        query: str,
    ) -> list[ChatSession]:
        return _wrap_session_sources(self.find_sources(context, query))

    def default_instance(self) -> ProviderInstance:
        return self.instance_from_homes(
            {
                slot.key: slot.default_home
                for slot in self.home_slots
            },
            index=None,
            is_default=True,
        )

    def instance_from_home(
        self,
        home: str,
        *,
        index: int | None,
        is_default: bool,
    ) -> ProviderInstance:
        if len(self.home_slots) != 1:
            supported_keys = ", ".join(self.supported_home_keys())
            field_name = _provider_instance_field_name(index=index, field="home")
            homes_field_name = _provider_instance_field_name(index=index, field="homes")
            raise CliError(
                f"{field_name} is only supported for providers with a single home root; "
                f"use {homes_field_name} with keys: {supported_keys}"
            )
        slot = self.home_slots[0]
        return self.instance_from_homes({slot.key: home}, index=index, is_default=is_default)

    def instance_from_homes(
        self,
        homes: dict[str, str],
        *,
        index: int | None,
        is_default: bool,
    ) -> ProviderInstance:
        supported_slots = {slot.key: slot for slot in self.home_slots}
        unsupported_keys = sorted(key for key in homes if key not in supported_slots)
        homes_field_name = _provider_instance_field_name(index=index, field="homes")
        if unsupported_keys:
            supported_keys = ", ".join(self.supported_home_keys())
            unsupported_keys_text = ", ".join(unsupported_keys)
            raise CliError(
                f"{homes_field_name} contains unsupported keys for provider {self.family}: "
                f"{unsupported_keys_text} (supported: {supported_keys})"
            )

        normalized_homes: list[tuple[str, Path]] = []
        direct_targets: list[Path] = []
        grep_targets: list[Path] = []
        sqlite_db_paths: list[Path] = []
        anchors: list[ProviderInstanceAnchor] = []

        for slot in self.home_slots:
            raw_home = homes.get(slot.key)
            if raw_home is None:
                continue
            normalized_home = Path(
                _normalize_provider_home(
                    raw_home,
                    field_name=f"{homes_field_name}.{slot.key}",
                )
            ).expanduser().resolve()
            normalized_homes.append((slot.key, normalized_home))
            slot_direct_paths, slot_grep_paths, slot_sqlite_db_paths = slot.build_paths(
                home=normalized_home,
            )
            direct_targets.extend(slot_direct_paths)
            grep_targets.extend(slot_grep_paths or slot_direct_paths)
            sqlite_db_paths.extend(slot_sqlite_db_paths)
            anchors.extend(slot.build_anchors(home=normalized_home))

        if not direct_targets and not sqlite_db_paths:
            supported_keys = ", ".join(self.supported_home_keys())
            raise CliError(
                f"{homes_field_name} must include at least one supported home key: {supported_keys}"
            )

        return ProviderInstance(
            family=self.family,
            homes=tuple(normalized_homes),
            direct_targets=_unique_paths(tuple(direct_targets)),
            grep_targets=_unique_paths(tuple(grep_targets)),
            sqlite_db_paths=_unique_paths(tuple(sqlite_db_paths)),
            anchors=tuple(anchors),
            is_default=is_default,
        )


@dataclass(frozen=True)
class SessionProviderContext:
    provider_handler: SessionProviderHandler
    provider_instance: ProviderInstance
    direct_targets: tuple[Path, ...]
    direct_existing_targets: tuple[Path, ...]
    direct_missing_targets: tuple[Path, ...]
    grep_targets: tuple[Path, ...]
    grep_existing_targets: tuple[Path, ...]
    grep_missing_targets: tuple[Path, ...]
    sqlite_db_paths: tuple[Path, ...]
    sqlite_existing_db_paths: tuple[Path, ...]
    sqlite_missing_db_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ChatSessionUriQuery:
    provider_family: str
    instance_fingerprint_prefix: str
    session_id: str


def _make_direct_session_discovery(
    discover_sources: Callable[..., list[SessionSource]],
    *,
    include_sqlite: bool = False,
) -> Callable[[SessionProviderContext], list[SessionSource]]:
    def handler(context: SessionProviderContext) -> list[SessionSource]:
        kwargs: dict[str, Any] = {
            "provider_instance": context.provider_instance,
            "targets": context.direct_existing_targets,
        }
        if include_sqlite:
            kwargs["sqlite_db_paths"] = context.sqlite_existing_db_paths
        return discover_sources(**kwargs)

    return handler


def _make_direct_session_finder(
    find_sources: Callable[..., list[SessionSource]],
    *,
    query_arg: str,
    include_sqlite: bool = False,
) -> Callable[[SessionProviderContext, str], list[SessionSource]]:
    def handler(context: SessionProviderContext, query: str) -> list[SessionSource]:
        kwargs: dict[str, Any] = {
            "provider_instance": context.provider_instance,
            "targets": context.direct_existing_targets,
            query_arg: query,
        }
        if include_sqlite:
            kwargs["sqlite_db_paths"] = context.sqlite_existing_db_paths
        return find_sources(**kwargs)

    return handler


def _make_typed_session_stats_builder(
    source_type: type[SessionSource],
    build_source_stats: Callable[[Any], dict[str, Any]],
) -> Callable[[SessionSource], dict[str, Any]]:
    def handler(source: SessionSource) -> dict[str, Any]:
        if not isinstance(source, source_type):
            raise CliError(f"chat session stats is not implemented for provider {source.provider_family}")
        return build_source_stats(source)

    return handler


def supported_provider_families() -> tuple[SessionProviderHandler, ...]:
    return (
        SessionProviderHandler(
            provider_family=require_canonical_provider_family("copilot-cli"),
            home_slots=(
                ProviderHomeSlot(
                    key="home",
                    default_home="~/.copilot",
                    direct_relpaths=("session-state",),
                    direct_anchor_roles=("session_state_root",),
                ),
            ),
            discover_sources=_make_direct_session_discovery(_list_copilot_sessions),
            find_sources=_make_direct_session_finder(
                _find_copilot_sessions,
                query_arg="session_id",
            ),
            build_source_stats=_make_typed_session_stats_builder(
                CopilotCliSessionSource,
                _build_copilot_cli_session_stats,
            ),
        ),
        SessionProviderHandler(
            provider_family=require_canonical_provider_family("gemini-cli"),
            home_slots=(
                ProviderHomeSlot(
                    key="home",
                    default_home="~/.gemini",
                    direct_relpaths=("tmp", "history"),
                    direct_anchor_roles=("tmp_root", "history_root"),
                ),
            ),
            discover_sources=_make_direct_session_discovery(_list_gemini_sessions),
            find_sources=_make_direct_session_finder(
                _find_gemini_sessions,
                query_arg="session_id",
            ),
            build_source_stats=_make_typed_session_stats_builder(
                GeminiCliSessionSource,
                _build_gemini_cli_session_stats,
            ),
        ),
        SessionProviderHandler(
            provider_family=require_canonical_provider_family("codex"),
            home_slots=(
                ProviderHomeSlot(
                    key="home",
                    default_home="~/.codex",
                    direct_relpaths=("sessions", "archived_sessions", "session_index.jsonl"),
                    direct_anchor_roles=("sessions_root", "archive_root", "session_index"),
                ),
            ),
            discover_sources=_make_direct_session_discovery(_list_codex_sessions),
            find_sources=_make_direct_session_finder(
                _find_codex_sessions,
                query_arg="query",
            ),
            build_source_stats=_make_typed_session_stats_builder(
                CodexSessionSource,
                _build_codex_session_stats,
            ),
        ),
        SessionProviderHandler(
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
            discover_sources=_make_direct_session_discovery(_list_claude_code_sessions),
            find_sources=_make_direct_session_finder(
                _find_claude_code_sessions,
                query_arg="query",
            ),
            build_source_stats=_make_typed_session_stats_builder(
                ClaudeCodeSessionSource,
                _build_claude_code_session_stats,
            ),
        ),
        SessionProviderHandler(
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
            discover_sources=_make_direct_session_discovery(
                _list_opencode_sessions,
                include_sqlite=True,
            ),
            find_sources=_make_direct_session_finder(
                _find_opencode_sessions,
                query_arg="session_id",
                include_sqlite=True,
            ),
            build_source_stats=_make_typed_session_stats_builder(
                OpencodeSessionSource,
                _build_opencode_session_stats,
            ),
        ),
        SessionProviderHandler(
            provider_family=require_canonical_provider_family("openclaw"),
            home_slots=(
                ProviderHomeSlot(
                    key="home",
                    default_home="~/.openclaw",
                    direct_relpaths=("agents",),
                    direct_anchor_roles=("agents_root",),
                ),
            ),
            discover_sources=_make_direct_session_discovery(_list_openclaw_sessions),
            find_sources=_make_direct_session_finder(
                _find_openclaw_sessions,
                query_arg="session_id",
            ),
            build_source_stats=_make_typed_session_stats_builder(
                OpenclawSessionSource,
                _build_openclaw_session_stats,
            ),
        ),
    )


def configured_provider_instances(*, start_path: Path | str = ".") -> tuple[ProviderInstance, ...]:
    provider_instances = [family.default_instance() for family in supported_provider_families()]
    provider_instances.extend(_load_configured_provider_instances(start_path=start_path))
    return _dedupe_provider_instances(tuple(provider_instances))


def _load_configured_provider_instances(*, start_path: Path | str = ".") -> tuple[ProviderInstance, ...]:
    entries = load_provider_instance_config_entries(
        start_path=start_path,
        sources=(_SESSION_PROVIDER_INSTANCE_CONFIG_SOURCE,),
    )
    return tuple(_provider_instance_from_config(entry) for entry in entries)


def _provider_instance_from_config(entry: ProviderInstanceConfigEntry) -> ProviderInstance:
    raw_instance = entry.raw_instance
    family_name = raw_instance.get("provider")
    if not isinstance(family_name, str) or not family_name:
        raise CliError(f"{entry.item_path()}.provider is required")

    family = _provider_family_for_name(family_name)
    if family is None:
        supported_providers = ", ".join(
            sorted(provider_family.family for provider_family in supported_provider_families())
        )
        raise CliError(
            f"{entry.item_path()}.provider must be one of: {supported_providers}"
        )

    home = raw_instance.get("home")
    raw_homes = raw_instance.get("homes")
    raw_direct_paths = raw_instance.get("direct_paths")
    raw_grep_paths = raw_instance.get("grep_paths")
    raw_sqlite_db_paths = raw_instance.get("sqlite_db_paths")
    raw_sqlite_db_path = raw_instance.get("sqlite_db_path")

    if home is not None and raw_homes is not None:
        raise CliError(
            f"{entry.item_path()} must not define both home and homes"
        )
    if raw_sqlite_db_path is not None and raw_sqlite_db_paths is not None:
        raise CliError(
            f"{entry.item_path()} must not define both sqlite_db_path and sqlite_db_paths"
        )

    direct_paths = _load_optional_string_tuple(
        raw_direct_paths,
        field_name=entry.field_name("direct_paths"),
    )
    grep_paths = _load_optional_string_tuple(
        raw_grep_paths,
        field_name=entry.field_name("grep_paths"),
    )
    sqlite_db_paths = _load_optional_string_tuple(
        raw_sqlite_db_paths if raw_sqlite_db_paths is not None else raw_sqlite_db_path,
        field_name=entry.field_name("sqlite_db_paths"),
    )
    homes = _load_optional_string_mapping(
        raw_homes,
        field_name=entry.field_name("homes"),
    )

    if home is not None:
        normalized_home = _normalize_provider_home(
            home,
            field_name=entry.field_name("home"),
        )
        if direct_paths or grep_paths or sqlite_db_paths:
            raise CliError(
                f"{entry.item_path()} must define either home or explicit paths, not both"
            )
        return family.instance_from_home(normalized_home, index=entry.index, is_default=False)

    if homes:
        if len(family.home_slots) == 1:
            raise CliError(
                f"{entry.field_name('homes')} is only supported for providers with multiple home roots; "
                f"use {entry.field_name('home')}"
            )
        if direct_paths or grep_paths or sqlite_db_paths:
            raise CliError(
                f"{entry.item_path()} must define either homes or explicit paths, not both"
            )
        return family.instance_from_homes(homes, index=entry.index, is_default=False)

    if not direct_paths:
        raise CliError(
            f"{entry.item_path()} must define home, homes, or direct_paths"
        )

    resolved_direct_targets = _resolve_raw_paths(direct_paths)
    resolved_grep_targets = _resolve_raw_paths(grep_paths) if grep_paths else resolved_direct_targets
    resolved_sqlite_db_paths = _resolve_raw_paths(sqlite_db_paths)
    return ProviderInstance(
        family=family_name,
        homes=(),
        direct_targets=resolved_direct_targets,
        grep_targets=resolved_grep_targets,
        sqlite_db_paths=resolved_sqlite_db_paths,
        anchors=_build_explicit_provider_instance_anchors(
            direct_targets=resolved_direct_targets,
            sqlite_db_paths=resolved_sqlite_db_paths,
        ),
        is_default=False,
    )


def _load_optional_string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise CliError(f"{field_name} must not be empty")
        return (stripped,)
    if not isinstance(value, list):
        raise CliError(f"{field_name} must be a string or array of strings")

    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise CliError(f"{field_name}[{index}] must be a non-empty string")
        items.append(item.strip())
    return tuple(items)


def _load_optional_string_mapping(value: object, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CliError(f"{field_name} must be a JSON object")

    items: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise CliError(f"{field_name} contains an invalid key")
        if not isinstance(item, str) or not item.strip():
            raise CliError(f"{field_name}.{key} must be a non-empty string")
        items[key.strip()] = item.strip()
    return items


def _provider_family_for_name(family_name: str) -> SessionProviderHandler | None:
    for family in supported_provider_families():
        if family.family == family_name:
            return family
    return None


def _provider_instance_field_name(*, index: int | None, field: str) -> str:
    if index is None:
        return field
    return f"chat.session.provider_instances[{index}].{field}"


def _normalize_provider_home(home: object, *, field_name: str) -> str:
    if not isinstance(home, str) or not home.strip():
        raise CliError(f"{field_name} must be a non-empty string")
    return home.strip()


def _resolve_raw_paths(raw_paths: tuple[str, ...]) -> tuple[Path, ...]:
    return _unique_paths(tuple(Path(raw_path).expanduser().resolve() for raw_path in raw_paths))


def _build_explicit_provider_instance_anchors(
    *,
    direct_targets: tuple[Path, ...],
    sqlite_db_paths: tuple[Path, ...],
) -> tuple[ProviderInstanceAnchor, ...]:
    anchors = [
        ProviderInstanceAnchor(role=f"direct_target_{index + 1}", path=path)
        for index, path in enumerate(direct_targets)
    ]
    anchors.extend(
        ProviderInstanceAnchor(role=f"sqlite_db_{index + 1}", path=path)
        for index, path in enumerate(sqlite_db_paths)
    )
    return tuple(anchors)


def _join_provider_home(home: Path, relpath: str) -> Path:
    if not relpath:
        return home
    return home / relpath


def _dedupe_provider_instances(provider_instances: tuple[ProviderInstance, ...]) -> tuple[ProviderInstance, ...]:
    unique_instances: dict[tuple[object, ...], ProviderInstance] = {}
    for provider_instance in provider_instances:
        key = provider_instance.identity_key()
        if key not in unique_instances:
            unique_instances[key] = provider_instance
            continue
        existing = unique_instances[key]
        if existing.is_default or not provider_instance.is_default:
            continue
        unique_instances[key] = provider_instance
    return tuple(unique_instances.values())


def list_chat_sessions(
    *,
    sort: str = "lexical",
    full_output: bool = False,
    limit: int | None = None,
    providers: tuple[str, ...] | None = None,
    extractable_only: bool = False,
    updated_after: float | None = None,
) -> dict[str, object]:
    _validate_sort_choice(sort)
    _validate_session_limit(limit)

    provider_groups = _iter_provider_context_groups(providers)
    discovered_sessions: list[ChatSession] = []
    provider_payloads: list[dict[str, Any]] = []

    for _, contexts in provider_groups:
        for context in contexts:
            discovered_sessions.extend(_discover_direct_provider_sessions(context))

    sessions = [
        session
        for session in _dedupe_sessions(discovered_sessions)
        if _session_matches_list_filters(
            session,
            extractable_only=extractable_only,
            updated_after=updated_after,
        )
    ]
    sessions = _sort_sessions(sessions, sort)
    if limit is not None:
        sessions = sessions[:limit]

    for provider_family, contexts in provider_groups:
        provider_sessions = [
            session
            for session in sessions
            if session.provider_family == provider_family.family
        ]
        provider_payload = _build_provider_payload(
            provider_family=provider_family.family,
            contexts=contexts,
            include_grep=False,
            item_count_key="session_count",
            item_count=len(provider_sessions),
        )
        provider_payloads.append(provider_payload)

    output_providers = (
        provider_payloads
        if full_output
        else [payload for payload in provider_payloads if payload["session_count"] > 0]
    )
    payload: dict[str, object] = {
        "status": "ok",
        "command": "chat session list",
        "selection": {
            "kind": "all",
            "providers": list(providers) if providers is not None else None,
            "filters": {
                "sort": sort,
                "limit": limit,
                "extractable": extractable_only,
                "updated_after": _format_stats_timestamp(updated_after),
            },
        },
        "expansions": [],
        "sessions": [_session_summary(session) for session in sessions],
        "session_count": len(sessions),
    }
    if full_output:
        payload["provider_diagnostics"] = output_providers
    return payload


def chat_session_stats(
    *,
    full_output: bool = False,
    providers: tuple[str, ...] | None = None,
) -> dict[str, object]:
    provider_payloads: list[dict[str, Any]] = []
    total_sessions = 0
    total_extractable_sessions = 0
    total_non_extractable_sessions = 0

    for provider_family, contexts in _iter_provider_context_groups(providers):
        sessions: list[ChatSession] = []
        for context in contexts:
            sessions.extend(_discover_direct_provider_sessions(context))
        sessions = _sort_sessions(_dedupe_sessions(sessions), "lexical")
        stats_payload = _build_stats_provider_payload(
            provider_family=provider_family.family,
            contexts=contexts,
            sessions=sessions,
        )
        provider_payloads.append(stats_payload)
        total_sessions += stats_payload["session_count"]
        total_extractable_sessions += stats_payload["extractable_session_count"]
        total_non_extractable_sessions += stats_payload["non_extractable_session_count"]

    output_providers = (
        provider_payloads
        if full_output
        else [payload for payload in provider_payloads if payload["session_count"] > 0]
    )
    return {
        "status": "ok",
        "command": "chat session stats",
        "selection": {
            "kind": "all",
            "providers": list(providers) if providers is not None else None,
        },
        "stats": {
            "session_count": total_sessions,
            "extractable_session_count": total_extractable_sessions,
            "non_extractable_session_count": total_non_extractable_sessions,
            "by_provider": output_providers,
        },
    }


def chat_session_resolved_stats(
    query: str,
    *,
    providers: tuple[str, ...] | None = None,
) -> dict[str, object]:
    sessions = resolve_chat_sessions(query, providers=providers)
    if not sessions:
        raise CliError(f"no session matched query {query}")
    if len(sessions) > 1:
        raise CliError(
            f"multiple sessions matched query {query}: {_format_resolved_session_choices(sessions)}"
        )

    session = sessions[0]
    provider_stats = _build_provider_session_stats(session)
    return {
        "status": "ok",
        "command": "chat session stats",
        "selection": {
            "kind": "query",
            "query": query,
            "providers": list(providers) if providers is not None else None,
        },
        "session": _build_common_session_stats(session, query=query),
        "stats": provider_stats,
    }


def format_chat_session_stats_markdown(payload: dict[str, object]) -> str:
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    lines = [
        "# Chat Session Stats",
        "",
        f"- Sessions: {stats.get('session_count', 0)}",
        f"- Extractable: {stats.get('extractable_session_count', 0)}",
        f"- Non-extractable: {stats.get('non_extractable_session_count', 0)}",
    ]

    providers = stats.get("by_provider")
    if not isinstance(providers, list) or not providers:
        return "\n".join(lines)

    lines.insert(2, f"- Providers: {len(providers)}")
    for provider_payload in providers:
        if not isinstance(provider_payload, dict):
            continue

        provider_name = provider_payload.get("provider", "unknown")
        lines.extend(
            [
                "",
                f"## {provider_name}",
                "",
                f"- Sessions: {provider_payload.get('session_count', 0)}",
                f"- Extractable: {provider_payload.get('extractable_session_count', 0)}",
                f"- Non-extractable: {provider_payload.get('non_extractable_session_count', 0)}",
                f"- Backing artifacts: {provider_payload.get('backing_artifact_count', 0)}",
            ]
        )

        examples = provider_payload.get("session_id_examples")
        if isinstance(examples, list) and examples:
            lines.append(f"- Examples: {', '.join(str(example) for example in examples)}")

        named_examples = provider_payload.get("session_examples")
        if isinstance(named_examples, list) and named_examples:
            formatted_examples = []
            for example in named_examples:
                if not isinstance(example, dict):
                    continue
                session_id = example.get("session_id")
                if session_id is None:
                    continue
                name = example.get("display_name")
                formatted_examples.append(f"{session_id} ({name})" if name else str(session_id))
            if formatted_examples:
                lines.append(f"- Named examples: {', '.join(formatted_examples)}")

        oldest_session_id = provider_payload.get("oldest_session_id")
        oldest_session_at = provider_payload.get("oldest_session_at")
        if oldest_session_id is not None:
            oldest_text = str(oldest_session_id)
            oldest_name = provider_payload.get("oldest_session_name")
            if oldest_name is not None:
                oldest_text += f" [{oldest_name}]"
            if oldest_session_at is not None:
                oldest_text += f" ({oldest_session_at})"
            lines.append(f"- Oldest: {oldest_text}")

        latest_session_id = provider_payload.get("latest_session_id")
        latest_session_at = provider_payload.get("latest_session_at")
        if latest_session_id is not None:
            latest_text = str(latest_session_id)
            latest_name = provider_payload.get("latest_session_name")
            if latest_name is not None:
                latest_text += f" [{latest_name}]"
            if latest_session_at is not None:
                latest_text += f" ({latest_session_at})"
            lines.append(f"- Latest: {latest_text}")

    return "\n".join(lines)


def format_chat_session_resolved_stats_markdown(payload: dict[str, object]) -> str:
    lines = ["# Chat Session Stats", ""]

    selection = payload.get("selection")
    query = None
    if isinstance(selection, dict):
        query = selection.get("query")
    if query is not None:
        lines.append(f"- Query: {query}")

    session = payload.get("session")
    if isinstance(session, dict):
        provider = session.get("provider")
        if provider is not None:
            lines.append(f"- Provider: {provider}")

        uri = session.get("uri")
        if uri is not None:
            lines.append(f"- URI: {uri}")

        fingerprint = session.get("provider_instance_fingerprint")
        if fingerprint is not None:
            lines.append(f"- Provider instance: {fingerprint}")

        session_id = session.get("session_id")
        if session_id is not None:
            lines.append(f"- Session ID: {session_id}")

        match = session.get("match")
        if isinstance(match, dict):
            match_fields = match.get("fields")
            if isinstance(match_fields, list) and match_fields:
                formatted_fields = [
                    str(field.get("field"))
                    for field in match_fields
                    if isinstance(field, dict) and field.get("field") is not None
                ]
                if formatted_fields:
                    lines.append(f"- Matched by: {', '.join(formatted_fields)}")

        display_name = session.get("display_name")
        if display_name is not None:
            lines.append(f"- Name: {display_name}")

        created_at = session.get("created_at")
        if created_at is not None:
            lines.append(f"- Created at: {created_at}")

        updated_at = session.get("updated_at")
        if updated_at is not None:
            lines.append(f"- Updated at: {updated_at}")

        lines.append(f"- Extractable: {'yes' if session.get('extractable') else 'no'}")

        primary_artifact = session.get("primary_backing_artifact")
        if isinstance(primary_artifact, dict):
            primary_artifact_path = primary_artifact.get("path")
            if primary_artifact_path is not None:
                lines.append(f"- Primary backing artifact: {primary_artifact_path}")

        backing_artifact_count = session.get("backing_artifact_count")
        if backing_artifact_count is not None:
            lines.append(f"- Backing artifacts: {backing_artifact_count}")

    provider_stats = payload.get("stats")
    provider_name = None
    if isinstance(session, dict):
        provider_name = session.get("provider")
    if isinstance(provider_stats, dict):
        lines.extend(["", f"## {provider_name or 'provider'}", ""])
        for key, value in provider_stats.items():
            if value is None:
                continue
            if isinstance(value, bool):
                value = "yes" if value else "no"
            lines.append(f"- {_format_provider_stats_label(key)}: {value}")

    return "\n".join(lines)


def find_chat_session(
    query: str,
    *,
    include_artifacts: bool = False,
    include_grep: bool = False,
    full_output: bool = False,
    providers: tuple[str, ...] | None = None,
) -> dict[str, object]:
    provider_groups = _iter_provider_context_groups(providers)
    sessions = resolve_chat_sessions(query, providers=providers)
    search_findings: list[dict[str, Any]] = []
    search_findings_seen_keys: set[tuple[object, ...]] = set()
    provider_payloads: list[dict[str, Any]] = []
    sessions_by_provider: dict[str, list[ChatSession]] = {}
    search_findings_by_provider: dict[str, list[dict[str, Any]]] = {}

    for session in sessions:
        sessions_by_provider.setdefault(session.provider_family, []).append(session)

    for provider_family, contexts in provider_groups:
        provider_search_findings: list[dict[str, Any]] = []
        provider_seen_keys: set[tuple[object, ...]] = set()

        if include_grep:
            for context in contexts:
                for target in context.grep_existing_targets:
                    for finding in _scan_grep_findings(
                        provider=provider_family.family,
                        target=target,
                        session_id=query,
                    ):
                        _append_unique_finding(provider_search_findings, provider_seen_keys, finding)
                        _append_unique_finding(search_findings, search_findings_seen_keys, finding)

        search_findings_by_provider[provider_family.family] = _sort_findings(provider_search_findings)
        provider_payload = _build_provider_payload(
            provider_family=provider_family.family,
            contexts=contexts,
            include_grep=include_grep,
            item_count_key="session_count",
            item_count=len(sessions_by_provider.get(provider_family.family, [])),
        )
        if include_grep:
            provider_payload["search_finding_count"] = len(
                search_findings_by_provider[provider_family.family]
            )
        provider_payloads.append(provider_payload)

    expansions = ["match"]
    if include_artifacts:
        expansions.append("backing_artifacts")
    if include_grep:
        expansions.append("search_findings")

    payload: dict[str, object] = {
        "status": "ok",
        "command": "chat session find",
        "selection": {
            "kind": "query",
            "query": query,
            "providers": list(providers) if providers is not None else None,
        },
        "expansions": expansions,
        "session_count": len(sessions),
        "sessions": [
            _build_common_session_stats(
                session,
                query=query,
                include_artifacts=include_artifacts,
            )
            for session in sessions
        ],
    }
    if include_grep:
        payload["search_finding_count"] = len(search_findings)
        payload["search_findings"] = _sort_findings(search_findings)
    if full_output:
        payload["provider_diagnostics"] = provider_payloads
    return payload


def resolve_chat_sessions(
    query: str,
    *,
    providers: tuple[str, ...] | None = None,
) -> list[ChatSession]:
    resolved_sessions: list[ChatSession] = []
    for _, contexts in _iter_provider_context_groups(providers):
        for context in contexts:
            resolved_sessions.extend(_find_direct_provider_sessions(context, query))
    return _sort_sessions(_dedupe_sessions(resolved_sessions), "lexical")


def _iter_provider_context_groups(
    providers: tuple[str, ...] | None,
) -> tuple[tuple[SessionProviderHandler, tuple[SessionProviderContext, ...]], ...]:
    provider_instances = configured_provider_instances()
    if providers is not None:
        requested_providers = set(providers)
        provider_instances = tuple(
            provider_instance
            for provider_instance in provider_instances
            if provider_instance.family in requested_providers
        )

    contexts_by_family: dict[str, list[SessionProviderContext]] = {}
    for provider_instance in provider_instances:
        context = _build_provider_context(provider_instance)
        contexts_by_family.setdefault(provider_instance.family, []).append(context)

    groups: list[tuple[SessionProviderHandler, tuple[SessionProviderContext, ...]]] = []
    for provider_handler in supported_provider_families():
        family_contexts = contexts_by_family.get(provider_handler.family)
        if not family_contexts:
            continue
        groups.append((provider_handler, tuple(family_contexts)))
    return tuple(groups)


def _build_provider_context(provider_instance: ProviderInstance) -> SessionProviderContext:
    provider_handler = _provider_family_for_name(provider_instance.family)
    if provider_handler is None:
        raise CliError(f"unsupported provider family {provider_instance.family}")

    direct_targets = provider_instance.direct_targets
    grep_targets = provider_instance.grep_targets
    sqlite_db_paths = provider_instance.sqlite_db_paths

    return SessionProviderContext(
        provider_handler=provider_handler,
        provider_instance=provider_instance,
        direct_targets=direct_targets,
        direct_existing_targets=tuple(target for target in direct_targets if target.exists()),
        direct_missing_targets=tuple(target for target in direct_targets if not target.exists()),
        grep_targets=grep_targets,
        grep_existing_targets=tuple(target for target in grep_targets if target.exists()),
        grep_missing_targets=tuple(target for target in grep_targets if not target.exists()),
        sqlite_db_paths=sqlite_db_paths,
        sqlite_existing_db_paths=tuple(path for path in sqlite_db_paths if path.exists()),
        sqlite_missing_db_paths=tuple(path for path in sqlite_db_paths if not path.exists()),
    )


def _find_session_for_provider(
    *,
    provider_family: str,
    contexts: tuple[SessionProviderContext, ...],
    query: str,
    include_grep: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen_keys: set[tuple[object, ...]] = set()

    for context in contexts:
        direct_sessions = _find_direct_provider_sessions(context, query)
        for session in direct_sessions:
            for finding in _session_findings(session, query=query):
                _append_unique_finding(findings, seen_keys, finding)

        if include_grep:
            for target in context.grep_existing_targets:
                for finding in _scan_grep_findings(
                    provider=provider_family,
                    target=target,
                    session_id=query,
                ):
                    _append_unique_finding(findings, seen_keys, finding)

    payload = _build_provider_payload(
        provider_family=provider_family,
        contexts=contexts,
        include_grep=include_grep,
        item_count_key="finding_count",
        item_count=len(findings),
    )
    return _sort_findings(findings), payload


def _build_provider_payload(
    *,
    provider_family: str,
    contexts: tuple[SessionProviderContext, ...],
    include_grep: bool,
    item_count_key: str,
    item_count: int,
) -> dict[str, Any]:
    direct_targets = _unique_paths(
        tuple(path for context in contexts for path in context.direct_targets)
    )
    direct_existing_targets = _unique_paths(
        tuple(path for context in contexts for path in context.direct_existing_targets)
    )
    direct_missing_targets = _unique_paths(
        tuple(path for context in contexts for path in context.direct_missing_targets)
    )
    grep_targets = _unique_paths(
        tuple(path for context in contexts for path in context.grep_targets)
    )
    grep_existing_targets = _unique_paths(
        tuple(path for context in contexts for path in context.grep_existing_targets)
    )
    grep_missing_targets = _unique_paths(
        tuple(path for context in contexts for path in context.grep_missing_targets)
    )
    sqlite_db_paths = _unique_paths(
        tuple(path for context in contexts for path in context.sqlite_db_paths)
    )
    sqlite_existing_db_paths = _unique_paths(
        tuple(path for context in contexts for path in context.sqlite_existing_db_paths)
    )
    sqlite_missing_db_paths = _unique_paths(
        tuple(path for context in contexts for path in context.sqlite_missing_db_paths)
    )

    if include_grep:
        candidate_targets = _unique_paths(direct_targets + grep_targets)
        searched_targets = _unique_paths(direct_existing_targets + grep_existing_targets)
        missing_targets = _unique_paths(direct_missing_targets + grep_missing_targets)
    else:
        candidate_targets = direct_targets
        searched_targets = direct_existing_targets
        missing_targets = direct_missing_targets

    payload = {
        "provider": provider_family,
        "provider_family": provider_family,
        "provider_instance_count": len(contexts),
        "provider_instances": [context.provider_instance.summary() for context in contexts],
        "candidate_targets": [str(path) for path in candidate_targets],
        "searched_targets": [str(path) for path in searched_targets],
        "missing_targets": [str(path) for path in missing_targets],
        "sqlite_db_paths": [str(path) for path in sqlite_db_paths],
        "sqlite_existing_db_paths": [str(path) for path in sqlite_existing_db_paths],
        "sqlite_missing_db_paths": [str(path) for path in sqlite_missing_db_paths],
        "sqlite_db_path": (
            str(sqlite_db_paths[0]) if len(sqlite_db_paths) == 1 else None
        ),
        "sqlite_db_exists": (
            sqlite_db_paths[0].exists() if len(sqlite_db_paths) == 1 else None
        ),
        "strategies_attempted": _strategies_attempted(contexts, include_grep=include_grep),
        item_count_key: item_count,
    }
    return payload


def _build_stats_provider_payload(
    *,
    provider_family: str,
    contexts: tuple[SessionProviderContext, ...],
    sessions: list[ChatSession],
) -> dict[str, Any]:
    extractable_sessions = [session for session in sessions if _session_is_extractable(session)]
    timestamps = [
        (session, session.sort_timestamp())
        for session in sessions
        if session.sort_timestamp() is not None
    ]
    timestamps.sort(key=lambda item: (item[1] or 0.0, item[0].session_id))

    return {
        "provider": provider_family,
        "session_count": len(sessions),
        "extractable_session_count": len(extractable_sessions),
        "non_extractable_session_count": len(sessions) - len(extractable_sessions),
        "backing_artifact_count": sum(len(session.backing_artifacts()) for session in sessions),
        "session_id_examples": [session.session_id for session in sessions[:3]],
        "session_examples": [_session_summary(session) for session in sessions[:3]],
        "oldest_session_id": timestamps[0][0].session_id if timestamps else None,
        "oldest_session_name": _session_display_name(timestamps[0][0]) if timestamps else None,
        "oldest_session_at": _format_stats_timestamp(timestamps[0][1]) if timestamps else None,
        "latest_session_id": timestamps[-1][0].session_id if timestamps else None,
        "latest_session_name": _session_display_name(timestamps[-1][0]) if timestamps else None,
        "latest_session_at": _format_stats_timestamp(timestamps[-1][1]) if timestamps else None,
    }


def _session_native_payload(session: ChatSession) -> dict[str, Any]:
    payload = dict(session.native_fields())
    payload.pop("session_id", None)
    return payload


def _matched_query_fields(
    session: ChatSession,
    *,
    query: str,
) -> tuple[tuple[str, str], ...]:
    uri_query = _parse_chat_session_uri(query)
    if uri_query is not None and _session_matches_uri_query(session, uri_query):
        return (("uri", session.uri),)

    matched_fields: list[tuple[str, str]] = []
    seen_fields: set[tuple[str, str]] = set()
    for field_name, value in session.query_fields():
        if value != query:
            continue
        key = (field_name, value)
        if key in seen_fields:
            continue
        seen_fields.add(key)
        matched_fields.append(key)
    return tuple(matched_fields)


def _build_session_match_payload(
    session: ChatSession,
    *,
    query: str,
) -> dict[str, Any]:
    matched_fields = _matched_query_fields(session, query=query)
    if not matched_fields:
        matched_fields = ((session.matched_field(query), query),)

    return {
        "query": query,
        "kind": "exact_identity",
        "fields": [
            {
                "field": field_name,
                "value": value,
            }
            for field_name, value in matched_fields
        ],
    }


def _backing_artifact_is_extractable(
    session: ChatSession,
    artifact: BackingArtifact,
) -> bool:
    path = artifact.path
    if not path.exists() or path.is_dir():
        return False

    try:
        if session.provider == "claude-code":
            from agentos.chat.extractors.claude_code import is_claude_code_session_path

            return is_claude_code_session_path(path)
        if session.provider == "codex":
            from agentos.chat.extractors.codex import is_codex_rollout_path

            return is_codex_rollout_path(path)
        if session.provider == "copilot-cli":
            from agentos.chat.extractors.copilot_cli import is_copilot_cli_session_path

            return is_copilot_cli_session_path(path)
        if session.provider == "gemini-cli":
            from agentos.chat.extractors.gemini_cli import is_gemini_cli_session_path

            return is_gemini_cli_session_path(path)
        if session.provider == "openclaw":
            from agentos.chat.extractors.openclaw import is_openclaw_session_path

            return is_openclaw_session_path(path)
        if session.provider == "opencode":
            from agentos.chat.extractors.opencode import is_opencode_session_path

            return is_opencode_session_path(path)
    except CliError:
        return False

    return False


def _serialize_backing_artifact(
    session: ChatSession,
    artifact: BackingArtifact,
) -> dict[str, Any]:
    return artifact.summary(
        extractable=_backing_artifact_is_extractable(session, artifact),
    )


def _created_timestamp_from_turns(turns: list[Any]) -> float | None:
    for turn in turns:
        timestamp = coerce_timestamp(getattr(turn, "timestamp", None))
        if timestamp is not None:
            return timestamp
    return None


def _session_created_timestamp(session: ChatSession) -> float | None:
    created_at = session.created_timestamp()
    if created_at is not None:
        return created_at

    artifact = session.primary_artifact_path()
    if artifact is None or not artifact.exists():
        return None

    try:
        if session.provider == "codex":
            from agentos.chat.extractors.codex import extract_dialog_from_codex_rollout

            return _created_timestamp_from_turns(extract_dialog_from_codex_rollout(artifact, raw=False))

        if session.provider == "claude-code":
            if artifact.suffix == ".jsonl":
                from agentos.chat.extractors.claude_code import extract_dialog_from_claude_code_session

                return _created_timestamp_from_turns(
                    extract_dialog_from_claude_code_session(artifact, raw=False)
                )
            if artifact.suffix == ".json":
                obj = json.loads(artifact.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(obj, dict):
                    return coerce_timestamp(obj.get("createdAt")) or coerce_timestamp(obj.get("lastActivityAt"))
                return None

        if session.provider == "copilot-cli":
            from agentos.chat.extractors.copilot_cli import load_copilot_cli_events

            events = load_copilot_cli_events(artifact)
            first_event_timestamp: float | None = None
            for event in events:
                timestamp = coerce_timestamp(event.get("timestamp"))
                if timestamp is not None and first_event_timestamp is None:
                    first_event_timestamp = timestamp
                if event.get("type") == "session.start":
                    return timestamp
            return first_event_timestamp

        if session.provider == "gemini-cli":
            from agentos.chat.extractors.gemini_cli import load_gemini_cli_session_data

            session_data = load_gemini_cli_session_data(artifact)
            if not isinstance(session_data, dict):
                return None
            return coerce_timestamp(session_data.get("startTime"))

        if session.provider == "openclaw":
            from agentos.chat.extractors.openclaw import load_openclaw_session_records

            records = load_openclaw_session_records(artifact)
            if not records:
                return None
            return coerce_timestamp(records[0].get("timestamp"))

        if session.provider == "opencode":
            from agentos.chat.extractors.opencode import load_opencode_session_messages, resolve_opencode_db_path

            db_path = artifact if artifact.name == "opencode.db" else resolve_opencode_db_path(artifact)
            messages = load_opencode_session_messages(db_path=db_path, session_id=session.session_id)
            if not messages:
                return None
            return coerce_timestamp(messages[0].get("time_created"))
    except (CliError, OSError, json.JSONDecodeError):
        return None

    return None


def _build_common_session_stats(
    session: ChatSession,
    *,
    query: str | None = None,
    include_artifacts: bool = False,
) -> dict[str, Any]:
    backing_artifacts = session.backing_artifacts()
    primary_backing_artifact = session.primary_backing_artifact()
    payload = {
        "provider": session.provider,
        "uri": session.uri,
        "provider_instance_fingerprint": session.provider_instance.fingerprint,
        "session_id": session.session_id,
        "display_name": _session_display_name(session),
        "display_name_field": _session_display_field_name(session),
        "created_at": _format_stats_timestamp(_session_created_timestamp(session)),
        "updated_at": _format_stats_timestamp(session.sort_timestamp()),
        "extractable": _session_is_extractable(session),
        "backing_artifact_count": len(backing_artifacts),
        "primary_backing_artifact": (
            _serialize_backing_artifact(session, primary_backing_artifact)
            if primary_backing_artifact is not None
            else None
        ),
        "native": _session_native_payload(session),
    }
    if query is not None:
        payload["match"] = _build_session_match_payload(session, query=query)
    if include_artifacts:
        payload["backing_artifacts"] = [
            _serialize_backing_artifact(session, artifact)
            for artifact in backing_artifacts
        ]
    return payload


def _build_provider_session_stats(session: ChatSession) -> dict[str, Any]:
    provider_family = _provider_family_for_name(session.provider_family)
    if provider_family is None:
        raise CliError(f"chat session stats is not implemented for provider {session.provider_family}")
    return provider_family.build_source_stats(session.source)


def _parse_chat_session_uri(query: str) -> ChatSessionUriQuery | None:
    prefix = "agentos://chat-session/"
    if not query.startswith(prefix):
        return None

    remainder = query[len(prefix):]
    parts = remainder.split("/", 2)
    if len(parts) != 3:
        return None

    provider_family, instance_fingerprint_prefix, session_id = (unquote(part) for part in parts)
    if not provider_family or not instance_fingerprint_prefix or not session_id:
        return None
    return ChatSessionUriQuery(
        provider_family=provider_family,
        instance_fingerprint_prefix=instance_fingerprint_prefix.lower(),
        session_id=session_id,
    )


def _session_matches_uri_query(
    session: ChatSession,
    uri_query: ChatSessionUriQuery,
) -> bool:
    return (
        session.provider_family == uri_query.provider_family
        and session.session_id == uri_query.session_id
        and session.provider_instance.matches_fingerprint_prefix(uri_query.instance_fingerprint_prefix)
    )


def _strategies_attempted(
    contexts: tuple[SessionProviderContext, ...],
    *,
    include_grep: bool,
) -> list[str]:
    strategies = ["path"]
    if any(context.sqlite_db_paths for context in contexts):
        strategies.append("sqlite")
    if include_grep:
        strategies.append("grep")
    return strategies


def _discover_direct_provider_sessions(context: SessionProviderContext) -> list[ChatSession]:
    return context.provider_handler.discover_sessions(context)


def _find_direct_provider_sessions(
    context: SessionProviderContext,
    query: str,
) -> list[ChatSession]:
    uri_query = _parse_chat_session_uri(query)
    if uri_query is not None:
        if context.provider_handler.family != uri_query.provider_family:
            return []
        if not context.provider_instance.matches_fingerprint_prefix(uri_query.instance_fingerprint_prefix):
            return []
        return [
            session
            for session in _discover_direct_provider_sessions(context)
            if _session_matches_uri_query(session, uri_query)
        ]
    return context.provider_handler.find_sessions(context, query)


def _wrap_session_sources(session_sources: list[SessionSource]) -> list[ChatSession]:
    return [ChatSession(source=source) for source in session_sources]


def _list_claude_code_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
) -> list[SessionSource]:
    sessions: list[SessionSource] = []

    for target in targets:
        if target.name == "projects":
            for path in _glob_paths(target, "**/*.jsonl"):
                session = _read_claude_project_session(path, provider_instance=provider_instance)
                if session is not None:
                    sessions.append(session)
            continue

        for path in _glob_paths(target, "**/*.json"):
            session = _read_claude_desktop_session(path, provider_instance=provider_instance)
            if session is not None:
                sessions.append(session)

    return _dedupe_session_sources(sessions)


def _find_claude_code_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
    query: str,
) -> list[SessionSource]:
    sessions_by_id: dict[tuple[object, ...], SessionSource] = {}
    all_sessions = _list_claude_code_sessions(provider_instance=provider_instance, targets=targets)

    for session in all_sessions:
        if session.matches_query(query):
            _merge_session_source(sessions_by_id, session)

    return _sort_session_sources(list(sessions_by_id.values()), "lexical")


def _list_codex_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
) -> list[SessionSource]:
    sessions_by_id: dict[tuple[object, ...], SessionSource] = {}

    for target in targets:
        if target.is_file() and target.name == "session_index.jsonl":
            for session in _read_codex_index_sessions(target, provider_instance=provider_instance):
                _merge_session_source(sessions_by_id, session)
            continue
        for path in _glob_paths(target, "**/rollout-*.jsonl"):
            session = _read_codex_rollout_session(path, provider_instance=provider_instance)
            if session is not None:
                _merge_session_source(sessions_by_id, session)

    return _sort_session_sources(list(sessions_by_id.values()), "lexical")


def _find_codex_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
    query: str,
) -> list[SessionSource]:
    sessions_by_id: dict[tuple[object, ...], SessionSource] = {}
    all_sessions = _list_codex_sessions(provider_instance=provider_instance, targets=targets)

    for session in all_sessions:
        if session.matches_query(query):
            _merge_session_source(sessions_by_id, session)

    return _sort_session_sources(list(sessions_by_id.values()), "lexical")


def _list_copilot_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
) -> list[SessionSource]:
    sessions_by_id: dict[tuple[object, ...], SessionSource] = {}

    for target in targets:
        if not target.is_dir():
            continue

        for child in sorted(target.iterdir(), key=lambda path: path.name):
            session: SessionSource | None = None
            if child.is_dir():
                session = CopilotCliSessionSource(
                    provider_instance=provider_instance,
                    native_session_id=child.name,
                    session_root=child,
                    updated_at=_copilot_updated_at(child),
                )
            elif child.is_file() and child.suffix == ".jsonl":
                session = CopilotCliSessionSource(
                    provider_instance=provider_instance,
                    native_session_id=child.stem,
                    session_file=child,
                    updated_at=safe_path_mtime(child),
                )

            if session is not None:
                _merge_session_source(sessions_by_id, session)

    return _sort_session_sources(list(sessions_by_id.values()), "lexical")


def _find_copilot_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[SessionSource]:
    sessions: list[SessionSource] = []

    for target in targets:
        session_root = target / session_id
        session_file = target / f"{session_id}.jsonl"
        if not session_root.is_dir() and not session_file.is_file():
            continue

        sessions.append(
            CopilotCliSessionSource(
                provider_instance=provider_instance,
                native_session_id=session_id,
                session_root=session_root if session_root.is_dir() else None,
                session_file=session_file if session_file.is_file() else None,
                updated_at=_copilot_updated_at(session_root if session_root.is_dir() else None)
                or safe_path_mtime(session_file if session_file.is_file() else None),
            )
        )

    return _dedupe_session_sources(sessions)


def _list_gemini_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
) -> list[SessionSource]:
    sessions: list[SessionSource] = []

    for target in targets:
        for path in _glob_paths(target, "**/chats/session-*.json"):
            session = _read_gemini_session(path, provider_instance=provider_instance)
            if session is not None:
                sessions.append(session)

    return _dedupe_session_sources(sessions)


def _find_gemini_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[SessionSource]:
    sessions: list[SessionSource] = []

    for target in targets:
        for path in _glob_paths(target, "**/chats/session-*.json"):
            session = _read_gemini_session(path, provider_instance=provider_instance)
            if session is None:
                continue
            if not _gemini_session_matches(session_id, session, path):
                continue
            sessions.append(session)

    return _dedupe_session_sources(sessions)


def _list_opencode_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
    sqlite_db_paths: tuple[Path, ...],
) -> list[SessionSource]:
    sessions_by_id: dict[tuple[object, ...], SessionSource] = {}

    for target in targets:
        for path in _glob_paths(target, "*.json"):
            _merge_session_source(
                sessions_by_id,
                OpencodeSessionSource(
                    provider_instance=provider_instance,
                    native_session_id=path.stem,
                    diff_path=path,
                    updated_at=safe_path_mtime(path),
                ),
            )

    for sqlite_db_path in sqlite_db_paths:
        for session in _query_opencode_sessions(sqlite_db_path, provider_instance=provider_instance):
            _merge_session_source(sessions_by_id, session)

    return _sort_session_sources(list(sessions_by_id.values()), "lexical")


def _find_opencode_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
    session_id: str,
    sqlite_db_paths: tuple[Path, ...],
) -> list[SessionSource]:
    sessions_by_id: dict[tuple[object, ...], SessionSource] = {}

    for target in targets:
        session_file = target / f"{session_id}.json"
        if session_file.is_file():
            _merge_session_source(
                sessions_by_id,
                OpencodeSessionSource(
                    provider_instance=provider_instance,
                    native_session_id=session_id,
                    diff_path=session_file,
                    updated_at=safe_path_mtime(session_file),
                ),
            )

    for sqlite_db_path in sqlite_db_paths:
        for session in _query_opencode_sessions(
            sqlite_db_path,
            provider_instance=provider_instance,
            session_id=session_id,
        ):
            _merge_session_source(sessions_by_id, session)

    return _sort_session_sources(list(sessions_by_id.values()), "lexical")


def _list_openclaw_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
) -> list[SessionSource]:
    sessions_by_id: dict[tuple[object, ...], SessionSource] = {}

    for target in targets:
        for agent_dir in _iter_openclaw_agent_dirs(target):
            for session in _read_openclaw_agent_sessions(agent_dir, provider_instance=provider_instance):
                _merge_session_source(sessions_by_id, session)

    return _sort_session_sources(list(sessions_by_id.values()), "lexical")


def _find_openclaw_sessions(
    *,
    provider_instance: ProviderInstance,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[SessionSource]:
    sessions_by_id: dict[tuple[object, ...], SessionSource] = {}

    for target in targets:
        for agent_dir in _iter_openclaw_agent_dirs(target):
            for session in _read_openclaw_agent_sessions(agent_dir, provider_instance=provider_instance):
                if session.session_id != session_id and session_id not in session.session_keys:
                    continue
                _merge_session_source(sessions_by_id, session)

    return _sort_session_sources(list(sessions_by_id.values()), "lexical")


def _append_unique_finding(
    findings: list[dict[str, Any]],
    seen_keys: set[tuple[object, ...]],
    finding: dict[str, Any],
) -> None:
    key = (
        finding.get("provider"),
        finding.get("match_kind"),
        finding.get("path"),
        finding.get("line_number"),
        finding.get("strategy"),
    )
    if key in seen_keys:
        return
    seen_keys.add(key)
    findings.append(finding)


def _session_summary(session: ChatSession) -> dict[str, Any]:
    return _build_common_session_stats(session)


def _session_display_name(session: ChatSession) -> str | None:
    return session.display_name()


def _session_display_field_name(session: ChatSession) -> str | None:
    return session.display_name_field()


def _session_findings(
    session: ChatSession,
    *,
    query: str,
) -> tuple[dict[str, Any], ...]:
    findings: list[dict[str, Any]] = []
    matched_field = _matched_field_name(session, query=query)
    for finding in session.canonical_findings():
        enriched = dict(finding)
        enriched["matched_field"] = matched_field
        enriched["matched_value"] = query
        enriched["session_id"] = session.session_id
        enriched["uri"] = session.uri
        enriched["provider_instance_fingerprint"] = session.provider_instance.fingerprint
        enriched["native"] = _session_native_payload(session)
        findings.append(enriched)

    if findings:
        return tuple(findings)

    return session.supplemental_findings(query=query, matched_field=matched_field)


def _matched_field_name(session: ChatSession, *, query: str) -> str:
    matched_fields = _matched_query_fields(session, query=query)
    if matched_fields:
        return matched_fields[0][0]
    return session.matched_field(query)


def _merge_session(
    sessions_by_id: dict[str, ChatSession],
    session: ChatSession,
) -> None:
    session_key = session.uri
    existing = sessions_by_id.get(session_key)
    if existing is None:
        sessions_by_id[session_key] = session
        return

    if type(existing.source) is type(session.source):
        sessions_by_id[session_key] = existing.merge(session)
        return

    if _session_preference_key(session) > _session_preference_key(existing):
        sessions_by_id[session_key] = session


def _dedupe_sessions(sessions: list[ChatSession]) -> list[ChatSession]:
    deduped: dict[str, ChatSession] = {}
    for session in sessions:
        _merge_session(deduped, session)
    return _sort_sessions(list(deduped.values()), "lexical")


def _sort_sessions(sessions: list[ChatSession], sort: str) -> list[ChatSession]:
    _validate_sort_choice(sort)

    if sort == "lexical":
        sessions.sort(key=lambda session: session.session_id)
        return sessions

    if sort == "newest":
        sessions.sort(
            key=lambda session: (
                session.sort_timestamp() is None,
                -(session.sort_timestamp() or 0.0),
                session.session_id,
            )
        )
        return sessions

    sessions.sort(
        key=lambda session: (
            session.sort_timestamp() is None,
            session.sort_timestamp() or 0.0,
            session.session_id,
        )
    )
    return sessions


def _session_preference_key(session: ChatSession) -> tuple[float, int, str]:
    timestamp = session.sort_timestamp()
    return (
        timestamp if timestamp is not None else float("-inf"),
        len(session.canonical_findings()),
        str(session.primary_artifact_path() or ""),
    )


def _merge_session_source(
    sessions_by_id: dict[tuple[object, ...], SessionSource],
    session: SessionSource,
) -> None:
    session_key = session.source_identity_key()
    existing = sessions_by_id.get(session_key)
    if existing is None:
        sessions_by_id[session_key] = session
        return

    if type(existing) is type(session):
        sessions_by_id[session_key] = existing.merge(session)
        return

    if _session_source_preference_key(session) > _session_source_preference_key(existing):
        sessions_by_id[session_key] = session


def _dedupe_session_sources(sessions: list[SessionSource]) -> list[SessionSource]:
    deduped: dict[tuple[object, ...], SessionSource] = {}
    for session in sessions:
        _merge_session_source(deduped, session)
    return _sort_session_sources(list(deduped.values()), "lexical")


def _sort_session_sources(sessions: list[SessionSource], sort: str) -> list[SessionSource]:
    _validate_sort_choice(sort)

    if sort == "lexical":
        sessions.sort(key=lambda session: session.session_id)
        return sessions

    if sort == "newest":
        sessions.sort(
            key=lambda session: (
                session.sort_timestamp() is None,
                -(session.sort_timestamp() or 0.0),
                session.session_id,
            )
        )
        return sessions

    sessions.sort(
        key=lambda session: (
            session.sort_timestamp() is None,
            session.sort_timestamp() or 0.0,
            session.session_id,
        )
    )
    return sessions


def _session_source_preference_key(session: SessionSource) -> tuple[float, int, str]:
    timestamp = session.sort_timestamp()
    return (
        timestamp if timestamp is not None else float("-inf"),
        len(session.canonical_findings()),
        str(session.primary_artifact_path() or ""),
    )


def _session_matches_list_filters(
    session: ChatSession,
    *,
    extractable_only: bool,
    updated_after: float | None,
) -> bool:
    if extractable_only and not _session_is_extractable(session):
        return False
    if updated_after is not None:
        timestamp = session.sort_timestamp()
        if timestamp is None or timestamp < updated_after:
            return False
    return True


def _format_provider_stats_label(key: str) -> str:
    labels = {
        "agent_id": "Agent id",
        "artifact_count": "Artifacts",
        "assistant_message_count": "Assistant messages",
        "assistant_message_event_count": "Assistant message events",
        "assistant_turn_count": "Assistant turns",
        "developer_message_count": "Developer messages",
        "dialog_turn_count": "Dialog turns",
        "event_count": "Events",
        "event_message_count": "Event messages",
        "first_event_at": "First event",
        "first_message_at": "First message",
        "first_record_at": "First record",
        "first_turn_at": "First turn",
        "has_diff_artifact": "Has diff artifact",
        "has_extractable_artifact": "Has extractable artifact",
        "has_rollout_artifact": "Has rollout artifact",
        "has_sessions_index": "Has sessions index",
        "has_sqlite_db": "Has sqlite db",
        "has_transcript": "Has transcript",
        "last_event_at": "Last event",
        "last_message_at": "Last message",
        "last_record_at": "Last record",
        "last_turn_at": "Last turn",
        "last_updated": "Last updated",
        "message_count": "Messages",
        "message_record_count": "Message records",
        "non_text_part_count": "Non-text parts",
        "part_count": "Parts",
        "reasoning_item_count": "Reasoning items",
        "record_count": "Records",
        "response_item_count": "Response items",
        "rollout_artifact_count": "Rollout artifacts",
        "session_file_present": "Session file present",
        "session_index_count": "Session indexes",
        "session_key_count": "Session keys",
        "session_meta_count": "Session meta records",
        "session_record_count": "Session records",
        "session_root_present": "Session root present",
        "session_start_count": "Session starts",
        "skill_invoked_count": "Skills invoked",
        "source_kind": "Source kind",
        "start_time": "Start time",
        "text_part_count": "Text parts",
        "thought_count": "Thoughts",
        "tool_call_count": "Tool calls",
        "tool_call_output_count": "Tool call outputs",
        "tool_event_count": "Tool events",
        "user_message_count": "User messages",
        "user_message_event_count": "User message events",
        "user_turn_count": "User turns",
    }
    return labels.get(key, key.replace("_", " ").capitalize())


def _build_dialog_turn_stats(turns: list[Any]) -> dict[str, Any]:
    return {
        "dialog_turn_count": len(turns),
        "user_turn_count": sum(1 for turn in turns if getattr(turn, "role", None) == "user"),
        "assistant_turn_count": sum(1 for turn in turns if getattr(turn, "role", None) == "assistant"),
        "first_turn_at": turns[0].timestamp if turns else None,
        "last_turn_at": turns[-1].timestamp if turns else None,
    }


def _update_time_bounds(
    first_timestamp: float | None,
    last_timestamp: float | None,
    value: object,
) -> tuple[float | None, float | None]:
    timestamp = coerce_timestamp(value)
    if timestamp is None:
        return first_timestamp, last_timestamp
    if first_timestamp is None or timestamp < first_timestamp:
        first_timestamp = timestamp
    if last_timestamp is None or timestamp > last_timestamp:
        last_timestamp = timestamp
    return first_timestamp, last_timestamp


def _try_provider_stats_call(callback: Callable[[], Any]) -> Any | None:
    try:
        return callback()
    except (CliError, OSError):
        return None


def _try_build_dialog_turn_stats(callback: Callable[[], list[Any]]) -> dict[str, Any]:
    turns = _try_provider_stats_call(callback)
    if not isinstance(turns, list):
        return {}
    return _build_dialog_turn_stats(turns)


def _build_claude_code_session_stats(session: ClaudeCodeSessionSource) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifact_count": len(session.artifact_paths),
        "source_kind": session.source_kind,
        "has_extractable_artifact": False,
    }

    from agentos.chat.extractors.claude_code import (
        extract_dialog_from_claude_code_session,
        is_claude_code_session_path,
    )

    artifact_path = next(
        (path for path in session.artifact_paths if path.is_file() and is_claude_code_session_path(path)),
        None,
    )
    if artifact_path is None:
        return payload

    payload["has_extractable_artifact"] = True
    record_count = 0

    try:
        with artifact_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue

                record_count += 1
    except OSError:
        return payload

    turns = _try_provider_stats_call(
        lambda: extract_dialog_from_claude_code_session(artifact_path, raw=False)
    )
    if not isinstance(turns, list):
        return payload

    turn_stats = _build_dialog_turn_stats(turns)
    payload.update(
        {
            "record_count": record_count,
            "message_record_count": turn_stats["dialog_turn_count"],
            "user_message_count": turn_stats["user_turn_count"],
            "assistant_message_count": turn_stats["assistant_turn_count"],
            "first_record_at": turn_stats["first_turn_at"],
            "last_record_at": turn_stats["last_turn_at"],
            **turn_stats,
        }
    )
    return payload


def _build_codex_session_stats(session: CodexSessionSource) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rollout_artifact_count": len(session.artifact_paths),
        "session_index_count": len(session.index_paths),
        "has_rollout_artifact": _session_is_extractable(session),
    }

    artifact_path = session.primary_artifact_path()
    if artifact_path is None or not artifact_path.is_file():
        return payload

    record_count = 0
    session_meta_count = 0
    response_item_count = 0
    event_message_count = 0
    message_count = 0
    user_message_count = 0
    assistant_message_count = 0
    developer_message_count = 0
    tool_call_count = 0
    tool_call_output_count = 0
    reasoning_item_count = 0
    first_record_at: float | None = None
    last_record_at: float | None = None

    try:
        with artifact_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue

                record_count += 1
                first_record_at, last_record_at = _update_time_bounds(
                    first_record_at,
                    last_record_at,
                    obj.get("timestamp"),
                )

                record_type = obj.get("type")
                if record_type == "session_meta":
                    session_meta_count += 1
                    continue
                if record_type == "event_msg":
                    event_message_count += 1
                    continue
                if record_type != "response_item":
                    continue

                response_item_count += 1
                response_payload = obj.get("payload")
                if not isinstance(response_payload, dict):
                    continue

                response_type = response_payload.get("type")
                if response_type == "message":
                    message_count += 1
                    role = response_payload.get("role")
                    if role == "user":
                        user_message_count += 1
                    elif role == "assistant":
                        assistant_message_count += 1
                    elif role == "developer":
                        developer_message_count += 1
                elif response_type == "function_call":
                    tool_call_count += 1
                elif response_type == "function_call_output":
                    tool_call_output_count += 1
                elif response_type == "reasoning":
                    reasoning_item_count += 1
    except OSError:
        return payload

    # Import lazily to avoid an import cycle through agentos.chat.extractors.__init__.
    from agentos.chat.extractors.codex import extract_dialog_from_codex_rollout

    turns = extract_dialog_from_codex_rollout(artifact_path, raw=False)
    payload.update(
        {
            "record_count": record_count,
            "session_meta_count": session_meta_count,
            "response_item_count": response_item_count,
            "event_message_count": event_message_count,
            "message_count": message_count,
            "user_message_count": user_message_count,
            "assistant_message_count": assistant_message_count,
            "developer_message_count": developer_message_count,
            "tool_call_count": tool_call_count,
            "tool_call_output_count": tool_call_output_count,
            "reasoning_item_count": reasoning_item_count,
            "first_record_at": _format_stats_timestamp(first_record_at),
            "last_record_at": _format_stats_timestamp(last_record_at),
            **_build_dialog_turn_stats(turns),
        }
    )
    return payload


def _build_copilot_cli_session_stats(session: CopilotCliSessionSource) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_root_present": session.session_root is not None,
        "session_file_present": session.session_file is not None,
    }

    artifact_path = session.primary_artifact_path()
    if artifact_path is None or not artifact_path.is_file():
        return payload

    from agentos.chat.extractors.copilot_cli import (
        load_copilot_cli_events,
        extract_dialog_from_copilot_cli_session,
    )

    events = _try_provider_stats_call(lambda: load_copilot_cli_events(artifact_path))
    if not isinstance(events, list):
        return payload

    session_start_count = 0
    user_message_event_count = 0
    assistant_message_event_count = 0
    tool_event_count = 0
    skill_invoked_count = 0
    first_event_at: float | None = None
    last_event_at: float | None = None

    for event in events:
        event_type = event.get("type")
        first_event_at, last_event_at = _update_time_bounds(first_event_at, last_event_at, event.get("timestamp"))
        if event_type == "session.start":
            session_start_count += 1
        elif event_type == "user.message":
            user_message_event_count += 1
        elif event_type == "assistant.message":
            assistant_message_event_count += 1
        elif event_type in {"tool.execution_start", "tool.execution_complete"}:
            tool_event_count += 1
        elif event_type == "skill.invoked":
            skill_invoked_count += 1

    payload.update(
        {
            "event_count": len(events),
            "session_start_count": session_start_count,
            "user_message_event_count": user_message_event_count,
            "assistant_message_event_count": assistant_message_event_count,
            "tool_event_count": tool_event_count,
            "skill_invoked_count": skill_invoked_count,
            "first_event_at": _format_stats_timestamp(first_event_at),
            "last_event_at": _format_stats_timestamp(last_event_at),
        }
    )
    payload.update(
        _try_build_dialog_turn_stats(
            lambda: extract_dialog_from_copilot_cli_session(
                events=events,
                session_id=session.session_id,
                raw=False,
            )
        )
    )
    return payload


def _build_gemini_cli_session_stats(session: GeminiCliSessionSource) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifact_count": len(session.artifact_paths),
    }

    artifact_path = session.primary_artifact_path()
    if artifact_path is None or not artifact_path.is_file():
        return payload

    from agentos.chat.extractors.gemini_cli import (
        load_gemini_cli_session_data,
        extract_dialog_from_gemini_cli_session,
    )

    session_data = _try_provider_stats_call(lambda: load_gemini_cli_session_data(artifact_path))
    if not isinstance(session_data, dict):
        return payload

    messages = session_data.get("messages")
    if not isinstance(messages, list):
        return payload

    message_count = 0
    user_message_count = 0
    assistant_message_count = 0
    thought_count = 0
    tool_call_count = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        message_count += 1
        message_type = message.get("type")
        if message_type == "user":
            user_message_count += 1
        elif message_type == "gemini":
            assistant_message_count += 1
        thoughts = message.get("thoughts")
        if isinstance(thoughts, list):
            thought_count += len(thoughts)
        tool_calls = message.get("toolCalls")
        if isinstance(tool_calls, list):
            tool_call_count += len(tool_calls)

    payload.update(
        {
            "message_count": message_count,
            "user_message_count": user_message_count,
            "assistant_message_count": assistant_message_count,
            "thought_count": thought_count,
            "tool_call_count": tool_call_count,
            "start_time": session_data.get("startTime") if isinstance(session_data.get("startTime"), str) else None,
            "last_updated": session_data.get("lastUpdated")
            if isinstance(session_data.get("lastUpdated"), str)
            else None,
        }
    )
    payload.update(
        _try_build_dialog_turn_stats(
            lambda: extract_dialog_from_gemini_cli_session(
                session_data=session_data,
                session_id=session.session_id,
                raw=False,
            )
        )
    )
    return payload


def _build_openclaw_session_stats(session: OpenclawSessionSource) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "has_transcript": session.transcript_path is not None and session.transcript_path.is_file(),
        "has_sessions_index": session.sessions_index_path is not None and session.sessions_index_path.is_file(),
        "session_key_count": len(session.session_keys),
        "agent_id": session.agent_id,
    }

    artifact_path = session.transcript_path
    if artifact_path is None or not artifact_path.is_file():
        return payload

    from agentos.chat.extractors.openclaw import (
        load_openclaw_session_records,
        extract_dialog_from_openclaw_session,
    )

    records = _try_provider_stats_call(lambda: load_openclaw_session_records(artifact_path))
    if not isinstance(records, list):
        return payload

    session_record_count = 0
    message_record_count = 0
    user_message_count = 0
    assistant_message_count = 0
    first_record_at: float | None = None
    last_record_at: float | None = None

    for record in records:
        record_type = record.get("type")
        first_record_at, last_record_at = _update_time_bounds(
            first_record_at,
            last_record_at,
            record.get("timestamp"),
        )
        if record_type == "session":
            session_record_count += 1
        elif record_type == "message":
            message_record_count += 1
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role == "user":
                user_message_count += 1
            elif role == "assistant":
                assistant_message_count += 1

    payload.update(
        {
            "record_count": len(records),
            "session_record_count": session_record_count,
            "message_record_count": message_record_count,
            "user_message_count": user_message_count,
            "assistant_message_count": assistant_message_count,
            "first_record_at": _format_stats_timestamp(first_record_at),
            "last_record_at": _format_stats_timestamp(last_record_at),
        }
    )
    payload.update(
        _try_build_dialog_turn_stats(
            lambda: extract_dialog_from_openclaw_session(
                records=records,
                session_id=session.session_id,
                raw=False,
            )
        )
    )
    return payload


def _build_opencode_session_stats(session: OpencodeSessionSource) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "has_diff_artifact": session.diff_path is not None and session.diff_path.is_file(),
        "has_sqlite_db": session.sqlite_db_path is not None and session.sqlite_db_path.is_file(),
    }

    from agentos.chat.extractors.opencode import (
        load_opencode_session_messages,
        resolve_opencode_db_path,
        extract_dialog_from_opencode_session,
    )

    db_path = session.sqlite_db_path
    if db_path is None and session.diff_path is not None:
        resolved_db_path = _try_provider_stats_call(
            lambda: resolve_opencode_db_path(session.diff_path)
        )
        if isinstance(resolved_db_path, Path):
            db_path = resolved_db_path

    if db_path is None or not db_path.is_file():
        return payload

    payload["has_sqlite_db"] = True
    messages = _try_provider_stats_call(
        lambda: load_opencode_session_messages(db_path=db_path, session_id=session.session_id)
    )
    if not isinstance(messages, list):
        return payload
    if not messages:
        return payload

    message_count = 0
    user_message_count = 0
    assistant_message_count = 0
    part_count = 0
    text_part_count = 0
    non_text_part_count = 0
    first_message_at: float | None = None
    last_message_at: float | None = None

    for message in messages:
        message_count += 1
        role = message.get("role")
        if role == "user":
            user_message_count += 1
        elif role == "assistant":
            assistant_message_count += 1

        first_message_at, last_message_at = _update_time_bounds(
            first_message_at,
            last_message_at,
            message.get("time_created"),
        )

        parts = message.get("parts")
        if not isinstance(parts, list):
            continue
        part_count += len(parts)
        for part in parts:
            if not isinstance(part, dict):
                continue
            part_data = part.get("data")
            if not isinstance(part_data, dict):
                continue
            if part_data.get("type") == "text":
                text_part_count += 1
            else:
                non_text_part_count += 1

    payload.update(
        {
            "message_count": message_count,
            "user_message_count": user_message_count,
            "assistant_message_count": assistant_message_count,
            "part_count": part_count,
            "text_part_count": text_part_count,
            "non_text_part_count": non_text_part_count,
            "first_message_at": _format_stats_timestamp(first_message_at),
            "last_message_at": _format_stats_timestamp(last_message_at),
        }
    )
    payload.update(
        _try_build_dialog_turn_stats(
            lambda: extract_dialog_from_opencode_session(
                db_path=db_path,
                session_id=session.session_id,
                raw=False,
            )
        )
    )
    return payload


def _format_resolved_session_choices(sessions: list[ChatSession]) -> str:
    choices: list[str] = []
    for session in sessions:
        display_name = _session_display_name(session)
        choice = session.uri
        if display_name is not None:
            choice += f" ({display_name})"
        choices.append(choice)
    return ", ".join(choices)


def _validate_sort_choice(sort: str) -> None:
    if sort not in SESSION_SORT_CHOICES:
        raise ValueError(f"unsupported session sort: {sort}")


def _validate_session_limit(limit: int | None) -> None:
    if limit is None:
        return
    if limit < 1:
        raise ValueError(f"unsupported session limit: {limit}")


def _glob_paths(target: Path, pattern: str) -> list[Path]:
    if not target.is_dir():
        return []

    try:
        paths = sorted(path.resolve() for path in target.glob(pattern))
    except OSError:
        return []

    return paths


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    unique_paths: list[Path] = []
    seen_paths: set[Path] = set()

    for path in paths:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        unique_paths.append(path)

    return tuple(unique_paths)


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    unique_values: list[str] = []
    seen_values: set[str] = set()

    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        unique_values.append(value)

    return tuple(unique_values)


def _sort_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings.sort(key=lambda item: (item["path"], item.get("line_number") or 0, item["match_kind"]))
    return findings


def _scan_grep_findings(
    *,
    provider: str,
    target: Path,
    session_id: str,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    if target.is_file():
        findings.extend(_grep_file(provider=provider, path=target, session_id=session_id))
        return findings

    if not target.is_dir():
        return findings

    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = sorted(
            dirname for dirname in dirnames if dirname not in DEFAULT_SCAN_EXCLUDES
        )
        current_path = Path(dirpath)
        if session_id in current_path.name:
            findings.append(
                {
                    "provider": provider,
                    "strategy": "grep",
                    "match_kind": "grep_path",
                    "path": str(current_path),
                }
            )

        for filename in sorted(filenames):
            file_path = current_path / filename
            if session_id in filename:
                findings.append(
                    {
                        "provider": provider,
                        "strategy": "grep",
                        "match_kind": "grep_path",
                        "path": str(file_path),
                    }
                )
                continue

            findings.extend(_grep_file(provider=provider, path=file_path, session_id=session_id))

    return _sort_findings(findings)


def _grep_file(
    *,
    provider: str,
    path: Path,
    session_id: str,
) -> list[dict[str, Any]]:
    if not _is_text_like_file(path):
        return []

    try:
        if path.stat().st_size > MAX_GREP_FILE_BYTES:
            return []
    except OSError:
        return []

    findings: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line_number, line in enumerate(handle, start=1):
                if session_id not in line:
                    continue
                findings.append(
                    {
                        "provider": provider,
                        "strategy": "grep",
                        "match_kind": "grep_content",
                        "path": str(path),
                        "line_number": line_number,
                    }
                )
    except OSError:
        return []

    return findings


def _is_text_like_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in TEXT_FILE_SUFFIXES


def _copilot_updated_at(session_root: Path | None) -> float | None:
    if session_root is None:
        return None

    events_path = session_root / "events.jsonl"
    return safe_path_mtime(events_path) or safe_path_mtime(session_root)


def _session_is_extractable(session: ChatSession) -> bool:
    backing_artifacts = session.backing_artifacts()
    if backing_artifacts:
        return any(
            _backing_artifact_is_extractable(session, artifact)
            for artifact in backing_artifacts
        )

    artifact_path = session.primary_artifact_path()
    return artifact_path is not None and artifact_path.is_file()


def _format_stats_timestamp(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _iter_openclaw_agent_dirs(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(
        child
        for child in sorted(root.iterdir(), key=lambda path: path.name)
        if child.is_dir() and (child / "sessions").is_dir()
    )


def _read_openclaw_agent_sessions(
    agent_dir: Path,
    *,
    provider_instance: ProviderInstance,
) -> list[OpenclawSessionSource]:
    sessions_dir = agent_dir / "sessions"
    index_path = sessions_dir / "sessions.json"
    transcript_paths = {
        path.stem: path
        for path in sorted(sessions_dir.glob("*.jsonl"), key=lambda path: path.name)
        if ".reset." not in path.name
    }

    sessions_by_id: dict[tuple[object, ...], OpenclawSessionSource] = {}
    index_obj = _read_json_file(index_path)
    if isinstance(index_obj, dict):
        for session_key, entry in index_obj.items():
            if not isinstance(entry, dict):
                continue
            session_id = entry.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                continue

            session_file = entry.get("sessionFile")
            transcript_path: Path | None = None
            if isinstance(session_file, str) and session_file:
                candidate = Path(session_file).expanduser()
                if candidate.is_file():
                    transcript_path = candidate.resolve()
            if transcript_path is None:
                transcript_path = transcript_paths.get(session_id)

            session = OpenclawSessionSource(
                provider_instance=provider_instance,
                native_session_id=session_id,
                transcript_path=transcript_path,
                sessions_index_path=index_path.resolve(),
                session_keys=(session_key,) if isinstance(session_key, str) and session_key else (),
                agent_id=agent_dir.name,
                updated_at=coerce_timestamp(entry.get("updatedAt"))
                or safe_path_mtime(transcript_path)
                or safe_path_mtime(index_path),
            )
            _merge_session_source(sessions_by_id, session)

    for session_id, transcript_path in transcript_paths.items():
        session_key = (
            provider_instance.family,
            provider_instance.identity_key(),
            session_id,
        )
        existing = sessions_by_id.get(session_key)
        if existing is None:
            sessions_by_id[session_key] = OpenclawSessionSource(
                provider_instance=provider_instance,
                native_session_id=session_id,
                transcript_path=transcript_path.resolve(),
                sessions_index_path=index_path.resolve() if index_path.exists() else None,
                session_keys=(),
                agent_id=agent_dir.name,
                updated_at=safe_path_mtime(transcript_path),
            )
            continue

        sessions_by_id[session_key] = OpenclawSessionSource(
            provider_instance=provider_instance,
            native_session_id=session_id,
            transcript_path=existing.transcript_path or transcript_path.resolve(),
            sessions_index_path=existing.sessions_index_path,
            session_keys=existing.session_keys,
            agent_id=existing.agent_id,
            updated_at=existing.updated_at or safe_path_mtime(transcript_path),
        )

    return list(sessions_by_id.values())


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    try:
        obj = json.loads(raw_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(obj, dict):
        return None
    return obj


def _read_first_jsonl_object(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    return obj
    except OSError:
        return None

    return None


def _read_codex_session_meta(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") != "session_meta":
                    continue
                payload = obj.get("payload")
                if not isinstance(payload, dict):
                    continue
                if not isinstance(payload.get("id"), str):
                    continue
                return obj
    except OSError:
        return None

    return None


def _is_claude_project_session_artifact(path: Path) -> bool:
    if path.suffix != ".jsonl":
        return False
    return "subagents" not in path.parts


def _read_claude_project_session(
    path: Path,
    *,
    provider_instance: ProviderInstance,
) -> ClaudeCodeSessionSource | None:
    if not _is_claude_project_session_artifact(path):
        return None

    first_obj = _read_first_jsonl_object(path)
    session_id = path.stem
    updated_at = safe_path_mtime(path)

    if first_obj is not None:
        first_session_id = first_obj.get("sessionId")
        if isinstance(first_session_id, str) and first_session_id:
            session_id = first_session_id
        updated_at = coerce_timestamp(first_obj.get("timestamp")) or updated_at

    return ClaudeCodeSessionSource(
        provider_instance=provider_instance,
        native_session_id=session_id,
        artifact_paths=(path,),
        source_kind="project",
        updated_at=updated_at,
    )


def _read_claude_desktop_session(
    path: Path,
    *,
    provider_instance: ProviderInstance,
) -> ClaudeCodeSessionSource | None:
    obj = _read_json_file(path)
    if obj is None:
        return None

    session_id = obj.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        return None

    updated_at = (
        coerce_timestamp(obj.get("lastActivityAt"))
        or coerce_timestamp(obj.get("createdAt"))
        or safe_path_mtime(path)
    )
    return ClaudeCodeSessionSource(
        provider_instance=provider_instance,
        native_session_id=session_id,
        artifact_paths=(path,),
        source_kind="desktop",
        title=obj.get("title") if isinstance(obj.get("title"), str) and obj.get("title") else None,
        updated_at=updated_at,
    )


def _read_codex_rollout_session(
    path: Path,
    *,
    provider_instance: ProviderInstance,
) -> CodexSessionSource | None:
    meta_obj = _read_codex_session_meta(path)
    if meta_obj is None:
        return None

    payload = meta_obj.get("payload")
    if not isinstance(payload, dict):
        return None

    session_id = payload.get("id")
    if not isinstance(session_id, str) or not session_id:
        return None

    updated_at = safe_path_mtime(path) or coerce_timestamp(meta_obj.get("timestamp"))
    return CodexSessionSource(
        provider_instance=provider_instance,
        native_session_id=session_id,
        artifact_paths=(path,),
        updated_at=updated_at,
    )


def _read_codex_index_sessions(
    path: Path,
    *,
    provider_instance: ProviderInstance,
) -> list[CodexSessionSource]:
    if not path.is_file():
        return []

    sessions: list[CodexSessionSource] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                session_id = obj.get("id")
                if not isinstance(session_id, str) or not session_id:
                    continue
                thread_name = obj.get("thread_name")
                if not isinstance(thread_name, str) or not thread_name:
                    thread_name = None
                updated_at = coerce_timestamp(obj.get("updated_at")) or safe_path_mtime(path)
                sessions.append(
                    CodexSessionSource(
                        provider_instance=provider_instance,
                        native_session_id=session_id,
                        thread_name=thread_name,
                        index_paths=(path,),
                        updated_at=updated_at,
                    )
                )
    except OSError:
        return []

    return sessions


def _read_gemini_session(
    path: Path,
    *,
    provider_instance: ProviderInstance,
) -> GeminiCliSessionSource | None:
    obj = _read_json_file(path)
    if obj is None:
        return None

    session_id = obj.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        return None

    updated_at = (
        coerce_timestamp(obj.get("lastUpdated"))
        or coerce_timestamp(obj.get("startTime"))
        or safe_path_mtime(path)
    )
    return GeminiCliSessionSource(
        provider_instance=provider_instance,
        native_session_id=session_id,
        artifact_paths=(path,),
        updated_at=updated_at,
    )


def _gemini_session_matches(
    requested_session_id: str,
    session: GeminiCliSessionSource,
    path: Path,
) -> bool:
    if requested_session_id == session.session_id:
        return True
    return requested_session_id in path.name


def _query_opencode_sessions(
    sqlite_db_path: Path,
    *,
    provider_instance: ProviderInstance,
    session_id: str | None = None,
) -> list[OpencodeSessionSource]:
    try:
        connection = sqlite3.connect(str(sqlite_db_path))
    except sqlite3.Error:
        return []

    sessions: list[OpencodeSessionSource] = []
    try:
        try:
            if session_id is None:
                cursor = connection.execute("SELECT id, time_updated FROM session ORDER BY id")
            else:
                cursor = connection.execute(
                    "SELECT id, time_updated FROM session WHERE id = ? ORDER BY id",
                    (session_id,),
                )
            rows = cursor.fetchall()
        except sqlite3.Error:
            if session_id is None:
                cursor = connection.execute("SELECT id FROM session ORDER BY id")
            else:
                cursor = connection.execute(
                    "SELECT id FROM session WHERE id = ? ORDER BY id",
                    (session_id,),
                )
            rows = [(row_id, None) for (row_id,) in cursor.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        connection.close()

    for row_id, time_updated in rows:
        if not isinstance(row_id, str) or not row_id:
            continue
        sessions.append(
            OpencodeSessionSource(
                provider_instance=provider_instance,
                native_session_id=row_id,
                sqlite_db_path=sqlite_db_path,
                updated_at=coerce_timestamp(time_updated),
            )
        )

    return sessions


__all__ = [
    "chat_session_resolved_stats",
    "chat_session_stats",
    "find_chat_session",
    "format_chat_session_resolved_stats_markdown",
    "format_chat_session_stats_markdown",
    "list_chat_sessions",
    "resolve_chat_sessions",
    "configured_provider_instances",
    "supported_provider_families",
]
