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
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

from tarav._core.persistence import atomic_write_json

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
DEPOT_TYPES = (TYPE_FILES,)

Cargo = Any
Query = Mapping[str, Mapping[str, Any]]

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
    """A namespace partitions *placement* only; it never enters identity or meaning."""
    if namespace is None:
        return None
    if not isinstance(namespace, str) or not namespace or "/" in namespace or namespace.startswith("."):
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


class BloberiaDepot:
    """One record store rooted at an explicit directory."""

    def __init__(self, root: Path | str, *, depot_type: str = TYPE_FILES) -> None:
        if depot_type not in DEPOT_TYPES:
            raise InvalidBloberiaInputError(f"unknown depot type: {depot_type}")
        self.root = Path(root).expanduser().resolve()
        self._type = depot_type

    # -- reading -----------------------------------------------------------------

    def iterate(self, *, namespace: str | None = None) -> Iterator[Cargo]:
        """Every record, in a stable order the caller must not depend on for meaning."""
        for path in self._record_paths(namespace):
            yield self._read(path)

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
        with self._lock(exclusive=True, create=True):
            atomic_write_json(self._new_path(_validate_namespace(namespace)), normalized)

    def replace(self, query: Query, cargo: Cargo, *, namespace: str | None = None) -> int:
        normalized = _normalize(cargo)
        with self._lock(exclusive=True, create=True):
            paths = [p for p, _ in self._scan(query, namespace=namespace, locked=True)]
            for path in paths:
                atomic_write_json(path, normalized)
        return len(paths)

    def delete(self, query: Query, *, namespace: str | None = None) -> int:
        with self._lock(exclusive=True, create=True):
            paths = [p for p, _ in self._scan(query, namespace=namespace, locked=True)]
            for path in paths:
                path.unlink()
        return len(paths)

    # -- internals ---------------------------------------------------------------

    def _records_root(self) -> Path:
        return self.root / RECORDS_DIRNAME

    def _new_path(self, namespace: str | None) -> Path:
        """A private filename. Opaque and never surfaced, so the topology stays free."""
        root = self._records_root() / namespace if namespace else self._records_root()
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{uuid4().hex}.json"

    def _record_paths(self, namespace: str | None = None) -> tuple[Path, ...]:
        namespace = _validate_namespace(namespace)
        root = self._records_root() / namespace if namespace else self._records_root()
        if not root.is_dir():
            return ()
        return tuple(sorted(root.rglob("*.json")))

    def namespaces(self) -> tuple[str, ...]:
        root = self._records_root()
        if not root.is_dir():
            return ()
        return tuple(sorted(p.name for p in root.iterdir() if p.is_dir()))

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

    def _scan_unlocked(self, query: Query, namespace: str | None) -> Iterator[tuple[Path, Cargo]]:
        for path in self._record_paths(namespace):
            cargo = self._read(path)
            if _matches(cargo, query):
                yield path, cargo

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
    "BloberiaDepot",
    "BloberiaError",
    "CorruptBloberiaDepotError",
    "InvalidBloberiaInputError",
    "PUBLIC_DEPOT_ROOT",
    "TYPE_FILES",
]
