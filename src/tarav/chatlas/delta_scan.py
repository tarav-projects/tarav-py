from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
from shutil import rmtree
import time
from typing import Any, Callable

from tarav.agent.primitives import AgentConfig, SessionSource
from tarav.agent.providers.registry import agent_from_config
from tarav.agent.sessions import _format_stats_timestamp
from tarav.chatlas._cache_io import write_text_if_changed
from tarav.chatlas.config import cold_session_cutoff_seconds_for_provider
from tarav.chatlas.paths import (
    SESSION_INDEX_DERIVATIONS_CACHE_DIR,
    SESSION_INDEX_ROOT,
    default_chatlas_root,
)
from tarav.chatlas.provider_home_adapter import (
    ChatlasDeltaSession,
    ChatlasDiscoveredSession,
    ChatlasProviderInstance,
    ProviderHomeAdapter,
    provider_instance_home,
)
from tarav.chatlas.raw_archive import (
    _copied_paths_for_sources,
    _create_raw_partition_manifest_if_missing as _raw_create_manifest_if_missing,
    _raw_partition_manifest_home,
)
from tarav.chatlas.index_writer import (
    _index_partition_count,
    _replace_session_index_rows,
    _session_index_row,
    _upsert_session_index_rows,
)
from tarav.chatlas.index_store import clear_session_index_provider


def _copy_delta_session_sources(delta_session, *, raw_root):
    return ProviderHomeAdapter(delta_session.session.provider_instance).archive(
        delta_session,
        raw_root=raw_root,
        empty_report=_empty_raw_copy_report(),
    )


def _create_raw_partition_manifest_if_missing(instance, *, raw_root):
    _raw_create_manifest_if_missing(
        instance,
        raw_root=raw_root,
        provider_instance_home=provider_instance_home(instance),
    )

DEFAULT_CHATLAS_PHASE = "index-only"
_SESSION_SUMMARY_EXCERPT_CHAR_LIMIT = 240

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
        "cold_skip_count": 0,
        "cold_marked_count": 0,
        "full_scan_count": 0,
        "window_skip_count": 0,
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

@dataclass(frozen=True)
class ScanScope:
    """`Scan.Scope` — the selection an update run hands the scan: which
    sessions the pipeline considers. Scope picks the candidates; cold-cache
    trust and `full_scan` are comparison policies orthogonal to it."""

    providers: tuple[str, ...] | None = None
    instances: tuple[str, ...] | None = None
    session_ids: tuple[str, ...] = ()
    window_seconds: int | None = None


def chatlas_delta_scan(
    *,
    scope: ScanScope,
    chatlas_root: Path | None,
    start_path: Path | str,
    cache_enabled: bool,
    full_scan: bool = False,
    command_name: str = "chatlas index update",
    progress: Callable[[str], None] | None,
) -> dict[str, object]:
    started_at = time.perf_counter()
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    raw_root = chatlas_root_path / "raw"
    session_index_root = chatlas_root_path / SESSION_INDEX_ROOT
    cache_root = chatlas_root_path / SESSION_INDEX_DERIVATIONS_CACHE_DIR
    from tarav.chatlas.instance_selection import selected_provider_instances
    selected_instances = selected_provider_instances(
        providers=scope.providers,
        start_path=start_path,
    )
    if scope.instances is not None:
        wanted = set(scope.instances)
        selected_instances = tuple(
            instance for instance in selected_instances
            if instance.agent.profile_id in wanted or instance.instance in wanted
        )
    if scope.session_ids:
        selected_instances = _narrow_instances_to_indexed_sessions(
            selected_instances,
            session_ids=scope.session_ids,
            chatlas_root=chatlas_root_path,
        )

    report = _empty_report()
    report["provider_count"] = len({instance.provider for instance in selected_instances})
    report["instance_count"] = len(selected_instances)
    selected_payload = {
        "providers": list(scope.providers) if scope.providers is not None else None,
        "session_ids": list(scope.session_ids),
        "instances": [
            _provider_instance_summary(instance, raw_root=raw_root)
            for instance in selected_instances
        ],
    }
    instance_payloads: list[dict[str, Any]] = []

    for instance in selected_instances:
        cold_session_cutoff_seconds = cold_session_cutoff_seconds_for_provider(
            instance.provider,
            start_path=start_path,
        )
        _emit(progress, f"[chatlas] {_provider_instance_progress_label(instance)}: native scan")
        instance_report = _process_provider_instance(
            instance=instance,
            raw_root=raw_root,
            session_index_root=session_index_root,
            cache_root=cache_root,
            cache_enabled=cache_enabled,
            cold_session_cutoff_seconds=cold_session_cutoff_seconds,
            full_scan=full_scan,
            window_seconds=scope.window_seconds,
            session_ids=scope.session_ids,
            progress=progress,
        )
        _merge_report(report, instance_report)
        instance_payloads.append(
            {
                **_provider_instance_summary(instance, raw_root=raw_root),
                "cold_session_cutoff_seconds": cold_session_cutoff_seconds,
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
        "full_scan_enabled": full_scan,
        "window_seconds": scope.window_seconds,
        **report,
    }
    _emit_update_summary(progress, payload)
    return payload


def chatlas_index_reset(
    *,
    chatlas_root: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
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
    return payload


def chatlas_index_redo(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    started_at = time.perf_counter()
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    raw_root = chatlas_root_path / "raw"
    session_index_root = chatlas_root_path / SESSION_INDEX_ROOT
    from tarav.chatlas.instance_selection import archived_provider_instances
    selected_instances = archived_provider_instances(raw_root=raw_root, providers=providers)
    _reset_session_index_for_redo(session_index_root, providers=providers)

    report = _empty_report()
    report["provider_count"] = len({instance.provider for instance in selected_instances})
    report["instance_count"] = len(selected_instances)
    instance_payloads: list[dict[str, Any]] = []

    redo_rows: list[dict[str, Any]] = []
    for instance in selected_instances:
        _emit(progress, f"[chatlas] {_provider_instance_progress_label(instance)}: raw index redo")
        instance_report, instance_rows = _redo_provider_instance_index(
            instance=instance,
            raw_root=raw_root,
            progress=progress,
        )
        redo_rows.extend(instance_rows)
        _merge_report(report, instance_report)
        instance_payloads.append(
            {
                **_provider_instance_summary(instance, raw_root=raw_root),
                "stats": _report_stats_payload(instance_report),
            }
        )
    if redo_rows:
        written = _replace_session_index_rows(session_index_root, rows=redo_rows)
        report["session_index"]["upserted_row_count"] = written
        report["session_index"]["partition_count"] = _index_partition_count(rows=redo_rows)

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
    return payload


def _process_provider_instance(
    *,
    instance: ChatlasProviderInstance,
    raw_root: Path,
    session_index_root: Path,
    cache_root: Path,
    cache_enabled: bool,
    cold_session_cutoff_seconds: int,
    full_scan: bool,
    window_seconds: int | None = None,
    session_ids: tuple[str, ...] = (),
    progress: Callable[[str], None] | None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    report = _empty_report()
    discovery_started_at = time.perf_counter()
    adapter = ProviderHomeAdapter(instance)
    if session_ids:


        native_sessions = [
            session
            for session_id in session_ids
            if (session := adapter.find_session(session_id)) is not None
        ]
    else:
        native_sessions = adapter.discover()
    report["timing"]["native_scan_seconds"] += _elapsed_seconds(discovery_started_at)
    report["native_scan"]["session_count"] = len(native_sessions)
    _create_raw_partition_manifest_if_missing(instance, raw_root=raw_root)

    cache_compare_started_at = time.perf_counter()
    old_cache = _load_derivation_cache_partition(cache_root, instance=instance) if cache_enabled else {}


    next_cache: dict[str, dict[str, object]] = dict(old_cache) if session_ids else {}
    delta_sessions: list[ChatlasDeltaSession] = []

    for session in native_sessions:
        cached_signature = old_cache.get(session.cache_key)
        if window_seconds is not None and not _session_within_window(session, window_seconds):
            if cached_signature is not None:
                next_cache[session.cache_key] = cached_signature
            report["cache"]["window_skip_count"] += 1
            report["native_scan"]["unchanged_session_count"] += 1
            continue
        if cache_enabled and not full_scan and _is_cold_cache_entry(cached_signature):
            next_cache[session.cache_key] = cached_signature
            report["cache"]["hit_count"] += 1
            report["cache"]["cold_skip_count"] += 1
            report["native_scan"]["unchanged_session_count"] += 1
            continue
        if full_scan and _is_cold_cache_entry(cached_signature):
            report["cache"]["full_scan_count"] += 1
        sources = session.sources()
        source_count = len(sources)
        report["native_scan"]["source_artifact_count"] += source_count
        signature = _native_derivation_signature(
            session,
            sources=sources,
            cached_signature=cached_signature,
            cold_session_cutoff_seconds=cold_session_cutoff_seconds,
        )
        next_cache[session.cache_key] = signature
        if _is_cold_cache_entry(signature) and not _is_cold_cache_entry(cached_signature):
            report["cache"]["cold_marked_count"] += 1
        if cache_enabled and _derivation_signatures_match(cached_signature, signature):
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
    upserted = _upsert_session_index_rows(
        session_index_root,
        rows=indexed_rows,
    )
    report["session_index"]["delta_session_count"] = len(delta_sessions)
    report["session_index"]["derived_row_count"] = len(indexed_rows)
    report["session_index"]["upserted_row_count"] = upserted
    report["session_index"]["partition_count"] = _index_partition_count(
        rows=indexed_rows,
    )
    report["raw_copy"]["copied_session_count"] = len(copied_session_ids)
    report["timing"]["index_seconds"] += _elapsed_seconds(index_started_at)
    report["timing"]["elapsed_seconds"] = _elapsed_seconds(started_at)
    _emit(
        progress,
        f"[chatlas] {_provider_instance_progress_label(instance)}: indexed {len(indexed_rows)} delta sessions",
    )
    return report


def _narrow_instances_to_indexed_sessions(
    selected_instances: tuple[ChatlasProviderInstance, ...],
    *,
    session_ids: tuple[str, ...],
    chatlas_root: Path,
) -> tuple[ChatlasProviderInstance, ...]:
    """Depot-side pre-filter for session scopes: when the index already knows
    a session, only its provider instance needs a scoped scan. Unknown
    sessions keep the whole pool (adapter discovery decides)."""
    from tarav.chatlas.index_store import load_chatlas_session_index_rows

    try:
        index = load_chatlas_session_index_rows(chatlas_root=chatlas_root)
    except Exception:
        return selected_instances
    wanted_ids = set(session_ids)
    covered_ids: set[str] = set()
    wanted_partitions: set[tuple[str, str]] = set()
    for row in index.rows:
        session_id = row.get("session_id")
        provider = row.get("provider")
        fingerprint = row.get("provider_instance_fingerprint")
        if session_id in wanted_ids and isinstance(provider, str) and isinstance(fingerprint, str):
            covered_ids.add(session_id)
            wanted_partitions.add((provider, fingerprint))
    if covered_ids != wanted_ids:
        return selected_instances
    narrowed = tuple(
        instance
        for instance in selected_instances
        if (instance.provider, instance.fingerprint) in wanted_partitions
    )
    return narrowed or selected_instances


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
        clear_session_index_provider(session_index_root, provider=provider)


def _redo_provider_instance_index(
    *,
    instance: ChatlasProviderInstance,
    raw_root: Path,
    progress: Callable[[str], None] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started_at = time.perf_counter()
    report = _empty_report()
    discovery_started_at = time.perf_counter()
    sessions = ProviderHomeAdapter(instance).discover()
    report["timing"]["native_scan_seconds"] += _elapsed_seconds(discovery_started_at)
    report["native_scan"]["session_count"] = len(sessions)
    report["native_scan"]["changed_session_count"] = len(sessions)
    for session in sessions:
        source_count = len(session.sources())
        report["native_scan"]["source_artifact_count"] += source_count
        report["native_scan"]["changed_source_artifact_count"] += source_count

    index_started_at = time.perf_counter()
    manifest_home = _raw_partition_manifest_home(raw_root, instance=instance)
    rows = [
        _session_index_row(
            session,
            provider_home=manifest_home,
        )
        for session in sessions
    ]
    report["session_index"]["delta_session_count"] = len(sessions)
    report["session_index"]["derived_row_count"] = len(rows)
    report["session_index"]["upserted_row_count"] = len(rows)
    report["session_index"]["partition_count"] = _index_partition_count(
        rows=rows,
    )
    report["timing"]["index_seconds"] += _elapsed_seconds(index_started_at)
    report["timing"]["elapsed_seconds"] = _elapsed_seconds(started_at)
    _emit(
        progress,
        f"[chatlas] {_provider_instance_progress_label(instance)}: redid {len(rows)} indexed sessions",
    )
    return report, rows


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
    if archived_agent is None:
        return []
    delta_session_ids = {delta_session.session_id for delta_session in delta_sessions}
    archived_instance = ChatlasProviderInstance(agent=archived_agent, fingerprint=instance.fingerprint)


    archived_sessions = [
        session
        for session in ProviderHomeAdapter(archived_instance).discover()
        if session.session_id in delta_session_ids
    ]
    return [
        _session_index_row(
            session,
            provider_home=provider_instance_home(instance),
        )
        for session in archived_sessions
    ]


def _archived_provider_agent(
    instance: ChatlasProviderInstance,
    *,
    raw_root: Path,
    delta_sessions: tuple[ChatlasDeltaSession, ...],
) -> AgentConfig | None:
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
            profile_id=instance.agent.profile_id,
            label=instance.agent.label,
            home=raw_home,
            direct_targets=direct_targets,
            sqlite_db_paths=sqlite_db_paths,
            is_default=instance.agent.is_default,
            fingerprint_override=instance.fingerprint,
        )
    )


def _native_derivation_signature(
    session: ChatlasDiscoveredSession,
    *,
    sources: tuple[SessionSource, ...],
    cold_session_cutoff_seconds: int,
    cached_signature: dict[str, object] | None = None,
) -> dict[str, object]:
    timestamp = session.session_ref.sort_timestamp()
    signature: dict[str, object] = {
        "class": "agentos_chatlas.session_index_derivation",
        "schema_version": 1,
        "provider": session.provider_instance.provider,
        "provider_instance_fingerprint": session.provider_instance.fingerprint,
        "home": provider_instance_home(session.provider_instance),
        "session_id": session.session_id,
        "display_name": session.session_ref.display_name(),
        "display_name_field": session.session_ref.display_name_field(),
        "last_activity_at": _format_stats_timestamp(timestamp),
        "native": dict(session.session_ref.native_ref_metadata()),
        "sources": [
            ProviderHomeAdapter(session.provider_instance).source_signature(source)
            for source in sources
        ],
    }
    if _session_is_cold(timestamp, cold_session_cutoff_seconds=cold_session_cutoff_seconds):
        signature["scan_state"] = "cold"
        existing_cold_since = (
            cached_signature.get("cold_since")
            if _is_cold_cache_entry(cached_signature)
            else None
        )
        signature["cold_since"] = existing_cold_since if isinstance(existing_cold_since, str) else _format_stats_timestamp(time.time())
    return signature


def _session_within_window(session: ChatlasDiscoveredSession, window_seconds: int) -> bool:
    timestamp = session.session_ref.sort_timestamp()
    if timestamp is None:
        return False
    return timestamp >= time.time() - window_seconds


def _session_is_cold(timestamp: float | None, *, cold_session_cutoff_seconds: int) -> bool:
    if timestamp is None:
        return False
    return timestamp < time.time() - cold_session_cutoff_seconds


def _is_cold_cache_entry(entry: dict[str, object] | None) -> bool:
    return isinstance(entry, dict) and entry.get("scan_state") == "cold"


def _derivation_signatures_match(
    cached_signature: dict[str, object] | None,
    signature: dict[str, object],
) -> bool:
    if cached_signature is None:
        return False
    return _cache_comparison_signature(cached_signature) == _cache_comparison_signature(signature)


def _cache_comparison_signature(signature: dict[str, object]) -> dict[str, object]:
    comparable = dict(signature)
    comparable.pop("scan_state", None)
    comparable.pop("cold_since", None)
    return comparable


def _provider_instance_progress_label(instance: ChatlasProviderInstance) -> str:
    home = provider_instance_home(instance)
    if home is not None:
        return f"{instance.provider} {_compact_home_path(home)}"
    return f"{instance.provider}/{instance.instance}"


def _compact_home_path(path: str) -> str:
    expanded = Path(os.path.expanduser(path))
    try:
        return str(Path("~") / expanded.relative_to(Path.home()))
    except ValueError:
        return str(expanded)


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
        "class": "agentos_chatlas.session_index_derivations",
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


def _provider_instance_summary(instance: ChatlasProviderInstance, *, raw_root: Path) -> dict[str, object]:
    return {
        "provider": instance.provider,
        "instance": instance.instance,
        "provider_instance_fingerprint": instance.fingerprint,
        "home": provider_instance_home(instance),
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
    instances = payload.get("instances")
    if isinstance(instances, list):
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            stats = instance.get("stats")
            if not isinstance(stats, dict):
                continue
            provider = instance.get("provider")
            name = instance.get("instance")
            home = instance.get("home")
            if isinstance(provider, str) and isinstance(home, str):
                label = f"{provider} {_compact_home_path(home)}"
            elif isinstance(provider, str) and isinstance(name, str):
                label = f"{provider}/{name}"
            else:
                label = "instance"
            _emit(progress, _format_update_summary(label=label, stats=stats))
    _emit(progress, _format_update_summary(label="update complete", stats=payload))


def _format_update_summary(*, label: str, stats: dict[str, Any]) -> str:
    native_scan = _dict_value(stats, "native_scan")
    cache = _dict_value(stats, "cache")
    raw_copy = _dict_value(stats, "raw_copy")
    session_index = _dict_value(stats, "session_index")
    timing = _dict_value(stats, "timing")
    return "\n".join(
        (
            f"[chatlas] {label}",
            (
                "  sessions   "
                f"total {_format_int(_int_value(native_scan, 'session_count'))}  "
                f"changed {_format_int(_int_value(native_scan, 'changed_session_count'))}  "
                f"cached {_format_int(_int_value(cache, 'hit_count'))}  "
                f"cold-skip {_format_int(_int_value(cache, 'cold_skip_count'))}"
            ),
            (
                "  artifacts  "
                f"total {_format_int(_int_value(native_scan, 'source_artifact_count'))}  "
                f"cached {_format_int(_int_value(native_scan, 'cached_source_artifact_count'))}  "
                f"copied {_format_int(_int_value(raw_copy, 'copied_file_count'))}"
            ),
            (
                "  index      "
                f"delta {_format_int(_int_value(session_index, 'delta_session_count'))}  "
                f"rows {_format_int(_int_value(session_index, 'derived_row_count'))}  "
                f"upserted {_format_int(_int_value(session_index, 'upserted_row_count'))}"
            ),
            (
                "  time       "
                f"total {_float_value(timing, 'elapsed_seconds'):.3f}s  "
                f"scan {_float_value(timing, 'native_scan_seconds'):.3f}s  "
                f"compare {_float_value(timing, 'cache_compare_seconds'):.3f}s  "
                f"copy {_float_value(timing, 'raw_copy_seconds'):.3f}s  "
                f"index {_float_value(timing, 'index_seconds'):.3f}s"
            ),
        )
    )


def _format_int(value: int) -> str:
    return f"{value:,}"


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


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


__all__ = [
    "DEFAULT_CHATLAS_PHASE",
    "ScanScope",
    "chatlas_delta_scan",
    "chatlas_index_redo",
    "chatlas_index_reset",
]
