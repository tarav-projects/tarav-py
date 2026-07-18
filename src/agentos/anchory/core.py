from __future__ import annotations

from bisect import bisect_right
import hashlib
import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Pattern


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


class AnchoryDepot:
    """A single Anchory store rooted at an explicit directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

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
        self._touch_registry()
        return AnchoryEntry(anchor=anchor, record=dict(normalized_record))

    def _touch_registry(self) -> None:
        from .registry import record_depot_touch

        record_depot_touch(self)

    def resolve(
        self, anchor: str, *, namespace: str | None = None
    ) -> AnchoryResolution | None:
        anchor = _validate_anchor(anchor)
        base = _base_key(anchor)
        self._touch_registry()
        namespaces = (
            [_validate_namespace(namespace)]
            if namespace is not None
            else self.namespaces()
        )
        with self._lock(exclusive=False, create=False):
            for candidate in namespaces:
                records = _read_shard(self._shard_path(candidate, anchor))
                record = records.get(anchor)
                if record is not None:
                    return AnchoryResolution(
                        anchor=anchor,
                        namespace=candidate,
                        record=dict(record),
                        tag_mismatch=False,
                    )
                for existing, existing_record in records.items():
                    if existing != anchor and _base_key(existing) == base:
                        return AnchoryResolution(
                            anchor=existing,
                            namespace=candidate,
                            record=dict(existing_record),
                            tag_mismatch=True,
                        )
        return None

    def amend(
        self,
        anchor: str,
        record: Mapping[str, object],
        *,
        namespace: str | None = None,
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
                    records[anchor] = normalized_record
                    _write_shard_atomic(path, records)
                    self._touch_registry()
                    return AnchoryEntry(anchor=anchor, record=dict(normalized_record))
        raise AnchorNotFoundError(f"anchor does not exist: {anchor}")

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
            raise CorruptAnchoryDepotError(f"namespace meta must be a JSON object: {path}")
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
            path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
                    key=lambda finding: (finding.path, finding.anchor or "", finding.code),
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
        prefixed_namespace = isinstance(meta, dict) and isinstance(meta.get("prefix"), str)
        for path in sorted(namespace_root.glob("*.json")):
            if path.name == META_FILENAME:
                continue
            relative_path = str(path.relative_to(self.root))
            if len(path.stem) != 2 or any(char not in "0123456789abcdef" for char in path.stem):
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
                if (
                    prefixed_namespace
                    and re.fullmatch(r".*-\d+", anchor)
                ):
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

    def _allocate_anchor(self, namespace: str, full_prefix: str, tag: str | None) -> str:
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
    if not isinstance(namespace, str) or not namespace or "/" in namespace or namespace.startswith("."):
        raise InvalidAnchoryInputError("namespace must be a plain directory name")
    return namespace


def _normalize_record(record: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(record, Mapping):
        raise InvalidAnchoryInputError("record must be a JSON object")
    try:
        normalized = json.loads(json.dumps(dict(record)))
    except (TypeError, ValueError) as exc:
        raise InvalidAnchoryInputError(f"record must be JSON serializable: {exc}") from exc
    if not isinstance(normalized, dict):
        raise InvalidAnchoryInputError("record must be a JSON object")
    return normalized


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
        raise CorruptAnchoryDepotError(f"cannot read Anchory shard {path}: {exc}") from exc
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


def _write_shard_atomic(path: Path, records: Mapping[str, Mapping[str, object]]) -> None:
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
