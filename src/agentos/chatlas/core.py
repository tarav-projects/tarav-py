from __future__ import annotations

import base64
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import json
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar
from urllib.parse import quote

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.sequences import _unique_strings
from agentos._core.git_ops import git_has_staged_changes, run_git
from agentos.agent.primitives import AgentConfig, SessionSource
from agentos.agent.providers import Agent, agent_from_config, load_configured_agents
from agentos.agent.sessions import (
    _format_stats_timestamp,
    _provider_family_for_name,
)
from agentos.agent.config import (
    load_chat_config_documents,
    load_unique_string_list,
)
from agentos.agent.session_refs import (
    BackingArtifact,
    ProviderSessionRef,
    backing_artifacts_from_sources,
)
from agentos.agent.session_utils import coerce_timestamp
from agentos.chatlas._cache_io import (
    load_chatlas_cache_section,
    write_chatlas_cache_section,
    write_text_if_changed,
)
from agentos.chatlas.session_model._hashes import _session_identity_hash
from agentos.chatlas.raw import (
    ChatlasArchiveConfig,
    ChatlasProviderMirrorResult,
    _build_chatlas_provider_context,
    _chatlas_archive_config_from_agent,
    _chatlas_home_destination,
    _dedupe_chatlas_archive_configs,
    _load_chatlas_raw_scan_cache,
    _mirror_chatlas_provider_context,
    _validate_unique_chatlas_destinations,
    _write_chatlas_raw_scan_cache,
    supported_chatlas_provider_families,
)
from agentos.codex.session import CodexSession
from agentos.openclaw.session import OpenclawSession

CHATLAS_DIRNAME = "chatlas"
DEFAULT_CHATLAS_COMMIT_PREFIX = "chatlas update"
_SESSION_INDEX_ROOT_RELATIVE_PATH = Path("index") / "sessions"
_SESSION_INDEX_CACHE_RELATIVE_PATH = Path("cache") / "session-index-v1.json"
_SESSION_INDEX_DERIVATION_VERSION = 2
_PROGRESS_PREFIX = "[chatlas]"
_MAX_CHATLAS_ARCHIVE_WORKERS = 4
_CHATLAS_DOCUMENTS_DIRNAME = "Documents"
T = TypeVar("T")


@dataclass(frozen=True)
class ChatlasSettings:
    commit_prefix: str
    provider_configs: tuple[ChatlasArchiveConfig, ...]


@dataclass(frozen=True)
class ChatlasSessionSelection:
    session: dict[str, Any]
    matched_fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ChatlasArchiveResult:
    index: int
    payload: dict[str, object]
    scan_cache_updates: dict[str, dict[str, dict[str, int]]]


@dataclass(frozen=True)
class ChatlasSessionIndexMaterialization:
    sessions: list[dict[str, Any]]
    source_signatures: dict[str, dict[str, object]]
    session_index_cache: dict[str, dict[str, object]]


@dataclass(frozen=True)
class ChatlasProviderSessionRef:
    archive_config: ChatlasArchiveConfig
    agent: Agent
    session_ref: ProviderSessionRef

    def sources(self) -> tuple[SessionSource, ...]:
        return self.session_ref.to_session().sources()

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        return backing_artifacts_from_sources(self.sources())


@dataclass
class ChatlasUpdateCaches:
    raw_scan: dict[str, dict[str, dict[str, int]]]
    session_index: dict[str, dict[str, object]]


def default_chatlas_root() -> Path:
    return Path.home().expanduser().resolve() / _CHATLAS_DOCUMENTS_DIRNAME / CHATLAS_DIRNAME


def configured_chatlas_settings(*, start_path: Path | str = ".") -> ChatlasSettings:
    commit_prefix = DEFAULT_CHATLAS_COMMIT_PREFIX
    supported_families = {
        provider_family.family for provider_family in supported_chatlas_provider_families()
    }
    all_agents = load_configured_agents(start_path=start_path)
    selected_instance_ids = load_chatlas_instance_ids(start_path=start_path)
    selected_agents = _select_configured_agents(
        all_agents,
        selected_instance_ids=selected_instance_ids,
        supported_families=supported_families,
        selector_field_name="chatlas.instance_ids",
        unsupported_instance_label="Chatlas",
        default_to_supported_families=False,
    )

    for config in load_chat_config_documents(start_path=start_path):
        chatlas_config = _chatlas_config_from_config(config)
        if chatlas_config is not None:
            raw_commit_prefix = chatlas_config.get("commit_prefix")
            if raw_commit_prefix is not None:
                if not isinstance(raw_commit_prefix, str) or not raw_commit_prefix.strip():
                    raise CliError("config field chatlas.commit_prefix must be a non-empty string")
                commit_prefix = raw_commit_prefix.strip()

    provider_configs = tuple(
        _chatlas_archive_config_from_agent(agent)
        for agent in selected_agents
    )
    deduped_configs = _dedupe_chatlas_archive_configs(provider_configs)
    _validate_unique_chatlas_destinations(deduped_configs)
    return ChatlasSettings(
        commit_prefix=commit_prefix,
        provider_configs=deduped_configs,
    )


def load_chatlas_instance_ids(
    *,
    start_path: Path | str = ".",
) -> tuple[str, ...] | None:
    result: tuple[str, ...] | None = None
    for config in load_chat_config_documents(start_path=start_path):
        chatlas_config = _chatlas_config_from_config(config)
        if chatlas_config is None or "instance_ids" not in chatlas_config:
            continue
        result = load_unique_string_list(
            chatlas_config["instance_ids"],
            container_field_name="config field chatlas.instance_ids",
            item_field_name="chatlas.instance_ids",
        )
    return result


def _select_configured_agents(
    agents: tuple[Agent, ...],
    *,
    selected_instance_ids: tuple[str, ...] | None,
    supported_families: set[str],
    selector_field_name: str,
    unsupported_instance_label: str,
    default_to_supported_families: bool,
) -> tuple[Agent, ...]:
    supported_agents = tuple(agent for agent in agents if agent.provider in supported_families)
    if selected_instance_ids is None:
        if default_to_supported_families:
            return supported_agents
        return ()

    agents_by_id = {
        agent.instance_id: agent
        for agent in agents
        if agent.instance_id is not None
    }
    selected_agents: list[Agent] = []
    for instance_id in selected_instance_ids:
        agent = agents_by_id.get(instance_id)
        if agent is None:
            raise CliError(
                f"{selector_field_name} references unknown agent instance id: {instance_id}"
            )
        if agent.provider not in supported_families:
            raise CliError(
                f"{unsupported_instance_label} does not support provider "
                f"{agent.provider} for agent instance id: {instance_id}"
            )
        selected_agents.append(agent)
    return tuple(selected_agents)


def chatlas_update(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
    scan_cache_enabled: bool = True,
    session_index_cache_enabled: bool = True,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    settings = configured_chatlas_settings(start_path=start_path)
    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    raw_root = chatlas_root_path / "raw"
    index_root = chatlas_root_path / "index"
    selected_configs = settings.provider_configs
    if providers is not None:
        selected_configs = tuple(
            config
            for config in selected_configs
            if config.family in providers
        )
    if not selected_configs:
        session_index = _selected_session_index(chatlas_root_path, providers=providers)
        return {
            "status": "ok",
            "command": "chatlas update",
            "chatlas_root": str(chatlas_root_path),
            "raw_root": str(raw_root),
            "index_root": str(index_root),
            "session_index_root": str(_session_index_dir(chatlas_root_path)),
            "session_index_count": len(session_index),
            "manifest_path": None,
            "scan_cache_enabled": scan_cache_enabled,
            "session_index_cache_enabled": session_index_cache_enabled,
            "commit_prefix": settings.commit_prefix,
            "provider_count": 0,
            "instance_count": 0,
            "synced_instance_count": 0,
            "skipped_instance_count": 0,
            "changes_detected": False,
            "committed": False,
            "commit_message": None,
            "instances": [],
        }
    selected_contexts = tuple(
        _build_chatlas_provider_context(config)
        for config in selected_configs
    )
    _ensure_git_repo(chatlas_root_path)
    if scan_cache_enabled or session_index_cache_enabled:
        _ensure_chatlas_cache_gitignore(chatlas_root_path)
    update_caches = _load_chatlas_update_caches(
        chatlas_root=chatlas_root_path,
        scan_cache_enabled=scan_cache_enabled,
        session_index_cache_enabled=session_index_cache_enabled,
    )
    _emit_chatlas_progress(
        progress,
        f"update start: {len(selected_contexts)} instance(s) -> {chatlas_root_path}",
    )

    archive_started_at = time.perf_counter()
    archive_results = _archive_chatlas_provider_contexts(
        selected_contexts=selected_contexts,
        raw_root=raw_root,
        progress=progress,
        scan_cache_enabled=scan_cache_enabled,
        raw_scan_cache=update_caches.raw_scan,
    )
    instance_payloads = [result.payload for result in archive_results]
    synced_instance_count = sum(1 for payload in instance_payloads if bool(payload["synced"]))
    skipped_instance_count = len(instance_payloads) - synced_instance_count
    if scan_cache_enabled:
        update_caches.raw_scan = _merge_chatlas_raw_scan_cache(update_caches.raw_scan, archive_results)
    _emit_chatlas_archive_summary(
        progress=progress,
        instance_payloads=instance_payloads,
        elapsed_seconds=time.perf_counter() - archive_started_at,
    )

    session_index_materialization = _run_chatlas_timed_phase(
        progress=progress,
        start_message="materializing session index",
        finish_message=lambda materialization: (
            f"session index: {len(materialization.sessions)}"
        ),
        run=lambda: _materialize_session_index(
            chatlas_root=chatlas_root_path,
            provider_configs=settings.provider_configs,
            session_index_cache=update_caches.session_index,
            session_index_cache_enabled=session_index_cache_enabled,
        ),
    )
    session_index = session_index_materialization.sessions
    git_started_at = time.perf_counter()
    _emit_chatlas_progress(progress, "staging dataset changes")
    run_git(chatlas_root_path, "add", "-A")
    dataset_changes_detected = git_has_staged_changes(chatlas_root_path)

    recorded_at = utc_now_iso()
    manifest_path: Path | None = None
    if dataset_changes_detected:
        manifest_path = _write_update_manifest(
            chatlas_root=chatlas_root_path,
            payload=_build_update_manifest(
                recorded_at=recorded_at,
                chatlas_root=chatlas_root_path,
                raw_root=raw_root,
                index_root=index_root,
                settings=settings,
                selected_contexts=selected_contexts,
                synced_instance_count=synced_instance_count,
                skipped_instance_count=skipped_instance_count,
                session_index_count=len(session_index),
                instance_payloads=instance_payloads,
            ),
        )
        run_git(chatlas_root_path, "add", str(manifest_path.relative_to(chatlas_root_path)))
        _emit_chatlas_progress(progress, "staged dataset changes")

    committed = False
    commit_message: str | None = None
    if dataset_changes_detected:
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
    git_status = "committed" if committed else "no commit needed"
    _emit_chatlas_progress(
        progress,
        f"git finalization: {git_status} (elapsed={_format_wall_clock_elapsed(time.perf_counter() - git_started_at)})",
    )

    update_caches.session_index = session_index_materialization.session_index_cache
    _write_chatlas_update_caches(
        chatlas_root=chatlas_root_path,
        caches=update_caches,
        scan_cache_enabled=scan_cache_enabled,
        session_index_cache_enabled=session_index_cache_enabled,
    )

    provider_names = _unique_strings(tuple(context.family for context in selected_contexts))
    return {
        "status": "ok",
        "command": "chatlas update",
        "chatlas_root": str(chatlas_root_path),
        "raw_root": str(raw_root),
        "index_root": str(index_root),
        "session_index_root": str(_session_index_dir(chatlas_root_path)),
        "session_index_count": len(session_index),
        "manifest_path": None if manifest_path is None else str(manifest_path),
        "scan_cache_enabled": scan_cache_enabled,
        "session_index_cache_enabled": session_index_cache_enabled,
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
    provider = context.family
    return f"{provider}/{instance}"


def _format_wall_clock_elapsed(elapsed_seconds: float) -> str:
    return f"{elapsed_seconds:.2f}s"


def _run_chatlas_timed_phase(
    *,
    progress: Callable[[str], None] | None,
    start_message: str,
    finish_message: Callable[[T], str],
    run: Callable[[], T],
) -> T:
    _emit_chatlas_progress(progress, start_message)
    started_at = time.perf_counter()
    result = run()
    _emit_chatlas_progress(
        progress,
        f"{finish_message(result)} (elapsed={_format_wall_clock_elapsed(time.perf_counter() - started_at)})",
    )
    return result


def _load_chatlas_update_caches(
    *,
    chatlas_root: Path,
    scan_cache_enabled: bool,
    session_index_cache_enabled: bool,
) -> ChatlasUpdateCaches:
    return ChatlasUpdateCaches(
        raw_scan=_load_chatlas_raw_scan_cache(chatlas_root) if scan_cache_enabled else {},
        session_index=(
            _load_session_index_cache(chatlas_root) if session_index_cache_enabled else {}
        ),
    )


def _write_chatlas_update_caches(
    *,
    chatlas_root: Path,
    caches: ChatlasUpdateCaches,
    scan_cache_enabled: bool,
    session_index_cache_enabled: bool,
) -> None:
    if scan_cache_enabled:
        _write_chatlas_raw_scan_cache(chatlas_root, caches.raw_scan)
    if session_index_cache_enabled:
        _write_session_index_cache(chatlas_root, caches.session_index)


def _emit_chatlas_archive_done(
    progress: Callable[[str], None] | None,
    *,
    context_label: str,
    mirror_result: ChatlasProviderMirrorResult,
) -> None:
    _emit_chatlas_progress(
        progress,
        f"{context_label}: archive done "
        f"(synced={bool(mirror_result.payload['synced'])}, "
        f"elapsed={_format_wall_clock_elapsed(mirror_result.elapsed_seconds)})",
    )


def _archive_chatlas_provider_contexts(
    *,
    selected_contexts: tuple[object, ...],
    raw_root: Path,
    progress: Callable[[str], None] | None,
    scan_cache_enabled: bool,
    raw_scan_cache: dict[str, dict[str, dict[str, int]]],
) -> tuple[ChatlasArchiveResult, ...]:
    if not selected_contexts:
        return ()

    if len(selected_contexts) == 1:
        context = selected_contexts[0]
        context_label = _chatlas_progress_context_label(context)
        _emit_chatlas_progress(progress, f"{context_label}: archive start")
        mirror_result = _mirror_chatlas_provider_context(
            context=context,
            raw_root=raw_root,
            progress=progress,
            scan_cache=raw_scan_cache,
            scan_cache_enabled=scan_cache_enabled,
        )
        _emit_chatlas_archive_done(progress, context_label=context_label, mirror_result=mirror_result)
        return (
            ChatlasArchiveResult(
                index=0,
                payload=mirror_result.payload,
                scan_cache_updates=mirror_result.scan_cache_updates,
            ),
        )

    max_workers = min(_MAX_CHATLAS_ARCHIVE_WORKERS, len(selected_contexts))
    results: list[ChatlasArchiveResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_lookup: dict[Future[ChatlasProviderMirrorResult], tuple[int, str]] = {}
        for index, context in enumerate(selected_contexts):
            context_label = _chatlas_progress_context_label(context)
            _emit_chatlas_progress(progress, f"{context_label}: archive start")
            future = executor.submit(
                _mirror_chatlas_provider_context,
                context=context,
                raw_root=raw_root,
                progress=progress,
                scan_cache=raw_scan_cache,
                scan_cache_enabled=scan_cache_enabled,
            )
            future_lookup[future] = (index, context_label)

        for future in as_completed(future_lookup):
            index, context_label = future_lookup[future]
            mirror_result = future.result()
            _emit_chatlas_archive_done(progress, context_label=context_label, mirror_result=mirror_result)
            results.append(
                ChatlasArchiveResult(
                    index=index,
                    payload=mirror_result.payload,
                    scan_cache_updates=mirror_result.scan_cache_updates,
                )
            )

    return tuple(sorted(results, key=lambda result: result.index))


def _merge_chatlas_raw_scan_cache(
    current_cache: dict[str, dict[str, dict[str, int]]],
    archive_results: tuple[ChatlasArchiveResult, ...],
) -> dict[str, dict[str, dict[str, int]]]:
    merged_cache = {
        home_key: {
            rel_path: dict(metadata)
            for rel_path, metadata in home_entries.items()
        }
        for home_key, home_entries in current_cache.items()
    }
    for archive_result in archive_results:
        for home_key, home_entries in archive_result.scan_cache_updates.items():
            merged_cache[home_key] = {
                rel_path: dict(metadata)
                for rel_path, metadata in home_entries.items()
            }
    return merged_cache


def _emit_chatlas_archive_summary(
    *,
    progress: Callable[[str], None] | None,
    instance_payloads: list[dict[str, object]],
    elapsed_seconds: float,
) -> None:
    provider_stats: dict[str, dict[str, int]] = {}
    for instance_payload in instance_payloads:
        provider_name = str(instance_payload.get("provider", "unknown"))
        stats = provider_stats.setdefault(provider_name, _new_chatlas_archive_stats())
        _accumulate_chatlas_archive_payload_stats(stats=stats, instance_payload=instance_payload)

    for provider_name, stats in provider_stats.items():
        _emit_chatlas_progress(
            progress,
            f"archive provider {provider_name}: {_format_chatlas_archive_stats(stats)}",
        )

    total_stats = _new_chatlas_archive_stats()
    total_stats["providers"] = len(provider_stats)
    for instance_payload in instance_payloads:
        _accumulate_chatlas_archive_payload_stats(stats=total_stats, instance_payload=instance_payload)
    _emit_chatlas_progress(
        progress,
        "archive totals: "
        f"{_format_chatlas_archive_stats(total_stats, include_providers=True)} "
        f"elapsed={_format_wall_clock_elapsed(elapsed_seconds)}",
    )


def _new_chatlas_archive_stats() -> dict[str, int]:
    return {
        "providers": 0,
        "instances": 0,
        "synced_instances": 0,
        "skipped_instances": 0,
        "homes": 0,
        "missing_homes": 0,
        "scanned": 0,
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
    }


def _accumulate_chatlas_archive_payload_stats(
    *,
    stats: dict[str, int],
    instance_payload: dict[str, object],
) -> None:
    stats["instances"] += 1
    if bool(instance_payload.get("synced")):
        stats["synced_instances"] += 1
    else:
        stats["skipped_instances"] += 1

    homes_status = instance_payload.get("homes_status")
    if not isinstance(homes_status, list):
        return
    stats["homes"] += len(homes_status)
    stats["missing_homes"] += sum(
        1
        for home_status in homes_status
        if isinstance(home_status, dict) and not bool(home_status.get("exists"))
    )
    for home_status in homes_status:
        if not isinstance(home_status, dict):
            continue
        added = _chatlas_archive_stat_count(home_status, "added_file_count")
        updated = _chatlas_archive_stat_count(home_status, "updated_file_count")
        unchanged = _chatlas_archive_stat_count(home_status, "unchanged_file_count")
        skipped = _chatlas_archive_stat_count(home_status, "skipped_file_count")
        stats["added"] += added
        stats["updated"] += updated
        stats["unchanged"] += unchanged
        stats["skipped"] += skipped
        stats["scanned"] += added + updated + unchanged + skipped


def _chatlas_archive_stat_count(home_status: dict[str, object], key: str) -> int:
    value = home_status.get(key)
    return value if isinstance(value, int) else 0


def _format_chatlas_archive_stats(
    stats: dict[str, int],
    *,
    include_providers: bool = False,
) -> str:
    parts: list[str] = []
    if include_providers:
        parts.append(f"providers={stats['providers']}")
    parts.extend(
        (
            f"instances={stats['instances']}",
            f"synced_instances={stats['synced_instances']}",
            f"skipped_instances={stats['skipped_instances']}",
            f"homes={stats['homes']}",
            f"missing_homes={stats['missing_homes']}",
            f"scanned={stats['scanned']}",
            f"added={stats['added']}",
            f"updated={stats['updated']}",
            f"unchanged={stats['unchanged']}",
            f"skipped={stats['skipped']}",
        )
    )
    return " ".join(parts)


def chatlas_stats(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    full_output: bool = False,
) -> dict[str, object]:
    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    sessions = _selected_session_index(chatlas_root_path, providers=providers)

    sessions_by_provider: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        provider = _string_or_none(session.get("provider")) or "unknown"
        sessions_by_provider.setdefault(provider, []).append(session)

    requested_providers = (
        tuple(providers)
        if providers is not None
        else tuple(provider_family.family for provider_family in supported_chatlas_provider_families())
    )
    by_provider = [
        _build_chatlas_stats_provider_payload(provider, sessions_by_provider.get(provider, []))
        for provider in requested_providers
        if full_output or sessions_by_provider.get(provider)
    ]
    latest_manifest = _latest_update_manifest(chatlas_root_path)

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
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    extractable_only: bool = False,
    updated_after: float | None = None,
    include_match: bool = False,
    include_artifacts: bool = False,
    include_provider_stats: bool = False,
    compact: bool = False,
) -> dict[str, object]:
    _validate_chatlas_sort(sort)
    _validate_chatlas_limit(limit)
    normalized_query = None if query is None else query.strip()
    normalized_instances = _normalize_chatlas_instance_filters(instances)
    if normalized_query == "":
        normalized_query = None

    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    selections = _select_chatlas_sessions(
        chatlas_root_path,
        query=normalized_query,
        providers=providers,
        instances=normalized_instances,
        extractable_only=extractable_only,
        updated_after=updated_after,
    )
    selections = _sort_chatlas_session_selections(selections, sort=sort)
    if limit is not None:
        selections = selections[:limit]

    matched_sessions: list[dict[str, Any]] = []
    for selection in selections:
        if compact:
            enriched = _compact_chatlas_session_payload(selection.session)
        else:
            enriched = dict(selection.session)
            if not include_artifacts:
                enriched.pop("backing_artifacts", None)
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
        if include_provider_stats:
            enriched["provider_stats"] = _chatlas_provider_stats_for_session(
                chatlas_root_path,
                selection.session,
            )
        matched_sessions.append(enriched)

    expansions: list[str] = []
    if include_artifacts:
        expansions.append("backing_artifacts")
    if include_match and normalized_query is not None:
        expansions.append("match")
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
                "instances": list(normalized_instances) if normalized_instances is not None else None,
                "compact": compact,
            },
        },
        "expansions": expansions,
        "session_count": len(matched_sessions),
        "sessions": matched_sessions,
    }


def chatlas_raw_paths(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    session = _select_one_chatlas_session(
        chatlas_root_path,
        query=query,
        providers=providers,
    )
    sources = _chatlas_raw_source_payloads(session)
    return {
        "status": "ok",
        "command": "chatlas raw path",
        "selection": _chatlas_single_session_selection_payload(
            query=query,
            providers=providers,
        ),
        "session": _compact_chatlas_session_payload(session),
        "paths": [
            source["path"]
            for source in sources
            if isinstance(source.get("path"), str)
        ],
        "sources": sources,
    }


def chatlas_raw_export(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    session = _select_one_chatlas_session(
        chatlas_root_path,
        query=query,
        providers=providers,
    )
    return {
        "status": "ok",
        "class": "agentos.chatlas.raw_export",
        "schema_version": 1,
        "command": "chatlas raw export",
        "selection": _chatlas_single_session_selection_payload(
            query=query,
            providers=providers,
        ),
        "session": _compact_chatlas_session_payload(session),
        "sources": _chatlas_raw_source_payloads(session, include_content=True),
    }


def resolve_chatlas_sessions(
    query: str,
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
) -> list[dict[str, Any]]:
    chatlas_root_path = _resolve_chatlas_root(chatlas_root)
    selections = _select_chatlas_sessions(
        chatlas_root_path,
        query=query,
        providers=providers,
    )
    return [
        _chatlas_session_with_match(selection)
        for selection in _sort_chatlas_session_selections(selections, sort="lexical")
    ]


def chatlas_resolved_session_stats(
    query: str,
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
) -> dict[str, object]:
    _ = start_path
    sessions = resolve_chatlas_sessions(
        query,
        providers=providers,
        chatlas_root=chatlas_root,
    )
    if not sessions:
        raise CliError(f"no session matched query {query}")
    if len(sessions) > 1:
        raise CliError(
            f"multiple sessions matched query {query}: {_format_chatlas_resolved_session_choices(sessions)}"
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
        "session": session,
        "stats": _chatlas_provider_stats_from_index_session(session),
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


def _ensure_chatlas_cache_gitignore(chatlas_root: Path) -> None:
    gitignore_path = chatlas_root / ".gitignore"
    ignore_line = "/cache/"
    existing = ""
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")
        if ignore_line in existing.splitlines():
            return
    separator = "" if not existing or existing.endswith("\n") else "\n"
    gitignore_path.write_text(existing + separator + ignore_line + "\n", encoding="utf-8")


def _build_update_manifest(
    *,
    recorded_at: str,
    chatlas_root: Path,
    raw_root: Path,
    index_root: Path,
    settings: ChatlasSettings,
    selected_contexts: tuple[object, ...],
    synced_instance_count: int,
    skipped_instance_count: int,
    session_index_count: int,
    instance_payloads: list[dict[str, object]],
) -> dict[str, object]:
    provider_names = _unique_strings(
        tuple(context.family for context in selected_contexts)
    )
    return {
        "class": "agentos.chatlas.update",
        "schema_version": 1,
        "recorded_at": recorded_at,
        "command": "chatlas update",
        "chatlas_root": str(chatlas_root),
        "raw_root": str(raw_root),
        "index_root": str(index_root),
        "commit_prefix": settings.commit_prefix,
        "provider_count": len(provider_names),
        "providers": list(provider_names),
        "instance_count": len(selected_contexts),
        "synced_instance_count": synced_instance_count,
        "skipped_instance_count": skipped_instance_count,
        "session_index_count": session_index_count,
        "instances": instance_payloads,
    }


def _write_update_manifest(*, chatlas_root: Path, payload: dict[str, object]) -> Path:
    manifest_dir = chatlas_root / "manifests" / "updates"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    recorded_at = str(payload["recorded_at"])
    manifest_path = manifest_dir / f"{_compact_timestamp(recorded_at)}.json"
    write_text_if_changed(manifest_path, json.dumps(payload, indent=2) + "\n")
    return manifest_path


def _resolve_chatlas_root(chatlas_root: Path | None) -> Path:
    if chatlas_root is not None:
        return chatlas_root.expanduser().resolve()

    return default_chatlas_root().expanduser().resolve()


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


def _materialize_session_index(
    *,
    chatlas_root: Path,
    provider_configs: tuple[ChatlasArchiveConfig, ...],
    session_index_cache: dict[str, dict[str, object]],
    session_index_cache_enabled: bool,
) -> ChatlasSessionIndexMaterialization:
    discovered_sessions = _discover_chatlas_session_refs(
        raw_root=chatlas_root / "raw",
        provider_configs=provider_configs,
    )
    session_index: list[dict[str, Any]] = []
    source_signatures: dict[str, dict[str, object]] = {}
    next_session_index_cache: dict[str, dict[str, object]] = {}
    for session_ref in discovered_sessions:
        cache_key = _session_ref_index_cache_key(session_ref)
        source_signature = _session_ref_index_source_signature(session_ref)
        source_signatures[cache_key] = source_signature
        cached_entry = session_index_cache.get(cache_key)
        if (
            session_index_cache_enabled
            and _session_index_cache_entry_matches(cached_entry, source_signature)
        ):
            cached_session = cached_entry.get("session")
            if isinstance(cached_session, dict):
                indexed_session = dict(cached_session)
                session_index.append(indexed_session)
                next_session_index_cache[cache_key] = {
                    "source_signature": source_signature,
                    "session": indexed_session,
                }
                continue
        indexed_session = _session_ref_index_record(session_ref)
        session_index.append(indexed_session)
        next_session_index_cache[cache_key] = {
            "source_signature": source_signature,
            "session": indexed_session,
        }
    _write_session_index_shards(chatlas_root, session_index)
    return ChatlasSessionIndexMaterialization(
        sessions=session_index,
        source_signatures=source_signatures,
        session_index_cache=next_session_index_cache,
    )


def _discover_chatlas_session_refs(
    *,
    raw_root: Path,
    provider_configs: tuple[ChatlasArchiveConfig, ...],
) -> list[ChatlasProviderSessionRef]:
    discovered_sessions: list[ChatlasProviderSessionRef] = []
    for provider_config in provider_configs:
        agent = _chatlas_session_agent(
            raw_root=raw_root,
            archive_provider_config=provider_config,
        )
        if agent is None or not hasattr(agent, "discover_session_refs"):
            continue
        for session_ref in agent.discover_session_refs():
            discovered_sessions.append(
                ChatlasProviderSessionRef(
                    archive_config=provider_config,
                    agent=agent,
                    session_ref=session_ref,
                )
            )

    return _dedupe_chatlas_session_refs(discovered_sessions)


def _chatlas_session_agent(
    *,
    raw_root: Path,
    archive_provider_config: ChatlasArchiveConfig,
) -> Agent | None:
    if _provider_family_for_name(archive_provider_config.family) is None:
        return None

    raw_homes = tuple(
        (
            home_key,
            _chatlas_home_destination(
                raw_root=raw_root,
                home_path=source_home_path,
            ),
        )
        for home_key, source_home_path in archive_provider_config.homes
    )
    return agent_from_config(
        AgentConfig(
            provider=archive_provider_config.family,
            instance_id=archive_provider_config.instance_id,
            label=archive_provider_config.label,
            homes=raw_homes,
            is_default=archive_provider_config.is_default,
            fingerprint=archive_provider_config.fingerprint,
        )
    )


def _dedupe_chatlas_session_refs(
    sessions: list[ChatlasProviderSessionRef],
) -> list[ChatlasProviderSessionRef]:
    deduped: dict[tuple[object, ...], ChatlasProviderSessionRef] = {}
    for session in sessions:
        key = _chatlas_session_ref_identity_key(session)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = session
            continue
        deduped[key] = _merge_chatlas_session_ref(existing, session)
    return sorted(
        deduped.values(),
        key=lambda session: (
            session.archive_config.family,
            session.archive_config.fingerprint,
            session.session_ref.native_session_id,
        ),
    )


def _chatlas_session_ref_identity_key(session: ChatlasProviderSessionRef) -> tuple[object, ...]:
    return (
        session.archive_config.family,
        session.archive_config.identity_key(),
        session.session_ref.native_session_id,
    )


def _merge_chatlas_session_ref(
    left: ChatlasProviderSessionRef,
    right: ChatlasProviderSessionRef,
) -> ChatlasProviderSessionRef:
    left_ref = left.session_ref
    right_ref = right.session_ref
    if hasattr(left_ref, "merge"):
        merged_ref = left_ref.merge(right_ref)
    else:
        merged_ref = left_ref
    return ChatlasProviderSessionRef(
        archive_config=left.archive_config,
        agent=left.agent,
        session_ref=merged_ref,
    )


def _session_ref_index_record(session: ChatlasProviderSessionRef) -> dict[str, Any]:
    session_ref = session.session_ref
    backing_artifacts = session.backing_artifacts()
    primary_backing_artifact = backing_artifacts[0] if backing_artifacts else None
    payload = {
        "provider": session.archive_config.family,
        "uri": _chatlas_session_ref_uri(session),
        "provider_instance_fingerprint": session.archive_config.fingerprint,
        "session_id": session_ref.native_session_id,
        "display_name": session_ref.display_name(),
        "display_name_field": session_ref.display_name_field(),
        "created_at": _format_stats_timestamp(session_ref.to_session().created_timestamp()),
        "updated_at": _format_stats_timestamp(session_ref.sort_timestamp()),
        "extractable": _chatlas_session_ref_is_probably_extractable(
            session.archive_config.family,
            backing_artifacts,
        ),
        "backing_artifact_count": len(backing_artifacts),
        "primary_backing_artifact": (
            _serialize_session_ref_backing_artifact(session.archive_config.family, primary_backing_artifact)
            if primary_backing_artifact is not None
            else None
        ),
        "native": dict(session_ref.native_ref_metadata()),
        "backing_artifacts": [
            _serialize_session_ref_backing_artifact(session.archive_config.family, artifact)
            for artifact in backing_artifacts
        ],
        "instance": _chatlas_archive_identity_name(session.archive_config),
        "identity_hash": _session_identity_hash(
            provider=session.archive_config.family,
            provider_session_id=session_ref.native_session_id,
        ),
        "class": "agentos.chatlas.session",
        "schema_version": 1,
    }
    return payload


def _chatlas_session_ref_uri(session: ChatlasProviderSessionRef) -> str:
    return (
        f"agentos://chat-session/{quote(session.archive_config.family, safe='')}/"
        f"{session.archive_config.uri_key}/"
        f"{quote(session.session_ref.native_session_id, safe='')}"
    )


def _session_ref_index_cache_key(session: ChatlasProviderSessionRef) -> str:
    provider = _session_fs_component(session.archive_config.family)
    fingerprint = _session_fs_component(session.archive_config.fingerprint)
    session_id = _session_fs_component(session.session_ref.native_session_id)
    return f"{provider}/{fingerprint}/{session_id}"


def _session_ref_index_source_signature(session: ChatlasProviderSessionRef) -> dict[str, object]:
    session_ref = session.session_ref
    backing_artifacts = session.backing_artifacts()
    primary_backing_artifact = backing_artifacts[0] if backing_artifacts else None
    provider = session.archive_config.family
    return {
        "provider": provider,
        "instance": _chatlas_archive_identity_name(session.archive_config),
        "provider_instance_fingerprint": session.archive_config.fingerprint,
        "session_id": session_ref.native_session_id,
        "display_name": session_ref.display_name(),
        "display_name_field": session_ref.display_name_field(),
        "updated_at": _format_stats_timestamp(session_ref.sort_timestamp()),
        "extractable": _chatlas_session_ref_is_probably_extractable(provider, backing_artifacts),
        "native": dict(session_ref.native_ref_metadata()),
        "primary_backing_artifact": (
            None
            if primary_backing_artifact is None
            else _session_ref_index_backing_artifact_signature(provider, primary_backing_artifact)
        ),
        "backing_artifacts": [
            _session_ref_index_backing_artifact_signature(provider, artifact)
            for artifact in backing_artifacts
        ],
        "signature_version": 2,
        "derivation_version": _SESSION_INDEX_DERIVATION_VERSION,
    }


def _serialize_session_ref_backing_artifact(
    provider: str,
    artifact: BackingArtifact,
) -> dict[str, Any]:
    return artifact.summary(
        extractable=_chatlas_backing_artifact_is_probably_extractable(
            provider,
            artifact,
            source_signature=_chatlas_cache_path_metadata_signature(artifact.path),
        ),
    )


def _chatlas_session_ref_is_probably_extractable(
    provider: str,
    backing_artifacts: tuple[BackingArtifact, ...],
) -> bool:
    return any(
        _chatlas_backing_artifact_is_probably_extractable(
            provider,
            artifact,
            source_signature=_chatlas_cache_path_metadata_signature(artifact.path),
        )
        for artifact in backing_artifacts
    )


def _session_ref_index_backing_artifact_signature(
    provider: str,
    artifact: BackingArtifact,
) -> dict[str, object]:
    source_signature = _chatlas_cache_path_metadata_signature(artifact.path)
    signature = {
        "role": artifact.role,
        "storage_kind": _normalized_backing_artifact_storage_kind(
            artifact,
            source_signature=source_signature,
        ),
        "path": str(artifact.path),
        "locator": artifact.locator,
        "extractable": _chatlas_backing_artifact_is_probably_extractable(
            provider,
            artifact,
            source_signature=source_signature,
        ),
    }
    signature["source_signature"] = source_signature
    return signature


def _chatlas_archive_identity_name(config: ChatlasArchiveConfig) -> str:
    summary = config.summary()
    instance_id = summary.get("instance_id")
    if isinstance(instance_id, str) and instance_id:
        return instance_id

    homes = summary.get("homes")
    if isinstance(homes, dict):
        derived_name = _derive_chatlas_identity_name(config.family, homes.values())
        if derived_name is not None:
            return derived_name

    return config.fingerprint[:12]


def _normalized_backing_artifact_storage_kind(
    artifact,
    *,
    source_signature: dict[str, object],
) -> str:
    if artifact.storage_kind is not None:
        return str(artifact.storage_kind)
    if isinstance(source_signature.get("size"), int):
        return "file"
    storage_kind = source_signature.get("storage_kind")
    if isinstance(storage_kind, str) and storage_kind:
        return storage_kind
    return "other"


def _chatlas_backing_artifact_is_probably_extractable(
    provider: str,
    artifact,
    *,
    source_signature: dict[str, object],
) -> bool:
    if not bool(source_signature.get("exists")):
        return False
    if not isinstance(source_signature.get("size"), int):
        return False

    path = artifact.path
    if provider == "claude-code":
        return artifact.role == "transcript" and path.suffix in {".json", ".jsonl"}
    if provider == "codex":
        return artifact.role == "transcript" and path.suffix == ".jsonl" and path.name.startswith("rollout-")
    if provider == "copilot-cli":
        return artifact.role == "transcript" and path.suffix == ".jsonl"
    if provider == "gemini-cli":
        return artifact.role == "transcript" and path.suffix == ".json"
    if provider == "pi":
        return artifact.role == "transcript" and path.suffix == ".jsonl"
    if provider == "openclaw":
        return artifact.role == "transcript" and path.suffix == ".jsonl"
    if provider == "opencode":
        return artifact.role in {"session_diff", "sqlite_session_row"} and (
            path.suffix == ".json" or path.name == "opencode.db"
        )
    return False


def _session_fs_component(value: str) -> str:
    return quote(value, safe="._-")


def _session_index_dir(chatlas_root: Path) -> Path:
    return chatlas_root / _SESSION_INDEX_ROOT_RELATIVE_PATH


def _session_index_shard_prefix(session: dict[str, Any]) -> str:
    identity_hash = session.get("identity_hash")
    if not isinstance(identity_hash, str) or not identity_hash.startswith("sha256:"):
        raise CliError("session index row is missing sha256 identity_hash")
    digest = identity_hash.removeprefix("sha256:")
    if len(digest) < 2:
        raise CliError("session index row has invalid identity_hash")
    return digest[:2]


def _session_index_shard_path(chatlas_root: Path, prefix: str) -> Path:
    return _session_index_dir(chatlas_root) / f"{prefix}.index.jsonl"


def _write_session_index_shards(
    chatlas_root: Path,
    sessions: list[dict[str, Any]],
) -> None:
    index_dir = _session_index_dir(chatlas_root)
    index_dir.mkdir(parents=True, exist_ok=True)

    shards: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        shards.setdefault(_session_index_shard_prefix(session), []).append(session)

    expected_paths = {
        _session_index_shard_path(chatlas_root, prefix)
        for prefix in shards
    }
    for shard_path in index_dir.glob("*.index.jsonl"):
        if shard_path not in expected_paths:
            shard_path.unlink()

    for prefix, shard_sessions in sorted(shards.items()):
        sorted_sessions = sorted(
            shard_sessions,
            key=lambda session: (
                str(session.get("provider", "")),
                str(session.get("instance", "")),
                str(session.get("session_id", "")),
            ),
        )
        rendered = "".join(
            json.dumps(session, sort_keys=True) + "\n"
            for session in sorted_sessions
        )
        write_text_if_changed(
            _session_index_shard_path(chatlas_root, prefix),
            rendered,
        )


def _load_session_index(chatlas_root: Path) -> list[dict[str, Any]]:
    index_dir = _session_index_dir(chatlas_root)
    if not index_dir.is_dir():
        return []
    sessions: list[dict[str, Any]] = []
    for shard_path in sorted(index_dir.glob("*.index.jsonl")):
        sessions.extend(_load_jsonl_dict_rows(shard_path))
    return sessions

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


def _selected_session_index(
    chatlas_root: Path,
    *,
    providers: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    sessions = _load_session_index(chatlas_root)
    if providers is None:
        return sessions
    requested_providers = set(providers)
    return [session for session in sessions if session.get("provider") in requested_providers]


def _session_matches_query_filters(
    session: dict[str, Any],
    *,
    extractable_only: bool,
    updated_after: float | None,
    instances: frozenset[str] | None,
) -> bool:
    if extractable_only and not bool(session.get("extractable")):
        return False
    if updated_after is not None:
        timestamp = _chatlas_session_sort_timestamp(session)
        if timestamp is None or timestamp < updated_after:
            return False
    if instances is not None:
        instance = _string_or_none(session.get("instance"))
        if instance is None or instance not in instances:
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


def _matched_session_index_fields(
    session: dict[str, Any],
    *,
    query: str | None,
) -> tuple[tuple[str, str], ...]:
    if query is None:
        return ()
    matched_fields: list[tuple[str, str]] = []
    for field_name in (
        "uri",
        "instance",
        "provider_instance_fingerprint",
        "session_id",
        "identity_hash",
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
    _ = chatlas_root
    return _chatlas_provider_stats_from_index_session(session)


def _chatlas_provider_stats_from_index_session(session: dict[str, Any]) -> dict[str, Any]:
    provider = _string_or_none(session.get("provider"))
    payload: dict[str, Any] = {
        "provider": provider,
        "session_id": session.get("session_id"),
        "display_name": session.get("display_name"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "extractable": session.get("extractable"),
        "backing_artifact_count": session.get("backing_artifact_count", 0),
    }
    primary = session.get("primary_backing_artifact")
    if isinstance(primary, dict):
        payload["primary_backing_artifact"] = primary.get("path")
    native = session.get("native")
    if isinstance(native, dict):
        payload.update(native)
    payload.update(_provider_stats_from_index_session(session))
    return {key: value for key, value in payload.items() if value is not None}


def _provider_stats_from_index_session(session: dict[str, Any]) -> dict[str, object]:
    provider = _string_or_none(session.get("provider"))
    if provider == "codex":
        codex_session = CodexSession.from_chatlas_session_payload(
            session,
            sources=_chatlas_backing_artifacts(session),
        )
        if codex_session is not None:
            return codex_session.provider_stats()
    if provider == "openclaw":
        openclaw_session = OpenclawSession.from_chatlas_session_payload(session)
        if openclaw_session is not None:
            return openclaw_session.provider_stats()
    return {}


def _chatlas_backing_artifacts(session: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = session.get("backing_artifacts")
    if isinstance(artifacts, list):
        return [artifact for artifact in artifacts if isinstance(artifact, dict)]
    primary = session.get("primary_backing_artifact")
    return [primary] if isinstance(primary, dict) else []


def _chatlas_session_with_match(selection: ChatlasSessionSelection) -> dict[str, Any]:
    session = dict(selection.session)
    if selection.matched_fields:
        session["match"] = {
            "query": selection.matched_fields[0][1],
            "kind": "exact_identity",
            "fields": [
                {
                    "field": field_name,
                    "value": value,
                }
                for field_name, value in selection.matched_fields
            ],
        }
    return session


def _format_chatlas_resolved_session_choices(sessions: list[dict[str, Any]]) -> str:
    return ", ".join(
        str(session.get("uri") or session.get("session_id"))
        for session in sessions[:5]
    )


def _select_chatlas_sessions(
    chatlas_root: Path,
    *,
    query: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    extractable_only: bool = False,
    updated_after: float | None = None,
) -> list[ChatlasSessionSelection]:
    instance_filters = None if instances is None else frozenset(instances)
    selections: list[ChatlasSessionSelection] = []
    for session in _selected_session_index(chatlas_root, providers=providers):
        if not _session_matches_query_filters(
            session,
            extractable_only=extractable_only,
            updated_after=updated_after,
            instances=instance_filters,
        ):
            continue
        matched_fields = _matched_session_index_fields(session, query=query)
        if query is not None and not matched_fields:
            continue
        selections.append(
            ChatlasSessionSelection(
                session=session,
                matched_fields=matched_fields,
            )
        )
    return selections


def _select_one_chatlas_session(
    chatlas_root: Path,
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        raise CliError("query must not be empty")
    selections = _select_chatlas_sessions(
        chatlas_root,
        query=normalized_query,
        providers=providers,
    )
    if not selections:
        raise CliError(f"no Chatlas session matched query {query}")
    if len(selections) > 1:
        choices = ", ".join(
            str(selection.session.get("uri"))
            for selection in selections[:5]
        )
        raise CliError(f"multiple Chatlas sessions matched query {query}: {choices}")
    return selections[0].session


def _chatlas_single_session_selection_payload(
    *,
    query: str,
    providers: tuple[str, ...] | None,
) -> dict[str, object]:
    return {
        "kind": "query",
        "query": query,
        "providers": list(providers) if providers is not None else None,
    }


def _chatlas_raw_source_payloads(
    session: dict[str, Any],
    *,
    include_content: bool = False,
) -> list[dict[str, object]]:
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        primary = session.get("primary_backing_artifact")
        artifacts = [primary] if isinstance(primary, dict) else []

    sources: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            continue
        source = _chatlas_raw_source_payload(index=index, artifact=artifact)
        identity = (
            source.get("role"),
            source.get("storage_kind"),
            source.get("path"),
            json.dumps(source.get("locator"), sort_keys=True, default=str),
        )
        if identity in seen:
            continue
        seen.add(identity)
        if include_content:
            source.update(_chatlas_raw_source_content(source))
        sources.append(source)
    return sources


def _chatlas_raw_source_payload(*, index: int, artifact: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_index": index,
    }
    for key in (
        "role",
        "storage_kind",
        "path",
        "locator",
        "extractable",
    ):
        value = artifact.get(key)
        if value is not None:
            payload[key] = value
    return payload


def _chatlas_raw_source_content(source: dict[str, object]) -> dict[str, object]:
    path_text = _string_or_none(source.get("path"))
    if path_text is None:
        return {
            "content": None,
            "content_encoding": None,
            "content_unavailable_reason": "missing_path",
        }

    path = Path(path_text)
    try:
        path_stat = path.stat()
    except OSError as exc:
        return {
            "content": None,
            "content_encoding": None,
            "content_unavailable_reason": f"stat_failed: {exc}",
        }
    if not stat.S_ISREG(path_stat.st_mode):
        return {
            "content": None,
            "content_encoding": None,
            "content_unavailable_reason": "not_regular_file",
        }

    try:
        raw_content = path.read_bytes()
    except OSError as exc:
        return {
            "content": None,
            "content_encoding": None,
            "content_unavailable_reason": f"read_failed: {exc}",
        }

    try:
        return {
            "content": raw_content.decode("utf-8"),
            "content_encoding": "utf-8",
        }
    except UnicodeDecodeError:
        return {
            "content": base64.b64encode(raw_content).decode("ascii"),
            "content_encoding": "base64",
        }


def _derive_chatlas_identity_name(family: str, home_paths: object) -> str | None:
    for home_path in home_paths:
        basename = Path(str(home_path)).expanduser().name
        if not basename:
            continue
        for separator in ("-", "_"):
            family_prefix = f"{family}{separator}"
            if basename.startswith(family_prefix):
                suffix = basename[len(family_prefix):].strip()
                if suffix:
                    return suffix
        return basename
    return None


def _normalize_chatlas_instance_filters(instances: tuple[str, ...] | None) -> tuple[str, ...] | None:
    if not instances:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for instance in instances:
        stripped = instance.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        normalized.append(stripped)
    return tuple(normalized) or None


def _compact_chatlas_session_payload(session: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field_name in ("provider", "instance", "session_id", "display_name", "updated_at"):
        value = session.get(field_name)
        if value is not None:
            payload[field_name] = value
    return payload


def _session_index_cache_path(chatlas_root: Path) -> Path:
    return chatlas_root / _SESSION_INDEX_CACHE_RELATIVE_PATH


def _load_session_index_cache(chatlas_root: Path) -> dict[str, dict[str, object]]:
    raw_sessions = load_chatlas_cache_section(
        _session_index_cache_path(chatlas_root),
        entries_key="sessions",
    )
    sessions: dict[str, dict[str, object]] = {}
    for session_key, raw_entry in raw_sessions.items():
        if not isinstance(session_key, str) or not session_key.strip() or not isinstance(raw_entry, dict):
            continue
        source_signature = raw_entry.get("source_signature")
        session_payload = raw_entry.get("session")
        if not isinstance(source_signature, dict) or not isinstance(session_payload, dict):
            continue
        sessions[session_key] = {
            "source_signature": source_signature,
            "session": session_payload,
        }
    return sessions


def _write_session_index_cache(
    chatlas_root: Path,
    session_index_cache: dict[str, dict[str, object]],
) -> None:
    write_chatlas_cache_section(
        _session_index_cache_path(chatlas_root),
        cache_class="agentos.chatlas.session_index_cache",
        entries_key="sessions",
        entries={
            session_key: {
                "source_signature": dict(entry["source_signature"]),
                "session": dict(entry["session"]),
            }
            for session_key, entry in sorted(session_index_cache.items())
        },
    )


def _chatlas_cache_path_metadata_signature(path: Path) -> dict[str, object]:
    signature: dict[str, object] = {
        "path": str(path),
    }
    try:
        source_stat = path.stat()
    except OSError:
        signature["exists"] = False
        return signature

    signature["exists"] = True
    signature["mtime_ns"] = int(source_stat.st_mtime_ns)
    mode = source_stat.st_mode
    if stat.S_ISREG(mode):
        signature["size"] = int(source_stat.st_size)
        return signature
    if stat.S_ISDIR(mode):
        signature["storage_kind"] = "directory"
        return signature
    signature["storage_kind"] = "other"
    return signature


def _session_index_cache_entry_matches(
    cached_entry: dict[str, object] | None,
    source_signature: dict[str, object],
) -> bool:
    if cached_entry is None:
        return False
    cached_session = cached_entry.get("session")
    if not isinstance(cached_session, dict):
        return False
    cached_source_signature = cached_entry.get("source_signature")
    if not isinstance(cached_source_signature, dict):
        return False

    comparable_fields = (
        "provider",
        "instance",
        "provider_instance_fingerprint",
        "session_id",
        "display_name",
        "display_name_field",
        "updated_at",
        "extractable",
        "native",
        "derivation_version",
    )
    for field_name in comparable_fields:
        if cached_source_signature.get(field_name) != source_signature.get(field_name):
            return False

    if not _session_index_artifact_signature_matches(
        cached_source_signature.get("primary_backing_artifact"),
        source_signature.get("primary_backing_artifact"),
    ):
        return False

    cached_artifacts = cached_source_signature.get("backing_artifacts")
    source_artifacts = source_signature.get("backing_artifacts")
    if not isinstance(cached_artifacts, list) or not isinstance(source_artifacts, list):
        return cached_artifacts == source_artifacts
    if len(cached_artifacts) != len(source_artifacts):
        return False
    return all(
        _session_index_artifact_signature_matches(cached_artifact, source_artifact)
        for cached_artifact, source_artifact in zip(cached_artifacts, source_artifacts)
    )


def _session_index_artifact_signature_matches(
    cached_artifact: object,
    source_artifact: object,
) -> bool:
    if cached_artifact is None or source_artifact is None:
        return cached_artifact is None and source_artifact is None
    if not isinstance(cached_artifact, dict) or not isinstance(source_artifact, dict):
        return False

    comparable_fields = ("role", "storage_kind", "path", "locator", "extractable")
    for field_name in comparable_fields:
        if cached_artifact.get(field_name) != source_artifact.get(field_name):
            return False

    return _session_index_path_signature_matches(
        cached_artifact.get("source_signature"),
        source_artifact.get("source_signature"),
    )


def _session_index_path_signature_matches(
    cached_path_signature: object,
    source_path_signature: object,
) -> bool:
    if not isinstance(cached_path_signature, dict) or not isinstance(source_path_signature, dict):
        return cached_path_signature == source_path_signature

    comparable_fields = ("path", "exists", "mtime_ns", "size", "storage_kind")
    return all(
        cached_path_signature.get(field_name) == source_path_signature.get(field_name)
        for field_name in comparable_fields
    )


__all__ = [
    "chatlas_query",
    "chatlas_raw_export",
    "chatlas_raw_paths",
    "chatlas_resolved_session_stats",
    "chatlas_stats",
    "chatlas_update",
    "configured_chatlas_settings",
    "default_chatlas_root",
    "format_chatlas_stats_markdown",
    "resolve_chatlas_sessions",
]
