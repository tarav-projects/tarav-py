from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.git_ops import run_git
from agentos._core.project import agentos_home_dir
from agentos.chat.archive import (
    _archive_home_destination,
    _archive_single_instance,
    _build_archive_provider_context,
    _dedupe_archive_instances,
    _provider_instances_from_config_entries,
    _validate_unique_archive_destinations,
    supported_archive_provider_families,
)
from agentos.chat.providers import (
    ProviderInstance,
    ProviderInstanceConfigSource,
    load_chat_config_documents,
    provider_instance_config_entries_from_config,
)
from agentos.chat.core import (
    _build_common_session_stats,
    _build_provider_context,
    _dedupe_sessions,
    _discover_direct_provider_sessions,
    _provider_family_for_name,
)
from agentos.chat.extractors import extract_chat_session

CHATLAS_DIRNAME = "chatlas"
DEFAULT_CHATLAS_COMMIT_PREFIX = "chatlas update"
_NORMALIZED_SESSIONS_RELATIVE_PATH = Path("normalized") / "sessions.jsonl"
_DERIVED_TRANSCRIPTS_RELATIVE_ROOT = Path("derived") / "transcripts"
_DERIVED_SUMMARIES_RELATIVE_PATH = Path("derived") / "summaries" / "sessions.jsonl"
_CHATLAS_PROVIDER_INSTANCE_CONFIG_SOURCE = ProviderInstanceConfigSource(
    object_path=("chatlas", "provider_instances"),
    field_prefix="chatlas.provider_instances",
)


@dataclass(frozen=True)
class ChatlasSettings:
    commit_prefix: str
    provider_instances: tuple[ProviderInstance, ...]


def default_chatlas_root() -> Path:
    return agentos_home_dir() / CHATLAS_DIRNAME


def configured_chatlas_settings(*, start_path: Path | str = ".") -> ChatlasSettings:
    commit_prefix = DEFAULT_CHATLAS_COMMIT_PREFIX
    provider_instances = [family.default_instance() for family in supported_archive_provider_families()]

    for config in load_chat_config_documents(start_path=start_path):
        chatlas_config = _chatlas_config_from_config(config)
        if chatlas_config is None:
            continue

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

    deduped_instances = _dedupe_archive_instances(tuple(provider_instances))
    _validate_unique_archive_destinations(deduped_instances)
    return ChatlasSettings(
        commit_prefix=commit_prefix,
        provider_instances=deduped_instances,
    )


def chatlas_update(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
) -> dict[str, object]:
    settings = configured_chatlas_settings(start_path=start_path)
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
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
    selected_contexts = tuple(_build_archive_provider_context(instance) for instance in selected_instances)

    instance_payloads: list[dict[str, object]] = []
    synced_instance_count = 0
    skipped_instance_count = 0

    for context in selected_contexts:
        instance_payload = _archive_single_instance(
            context=context,
            archive_root=raw_root,
        )
        instance_payloads.append(instance_payload)
        if bool(instance_payload["synced"]):
            synced_instance_count += 1
        else:
            skipped_instance_count += 1

    _ensure_git_repo(chatlas_root_path)
    normalized_sessions = _materialize_normalized_sessions(
        chatlas_root=chatlas_root_path,
        provider_instances=selected_instances,
    )
    derived_transcript_session_count = _materialize_derived_transcripts(
        chatlas_root=chatlas_root_path,
        normalized_sessions=normalized_sessions,
    )
    derived_summary_count = _materialize_derived_summaries(
        chatlas_root=chatlas_root_path,
        normalized_sessions=normalized_sessions,
    )
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
                derived_summary_count=derived_summary_count,
                instance_payloads=instance_payloads,
            ),
        )
        run_git(chatlas_root_path, "add", "-A")

    committed = False
    commit_message: str | None = None
    if dataset_changes_detected and run_git(chatlas_root_path, "status", "--porcelain").strip():
        commit_message = f"{settings.commit_prefix}: {recorded_at}"
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
        "derived_summaries_path": str(chatlas_root_path / _DERIVED_SUMMARIES_RELATIVE_PATH),
        "derived_summary_count": derived_summary_count,
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


def chatlas_stats(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    sessions = _load_normalized_sessions(chatlas_root_path)
    if providers is not None:
        sessions = [session for session in sessions if session.get("provider") in set(providers)]

    sessions_by_provider: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        provider = _string_or_none(session.get("provider")) or "unknown"
        sessions_by_provider.setdefault(provider, []).append(session)

    by_provider = [
        {
            "provider": provider,
            "session_count": len(provider_sessions),
            "extractable_session_count": sum(1 for session in provider_sessions if bool(session.get("extractable"))),
            "non_extractable_session_count": sum(
                1 for session in provider_sessions if not bool(session.get("extractable"))
            ),
            "backing_artifact_count": sum(
                int(session.get("backing_artifact_count", 0))
                for session in provider_sessions
            ),
        }
        for provider, provider_sessions in sorted(sessions_by_provider.items())
    ]
    latest_manifest = _latest_update_manifest(chatlas_root_path)
    summaries = _summaries_by_uri(chatlas_root_path)

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
            "derived_summary_count": sum(
                1
                for session in sessions
                if _string_or_none(session.get("uri")) in summaries
            ),
            "by_provider": by_provider,
            "last_update_recorded_at": None if latest_manifest is None else latest_manifest.get("recorded_at"),
            "last_update_manifest_path": None if latest_manifest is None else latest_manifest.get("_manifest_path"),
        },
    }


def chatlas_query(
    *,
    query: str | None,
    text_contain: str | None = None,
    user_contain: str | None = None,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    normalized_query = None if query is None else query.strip()
    normalized_text_contain = None if text_contain is None else text_contain.strip()
    normalized_user_contain = None if user_contain is None else user_contain.strip()
    if normalized_query == "":
        normalized_query = None
    if normalized_text_contain == "":
        normalized_text_contain = None
    if normalized_user_contain == "":
        normalized_user_contain = None
    if normalized_query is None and normalized_text_contain is None and normalized_user_contain is None:
        raise CliError("query, --text-contain, or --user-contain is required")

    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    sessions = _load_normalized_sessions(chatlas_root_path)
    if providers is not None:
        requested_providers = set(providers)
        sessions = [session for session in sessions if session.get("provider") in requested_providers]
    summaries = _summaries_by_uri(chatlas_root_path)

    matched_sessions: list[dict[str, Any]] = []
    for session in sessions:
        matched_fields = (
            _matched_normalized_session_fields(session, query=normalized_query)
            if normalized_query is not None
            else ()
        )
        if normalized_query is not None and not matched_fields:
            continue
        if normalized_text_contain is not None and not _session_text_contains(
            chatlas_root_path,
            session,
            text=normalized_text_contain,
        ):
            continue
        if normalized_user_contain is not None and not _session_text_contains(
            chatlas_root_path,
            session,
            text=normalized_user_contain,
            role="user",
        ):
            continue
        enriched = dict(session)
        uri = _string_or_none(session.get("uri"))
        if uri is not None and uri in summaries:
            enriched["summary"] = summaries[uri]
        if normalized_query is not None:
            enriched["match"] = {
                "query": normalized_query,
                "kind": "exact_identity",
                "fields": [
                    {
                        "field": field_name,
                        "value": value,
                    }
                    for field_name, value in matched_fields
                ],
            }
        transcript_filters: dict[str, str] = {}
        if normalized_text_contain is not None:
            transcript_filters["text_contain"] = normalized_text_contain
        if normalized_user_contain is not None:
            transcript_filters["user_contain"] = normalized_user_contain
        if transcript_filters:
            enriched["transcript_filter_match"] = transcript_filters
        matched_sessions.append(enriched)

    matched_sessions.sort(key=lambda session: str(session.get("session_id", "")))
    expansions = ["backing_artifacts", "summary"]
    if normalized_query is not None:
        expansions.append("match")
    if normalized_text_contain is not None or normalized_user_contain is not None:
        expansions.append("transcript_filter_match")
    return {
        "status": "ok",
        "command": "chatlas query",
        "selection": {
            "kind": "query",
            "query": normalized_query,
            "text_contain": normalized_text_contain,
            "user_contain": normalized_user_contain,
            "providers": list(providers) if providers is not None else None,
        },
        "expansions": expansions,
        "session_count": len(matched_sessions),
        "sessions": matched_sessions,
    }


def chatlas_export(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    output_format: str = "markdown",
    chatlas_root: Path | None = None,
) -> str:
    if output_format not in {"jsonl", "markdown"}:
        raise CliError(f"unsupported export format: {output_format}")

    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    sessions = _load_normalized_sessions(chatlas_root_path)
    if providers is not None:
        requested_providers = set(providers)
        sessions = [session for session in sessions if session.get("provider") in requested_providers]

    matched_sessions = [
        session
        for session in sessions
        if _matched_normalized_session_fields(session, query=query.strip())
    ]
    if not matched_sessions:
        raise CliError(f"no normalized Chatlas session matched query {query}")
    if len(matched_sessions) > 1:
        choices = ", ".join(str(session.get("uri")) for session in matched_sessions[:5])
        raise CliError(f"multiple Chatlas sessions matched query {query}: {choices}")

    session = matched_sessions[0]
    transcript_path = _derived_transcript_path(chatlas_root_path, session, output_format=output_format)
    if transcript_path.is_file():
        return transcript_path.read_text(encoding="utf-8")

    rendered = _render_transcript(session, output_format=output_format)
    _write_text_if_changed(transcript_path, rendered)
    return rendered


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
    derived_summary_count: int,
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
        "derived_summary_count": derived_summary_count,
        "instances": instance_payloads,
    }


def _write_update_manifest(*, chatlas_root: Path, payload: dict[str, object]) -> Path:
    manifest_dir = chatlas_root / "manifests" / "updates"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    recorded_at = str(payload["recorded_at"])
    manifest_path = manifest_dir / f"{_compact_timestamp(recorded_at)}.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _compact_timestamp(value: str) -> str:
    return (
        value.replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace("T", "T")
        .replace("Z", "Z")
    )


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        items.append(value)
    return tuple(items)


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
        transcript_session_count += 1
        for output_format in ("jsonl", "markdown"):
            transcript_path = _derived_transcript_path(chatlas_root, session, output_format=output_format)
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            _write_text_if_changed(
                transcript_path,
                _render_transcript(session, output_format=output_format),
            )
            expected_paths.add(transcript_path)

    _prune_stale_files(root=transcript_root, expected_paths=expected_paths)
    _prune_empty_dirs(transcript_root, stop=transcript_root)
    return transcript_session_count


def _materialize_derived_summaries(
    *,
    chatlas_root: Path,
    normalized_sessions: list[dict[str, Any]],
) -> int:
    summaries = [
        _build_session_summary(chatlas_root, session)
        for session in normalized_sessions
    ]
    summaries_path = chatlas_root / _DERIVED_SUMMARIES_RELATIVE_PATH
    rendered = "".join(json.dumps(summary, sort_keys=True) + "\n" for summary in summaries)
    _write_text_if_changed(summaries_path, rendered)
    return len(summaries)


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

    for _, source_home_path in archive_provider_instance.homes:
        raw_home_path = _archive_home_destination(
            archive_root=raw_root,
            home_path=source_home_path,
        )
        home_slot = _match_session_home_slot(provider_handler.family, source_home_path)
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


def _match_session_home_slot(provider_family: str, source_home_path: Path):
    provider_handler = _provider_family_for_name(provider_family)
    if provider_handler is None:
        return None

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


def _build_session_summary(chatlas_root: Path, session: dict[str, Any]) -> dict[str, Any]:
    turns = _load_transcript_turns(chatlas_root, session)
    user_turns = [turn for turn in turns if _string_or_none(turn.get("role")) == "user"]
    assistant_turns = [turn for turn in turns if _string_or_none(turn.get("role")) == "assistant"]
    first_user_text = _first_turn_text(user_turns)
    last_assistant_text = _last_turn_text(assistant_turns)
    preview_source = first_user_text or last_assistant_text or _first_turn_text(turns)
    return {
        "class": "agentos.chatlas.session_summary",
        "schema_version": 1,
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
    path = chatlas_root / _NORMALIZED_SESSIONS_RELATIVE_PATH
    if not path.is_file():
        return []

    sessions: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            sessions.append(payload)
    return sessions


def _load_derived_summaries(chatlas_root: Path) -> list[dict[str, Any]]:
    path = chatlas_root / _DERIVED_SUMMARIES_RELATIVE_PATH
    if not path.is_file():
        return []

    summaries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            summaries.append(payload)
    return summaries


def _summaries_by_uri(chatlas_root: Path) -> dict[str, dict[str, Any]]:
    rows = _load_derived_summaries(chatlas_root)
    return {
        uri: row
        for row in rows
        if (uri := _string_or_none(row.get("uri"))) is not None
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
                matched_fields.append((str(field_name), value))

    seen: set[tuple[str, str]] = set()
    unique_matches: list[tuple[str, str]] = []
    for item in matched_fields:
        if item in seen:
            continue
        seen.add(item)
        unique_matches.append(item)
    return tuple(unique_matches)


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _load_transcript_turns(chatlas_root: Path, session: dict[str, Any]) -> list[dict[str, Any]]:
    transcript_path = _derived_transcript_path(chatlas_root, session, output_format="jsonl")
    if not transcript_path.is_file():
        return []

    turns: list[dict[str, Any]] = []
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            turns.append(payload)
    return turns


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
    "chatlas_stats",
    "chatlas_update",
    "configured_chatlas_settings",
    "default_chatlas_root",
]
