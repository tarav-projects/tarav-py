# $kw: --from Agent.Normal.Model
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from tarav.l0._core.errors import CliError
from tarav.l0._core.sequences import _unique_paths
from tarav.l0._core.scan import DEFAULT_SCAN_EXCLUDES
from tarav.l1.agent.primitives import AgentConfig, SessionDiscoveryCapable, SessionSource
from tarav.l1.agent.providers.registry import agent_from_config, load_configured_agents
from tarav.l1.agent.config import (
    canonical_chat_provider_specs,
    default_agent_configs,
)
from tarav.l1.agent.config import ProviderFamily
from tarav.l1.agent.session_refs import (
    BackingArtifact,
    ProviderSessionRef,
    _build_path_finding,
    backing_artifacts_from_sources,
)
from tarav.l1.agent.session_utils import (
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


@dataclass(frozen=True)
class ProviderAgentContext:
    agent: AgentConfig
    adapter_fingerprint: str
    profile_identity_key: tuple[object, ...]
    adapter_uri_key: str
    direct_targets: tuple[Path, ...]
    direct_existing_targets: tuple[Path, ...]
    direct_missing_targets: tuple[Path, ...]
    grep_targets: tuple[Path, ...]
    grep_existing_targets: tuple[Path, ...]
    grep_missing_targets: tuple[Path, ...]
    sqlite_db_paths: tuple[Path, ...]
    sqlite_existing_db_paths: tuple[Path, ...]
    sqlite_missing_db_paths: tuple[Path, ...]

    @property
    def provider(self) -> str:
        return self.agent.provider

    @property
    def adapter_summary(self) -> dict[str, Any]:
        return self.agent.summary()


@dataclass(frozen=True)
class ProviderSessionRefEntry:
    context: ProviderAgentContext
    session_ref: ProviderSessionRef

    @property
    def provider_family(self) -> str:
        return self.context.provider

    @property
    def provider(self) -> str:
        return self.context.provider

    @property
    def session_id(self) -> str:
        return self.session_ref.native_session_id

    @property
    def uri(self) -> str:
        return _build_session_ref_uri(self)

    def record_identity_key(self) -> tuple[object, ...]:
        return (
            self.provider,
            self.context.profile_identity_key,
            self.session_id,
        )

    def sources(self) -> tuple[SessionSource, ...]:
        return self.session_ref.to_session().sources()

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        return backing_artifacts_from_sources(self.sources())

    def primary_backing_artifact(self) -> BackingArtifact | None:
        artifacts = self.backing_artifacts()
        if not artifacts:
            return None
        return artifacts[0]

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            _build_path_finding(provider=self.provider, path=artifact.path)
            for artifact in self.backing_artifacts()
            if artifact.role in {"transcript", "session_diff"}
        )

    def primary_artifact_path(self) -> Path | None:
        primary = self.primary_backing_artifact()
        if primary is None:
            return None
        return primary.path

    def created_timestamp(self) -> float | None:
        return self.session_ref.to_session().created_timestamp()

    def sort_timestamp(self) -> float | None:
        return self.session_ref.sort_timestamp()

    def merge(self, other: "ProviderSessionRefEntry") -> "ProviderSessionRefEntry":
        if self.record_identity_key() != other.record_identity_key():
            raise TypeError(f"cannot merge distinct session refs: {self.uri} != {other.uri}")
        ref = self.session_ref
        if hasattr(ref, "merge"):
            ref = ref.merge(other.session_ref)
        return ProviderSessionRefEntry(context=self.context, session_ref=ref)

    def display_name(self) -> str | None:
        return self.session_ref.display_name()

    def display_name_field(self) -> str | None:
        return self.session_ref.display_name_field()

    def native_fields(self) -> dict[str, Any]:
        payload = {"session_id": self.session_id}
        payload.update(self.session_ref.native_ref_metadata())
        return payload

    def query_fields(self) -> tuple[tuple[str, str], ...]:
        fields = [
            ("uri", self.uri),
            ("provider_instance_fingerprint", self.context.adapter_fingerprint),
            ("session_id", self.session_id),
        ]
        display_name = self.display_name()
        display_name_field = self.display_name_field()
        if display_name is not None:
            fields.append((display_name_field or "display_name", display_name))
        native = self.session_ref.native_ref_metadata()
        for field_name, raw_value in native.items():
            if isinstance(raw_value, str):
                fields.append((_query_field_name_for_native_field(field_name), raw_value))
            elif isinstance(raw_value, list):
                fields.extend(
                    (_query_field_name_for_native_field(field_name), value)
                    for value in raw_value
                    if isinstance(value, str)
                )
        return tuple(fields)

    def matches_query(self, query: str) -> bool:
        return any(value == query for _, value in self.query_fields())

    def matched_field(self, query: str) -> str:
        for field_name, value in self.query_fields():
            if value == query:
                return field_name
        return "query"

    def supplemental_findings(
        self,
        *,
        query: str,
        matched_field: str,
    ) -> tuple[dict[str, Any], ...]:
        if not hasattr(self.session_ref, "supplemental_findings"):
            return ()
        return self.session_ref.supplemental_findings(
            provider=self.provider,
            query=query,
            matched_field=matched_field,
        )


@dataclass(frozen=True)
class SessionRefUriQuery:
    provider_family: str
    adapter_fingerprint_prefix: str
    session_id: str


def _build_session_ref_uri(entry: ProviderSessionRefEntry) -> str:
    from urllib.parse import quote

    return (
        f"agentos://chat-session/{quote(entry.provider, safe='')}/"
        f"{entry.context.adapter_uri_key}/"
        f"{quote(entry.session_id, safe='')}"
    )


def _query_field_name_for_native_field(field_name: str) -> str:
    if field_name == "session_keys":
        return "session_key"
    return field_name


SESSION_DISCOVERY_PROVIDER_FAMILIES = {
    "claude-code",
    "codex",
    "copilot-cli",
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


def configured_session_agents(*, start_path: Path | str = ".") -> tuple[AgentConfig, ...]:
    supported_families = {provider_handler.family for provider_handler in supported_provider_families()}
    agents = tuple(
        agent
        for agent in load_configured_agents(start_path=start_path)
        if agent.provider in supported_families
    )
    return _dedupe_agents(agents)


def configured_session_provider_contexts(
    *,
    start_path: Path | str = ".",
) -> tuple[ProviderAgentContext, ...]:
    configured_agents = configured_session_agents(start_path=start_path)
    default_agents = tuple(
        agent_from_config(config)
        for config in default_agent_configs(supports_session_discovery_only=True)
    )
    agents = _dedupe_agents(configured_agents + default_agents)
    return tuple(_provider_agent_context_from_agent(agent) for agent in agents)


def _provider_family_for_name(family_name: str) -> ProviderFamily | None:
    for family in supported_provider_families():
        if family.family == family_name:
            return family
    return None


def _dedupe_agents(
    agents: tuple[AgentConfig, ...],
) -> tuple[AgentConfig, ...]:
    unique_adapters: dict[tuple[object, ...], AgentConfig] = {}
    for agent in agents:
        key = agent.identity_key()
        if key not in unique_adapters:
            unique_adapters[key] = agent
    return tuple(unique_adapters.values())


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
    discovered_sessions: list[ProviderSessionRefEntry] = []
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


def _session_matches_list_filters(
    session: ProviderSessionRefEntry,
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
        sessions: list[ProviderSessionRefEntry] = []
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
            lines.append(f"- Agent adapter: {fingerprint}")

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
    sessions_by_provider: dict[str, list[ProviderSessionRefEntry]] = {}
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
) -> list[ProviderSessionRefEntry]:
    resolved_sessions: list[ProviderSessionRefEntry] = []
    for _, contexts in _iter_provider_context_groups(providers, start_path=start_path):
        for context in contexts:
            resolved_sessions.extend(_find_direct_provider_sessions(context, query))
    return _sort_sessions(_dedupe_sessions(resolved_sessions), "lexical")


def _iter_provider_context_groups(
    providers: tuple[str, ...] | None,
    *,
    start_path: Path | str = ".",
) -> tuple[tuple[ProviderFamily, tuple[ProviderAgentContext, ...]], ...]:
    contexts = configured_session_provider_contexts(start_path=start_path)
    if providers is not None:
        requested_providers = set(providers)
        contexts = tuple(
            context
            for context in contexts
            if context.provider in requested_providers
        )

    contexts_by_family: dict[str, list[ProviderAgentContext]] = {}
    for context in contexts:
        contexts_by_family.setdefault(context.provider, []).append(context)

    groups: list[tuple[ProviderFamily, tuple[ProviderAgentContext, ...]]] = []
    for provider_family in supported_provider_families():
        family_contexts = contexts_by_family.get(provider_family.family)
        if not family_contexts:
            continue
        groups.append((provider_family, tuple(family_contexts)))
    return tuple(groups)


def _provider_agent_context_from_agent(
    agent: AgentConfig,
) -> ProviderAgentContext:
    provider_handler = _provider_family_for_name(agent.provider)
    if provider_handler is None:
        raise CliError(f"unsupported provider family {agent.provider}")
    direct_targets = agent.direct_targets
    grep_targets = agent.grep_targets
    sqlite_db_paths = agent.sqlite_db_paths
    return ProviderAgentContext(
        agent=agent,
        adapter_fingerprint=agent.fingerprint(),
        profile_identity_key=agent.identity_key(),
        adapter_uri_key=agent.uri_key(),
        direct_targets=agent.direct_targets,
        direct_existing_targets=tuple(target for target in direct_targets if target.exists()),
        direct_missing_targets=tuple(target for target in direct_targets if not target.exists()),
        grep_targets=agent.grep_targets,
        grep_existing_targets=tuple(target for target in grep_targets if target.exists()),
        grep_missing_targets=tuple(target for target in grep_targets if not target.exists()),
        sqlite_db_paths=agent.sqlite_db_paths,
        sqlite_existing_db_paths=tuple(path for path in sqlite_db_paths if path.exists()),
        sqlite_missing_db_paths=tuple(path for path in sqlite_db_paths if not path.exists()),
    )



def _build_provider_payload(
    *,
    provider_family: str,
    contexts: tuple[ProviderAgentContext, ...],
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
        "provider_instances": [context.adapter_summary for context in contexts],
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
    contexts: tuple[ProviderAgentContext, ...],
    sessions: list[ProviderSessionRefEntry],
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


def _session_native_payload(session: ProviderSessionRefEntry) -> dict[str, Any]:
    payload = dict(session.native_fields())
    payload.pop("session_id", None)
    return payload


def _matched_query_fields(
    session: ProviderSessionRefEntry,
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
    session: ProviderSessionRefEntry,
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
    session: ProviderSessionRefEntry,
    artifact: BackingArtifact,
) -> bool:
    path = artifact.path
    if not path.exists() or path.is_dir():
        return False

    try:
        from tarav.l1.agent.providers.extraction import _PROVIDER_SESSION_EXTRACTORS

        spec = _PROVIDER_SESSION_EXTRACTORS.get(session.provider)
        if spec is None:
            return False
        return spec.probe_artifact_path(path)
    except Exception:
        return False


def _serialize_backing_artifact(
    session: ProviderSessionRefEntry,
    artifact: BackingArtifact,
) -> dict[str, Any]:
    return artifact.summary(
        extractable=_backing_artifact_is_extractable(session, artifact),
    )


def _session_created_timestamp(session: ProviderSessionRefEntry) -> float | None:
    return session.created_timestamp()


def _build_common_session_stats(
    session: ProviderSessionRefEntry,
    *,
    query: str | None = None,
    include_artifacts: bool = False,
) -> dict[str, Any]:
    backing_artifacts = session.backing_artifacts()
    primary_backing_artifact = session.primary_backing_artifact()
    payload = {
        "provider": session.provider,
        "uri": session.uri,
        "provider_instance_fingerprint": session.context.adapter_fingerprint,
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


def _build_provider_session_stats(session: ProviderSessionRefEntry) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": session.provider,
        "session_id": session.session_id,
        "display_name": session.display_name(),
        "created_at": _format_stats_timestamp(_session_created_timestamp(session)),
        "updated_at": _format_stats_timestamp(session.sort_timestamp()),
        "extractable": _session_is_extractable(session),
        "backing_artifact_count": len(session.backing_artifacts()),
    }
    primary = session.primary_artifact_path()
    if primary is not None:
        payload["primary_backing_artifact"] = str(primary)
    payload.update(_session_native_payload(session))

    native_session = session.session_ref.to_session()
    if hasattr(native_session, "provider_stats"):
        payload.update(native_session.provider_stats())

    return {key: value for key, value in payload.items() if value is not None}


def _parse_chat_session_uri(query: str) -> SessionRefUriQuery | None:
    prefix = "agentos://chat-session/"
    if not query.startswith(prefix):
        return None

    remainder = query[len(prefix):]
    parts = remainder.split("/", 2)
    if len(parts) != 3:
        return None

    provider_family, adapter_fingerprint_prefix, session_id = (unquote(part) for part in parts)
    if not provider_family or not adapter_fingerprint_prefix or not session_id:
        return None
    return SessionRefUriQuery(
        provider_family=provider_family,
        adapter_fingerprint_prefix=adapter_fingerprint_prefix.lower(),
        session_id=session_id,
    )


def _session_matches_uri_query(
    session: ProviderSessionRefEntry,
    uri_query: SessionRefUriQuery,
) -> bool:
    return (
        session.provider_family == uri_query.provider_family
        and session.session_id == uri_query.session_id
        and session.context.adapter_fingerprint.startswith(uri_query.adapter_fingerprint_prefix)
    )


def _strategies_attempted(
    contexts: tuple[ProviderAgentContext, ...],
    *,
    include_grep: bool,
) -> list[str]:
    strategies = ["path"]
    if any(context.sqlite_db_paths for context in contexts):
        strategies.append("sqlite")
    if include_grep:
        strategies.append("grep")
    return strategies


def _discover_direct_provider_sessions(context: ProviderAgentContext) -> list[ProviderSessionRefEntry]:
    if not isinstance(context.agent, SessionDiscoveryCapable):
        return []
    discovery_agent = _agent_with_discoverable_direct_targets(context)
    if discovery_agent is None:
        return []
    return [
        ProviderSessionRefEntry(context=context, session_ref=session_ref)
        for session_ref in discovery_agent.discover_session_refs()
    ]


def _agent_with_discoverable_direct_targets(context: ProviderAgentContext) -> AgentConfig | None:
    direct_targets = _discoverable_direct_targets(context)
    if context.direct_targets and not direct_targets:
        return None
    if direct_targets == context.direct_targets:
        return context.agent
    return context.agent.with_session_discovery_paths(
        direct_targets=direct_targets,
        sqlite_db_paths=context.sqlite_db_paths,
    )


def _discoverable_direct_targets(context: ProviderAgentContext) -> tuple[Path, ...]:
    return tuple(target for target in context.direct_targets if not target.is_symlink())


def _find_direct_provider_sessions(
    context: ProviderAgentContext,
    query: str,
) -> list[ProviderSessionRefEntry]:
    uri_query = _parse_chat_session_uri(query)
    if uri_query is not None:
        if context.provider != uri_query.provider_family:
            return []
        if not context.adapter_fingerprint.startswith(uri_query.adapter_fingerprint_prefix):
            return []
        return [
            session
            for session in _discover_direct_provider_sessions(context)
            if _session_matches_uri_query(session, uri_query)
        ]
    return [
        session
        for session in _discover_direct_provider_sessions(context)
        if session.matches_query(query)
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


def _session_summary(session: ProviderSessionRefEntry) -> dict[str, Any]:
    return _build_common_session_stats(session)


def _session_display_name(session: ProviderSessionRefEntry) -> str | None:
    return session.display_name()


def _session_display_field_name(session: ProviderSessionRefEntry) -> str | None:
    return session.display_name_field()


def _session_findings(
    session: ProviderSessionRefEntry,
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
        enriched["provider_instance_fingerprint"] = session.context.adapter_fingerprint
        enriched["native"] = _session_native_payload(session)
        findings.append(enriched)

    if findings:
        return tuple(findings)

    return session.supplemental_findings(query=query, matched_field=matched_field)


def _matched_field_name(session: ProviderSessionRefEntry, *, query: str) -> str:
    matched_fields = _matched_query_fields(session, query=query)
    if matched_fields:
        return matched_fields[0][0]
    return session.matched_field(query)


def _merge_session(
    sessions_by_id: dict[str, ProviderSessionRefEntry],
    session: ProviderSessionRefEntry,
) -> None:
    session_key = session.uri
    existing = sessions_by_id.get(session_key)
    if existing is None:
        sessions_by_id[session_key] = session
        return

    if type(existing.session_ref) is type(session.session_ref):
        sessions_by_id[session_key] = existing.merge(session)
        return

    if _session_preference_key(session) > _session_preference_key(existing):
        sessions_by_id[session_key] = session


def _dedupe_sessions(sessions: list[ProviderSessionRefEntry]) -> list[ProviderSessionRefEntry]:
    deduped: dict[str, ProviderSessionRefEntry] = {}
    for session in sessions:
        _merge_session(deduped, session)
    return _sort_sessions(list(deduped.values()), "lexical")


def _sort_sessions(sessions: list[ProviderSessionRefEntry], sort: str) -> list[ProviderSessionRefEntry]:
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


def _session_preference_key(session: ProviderSessionRefEntry) -> tuple[float, int, str]:
    timestamp = session.sort_timestamp()
    return (
        timestamp if timestamp is not None else float("-inf"),
        len(session.canonical_findings()),
        str(session.primary_artifact_path() or ""),
    )


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



def _format_resolved_session_choices(sessions: list[ProviderSessionRefEntry]) -> str:
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


def _session_is_extractable(session: ProviderSessionRefEntry) -> bool:
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



__all__ = [
    "chat_session_resolved_stats",
    "chat_session_stats",
    "find_chat_session",
    "format_chat_session_resolved_stats_markdown",
    "format_chat_session_stats_markdown",
    "list_chat_sessions",
    "resolve_chat_sessions",
    "configured_session_provider_contexts",
    "configured_session_agents",
    "supported_provider_families",
]
