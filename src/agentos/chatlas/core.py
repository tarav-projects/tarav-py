from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.git_ops import run_git
from agentos._core.project import agentos_home_dir
from agentos.chat.core import (
    _build_common_session_stats,
    _build_provider_context,
    _build_provider_session_stats,
    _dedupe_sessions,
    _discover_direct_provider_sessions,
    _find_direct_provider_sessions,
    _format_resolved_session_choices,
    _format_stats_timestamp,
    _provider_family_for_name,
    _sort_sessions,
)
from agentos.chat.extractors import extract_chat_session
from agentos.chat.providers import (
    ProviderInstance,
    ProviderInstanceConfigSource,
    load_chat_config_documents,
    provider_instance_config_entries_from_config,
)
from agentos.chat.sessions import ChatSession, coerce_timestamp
from agentos.chatlas.raw import (
    _build_chatlas_provider_context,
    _chatlas_home_destination,
    _dedupe_chatlas_instances,
    _mirror_chatlas_provider_instance,
    _provider_instances_from_config_entries,
    _validate_unique_chatlas_destinations,
    supported_chatlas_provider_families,
)

CHATLAS_DIRNAME = "chatlas"
DEFAULT_CHATLAS_COMMIT_PREFIX = "chatlas update"
_NORMALIZED_SESSIONS_RELATIVE_PATH = Path("normalized") / "sessions.jsonl"
_DERIVED_TRANSCRIPTS_RELATIVE_ROOT = Path("derived") / "transcripts"
_DERIVED_SUMMARIES_RELATIVE_ROOT = Path("derived") / "summaries"
_DERIVED_BRIEF_SUMMARIES_RELATIVE_PATH = _DERIVED_SUMMARIES_RELATIVE_ROOT / "brief.jsonl"
_DERIVED_DETAILED_SUMMARIES_RELATIVE_PATH = _DERIVED_SUMMARIES_RELATIVE_ROOT / "detailed.jsonl"
_SUMMARY_RELATIVE_PATHS = {
    "brief": _DERIVED_BRIEF_SUMMARIES_RELATIVE_PATH,
    "detailed": _DERIVED_DETAILED_SUMMARIES_RELATIVE_PATH,
}
_CHATLAS_PROVIDER_INSTANCE_CONFIG_SOURCE = ProviderInstanceConfigSource(
    object_path=("chatlas", "provider_instances"),
    field_prefix="chatlas.provider_instances",
)
_CHAT_SESSION_PROVIDER_INSTANCE_CONFIG_SOURCE = ProviderInstanceConfigSource(
    object_path=("chat", "session", "provider_instances"),
    field_prefix="chat.session.provider_instances",
)
_SUMMARY_LEVELS = ("brief", "detailed")
_PROGRESS_PREFIX = "[chatlas]"


@dataclass(frozen=True)
class ChatlasSettings:
    commit_prefix: str
    provider_instances: tuple[ProviderInstance, ...]


@dataclass(frozen=True)
class ChatlasSessionSelection:
    session: dict[str, Any]
    matched_fields: tuple[tuple[str, str], ...]
    transcript_filter_match: dict[str, str]
    summary: dict[str, Any] | None
    summary_levels: dict[str, dict[str, Any]]


def default_chatlas_root() -> Path:
    return agentos_home_dir() / CHATLAS_DIRNAME


def configured_chatlas_settings(*, start_path: Path | str = ".") -> ChatlasSettings:
    commit_prefix = DEFAULT_CHATLAS_COMMIT_PREFIX
    provider_instances = [family.default_instance() for family in supported_chatlas_provider_families()]

    for config in load_chat_config_documents(start_path=start_path):
        chatlas_config = _chatlas_config_from_config(config)
        if chatlas_config is not None:
            raw_commit_prefix = chatlas_config.get("commit_prefix")
            if raw_commit_prefix is not None:
                if not isinstance(raw_commit_prefix, str) or not raw_commit_prefix.strip():
                    raise CliError("config field chatlas.commit_prefix must be a non-empty string")
                commit_prefix = raw_commit_prefix.strip()

            provider_instances.extend(
                _provider_instances_from_config_entries(
                    provider_instance_config_entries_from_config(
                        config,
                        source=_CHATLAS_PROVIDER_INSTANCE_CONFIG_SOURCE,
                    )
                )
            )
        provider_instances.extend(
            _provider_instances_from_config_entries(
                provider_instance_config_entries_from_config(
                    config,
                    source=_CHAT_SESSION_PROVIDER_INSTANCE_CONFIG_SOURCE,
                )
            )
        )

    deduped_instances = _dedupe_chatlas_instances(tuple(provider_instances))
    _validate_unique_chatlas_destinations(deduped_instances)
    return ChatlasSettings(
        commit_prefix=commit_prefix,
        provider_instances=deduped_instances,
    )


def chatlas_update(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    settings = configured_chatlas_settings(start_path=start_path)
    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    raw_root = chatlas_root_path / "raw"
    normalized_root = chatlas_root_path / "normalized"
    derived_root = chatlas_root_path / "derived"

    selected_instances = settings.provider_instances
    if providers is not None:
        selected_instances = tuple(
            instance
            for instance in selected_instances
            if instance.family in providers
        )
    selected_contexts = tuple(_build_chatlas_provider_context(instance) for instance in selected_instances)
    _emit_chatlas_progress(
        progress,
        f"update start: {len(selected_contexts)} instance(s) -> {chatlas_root_path}",
    )

    instance_payloads: list[dict[str, object]] = []
    synced_instance_count = 0
    skipped_instance_count = 0

    for context in selected_contexts:
        context_label = _chatlas_progress_context_label(context)
        _emit_chatlas_progress(progress, f"{context_label}: archive start")
        instance_payload = _mirror_chatlas_provider_instance(
            context=context,
            raw_root=raw_root,
            progress=progress,
        )
        instance_payloads.append(instance_payload)
        if bool(instance_payload["synced"]):
            synced_instance_count += 1
        else:
            skipped_instance_count += 1
        _emit_chatlas_progress(
            progress,
            f"{context_label}: archive done (synced={bool(instance_payload['synced'])})",
        )

    _ensure_git_repo(chatlas_root_path)
    _emit_chatlas_progress(progress, "materializing normalized sessions")
    normalized_sessions = _materialize_normalized_sessions(
        chatlas_root=chatlas_root_path,
        provider_instances=settings.provider_instances,
    )
    _emit_chatlas_progress(progress, f"normalized sessions: {len(normalized_sessions)}")
    _emit_chatlas_progress(progress, "materializing derived transcripts")
    derived_transcript_session_count = _materialize_derived_transcripts(
        chatlas_root=chatlas_root_path,
        normalized_sessions=normalized_sessions,
    )
    _emit_chatlas_progress(progress, f"derived transcripts: {derived_transcript_session_count}")
    _emit_chatlas_progress(progress, "materializing derived summaries")
    derived_summary_counts = _materialize_derived_summaries(
        chatlas_root=chatlas_root_path,
        normalized_sessions=normalized_sessions,
    )
    _emit_chatlas_progress(
        progress,
        f"derived summaries: brief={derived_summary_counts['brief']} detailed={derived_summary_counts['detailed']}",
    )
    _emit_chatlas_progress(progress, "checking git status")
    dataset_changes_detected = bool(run_git(chatlas_root_path, "status", "--porcelain"))

    recorded_at = utc_now_iso()
    manifest_path: Path | None = None
    if dataset_changes_detected:
        manifest_path = _write_update_manifest(
            chatlas_root=chatlas_root_path,
            payload=_build_update_manifest(
                recorded_at=recorded_at,
                chatlas_root=chatlas_root_path,
                raw_root=raw_root,
                normalized_root=normalized_root,
                derived_root=derived_root,
                settings=settings,
                selected_contexts=selected_contexts,
                synced_instance_count=synced_instance_count,
                skipped_instance_count=skipped_instance_count,
                normalized_session_count=len(normalized_sessions),
                derived_transcript_session_count=derived_transcript_session_count,
                derived_summary_counts=derived_summary_counts,
                instance_payloads=instance_payloads,
            ),
        )
        run_git(chatlas_root_path, "add", "-A")
        _emit_chatlas_progress(progress, "staged dataset changes")

    committed = False
    commit_message: str | None = None
    if dataset_changes_detected and run_git(chatlas_root_path, "status", "--porcelain").strip():
        commit_message = f"{settings.commit_prefix}: {recorded_at}"
        _emit_chatlas_progress(progress, f"creating commit: {commit_message}")
        run_git(
            chatlas_root_path,
            "-c",
            "user.name=agentos",
            "-c",
            "user.email=agentos@local.invalid",
            "commit",
            "-m",
            commit_message,
        )
        committed = True
    else:
        _emit_chatlas_progress(progress, "no git commit needed")

    provider_names = _unique_strings(tuple(context.provider_instance.family for context in selected_contexts))
    return {
        "status": "ok",
        "command": "chatlas update",
        "chatlas_root": str(chatlas_root_path),
        "raw_root": str(raw_root),
        "normalized_root": str(normalized_root),
        "derived_root": str(derived_root),
        "normalized_sessions_path": str(chatlas_root_path / _NORMALIZED_SESSIONS_RELATIVE_PATH),
        "normalized_session_count": len(normalized_sessions),
        "derived_transcript_session_count": derived_transcript_session_count,
        "derived_summaries_path": str(chatlas_root_path / _DERIVED_BRIEF_SUMMARIES_RELATIVE_PATH),
        "derived_summary_paths": {
            "brief": str(chatlas_root_path / _DERIVED_BRIEF_SUMMARIES_RELATIVE_PATH),
            "detailed": str(chatlas_root_path / _DERIVED_DETAILED_SUMMARIES_RELATIVE_PATH),
        },
        "derived_summary_count": derived_summary_counts["brief"],
        "derived_summary_counts": derived_summary_counts,
        "manifest_path": None if manifest_path is None else str(manifest_path),
        "commit_prefix": settings.commit_prefix,
        "provider_count": len(provider_names),
        "instance_count": len(selected_contexts),
        "synced_instance_count": synced_instance_count,
        "skipped_instance_count": skipped_instance_count,
        "changes_detected": dataset_changes_detected,
        "committed": committed,
        "commit_message": commit_message,
        "instances": instance_payloads,
    }


def _emit_chatlas_progress(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is None:
        return
    progress(f"{_PROGRESS_PREFIX} {message}")


def _chatlas_progress_context_label(context) -> str:
    instance = context.resolved_instance_name
    provider = context.provider_instance.family
    return f"{provider}/{instance}"


def chatlas_stats(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    full_output: bool = False,
) -> dict[str, object]:
    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    sessions = _selected_normalized_sessions(chatlas_root_path, providers=providers)

    sessions_by_provider: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        provider = _string_or_none(session.get("provider")) or "unknown"
        sessions_by_provider.setdefault(provider, []).append(session)

    requested_providers = (
        tuple(providers)
        if providers is not None
        else tuple(provider_handler.family for provider_handler in supported_chatlas_provider_families())
    )
    by_provider = [
        _build_chatlas_stats_provider_payload(provider, sessions_by_provider.get(provider, []))
        for provider in requested_providers
        if full_output or sessions_by_provider.get(provider)
    ]
    latest_manifest = _latest_update_manifest(chatlas_root_path)
    summary_levels_by_uri = _summary_levels_by_uri(chatlas_root_path)

    derived_summary_counts = _derived_summary_counts(
        sessions,
        summary_levels_by_uri=summary_levels_by_uri,
    )

    return {
        "status": "ok",
        "command": "chatlas stats",
        "chatlas_root": str(chatlas_root_path),
        "selection": {
            "providers": list(providers) if providers is not None else None,
        },
        "stats": {
            "provider_count": len(by_provider),
            "session_count": len(sessions),
            "extractable_session_count": sum(1 for session in sessions if bool(session.get("extractable"))),
            "non_extractable_session_count": sum(1 for session in sessions if not bool(session.get("extractable"))),
            "derived_transcript_session_count": sum(
                1 for session in sessions if _derived_transcript_exists(chatlas_root_path, session, output_format="markdown")
            ),
            "derived_summary_count": derived_summary_counts["brief"],
            "derived_summary_counts": derived_summary_counts,
            "by_provider": by_provider,
            "last_update_recorded_at": None if latest_manifest is None else latest_manifest.get("recorded_at"),
            "last_update_manifest_path": None if latest_manifest is None else latest_manifest.get("_manifest_path"),
        },
    }


def format_chatlas_stats_markdown(payload: dict[str, object]) -> str:
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    lines = [
        "# Chatlas Stats",
        "",
        f"- Providers: {stats.get('provider_count', 0)}",
        f"- Sessions: {stats.get('session_count', 0)}",
        f"- Extractable: {stats.get('extractable_session_count', 0)}",
        f"- Non-extractable: {stats.get('non_extractable_session_count', 0)}",
        f"- Derived transcripts: {stats.get('derived_transcript_session_count', 0)}",
        f"- Derived summaries: {stats.get('derived_summary_count', 0)}",
    ]

    last_update_recorded_at = stats.get("last_update_recorded_at")
    if last_update_recorded_at is not None:
        lines.append(f"- Last update: {last_update_recorded_at}")

    last_update_manifest_path = stats.get("last_update_manifest_path")
    if last_update_manifest_path is not None:
        lines.append(f"- Manifest: {last_update_manifest_path}")

    providers = stats.get("by_provider")
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
            ]
        )

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


def chatlas_query(
    *,
    query: str | None,
    text_contain: str | None = None,
    user_contain: str | None = None,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    extractable_only: bool = False,
    updated_after: float | None = None,
    include_match: bool = False,
    include_artifacts: bool = False,
    include_summary: bool = False,
    include_summary_levels: tuple[str, ...] = (),
    include_transcript_filter_match: bool = False,
    include_provider_stats: bool = False,
) -> dict[str, object]:
    _validate_chatlas_sort(sort)
    _validate_chatlas_limit(limit)
    normalized_query = None if query is None else query.strip()
    normalized_text_contain = None if text_contain is None else text_contain.strip()
    normalized_user_contain = None if user_contain is None else user_contain.strip()
    if normalized_query == "":
        normalized_query = None
    if normalized_text_contain == "":
        normalized_text_contain = None
    if normalized_user_contain == "":
        normalized_user_contain = None
    normalized_summary_levels = _normalize_summary_levels(include_summary_levels)

    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    selections = _select_chatlas_sessions(
        chatlas_root_path,
        query=normalized_query,
        text_contain=normalized_text_contain,
        user_contain=normalized_user_contain,
        providers=providers,
        extractable_only=extractable_only,
        updated_after=updated_after,
    )
    selections = _sort_chatlas_session_selections(selections, sort=sort)
    if limit is not None:
        selections = selections[:limit]

    matched_sessions: list[dict[str, Any]] = []
    for selection in selections:
        enriched = dict(selection.session)
        if not include_artifacts:
            enriched.pop("backing_artifacts", None)
        if include_summary:
            enriched["summary"] = selection.summary or _build_session_summary(chatlas_root_path, selection.session, level="brief")
        if normalized_summary_levels:
            enriched["summary_levels"] = {
                level: selection.summary_levels.get(level) or _build_session_summary(
                    chatlas_root_path,
                    selection.session,
                    level=level,
                )
                for level in normalized_summary_levels
            }
        if include_match and normalized_query is not None:
            enriched["match"] = {
                "query": normalized_query,
                "kind": "exact_identity",
                "fields": [
                    {
                        "field": field_name,
                        "value": value,
                    }
                    for field_name, value in selection.matched_fields
                ],
            }
        if include_transcript_filter_match and selection.transcript_filter_match:
            enriched["transcript_filter_match"] = selection.transcript_filter_match
        if include_provider_stats:
            enriched["provider_stats"] = _chatlas_provider_stats_for_session(
                chatlas_root_path,
                selection.session,
            )
        matched_sessions.append(enriched)

    expansions: list[str] = []
    if include_artifacts:
        expansions.append("backing_artifacts")
    if include_summary:
        expansions.append("summary")
    if normalized_summary_levels:
        expansions.append("summary_levels")
    if include_match and normalized_query is not None:
        expansions.append("match")
    if include_transcript_filter_match and (normalized_text_contain is not None or normalized_user_contain is not None):
        expansions.append("transcript_filter_match")
    if include_provider_stats:
        expansions.append("provider_stats")
    return {
        "status": "ok",
        "command": "chatlas query",
        "selection": {
            "kind": "query" if normalized_query is not None else "all",
            "query": normalized_query,
            "providers": list(providers) if providers is not None else None,
            "filters": {
                "sort": sort,
                "limit": limit,
                "extractable": extractable_only,
                "updated_after": _format_stats_timestamp(updated_after),
                "text_contain": normalized_text_contain,
                "user_contain": normalized_user_contain,
            },
        },
        "expansions": expansions,
        "session_count": len(matched_sessions),
        "sessions": matched_sessions,
    }


def chatlas_export(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    artifact_kind: str = "transcript",
    summary_level: str = "brief",
    output_format: str = "markdown",
    chatlas_root: Path | None = None,
) -> str:
    if artifact_kind not in {"transcript", "summary"}:
        raise CliError(f"unsupported export kind: {artifact_kind}")
    if summary_level not in _SUMMARY_LEVELS:
        raise CliError(f"unsupported summary level: {summary_level}")
    if output_format not in {"json", "jsonl", "markdown"}:
        raise CliError(f"unsupported export format: {output_format}")
    if artifact_kind == "transcript" and output_format not in {"jsonl", "markdown"}:
        raise CliError("transcript export format must be jsonl or markdown")
    if artifact_kind == "summary" and output_format not in {"json", "markdown"}:
        raise CliError("summary export format must be json or markdown")

    normalized_query = query.strip()
    if not normalized_query:
        raise CliError("query must not be empty")

    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    selections = _select_chatlas_sessions(
        chatlas_root_path,
        query=normalized_query,
        providers=providers,
        extractable_only=True,
    )
    if not selections:
        raise CliError(f"no normalized Chatlas session matched query {query}")
    if len(selections) > 1:
        choices = ", ".join(str(selection.session.get("uri")) for selection in selections[:5])
        raise CliError(f"multiple Chatlas sessions matched query {query}: {choices}")

    session = selections[0].session
    if artifact_kind == "summary":
        summary = selections[0].summary_levels.get(summary_level)
        if summary is None:
            summary = _build_session_summary(chatlas_root_path, session, level=summary_level)
        return _render_summary(summary, output_format=output_format)

    transcript_path = _derived_transcript_path(chatlas_root_path, session, output_format=output_format)
    if transcript_path.is_file():
        return transcript_path.read_text(encoding="utf-8")

    rendered = _render_transcript(session, output_format=output_format)
    _write_text_if_changed(transcript_path, rendered)
    return rendered


def resolve_chatlas_sessions(
    query: str,
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
) -> list[ChatSession]:
    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    resolved_sessions: list[ChatSession] = []
    for context in _iter_chatlas_session_contexts(
        chatlas_root=chatlas_root_path,
        start_path=start_path,
        providers=providers,
    ):
        resolved_sessions.extend(_find_direct_provider_sessions(context, query))
    return _sort_sessions(_dedupe_sessions(resolved_sessions), "lexical")


def chatlas_resolved_session_stats(
    query: str,
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
) -> dict[str, object]:
    sessions = resolve_chatlas_sessions(
        query,
        providers=providers,
        chatlas_root=chatlas_root,
        start_path=start_path,
    )
    if not sessions:
        raise CliError(f"no session matched query {query}")
    if len(sessions) > 1:
        raise CliError(
            f"multiple sessions matched query {query}: {_format_resolved_session_choices(sessions)}"
        )

    session = sessions[0]
    return {
        "status": "ok",
        "command": "chatlas stats",
        "selection": {
            "kind": "query",
            "query": query,
            "providers": list(providers) if providers is not None else None,
        },
        "session": _build_common_session_stats(session, query=query),
        "stats": _build_provider_session_stats(session),
    }


def _chatlas_config_from_config(config: dict[str, object]) -> dict[str, object] | None:
    chatlas_config = config.get("chatlas")
    if chatlas_config is None:
        return None
    if not isinstance(chatlas_config, dict):
        raise CliError("config field chatlas must be a JSON object")
    return chatlas_config


def _ensure_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    git_dir = repo_root / ".git"
    if git_dir.exists() and not git_dir.is_dir():
        raise CliError(f"chatlas git path is not a directory: {git_dir}")
    if not git_dir.exists():
        run_git(repo_root, "init")


def _build_update_manifest(
    *,
    recorded_at: str,
    chatlas_root: Path,
    raw_root: Path,
    normalized_root: Path,
    derived_root: Path,
    settings: ChatlasSettings,
    selected_contexts: tuple[object, ...],
    synced_instance_count: int,
    skipped_instance_count: int,
    normalized_session_count: int,
    derived_transcript_session_count: int,
    derived_summary_counts: dict[str, int],
    instance_payloads: list[dict[str, object]],
) -> dict[str, object]:
    provider_names = _unique_strings(
        tuple(context.provider_instance.family for context in selected_contexts)
    )
    return {
        "class": "agentos.chatlas.update",
        "schema_version": 1,
        "recorded_at": recorded_at,
        "command": "chatlas update",
        "chatlas_root": str(chatlas_root),
        "raw_root": str(raw_root),
        "normalized_root": str(normalized_root),
        "derived_root": str(derived_root),
        "commit_prefix": settings.commit_prefix,
        "provider_count": len(provider_names),
        "providers": list(provider_names),
        "instance_count": len(selected_contexts),
        "synced_instance_count": synced_instance_count,
        "skipped_instance_count": skipped_instance_count,
        "normalized_session_count": normalized_session_count,
        "derived_transcript_session_count": derived_transcript_session_count,
        "derived_summary_count": derived_summary_counts["brief"],
        "derived_summary_counts": derived_summary_counts,
        "instances": instance_payloads,
    }


def _write_update_manifest(*, chatlas_root: Path, payload: dict[str, object]) -> Path:
    manifest_dir = chatlas_root / "manifests" / "updates"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    recorded_at = str(payload["recorded_at"])
    manifest_path = manifest_dir / f"{_compact_timestamp(recorded_at)}.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _resolve_chatlas_root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


def _compact_timestamp(value: str) -> str:
    return (
        value.replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace("T", "T")
        .replace("Z", "Z")
    )


def _validate_chatlas_sort(sort: str) -> None:
    if sort not in {"lexical", "newest", "oldest"}:
        raise CliError(f"unsupported chatlas query sort: {sort}")


def _validate_chatlas_limit(limit: int | None) -> None:
    if limit is None:
        return
    if limit < 1:
        raise CliError("chatlas query limit must be greater than 0")


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        items.append(value)
    return tuple(items)


def _normalize_summary_levels(levels: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for level in levels:
        if level not in _SUMMARY_LEVELS:
            raise CliError(f"unsupported summary level: {level}")
        if level in seen:
            continue
        seen.add(level)
        normalized.append(level)
    return tuple(normalized)


def _materialize_normalized_sessions(
    *,
    chatlas_root: Path,
    provider_instances: tuple[ProviderInstance, ...],
) -> list[dict[str, Any]]:
    normalized_sessions = _discover_normalized_sessions(
        raw_root=chatlas_root / "raw",
        provider_instances=provider_instances,
    )
    normalized_path = chatlas_root / _NORMALIZED_SESSIONS_RELATIVE_PATH
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(json.dumps(session, sort_keys=True) + "\n" for session in normalized_sessions)
    _write_text_if_changed(normalized_path, rendered)
    return normalized_sessions


def _materialize_derived_transcripts(
    *,
    chatlas_root: Path,
    normalized_sessions: list[dict[str, Any]],
) -> int:
    transcript_root = chatlas_root / _DERIVED_TRANSCRIPTS_RELATIVE_ROOT
    expected_paths: set[Path] = set()
    transcript_session_count = 0

    for session in normalized_sessions:
        if not _session_has_exportable_transcript(session):
            continue
        rendered_outputs: dict[str, str] = {}
        try:
            for output_format in ("jsonl", "markdown"):
                rendered_outputs[output_format] = _render_transcript(session, output_format=output_format)
        except (CliError, OSError, json.JSONDecodeError):
            continue
        transcript_session_count += 1
        for output_format, rendered_output in rendered_outputs.items():
            transcript_path = _derived_transcript_path(chatlas_root, session, output_format=output_format)
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            _write_text_if_changed(transcript_path, rendered_output)
            expected_paths.add(transcript_path)

    _prune_stale_files(root=transcript_root, expected_paths=expected_paths)
    _prune_empty_dirs(transcript_root, stop=transcript_root)
    return transcript_session_count


def _materialize_derived_summaries(
    *,
    chatlas_root: Path,
    normalized_sessions: list[dict[str, Any]],
) -> dict[str, int]:
    summary_rows_by_level = {
        level: [
            _build_session_summary(chatlas_root, session, level=level)
            for session in normalized_sessions
        ]
        for level in _SUMMARY_LEVELS
    }
    for level, rows in summary_rows_by_level.items():
        summaries_path = chatlas_root / _summary_relative_path(level)
        rendered = "".join(json.dumps(summary, sort_keys=True) + "\n" for summary in rows)
        _write_text_if_changed(summaries_path, rendered)
    return {
        level: len(rows)
        for level, rows in summary_rows_by_level.items()
    }


def _discover_normalized_sessions(
    *,
    raw_root: Path,
    provider_instances: tuple[ProviderInstance, ...],
) -> list[dict[str, Any]]:
    discovered_sessions = []
    for provider_instance in provider_instances:
        session_provider_instance = _chatlas_session_provider_instance(
            raw_root=raw_root,
            archive_provider_instance=provider_instance,
        )
        if session_provider_instance is None:
            continue
        context = _build_provider_context(session_provider_instance)
        discovered_sessions.extend(_discover_direct_provider_sessions(context))

    return [
        _normalized_session_record(session)
        for session in _dedupe_sessions(discovered_sessions)
    ]


def _chatlas_session_provider_instance(
    *,
    raw_root: Path,
    archive_provider_instance: ProviderInstance,
) -> ProviderInstance | None:
    provider_handler = _provider_family_for_name(archive_provider_instance.family)
    if provider_handler is None:
        return None

    direct_targets: list[Path] = []
    grep_targets: list[Path] = []
    sqlite_db_paths: list[Path] = []

    for home_key, source_home_path in archive_provider_instance.homes:
        raw_home_path = _chatlas_home_destination(
            raw_root=raw_root,
            home_path=source_home_path,
        )
        home_slot = _match_session_home_slot(
            provider_handler.family,
            source_home_path,
            slot_key=home_key,
        )
        if home_slot is None:
            continue
        slot_direct_paths, slot_grep_paths, slot_sqlite_db_paths = home_slot.build_paths(home=raw_home_path)
        direct_targets.extend(slot_direct_paths)
        grep_targets.extend(slot_grep_paths or slot_direct_paths)
        sqlite_db_paths.extend(slot_sqlite_db_paths)

    if not direct_targets and not sqlite_db_paths:
        return None

    return ProviderInstance(
        family=archive_provider_instance.family,
        instance_id=archive_provider_instance.instance_id,
        label=archive_provider_instance.label,
        homes=archive_provider_instance.homes,
        direct_targets=tuple(direct_targets),
        grep_targets=tuple(grep_targets),
        sqlite_db_paths=tuple(sqlite_db_paths),
        cli_command=archive_provider_instance.cli_command,
        env=archive_provider_instance.env,
        timeout_sec=archive_provider_instance.timeout_sec,
        live_usage_refresh=archive_provider_instance.live_usage_refresh,
        usage_progression_limit=archive_provider_instance.usage_progression_limit,
        includes=archive_provider_instance.includes,
        excludes=archive_provider_instance.excludes,
        anchors=archive_provider_instance.anchors,
        is_default=archive_provider_instance.is_default,
    )


def _match_session_home_slot(
    provider_family: str,
    source_home_path: Path,
    *,
    slot_key: str | None = None,
):
    provider_handler = _provider_family_for_name(provider_family)
    if provider_handler is None:
        return None

    if slot_key is not None:
        for home_slot in provider_handler.home_slots:
            if home_slot.key == slot_key:
                return home_slot

    source_home_name = source_home_path.name
    for home_slot in provider_handler.home_slots:
        if Path(home_slot.default_home).expanduser().name == source_home_name:
            return home_slot
    if len(provider_handler.home_slots) == 1:
        return provider_handler.home_slots[0]
    return None


def _normalized_session_record(session) -> dict[str, Any]:
    payload = _build_common_session_stats(
        session,
        include_artifacts=True,
    )
    payload["class"] = "agentos.chatlas.session"
    payload["schema_version"] = 1
    return payload


def _build_session_summary(chatlas_root: Path, session: dict[str, Any], *, level: str = "brief") -> dict[str, Any]:
    if level not in _SUMMARY_LEVELS:
        raise CliError(f"unsupported summary level: {level}")

    turns = _load_transcript_turns(chatlas_root, session)
    user_turns = [turn for turn in turns if _string_or_none(turn.get("role")) == "user"]
    assistant_turns = [turn for turn in turns if _string_or_none(turn.get("role")) == "assistant"]
    first_user_text = _first_turn_text(user_turns)
    last_assistant_text = _last_turn_text(assistant_turns)
    preview_source = first_user_text or last_assistant_text or _first_turn_text(turns)
    base_summary = {
        "schema_version": 1,
        "level": level,
        "uri": session.get("uri"),
        "provider": session.get("provider"),
        "provider_instance_fingerprint": session.get("provider_instance_fingerprint"),
        "session_id": session.get("session_id"),
        "display_name": session.get("display_name"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "turn_count": len(turns),
        "user_turn_count": len(user_turns),
        "assistant_turn_count": len(assistant_turns),
        "first_user_text": first_user_text,
        "last_assistant_text": last_assistant_text,
        "text_preview": _truncate_summary_text(preview_source),
    }
    if level == "brief":
        base_summary["class"] = "agentos.chatlas.session_summary"
        return base_summary

    base_summary["class"] = "agentos.chatlas.session_summary.detailed"
    base_summary["first_turn_text"] = _first_turn_text(turns)
    base_summary["last_turn_text"] = _last_turn_text(turns)
    base_summary["user_turn_previews"] = _turn_text_previews(user_turns, limit=3)
    base_summary["assistant_turn_previews"] = _turn_text_previews(assistant_turns, limit=3)
    base_summary["turn_previews"] = _turn_previews(turns, limit=6)
    return base_summary


def _session_has_exportable_transcript(session: dict[str, Any]) -> bool:
    if not bool(session.get("extractable")):
        return False
    return _primary_backing_artifact_path(session) is not None


def _primary_backing_artifact_path(session: dict[str, Any]) -> Path | None:
    primary = session.get("primary_backing_artifact")
    if not isinstance(primary, dict):
        return None
    path = primary.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    return Path(path).expanduser().resolve()


def _render_transcript(session: dict[str, Any], *, output_format: str) -> str:
    artifact_path = _primary_backing_artifact_path(session)
    if artifact_path is None:
        raise CliError(f"session has no extractable primary backing artifact: {session.get('uri')}")
    session_id = _string_or_none(session.get("session_id"))
    return extract_chat_session(
        session_query=session_id,
        file_path=str(artifact_path),
        output_format=output_format,
        raw=False,
    )


def _derived_transcript_exists(chatlas_root: Path, session: dict[str, Any], *, output_format: str) -> bool:
    return _derived_transcript_path(chatlas_root, session, output_format=output_format).is_file()


def _derived_transcript_path(chatlas_root: Path, session: dict[str, Any], *, output_format: str) -> Path:
    suffix = ".md" if output_format == "markdown" else ".jsonl"
    provider = _session_fs_component(_string_or_none(session.get("provider")) or "unknown")
    fingerprint = _session_fs_component(_string_or_none(session.get("provider_instance_fingerprint")) or "unknown")
    session_id = _session_fs_component(_string_or_none(session.get("session_id")) or "unknown")
    return chatlas_root / _DERIVED_TRANSCRIPTS_RELATIVE_ROOT / provider / fingerprint / f"{session_id}{suffix}"


def _session_fs_component(value: str) -> str:
    return quote(value, safe="._-")


def _load_normalized_sessions(chatlas_root: Path) -> list[dict[str, Any]]:
    return _load_jsonl_dict_rows(chatlas_root / _NORMALIZED_SESSIONS_RELATIVE_PATH)


def _load_derived_summaries_for_level(chatlas_root: Path, *, level: str) -> list[dict[str, Any]]:
    return _load_jsonl_dict_rows(chatlas_root / _summary_relative_path(level))


def _load_jsonl_dict_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _iter_chatlas_session_contexts(
    *,
    chatlas_root: Path,
    start_path: Path | str = ".",
    providers: tuple[str, ...] | None = None,
):
    settings = configured_chatlas_settings(start_path=start_path)
    raw_root = chatlas_root / "raw"
    requested_providers = None if providers is None else set(providers)
    for provider_instance in settings.provider_instances:
        if requested_providers is not None and provider_instance.family not in requested_providers:
            continue
        session_provider_instance = _chatlas_session_provider_instance(
            raw_root=raw_root,
            archive_provider_instance=provider_instance,
        )
        if session_provider_instance is None:
            continue
        yield _build_provider_context(session_provider_instance)


def _selected_normalized_sessions(
    chatlas_root: Path,
    *,
    providers: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    sessions = _load_normalized_sessions(chatlas_root)
    if providers is None:
        return sessions
    requested_providers = set(providers)
    return [session for session in sessions if session.get("provider") in requested_providers]


def _session_matches_query_filters(
    session: dict[str, Any],
    *,
    extractable_only: bool,
    updated_after: float | None,
) -> bool:
    if extractable_only and not bool(session.get("extractable")):
        return False
    if updated_after is not None:
        timestamp = _chatlas_session_sort_timestamp(session)
        if timestamp is None or timestamp < updated_after:
            return False
    return True


def _chatlas_session_sort_timestamp(session: dict[str, Any]) -> float | None:
    return coerce_timestamp(session.get("updated_at")) or coerce_timestamp(session.get("created_at"))


def _sort_chatlas_session_selections(
    selections: list[ChatlasSessionSelection],
    *,
    sort: str,
) -> list[ChatlasSessionSelection]:
    if sort == "lexical":
        return sorted(
            selections,
            key=lambda selection: str(selection.session.get("session_id") or ""),
        )

    reverse = sort == "newest"
    return sorted(
        selections,
        key=lambda selection: (
            _chatlas_session_sort_timestamp(selection.session) or 0.0,
            str(selection.session.get("session_id") or ""),
        ),
        reverse=reverse,
    )


def _build_chatlas_stats_provider_payload(
    provider: str,
    sessions: list[dict[str, Any]],
) -> dict[str, Any]:
    timestamps = [
        (session, _chatlas_session_sort_timestamp(session))
        for session in sessions
        if _chatlas_session_sort_timestamp(session) is not None
    ]
    timestamps.sort(key=lambda item: ((item[1] or 0.0), str(item[0].get("session_id") or "")))
    session_examples = [_chatlas_session_summary(session, include_artifacts=False) for session in sessions[:3]]
    return {
        "provider": provider,
        "session_count": len(sessions),
        "extractable_session_count": sum(1 for session in sessions if bool(session.get("extractable"))),
        "non_extractable_session_count": sum(1 for session in sessions if not bool(session.get("extractable"))),
        "backing_artifact_count": sum(int(session.get("backing_artifact_count", 0)) for session in sessions),
        "session_id_examples": [
            session_id
            for session_id in (
                _string_or_none(session.get("session_id"))
                for session in sessions[:3]
            )
            if session_id is not None
        ],
        "session_examples": session_examples,
        "oldest_session_id": _string_or_none(timestamps[0][0].get("session_id")) if timestamps else None,
        "oldest_session_name": _string_or_none(timestamps[0][0].get("display_name")) if timestamps else None,
        "oldest_session_at": _format_stats_timestamp(timestamps[0][1]) if timestamps else None,
        "latest_session_id": _string_or_none(timestamps[-1][0].get("session_id")) if timestamps else None,
        "latest_session_name": _string_or_none(timestamps[-1][0].get("display_name")) if timestamps else None,
        "latest_session_at": _format_stats_timestamp(timestamps[-1][1]) if timestamps else None,
    }


def _summary_levels_by_uri(chatlas_root: Path) -> dict[str, dict[str, dict[str, Any]]]:
    summary_levels_by_uri: dict[str, dict[str, dict[str, Any]]] = {}
    for level in _SUMMARY_LEVELS:
        for row in _load_derived_summaries_for_level(chatlas_root, level=level):
            uri = _string_or_none(row.get("uri"))
            if uri is None:
                continue
            summary_levels_by_uri.setdefault(uri, {})[level] = row
    return summary_levels_by_uri


def _session_summary_for_uri(
    summary_levels_by_uri: dict[str, dict[str, dict[str, Any]]],
    session: dict[str, Any],
    *,
    level: str = "brief",
) -> dict[str, Any] | None:
    uri = _string_or_none(session.get("uri"))
    if uri is None:
        return None
    return summary_levels_by_uri.get(uri, {}).get(level)


def _session_summary_levels(
    summary_levels_by_uri: dict[str, dict[str, dict[str, Any]]],
    session: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    uri = _string_or_none(session.get("uri"))
    if uri is None:
        return {}
    return summary_levels_by_uri.get(uri, {})


def _derived_summary_counts(
    sessions: list[dict[str, Any]],
    *,
    summary_levels_by_uri: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, int]:
    return {
        level: sum(
            1
            for session in sessions
            if _session_summary_for_uri(summary_levels_by_uri, session, level=level) is not None
        )
        for level in _SUMMARY_LEVELS
    }


def _latest_update_manifest(chatlas_root: Path) -> dict[str, Any] | None:
    manifest_dir = chatlas_root / "manifests" / "updates"
    if not manifest_dir.is_dir():
        return None

    manifest_paths = sorted(path for path in manifest_dir.iterdir() if path.is_file() and path.suffix == ".json")
    if not manifest_paths:
        return None

    latest_path = manifest_paths[-1]
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    payload["_manifest_path"] = str(latest_path)
    return payload


def _matched_normalized_session_fields(
    session: dict[str, Any],
    *,
    query: str | None,
) -> tuple[tuple[str, str], ...]:
    if query is None:
        return ()
    matched_fields: list[tuple[str, str]] = []
    for field_name in (
        "uri",
        "provider_instance_fingerprint",
        "session_id",
    ):
        value = _string_or_none(session.get(field_name))
        if value == query:
            matched_fields.append((field_name, value))

    display_name = _string_or_none(session.get("display_name"))
    display_name_field = _string_or_none(session.get("display_name_field"))
    if display_name == query:
        matched_fields.append((display_name_field or "display_name", display_name))

    native = session.get("native")
    if isinstance(native, dict):
        for field_name, raw_value in native.items():
            value = _string_or_none(raw_value)
            if value == query:
                matched_fields.append((_query_field_name_for_native_field(str(field_name)), value))
                continue
            if not isinstance(raw_value, list):
                continue
            for item in raw_value:
                item_value = _string_or_none(item)
                if item_value == query:
                    matched_fields.append((_query_field_name_for_native_field(str(field_name)), item_value))

    seen: set[tuple[str, str]] = set()
    unique_matches: list[tuple[str, str]] = []
    for item in matched_fields:
        if item in seen:
            continue
        seen.add(item)
        unique_matches.append(item)
    return tuple(unique_matches)


def _query_field_name_for_native_field(field_name: str) -> str:
    if field_name == "session_keys":
        return "session_key"
    return field_name


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _chatlas_session_summary(
    session: dict[str, Any],
    *,
    include_artifacts: bool,
) -> dict[str, Any]:
    payload = dict(session)
    payload.pop("class", None)
    payload.pop("schema_version", None)
    if not include_artifacts:
        payload.pop("backing_artifacts", None)
    payload.pop("summary", None)
    payload.pop("summary_levels", None)
    payload.pop("match", None)
    payload.pop("transcript_filter_match", None)
    payload.pop("provider_stats", None)
    return payload


def _chatlas_provider_stats_for_session(
    chatlas_root: Path,
    session: dict[str, Any],
) -> dict[str, Any] | None:
    uri = _string_or_none(session.get("uri"))
    provider = _string_or_none(session.get("provider"))
    if uri is None:
        return None
    resolved_sessions = resolve_chatlas_sessions(
        uri,
        providers=None if provider is None else (provider,),
        chatlas_root=chatlas_root,
    )
    if len(resolved_sessions) != 1:
        return None
    return _build_provider_session_stats(resolved_sessions[0])


def _select_chatlas_sessions(
    chatlas_root: Path,
    *,
    query: str | None = None,
    text_contain: str | None = None,
    user_contain: str | None = None,
    providers: tuple[str, ...] | None = None,
    extractable_only: bool = False,
    updated_after: float | None = None,
) -> list[ChatlasSessionSelection]:
    summary_levels_by_uri = _summary_levels_by_uri(chatlas_root)
    selections: list[ChatlasSessionSelection] = []
    for session in _selected_normalized_sessions(chatlas_root, providers=providers):
        if not _session_matches_query_filters(
            session,
            extractable_only=extractable_only,
            updated_after=updated_after,
        ):
            continue
        matched_fields = _matched_normalized_session_fields(session, query=query)
        if query is not None and not matched_fields:
            continue
        transcript_filter_match = _transcript_filter_match(
            chatlas_root,
            session,
            text_contain=text_contain,
            user_contain=user_contain,
        )
        if text_contain is not None or user_contain is not None:
            if transcript_filter_match is None:
                continue
        selections.append(
            ChatlasSessionSelection(
                session=session,
                matched_fields=matched_fields,
                transcript_filter_match=transcript_filter_match or {},
                summary=_session_summary_for_uri(summary_levels_by_uri, session),
                summary_levels=_session_summary_levels(summary_levels_by_uri, session),
            )
        )
    return selections


def _transcript_filter_match(
    chatlas_root: Path,
    session: dict[str, Any],
    *,
    text_contain: str | None = None,
    user_contain: str | None = None,
) -> dict[str, str] | None:
    matched: dict[str, str] = {}
    if text_contain is not None:
        if not _session_text_contains(chatlas_root, session, text=text_contain):
            return None
        matched["text_contain"] = text_contain
    if user_contain is not None:
        if not _session_text_contains(chatlas_root, session, text=user_contain, role="user"):
            return None
        matched["user_contain"] = user_contain
    return matched


def _load_transcript_turns(chatlas_root: Path, session: dict[str, Any]) -> list[dict[str, Any]]:
    return _load_jsonl_dict_rows(
        _derived_transcript_path(chatlas_root, session, output_format="jsonl")
    )


def _session_text_contains(
    chatlas_root: Path,
    session: dict[str, Any],
    *,
    text: str,
    role: str | None = None,
) -> bool:
    needle = text.casefold()
    for turn in _load_transcript_turns(chatlas_root, session):
        turn_role = _string_or_none(turn.get("role"))
        if role is not None and turn_role != role:
            continue
        turn_text = _string_or_none(turn.get("text"))
        if turn_text is None:
            continue
        if needle in turn_text.casefold():
            return True
    return False


def _first_turn_text(turns: list[dict[str, Any]]) -> str | None:
    for turn in turns:
        text = _string_or_none(turn.get("text"))
        if text is not None:
            return text
    return None


def _last_turn_text(turns: list[dict[str, Any]]) -> str | None:
    for turn in reversed(turns):
        text = _string_or_none(turn.get("text"))
        if text is not None:
            return text
    return None


def _truncate_summary_text(text: str | None, *, limit: int = 120) -> str | None:
    if text is None:
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _turn_text_previews(turns: list[dict[str, Any]], *, limit: int) -> list[str]:
    previews: list[str] = []
    for turn in turns:
        text = _truncate_summary_text(_string_or_none(turn.get("text")), limit=160)
        if text is None:
            continue
        previews.append(text)
        if len(previews) >= limit:
            break
    return previews


def _turn_previews(turns: list[dict[str, Any]], *, limit: int) -> list[dict[str, str]]:
    previews: list[dict[str, str]] = []
    for turn in turns:
        role = _string_or_none(turn.get("role"))
        text_preview = _truncate_summary_text(_string_or_none(turn.get("text")), limit=160)
        if role is None or text_preview is None:
            continue
        previews.append(
            {
                "role": role,
                "text_preview": text_preview,
            }
        )
        if len(previews) >= limit:
            break
    return previews


def _summary_relative_path(level: str) -> Path:
    path = _SUMMARY_RELATIVE_PATHS.get(level)
    if path is None:
        raise CliError(f"unsupported summary level: {level}")
    return path


def _render_summary(summary: dict[str, Any], *, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(summary, indent=2)
    if output_format != "markdown":
        raise CliError(f"unsupported summary output format: {output_format}")

    lines = [
        f"# Chatlas Summary ({summary.get('level', 'brief')})",
        "",
        f"- URI: {summary.get('uri')}",
        f"- Provider: {summary.get('provider')}",
        f"- Session ID: {summary.get('session_id')}",
        f"- Display Name: {summary.get('display_name')}",
        f"- Turns: {summary.get('turn_count', 0)}",
        f"- User Turns: {summary.get('user_turn_count', 0)}",
        f"- Assistant Turns: {summary.get('assistant_turn_count', 0)}",
    ]
    text_preview = _string_or_none(summary.get("text_preview"))
    if text_preview is not None:
        lines.extend(["", "## Preview", "", text_preview])
    first_user_text = _string_or_none(summary.get("first_user_text"))
    if first_user_text is not None:
        lines.extend(["", "## First User", "", first_user_text])
    last_assistant_text = _string_or_none(summary.get("last_assistant_text"))
    if last_assistant_text is not None:
        lines.extend(["", "## Last Assistant", "", last_assistant_text])
    turn_previews = summary.get("turn_previews")
    if isinstance(turn_previews, list) and turn_previews:
        lines.extend(["", "## Outline", ""])
        for preview in turn_previews:
            if not isinstance(preview, dict):
                continue
            role = _string_or_none(preview.get("role")) or "unknown"
            preview_text = _string_or_none(preview.get("text_preview"))
            if preview_text is None:
                continue
            lines.append(f"- {role}: {preview_text}")
    return "\n".join(lines)


def _write_text_if_changed(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")


def _prune_stale_files(*, root: Path, expected_paths: set[Path]) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path in expected_paths:
            continue
        path.unlink()


def _prune_empty_dirs(root: Path, *, stop: Path) -> None:
    if not root.exists():
        return
    for path in sorted((candidate for candidate in root.rglob("*") if candidate.is_dir()), key=lambda candidate: len(candidate.parts), reverse=True):
        if path == stop:
            continue
        if any(path.iterdir()):
            continue
        path.rmdir()


__all__ = [
    "chatlas_export",
    "chatlas_query",
    "chatlas_resolved_session_stats",
    "chatlas_stats",
    "chatlas_update",
    "configured_chatlas_settings",
    "default_chatlas_root",
    "format_chatlas_stats_markdown",
    "resolve_chatlas_sessions",
]
