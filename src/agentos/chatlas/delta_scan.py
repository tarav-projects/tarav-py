from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
from shutil import copy2, rmtree
import stat
import time
from typing import Any, Callable, Literal
from urllib.parse import quote, unquote

from agentos._core.errors import CliError
from agentos.agent.config import load_chat_config_documents, load_unique_string_list
from agentos.agent.primitives import Agent, AgentConfig, SessionSource, agent_fingerprint
from agentos.agent.providers import agent_from_config, load_configured_agents
from agentos.agent.session_refs import BackingArtifact, ProviderSessionRef, backing_artifacts_from_sources
from agentos.agent.sessions import _format_stats_timestamp
from agentos.chatlas._cache_io import write_text_if_changed
from agentos.chatlas.raw import supported_chatlas_provider_families
from agentos.chatlas.session_model._hashes import _session_identity_hash

CHATLAS_DIRNAME = "chatlas"
DEFAULT_CHATLAS_PHASE = "index-only"
SESSION_INDEX_DERIVATIONS_CACHE_DIR = Path("cache") / "session-index-derivations-v1"
SESSION_INDEX_ROOT = Path("index") / "sessions"
CopyResult = Literal["added", "updated", "unchanged", "skipped"]

_REPORT_TEMPLATE: dict[str, Any] = {
    "provider_count": 0,
    "instance_count": 0,
    "native_scan": {
        "session_count": 0,
        "source_artifact_count": 0,
        "changed_session_count": 0,
        "changed_source_artifact_count": 0,
        "unchanged_session_count": 0,
        "cached_source_artifact_count": 0,
    },
    "cache": {
        "hit_count": 0,
        "miss_count": 0,
        "removed_entry_count": 0,
    },
    "raw_copy": {
        "scanned_source_count": 0,
        "copied_session_count": 0,
        "copied_file_count": 0,
        "added_file_count": 0,
        "updated_file_count": 0,
        "unchanged_file_count": 0,
        "skipped_source_count": 0,
    },
    "session_index": {
        "delta_session_count": 0,
        "derived_row_count": 0,
        "upserted_row_count": 0,
        "partition_count": 0,
    },
    "timing": {
        "elapsed_seconds": 0.0,
        "native_scan_seconds": 0.0,
        "cache_compare_seconds": 0.0,
        "cache_write_seconds": 0.0,
        "raw_copy_seconds": 0.0,
        "index_seconds": 0.0,
    },
}

_TRANSCRIPT_EXTRACTABLE_SUFFIXES = {
    "claude-code": {".json", ".jsonl"},
    "copilot-cli": {".jsonl"},
    "gemini-cli": {".json"},
    "openclaw": {".jsonl"},
    "pi": {".jsonl"},
}


@dataclass(frozen=True)
class ChatlasProviderInstance:
    agent: Agent
    fingerprint: str

    @property
    def provider(self) -> str:
        return self.agent.provider

    @property
    def instance(self) -> str:
        return self.agent.instance_id or self.fingerprint[:12]

    @property
    def partition_key(self) -> str:
        return f"{_path_component(self.provider)}/{_path_component(self.fingerprint)}"

    def raw_home(self, raw_root: Path) -> Path | None:
        if self.agent.home is None:
            return None
        return raw_root / self.partition_key / "home"


@dataclass(frozen=True)
class ChatlasDiscoveredSession:
    provider_instance: ChatlasProviderInstance
    session_ref: ProviderSessionRef

    @property
    def session_id(self) -> str:
        return self.session_ref.native_session_id

    @property
    def cache_key(self) -> str:
        return _session_cache_key(self.session_id)

    def sources(self) -> tuple[SessionSource, ...]:
        return self.session_ref.to_session().sources()

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        return backing_artifacts_from_sources(self.sources())


@dataclass(frozen=True)
class ChatlasDeltaSession:
    session: ChatlasDiscoveredSession
    sources: tuple[SessionSource, ...]

    @property
    def session_id(self) -> str:
        return self.session.session_id


@dataclass(frozen=True)
class ChatlasDeltaScanResult:
    payload: dict[str, object]


def default_chatlas_root() -> Path:
    return Path.home().expanduser().resolve() / "Documents" / CHATLAS_DIRNAME


def run_chatlas_delta_scan(
    *,
    providers: tuple[str, ...] | None,
    chatlas_root: Path | None,
    start_path: Path | str,
    cache_enabled: bool,
    command_name: str = "chatlas index update",
    progress: Callable[[str], None] | None,
) -> ChatlasDeltaScanResult:
    started_at = time.perf_counter()
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    raw_root = chatlas_root_path / "raw"
    session_index_root = chatlas_root_path / SESSION_INDEX_ROOT
    cache_root = chatlas_root_path / SESSION_INDEX_DERIVATIONS_CACHE_DIR
    selected_instances = _selected_provider_instances(
        providers=providers,
        start_path=start_path,
    )

    report = _empty_report()
    report["provider_count"] = len({instance.provider for instance in selected_instances})
    report["instance_count"] = len(selected_instances)
    selected_payload = {
        "providers": list(providers) if providers is not None else None,
        "instances": [
            _provider_instance_summary(instance, raw_root=raw_root)
            for instance in selected_instances
        ],
    }
    instance_payloads: list[dict[str, Any]] = []

    for instance in selected_instances:
        _emit(progress, f"[chatlas] {instance.provider}/{instance.instance}: native scan")
        instance_report = _process_provider_instance(
            instance=instance,
            raw_root=raw_root,
            session_index_root=session_index_root,
            cache_root=cache_root,
            cache_enabled=cache_enabled,
            progress=progress,
        )
        _merge_report(report, instance_report)
        instance_payloads.append(
            {
                **_provider_instance_summary(instance, raw_root=raw_root),
                "stats": _report_stats_payload(instance_report),
            }
        )

    report["timing"]["elapsed_seconds"] = _elapsed_seconds(started_at)
    payload = {
        "status": "ok",
        "command": command_name,
        "phase": DEFAULT_CHATLAS_PHASE,
        "chatlas_root": str(chatlas_root_path),
        "raw_root": str(raw_root),
        "session_index_root": str(session_index_root),
        "cache_root": str(cache_root),
        "selection": selected_payload,
        "instances": instance_payloads,
        "scan_cache_enabled": cache_enabled,
        **report,
    }
    _emit_update_summary(progress, payload)
    return ChatlasDeltaScanResult(payload=payload)


def run_chatlas_index_reset(
    *,
    chatlas_root: Path | None,
    progress: Callable[[str], None] | None,
) -> ChatlasDeltaScanResult:
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    reset_targets = (
        chatlas_root_path / SESSION_INDEX_ROOT,
        chatlas_root_path / SESSION_INDEX_DERIVATIONS_CACHE_DIR,
    )
    deleted: list[dict[str, object]] = []
    for path in reset_targets:
        existed = path.exists()
        if existed:
            rmtree(path)
        deleted.append({"path": str(path), "existed": existed, "deleted": existed})
    payload = {
        "status": "ok",
        "command": "chatlas index reset",
        "chatlas_root": str(chatlas_root_path),
        "deleted": deleted,
    }
    _emit(progress, f"[chatlas] index reset: deleted {sum(1 for row in deleted if row['deleted'])} paths")
    return ChatlasDeltaScanResult(payload=payload)


def run_chatlas_index_redo(
    *,
    providers: tuple[str, ...] | None,
    chatlas_root: Path | None,
    progress: Callable[[str], None] | None,
) -> ChatlasDeltaScanResult:
    started_at = time.perf_counter()
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    raw_root = chatlas_root_path / "raw"
    session_index_root = chatlas_root_path / SESSION_INDEX_ROOT
    selected_instances = _archived_provider_instances(raw_root=raw_root, providers=providers)
    _reset_session_index_for_redo(session_index_root, providers=providers)

    report = _empty_report()
    report["provider_count"] = len({instance.provider for instance in selected_instances})
    report["instance_count"] = len(selected_instances)
    instance_payloads: list[dict[str, Any]] = []

    for instance in selected_instances:
        _emit(progress, f"[chatlas] {instance.provider}/{instance.instance}: raw index redo")
        instance_report = _redo_provider_instance_index(
            instance=instance,
            raw_root=raw_root,
            session_index_root=session_index_root,
            progress=progress,
        )
        _merge_report(report, instance_report)
        instance_payloads.append(
            {
                **_provider_instance_summary(instance, raw_root=raw_root),
                "stats": _report_stats_payload(instance_report),
            }
        )

    report["timing"]["elapsed_seconds"] = _elapsed_seconds(started_at)
    payload = {
        "status": "ok",
        "command": "chatlas index redo",
        "phase": "index-redo",
        "chatlas_root": str(chatlas_root_path),
        "raw_root": str(raw_root),
        "session_index_root": str(session_index_root),
        "selection": {
            "providers": list(providers) if providers is not None else None,
            "instances": [
                _provider_instance_summary(instance, raw_root=raw_root)
                for instance in selected_instances
            ],
        },
        "instances": instance_payloads,
        **report,
    }
    _emit_update_summary(progress, payload)
    return ChatlasDeltaScanResult(payload=payload)


def _selected_provider_instances(
    *,
    providers: tuple[str, ...] | None,
    start_path: Path | str,
) -> tuple[ChatlasProviderInstance, ...]:
    supported = {
        provider_family.family
        for provider_family in supported_chatlas_provider_families()
    }
    selected_instance_ids = _load_chatlas_instance_ids(start_path=start_path)
    agents = _select_chatlas_agents(
        load_configured_agents(start_path=start_path),
        selected_instance_ids=selected_instance_ids,
        supported_families=supported,
    )
    if providers is not None:
        provider_filter = set(providers)
        agents = tuple(agent for agent in agents if agent.provider in provider_filter)

    deduped: dict[tuple[str, str], ChatlasProviderInstance] = {}
    for agent in agents:
        instance = ChatlasProviderInstance(agent=agent, fingerprint=agent_fingerprint(agent))
        deduped[(instance.provider, instance.fingerprint)] = instance
    return tuple(sorted(deduped.values(), key=lambda instance: (instance.provider, instance.instance)))


def _load_chatlas_instance_ids(*, start_path: Path | str) -> tuple[str, ...] | None:
    result: tuple[str, ...] | None = None
    for config in load_chat_config_documents(start_path=start_path):
        chatlas_config = config.get("chatlas")
        if not isinstance(chatlas_config, dict) or "instance_ids" not in chatlas_config:
            continue
        result = load_unique_string_list(
            chatlas_config["instance_ids"],
            container_field_name="config field chatlas.instance_ids",
            item_field_name="chatlas.instance_ids",
        )
    return result


def _select_chatlas_agents(
    agents: tuple[Agent, ...],
    *,
    selected_instance_ids: tuple[str, ...] | None,
    supported_families: set[str],
) -> tuple[Agent, ...]:
    supported_agents = tuple(agent for agent in agents if agent.provider in supported_families)
    if selected_instance_ids is None:
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
            raise CliError(f"chatlas.instance_ids references unknown agent instance id: {instance_id}")
        if agent.provider not in supported_families:
            raise CliError(
                f"Chatlas does not support provider {agent.provider} for agent instance id: {instance_id}"
            )
        selected_agents.append(agent)
    return tuple(agent for agent in selected_agents if agent in supported_agents)


def _process_provider_instance(
    *,
    instance: ChatlasProviderInstance,
    raw_root: Path,
    session_index_root: Path,
    cache_root: Path,
    cache_enabled: bool,
    progress: Callable[[str], None] | None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    report = _empty_report()
    discovery_started_at = time.perf_counter()
    native_sessions = _discover_instance_sessions(instance)
    report["timing"]["native_scan_seconds"] += _elapsed_seconds(discovery_started_at)
    report["native_scan"]["session_count"] = len(native_sessions)
    _create_raw_partition_manifest_if_missing(instance, raw_root=raw_root)

    cache_compare_started_at = time.perf_counter()
    old_cache = _load_derivation_cache_partition(cache_root, instance=instance) if cache_enabled else {}
    next_cache: dict[str, dict[str, object]] = {}
    delta_sessions: list[ChatlasDeltaSession] = []

    for session in native_sessions:
        sources = session.sources()
        source_count = len(sources)
        report["native_scan"]["source_artifact_count"] += source_count
        signature = _native_derivation_signature(session, sources=sources)
        next_cache[session.cache_key] = signature
        cached_signature = old_cache.get(session.cache_key)
        if cache_enabled and cached_signature == signature:
            report["cache"]["hit_count"] += 1
            report["native_scan"]["unchanged_session_count"] += 1
            report["native_scan"]["cached_source_artifact_count"] += source_count
            continue
        report["cache"]["miss_count"] += 1
        report["native_scan"]["changed_session_count"] += 1
        report["native_scan"]["changed_source_artifact_count"] += source_count
        delta_sessions.append(ChatlasDeltaSession(session=session, sources=sources))

    report["cache"]["removed_entry_count"] = len(set(old_cache) - set(next_cache))
    report["timing"]["cache_compare_seconds"] += _elapsed_seconds(cache_compare_started_at)
    if cache_enabled:
        cache_write_started_at = time.perf_counter()
        _write_derivation_cache_partition(cache_root, instance=instance, entries=next_cache)
        report["timing"]["cache_write_seconds"] += _elapsed_seconds(cache_write_started_at)

    raw_copy_started_at = time.perf_counter()
    copied_session_ids: set[str] = set()
    for delta_session in delta_sessions:
        copied = _copy_delta_session_sources(
            delta_session,
            raw_root=raw_root,
        )
        if copied["copied_file_count"] > 0:
            copied_session_ids.add(delta_session.session_id)
        _merge_nested_counter(report["raw_copy"], copied)
    report["timing"]["raw_copy_seconds"] += _elapsed_seconds(raw_copy_started_at)

    if not delta_sessions:
        report["timing"]["elapsed_seconds"] = _elapsed_seconds(started_at)
        return report

    index_started_at = time.perf_counter()
    indexed_rows = _derive_delta_index_rows_from_chatlas_raw(
        instance=instance,
        raw_root=raw_root,
        delta_sessions=tuple(delta_sessions),
    )
    upserted = _upsert_session_index_partition(
        session_index_root,
        instance=instance,
        rows=indexed_rows,
    )
    report["session_index"]["delta_session_count"] = len(delta_sessions)
    report["session_index"]["derived_row_count"] = len(indexed_rows)
    report["session_index"]["upserted_row_count"] = upserted
    report["session_index"]["partition_count"] = _index_partition_count(
        session_index_root,
        instance=instance,
        rows=indexed_rows,
    )
    report["raw_copy"]["copied_session_count"] = len(copied_session_ids)
    report["timing"]["index_seconds"] += _elapsed_seconds(index_started_at)
    report["timing"]["elapsed_seconds"] = _elapsed_seconds(started_at)
    _emit(
        progress,
        f"[chatlas] {instance.provider}/{instance.instance}: indexed {len(indexed_rows)} delta sessions",
    )
    return report


def _discover_instance_sessions(instance: ChatlasProviderInstance) -> list[ChatlasDiscoveredSession]:
    agent = instance.agent
    if not hasattr(agent, "discover_session_refs"):
        return []
    sessions = [
        ChatlasDiscoveredSession(provider_instance=instance, session_ref=session_ref)
        for session_ref in agent.discover_session_refs()
    ]
    return _dedupe_sessions(sessions)


def _archived_provider_instances(
    *,
    raw_root: Path,
    providers: tuple[str, ...] | None,
) -> tuple[ChatlasProviderInstance, ...]:
    if not raw_root.is_dir():
        return ()
    provider_filter = set(providers) if providers is not None else None
    instances: list[ChatlasProviderInstance] = []
    for provider_dir in sorted(path for path in raw_root.iterdir() if path.is_dir()):
        provider = unquote(provider_dir.name)
        if provider_filter is not None and provider not in provider_filter:
            continue
        for partition_dir in sorted(path for path in provider_dir.iterdir() if path.is_dir()):
            fingerprint = unquote(partition_dir.name)
            agent = _agent_from_raw_partition(
                provider=provider,
                fingerprint=fingerprint,
                partition_dir=partition_dir,
            )
            if agent is None:
                continue
            instances.append(ChatlasProviderInstance(agent=agent, fingerprint=fingerprint))
    return tuple(sorted(instances, key=lambda instance: (instance.provider, instance.instance)))


def _agent_from_raw_partition(
    *,
    provider: str,
    fingerprint: str,
    partition_dir: Path,
) -> Agent | None:
    raw_home = partition_dir / "home"
    raw_paths = partition_dir / "paths"
    home = raw_home if raw_home.is_dir() else None
    direct_targets: tuple[Path, ...] = ()
    if home is None and raw_paths.is_dir():
        direct_targets = tuple(sorted(path for path in raw_paths.rglob("*") if path.is_file()))
    if home is None and not direct_targets:
        return None
    return agent_from_config(
        AgentConfig(
            provider=provider,
            instance_id=None,
            label=None,
            home=home,
            direct_targets=direct_targets,
            sqlite_db_paths=(),
            is_default=False,
            fingerprint=fingerprint,
        )
    )


def _reset_session_index_for_redo(
    session_index_root: Path,
    *,
    providers: tuple[str, ...] | None,
) -> None:
    if providers is None:
        if session_index_root.exists():
            rmtree(session_index_root)
        return
    for provider in providers:
        provider_index_dir = session_index_root / _path_component(provider)
        if provider_index_dir.exists():
            rmtree(provider_index_dir)


def _redo_provider_instance_index(
    *,
    instance: ChatlasProviderInstance,
    raw_root: Path,
    session_index_root: Path,
    progress: Callable[[str], None] | None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    report = _empty_report()
    discovery_started_at = time.perf_counter()
    sessions = _discover_instance_sessions(instance)
    report["timing"]["native_scan_seconds"] += _elapsed_seconds(discovery_started_at)
    report["native_scan"]["session_count"] = len(sessions)
    report["native_scan"]["changed_session_count"] = len(sessions)
    for session in sessions:
        source_count = len(session.sources())
        report["native_scan"]["source_artifact_count"] += source_count
        report["native_scan"]["changed_source_artifact_count"] += source_count

    index_started_at = time.perf_counter()
    manifest_home = _raw_partition_manifest_home(raw_root, instance=instance)
    rows = [_session_index_row(session, provider_home=manifest_home) for session in sessions]
    upserted = _replace_session_index_partition(
        session_index_root,
        instance=instance,
        rows=rows,
    )
    report["session_index"]["delta_session_count"] = len(sessions)
    report["session_index"]["derived_row_count"] = len(rows)
    report["session_index"]["upserted_row_count"] = upserted
    report["session_index"]["partition_count"] = _index_partition_count(
        session_index_root,
        instance=instance,
        rows=rows,
    )
    report["timing"]["index_seconds"] += _elapsed_seconds(index_started_at)
    report["timing"]["elapsed_seconds"] = _elapsed_seconds(started_at)
    _emit(
        progress,
        f"[chatlas] {instance.provider}/{instance.instance}: redid {len(rows)} indexed sessions",
    )
    return report


def _derive_delta_index_rows_from_chatlas_raw(
    *,
    instance: ChatlasProviderInstance,
    raw_root: Path,
    delta_sessions: tuple[ChatlasDeltaSession, ...],
) -> list[dict[str, Any]]:
    archived_agent = _archived_provider_agent(
        instance,
        raw_root=raw_root,
        delta_sessions=delta_sessions,
    )
    if archived_agent is None or not hasattr(archived_agent, "discover_session_refs"):
        return []
    delta_session_ids = {delta_session.session_id for delta_session in delta_sessions}
    archived_instance = ChatlasProviderInstance(agent=archived_agent, fingerprint=instance.fingerprint)
    archived_sessions = _dedupe_sessions(
        [
            ChatlasDiscoveredSession(provider_instance=archived_instance, session_ref=session_ref)
            for session_ref in archived_agent.discover_session_refs()
            if session_ref.native_session_id in delta_session_ids
        ]
    )
    return [
        _session_index_row(session, provider_home=_provider_instance_home(instance))
        for session in archived_sessions
    ]


def _archived_provider_agent(
    instance: ChatlasProviderInstance,
    *,
    raw_root: Path,
    delta_sessions: tuple[ChatlasDeltaSession, ...],
) -> Agent | None:
    raw_home = instance.raw_home(raw_root)
    direct_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    if raw_home is None:
        direct_targets = tuple(
            sorted(
                {
                    copied_path
                    for delta_session in delta_sessions
                    for copied_path in _copied_paths_for_sources(
                        instance,
                        raw_root=raw_root,
                        sources=delta_session.sources,
                    )
                    if copied_path.exists()
                }
            )
        )
    return agent_from_config(
        AgentConfig(
            provider=instance.provider,
            instance_id=instance.agent.instance_id,
            label=instance.agent.label,
            home=raw_home,
            direct_targets=direct_targets,
            sqlite_db_paths=sqlite_db_paths,
            is_default=instance.agent.is_default,
            fingerprint=instance.fingerprint,
        )
    )


def _native_derivation_signature(
    session: ChatlasDiscoveredSession,
    *,
    sources: tuple[SessionSource, ...],
) -> dict[str, object]:
    return {
        "class": "agentos.chatlas.session_index_derivation",
        "schema_version": 1,
        "provider": session.provider_instance.provider,
        "provider_instance_fingerprint": session.provider_instance.fingerprint,
        "home": _provider_instance_home(session.provider_instance),
        "session_id": session.session_id,
        "display_name": session.session_ref.display_name(),
        "display_name_field": session.session_ref.display_name_field(),
        "updated_at": _format_stats_timestamp(session.session_ref.sort_timestamp()),
        "native": dict(session.session_ref.native_ref_metadata()),
        "sources": [
            _source_signature(source)
            for source in sources
        ],
    }


def _source_signature(source: SessionSource) -> dict[str, object]:
    signature = _path_metadata_signature(source.path)
    signature.update(
        {
            "role": source.role,
            "storage_kind": source.normalized_storage_kind(),
            "locator": source.locator,
        }
    )
    return signature


def _copy_delta_session_sources(
    delta_session: ChatlasDeltaSession,
    *,
    raw_root: Path,
) -> dict[str, int]:
    report = _empty_raw_copy_report()
    for source in delta_session.sources:
        report["scanned_source_count"] += 1
        if source.path.is_dir():
            report["skipped_source_count"] += 1
            continue
        destination = _copied_source_path(
            delta_session.session.provider_instance,
            raw_root=raw_root,
            source_path=source.path,
        )
        copy_result = _copy_file_if_changed(source.path, destination)
        if copy_result == "added":
            report["copied_file_count"] += 1
            report["added_file_count"] += 1
        elif copy_result == "updated":
            report["copied_file_count"] += 1
            report["updated_file_count"] += 1
        elif copy_result == "unchanged":
            report["unchanged_file_count"] += 1
        else:
            report["skipped_source_count"] += 1
    return report


def _copied_paths_for_sources(
    instance: ChatlasProviderInstance,
    *,
    raw_root: Path,
    sources: tuple[SessionSource, ...],
) -> tuple[Path, ...]:
    return tuple(
        _copied_source_path(instance, raw_root=raw_root, source_path=source.path)
        for source in sources
    )


def _copied_source_path(
    instance: ChatlasProviderInstance,
    *,
    raw_root: Path,
    source_path: Path,
) -> Path:
    if instance.agent.home is not None:
        try:
            relative = source_path.resolve().relative_to(instance.agent.home.resolve())
        except ValueError:
            relative = _absolute_path_relpath(source_path)
        return raw_root / instance.partition_key / "home" / relative
    return raw_root / instance.partition_key / "paths" / _absolute_path_relpath(source_path)


def _absolute_path_relpath(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_absolute():
        try:
            relative_text = os.path.relpath(str(resolved), resolved.anchor)
        except ValueError:
            return Path(resolved.name)
        return Path(relative_text)
    return resolved


def _copy_file_if_changed(source_path: Path, destination_path: Path) -> CopyResult:
    try:
        if not source_path.is_file():
            return "skipped"
        if destination_path.is_file() and _file_metadata_matches(source_path, destination_path):
            return "unchanged"
        existed = destination_path.exists() or destination_path.is_symlink()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        copy2(source_path, destination_path)
    except FileNotFoundError:
        return "skipped"
    except OSError as exc:
        raise CliError(f"failed to copy Chatlas raw source {source_path}: {exc}") from exc
    return "updated" if existed else "added"


def _file_metadata_matches(left: Path, right: Path) -> bool:
    try:
        left_stat = left.stat()
        right_stat = right.stat()
    except OSError:
        return False
    return (
        int(left_stat.st_mtime_ns) == int(right_stat.st_mtime_ns)
        and int(left_stat.st_size) == int(right_stat.st_size)
    )


_USE_PROVIDER_INSTANCE_HOME = object()


def _session_index_row(
    session: ChatlasDiscoveredSession,
    *,
    provider_home: str | None | object = _USE_PROVIDER_INSTANCE_HOME,
) -> dict[str, Any]:
    session_ref = session.session_ref
    native = dict(session_ref.native_ref_metadata())
    backing_artifacts = session.backing_artifacts()
    primary_backing_artifact = backing_artifacts[0] if backing_artifacts else None
    if provider_home is _USE_PROVIDER_INSTANCE_HOME:
        provider_home = _provider_instance_home(session.provider_instance)
    home_value = provider_home if isinstance(provider_home, str) else None
    return {
        "class": "agentos.chatlas.session",
        "schema_version": 1,
        "provider": session.provider_instance.provider,
        "instance": session.provider_instance.instance,
        "provider_instance_fingerprint": session.provider_instance.fingerprint,
        "home": home_value,
        "project_path": _session_project_path(native),
        "uri": _session_uri(session),
        "session_id": session.session_id,
        "display_name": session_ref.display_name(),
        "display_name_field": session_ref.display_name_field(),
        "created_at": _format_stats_timestamp(session_ref.to_session().created_timestamp()),
        "updated_at": _format_stats_timestamp(session_ref.sort_timestamp()),
        "extractable": any(_backing_artifact_is_extractable(session.provider_instance.provider, artifact) for artifact in backing_artifacts),
        "backing_artifact_count": len(backing_artifacts),
        "primary_backing_artifact": (
            _serialize_backing_artifact(session.provider_instance.provider, primary_backing_artifact)
            if primary_backing_artifact is not None
            else None
        ),
        "backing_artifacts": [
            _serialize_backing_artifact(session.provider_instance.provider, artifact)
            for artifact in backing_artifacts
        ],
        "native": native,
        "identity_hash": _session_identity_hash(
            provider=session.provider_instance.provider,
            provider_session_id=session.session_id,
        ),
    }


def _provider_instance_home(instance: ChatlasProviderInstance) -> str | None:
    if instance.agent.home is None:
        return None
    return str(instance.agent.home)


def _session_project_path(native: dict[str, object]) -> str | None:
    project_path = native.get("project_path")
    if isinstance(project_path, str) and project_path:
        return project_path
    cwd = native.get("cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    return None


def _session_uri(session: ChatlasDiscoveredSession) -> str:
    return (
        f"agentos://chat-session/{quote(session.provider_instance.provider, safe='')}/"
        f"{quote(session.provider_instance.fingerprint, safe='')}/"
        f"{quote(session.session_id, safe='')}"
    )


def _serialize_backing_artifact(provider: str, artifact: BackingArtifact) -> dict[str, Any]:
    return artifact.summary(
        extractable=_backing_artifact_is_extractable(provider, artifact),
    )


def _backing_artifact_is_extractable(provider: str, artifact: BackingArtifact) -> bool:
    if not artifact.path.is_file():
        return False
    if provider == "codex":
        return artifact.role == "transcript" and artifact.path.name.startswith("rollout-") and artifact.path.suffix == ".jsonl"
    if provider in _TRANSCRIPT_EXTRACTABLE_SUFFIXES:
        return artifact.role == "transcript" and artifact.path.suffix in _TRANSCRIPT_EXTRACTABLE_SUFFIXES[provider]
    if provider == "opencode":
        return artifact.role in {"session_diff", "sqlite_session_row"} and (
            artifact.path.suffix == ".json" or artifact.path.name == "opencode.db"
        )
    return False


def _upsert_session_index_partition(
    session_index_root: Path,
    *,
    instance: ChatlasProviderInstance,
    rows: list[dict[str, Any]],
) -> int:
    path = _session_index_partition_path(session_index_root, instance=instance)
    existing_rows = _load_jsonl_rows(path)
    row_by_session_id = {
        str(row.get("session_id")): row
        for row in existing_rows
        if isinstance(row.get("session_id"), str)
    }
    for row in rows:
        row_by_session_id[str(row["session_id"])] = row
    rendered = _render_session_index_rows(list(row_by_session_id.values()))
    write_text_if_changed(path, rendered)
    return len(rows)


def _replace_session_index_partition(
    session_index_root: Path,
    *,
    instance: ChatlasProviderInstance,
    rows: list[dict[str, Any]],
) -> int:
    path = _session_index_partition_path(session_index_root, instance=instance)
    rendered = _render_session_index_rows(rows)
    write_text_if_changed(path, rendered)
    return len(rows)


def _render_session_index_rows(rows: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(row, sort_keys=True) + "\n"
        for row in sorted(rows, key=lambda payload: str(payload.get("session_id", "")))
    )


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                rows.append(payload)
    except (OSError, json.JSONDecodeError):
        return []
    return rows


def _session_index_partition_path(session_index_root: Path, *, instance: ChatlasProviderInstance) -> Path:
    return session_index_root / instance.partition_key / "sessions.index.jsonl"


def _index_partition_count(
    session_index_root: Path,
    *,
    instance: ChatlasProviderInstance,
    rows: list[dict[str, Any]],
) -> int:
    if rows or _session_index_partition_path(session_index_root, instance=instance).exists():
        return 1
    return 0


def _load_derivation_cache_partition(
    cache_root: Path,
    *,
    instance: ChatlasProviderInstance,
) -> dict[str, dict[str, object]]:
    path = _derivation_cache_partition_path(cache_root, instance=instance)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return {}
    entries = payload.get("sessions")
    if not isinstance(entries, dict):
        return {}
    return {
        key: value
        for key, value in entries.items()
        if isinstance(key, str) and isinstance(value, dict)
    }


def _write_derivation_cache_partition(
    cache_root: Path,
    *,
    instance: ChatlasProviderInstance,
    entries: dict[str, dict[str, object]],
) -> None:
    path = _derivation_cache_partition_path(cache_root, instance=instance)
    payload = {
        "class": "agentos.chatlas.session_index_derivations",
        "schema_version": 1,
        "provider": instance.provider,
        "provider_instance_fingerprint": instance.fingerprint,
        "sessions": {
            key: entries[key]
            for key in sorted(entries)
        },
    }
    write_text_if_changed(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _derivation_cache_partition_path(cache_root: Path, *, instance: ChatlasProviderInstance) -> Path:
    return cache_root / instance.partition_key / "sessions.json"


def _raw_partition_manifest_path(raw_root: Path, *, instance: ChatlasProviderInstance) -> Path:
    return raw_root / instance.partition_key / "manifest.json"


def _load_raw_partition_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _raw_partition_manifest_home(raw_root: Path, *, instance: ChatlasProviderInstance) -> str | None:
    manifest = _load_raw_partition_manifest(_raw_partition_manifest_path(raw_root, instance=instance))
    if manifest is None:
        return None
    home = manifest.get("home")
    return home if isinstance(home, str) and home else None


def _raw_partition_manifest_payload(instance: ChatlasProviderInstance, *, raw_root: Path) -> dict[str, Any]:
    home = _provider_instance_home(instance)
    raw_home = instance.raw_home(raw_root)
    source_roots: list[dict[str, str]] = []
    if home is not None and raw_home is not None:
        source_roots.append(
            {
                "role": "home",
                "source_root": home,
                "raw_root": str(raw_home),
            }
        )
    return {
        "class": "agentos.chatlas.raw_partition_manifest",
        "schema_version": 1,
        "provider": instance.provider,
        "provider_instance_fingerprint": instance.fingerprint,
        "instance": instance.instance,
        "home": home,
        "raw_home": str(raw_home) if raw_home is not None else None,
        "home_source": "configured_agent_home" if home is not None else None,
        "source_roots": source_roots,
    }


def _create_raw_partition_manifest_if_missing(instance: ChatlasProviderInstance, *, raw_root: Path) -> None:
    path = _raw_partition_manifest_path(raw_root, instance=instance)
    if path.exists():
        return
    payload = _raw_partition_manifest_payload(instance, raw_root=raw_root)
    write_text_if_changed(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _path_metadata_signature(path: Path) -> dict[str, object]:
    signature: dict[str, object] = {"path": str(path)}
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
    elif stat.S_ISDIR(mode):
        signature["storage_kind"] = "directory"
    else:
        signature["storage_kind"] = "other"
    return signature


def _dedupe_sessions(sessions: list[ChatlasDiscoveredSession]) -> list[ChatlasDiscoveredSession]:
    deduped: dict[tuple[str, str, str], ChatlasDiscoveredSession] = {}
    for session in sessions:
        key = (
            session.provider_instance.provider,
            session.provider_instance.fingerprint,
            session.session_id,
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = session
            continue
        left_ref = existing.session_ref
        right_ref = session.session_ref
        if hasattr(left_ref, "merge"):
            merged_ref = left_ref.merge(right_ref)
        else:
            merged_ref = left_ref
        deduped[key] = ChatlasDiscoveredSession(
            provider_instance=existing.provider_instance,
            session_ref=merged_ref,
        )
    return sorted(
        deduped.values(),
        key=lambda session: (
            session.provider_instance.provider,
            session.provider_instance.fingerprint,
            session.session_id,
        ),
    )


def _provider_instance_summary(instance: ChatlasProviderInstance, *, raw_root: Path) -> dict[str, object]:
    return {
        "provider": instance.provider,
        "instance": instance.instance,
        "provider_instance_fingerprint": instance.fingerprint,
        "home": str(instance.agent.home) if instance.agent.home is not None else None,
        "partition": instance.partition_key,
        "raw_home": str(instance.raw_home(raw_root)) if instance.raw_home(raw_root) is not None else None,
    }


def _empty_report() -> dict[str, Any]:
    return deepcopy(_REPORT_TEMPLATE)


def _empty_raw_copy_report() -> dict[str, int]:
    return {
        key: int(value)
        for key, value in _REPORT_TEMPLATE["raw_copy"].items()
    }


def _merge_report(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("native_scan", "cache", "raw_copy", "session_index"):
        _merge_nested_counter(target[key], source[key])
    _merge_nested_float_counter(target["timing"], source["timing"], skip_keys={"elapsed_seconds"})


def _merge_nested_counter(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + int(value)


def _merge_nested_float_counter(
    target: dict[str, float],
    source: dict[str, float],
    *,
    skip_keys: set[str],
) -> None:
    for key, value in source.items():
        if key in skip_keys:
            continue
        target[key] = round(float(target.get(key, 0.0)) + float(value), 6)


def _report_stats_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "native_scan": report["native_scan"],
        "cache": report["cache"],
        "raw_copy": report["raw_copy"],
        "session_index": report["session_index"],
        "timing": report["timing"],
    }


def _emit_update_summary(progress: Callable[[str], None] | None, payload: dict[str, Any]) -> None:
    if progress is None:
        return
    _emit(progress, f"[chatlas] update summary: {_summary_counts(payload)}")
    instances = payload.get("instances")
    if not isinstance(instances, list):
        return
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        stats = instance.get("stats")
        if not isinstance(stats, dict):
            continue
        provider = instance.get("provider")
        name = instance.get("instance")
        home = instance.get("home")
        label = f"{provider}/{name}" if isinstance(provider, str) and isinstance(name, str) else "instance"
        if isinstance(home, str):
            label = f"{label} home={home}"
        _emit(progress, f"[chatlas] {label}: {_summary_counts(stats)}")


def _summary_counts(stats: dict[str, Any]) -> str:
    native_scan = _dict_value(stats, "native_scan")
    cache = _dict_value(stats, "cache")
    raw_copy = _dict_value(stats, "raw_copy")
    session_index = _dict_value(stats, "session_index")
    timing = _dict_value(stats, "timing")
    return (
        f"sessions={_int_value(native_scan, 'session_count')} "
        f"changed={_int_value(native_scan, 'changed_session_count')} "
        f"cached={_int_value(cache, 'hit_count')} "
        f"artifacts={_int_value(native_scan, 'source_artifact_count')} "
        f"cached_artifacts={_int_value(native_scan, 'cached_source_artifact_count')} "
        f"copied={_int_value(raw_copy, 'copied_file_count')} "
        f"indexed={_int_value(session_index, 'upserted_row_count')} "
        f"elapsed={_float_value(timing, 'elapsed_seconds'):.3f}s"
    )


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _int_value(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, int):
        return value
    return 0


def _float_value(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _elapsed_seconds(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 6)


def _path_component(value: str) -> str:
    return quote(value, safe="._-")


def _session_cache_key(session_id: str) -> str:
    return _path_component(session_id)


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


__all__ = [
    "CHATLAS_DIRNAME",
    "DEFAULT_CHATLAS_PHASE",
    "SESSION_INDEX_DERIVATIONS_CACHE_DIR",
    "SESSION_INDEX_ROOT",
    "default_chatlas_root",
    "run_chatlas_delta_scan",
]
