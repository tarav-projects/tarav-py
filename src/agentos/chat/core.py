from __future__ import annotations

import glob
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos._core.project import (
    agentos_home_dir,
    find_agentos_project_root,
    global_config_path,
    load_global_config,
    load_project_config,
    project_config_path,
)
from agentos._core.scan import DEFAULT_SCAN_EXCLUDES
from agentos.chat.sessions import (
    ChatSession,
    ClaudeCodeChatSession,
    CodexChatSession,
    CopilotCliChatSession,
    GeminiCliChatSession,
    OpenclawChatSession,
    OpencodeChatSession,
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


@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    direct_paths: tuple[str, ...]
    grep_paths: tuple[str, ...] = ()
    sqlite_db_paths: tuple[str, ...] = ()

    def resolved_direct_targets(self) -> tuple[Path, ...]:
        return tuple(Path(raw_path).expanduser().resolve() for raw_path in self.direct_paths)

    def resolved_grep_targets(self) -> tuple[Path, ...]:
        raw_paths = self.grep_paths or self.direct_paths
        return tuple(Path(raw_path).expanduser().resolve() for raw_path in raw_paths)

    def resolved_sqlite_db_paths(self) -> tuple[Path, ...]:
        return tuple(Path(raw_path).expanduser().resolve() for raw_path in self.sqlite_db_paths)


@dataclass(frozen=True)
class ProviderSearchContext:
    provider_spec: ProviderSpec
    direct_targets: tuple[Path, ...]
    direct_existing_targets: tuple[Path, ...]
    direct_missing_targets: tuple[Path, ...]
    grep_targets: tuple[Path, ...]
    grep_existing_targets: tuple[Path, ...]
    grep_missing_targets: tuple[Path, ...]
    sqlite_db_paths: tuple[Path, ...]
    sqlite_existing_db_paths: tuple[Path, ...]
    sqlite_missing_db_paths: tuple[Path, ...]


def supported_provider_specs() -> tuple[ProviderSpec, ...]:
    return (
        ProviderSpec(
            provider="copilot-cli",
            direct_paths=(
                "~/.copilot/session-state",
            ),
        ),
        ProviderSpec(
            provider="gemini-cli",
            direct_paths=(
                "~/.gemini/tmp",
                "~/.gemini/history",
            ),
        ),
        ProviderSpec(
            provider="codex",
            direct_paths=(
                "~/.codex/sessions",
                "~/.codex/archived_sessions",
                "~/.codex/session_index.jsonl",
            ),
            grep_paths=(
                "~/.codex/sessions",
                "~/.codex/archived_sessions",
                "~/.codex/session_index.jsonl",
            ),
        ),
        ProviderSpec(
            provider="claude-code",
            direct_paths=(
                "~/.claude/projects",
                "~/Library/Application Support/Claude/claude-code-sessions",
            ),
            grep_paths=(
                "~/.claude",
                "~/Library/Application Support/Claude/claude-code-sessions",
            ),
        ),
        ProviderSpec(
            provider="opencode",
            direct_paths=(
                "~/.local/share/opencode/storage/session_diff",
            ),
            grep_paths=(
                "~/.local/share/opencode/storage",
                "~/.local/share/opencode/log",
            ),
            sqlite_db_paths=("~/.local/share/opencode/opencode.db",),
        ),
        ProviderSpec(
            provider="openclaw",
            direct_paths=(
                "~/.openclaw/agents",
            ),
            grep_paths=(
                "~/.openclaw/agents",
            ),
        ),
    )


def configured_provider_specs(*, start_path: Path | str = ".") -> tuple[ProviderSpec, ...]:
    provider_specs = list(supported_provider_specs())
    provider_specs.extend(_load_configured_provider_specs(start_path=start_path))
    return _merge_provider_specs(tuple(provider_specs))


def _load_configured_provider_specs(*, start_path: Path | str = ".") -> tuple[ProviderSpec, ...]:
    configs: list[dict[str, object]] = []

    global_path = global_config_path(agentos_home_dir())
    if global_path.exists():
        configs.append(load_global_config(global_path))

    project_root = find_agentos_project_root(start_path)
    if project_root is not None:
        project_path = project_config_path(project_root)
        if project_path.exists():
            configs.append(load_project_config(project_path))

    provider_specs: list[ProviderSpec] = []
    for config in configs:
        provider_specs.extend(_provider_specs_from_config(config))
    return tuple(provider_specs)


def _provider_specs_from_config(config: dict[str, object]) -> tuple[ProviderSpec, ...]:
    chat_config = config.get("chat")
    if chat_config is None:
        return ()
    if not isinstance(chat_config, dict):
        raise CliError("config field chat must be a JSON object")

    raw_instances = chat_config.get("provider_instances")
    if raw_instances is None:
        return ()
    if not isinstance(raw_instances, list):
        raise CliError("config field chat.provider_instances must be a JSON array")

    provider_specs: list[ProviderSpec] = []
    for index, raw_instance in enumerate(raw_instances):
        if not isinstance(raw_instance, dict):
            raise CliError(f"chat.provider_instances[{index}] must be a JSON object")
        provider_specs.append(_provider_spec_from_instance_config(raw_instance, index=index))
    return tuple(provider_specs)


def _provider_spec_from_instance_config(raw_instance: dict[str, object], *, index: int) -> ProviderSpec:
    provider = raw_instance.get("provider")
    if not isinstance(provider, str) or not provider:
        raise CliError(f"chat.provider_instances[{index}].provider is required")

    supported_providers = {spec.provider for spec in supported_provider_specs()}
    if provider not in supported_providers:
        raise CliError(
            f"chat.provider_instances[{index}].provider must be one of: {', '.join(sorted(supported_providers))}"
        )

    home = raw_instance.get("home")
    raw_direct_paths = raw_instance.get("direct_paths")
    raw_grep_paths = raw_instance.get("grep_paths")
    raw_sqlite_db_paths = raw_instance.get("sqlite_db_paths")
    raw_sqlite_db_path = raw_instance.get("sqlite_db_path")

    if raw_sqlite_db_path is not None and raw_sqlite_db_paths is not None:
        raise CliError(
            f"chat.provider_instances[{index}] must not define both sqlite_db_path and sqlite_db_paths"
        )

    direct_paths = _load_optional_string_tuple(
        raw_direct_paths,
        field_name=f"chat.provider_instances[{index}].direct_paths",
    )
    grep_paths = _load_optional_string_tuple(
        raw_grep_paths,
        field_name=f"chat.provider_instances[{index}].grep_paths",
    )
    sqlite_db_paths = _load_optional_string_tuple(
        raw_sqlite_db_paths if raw_sqlite_db_paths is not None else raw_sqlite_db_path,
        field_name=f"chat.provider_instances[{index}].sqlite_db_paths",
    )

    if home is not None:
        if not isinstance(home, str) or not home.strip():
            raise CliError(f"chat.provider_instances[{index}].home must be a non-empty string")
        if direct_paths or grep_paths or sqlite_db_paths:
            raise CliError(
                f"chat.provider_instances[{index}] must define either home or explicit paths, not both"
            )
        return _provider_spec_from_home(provider, home.strip(), index=index)

    if not direct_paths:
        raise CliError(
            f"chat.provider_instances[{index}] must define home or direct_paths"
        )

    return ProviderSpec(
        provider=provider,
        direct_paths=direct_paths,
        grep_paths=grep_paths,
        sqlite_db_paths=sqlite_db_paths,
    )


def _provider_spec_from_home(provider: str, home: str, *, index: int) -> ProviderSpec:
    normalized_home = home.rstrip("/")

    if provider == "copilot-cli":
        return ProviderSpec(provider=provider, direct_paths=(f"{normalized_home}/session-state",))
    if provider == "gemini-cli":
        return ProviderSpec(
            provider=provider,
            direct_paths=(f"{normalized_home}/tmp", f"{normalized_home}/history"),
        )
    if provider == "codex":
        return ProviderSpec(
            provider=provider,
            direct_paths=(
                f"{normalized_home}/sessions",
                f"{normalized_home}/archived_sessions",
                f"{normalized_home}/session_index.jsonl",
            ),
            grep_paths=(
                f"{normalized_home}/sessions",
                f"{normalized_home}/archived_sessions",
                f"{normalized_home}/session_index.jsonl",
            ),
        )
    if provider == "opencode":
        return ProviderSpec(
            provider=provider,
            direct_paths=(f"{normalized_home}/storage/session_diff",),
            grep_paths=(f"{normalized_home}/storage", f"{normalized_home}/log"),
            sqlite_db_paths=(f"{normalized_home}/opencode.db",),
        )
    if provider == "openclaw":
        return ProviderSpec(
            provider=provider,
            direct_paths=(f"{normalized_home}/agents",),
            grep_paths=(f"{normalized_home}/agents",),
        )
    if provider == "claude-code":
        raise CliError(
            f"chat.provider_instances[{index}].home is not supported for claude-code; use direct_paths and grep_paths"
        )

    raise CliError(f"unsupported provider instance provider: {provider}")


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


def _merge_provider_specs(provider_specs: tuple[ProviderSpec, ...]) -> tuple[ProviderSpec, ...]:
    merged_specs: dict[str, ProviderSpec] = {}

    for provider_spec in provider_specs:
        existing = merged_specs.get(provider_spec.provider)
        if existing is None:
            merged_specs[provider_spec.provider] = provider_spec
            continue

        merged_specs[provider_spec.provider] = ProviderSpec(
            provider=provider_spec.provider,
            direct_paths=_unique_strings(existing.direct_paths + provider_spec.direct_paths),
            grep_paths=_unique_strings(existing.grep_paths + provider_spec.grep_paths),
            sqlite_db_paths=_unique_strings(existing.sqlite_db_paths + provider_spec.sqlite_db_paths),
        )

    preferred_order = [spec.provider for spec in supported_provider_specs()]
    return tuple(
        merged_specs[provider]
        for provider in preferred_order
        if provider in merged_specs
    )


def list_chat_sessions(
    *,
    sort: str = "lexical",
    full_output: bool = False,
    limit: int | None = None,
    providers: tuple[str, ...] | None = None,
) -> dict[str, object]:
    _validate_sort_choice(sort)
    _validate_session_limit(limit)

    provider_payloads: list[dict[str, Any]] = []
    total_sessions = 0

    for context in _iter_provider_contexts(providers):
        sessions = _sort_sessions(_discover_direct_provider_sessions(context), sort)
        if limit is not None:
            sessions = sessions[:limit]
        provider_payload = _build_provider_payload(
            context,
            include_grep=False,
            item_count_key="session_count",
            item_count=len(sessions),
        )
        provider_payload["session_ids"] = [session.session_id for session in sessions]
        provider_payload["sessions"] = [_session_summary(session) for session in sessions]
        provider_payloads.append(provider_payload)
        total_sessions += len(sessions)

    output_providers = (
        provider_payloads
        if full_output
        else [payload for payload in provider_payloads if payload["session_count"] > 0]
    )
    return {
        "status": "ok",
        "command": "chat session list",
        "sort": sort,
        "provider_count": len(output_providers),
        "session_count": total_sessions,
        "providers": output_providers,
    }


def chat_session_stats(
    *,
    full_output: bool = False,
    providers: tuple[str, ...] | None = None,
) -> dict[str, object]:
    provider_payloads: list[dict[str, Any]] = []
    total_sessions = 0
    total_extractable_sessions = 0
    total_non_extractable_sessions = 0

    for context in _iter_provider_contexts(providers):
        sessions = _sort_sessions(_discover_direct_provider_sessions(context), "lexical")
        stats_payload = _build_stats_provider_payload(context, sessions=sessions)
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
        "provider_count": len(output_providers),
        "session_count": total_sessions,
        "extractable_session_count": total_extractable_sessions,
        "non_extractable_session_count": total_non_extractable_sessions,
        "providers": output_providers,
    }


def format_chat_session_stats_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Chat Session Stats",
        "",
        f"- Providers: {payload['provider_count']}",
        f"- Sessions: {payload['session_count']}",
        f"- Extractable: {payload['extractable_session_count']}",
        f"- Non-extractable: {payload['non_extractable_session_count']}",
    ]

    providers = payload.get("providers")
    if not isinstance(providers, list) or not providers:
        return "\n".join(lines)

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
                f"- Canonical findings: {provider_payload.get('canonical_finding_count', 0)}",
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
                name = example.get("thread_name") or example.get("title")
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


def find_chat_session(
    query: str,
    *,
    include_grep: bool = False,
    full_output: bool = False,
    providers: tuple[str, ...] | None = None,
) -> dict[str, object]:
    all_findings: list[dict[str, Any]] = []
    provider_payloads: list[dict[str, Any]] = []

    for context in _iter_provider_contexts(providers):
        provider_findings, provider_payload = _find_session_for_provider(
            context,
            query,
            include_grep=include_grep,
        )
        all_findings.extend(provider_findings)
        provider_payloads.append(provider_payload)

    all_findings = _sort_findings(all_findings)
    output_providers = (
        provider_payloads
        if full_output
        else [payload for payload in provider_payloads if payload["finding_count"] > 0]
    )
    return {
        "status": "ok",
        "command": "chat session find",
        "query": query,
        "grep_enabled": include_grep,
        "provider_count": len(output_providers),
        "finding_count": len(all_findings),
        "providers": output_providers,
        "findings": all_findings,
    }


def resolve_chat_sessions(
    query: str,
    *,
    providers: tuple[str, ...] | None = None,
) -> list[ChatSession]:
    resolved_sessions: list[ChatSession] = []
    for context in _iter_provider_contexts(providers):
        resolved_sessions.extend(_find_direct_provider_sessions(context, query))
    return _sort_sessions(_dedupe_sessions(resolved_sessions), "lexical")


def _iter_provider_contexts(providers: tuple[str, ...] | None) -> tuple[ProviderSearchContext, ...]:
    provider_specs = configured_provider_specs()
    if providers is not None:
        requested_providers = set(providers)
        provider_specs = tuple(
            provider_spec
            for provider_spec in provider_specs
            if provider_spec.provider in requested_providers
        )

    return tuple(_build_provider_context(provider_spec) for provider_spec in provider_specs)


def _build_provider_context(provider_spec: ProviderSpec) -> ProviderSearchContext:
    direct_targets = provider_spec.resolved_direct_targets()
    grep_targets = provider_spec.resolved_grep_targets()
    sqlite_db_paths = provider_spec.resolved_sqlite_db_paths()

    return ProviderSearchContext(
        provider_spec=provider_spec,
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
    context: ProviderSearchContext,
    query: str,
    *,
    include_grep: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen_keys: set[tuple[object, ...]] = set()

    direct_sessions = _find_direct_provider_sessions(context, query)
    for session in direct_sessions:
        for finding in _session_findings(session, query=query):
            _append_unique_finding(findings, seen_keys, finding)

    if include_grep:
        for target in context.grep_existing_targets:
            for finding in _scan_grep_findings(
                provider=context.provider_spec.provider,
                target=target,
                session_id=query,
            ):
                _append_unique_finding(findings, seen_keys, finding)

    payload = _build_provider_payload(
        context,
        include_grep=include_grep,
        item_count_key="finding_count",
        item_count=len(findings),
    )
    return _sort_findings(findings), payload


def _build_provider_payload(
    context: ProviderSearchContext,
    *,
    include_grep: bool,
    item_count_key: str,
    item_count: int,
) -> dict[str, Any]:
    if include_grep:
        candidate_targets = _unique_paths(context.direct_targets + context.grep_targets)
        searched_targets = _unique_paths(
            context.direct_existing_targets + context.grep_existing_targets
        )
        missing_targets = _unique_paths(
            context.direct_missing_targets + context.grep_missing_targets
        )
    else:
        candidate_targets = context.direct_targets
        searched_targets = context.direct_existing_targets
        missing_targets = context.direct_missing_targets

    payload = {
        "provider": context.provider_spec.provider,
        "candidate_targets": [str(path) for path in candidate_targets],
        "searched_targets": [str(path) for path in searched_targets],
        "missing_targets": [str(path) for path in missing_targets],
        "sqlite_db_paths": [str(path) for path in context.sqlite_db_paths],
        "sqlite_existing_db_paths": [str(path) for path in context.sqlite_existing_db_paths],
        "sqlite_missing_db_paths": [str(path) for path in context.sqlite_missing_db_paths],
        "sqlite_db_path": (
            str(context.sqlite_db_paths[0]) if len(context.sqlite_db_paths) == 1 else None
        ),
        "sqlite_db_exists": (
            context.sqlite_db_paths[0].exists() if len(context.sqlite_db_paths) == 1 else None
        ),
        "strategies_attempted": _strategies_attempted(context, include_grep=include_grep),
        item_count_key: item_count,
    }
    return payload


def _build_stats_provider_payload(
    context: ProviderSearchContext,
    *,
    sessions: list[ChatSession],
) -> dict[str, Any]:
    extractable_sessions = [session for session in sessions if _session_is_extractable(session)]
    timestamps = [
        (session, session.sort_timestamp())
        for session in sessions
        if session.sort_timestamp() is not None
    ]
    timestamps.sort(key=lambda item: (item[1] or 0.0, item[0].session_id))

    payload = _build_provider_payload(
        context,
        include_grep=False,
        item_count_key="session_count",
        item_count=len(sessions),
    )
    payload.update(
        {
            "extractable_session_count": len(extractable_sessions),
            "non_extractable_session_count": len(sessions) - len(extractable_sessions),
            "canonical_finding_count": sum(len(session.canonical_findings()) for session in sessions),
            "session_id_examples": [session.session_id for session in sessions[:3]],
            "session_examples": [_session_summary(session) for session in sessions[:3]],
            "oldest_session_id": timestamps[0][0].session_id if timestamps else None,
            "oldest_session_name": _session_display_name(timestamps[0][0]) if timestamps else None,
            "oldest_session_at": _format_stats_timestamp(timestamps[0][1]) if timestamps else None,
            "latest_session_id": timestamps[-1][0].session_id if timestamps else None,
            "latest_session_name": _session_display_name(timestamps[-1][0]) if timestamps else None,
            "latest_session_at": _format_stats_timestamp(timestamps[-1][1]) if timestamps else None,
        }
    )
    return payload


def _strategies_attempted(
    context: ProviderSearchContext,
    *,
    include_grep: bool,
) -> list[str]:
    strategies = ["path"]
    if context.sqlite_db_paths:
        strategies.append("sqlite")
    if include_grep:
        strategies.append("grep")
    return strategies


def _discover_direct_provider_sessions(context: ProviderSearchContext) -> list[ChatSession]:
    provider = context.provider_spec.provider
    if provider == "claude-code":
        return _list_claude_code_sessions(targets=context.direct_existing_targets)
    if provider == "codex":
        return _list_codex_sessions(targets=context.direct_existing_targets)
    if provider == "copilot-cli":
        return _list_copilot_sessions(targets=context.direct_existing_targets)
    if provider == "gemini-cli":
        return _list_gemini_sessions(targets=context.direct_existing_targets)
    if provider == "opencode":
        return _list_opencode_sessions(
            targets=context.direct_existing_targets,
            sqlite_db_paths=context.sqlite_existing_db_paths,
        )
    if provider == "openclaw":
        return _list_openclaw_sessions(targets=context.direct_existing_targets)
    return []


def _find_direct_provider_sessions(
    context: ProviderSearchContext,
    query: str,
) -> list[ChatSession]:
    provider = context.provider_spec.provider
    if provider == "claude-code":
        return _find_claude_code_sessions(
            targets=context.direct_existing_targets,
            query=query,
        )
    if provider == "codex":
        return _find_codex_sessions(
            targets=context.direct_existing_targets,
            query=query,
        )
    if provider == "copilot-cli":
        return _find_copilot_sessions(
            targets=context.direct_existing_targets,
            session_id=query,
        )
    if provider == "gemini-cli":
        return _find_gemini_sessions(
            targets=context.direct_existing_targets,
            session_id=query,
        )
    if provider == "opencode":
        return _find_opencode_sessions(
            targets=context.direct_existing_targets,
            session_id=query,
            sqlite_db_paths=context.sqlite_existing_db_paths,
        )
    if provider == "openclaw":
        return _find_openclaw_sessions(
            targets=context.direct_existing_targets,
            session_id=query,
        )
    return []


def _list_claude_code_sessions(
    *,
    targets: tuple[Path, ...],
) -> list[ChatSession]:
    sessions: list[ChatSession] = []

    for target in targets:
        if target.name == "projects":
            for path in _glob_paths(target, "**/*.jsonl"):
                session = _read_claude_project_session(path)
                if session is not None:
                    sessions.append(session)
            continue

        for path in _glob_paths(target, "**/*.json"):
            session = _read_claude_desktop_session(path)
            if session is not None:
                sessions.append(session)

    return _dedupe_sessions(sessions)


def _find_claude_code_sessions(
    *,
    targets: tuple[Path, ...],
    query: str,
) -> list[ChatSession]:
    sessions_by_id: dict[tuple[str, str], ChatSession] = {}
    all_sessions = _list_claude_code_sessions(targets=targets)

    for session in all_sessions:
        if session.session_id == query:
            _merge_session(sessions_by_id, session)
            continue
        if isinstance(session, ClaudeCodeChatSession) and session.title == query:
            _merge_session(sessions_by_id, session)

    return _sort_sessions(list(sessions_by_id.values()), "lexical")


def _list_codex_sessions(
    *,
    targets: tuple[Path, ...],
) -> list[ChatSession]:
    sessions_by_id: dict[tuple[str, str], ChatSession] = {}

    for target in targets:
        if target.is_file() and target.name == "session_index.jsonl":
            for session in _read_codex_index_sessions(target):
                _merge_session(sessions_by_id, session)
            continue
        for path in _glob_paths(target, "**/rollout-*.jsonl"):
            session = _read_codex_rollout_session(path)
            if session is not None:
                _merge_session(sessions_by_id, session)

    return _sort_sessions(list(sessions_by_id.values()), "lexical")


def _find_codex_sessions(
    *,
    targets: tuple[Path, ...],
    query: str,
) -> list[ChatSession]:
    sessions_by_id: dict[tuple[str, str], ChatSession] = {}
    all_sessions = _list_codex_sessions(targets=targets)

    for session in all_sessions:
        if session.session_id == query:
            _merge_session(sessions_by_id, session)
            continue
        if isinstance(session, CodexChatSession) and session.thread_name == query:
            _merge_session(sessions_by_id, session)

    return _sort_sessions(list(sessions_by_id.values()), "lexical")


def _list_copilot_sessions(
    *,
    targets: tuple[Path, ...],
) -> list[ChatSession]:
    sessions_by_id: dict[tuple[str, str], ChatSession] = {}

    for target in targets:
        if not target.is_dir():
            continue

        for child in sorted(target.iterdir(), key=lambda path: path.name):
            session: ChatSession | None = None
            if child.is_dir():
                session = CopilotCliChatSession(
                    session_id=child.name,
                    session_root=child,
                    updated_at=_copilot_updated_at(child),
                )
            elif child.is_file() and child.suffix == ".jsonl":
                session = CopilotCliChatSession(
                    session_id=child.stem,
                    session_file=child,
                    updated_at=safe_path_mtime(child),
                )

            if session is not None:
                _merge_session(sessions_by_id, session)

    return _sort_sessions(list(sessions_by_id.values()), "lexical")


def _find_copilot_sessions(
    *,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[ChatSession]:
    sessions: list[ChatSession] = []

    for target in targets:
        session_root = target / session_id
        session_file = target / f"{session_id}.jsonl"
        if not session_root.is_dir() and not session_file.is_file():
            continue

        sessions.append(
            CopilotCliChatSession(
                session_id=session_id,
                session_root=session_root if session_root.is_dir() else None,
                session_file=session_file if session_file.is_file() else None,
                updated_at=_copilot_updated_at(session_root if session_root.is_dir() else None)
                or safe_path_mtime(session_file if session_file.is_file() else None),
            )
        )

    return _dedupe_sessions(sessions)


def _list_gemini_sessions(
    *,
    targets: tuple[Path, ...],
) -> list[ChatSession]:
    sessions: list[ChatSession] = []

    for target in targets:
        for path in _glob_paths(target, "**/chats/session-*.json"):
            session = _read_gemini_session(path)
            if session is not None:
                sessions.append(session)

    return _dedupe_sessions(sessions)


def _find_gemini_sessions(
    *,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[ChatSession]:
    sessions: list[ChatSession] = []

    for target in targets:
        for path in _glob_paths(target, "**/chats/session-*.json"):
            session = _read_gemini_session(path)
            if session is None:
                continue
            if not _gemini_session_matches(session_id, session, path):
                continue
            sessions.append(session)

    return _dedupe_sessions(sessions)


def _list_opencode_sessions(
    *,
    targets: tuple[Path, ...],
    sqlite_db_paths: tuple[Path, ...],
) -> list[ChatSession]:
    sessions_by_id: dict[tuple[str, str], ChatSession] = {}

    for target in targets:
        for path in _glob_paths(target, "*.json"):
            _merge_session(
                sessions_by_id,
                OpencodeChatSession(
                    session_id=path.stem,
                    diff_path=path,
                    updated_at=safe_path_mtime(path),
                ),
            )

    for sqlite_db_path in sqlite_db_paths:
        for session in _query_opencode_sessions(sqlite_db_path):
            _merge_session(sessions_by_id, session)

    return _sort_sessions(list(sessions_by_id.values()), "lexical")


def _find_opencode_sessions(
    *,
    targets: tuple[Path, ...],
    session_id: str,
    sqlite_db_paths: tuple[Path, ...],
) -> list[ChatSession]:
    sessions_by_id: dict[tuple[str, str], ChatSession] = {}

    for target in targets:
        session_file = target / f"{session_id}.json"
        if session_file.is_file():
            _merge_session(
                sessions_by_id,
                OpencodeChatSession(
                    session_id=session_id,
                    diff_path=session_file,
                    updated_at=safe_path_mtime(session_file),
                ),
            )

    for sqlite_db_path in sqlite_db_paths:
        for session in _query_opencode_sessions(sqlite_db_path, session_id=session_id):
            _merge_session(sessions_by_id, session)

    return _sort_sessions(list(sessions_by_id.values()), "lexical")


def _list_openclaw_sessions(
    *,
    targets: tuple[Path, ...],
) -> list[ChatSession]:
    sessions_by_id: dict[tuple[str, str], ChatSession] = {}

    for target in targets:
        for agent_dir in _iter_openclaw_agent_dirs(target):
            for session in _read_openclaw_agent_sessions(agent_dir):
                _merge_session(sessions_by_id, session)

    return _sort_sessions(list(sessions_by_id.values()), "lexical")


def _find_openclaw_sessions(
    *,
    targets: tuple[Path, ...],
    session_id: str,
) -> list[ChatSession]:
    sessions_by_id: dict[tuple[str, str], ChatSession] = {}

    for target in targets:
        for agent_dir in _iter_openclaw_agent_dirs(target):
            for session in _read_openclaw_agent_sessions(agent_dir):
                if session.session_id != session_id and session_id not in session.session_keys:
                    continue
                _merge_session(sessions_by_id, session)

    return _sort_sessions(list(sessions_by_id.values()), "lexical")


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
    summary: dict[str, Any] = {"session_id": session.session_id}
    if isinstance(session, ClaudeCodeChatSession) and session.title is not None:
        summary["title"] = session.title
    if isinstance(session, CodexChatSession) and session.thread_name is not None:
        summary["thread_name"] = session.thread_name
    return summary


def _session_display_name(session: ChatSession) -> str | None:
    if isinstance(session, ClaudeCodeChatSession):
        return session.title
    if isinstance(session, CodexChatSession):
        return session.thread_name
    return None


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
        if isinstance(session, ClaudeCodeChatSession) and session.title is not None:
            enriched["title"] = session.title
        if isinstance(session, CodexChatSession) and session.thread_name is not None:
            enriched["thread_name"] = session.thread_name
        if isinstance(session, OpenclawChatSession) and session.session_keys:
            enriched["session_keys"] = list(session.session_keys)
        findings.append(enriched)

    if findings:
        return tuple(findings)

    if isinstance(session, CodexChatSession) and session.index_paths:
        for path in session.index_paths:
            findings.append(
                {
                    "provider": session.provider,
                    "strategy": "index",
                    "match_kind": "exact",
                    "path": str(path),
                    "matched_field": matched_field,
                    "matched_value": query,
                    "session_id": session.session_id,
                    "thread_name": session.thread_name,
                }
            )
    return tuple(findings)


def _matched_field_name(session: ChatSession, *, query: str) -> str:
    if session.session_id == query:
        return "session_id"
    if isinstance(session, OpenclawChatSession) and query in session.session_keys:
        return "session_key"
    if isinstance(session, CodexChatSession):
        if session.thread_name == query:
            return "thread_name"
    if isinstance(session, ClaudeCodeChatSession):
        if session.title == query:
            return "title"
    return "query"


def _merge_session(
    sessions_by_id: dict[tuple[str, str], ChatSession],
    session: ChatSession,
) -> None:
    session_key = (session.provider, session.session_id)
    existing = sessions_by_id.get(session_key)
    if existing is None:
        sessions_by_id[session_key] = session
        return

    if type(existing) is type(session):
        sessions_by_id[session_key] = existing.merge(session)
        return

    if _session_preference_key(session) > _session_preference_key(existing):
        sessions_by_id[session_key] = session


def _dedupe_sessions(sessions: list[ChatSession]) -> list[ChatSession]:
    deduped: dict[tuple[str, str], ChatSession] = {}
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


def _read_openclaw_agent_sessions(agent_dir: Path) -> list[OpenclawChatSession]:
    sessions_dir = agent_dir / "sessions"
    index_path = sessions_dir / "sessions.json"
    transcript_paths = {
        path.stem: path
        for path in sorted(sessions_dir.glob("*.jsonl"), key=lambda path: path.name)
        if ".reset." not in path.name
    }

    sessions_by_id: dict[str, OpenclawChatSession] = {}
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

            session = OpenclawChatSession(
                session_id=session_id,
                transcript_path=transcript_path,
                sessions_index_path=index_path.resolve(),
                session_keys=(session_key,) if isinstance(session_key, str) and session_key else (),
                agent_id=agent_dir.name,
                updated_at=coerce_timestamp(entry.get("updatedAt"))
                or safe_path_mtime(transcript_path)
                or safe_path_mtime(index_path),
            )
            existing = sessions_by_id.get(session_id)
            sessions_by_id[session_id] = session if existing is None else existing.merge(session)

    for session_id, transcript_path in transcript_paths.items():
        existing = sessions_by_id.get(session_id)
        if existing is None:
            sessions_by_id[session_id] = OpenclawChatSession(
                session_id=session_id,
                transcript_path=transcript_path.resolve(),
                sessions_index_path=index_path.resolve() if index_path.exists() else None,
                session_keys=(),
                agent_id=agent_dir.name,
                updated_at=safe_path_mtime(transcript_path),
            )
            continue

        sessions_by_id[session_id] = OpenclawChatSession(
            session_id=session_id,
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


def _read_claude_project_session(path: Path) -> ClaudeCodeChatSession | None:
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

    return ClaudeCodeChatSession(
        session_id=session_id,
        artifact_paths=(path,),
        source_kind="project",
        updated_at=updated_at,
    )


def _read_claude_desktop_session(path: Path) -> ClaudeCodeChatSession | None:
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
    return ClaudeCodeChatSession(
        session_id=session_id,
        artifact_paths=(path,),
        source_kind="desktop",
        title=obj.get("title") if isinstance(obj.get("title"), str) and obj.get("title") else None,
        updated_at=updated_at,
    )


def _read_codex_rollout_session(path: Path) -> CodexChatSession | None:
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
    return CodexChatSession(
        session_id=session_id,
        artifact_paths=(path,),
        updated_at=updated_at,
    )


def _read_codex_index_sessions(path: Path) -> list[CodexChatSession]:
    if not path.is_file():
        return []

    sessions: list[CodexChatSession] = []
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
                    CodexChatSession(
                        session_id=session_id,
                        thread_name=thread_name,
                        index_paths=(path,),
                        updated_at=updated_at,
                    )
                )
    except OSError:
        return []

    return sessions


def _read_gemini_session(path: Path) -> GeminiCliChatSession | None:
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
    return GeminiCliChatSession(
        session_id=session_id,
        artifact_paths=(path,),
        updated_at=updated_at,
    )


def _gemini_session_matches(
    requested_session_id: str,
    session: GeminiCliChatSession,
    path: Path,
) -> bool:
    if requested_session_id == session.session_id:
        return True
    return requested_session_id in path.name


def _query_opencode_sessions(
    sqlite_db_path: Path,
    *,
    session_id: str | None = None,
) -> list[OpencodeChatSession]:
    try:
        connection = sqlite3.connect(str(sqlite_db_path))
    except sqlite3.Error:
        return []

    sessions: list[OpencodeChatSession] = []
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
            OpencodeChatSession(
                session_id=row_id,
                sqlite_db_path=sqlite_db_path,
                updated_at=coerce_timestamp(time_updated),
            )
        )

    return sessions


__all__ = [
    "chat_session_stats",
    "find_chat_session",
    "format_chat_session_stats_markdown",
    "list_chat_sessions",
    "resolve_chat_sessions",
    "supported_provider_specs",
]
