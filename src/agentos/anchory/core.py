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


@dataclass(frozen=True)
class AnchoryCheckResult:
    findings: tuple[AnchoryCheckFinding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings


class AnchoryDepot:
    """A single Anchory store rooted at an explicit directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def register(
        self,
        record: Mapping[str, object],
        *,
        anchor: str | None = None,
        prefix: str | None = None,
    ) -> AnchoryEntry:
        if (anchor is None) == (prefix is None):
            raise InvalidAnchoryInputError("exactly one of anchor or prefix is required")
        normalized_record = _normalize_record(record)
        with self._lock(exclusive=True, create=True):
            if prefix is not None:
                anchor = self._allocate_anchor(prefix)
            else:
                anchor = _validate_anchor(anchor)
            path = self._shard_path(anchor)
            records = _read_shard(path)
            if anchor in records:
                raise AnchorExistsError(f"anchor already exists: {anchor}")
            records[anchor] = normalized_record
            _write_shard_atomic(path, records)
        return AnchoryEntry(anchor=anchor, record=dict(normalized_record))

    def resolve(self, anchor: str) -> dict[str, object] | None:
        anchor = _validate_anchor(anchor)
        with self._lock(exclusive=False, create=False):
            record = _read_shard(self._shard_path(anchor)).get(anchor)
        return dict(record) if record is not None else None

    def amend(self, anchor: str, record: Mapping[str, object]) -> AnchoryEntry:
        anchor = _validate_anchor(anchor)
        normalized_record = _normalize_record(record)
        with self._lock(exclusive=True, create=True):
            path = self._shard_path(anchor)
            records = _read_shard(path)
            if anchor not in records:
                raise AnchorNotFoundError(f"anchor does not exist: {anchor}")
            records[anchor] = normalized_record
            _write_shard_atomic(path, records)
        return AnchoryEntry(anchor=anchor, record=dict(normalized_record))

    def query(self, *, prefix: str | None = None) -> tuple[AnchoryEntry, ...]:
        if prefix is not None and not isinstance(prefix, str):
            raise InvalidAnchoryInputError("prefix must be a string")
        entries: list[AnchoryEntry] = []
        with self._lock(exclusive=False, create=False):
            namespace_root = self.root / GLOBAL_NAMESPACE
            for path in sorted(namespace_root.glob("*.json")):
                for anchor, record in _read_shard(path).items():
                    if prefix is None or anchor.startswith(prefix):
                        entries.append(AnchoryEntry(anchor=anchor, record=dict(record)))
        return tuple(sorted(entries, key=lambda entry: entry.anchor))

    def check(self) -> AnchoryCheckResult:
        findings: list[AnchoryCheckFinding] = []
        seen: set[str] = set()
        with self._lock(exclusive=False, create=False):
            namespace_root = self.root / GLOBAL_NAMESPACE
            for path in sorted(namespace_root.glob("*.json")):
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
                    if _shard_name(anchor) != path.stem:
                        findings.append(
                            AnchoryCheckFinding(
                                code="misplaced-anchor",
                                path=relative_path,
                                anchor=anchor,
                                message=f"anchor belongs in shard {_shard_name(anchor)}.json",
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
        return AnchoryCheckResult(
            findings=tuple(
                sorted(
                    findings,
                    key=lambda finding: (finding.path, finding.anchor or "", finding.code),
                )
            )
        )

    def _shard_path(self, anchor: str) -> Path:
        return self.root / GLOBAL_NAMESPACE / f"{_shard_name(anchor)}.json"

    def _allocate_anchor(self, prefix: str) -> str:
        prefix = _validate_anchor(prefix)
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        max_suffix: int | None = None
        namespace_root = self.root / GLOBAL_NAMESPACE
        for path in sorted(namespace_root.glob("*.json")):
            for existing_anchor in _read_shard(path):
                match = pattern.fullmatch(existing_anchor)
                if match is None:
                    continue
                suffix = int(match.group(1))
                max_suffix = suffix if max_suffix is None else max(max_suffix, suffix)
        return f"{prefix}-{0 if max_suffix is None else max_suffix + 1}"

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
