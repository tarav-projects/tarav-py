# $kw: ^bloberia-core --from Agentos.Bloberia --note [DF] explicit-depot JSON records with library-owned identity and metadata ^c20260724-31u
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping
from uuid import UUID

from agentos._core.clock import iso_z
from agentos._core.ids import generate_uuid4_string


ENVELOPE_KEY = "_bloberia"
RECORD_KEYS = frozenset({ENVELOPE_KEY, "value"})
ENVELOPE_KEYS = frozenset({"id", "created_at", "updated_at", "revision"})


class BloberiaError(RuntimeError):
    pass


class InvalidBloberiaInputError(BloberiaError):
    pass


class RecordExistsError(BloberiaError):
    pass


class RecordNotFoundError(BloberiaError):
    pass


class CorruptBloberiaDepotError(BloberiaError):
    pass


@dataclass(frozen=True)
class BloberiaRecord:
    id: str
    created_at: str
    updated_at: str
    revision: int
    value: object

    def as_dict(self) -> dict[str, object]:
        return _normalize_json(
            {
                ENVELOPE_KEY: {
                    "id": self.id,
                    "created_at": self.created_at,
                    "updated_at": self.updated_at,
                    "revision": self.revision,
                },
                "value": self.value,
            }
        )


@dataclass(frozen=True)
class BloberiaCheckFinding:
    code: str
    path: str
    message: str
    record_id: str | None = None


@dataclass(frozen=True)
class BloberiaCheckResult:
    findings: tuple[BloberiaCheckFinding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings


class BloberiaDepot:
    """One Bloberia record store rooted at an explicit directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def create(self, value: object) -> BloberiaRecord:
        normalized_value = _normalize_json(value)
        record_id = generate_uuid4_string()
        timestamp = _now_iso()
        record = BloberiaRecord(
            id=record_id,
            created_at=timestamp,
            updated_at=timestamp,
            revision=1,
            value=normalized_value,
        )
        with self._lock(exclusive=True, create=True):
            path = self._record_path(record_id)
            if path.exists():
                raise RecordExistsError(f"record already exists: {record_id}")
            _write_json_atomic(path, record.as_dict())
        return _record_from_payload(record.as_dict(), path=self._record_path(record_id))

    def get(self, record_id: str) -> BloberiaRecord:
        record_id = _validate_record_id(record_id)
        with self._lock(exclusive=False, create=False):
            path = self._record_path(record_id)
            if not path.is_file():
                raise RecordNotFoundError(f"record does not exist: {record_id}")
            return _read_record(path, expected_id=record_id)

    def edit(self, record_id: str, value: object) -> BloberiaRecord:
        record_id = _validate_record_id(record_id)
        normalized_value = _normalize_json(value)
        with self._lock(exclusive=True, create=True):
            path = self._record_path(record_id)
            if not path.is_file():
                raise RecordNotFoundError(f"record does not exist: {record_id}")
            current = _read_record(path, expected_id=record_id)
            updated_at = _now_iso()
            while updated_at <= current.updated_at:
                updated_at = _now_iso()
            edited = BloberiaRecord(
                id=current.id,
                created_at=current.created_at,
                updated_at=updated_at,
                revision=current.revision + 1,
                value=normalized_value,
            )
            _write_json_atomic(path, edited.as_dict())
        return _record_from_payload(edited.as_dict(), path=path, expected_id=record_id)

    def query(self, query: Mapping[str, object]) -> tuple[BloberiaRecord, ...]:
        normalized_query = _normalize_json(query)
        if not isinstance(normalized_query, dict):
            raise InvalidBloberiaInputError("query must be a JSON object")
        records: list[BloberiaRecord] = []
        with self._lock(exclusive=False, create=False):
            records_root = self.root / "records"
            if not records_root.is_dir():
                return ()
            for path in sorted(records_root.glob("*.json")):
                try:
                    expected_id = _validate_record_id(path.stem)
                except InvalidBloberiaInputError as exc:
                    raise CorruptBloberiaDepotError(
                        f"invalid record filename {path}: {exc}"
                    ) from exc
                record = _read_record(path, expected_id=expected_id)
                if _matches_subset(normalized_query, record.as_dict()):
                    records.append(record)
        return tuple(sorted(records, key=lambda record: record.id))

    def check(self) -> BloberiaCheckResult:
        findings: list[BloberiaCheckFinding] = []
        with self._lock(exclusive=False, create=False):
            records_root = self.root / "records"
            if not records_root.is_dir():
                return BloberiaCheckResult(findings=())
            for path in sorted(records_root.glob("*.json")):
                relative_path = str(path.relative_to(self.root))
                try:
                    expected_id = _validate_record_id(path.stem)
                except InvalidBloberiaInputError as exc:
                    findings.append(
                        BloberiaCheckFinding(
                            code="invalid-record-filename",
                            path=relative_path,
                            record_id=path.stem,
                            message=str(exc),
                        )
                    )
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    findings.append(
                        BloberiaCheckFinding(
                            code="invalid-json",
                            path=relative_path,
                            record_id=expected_id,
                            message=str(exc),
                        )
                    )
                    continue
                try:
                    record = _record_from_payload(payload, path=path)
                except CorruptBloberiaDepotError as exc:
                    findings.append(
                        BloberiaCheckFinding(
                            code="invalid-record",
                            path=relative_path,
                            record_id=expected_id,
                            message=str(exc),
                        )
                    )
                    continue
                if record.id != expected_id:
                    findings.append(
                        BloberiaCheckFinding(
                            code="identity-mismatch",
                            path=relative_path,
                            record_id=expected_id,
                            message=(
                                f"record identity {record.id} does not match filename "
                                f"{expected_id}"
                            ),
                        )
                    )
        return BloberiaCheckResult(
            findings=tuple(
                sorted(
                    findings,
                    key=lambda finding: (
                        finding.path,
                        finding.code,
                        finding.record_id or "",
                    ),
                )
            )
        )

    def _record_path(self, record_id: str) -> Path:
        return self.root / "records" / f"{record_id}.json"

    @contextmanager
    def _lock(self, *, exclusive: bool, create: bool) -> Iterator[None]:
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        elif not self.root.is_dir():
            yield
            return
        lock_path = self.root / ".bloberia.lock"
        if not create and not lock_path.exists():
            yield
            return
        with lock_path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _now_iso() -> str:
    return iso_z(datetime.now(timezone.utc), drop_micros=False)


def _normalize_json(value: object) -> object:
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise InvalidBloberiaInputError(
            f"value must be JSON serializable: {exc}"
        ) from exc


def _validate_record_id(record_id: str) -> str:
    if not isinstance(record_id, str) or not record_id:
        raise InvalidBloberiaInputError("record id must be a UUID string")
    try:
        parsed = UUID(record_id)
    except ValueError as exc:
        raise InvalidBloberiaInputError(
            f"record id must be a UUID string: {record_id}"
        ) from exc
    return str(parsed)


def _matches_subset(query: object, candidate: object) -> bool:
    if isinstance(query, dict):
        if not isinstance(candidate, dict):
            return False
        return all(
            key in candidate and _matches_subset(value, candidate[key])
            for key, value in query.items()
        )
    return query == candidate


def _read_record(path: Path, *, expected_id: str | None = None) -> BloberiaRecord:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorruptBloberiaDepotError(
            f"cannot read Bloberia record {path}: {exc}"
        ) from exc
    return _record_from_payload(payload, path=path, expected_id=expected_id)


def _record_from_payload(
    payload: object,
    *,
    path: Path,
    expected_id: str | None = None,
) -> BloberiaRecord:
    if not isinstance(payload, dict) or set(payload) != RECORD_KEYS:
        raise CorruptBloberiaDepotError(
            f"record must contain exactly {sorted(RECORD_KEYS)}: {path}"
        )
    envelope = payload.get(ENVELOPE_KEY)
    if not isinstance(envelope, dict) or set(envelope) != ENVELOPE_KEYS:
        raise CorruptBloberiaDepotError(
            f"record envelope must contain exactly {sorted(ENVELOPE_KEYS)}: {path}"
        )
    record_id = envelope.get("id")
    try:
        normalized_id = _validate_record_id(record_id)  # type: ignore[arg-type]
    except InvalidBloberiaInputError as exc:
        raise CorruptBloberiaDepotError(f"invalid record identity in {path}: {exc}") from exc
    if expected_id is not None and normalized_id != expected_id:
        raise CorruptBloberiaDepotError(
            f"record identity does not match filename: {path}"
        )
    created_at = envelope.get("created_at")
    updated_at = envelope.get("updated_at")
    revision = envelope.get("revision")
    if not isinstance(created_at, str) or not created_at:
        raise CorruptBloberiaDepotError(f"created_at must be a non-empty string: {path}")
    if not isinstance(updated_at, str) or not updated_at:
        raise CorruptBloberiaDepotError(f"updated_at must be a non-empty string: {path}")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise CorruptBloberiaDepotError(f"revision must be a positive integer: {path}")
    value = _normalize_json(payload["value"])
    return BloberiaRecord(
        id=normalized_id,
        created_at=created_at,
        updated_at=updated_at,
        revision=revision,
        value=value,
    )


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
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
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
