from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from shutil import move
import time

from agentos._core.errors import CliError
from agentos.agent.primitives import SessionSource
from agentos.chatlas._cache_io import write_text_if_changed
from agentos.chatlas._duration import parse_duration_seconds
from agentos.chatlas.provider_home_adapter import (
    ChatlasProviderInstance,
    ProviderHomeAdapter,
    provider_instance_home,
)
from agentos.chatlas.instance_selection import selected_provider_instances
from agentos.chatlas.paths import default_chatlas_root
from agentos.chatlas.raw_archive import _copied_source_path


GC_REPORT_CLASS = "agentos_chatlas.provider_gc_report"
GC_REPORT_SCHEMA_VERSION = 1
DEFAULT_OLDER_THAN = "30d"


@dataclass(frozen=True)
class _GcCandidate:
    provider: str
    instance: str
    provider_instance_fingerprint: str
    session_id: str
    role: str
    source_path: Path
    storage_kind: str
    archived_path: Path | None
    destination_path: Path
    mtime: float
    source_sha256: str | None
    archived_sha256: str | None


def chatlas_gc(
    *,
    providers: tuple[str, ...] | None,
    instances: tuple[str, ...] | None = None,
    session_ids: tuple[str, ...] = (),
    older_than: str = DEFAULT_OLDER_THAN,
    apply: bool = False,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    started_at = time.perf_counter()
    if providers is None:
        raise CliError("chatlas gc requires at least one --provider")
    cutoff_seconds = parse_duration_seconds(older_than, field_name="--older-than")
    cutoff_timestamp = time.time() - cutoff_seconds
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    raw_root = chatlas_root_path / "raw"
    gc_root = chatlas_root_path / "gc"
    instances_selected = _select_instances(
        providers=providers,
        instances=instances,
        start_path=start_path,
    )

    candidates: list[_GcCandidate] = []
    skipped: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    moved: list[dict[str, object]] = []
    session_filter = set(session_ids)
    scanned_source_count = 0
    scanned_session_count = 0
    instance_payloads: list[dict[str, object]] = []

    for instance in instances_selected:
        _emit(progress, f"[chatlas] {instance.provider}/{instance.instance}: gc scan")
        instance_sessions = ProviderHomeAdapter(instance).discover()
        instance_scanned_sessions = 0
        instance_candidates = 0
        instance_skipped = 0
        for session in instance_sessions:
            if session_filter and session.session_id not in session_filter:
                continue
            scanned_session_count += 1
            instance_scanned_sessions += 1
            sources = session.sources()
            scanned_source_count += len(sources)
            session_candidates, session_skipped = _candidates_for_session(
                instance=instance,
                session_id=session.session_id,
                sources=sources,
                raw_root=raw_root,
                gc_root=gc_root,
                cutoff_timestamp=cutoff_timestamp,
            )
            candidates.extend(session_candidates)
            skipped.extend(session_skipped)
            instance_candidates += len(session_candidates)
            instance_skipped += len(session_skipped)
        instance_payloads.append(
            {
                **_instance_summary(instance),
                "scanned_session_count": instance_scanned_sessions,
                "candidate_count": instance_candidates,
                "skipped_count": instance_skipped,
            }
        )

    if apply:
        _ensure_gc_gitignore(chatlas_root_path)
        for candidate in candidates:
            try:
                moved.append(_move_candidate(candidate))
            except OSError as exc:
                failures.append({
                    **_candidate_payload(candidate),
                    "reason": "move_failed",
                    "error": str(exc),
                })

    payload: dict[str, object] = {
        "status": "ok" if not failures else "partial",
        "class": GC_REPORT_CLASS,
        "schema_version": GC_REPORT_SCHEMA_VERSION,
        "command": "chatlas gc",
        "chatlas_root": str(chatlas_root_path),
        "raw_root": str(raw_root),
        "gc_root": str(gc_root),
        "selection": {
            "providers": list(providers),
            "instances": list(instances) if instances is not None else None,
            "session_ids": list(session_ids),
        },
        "older_than": older_than,
        "cutoff_timestamp": datetime.fromtimestamp(cutoff_timestamp, timezone.utc).isoformat(),
        "apply": apply,
        "instances": instance_payloads,
        "counts": {
            "instance_count": len(instances_selected),
            "scanned_session_count": scanned_session_count,
            "scanned_source_count": scanned_source_count,
            "candidate_count": len(candidates),
            "skipped_count": len(skipped),
            "moved_count": len(moved),
            "failure_count": len(failures),
        },
        "candidates": [_candidate_payload(candidate) for candidate in candidates],
        "moved": moved,
        "skipped": skipped,
        "failures": failures,
        "timing": {
            "elapsed_seconds": round(time.perf_counter() - started_at, 6),
        },
    }
    if apply:
        report_path = _write_gc_report(chatlas_root_path, payload)
        payload["report_path"] = str(report_path)
    _emit(
        progress,
        f"[chatlas] gc: candidates={len(candidates)} moved={len(moved)} skipped={len(skipped)} failures={len(failures)}",
    )
    return payload


def _select_instances(
    *,
    providers: tuple[str, ...],
    instances: tuple[str, ...] | None,
    start_path: Path | str,
) -> tuple[ChatlasProviderInstance, ...]:
    selected = selected_provider_instances(providers=providers, start_path=start_path)
    if instances is not None:
        wanted = set(instances)
        selected = tuple(
            inst for inst in selected
            if inst.agent.profile_id in wanted or inst.instance in wanted
        )
    if not selected:
        raise CliError(
            f"no configured instances match providers={list(providers)!r}"
            + (f" instances={list(instances)}" if instances else "")
        )
    return selected


def _candidates_for_session(
    *,
    instance: ChatlasProviderInstance,
    session_id: str,
    sources: tuple[SessionSource, ...],
    raw_root: Path,
    gc_root: Path,
    cutoff_timestamp: float,
) -> tuple[list[_GcCandidate], list[dict[str, object]]]:
    candidates: list[_GcCandidate] = []
    skipped: list[dict[str, object]] = []
    for source in sources:
        if source.normalized_storage_kind() == "directory":
            continue
        result = _candidate_for_file_source(
            instance=instance,
            session_id=session_id,
            source=source,
            raw_root=raw_root,
            gc_root=gc_root,
            cutoff_timestamp=cutoff_timestamp,
        )
        if isinstance(result, _GcCandidate):
            candidates.append(result)
        else:
            skipped.append(result)
    if not candidates:
        return candidates, skipped

    for source in sources:
        if source.normalized_storage_kind() != "directory":
            continue
        result = _candidate_for_directory_source(
            instance=instance,
            session_id=session_id,
            source=source,
            gc_root=gc_root,
        )
        if isinstance(result, _GcCandidate):
            candidates = [
                candidate
                for candidate in candidates
                if not _is_relative_to(candidate.source_path, result.source_path)
            ]
            candidates.append(result)
        else:
            skipped.append(result)
    return candidates, skipped


def _candidate_for_file_source(
    *,
    instance: ChatlasProviderInstance,
    session_id: str,
    source: SessionSource,
    raw_root: Path,
    gc_root: Path,
    cutoff_timestamp: float,
) -> _GcCandidate | dict[str, object]:
    source_path = source.path.expanduser()
    base_payload = _source_payload(
        instance=instance,
        session_id=session_id,
        source=source,
        source_path=source_path,
    )
    if source.locator is not None:
        return {**base_payload, "reason": "locator_source"}
    if source.normalized_storage_kind() != "file":
        return {**base_payload, "reason": "unsupported_storage_kind"}
    if instance.agent.home is None:
        return {**base_payload, "reason": "missing_provider_home"}
    if not source_path.is_file():
        return {**base_payload, "reason": "source_missing"}
    try:
        source_mtime = source_path.stat().st_mtime
    except OSError as exc:
        return {**base_payload, "reason": "source_stat_failed", "error": str(exc)}
    if source_mtime > cutoff_timestamp:
        return {**base_payload, "reason": "recent"}
    try:
        relative = source_path.resolve().relative_to(instance.agent.home.resolve())
    except ValueError:
        return {**base_payload, "reason": "outside_provider_home"}
    archived_path = _copied_source_path(instance, raw_root=raw_root, source_path=source_path)
    if not archived_path.is_file():
        return {
            **base_payload,
            "reason": "archive_missing",
            "archived_path": str(archived_path),
        }
    try:
        source_hash = _sha256_file(source_path)
        archived_hash = _sha256_file(archived_path)
    except OSError as exc:
        return {
            **base_payload,
            "reason": "hash_failed",
            "archived_path": str(archived_path),
            "error": str(exc),
        }
    if source_hash != archived_hash:
        return {
            **base_payload,
            "reason": "hash_mismatch",
            "archived_path": str(archived_path),
            "source_sha256": source_hash,
            "archived_sha256": archived_hash,
        }
    destination_path = (
        gc_root
        / "provider-home"
        / instance.provider
        / instance.fingerprint
        / "home"
        / relative
    )
    return _GcCandidate(
        provider=instance.provider,
        instance=instance.instance,
        provider_instance_fingerprint=instance.fingerprint,
        session_id=session_id,
        role=source.role,
        source_path=source_path,
        storage_kind=source.normalized_storage_kind(),
        archived_path=archived_path,
        destination_path=destination_path,
        mtime=source_mtime,
        source_sha256=source_hash,
        archived_sha256=archived_hash,
    )


def _candidate_for_directory_source(
    *,
    instance: ChatlasProviderInstance,
    session_id: str,
    source: SessionSource,
    gc_root: Path,
) -> _GcCandidate | dict[str, object]:
    source_path = source.path.expanduser()
    base_payload = _source_payload(
        instance=instance,
        session_id=session_id,
        source=source,
        source_path=source_path,
    )
    if source.locator is not None:
        return {**base_payload, "reason": "locator_source"}
    if instance.agent.home is None:
        return {**base_payload, "reason": "missing_provider_home"}
    if not source_path.is_dir():
        return {**base_payload, "reason": "source_missing"}
    try:
        source_mtime = source_path.stat().st_mtime
        relative = source_path.resolve().relative_to(instance.agent.home.resolve())
    except OSError as exc:
        return {**base_payload, "reason": "source_stat_failed", "error": str(exc)}
    except ValueError:
        return {**base_payload, "reason": "outside_provider_home"}
    destination_path = (
        gc_root
        / "provider-home"
        / instance.provider
        / instance.fingerprint
        / "home"
        / relative
    )
    return _GcCandidate(
        provider=instance.provider,
        instance=instance.instance,
        provider_instance_fingerprint=instance.fingerprint,
        session_id=session_id,
        role=source.role,
        source_path=source_path,
        storage_kind=source.normalized_storage_kind(),
        archived_path=None,
        destination_path=destination_path,
        mtime=source_mtime,
        source_sha256=None,
        archived_sha256=None,
    )


def _source_payload(
    *,
    instance: ChatlasProviderInstance,
    session_id: str,
    source: SessionSource,
    source_path: Path,
) -> dict[str, object]:
    return {
        "provider": instance.provider,
        "instance": instance.instance,
        "provider_instance_fingerprint": instance.fingerprint,
        "session_id": session_id,
        "role": source.role,
        "storage_kind": source.normalized_storage_kind(),
        "source_path": str(source_path),
    }


def _candidate_payload(candidate: _GcCandidate) -> dict[str, object]:
    return {
        "provider": candidate.provider,
        "instance": candidate.instance,
        "provider_instance_fingerprint": candidate.provider_instance_fingerprint,
        "session_id": candidate.session_id,
        "role": candidate.role,
        "storage_kind": candidate.storage_kind,
        "source_path": str(candidate.source_path),
        "archived_path": str(candidate.archived_path) if candidate.archived_path is not None else None,
        "destination_path": str(candidate.destination_path),
        "mtime": datetime.fromtimestamp(candidate.mtime, timezone.utc).isoformat(),
        "source_sha256": candidate.source_sha256,
        "archived_sha256": candidate.archived_sha256,
    }


def _move_candidate(candidate: _GcCandidate) -> dict[str, object]:
    candidate.destination_path.parent.mkdir(parents=True, exist_ok=True)
    if candidate.destination_path.exists():
        if candidate.destination_path.is_dir():
            from shutil import rmtree

            rmtree(candidate.destination_path)
        else:
            candidate.destination_path.unlink()
    move(str(candidate.source_path), str(candidate.destination_path))
    return _candidate_payload(candidate)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _ensure_gc_gitignore(chatlas_root: Path) -> None:
    gitignore_path = chatlas_root / ".gitignore"
    existing = ""
    if gitignore_path.is_file():
        existing = gitignore_path.read_text(encoding="utf-8")
    lines = existing.splitlines()
    if "/gc/" not in lines:
        lines.append("/gc/")
    text = "\n".join(lines).rstrip() + "\n"
    write_text_if_changed(gitignore_path, text)


def _write_gc_report(chatlas_root: Path, payload: dict[str, object]) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = chatlas_root / "manifests" / "gc" / f"{timestamp}.json"
    write_text_if_changed(report_path, json.dumps(payload, sort_keys=True, indent=2) + "\n")
    return report_path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _instance_summary(instance: ChatlasProviderInstance) -> dict[str, object]:
    return {
        "provider": instance.provider,
        "instance": instance.instance,
        "fingerprint": instance.fingerprint,
        "home": provider_instance_home(instance),
    }


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


__all__ = ["DEFAULT_OLDER_THAN", "chatlas_gc"]
