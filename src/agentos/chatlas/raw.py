from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import fnmatch
import os
import shutil
import tempfile
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from agentos._core.errors import CliError
from agentos._core.sequences import _unique_strings
from agentos._core.path_validation import validate_string_for_path
from agentos._core.scan import normalize_rel
from agentos.chat.providers import (
    canonical_chat_provider_specs,
    ProviderHomeSlot,
    ProviderInstance,
    ProviderInstanceAnchor,
    canonical_chat_provider_spec_for_name,
)
from agentos.chatlas._cache_io import load_chatlas_cache_section, write_chatlas_cache_section

_CHATLAS_RAW_SCAN_CACHE_RELATIVE_PATH = Path("cache") / "raw-scan-v1.json"
_CHATLAS_RAW_DETECTION_BATCH_SIZE = 512
_CHATLAS_RAW_DETECTION_MIN_FILES = 1024
_CHATLAS_RAW_DETECTION_MAX_WORKERS = 4
_CHATLAS_RAW_DETECTION_IN_FLIGHT_MULTIPLIER = 2


ChatlasRawScanCacheEntry = dict[str, int]
ChatlasRawScanCacheHome = dict[str, ChatlasRawScanCacheEntry]
ChatlasRawScanCache = dict[str, ChatlasRawScanCacheHome]


@dataclass(frozen=True)
class ChatlasProviderHandler:
    family: str
    home_slots: tuple[ProviderHomeSlot, ...]
    default_excludes: tuple[str, ...] = ()
    default_includes: tuple[str, ...] = ()

    def supported_home_keys(self) -> tuple[str, ...]:
        return tuple(slot.key for slot in self.home_slots)

    def instance_from_home(
        self,
        home: str,
        *,
        field_prefix: str,
        index: int | None,
        is_default: bool,
        instance_name: str | None,
        includes: tuple[str, ...],
        excludes: tuple[str, ...],
    ) -> ProviderInstance:
        if len(self.home_slots) != 1:
            field_name = _provider_instance_field_name(field_prefix=field_prefix, index=index, field="home")
            homes_field_name = _provider_instance_field_name(field_prefix=field_prefix, index=index, field="homes")
            supported_keys = ", ".join(self.supported_home_keys())
            raise CliError(
                f"{field_name} is only supported for providers with a single home root; "
                f"use {homes_field_name} with keys: {supported_keys}"
            )
        slot = self.home_slots[0]
        return self.instance_from_homes(
            {slot.key: home},
            field_prefix=field_prefix,
            index=index,
            is_default=is_default,
            instance_name=instance_name,
            includes=includes,
            excludes=excludes,
        )

    def instance_from_homes(
        self,
        homes: dict[str, str],
        *,
        field_prefix: str,
        index: int | None,
        is_default: bool,
        instance_name: str | None,
        includes: tuple[str, ...],
        excludes: tuple[str, ...],
    ) -> ProviderInstance:
        supported_slots = {slot.key: slot for slot in self.home_slots}
        unsupported_keys = sorted(key for key in homes if key not in supported_slots)
        homes_field_name = _provider_instance_field_name(field_prefix=field_prefix, index=index, field="homes")
        if unsupported_keys:
            supported_keys = ", ".join(self.supported_home_keys())
            unsupported_text = ", ".join(unsupported_keys)
            raise CliError(
                f"{homes_field_name} contains unsupported keys for provider {self.family}: "
                f"{unsupported_text} (supported: {supported_keys})"
            )

        normalized_homes: list[tuple[str, Path]] = []
        for slot in self.home_slots:
            raw_home = homes.get(slot.key)
            if raw_home is None:
                continue
            normalized_home = Path(
                _normalize_chatlas_home(
                    raw_home,
                    field_name=f"{homes_field_name}.{slot.key}",
                )
            ).expanduser().resolve()
            normalized_homes.append((slot.key, normalized_home))

        if not normalized_homes:
            supported_keys = ", ".join(self.supported_home_keys())
            raise CliError(
                f"{homes_field_name} must include at least one supported home key: {supported_keys}"
            )

        resolved_instance_name: str | None = None
        if instance_name is not None:
            field_name = _provider_instance_field_name(field_prefix=field_prefix, index=index, field="instance")
            resolved_instance_name = validate_string_for_path(instance_name, field_name=field_name)

        anchors = tuple(
            ProviderInstanceAnchor(role="home", path=home_path, slot=home_key)
            for home_key, home_path in normalized_homes
        )

        return ProviderInstance(
            family=self.family,
            instance_id=resolved_instance_name,
            homes=tuple(normalized_homes),
            includes=_unique_strings(self.default_includes + includes),
            excludes=_unique_strings(self.default_excludes + excludes),
            anchors=anchors,
            is_default=is_default,
        )


@dataclass(frozen=True)
class ChatlasProviderContext:
    provider_handler: ChatlasProviderHandler
    provider_instance: ProviderInstance
    resolved_instance_name: str
    effective_includes: tuple[str, ...]
    effective_excludes: tuple[str, ...]

    def destination_root(self, raw_root: Path) -> Path:
        homes = self.provider_instance.homes
        if len(homes) != 1:
            return raw_root
        _, home_path = homes[0]
        return _chatlas_home_destination(
            raw_root=raw_root,
            home_path=home_path,
        )

    def summary(self, raw_root: Path) -> dict[str, Any]:
        destination_roots = {
            key: str(
                _chatlas_home_destination(
                    raw_root=raw_root,
                    home_path=home_path,
                )
            )
            for key, home_path in self.provider_instance.homes
        }
        return {
            "provider": self.provider_instance.family,
            "instance": self.resolved_instance_name,
            "is_default": self.provider_instance.is_default,
            "homes": {key: str(path) for key, path in self.provider_instance.homes},
            "includes": list(self.effective_includes),
            "excludes": list(self.effective_excludes),
            "destination_root": str(self.destination_root(raw_root)) if len(self.provider_instance.homes) == 1 else None,
            "destination_roots": destination_roots,
        }


@dataclass(frozen=True)
class ChatlasHomeMirrorResult:
    archive_stats: dict[str, object]
    scan_cache_entries: ChatlasRawScanCacheHome
    elapsed_seconds: float


@dataclass(frozen=True)
class ChatlasRawCopyCandidate:
    rel_path_text: str
    source_path: Path
    destination_path: Path


@dataclass(frozen=True)
class ChatlasRawDetectionBatchResult:
    actionable_files: tuple[ChatlasRawCopyCandidate, ...]
    cache_updates: ChatlasRawScanCacheHome
    processed_file_count: int
    unchanged_file_count: int
    skipped_file_count: int
    skipped_file_examples: tuple[str, ...]


@dataclass(frozen=True)
class ChatlasArchivePattern:
    value: str
    parts: tuple[str, ...]
    has_slash: bool


@dataclass(frozen=True)
class ChatlasProviderMirrorResult:
    payload: dict[str, object]
    scan_cache_updates: ChatlasRawScanCache
    elapsed_seconds: float


def _build_chatlas_provider_handler(provider_spec) -> ChatlasProviderHandler:
    return ChatlasProviderHandler(
        family=provider_spec.family,
        home_slots=provider_spec.home_slots,
        default_excludes=provider_spec.chatlas_default_excludes,
        default_includes=provider_spec.chatlas_default_includes,
    )


_CHATLAS_PROVIDER_HANDLERS = tuple(
    _build_chatlas_provider_handler(provider_spec)
    for provider_spec in canonical_chat_provider_specs()
    if provider_spec.supports_chatlas_raw
)
_CHATLAS_PROVIDER_HANDLERS_BY_NAME = {
    provider_handler.family: provider_handler
    for provider_handler in _CHATLAS_PROVIDER_HANDLERS
}


def supported_chatlas_provider_families() -> tuple[ChatlasProviderHandler, ...]:
    return _CHATLAS_PROVIDER_HANDLERS


def _chatlas_provider_handler_for_name(family_name: str) -> ChatlasProviderHandler | None:
    provider_spec = canonical_chat_provider_spec_for_name(family_name)
    if provider_spec is None or not provider_spec.supports_chatlas_raw:
        return None
    return _CHATLAS_PROVIDER_HANDLERS_BY_NAME.get(family_name)


def _provider_instance_field_name(*, field_prefix: str, index: int | None, field: str) -> str:
    if index is None:
        return field
    return f"{field_prefix}[{index}].{field}"


def _normalize_chatlas_home(home: object, *, field_name: str) -> str:
    if not isinstance(home, str) or not home.strip():
        raise CliError(f"{field_name} must be a non-empty string")
    return home.strip()


def _build_chatlas_provider_context(provider_instance: ProviderInstance) -> ChatlasProviderContext:
    provider_handler = _chatlas_provider_handler_for_name(provider_instance.family)
    if provider_handler is None:
        raise CliError(f"unsupported chatlas provider family {provider_instance.family}")

    return ChatlasProviderContext(
        provider_handler=provider_handler,
        provider_instance=provider_instance,
        resolved_instance_name=_resolve_chatlas_instance_name(provider_instance),
        effective_includes=_unique_strings(
            provider_handler.default_includes + provider_instance.includes
        ),
        effective_excludes=_unique_strings(
            provider_handler.default_excludes
            + provider_instance.excludes
            + _derived_chatlas_instance_excludes(provider_instance.family, provider_instance.homes)
        ),
    )


def _mirror_chatlas_provider_instance(
    *,
    context: ChatlasProviderContext,
    raw_root: Path,
    progress: Callable[[str], None] | None = None,
    scan_cache: ChatlasRawScanCache | None = None,
    scan_cache_enabled: bool = True,
) -> ChatlasProviderMirrorResult:
    started_at = time.perf_counter()
    home_results: list[dict[str, object]] = []
    scan_cache_updates: ChatlasRawScanCache = {}
    archived = False

    for home_key, home_path in context.provider_instance.homes:
        exists = home_path.is_dir()
        destination_path = _chatlas_home_destination(
            raw_root=raw_root,
            home_path=home_path,
        )
        home_payload = {
            "key": home_key,
            "source_path": str(home_path),
            "destination_path": str(destination_path),
            "exists": exists,
            "synced": False,
        }
        if exists:
            _emit_raw_progress(
                progress,
                f"{context.provider_instance.family}/{context.resolved_instance_name}:{home_key} archive {home_path}",
            )
            cache_home_key = _chatlas_raw_scan_cache_home_key(
                raw_root=raw_root,
                destination_path=destination_path,
            )
            archive_result = _mirror_chatlas_home(
                source_path=home_path,
                destination_path=destination_path,
                includes=context.effective_includes,
                excludes=context.effective_excludes,
                progress=progress,
                progress_label=f"{context.provider_instance.family}/{context.resolved_instance_name}:{home_key}",
                scan_cache_entries=None if scan_cache is None else scan_cache.get(cache_home_key),
                scan_cache_enabled=scan_cache_enabled,
            )
            home_payload["synced"] = True
            home_payload.update(archive_result.archive_stats)
            if scan_cache_enabled:
                scan_cache_updates[cache_home_key] = archive_result.scan_cache_entries
            archived = True
        home_results.append(home_payload)

    missing_home_keys = [
        home_result["key"]
        for home_result in home_results
        if not bool(home_result["exists"])
    ]

    payload = context.summary(raw_root)
    payload.update(
        {
            "synced": archived,
            "missing_home_keys": missing_home_keys,
            "homes_status": home_results,
        }
    )
    return ChatlasProviderMirrorResult(
        payload=payload,
        scan_cache_updates=scan_cache_updates,
        elapsed_seconds=time.perf_counter() - started_at,
    )


def _chatlas_home_destination(
    *,
    raw_root: Path,
    home_path: Path,
) -> Path:
    return raw_root / _chatlas_home_relpath(home_path)


def _mirror_chatlas_home(
    *,
    source_path: Path,
    destination_path: Path,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    progress: Callable[[str], None] | None = None,
    progress_label: str | None = None,
    scan_cache_entries: ChatlasRawScanCacheHome | None = None,
    scan_cache_enabled: bool = True,
) -> ChatlasHomeMirrorResult:
    started_at = time.perf_counter()
    destination_path.mkdir(parents=True, exist_ok=True)
    # Chatlas keeps an append-preserving archive of selected provider files.
    archive_stats = {
        "added_file_count": 0,
        "updated_file_count": 0,
        "unchanged_file_count": 0,
        "skipped_file_count": 0,
        "skipped_file_examples": [],
    }
    effective_excludes = (".git",) + excludes
    processed_file_count = 0
    next_scan_cache_entries: ChatlasRawScanCacheHome = {}
    next_progress_report = 250
    actionable_files: list[ChatlasRawCopyCandidate] = []

    for batch_result in _detect_chatlas_archive_candidates(
        candidate_files=_iter_chatlas_archive_source_files(
            source_path=source_path,
            includes=includes,
            excludes=effective_excludes,
        ),
        destination_path=destination_path,
        scan_cache_entries=scan_cache_entries,
        scan_cache_enabled=scan_cache_enabled,
    ):
        actionable_files.extend(batch_result.actionable_files)
        next_scan_cache_entries.update(batch_result.cache_updates)
        archive_stats["unchanged_file_count"] += batch_result.unchanged_file_count
        archive_stats["skipped_file_count"] += batch_result.skipped_file_count
        _extend_skipped_examples(
            archive_stats["skipped_file_examples"],
            batch_result.skipped_file_examples,
        )
        processed_file_count += batch_result.processed_file_count
        if progress is not None and processed_file_count >= next_progress_report:
            _emit_raw_progress(
                progress,
                f"{progress_label or destination_path.name}: {processed_file_count} files scanned "
                f"(added={archive_stats['added_file_count']} updated={archive_stats['updated_file_count']} "
                f"unchanged={archive_stats['unchanged_file_count']} skipped={archive_stats['skipped_file_count']} "
                f"elapsed={_format_wall_clock_elapsed(time.perf_counter() - started_at)})",
            )
            next_progress_report = ((processed_file_count // 250) + 1) * 250

    for copy_candidate in sorted(actionable_files, key=lambda candidate: candidate.rel_path_text):
        copy_result = _copy_chatlas_archive_file(
            source_path=copy_candidate.source_path,
            destination_path=copy_candidate.destination_path,
        )
        if copy_result == "added":
            archive_stats["added_file_count"] += 1
        elif copy_result == "updated":
            archive_stats["updated_file_count"] += 1
        elif copy_result == "unchanged":
            archive_stats["unchanged_file_count"] += 1
        else:
            archive_stats["skipped_file_count"] += 1
            _extend_skipped_examples(
                archive_stats["skipped_file_examples"],
                (copy_candidate.rel_path_text,),
            )
        if copy_result == "skipped":
            continue
        try:
            source_signature = _chatlas_archive_source_signature(copy_candidate.source_path)
        except FileNotFoundError:
            continue
        next_scan_cache_entries[copy_candidate.rel_path_text] = source_signature

    elapsed_seconds = time.perf_counter() - started_at
    _emit_raw_progress(
        progress,
        f"{progress_label or destination_path.name}: done "
        f"(scanned={processed_file_count} added={archive_stats['added_file_count']} "
        f"updated={archive_stats['updated_file_count']} unchanged={archive_stats['unchanged_file_count']} "
        f"skipped={archive_stats['skipped_file_count']} elapsed={_format_wall_clock_elapsed(elapsed_seconds)})",
    )

    return ChatlasHomeMirrorResult(
        archive_stats=archive_stats,
        scan_cache_entries=next_scan_cache_entries,
        elapsed_seconds=elapsed_seconds,
    )


def _detect_chatlas_archive_candidates(
    *,
    candidate_files: Iterable[tuple[Path, Path]],
    destination_path: Path,
    scan_cache_entries: ChatlasRawScanCacheHome | None,
    scan_cache_enabled: bool,
) -> Iterator[ChatlasRawDetectionBatchResult]:
    batches = _iter_chatlas_archive_detection_batches(candidate_files)
    worker_count = _chatlas_raw_detection_worker_count()

    initial_batches: list[tuple[tuple[Path, Path], ...]] = []
    initial_file_count = 0
    while initial_file_count < _CHATLAS_RAW_DETECTION_MIN_FILES:
        try:
            batch = next(batches)
        except StopIteration:
            break
        initial_batches.append(batch)
        initial_file_count += len(batch)

    if worker_count <= 1 or initial_file_count < _CHATLAS_RAW_DETECTION_MIN_FILES:
        for batch in initial_batches:
            yield _detect_chatlas_archive_batch(
                batch=batch,
                destination_path=destination_path,
                scan_cache_entries=scan_cache_entries,
                scan_cache_enabled=scan_cache_enabled,
            )
        for batch in batches:
            yield _detect_chatlas_archive_batch(
                batch=batch,
                destination_path=destination_path,
                scan_cache_entries=scan_cache_entries,
                scan_cache_enabled=scan_cache_enabled,
            )
        return

    max_in_flight = max(1, worker_count * _CHATLAS_RAW_DETECTION_IN_FLIGHT_MULTIPLIER)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_lookup: dict[Future[ChatlasRawDetectionBatchResult], None] = {}
        for batch in initial_batches:
            future_lookup[
                executor.submit(
                    _detect_chatlas_archive_batch,
                    batch=batch,
                    destination_path=destination_path,
                    scan_cache_entries=scan_cache_entries,
                    scan_cache_enabled=scan_cache_enabled,
                )
            ] = None
        yield from _drain_chatlas_archive_detection_futures(future_lookup, wait=False)

        for batch in batches:
            while len(future_lookup) >= max_in_flight:
                yield from _drain_chatlas_archive_detection_futures(future_lookup, wait=True)
            future_lookup[
                executor.submit(
                    _detect_chatlas_archive_batch,
                    batch=batch,
                    destination_path=destination_path,
                    scan_cache_entries=scan_cache_entries,
                    scan_cache_enabled=scan_cache_enabled,
                )
            ] = None
            yield from _drain_chatlas_archive_detection_futures(future_lookup, wait=False)

        while future_lookup:
            yield from _drain_chatlas_archive_detection_futures(future_lookup, wait=True)


def _iter_chatlas_archive_detection_batches(
    candidate_files: Iterable[tuple[Path, Path]],
) -> Iterator[tuple[tuple[Path, Path], ...]]:
    batch: list[tuple[Path, Path]] = []
    for candidate_file in candidate_files:
        batch.append(candidate_file)
        if len(batch) >= _CHATLAS_RAW_DETECTION_BATCH_SIZE:
            yield tuple(batch)
            batch = []
    if batch:
        yield tuple(batch)


def _drain_chatlas_archive_detection_futures(
    future_lookup: dict[Future[ChatlasRawDetectionBatchResult], None],
    *,
    wait: bool,
) -> Iterator[ChatlasRawDetectionBatchResult]:
    if not future_lookup:
        return
    if wait:
        futures = (next(as_completed(tuple(future_lookup))),)
    else:
        futures = tuple(future for future in future_lookup if future.done())

    for future in futures:
        if future not in future_lookup:
            continue
        future_lookup.pop(future)
        yield future.result()


def _detect_chatlas_archive_batch(
    *,
    batch: tuple[tuple[Path, Path], ...],
    destination_path: Path,
    scan_cache_entries: ChatlasRawScanCacheHome | None,
    scan_cache_enabled: bool,
) -> ChatlasRawDetectionBatchResult:
    actionable_files: list[ChatlasRawCopyCandidate] = []
    cache_updates: ChatlasRawScanCacheHome = {}
    unchanged_file_count = 0
    skipped_file_count = 0
    skipped_file_examples: list[str] = []

    for source_file, rel_path in batch:
        destination_file = destination_path / rel_path
        rel_path_text = rel_path.as_posix()
        try:
            source_signature = _chatlas_archive_source_signature(source_file)
        except FileNotFoundError:
            skipped_file_count += 1
            if len(skipped_file_examples) < 20:
                skipped_file_examples.append(rel_path_text)
            continue
        cached_entry = None if scan_cache_entries is None else scan_cache_entries.get(rel_path_text)
        if (
            scan_cache_enabled
            and cached_entry is not None
            and _chatlas_raw_scan_cache_entry_matches(cached_entry, source_signature)
            and _chatlas_archive_destination_matches_size(
                destination_file,
                expected_size=source_signature["size"],
            )
        ):
            unchanged_file_count += 1
            cache_updates[rel_path_text] = source_signature
            continue
        actionable_files.append(
            ChatlasRawCopyCandidate(
                rel_path_text=rel_path_text,
                source_path=source_file,
                destination_path=destination_file,
            )
        )

    return ChatlasRawDetectionBatchResult(
        actionable_files=tuple(actionable_files),
        cache_updates=cache_updates,
        processed_file_count=len(batch),
        unchanged_file_count=unchanged_file_count,
        skipped_file_count=skipped_file_count,
        skipped_file_examples=tuple(skipped_file_examples),
    )


def _chatlas_raw_detection_worker_count() -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, min(_CHATLAS_RAW_DETECTION_MAX_WORKERS, cpu_count))


def _extend_skipped_examples(skipped_examples: list[str], new_examples: tuple[str, ...]) -> None:
    for rel_path_text in new_examples:
        if len(skipped_examples) >= 20:
            break
        skipped_examples.append(rel_path_text)


def _emit_raw_progress(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is None:
        return
    progress(message)


def _format_wall_clock_elapsed(elapsed_seconds: float) -> str:
    return f"{elapsed_seconds:.2f}s"


def _iter_chatlas_archive_source_files(
    *,
    source_path: Path,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
) -> Iterator[tuple[Path, Path]]:
    include_patterns = _compile_chatlas_archive_patterns(includes)
    exclude_patterns = _compile_chatlas_archive_patterns(excludes)
    stack: list[tuple[Path, str]] = [(source_path, "")]
    while stack:
        current, rel_current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue

        child_dirs: list[tuple[Path, str]] = []
        for entry in entries:
            rel_text = f"{rel_current}/{entry.name}" if rel_current else entry.name
            rel_parts = _chatlas_archive_rel_parts(rel_text)
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False

            if is_dir:
                if _chatlas_archive_path_is_excluded(rel_text, rel_parts, exclude_patterns):
                    continue
                if include_patterns and not _chatlas_archive_dir_can_match_include_patterns(
                    rel_parts,
                    include_patterns,
                ):
                    continue
                child_dirs.append((Path(entry.path), rel_text))
                continue

            if not _chatlas_archive_entry_is_file_candidate(entry):
                continue
            if _chatlas_archive_path_is_excluded(rel_text, rel_parts, exclude_patterns):
                continue
            if include_patterns and not _chatlas_archive_path_matches_include_patterns(
                rel_text,
                rel_parts,
                include_patterns,
            ):
                continue
            yield Path(entry.path), Path(rel_text)

        stack.extend(reversed(child_dirs))


def _chatlas_archive_entry_is_file_candidate(entry: os.DirEntry[str]) -> bool:
    try:
        if entry.is_file(follow_symlinks=False):
            return True
        if not entry.is_symlink():
            return False
        return not entry.is_dir(follow_symlinks=True)
    except OSError:
        return False


def _compile_chatlas_archive_patterns(patterns: tuple[str, ...]) -> tuple[ChatlasArchivePattern, ...]:
    compiled_patterns: list[ChatlasArchivePattern] = []
    for raw_pattern in patterns:
        pattern = raw_pattern.strip().strip("/")
        if not pattern:
            continue
        compiled_patterns.append(
            ChatlasArchivePattern(
                value=pattern,
                parts=_chatlas_archive_rel_parts(pattern),
                has_slash="/" in pattern,
            )
        )
    return tuple(compiled_patterns)


def _chatlas_archive_rel_parts(rel_text: str) -> tuple[str, ...]:
    return tuple(part for part in rel_text.split("/") if part)


def _chatlas_archive_path_is_excluded(
    rel_text: str,
    rel_parts: tuple[str, ...],
    patterns: tuple[ChatlasArchivePattern, ...],
) -> bool:
    if not rel_text:
        return False

    for pattern in patterns:
        if rel_text == pattern.value or rel_text.startswith(f"{pattern.value}/"):
            return True
        if not pattern.has_slash:
            if pattern.value in rel_parts:
                return True
            if rel_parts and fnmatch.fnmatchcase(rel_parts[-1], pattern.value):
                return True
            continue
        if _match_glob_parts(rel_parts, pattern.parts):
            return True
    return False


def _chatlas_archive_path_matches_include_patterns(
    rel_text: str,
    rel_parts: tuple[str, ...],
    patterns: tuple[ChatlasArchivePattern, ...],
) -> bool:
    if not rel_text:
        return False

    for pattern in patterns:
        if rel_text == pattern.value:
            return True
        if pattern.value.endswith("/**"):
            prefix = pattern.value[:-3].rstrip("/")
            if prefix and (rel_text == prefix or rel_text.startswith(f"{prefix}/")):
                return True
        if not pattern.has_slash:
            if rel_parts and fnmatch.fnmatchcase(rel_parts[-1], pattern.value):
                return True
            continue
        if _match_glob_parts(rel_parts, pattern.parts):
            return True
    return False


def _chatlas_archive_dir_can_match_include_patterns(
    dir_parts: tuple[str, ...],
    patterns: tuple[ChatlasArchivePattern, ...],
) -> bool:
    if not dir_parts:
        return True

    for pattern in patterns:
        if _chatlas_archive_dir_can_match_glob(dir_parts, pattern.parts):
            return True
    return False


def _chatlas_archive_dir_can_match_includes(rel_dir: PurePosixPath, includes: tuple[str, ...]) -> bool:
    rel_value = normalize_rel(rel_dir)
    if not rel_value:
        return True
    dir_parts = tuple(part for part in rel_value.split("/") if part)
    if not dir_parts:
        return True

    return _chatlas_archive_dir_can_match_include_patterns(
        dir_parts,
        _compile_chatlas_archive_patterns(includes),
    )


def _chatlas_archive_dir_can_match_glob(dir_parts: tuple[str, ...], pattern_parts: tuple[str, ...]) -> bool:
    if not dir_parts:
        return True
    if not pattern_parts:
        return False

    head = pattern_parts[0]
    tail = pattern_parts[1:]
    if head == "**":
        return (
            _chatlas_archive_dir_can_match_glob(dir_parts, tail)
            or _chatlas_archive_dir_can_match_glob(dir_parts[1:], pattern_parts)
        )
    if not fnmatch.fnmatchcase(dir_parts[0], head):
        return False
    return _chatlas_archive_dir_can_match_glob(dir_parts[1:], tail)


def _chatlas_archive_path_matches_includes(rel_path: PurePosixPath, includes: tuple[str, ...]) -> bool:
    rel_value = normalize_rel(rel_path)
    if not rel_value:
        return False

    for raw_pattern in includes:
        pattern = raw_pattern.strip().strip("/")
        if not pattern:
            continue
        if rel_value == pattern:
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if prefix and (rel_value == prefix or rel_value.startswith(f"{prefix}/")):
                return True
        if _chatlas_archive_path_matches_glob(rel_value, pattern):
            return True
    return False


def _chatlas_archive_path_matches_glob(rel_value: str, pattern: str) -> bool:
    path_parts = tuple(part for part in rel_value.split("/") if part)
    pattern_parts = tuple(part for part in pattern.split("/") if part)
    if not pattern_parts:
        return False
    return _match_glob_parts(path_parts, pattern_parts)


def _match_glob_parts(path_parts: tuple[str, ...], pattern_parts: tuple[str, ...]) -> bool:
    if not pattern_parts:
        return not path_parts
    head = pattern_parts[0]
    tail = pattern_parts[1:]
    if head == "**":
        if _match_glob_parts(path_parts, tail):
            return True
        if not path_parts:
            return False
        return _match_glob_parts(path_parts[1:], pattern_parts)
    if not path_parts:
        return False
    if not fnmatch.fnmatchcase(path_parts[0], head):
        return False
    return _match_glob_parts(path_parts[1:], tail)


def _copy_chatlas_archive_file(
    *,
    source_path: Path,
    destination_path: Path,
) -> str:
    temp_destination: Path | None = None
    try:
        destination_is_symlink = destination_path.is_symlink()
        destination_exists = destination_path.exists()
        destination_preexisting = destination_exists or destination_is_symlink
        if (
            destination_exists
            and not destination_is_symlink
            and _chatlas_archive_files_match(source_path, destination_path)
        ):
            return "unchanged"
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if destination_is_symlink:
            with tempfile.NamedTemporaryFile(
                prefix=f".{destination_path.name}.",
                suffix=".tmp",
                dir=destination_path.parent,
                delete=False,
            ) as handle:
                temp_destination = Path(handle.name)
            shutil.copy2(source_path, temp_destination)
            os.replace(temp_destination, destination_path)
            temp_destination = None
        else:
            shutil.copy2(source_path, destination_path)
    except FileNotFoundError:
        return "skipped"
    except OSError as exc:
        raise CliError(f"failed to archive {source_path}: {exc}") from exc
    finally:
        if temp_destination is not None:
            try:
                temp_destination.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
    return "updated" if destination_preexisting else "added"


def _chatlas_archive_files_match(source_path: Path, destination_path: Path) -> bool:
    if destination_path.is_symlink():
        return False

    try:
        source_stat = source_path.stat()
        destination_stat = destination_path.stat()
    except FileNotFoundError:
        raise
    except OSError:
        return False

    if source_stat.st_size != destination_stat.st_size:
        return False

    try:
        with source_path.open("rb") as source_handle, destination_path.open("rb") as destination_handle:
            while True:
                source_chunk = source_handle.read(1024 * 1024)
                destination_chunk = destination_handle.read(1024 * 1024)
                if source_chunk != destination_chunk:
                    return False
                if not source_chunk:
                    return True
    except FileNotFoundError:
        raise
    except OSError:
        return False


def _chatlas_archive_source_signature(source_path: Path) -> ChatlasRawScanCacheEntry:
    try:
        source_stat = source_path.stat()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise CliError(f"failed to stat archive source file {source_path}: {exc}") from exc
    return {
        "mtime_ns": int(source_stat.st_mtime_ns),
        "size": int(source_stat.st_size),
    }


def _chatlas_archive_destination_matches_size(destination_path: Path, *, expected_size: int) -> bool:
    if destination_path.is_symlink():
        return False

    try:
        return destination_path.stat().st_size == expected_size
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _chatlas_raw_scan_cache_entry_matches(
    entry: ChatlasRawScanCacheEntry,
    source_signature: ChatlasRawScanCacheEntry,
) -> bool:
    return (
        entry.get("mtime_ns") == source_signature["mtime_ns"]
        and entry.get("size") == source_signature["size"]
    )


def _chatlas_raw_scan_cache_home_key(*, raw_root: Path, destination_path: Path) -> str:
    relative_destination = destination_path.relative_to(raw_root)
    return normalize_rel(PurePosixPath(relative_destination.as_posix()))


def _chatlas_raw_scan_cache_path(chatlas_root: Path) -> Path:
    return chatlas_root / _CHATLAS_RAW_SCAN_CACHE_RELATIVE_PATH


def _load_chatlas_raw_scan_cache(chatlas_root: Path) -> ChatlasRawScanCache:
    raw_homes = load_chatlas_cache_section(
        _chatlas_raw_scan_cache_path(chatlas_root),
        entries_key="homes",
    )
    homes: ChatlasRawScanCache = {}
    for home_key, raw_entries in raw_homes.items():
        if not isinstance(home_key, str) or not home_key.strip() or not isinstance(raw_entries, dict):
            continue
        home_entries: ChatlasRawScanCacheHome = {}
        for rel_path, raw_entry in raw_entries.items():
            if not isinstance(rel_path, str) or not rel_path.strip() or not isinstance(raw_entry, dict):
                continue
            mtime_ns = raw_entry.get("mtime_ns")
            size = raw_entry.get("size")
            if not isinstance(mtime_ns, int) or not isinstance(size, int):
                continue
            if mtime_ns < 0 or size < 0:
                continue
            home_entries[rel_path] = {
                "mtime_ns": mtime_ns,
                "size": size,
            }
        homes[home_key] = home_entries
    return homes


def _write_chatlas_raw_scan_cache(chatlas_root: Path, cache: ChatlasRawScanCache) -> None:
    write_chatlas_cache_section(
        _chatlas_raw_scan_cache_path(chatlas_root),
        cache_class="agentos.chatlas.raw_scan_cache",
        entries_key="homes",
        entries={
            home_key: {
                rel_path: {
                    "mtime_ns": int(entry["mtime_ns"]),
                    "size": int(entry["size"]),
                }
                for rel_path, entry in sorted(home_entries.items())
            }
            for home_key, home_entries in sorted(cache.items())
        },
    )


def _chatlas_home_relpath(home_path: Path) -> Path:
    normalized_home = home_path.expanduser().resolve()
    user_home = Path.home().expanduser().resolve()

    try:
        relpath = normalized_home.relative_to(user_home)
        if relpath.parts:
            return relpath
    except ValueError:
        pass

    if normalized_home.is_absolute():
        relative_text = os.path.relpath(str(normalized_home), normalized_home.anchor)
        relpath = Path(relative_text)
        if relpath.parts and relpath != Path("."):
            return relpath

    return Path(normalized_home.name)


def _dedupe_chatlas_instances(provider_instances: tuple[ProviderInstance, ...]) -> tuple[ProviderInstance, ...]:
    unique_instances: dict[tuple[object, ...], ProviderInstance] = {}
    for provider_instance in provider_instances:
        key = provider_instance.identity_key()
        if key not in unique_instances:
            unique_instances[key] = provider_instance
    return tuple(unique_instances.values())


def _validate_unique_chatlas_destinations(provider_instances: tuple[ProviderInstance, ...]) -> None:
    seen_destinations: dict[tuple[str, str], ProviderInstance] = {}
    for provider_instance in provider_instances:
        context = _build_chatlas_provider_context(provider_instance)
        key = (provider_instance.family, context.resolved_instance_name)
        if key in seen_destinations:
            existing = seen_destinations[key]
            raise CliError(
                "chatlas provider instances resolve to the same destination "
                f"{provider_instance.family}/{context.resolved_instance_name}: "
                f"{existing.homes_map()} and {provider_instance.homes_map()}"
            )
        seen_destinations[key] = provider_instance



def _derive_chatlas_instance_name(
    family: str,
    homes: tuple[tuple[str, Path], ...],
) -> str | None:
    if len(homes) != 1:
        return None

    _, home_path = homes[0]
    basename = home_path.name.lstrip(".")
    if not basename or basename == family:
        return None

    for separator in ("-", "_"):
        family_prefix = f"{family}{separator}"
        if basename.startswith(family_prefix):
            suffix = basename[len(family_prefix):].strip()
            if suffix:
                return validate_string_for_path(suffix, field_name="chatlas instance name")

    return validate_string_for_path(basename, field_name="chatlas instance name")


def _resolve_chatlas_instance_name(provider_instance: ProviderInstance) -> str:
    if provider_instance.instance_id is not None:
        return provider_instance.instance_id
    derived_name = _derive_chatlas_instance_name(provider_instance.family, provider_instance.homes)
    if derived_name is not None:
        return derived_name
    return provider_instance.fingerprint[:12]


def _derived_chatlas_instance_excludes(
    family: str,
    homes: tuple[tuple[str, Path], ...],
) -> tuple[str, ...]:
    if family != "codex":
        return ()
    return ("_auth*.json",)


__all__ = [
    "supported_chatlas_provider_families",
]
