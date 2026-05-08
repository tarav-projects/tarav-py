from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from agentos._core.errors import CliError
from agentos._core.sequences import _unique_paths
from agentos._core.scan import DEFAULT_SCAN_EXCLUDES
from agentos.chat.providers import (
    canonical_chat_provider_specs,
    default_legacy_provider_configs,
    LegacyProviderConfig,
    load_legacy_provider_configs,
)
from agentos.chat.providers import ProviderFamily
from agentos.chat.sessions import (
    BackingArtifact,
    ChatSession,
    ClaudeCodeSessionRecord,
    CodexSessionRecord,
    CopilotCliSessionRecord,
    GeminiCliSessionRecord,
    OpenclawSessionRecord,
    OpencodeSessionRecord,
    PiSessionRecord,
    SessionProviderIdentity,
    ChatSessionRecord,
    coerce_timestamp,
    safe_path_mtime,
)
from agentos.codex.session import (
    CodexSession,
    discover_codex_sessions,
    find_codex_sessions,
)
from agentos.claude.session import (
    ClaudeSession,
    discover_claude_sessions,
    find_claude_sessions,
)
from agentos.copilot.session import (
    CopilotSession,
    discover_copilot_sessions,
    find_copilot_sessions,
)
from agentos.pi.session import (
    PiSession,
    discover_pi_sessions,
    find_pi_sessions,
)
from agentos.opencode.session import (
    OpencodeSession,
    discover_opencode_sessions,
    find_opencode_sessions,
)
from agentos.gemini.session import (
    GeminiSession,
    discover_gemini_sessions,
    find_gemini_sessions,
)
from agentos.openclaw.session import (
    OpenclawSession,
    discover_openclaw_sessions,
    find_openclaw_sessions,
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

@dataclass(frozen=True)
class SessionProviderContext:
    provider_identity: SessionProviderIdentity
    provider: str
    instance_summary: dict[str, Any]
    instance_fingerprint: str
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
class SessionProviderConfig:
    provider_identity: SessionProviderIdentity
    provider: str
    instance_summary: dict[str, Any]
    instance_fingerprint: str
    direct_targets: tuple[Path, ...]
    grep_targets: tuple[Path, ...]
    sqlite_db_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ChatSessionUriQuery:
    provider_family: str
    instance_fingerprint_prefix: str
    session_id: str


SESSION_DISCOVERY_PROVIDER_FAMILIES = {
    "claude-code",
    "codex",
    "copilot-cli",
    "gemini-cli",
    "openclaw",
    "opencode",
    "pi",
}


def supported_provider_families() -> tuple[ProviderFamily, ...]:
    families: list[ProviderFamily] = []
    for provider_spec in canonical_chat_provider_specs():
        if not provider_spec.supports_session_discovery:
            continue
        if provider_spec.family not in SESSION_DISCOVERY_PROVIDER_FAMILIES:
            continue
        families.append(provider_spec.provider_family)
    return tuple(families)


def configured_legacy_provider_configs(*, start_path: Path | str = ".") -> tuple[LegacyProviderConfig, ...]:
    supported_families = {provider_handler.family for provider_handler in supported_provider_families()}
    legacy_provider_configs = tuple(
        legacy_provider_config
        for legacy_provider_config in load_legacy_provider_configs(start_path=start_path)
        if legacy_provider_config.family in supported_families
    )
    return _dedupe_legacy_provider_configs(legacy_provider_configs)


def configured_session_provider_configs(
    *,
    start_path: Path | str = ".",
) -> tuple[SessionProviderConfig, ...]:
    configured_legacy_configs = configured_legacy_provider_configs(start_path=start_path)
    default_legacy_configs = default_legacy_provider_configs(supports_session_discovery_only=True)
    provider_configs = tuple(
        _session_provider_config_from_legacy_config(legacy_provider_config)
        for legacy_provider_config in configured_legacy_configs + default_legacy_configs
    )
    return _dedupe_session_provider_configs(provider_configs)


def _provider_family_for_name(family_name: str) -> ProviderFamily | None:
    for family in supported_provider_families():
        if family.family == family_name:
            return family
    return None


def _session_provider_home_slots(family_name: str):
    provider_spec = canonical_chat_provider_specs()
    for spec in provider_spec:
        if spec.family == family_name:
            return tuple(slot for slot in spec.home_slots if slot.supports_session_discovery())
    return ()

def _dedupe_legacy_provider_configs(
    legacy_provider_configs: tuple[LegacyProviderConfig, ...],
) -> tuple[LegacyProviderConfig, ...]:
    unique_instances: dict[tuple[object, ...], LegacyProviderConfig] = {}
    for legacy_provider_config in legacy_provider_configs:
        key = legacy_provider_config.identity_key()
        if key not in unique_instances:
            unique_instances[key] = legacy_provider_config
    return tuple(unique_instances.values())


def _dedupe_session_provider_configs(
    provider_configs: tuple[SessionProviderConfig, ...],
) -> tuple[SessionProviderConfig, ...]:
    unique_configs: dict[tuple[object, ...], SessionProviderConfig] = {}
    for provider_config in provider_configs:
        key = provider_config.provider_identity.identity_key()
        if key not in unique_configs:
            unique_configs[key] = provider_config
    return tuple(unique_configs.values())


def list_chat_sessions(
    *,
    sort: str = "lexical",
    full_output: bool = False,
    limit: int | None = None,
    providers: tuple[str, ...] | None = None,
    extractable_only: bool = False,
    updated_after: float | None = None,
    start_path: Path | str = ".",
) -> dict[str, object]:
    _validate_sort_choice(sort)
    _validate_session_limit(limit)

    provider_groups = _iter_provider_context_groups(providers, start_path=start_path)
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
    start_path: Path | str = ".",
) -> dict[str, object]:
    provider_groups = _iter_provider_context_groups(providers, start_path=start_path)
    sessions = resolve_chat_sessions(query, providers=providers, start_path=start_path)
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
    start_path: Path | str = ".",
) -> list[ChatSession]:
    resolved_sessions: list[ChatSession] = []
    for _, contexts in _iter_provider_context_groups(providers, start_path=start_path):
        for context in contexts:
            resolved_sessions.extend(_find_direct_provider_sessions(context, query))
    return _sort_sessions(_dedupe_sessions(resolved_sessions), "lexical")


def _iter_provider_context_groups(
    providers: tuple[str, ...] | None,
    *,
    start_path: Path | str = ".",
) -> tuple[tuple[ProviderFamily, tuple[SessionProviderContext, ...]], ...]:
    provider_configs = configured_session_provider_configs(start_path=start_path)
    if providers is not None:
        requested_providers = set(providers)
        provider_configs = tuple(
            provider_config
            for provider_config in provider_configs
            if provider_config.provider in requested_providers
        )

    contexts_by_family: dict[str, list[SessionProviderContext]] = {}
    for provider_config in provider_configs:
        context = _build_provider_context(provider_config)
        contexts_by_family.setdefault(provider_config.provider, []).append(context)

    groups: list[tuple[ProviderFamily, tuple[SessionProviderContext, ...]]] = []
    for provider_family in supported_provider_families():
        family_contexts = contexts_by_family.get(provider_family.family)
        if not family_contexts:
            continue
        groups.append((provider_family, tuple(family_contexts)))
    return tuple(groups)


def _session_provider_config_from_legacy_config(
    legacy_provider_config: LegacyProviderConfig,
) -> SessionProviderConfig:
    return SessionProviderConfig(
        provider_identity=_session_provider_identity_from_legacy_config(legacy_provider_config),
        provider=legacy_provider_config.family,
        instance_summary=legacy_provider_config.summary(),
        instance_fingerprint=legacy_provider_config.fingerprint,
        direct_targets=legacy_provider_config.direct_targets,
        grep_targets=legacy_provider_config.grep_targets,
        sqlite_db_paths=legacy_provider_config.sqlite_db_paths,
    )


def _build_provider_context(config: SessionProviderConfig) -> SessionProviderContext:
    provider_handler = _provider_family_for_name(config.provider)
    if provider_handler is None:
        raise CliError(f"unsupported provider family {config.provider}")

    direct_targets = config.direct_targets
    grep_targets = config.grep_targets
    sqlite_db_paths = config.sqlite_db_paths

    return SessionProviderContext(
        provider_identity=config.provider_identity,
        provider=config.provider,
        instance_summary=config.instance_summary,
        instance_fingerprint=config.instance_fingerprint,
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


def _session_provider_identity_from_legacy_config(legacy_provider_config: LegacyProviderConfig) -> SessionProviderIdentity:
    return SessionProviderIdentity(
        family=legacy_provider_config.family,
        identity=legacy_provider_config.identity_key(),
        uri_key=legacy_provider_config.uri_component(),
        fingerprint=legacy_provider_config.fingerprint,
        summary_payload=legacy_provider_config.summary(),
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
        "provider_instances": [context.instance_summary for context in contexts],
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
        if session.provider == "pi":
            from agentos.chat.extractors.pi import is_pi_session_path

            return is_pi_session_path(path)
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
        "provider_instance_fingerprint": session.provider_identity.fingerprint,
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
    return _build_session_record_stats(session.record)


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
        and session.provider_identity.matches_fingerprint_prefix(uri_query.instance_fingerprint_prefix)
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
    return _wrap_session_records(_discover_provider_session_records(context))


def _find_direct_provider_sessions(
    context: SessionProviderContext,
    query: str,
) -> list[ChatSession]:
    uri_query = _parse_chat_session_uri(query)
    if uri_query is not None:
        if context.provider != uri_query.provider_family:
            return []
        if not context.instance_fingerprint.startswith(uri_query.instance_fingerprint_prefix):
            return []
        return [
            session
            for session in _discover_direct_provider_sessions(context)
            if _session_matches_uri_query(session, uri_query)
        ]
    return _wrap_session_records(_find_provider_session_records(context, query))


def _wrap_session_records(session_records: list[ChatSessionRecord]) -> list[ChatSession]:
    return [ChatSession(record=source) for source in session_records]


def _discover_provider_session_records(context: SessionProviderContext) -> list[ChatSessionRecord]:
    if context.provider == "claude-code":
        return _list_claude_code_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
        )
    if context.provider == "codex":
        return _list_codex_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
        )
    if context.provider == "copilot-cli":
        return _list_copilot_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
        )
    if context.provider == "gemini-cli":
        return _list_gemini_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
        )
    if context.provider == "openclaw":
        return _list_openclaw_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
        )
    if context.provider == "opencode":
        return _list_opencode_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
            sqlite_db_paths=context.sqlite_existing_db_paths,
        )
    if context.provider == "pi":
        return _list_pi_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
        )
    raise CliError(f"unsupported provider family {context.provider}")


def _find_provider_session_records(
    context: SessionProviderContext,
    query: str,
) -> list[ChatSessionRecord]:
    if context.provider == "claude-code":
        return _find_claude_code_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
            query=query,
        )
    if context.provider == "codex":
        return _find_codex_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
            query=query,
        )
    if context.provider == "copilot-cli":
        return _find_copilot_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
            session_id=query,
        )
    if context.provider == "gemini-cli":
        return _find_gemini_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
            session_id=query,
        )
    if context.provider == "openclaw":
        return _find_openclaw_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
            session_id=query,
        )
    if context.provider == "opencode":
        return _find_opencode_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
            session_id=query,
            sqlite_db_paths=context.sqlite_existing_db_paths,
        )
    if context.provider == "pi":
        return _find_pi_sessions(
            provider_identity=context.provider_identity,
            targets=context.direct_existing_targets,
            session_id=query,
        )
    raise CliError(f"unsupported provider family {context.provider}")


def _build_session_record_stats(record: ChatSessionRecord) -> dict[str, Any]:
    if isinstance(record, ClaudeCodeSessionRecord):
        return _build_claude_code_session_stats(record)
    if isinstance(record, CodexSessionRecord):
        return _build_codex_session_stats(record)
    if isinstance(record, CopilotCliSessionRecord):
        return _build_copilot_cli_session_stats(record)
    if isinstance(record, GeminiCliSessionRecord):
        return _build_gemini_cli_session_stats(record)
    if isinstance(record, OpenclawSessionRecord):
        return _build_openclaw_session_stats(record)
    if isinstance(record, OpencodeSessionRecord):
        return _build_opencode_session_stats(record)
    if isinstance(record, PiSessionRecord):
        return _build_pi_session_stats(record)
    raise CliError(f"chat session stats is not implemented for provider {record.provider_family}")


def _list_claude_code_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
) -> list[ChatSessionRecord]:
    return [
        _claude_session_record_from_native(
            session,
            provider_identity=provider_identity,
        )
        for session in discover_claude_sessions(targets=targets)
    ]


def _find_claude_code_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
    query: str,
) -> list[ChatSessionRecord]:
    return [
        _claude_session_record_from_native(
            session,
            provider_identity=provider_identity,
        )
        for session in find_claude_sessions(targets=targets, query=query)
    ]


def _list_codex_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
) -> list[ChatSessionRecord]:
    return [
        _codex_session_record_from_native(
            session,
            provider_identity=provider_identity,
        )
        for session in discover_codex_sessions(targets=targets)
    ]


def _find_codex_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
    query: str,
) -> list[ChatSessionRecord]:
    return [
        _codex_session_record_from_native(
            session,
            provider_identity=provider_identity,
        )
        for session in find_codex_sessions(targets=targets, query=query)
    ]


def _list_copilot_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
) -> list[ChatSessionRecord]:
    return [
        _copilot_session_record_from_native(session, provider_identity=provider_identity)
        for session in discover_copilot_sessions(targets=targets)
    ]


def _find_copilot_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[ChatSessionRecord]:
    return [
        _copilot_session_record_from_native(session, provider_identity=provider_identity)
        for session in find_copilot_sessions(targets=targets, query=session_id)
    ]


def _list_gemini_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
) -> list[ChatSessionRecord]:
    return [
        _gemini_session_record_from_native(session, provider_identity=provider_identity)
        for session in discover_gemini_sessions(targets=targets)
    ]


def _find_gemini_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[ChatSessionRecord]:
    return [
        _gemini_session_record_from_native(session, provider_identity=provider_identity)
        for session in find_gemini_sessions(targets=targets, query=session_id)
    ]


def _list_pi_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
) -> list[ChatSessionRecord]:
    return [
        _pi_session_record_from_native(session, provider_identity=provider_identity)
        for session in discover_pi_sessions(targets=targets)
    ]


def _find_pi_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[ChatSessionRecord]:
    return [
        _pi_session_record_from_native(session, provider_identity=provider_identity)
        for session in find_pi_sessions(targets=targets, query=session_id)
    ]


def _list_opencode_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
    sqlite_db_paths: tuple[Path, ...],
) -> list[ChatSessionRecord]:
    return [
        _opencode_session_record_from_native(session, provider_identity=provider_identity)
        for session in discover_opencode_sessions(targets=targets, sqlite_db_paths=sqlite_db_paths)
    ]


def _find_opencode_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
    session_id: str,
    sqlite_db_paths: tuple[Path, ...],
) -> list[ChatSessionRecord]:
    return [
        _opencode_session_record_from_native(session, provider_identity=provider_identity)
        for session in find_opencode_sessions(targets=targets, sqlite_db_paths=sqlite_db_paths, query=session_id)
    ]


def _list_openclaw_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
) -> list[ChatSessionRecord]:
    return [
        _openclaw_session_record_from_native(session, provider_identity=provider_identity)
        for session in discover_openclaw_sessions(targets=targets)
    ]


def _find_openclaw_sessions(
    *,
    provider_identity: SessionProviderIdentity,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[ChatSessionRecord]:
    return [
        _openclaw_session_record_from_native(session, provider_identity=provider_identity)
        for session in find_openclaw_sessions(targets=targets, query=session_id)
    ]


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
        enriched["provider_instance_fingerprint"] = session.provider_identity.fingerprint
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

    if type(existing.record) is type(session.record):
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


def _merge_session_record(
    sessions_by_id: dict[tuple[object, ...], ChatSessionRecord],
    session: ChatSessionRecord,
) -> None:
    session_key = session.record_identity_key()
    existing = sessions_by_id.get(session_key)
    if existing is None:
        sessions_by_id[session_key] = session
        return

    if type(existing) is type(session):
        sessions_by_id[session_key] = existing.merge(session)
        return

    if _session_record_preference_key(session) > _session_record_preference_key(existing):
        sessions_by_id[session_key] = session


def _dedupe_session_records(sessions: list[ChatSessionRecord]) -> list[ChatSessionRecord]:
    deduped: dict[tuple[object, ...], ChatSessionRecord] = {}
    for session in sessions:
        _merge_session_record(deduped, session)
    return _sort_session_records(list(deduped.values()), "lexical")


def _sort_session_records(sessions: list[ChatSessionRecord], sort: str) -> list[ChatSessionRecord]:
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


def _session_record_preference_key(session: ChatSessionRecord) -> tuple[float, int, str]:
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


def _build_claude_code_session_stats(session: ClaudeCodeSessionRecord) -> dict[str, Any]:
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


def _build_codex_session_stats(session: CodexSessionRecord) -> dict[str, Any]:
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


def _build_copilot_cli_session_stats(session: CopilotCliSessionRecord) -> dict[str, Any]:
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


def _build_gemini_cli_session_stats(session: GeminiCliSessionRecord) -> dict[str, Any]:
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


def _build_pi_session_stats(session: PiSessionRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifact_count": len(session.artifact_paths),
    }
    if session.cwd is not None:
        payload["cwd"] = session.cwd
    if session.model_provider is not None:
        payload["model_provider"] = session.model_provider
    if session.model_id is not None:
        payload["model_id"] = session.model_id
    if session.thinking_level is not None:
        payload["thinking_level"] = session.thinking_level

    artifact_path = session.primary_artifact_path()
    if artifact_path is None or not artifact_path.is_file():
        return payload

    from agentos.chat.extractors.pi import (
        extract_dialog_from_pi_session,
        load_pi_session_records,
    )

    records = _try_provider_stats_call(lambda: load_pi_session_records(artifact_path))
    if not isinstance(records, list):
        return payload

    message_record_count = 0
    user_message_count = 0
    assistant_message_count = 0
    tool_result_message_count = 0
    custom_message_count = 0
    model_change_count = 0
    thinking_level_change_count = 0
    first_record_at: float | None = None
    last_record_at: float | None = None

    for record in records:
        record_type = record.get("type")
        first_record_at, last_record_at = _update_time_bounds(
            first_record_at,
            last_record_at,
            record.get("timestamp"),
        )
        if record_type == "message":
            message_record_count += 1
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role == "user":
                user_message_count += 1
            elif role == "assistant":
                assistant_message_count += 1
            elif role == "toolResult":
                tool_result_message_count += 1
        elif record_type == "custom_message":
            custom_message_count += 1
        elif record_type == "model_change":
            model_change_count += 1
        elif record_type == "thinking_level_change":
            thinking_level_change_count += 1

    payload.update(
        {
            "record_count": len(records),
            "message_record_count": message_record_count,
            "user_message_count": user_message_count,
            "assistant_message_count": assistant_message_count,
            "tool_result_message_count": tool_result_message_count,
            "custom_message_count": custom_message_count,
            "model_change_count": model_change_count,
            "thinking_level_change_count": thinking_level_change_count,
            "first_record_at": _format_stats_timestamp(first_record_at),
            "last_record_at": _format_stats_timestamp(last_record_at),
        }
    )
    payload.update(
        _try_build_dialog_turn_stats(
            lambda: extract_dialog_from_pi_session(
                records=records,
                session_id=session.session_id,
                raw=False,
            )
        )
    )
    return payload


def _build_openclaw_session_stats(session: OpenclawSessionRecord) -> dict[str, Any]:
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


def _build_opencode_session_stats(session: OpencodeSessionRecord) -> dict[str, Any]:
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


def _claude_session_record_from_native(
    session: ClaudeSession,
    *,
    provider_identity: SessionProviderIdentity,
) -> ClaudeCodeSessionRecord:
    return ClaudeCodeSessionRecord(
        provider_identity=provider_identity,
        native_session_id=session.native_session_id,
        artifact_paths=session.artifact_paths,
        source_kind=session.source_kind,
        title=session.title,
        updated_at=session.updated_at if isinstance(session.updated_at, (int, float)) else None,
    )


def _codex_session_record_from_native(
    session: CodexSession,
    *,
    provider_identity: SessionProviderIdentity,
) -> CodexSessionRecord:
    return CodexSessionRecord(
        provider_identity=provider_identity,
        native_session_id=session.native_session_id,
        artifact_paths=session.rollout_paths,
        thread_name=session.thread_name,
        index_paths=session.index_paths,
        updated_at=session.updated_at,
    )


def _copilot_session_record_from_native(
    session: CopilotSession,
    *,
    provider_identity: SessionProviderIdentity,
) -> CopilotCliSessionRecord:
    session_root = session.events_path.parent if session.events_path.name == "events.jsonl" else None
    session_file = session.events_path if session.events_path.is_file() else None
    return CopilotCliSessionRecord(
        provider_identity=provider_identity,
        native_session_id=session.native_session_id,
        session_root=session_root,
        session_file=session_file,
        updated_at=session.updated_at,
    )


def _gemini_session_record_from_native(
    session: GeminiSession,
    *,
    provider_identity: SessionProviderIdentity,
) -> GeminiCliSessionRecord:
    return GeminiCliSessionRecord(
        provider_identity=provider_identity,
        native_session_id=session.native_session_id,
        artifact_paths=session.artifact_paths,
        updated_at=session.updated_at,
    )


def _pi_session_record_from_native(
    session: PiSession,
    *,
    provider_identity: SessionProviderIdentity,
) -> PiSessionRecord:
    return PiSessionRecord(
        provider_identity=provider_identity,
        native_session_id=session.native_session_id,
        artifact_paths=session.artifact_paths,
        cwd=session.cwd,
        model_provider=session.model_provider,
        model_id=session.model_id,
        thinking_level=session.thinking_level,
        started_at=session.started_at,
        updated_at=session.updated_at,
    )


def _opencode_session_record_from_native(
    session: OpencodeSession,
    *,
    provider_identity: SessionProviderIdentity,
) -> OpencodeSessionRecord:
    return OpencodeSessionRecord(
        provider_identity=provider_identity,
        native_session_id=session.native_session_id,
        diff_path=session.diff_path,
        sqlite_db_path=session.sqlite_db_path,
        updated_at=session.updated_at,
    )


def _openclaw_session_record_from_native(
    session: OpenclawSession,
    *,
    provider_identity: SessionProviderIdentity,
) -> OpenclawSessionRecord:
    return OpenclawSessionRecord(
        provider_identity=provider_identity,
        native_session_id=session.native_session_id,
        transcript_path=session.transcript_path,
        sessions_index_path=session.sessions_index_path,
        session_keys=session.session_keys,
        agent_id=session.agent_id,
        updated_at=session.updated_at,
    )


__all__ = [
    "chat_session_resolved_stats",
    "chat_session_stats",
    "find_chat_session",
    "format_chat_session_resolved_stats_markdown",
    "format_chat_session_stats_markdown",
    "list_chat_sessions",
    "resolve_chat_sessions",
    "configured_session_provider_configs",
    "configured_legacy_provider_configs",
    "supported_provider_families",
]
