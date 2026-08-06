# $kw: ^anchory-amend-validator --from Anchory.System --note [CT] applications may validate replacement meaning inside Anchory's atomic amendment boundary --supp ^c20260730-33u
from __future__ import annotations

from bisect import bisect_right
from collections import OrderedDict
import hashlib
import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Mapping, Pattern


GLOBAL_NAMESPACE = "global"

META_FILENAME = "meta.json"

_TAG_RE = re.compile(r"^[a-z]$")
_NS_PREFIX_RE = re.compile(r"^[a-z]$")
_TAGGED_KEY_RE = re.compile(r"^(?P<base>.*-\d+)(?P<tag>[a-z])$")


class AnchoryError(RuntimeError):
    pass


class InvalidAnchoryInputError(AnchoryError):
    pass


class AnchorExistsError(AnchoryError):
    pass


class AnchorNotFoundError(AnchoryError):
    pass


class CorruptAnchoryDepotError(AnchoryError):
    pass


@dataclass(frozen=True)
class AnchoryEntry:
    anchor: str
    record: dict[str, object]


@dataclass(frozen=True)
class AnchoryResolution:
    anchor: str
    namespace: str
    record: dict[str, object]
    tag_mismatch: bool


@dataclass(frozen=True)
class AnchorySourceMatch:
    anchor: str
    line: int
    column: int
    start: int
    end: int


@dataclass(frozen=True)
class AnchoryCheckFinding:
    code: str
    path: str
    message: str
    anchor: str | None = None
    severity: str = "error"


@dataclass(frozen=True)
class AnchoryCheckResult:
    findings: tuple[AnchoryCheckFinding, ...]

    @property
    def ok(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)


AnchoryAmendValidator = Callable[
    [Path, dict[str, object], dict[str, object]],
    None,
]

# Decides one record's replacement, or None to leave it alone.
AnchoryBulkAmendment = Callable[[str, dict[str, object]], Mapping[str, object] | None]


@dataclass(frozen=True)
class AnchoryBulkAmendResult:
    """What one bulk amendment saw and changed."""

    scanned: int
    changed: tuple[str, ...]
    shards: int
    dry_run: bool

    @property
    def changed_count(self) -> int:
        return len(self.changed)


class AnchoryRuntimeCache:
    """Bounded, caller-owned cache for one Anchory operation."""

    def __init__(self, *, capacity: int = 4096) -> None:
        if capacity < 0:
            raise ValueError("Anchory runtime cache capacity must be non-negative")
        self.capacity = capacity
        self._resolutions: OrderedDict[
            tuple[str, str, str | None], AnchoryResolution | None
        ] = OrderedDict()
        self._registered_depots: set[tuple[str, str]] = set()

    @property
    def resolution_count(self) -> int:
        return len(self._resolutions)

    def get_resolution(
        self,
        root: Path,
        anchor: str,
        namespace: str | None,
    ) -> tuple[bool, AnchoryResolution | None]:
        key = (str(root), anchor, namespace)
        if key not in self._resolutions:
            return False, None
        resolution = self._resolutions.pop(key)
        self._resolutions[key] = resolution
        return True, _copy_resolution(resolution)

    def put_resolution(
        self,
        root: Path,
        anchor: str,
        namespace: str | None,
        resolution: AnchoryResolution | None,
    ) -> None:
        if self.capacity == 0:
            return
        key = (str(root), anchor, namespace)
        self._resolutions.pop(key, None)
        self._resolutions[key] = _copy_resolution(resolution)
        while len(self._resolutions) > self.capacity:
            self._resolutions.popitem(last=False)

    def invalidate_depot(self, root: Path) -> None:
        root_text = str(root)
        self._resolutions = OrderedDict(
            (key, value)
            for key, value in self._resolutions.items()
            if key[0] != root_text
        )

    def registry_touched(self, root: Path, registry: Path) -> bool:
        return (str(root), str(registry)) in self._registered_depots

    def mark_registry_touched(self, root: Path, registry: Path) -> None:
        self._registered_depots.add((str(root), str(registry)))

    def invalidate_registry_touch(self, root: Path) -> None:
        root_text = str(root)
        self._registered_depots = {
            key for key in self._registered_depots if key[0] != root_text
        }


class AnchoryDepot:
    """A single Anchory store rooted at an explicit directory."""

    def __init__(
        self,
        root: Path | str,
        *,
        runtime_cache: AnchoryRuntimeCache | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.runtime_cache = runtime_cache or AnchoryRuntimeCache()

    def register(
        self,
        record: Mapping[str, object],
        *,
        anchor: str | None = None,
        alloc_prefix: str | None = None,
        tag: str | None = None,
        namespace: str = GLOBAL_NAMESPACE,
    ) -> AnchoryEntry:
        if (anchor is None) == (alloc_prefix is None):
            raise InvalidAnchoryInputError(
                "exactly one of anchor or alloc_prefix is required"
            )
        if tag is not None:
            if anchor is not None:
                raise InvalidAnchoryInputError(
                    "tag decorates an allocated key; pass it with alloc_prefix, not anchor"
                )
            if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
                raise InvalidAnchoryInputError("tag must be a single lowercase letter")
        namespace = _validate_namespace(namespace)
        normalized_record = _normalize_record(record)
        with self._lock(exclusive=True, create=True):
            if alloc_prefix is not None:
                full_prefix = self._composed_prefix(namespace, alloc_prefix)
                anchor = self._allocate_anchor(namespace, full_prefix, tag)
            else:
                anchor = _validate_anchor(anchor)
            path = self._shard_path(namespace, anchor)
            records = _read_shard(path)
            if anchor in records:
                raise AnchorExistsError(f"anchor already exists: {anchor}")
            records[anchor] = normalized_record
            _write_shard_atomic(path, records)
        self._invalidate_runtime_cache()
        self._touch_registry(refresh=True)
        return AnchoryEntry(anchor=anchor, record=dict(normalized_record))

    def _touch_registry(self, *, refresh: bool = False) -> None:
        from .registry import record_depot_touch, registry_path

        registry = registry_path().expanduser().resolve()
        if refresh:
            self.runtime_cache.invalidate_registry_touch(self.root)
        if self.runtime_cache.registry_touched(self.root, registry):
            return
        record_depot_touch(self)
        self.runtime_cache.mark_registry_touched(self.root, registry)

    def _invalidate_runtime_cache(self) -> None:
        self.runtime_cache.invalidate_depot(self.root)

    def resolve(
        self, anchor: str, *, namespace: str | None = None
    ) -> AnchoryResolution | None:
        anchor = _validate_anchor(anchor)
        namespace = _validate_namespace(namespace) if namespace is not None else None
        base = _base_key(anchor)
        self._touch_registry()
        cached, resolution = self.runtime_cache.get_resolution(
            self.root,
            anchor,
            namespace,
        )
        if cached:
            return resolution
        namespaces = [namespace] if namespace is not None else self.namespaces()
        with self._lock(exclusive=False, create=False):
            for candidate in namespaces:
                records = _read_shard(self._shard_path(candidate, anchor))
                record = records.get(anchor)
                if record is not None:
                    resolution = AnchoryResolution(
                        anchor=anchor,
                        namespace=candidate,
                        record=dict(record),
                        tag_mismatch=False,
                    )
                    self.runtime_cache.put_resolution(
                        self.root, anchor, namespace, resolution
                    )
                    return resolution
                for existing, existing_record in records.items():
                    if existing != anchor and _base_key(existing) == base:
                        resolution = AnchoryResolution(
                            anchor=existing,
                            namespace=candidate,
                            record=dict(existing_record),
                            tag_mismatch=True,
                        )
                        self.runtime_cache.put_resolution(
                            self.root, anchor, namespace, resolution
                        )
                        return resolution
        self.runtime_cache.put_resolution(self.root, anchor, namespace, None)
        return None

    def amend(
        self,
        anchor: str,
        record: Mapping[str, object],
        *,
        namespace: str | None = None,
        validator: AnchoryAmendValidator | None = None,
    ) -> AnchoryEntry:
        anchor = _validate_anchor(anchor)
        normalized_record = _normalize_record(record)
        namespaces = (
            [_validate_namespace(namespace)]
            if namespace is not None
            else self.namespaces() or [GLOBAL_NAMESPACE]
        )
        with self._lock(exclusive=True, create=True):
            for candidate in namespaces:
                path = self._shard_path(candidate, anchor)
                records = _read_shard(path)
                if anchor in records:
                    if validator is not None:
                        validator(
                            self.root,
                            _normalize_record(records[anchor]),
                            _normalize_record(normalized_record),
                        )
                    records[anchor] = normalized_record
                    _write_shard_atomic(path, records)
                    self._invalidate_runtime_cache()
                    self._touch_registry(refresh=True)
                    return AnchoryEntry(anchor=anchor, record=dict(normalized_record))
        raise AnchorNotFoundError(f"anchor does not exist: {anchor}")

    def bulk_amend(
        self,
        amendment: AnchoryBulkAmendment,
        *,
        namespace: str | None = None,
        validator: AnchoryAmendValidator | None = None,
        dry_run: bool = False,
    ) -> AnchoryBulkAmendResult:
        """Amend every record in the depot under one exclusive lock.

        This is `amend` over the whole depot rather than one named anchor. It
        takes the same optional validator and applies it to each record it
        would change, so the rules do not depend on how many anchors a caller
        happens to be touching.

        The lock is what this exists for. Reading each shard, deciding, and
        writing it back is a read-modify-write; done without the lock held for
        the whole sweep, a concurrent `register` landing in an already-read
        shard is silently dropped. `dry_run` reports what would change without
        writing, under the same lock.
        """
        namespaces = (
            [_validate_namespace(namespace)]
            if namespace is not None
            else self.namespaces()
        )
        scanned = 0
        changed: list[str] = []
        shards = 0
        with self._lock(exclusive=True, create=True):
            for candidate in namespaces:
                namespace_root = self.root / candidate
                for path in sorted(namespace_root.glob("*.json")):
                    if path.name == META_FILENAME:
                        continue
                    records = _read_shard(path)
                    updated: dict[str, object] = {}
                    shard_changed = False
                    for anchor, record in records.items():
                        scanned += 1
                        current = _normalize_record(record)
                        proposed = amendment(anchor, dict(current))
                        if proposed is None:
                            updated[anchor] = record
                            continue
                        normalized = _normalize_record(proposed)
                        if normalized == current:
                            updated[anchor] = record
                            continue
                        if validator is not None:
                            validator(self.root, dict(current), dict(normalized))
                        updated[anchor] = normalized
                        changed.append(anchor)
                        shard_changed = True
                    if shard_changed:
                        shards += 1
                        if not dry_run:
                            _write_shard_atomic(path, updated)
        if changed and not dry_run:
            self._invalidate_runtime_cache()
            self._touch_registry(refresh=True)
        return AnchoryBulkAmendResult(
            scanned=scanned,
            changed=tuple(sorted(changed)),
            shards=shards,
            dry_run=dry_run,
        )

    def query(
        self, *, namespace: str | None = None, prefix: str | None = None
    ) -> tuple[AnchoryEntry, ...]:
        if prefix is not None and not isinstance(prefix, str):
            raise InvalidAnchoryInputError("prefix must be a string")
        self._touch_registry()
        namespaces = (
            [_validate_namespace(namespace)]
            if namespace is not None
            else self.namespaces()
        )
        entries: list[AnchoryEntry] = []
        with self._lock(exclusive=False, create=False):
            for candidate in namespaces:
                namespace_root = self.root / candidate
                for path in sorted(namespace_root.glob("*.json")):
                    if path.name == META_FILENAME:
                        continue
                    for anchor, record in _read_shard(path).items():
                        if prefix is None or anchor.startswith(prefix):
                            entries.append(
                                AnchoryEntry(anchor=anchor, record=dict(record))
                            )
        return tuple(sorted(entries, key=lambda entry: entry.anchor))

    def namespaces(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        )

    def namespace_meta(self, namespace: str) -> dict[str, object] | None:
        namespace = _validate_namespace(namespace)
        path = self.root / namespace / META_FILENAME
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CorruptAnchoryDepotError(
                f"cannot read namespace meta {path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise CorruptAnchoryDepotError(
                f"namespace meta must be a JSON object: {path}"
            )
        return payload

    def write_namespace_meta(
        self,
        namespace: str,
        *,
        prefix: str,
        intention: str | None = None,
        semantics: str | None = None,
    ) -> dict[str, object]:
        namespace = _validate_namespace(namespace)
        if not isinstance(prefix, str) or not _NS_PREFIX_RE.fullmatch(prefix):
            raise InvalidAnchoryInputError(
                "namespace prefix must be a single lowercase letter"
            )
        meta: dict[str, object] = {"prefix": prefix}
        if intention is not None:
            meta["intention"] = intention
        if semantics is not None:
            meta["semantics"] = semantics
        with self._lock(exclusive=True, create=True):
            path = self.root / namespace / META_FILENAME
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        self._invalidate_runtime_cache()
        self._touch_registry(refresh=True)
        return meta

    def _composed_prefix(self, namespace: str, alloc_prefix: str) -> str:
        alloc_prefix = _validate_anchor(alloc_prefix)
        if namespace == GLOBAL_NAMESPACE:
            return alloc_prefix
        meta = self.namespace_meta(namespace)
        ns_prefix = meta.get("prefix") if isinstance(meta, dict) else None
        if not isinstance(ns_prefix, str) or not _NS_PREFIX_RE.fullmatch(ns_prefix):
            raise InvalidAnchoryInputError(
                f"namespace {namespace!r} has no declared prefix in {META_FILENAME}; "
                "write namespace meta before allocating keys"
            )
        return f"{ns_prefix}{alloc_prefix}"

    def check(self) -> AnchoryCheckResult:
        self._touch_registry()
        findings: list[AnchoryCheckFinding] = []
        with self._lock(exclusive=False, create=False):
            for namespace in self.namespaces():
                findings.extend(self._check_namespace(namespace))
        return AnchoryCheckResult(
            findings=tuple(
                sorted(
                    findings,
                    key=lambda finding: (
                        finding.path,
                        finding.anchor or "",
                        finding.code,
                    ),
                )
            )
        )

    def _check_namespace(self, namespace: str) -> list[AnchoryCheckFinding]:
        findings: list[AnchoryCheckFinding] = []
        seen: set[str] = set()
        namespace_root = self.root / namespace
        meta_path = namespace_root / META_FILENAME
        if meta_path.is_file():
            try:
                self.namespace_meta(namespace)
            except CorruptAnchoryDepotError as exc:
                findings.append(
                    AnchoryCheckFinding(
                        code="invalid-meta",
                        path=str(meta_path.relative_to(self.root)),
                        message=str(exc),
                    )
                )
        try:
            meta = self.namespace_meta(namespace)
        except CorruptAnchoryDepotError:
            meta = None
        prefixed_namespace = isinstance(meta, dict) and isinstance(
            meta.get("prefix"), str
        )
        for path in sorted(namespace_root.glob("*.json")):
            if path.name == META_FILENAME:
                continue
            relative_path = str(path.relative_to(self.root))
            if len(path.stem) != 2 or any(
                char not in "0123456789abcdef" for char in path.stem
            ):
                findings.append(
                    AnchoryCheckFinding(
                        code="invalid-shard-name",
                        path=relative_path,
                        message="shard filename must be two lowercase hexadecimal characters",
                    )
                )
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                findings.append(
                    AnchoryCheckFinding(
                        code="invalid-json",
                        path=relative_path,
                        message=str(exc),
                    )
                )
                continue
            if not isinstance(payload, dict):
                findings.append(
                    AnchoryCheckFinding(
                        code="invalid-shard",
                        path=relative_path,
                        message="shard must be a JSON object",
                    )
                )
                continue
            for anchor, record in payload.items():
                if not isinstance(record, dict):
                    findings.append(
                        AnchoryCheckFinding(
                            code="invalid-record",
                            path=relative_path,
                            anchor=anchor,
                            message="record must be a JSON object",
                        )
                    )
                    continue
                if not anchor:
                    findings.append(
                        AnchoryCheckFinding(
                            code="invalid-anchor",
                            path=relative_path,
                            anchor=anchor,
                            message="anchor must be a non-empty string",
                        )
                    )
                    continue
                if _shard_name(_base_key(anchor)) != path.stem:
                    findings.append(
                        AnchoryCheckFinding(
                            code="misplaced-anchor",
                            path=relative_path,
                            anchor=anchor,
                            message=(
                                f"anchor belongs in shard {_shard_name(_base_key(anchor))}.json"
                            ),
                        )
                    )
                if anchor in seen:
                    findings.append(
                        AnchoryCheckFinding(
                            code="duplicate-anchor",
                            path=relative_path,
                            anchor=anchor,
                            message="anchor appears in more than one shard",
                        )
                    )
                seen.add(anchor)
                if prefixed_namespace and re.fullmatch(r".*-\d+", anchor):
                    findings.append(
                        AnchoryCheckFinding(
                            code="tagless-anchor",
                            path=relative_path,
                            anchor=anchor,
                            message="key carries no tag letter; amendable backlog, not an error",
                            severity="warning",
                        )
                    )
        return findings

    def _shard_path(self, namespace: str, anchor: str) -> Path:
        return self.root / namespace / f"{_shard_name(_base_key(anchor))}.json"

    def _allocate_anchor(
        self, namespace: str, full_prefix: str, tag: str | None
    ) -> str:
        pattern = re.compile(rf"^{re.escape(full_prefix)}-(\d+)[a-z]?$")
        max_suffix: int | None = None
        namespace_root = self.root / namespace
        for path in sorted(namespace_root.glob("*.json")):
            if path.name == META_FILENAME:
                continue
            for existing_anchor in _read_shard(path):
                match = pattern.fullmatch(existing_anchor)
                if match is None:
                    continue
                suffix = int(match.group(1))
                max_suffix = suffix if max_suffix is None else max(max_suffix, suffix)
        counter = 0 if max_suffix is None else max_suffix + 1
        return f"{full_prefix}-{counter}{tag or ''}"

    @contextmanager
    def _lock(self, *, exclusive: bool, create: bool) -> Iterator[None]:
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        elif not self.root.is_dir():
            yield
            return
        lock_path = self.root / ".anchory.lock"
        with lock_path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _validate_anchor(anchor: str) -> str:
    if not isinstance(anchor, str) or not anchor:
        raise InvalidAnchoryInputError("anchor must be a non-empty string")
    return anchor


def _shard_name(anchor: str) -> str:
    return hashlib.sha256(anchor.encode("utf-8")).hexdigest()[:2]


def _base_key(anchor: str) -> str:
    """The key without its trailing tag letter — the sharding and identity spine."""
    match = _TAGGED_KEY_RE.fullmatch(anchor)
    return match.group("base") if match else anchor


def _validate_namespace(namespace: str) -> str:
    if (
        not isinstance(namespace, str)
        or not namespace
        or "/" in namespace
        or namespace.startswith(".")
    ):
        raise InvalidAnchoryInputError("namespace must be a plain directory name")
    return namespace


def _normalize_record(record: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(record, Mapping):
        raise InvalidAnchoryInputError("record must be a JSON object")
    try:
        normalized = json.loads(json.dumps(dict(record)))
    except (TypeError, ValueError) as exc:
        raise InvalidAnchoryInputError(
            f"record must be JSON serializable: {exc}"
        ) from exc
    if not isinstance(normalized, dict):
        raise InvalidAnchoryInputError("record must be a JSON object")
    return normalized


def _copy_resolution(
    resolution: AnchoryResolution | None,
) -> AnchoryResolution | None:
    if resolution is None:
        return None
    return AnchoryResolution(
        anchor=resolution.anchor,
        namespace=resolution.namespace,
        record=dict(resolution.record),
        tag_mismatch=resolution.tag_mismatch,
    )


def scan_anchory_source(text: str, regex: str) -> tuple[AnchorySourceMatch, ...]:
    try:
        pattern = re.compile(regex)
    except re.error as exc:
        raise InvalidAnchoryInputError(f"invalid regex: {exc}") from exc
    line_starts = _line_starts(text)
    seen: set[str] = set()
    matches: list[AnchorySourceMatch] = []
    for match in pattern.finditer(text):
        anchor, start, end = _extract_anchor_match(pattern, match)
        anchor = _validate_anchor(anchor)
        if anchor in seen:
            continue
        seen.add(anchor)
        line, column = _line_column(line_starts, start)
        matches.append(
            AnchorySourceMatch(
                anchor=anchor,
                line=line,
                column=column,
                start=start,
                end=end,
            )
        )
    return tuple(matches)


def _extract_anchor_match(
    pattern: Pattern[str], match: re.Match[str]
) -> tuple[str, int, int]:
    if "anchor" in pattern.groupindex:
        anchor = match.group("anchor")
        return anchor, match.start("anchor"), match.end("anchor")
    if pattern.groups:
        anchor = match.group(1)
        return anchor, match.start(1), match.end(1)
    return match.group(0), match.start(0), match.end(0)


def _line_starts(text: str) -> tuple[int, ...]:
    starts = [0]
    starts.extend(index + 1 for index, char in enumerate(text) if char == "\n")
    return tuple(starts)


def _line_column(line_starts: tuple[int, ...], offset: int) -> tuple[int, int]:
    line_index = bisect_right(line_starts, offset) - 1
    return line_index + 1, offset - line_starts[line_index] + 1


def _read_shard(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorruptAnchoryDepotError(
            f"cannot read Anchory shard {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise CorruptAnchoryDepotError(f"Anchory shard must be a JSON object: {path}")
    records: dict[str, dict[str, object]] = {}
    for anchor, record in payload.items():
        if not isinstance(anchor, str) or not isinstance(record, dict):
            raise CorruptAnchoryDepotError(
                f"Anchory shard entries must map strings to JSON objects: {path}"
            )
        records[anchor] = record
    return records


def _write_shard_atomic(
    path: Path, records: Mapping[str, Mapping[str, object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(json.dumps(records, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
