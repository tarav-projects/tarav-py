# $kw: ^bloberia-core --from Agentos.Bloberia --from Bloberia.Record.Namespace --note [DF] opaque-cargo JSON records addressed by path queries; the depot owns storage topology and nothing else --supp ^c20260806-31u ^c20260724-31u
"""Depot-scoped storage for opaque JSON records.

Bloberia holds a consumer's cargo **verbatim**. There is no envelope — no id, no
timestamps, no revision, no `value` wrapper — because the moment the store adds a field
it owns a schema, and every consumer inherits its migrations. That refusal is what lets
one store serve consumers whose schemas move independently.

Three things follow from it, and they are the whole design:

- **Arity belongs to the call.** `first(query)` returns one match, `all(query)` returns
  every match. Nothing is declared, nothing is enforced, and a collision is the
  consumer's business rather than a configuration error.
- **The layout is private.** No caller learns where a record sits. Anchory's sharding
  leaked and two migration scripts in this repo reimplemented it, which is exactly what
  makes a storage topology unchangeable afterwards.
- **Placement is the caller's.** A depot is rooted at an explicit directory, so project
  tier, user tier and public depot are decisions bloberia never makes.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

from tarav._core.persistence import atomic_write_json

from .coordinate import RecordCoordinate, derive as _derive, resolve as _resolve
from .git import GitCheckpoint

#: The public depot for records that belong to no single project, beside the Chatlas
#: archive. An important system carries its own public depot rather than hiding in a
#: dotfile; a project-tier depot is rooted in the project instead.
PUBLIC_DEPOT_ROOT = Path.home() / "Documents" / "bloberia"

META_FILENAME = "meta.json"
RECORDS_DIRNAME = "records"
DEPOT_SCHEMA = "tarav.bloberia-depot.v2"

#: One storage topology under the shared contract. `files` is one JSON document per
#: record; jsonl and accelerated types are additions, not replacements, which is why the
#: contract below is fixed while only one type exists.
TYPE_FILES = "files"

#: Many records per file, grouped by two hex digits of the key's digest. Carried forward
#: from Anchory, where it was measured: 3,956 records under `files` is 3,956 opens per
#: scan. The key is a declared cargo path, so this type does look inside cargo — that is
#: the term a consumer accepts by choosing it, not a leak in the `files` contract.
TYPE_SHARDS = "shards"
DEPOT_TYPES = (TYPE_FILES, TYPE_SHARDS)

Cargo = Any
Query = Mapping[str, Mapping[str, Any]]

#: Where one record sits, in whatever the depot's topology is. A `files` record is a
#: whole file; a `shards` record is one entry inside one. Never surfaced to a caller.
_Locator = tuple[Path, str | None]

_PREDICATES = ("equals", "contains", "exists")


class BloberiaError(RuntimeError):
    pass


class InvalidBloberiaInputError(BloberiaError):
    pass


class CorruptBloberiaDepotError(BloberiaError):
    pass


def _normalize(value: object) -> object:
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise InvalidBloberiaInputError(f"cargo must be JSON serializable: {exc}") from exc


_MISSING = object()


def _validate_namespace(namespace: str | None) -> str | None:
    """A namespace partitions *placement* only; it never enters identity or meaning.

    It is a relative path prefix and may nest, because placement is organizational and a
    consumer's organization is its own. Every segment is checked rather than the string as
    a whole: `..` and a leading dot are the two ways a prefix stops being a prefix and
    starts being a re-rooting.
    """
    if namespace is None:
        return None
    if not isinstance(namespace, str) or not namespace:
        raise InvalidBloberiaInputError(f"invalid namespace: {namespace!r}")
    segments = namespace.split("/")
    if any(not segment or segment.startswith(".") for segment in segments):
        raise InvalidBloberiaInputError(f"invalid namespace: {namespace!r}")
    return namespace


def _at_path(cargo: object, path: str) -> object:
    """Resolve a dotted path, treating an integer segment as a list index.

    Returns a private sentinel rather than None for an absent path, because `exists`
    must distinguish "no such path" from "the path holds null" — a distinction the
    index relies on, where `links.landing: null` means *ungated* rather than *unknown*.
    """
    current: object = cargo
    for segment in path.split("."):
        if isinstance(current, Mapping):
            if segment not in current:
                return _MISSING
            current = current[segment]
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return current


def _matches(cargo: object, query: Query) -> bool:
    for path, condition in query.items():
        if not isinstance(condition, Mapping) or not condition:
            raise InvalidBloberiaInputError(
                f"query condition for {path!r} must name a predicate"
            )
        for predicate, operand in condition.items():
            if predicate not in _PREDICATES:
                # `regex` is deliberately absent: it is the one predicate no index or
                # textual prescan can serve, so admitting it would guarantee a fast path
                # and a slow path that diverge. Refused loudly rather than ignored.
                raise InvalidBloberiaInputError(
                    f"unsupported predicate {predicate!r}; bloberia supports "
                    f"{', '.join(_PREDICATES)} (regex is not available)"
                )
            found = _at_path(cargo, path)
            if predicate == "exists":
                if (found is not _MISSING) is not bool(operand):
                    return False
            elif found is _MISSING:
                return False
            elif predicate == "equals":
                if found != operand:
                    return False
            elif predicate == "contains":
                if not isinstance(found, str) or str(operand) not in found:
                    return False
    return True


@dataclass(frozen=True)
class BloberiaCheckFinding:
    """One record that does not parse. `path` is depot-relative, for a human to open."""

    code: str
    path: str
    message: str


@dataclass(frozen=True)
class BloberiaCheckResult:
    findings: tuple[BloberiaCheckFinding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings


class BloberiaDepot:
    """One record store rooted at an explicit directory."""

    def __init__(
        self,
        root: Path | str,
        *,
        depot_type: str | None = None,
        key: str | None = None,
        git: str | None = None,
        git_interval_seconds: int | None = None,
    ) -> None:
        if depot_type is not None and depot_type not in DEPOT_TYPES:
            raise InvalidBloberiaInputError(f"unknown depot type: {depot_type}")
        self.root = Path(root).expanduser().resolve()
        #: `None` means "whatever the depot is". It is distinct from an explicit
        #: `files`, which is a claim about the depot that a shards meta must refuse.
        self._type = depot_type or TYPE_FILES
        self._asked_for = depot_type
        self._declared_key = key
        self._declared_git = (git, git_interval_seconds)
        self._meta: dict[str, object] | None = None
        self._load_meta()

    # -- meta --------------------------------------------------------------------

    @property
    def meta_path(self) -> Path:
        return self.root / META_FILENAME

    def _load_meta(self) -> None:
        """A depot's own meta is authoritative; a constructor argument may not contradict it.

        The type decides the storage topology, so letting a caller pass a different one
        would mean reading a depot through a layout it was not written in.
        """
        if not self.meta_path.is_file():
            return
        try:
            meta = json.loads(self.meta_path.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise CorruptBloberiaDepotError(f"unreadable depot meta {self.meta_path}: {exc}") from exc
        if not isinstance(meta, dict):
            raise CorruptBloberiaDepotError(f"depot meta is not an object: {self.meta_path}")
        stored_type = meta.get("type", TYPE_FILES)
        if stored_type not in DEPOT_TYPES:
            raise CorruptBloberiaDepotError(f"unknown depot type in meta: {stored_type!r}")
        if self._asked_for is not None and self._asked_for != stored_type:
            raise InvalidBloberiaInputError(
                f"depot at {self.root} is type {stored_type!r}, not {self._asked_for!r}"
            )
        self._type = str(stored_type)
        self._meta = meta
        if self._declared_key is None:
            self._declared_key = meta.get("key")  # type: ignore[assignment]
        declared_git, declared_interval = self._declared_git
        self._declared_git = (
            declared_git if declared_git is not None else meta.get("git"),
            declared_interval
            if declared_interval is not None
            else meta.get("git_interval_seconds"),
        )

    def _write_meta(self) -> None:
        if self.meta_path.exists():
            return
        meta: dict[str, object] = {"schema": DEPOT_SCHEMA, "type": self._type}
        if self._type == TYPE_SHARDS:
            meta["key"] = self.shard_key
        git, interval = self._declared_git
        if git is not None:
            meta["git"] = git
            if interval is not None:
                meta["git_interval_seconds"] = interval
        atomic_write_json(self.meta_path, meta)
        self._meta = meta

    def initialize(self) -> "BloberiaDepot":
        """Materialize an empty depot's declared storage contract.

        Depot hosts sometimes need an inspectable store before its first cargo exists.
        This writes only Bloberia metadata; repository creation remains the host's job.
        """
        with self._lock(exclusive=True, create=True):
            self._write_meta()
        self._checkpoint()
        return self

    @property
    def git(self) -> GitCheckpoint | None:
        try:
            return GitCheckpoint.resolve(self.meta_path, *self._declared_git)
        except ValueError as exc:
            raise InvalidBloberiaInputError(str(exc)) from exc

    def _checkpoint(self) -> None:
        """Offered after every write, and free to decline. Never raises."""
        handler = self.git
        if handler is not None:
            handler.checkpoint(self.root)

    # -- reading -----------------------------------------------------------------

    def iterate(self, *, namespace: str | None = None) -> Iterator[Cargo]:
        """Every record, in a stable order the caller must not depend on for meaning."""
        for _locator, cargo in self._scan({}, namespace=namespace):
            yield cargo

    def first(self, query: Query, *, namespace: str | None = None) -> Cargo | None:
        for _path, cargo in self._scan(query, namespace=namespace):
            return cargo
        return None

    def all(self, query: Query, *, namespace: str | None = None) -> tuple[Cargo, ...]:
        return tuple(cargo for _path, cargo in self._scan(query, namespace=namespace))

    def count(self, query: Query, *, namespace: str | None = None) -> int:
        return sum(1 for _ in self._scan(query, namespace=namespace))

    # -- writing -----------------------------------------------------------------

    def insert(self, cargo: Cargo, *, namespace: str | None = None) -> None:
        """Store one record. Always a new record: bloberia never merges by content."""
        normalized = _normalize(cargo)
        namespace = _validate_namespace(namespace)
        with self._lock(exclusive=True, create=True):
            self._write_meta()
            if self._type == TYPE_SHARDS:
                key = self._key_of(normalized)
                path = self._shard_path(namespace, key)
                records = self._read_shard(path)
                if key in records:
                    raise InvalidBloberiaInputError(
                        f"{self.shard_key} {key!r} already exists in this depot"
                    )
                records[key] = normalized
                path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(path, records)
            else:
                atomic_write_json(self._new_path(namespace), normalized)
        self._checkpoint()

    def replace(self, query: Query, cargo: Cargo, *, namespace: str | None = None) -> int:
        normalized = _normalize(cargo)
        with self._lock(exclusive=True, create=True):
            located = [loc for loc, _ in self._scan(query, namespace=namespace, locked=True)]
            for locator in located:
                self._store(locator, normalized)
        self._checkpoint()
        return len(located)

    def delete(self, query: Query, *, namespace: str | None = None) -> int:
        with self._lock(exclusive=True, create=True):
            located = [loc for loc, _ in self._scan(query, namespace=namespace, locked=True)]
            for locator in located:
                self._drop(locator)
        self._checkpoint()
        return len(located)

    def _store(self, locator: _Locator, cargo: Cargo) -> None:
        path, key = locator
        if key is None:
            atomic_write_json(path, cargo)
            return
        records = self._read_shard(path)
        records.pop(key, None)
        records[self._key_of(cargo)] = cargo
        atomic_write_json(path, records)

    def _drop(self, locator: _Locator) -> None:
        path, key = locator
        if key is None:
            path.unlink()
            return
        records = self._read_shard(path)
        records.pop(key, None)
        if records:
            atomic_write_json(path, records)
        else:
            path.unlink()

    # -- internals ---------------------------------------------------------------

    def _records_root(self) -> Path:
        return self.root / RECORDS_DIRNAME

    def _namespace_root(self, namespace: str | None) -> Path:
        return self._records_root() / namespace if namespace else self._records_root()

    def _new_path(self, namespace: str | None) -> Path:
        """A private filename. Opaque and never surfaced, so the topology stays free."""
        root = self._namespace_root(namespace)
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{uuid4().hex}.json"

    # -- shards ------------------------------------------------------------------

    @property
    def shard_key(self) -> str:
        key = (self._meta or {}).get("key", self._declared_key)
        if not isinstance(key, str) or not key:
            raise InvalidBloberiaInputError(
                f"a {TYPE_SHARDS} depot must declare the cargo path it shards by"
            )
        return key

    def _shard_path(self, namespace: str | None, key_value: str) -> Path:
        digest = hashlib.sha256(key_value.encode("utf-8")).hexdigest()[:2]
        return self._namespace_root(namespace) / f"{digest}.json"

    def _key_of(self, cargo: object) -> str:
        """The declared key must be present and a string. A missing key is loud.

        Silently placing an unkeyed record would put it in a shard nothing can compute,
        which is a record written and never findable again.
        """
        value = _at_path(cargo, self.shard_key)
        if value is _MISSING:
            raise InvalidBloberiaInputError(
                f"cargo carries no {self.shard_key!r}, which this depot shards by"
            )
        if not isinstance(value, str) or not value:
            raise InvalidBloberiaInputError(
                f"{self.shard_key!r} must be a non-empty string, got {value!r}"
            )
        return value

    def _read_shard(self, path: Path) -> dict[str, Cargo]:
        if not path.is_file():
            return {}
        loaded = self._read(path)
        if not isinstance(loaded, dict):
            raise CorruptBloberiaDepotError(f"shard is not an object: {path}")
        return loaded

    def _shard_paths(self, namespace: str | None) -> tuple[Path, ...]:
        root = self._namespace_root(_validate_namespace(namespace))
        if not root.is_dir():
            return ()
        return tuple(
            sorted(p for p in root.rglob("*.json") if p.name != META_FILENAME)
        )

    def _record_paths(self, namespace: str | None = None) -> tuple[Path, ...]:
        namespace = _validate_namespace(namespace)
        root = self._records_root() / namespace if namespace else self._records_root()
        if not root.is_dir():
            return ()
        return tuple(sorted(p for p in root.rglob("*.json") if p.name != META_FILENAME))

    def namespaces(self) -> tuple[str, ...]:
        """Every namespace prefix present, without reading any record.

        A nested namespace contributes each of its prefixes, because `a/b/c` is reachable
        as `a` and `a/b` too — listing only the leaves would name places a read cannot
        address and hide places it can.
        """
        root = self._records_root()
        if not root.is_dir():
            return ()
        return tuple(
            sorted(
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_dir()
            )
        )

    def check(self) -> BloberiaCheckResult:
        """Audit every record against the only invariant bloberia still owns: it parses.

        The previous check also verified that a filename was a well-formed uuid, that a
        payload carried the store's envelope, and that the id inside a record matched its
        filename. All three describe a store that models its cargo. Nothing resolves by
        filename, there is no envelope, and a record has no id the store knows about — so
        those findings could only report on a structure that no longer exists.
        """

        findings: list[BloberiaCheckFinding] = []
        with self._lock(exclusive=False, create=False):
            paths = (
                self._shard_paths(None)
                if self._type == TYPE_SHARDS
                else self._record_paths(None)
            )
            for path in paths:
                try:
                    json.loads(path.read_text("utf-8"))
                except (OSError, ValueError) as exc:
                    findings.append(
                        BloberiaCheckFinding(
                            code="invalid-json",
                            path=str(path.relative_to(self.root)),
                            message=str(exc),
                        )
                    )
        return BloberiaCheckResult(findings=tuple(sorted(findings, key=lambda f: f.path)))

    # -- stable references -------------------------------------------------------

    def coordinate(
        self, query: Query, *, namespace: str | None = None, path: str = ""
    ) -> RecordCoordinate | None:
        """The `commit + file + path` of the first matching record, if git holds it.

        `path` addresses a sub-value, so a coordinate links to a piece of a record as
        readily as to the whole. Returns `None` when the depot is not git-tracked, or when
        the record is not committed — which is a fact reported, never one manufactured.
        """
        handler = self.git
        if handler is None:
            return None
        for locator, _cargo in self._scan(query, namespace=namespace):
            file, key = locator
            inner = f"{key}.{path}".rstrip(".") if key is not None else path
            return _derive(handler.repo, file, inner)
        return None

    def at(self, coordinate: RecordCoordinate) -> object:
        """Read the value a coordinate names, out of the commit it names."""
        handler = self.git
        if handler is None:
            raise InvalidBloberiaInputError(f"depot at {self.root} is not git-tracked")
        return _resolve(handler.repo, coordinate)

    def _read(self, path: Path) -> Cargo:
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise CorruptBloberiaDepotError(f"unreadable record {path}: {exc}") from exc

    def _scan(
        self, query: Query, *, namespace: str | None = None, locked: bool = False
    ) -> Iterator[tuple[Path, Cargo]]:
        if not isinstance(query, Mapping):
            raise InvalidBloberiaInputError("query must be a mapping of path to predicate")
        if locked:
            yield from self._scan_unlocked(query, namespace)
            return
        with self._lock(exclusive=False, create=False):
            yield from self._scan_unlocked(query, namespace)

    def _scan_unlocked(self, query: Query, namespace: str | None) -> Iterator[tuple[_Locator, Cargo]]:
        if self._type == TYPE_SHARDS:
            for path in self._candidate_shards(query, namespace):
                for key, cargo in self._read_shard(path).items():
                    if _matches(cargo, query):
                        yield (path, key), cargo
            return
        for path in self._record_paths(namespace):
            cargo = self._read(path)
            if _matches(cargo, query):
                yield (path, None), cargo

    def _candidate_shards(self, query: Query, namespace: str | None) -> tuple[Path, ...]:
        """One shard when the query pins the key, every shard otherwise.

        This is the only reason the type exists: a lookup by the declared key computes
        its shard instead of reading the depot. The result is identical either way, so
        the fast path can never disagree with the scan — it visits fewer files.
        """
        predicate = query.get(self.shard_key) if isinstance(query, Mapping) else None
        if isinstance(predicate, Mapping) and isinstance(predicate.get("equals"), str):
            path = self._shard_path(_validate_namespace(namespace), predicate["equals"])
            return (path,) if path.is_file() else ()
        return self._shard_paths(namespace)

    @contextmanager
    def _lock(self, *, exclusive: bool, create: bool) -> Iterator[None]:
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            yield
            return
        lock_path = self.root / ".bloberia.lock"
        with open(lock_path, "a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


__all__ = [
    "BloberiaCheckFinding",
    "BloberiaCheckResult",
    "BloberiaDepot",
    "BloberiaError",
    "CorruptBloberiaDepotError",
    "InvalidBloberiaInputError",
    "PUBLIC_DEPOT_ROOT",
    "RecordCoordinate",
    "TYPE_FILES",
    "TYPE_SHARDS",
]
