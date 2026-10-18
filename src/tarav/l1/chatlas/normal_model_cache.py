"""Chatlas cache mechanics for canonical Normal Model directories."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from uuid import uuid4

from filelock import FileLock

from tarav.l0._core.errors import CliError
from tarav.l0._core.persistence import atomic_write_json
from tarav.l1.chatlas.index_writer import raw_version
from tarav.l1.chatlas.paths import default_chatlas_root

from .normal_model.model import (
    ChatlasNormalModel,
    COLLECTION_FILES,
    JsonObject,
    MAIN_FILENAME,
)
from .normal_model.pipeline import build_normal_model_from_row


CACHE_SCHEMA = "tarav.chatlas.normal-model-cache"
CACHE_SCHEMA_VERSION = 5
CACHE_ROOT = Path("normal-model")
LOCK_ROOT = CACHE_ROOT / "locks"
CACHE_FILENAME = "cache.json"
PART_FILES = {"main": MAIN_FILENAME, **COLLECTION_FILES}
PARTS = tuple(PART_FILES)


# tarav.breadcrumb 5ca16ac6a344
@dataclass(frozen=True, slots=True)
class CachedPart:
    """One cached part of a Normal Model and the raw data it was built from."""

    name: str
    present: bool
    raw_version: str | None
    current_raw_version: str | None

    @property
    def fresh(self) -> bool:
        return (
            self.present
            and self.raw_version is not None
            and self.raw_version == self.current_raw_version
        )

    @property
    def stale(self) -> bool:
        return self.present and not self.fresh


# tarav.breadcrumb 0221441d98de
# tarav.breadcrumb 1f264fd09a1d
# tarav.breadcrumb 0ad91b2a24d2
class NormalModelCache:
    """What the cache holds for one session, without policy.

    Every part is judged only by the raw data it was built from: it is fresh
    while that `raw_version` is the one the Session Index row names. Reading
    returns what is stored, fresh or not; building rewrites every part.
    """

    def __init__(self, row: JsonObject, *, chatlas_root: Path | None = None) -> None:
        self.row = row
        self.chatlas_root = _root(chatlas_root)
        self.path = self.chatlas_root / CACHE_ROOT / _identity_hash(row)

    @property
    def current_raw_version(self) -> str | None:
        value = self.row.get("raw_version")
        return value if isinstance(value, str) else None

    def parts(self) -> dict[str, CachedPart]:
        built_from = _read_cache_parts(self.path)
        return {
            name: CachedPart(
                name=name,
                present=(self.path / filename).is_file(),
                raw_version=built_from.get(name),
                current_raw_version=self.current_raw_version,
            )
            for name, filename in PART_FILES.items()
        }

    def fresh(self, parts: tuple[str, ...] = PARTS) -> bool:
        standing = self.parts()
        return all(standing[name].fresh for name in _known_parts(parts))

    def model(self) -> ChatlasNormalModel:
        """The stored Model, fresh or not; a missing collection fails when read."""
        return ChatlasNormalModel.open(self.path)

    def build(self) -> ChatlasNormalModel:
        """Normalize the raw data again and cache every part with its version."""
        identity = _identity_hash(self.row)
        lock_path = self.chatlas_root / LOCK_ROOT / f"{identity}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(lock_path):
            before = raw_version(self.row)
            model = build_normal_model_from_row(self.row, include_raw=False)
            if raw_version(self.row) != before:
                raise CliError("chat transcript sources changed during normalization")
            _validate_model(model, identity=identity)
            _replace_cache_directory(
                self.path,
                model=model,
                metadata={
                    "schema": CACHE_SCHEMA,
                    "schema_version": CACHE_SCHEMA_VERSION,
                    "session_identity": identity,
                    "parts": {name: before for name in PARTS},
                },
            )
        return self.model()


# tarav.breadcrumb c08df8634db5
# tarav.breadcrumb e6ee5c5b3615
def provide_normal_model_reader_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
    refresh: bool = False,
    parts: tuple[str, ...] = PARTS,
) -> ChatlasNormalModel:
    """The safe path: the cached Model when the requested parts are fresh, else a build."""
    cache = NormalModelCache(row, chatlas_root=chatlas_root)
    if not refresh and cache.fresh(parts):
        return cache.model()
    return cache.build()


def provide_normal_model_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
    refresh: bool = False,
) -> JsonObject:
    return provide_normal_model_reader_from_row(
        row,
        chatlas_root=chatlas_root,
        refresh=refresh,
    ).load_normal_model()


def _known_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    unknown = set(parts) - set(PARTS)
    if unknown:
        raise ValueError(f"unknown Normal Model parts: {', '.join(sorted(unknown))}")
    return parts


def _validate_model(model: JsonObject, *, identity: str) -> None:
    header, _collections = ChatlasNormalModel.validate_projection(model)
    session = header.get("session")
    if not isinstance(session, dict) or session.get("identity_hash") != identity:
        raise CliError("Normal Model session identity does not match its index row")


def _replace_cache_directory(
    path: Path,
    *,
    model: JsonObject,
    metadata: JsonObject,
) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    backup = path.with_name(f".{path.name}.old-{uuid4().hex}")
    try:
        ChatlasNormalModel.materialize(temporary, model)
        atomic_write_json(temporary / CACHE_FILENAME, metadata, ensure_ascii=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.rename(backup)
        try:
            temporary.rename(path)
        except Exception:
            if backup.exists() and not path.exists():
                backup.rename(path)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _read_cache_parts(path: Path) -> dict[str, str]:
    """The raw version each part was built from; unreadable metadata records none."""
    try:
        value = json.loads((path / CACHE_FILENAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if (
        not isinstance(value, dict)
        or value.get("schema") != CACHE_SCHEMA
        or value.get("schema_version") != CACHE_SCHEMA_VERSION
        or not isinstance(value.get("parts"), dict)
    ):
        return {}
    return {
        name: version
        for name, version in value["parts"].items()
        if name in PART_FILES and isinstance(version, str)
    }


def _identity_hash(row: JsonObject) -> str:
    identity = row.get("identity_hash")
    if not isinstance(identity, str) or not identity:
        raise CliError("Normal Model cache requires a session identity hash")
    return identity


def _root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


__all__ = [
    "CachedPart",
    "NormalModelCache",
    "PARTS",
    "provide_normal_model_from_row",
    "provide_normal_model_reader_from_row",
]
