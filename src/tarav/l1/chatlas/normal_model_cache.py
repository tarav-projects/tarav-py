"""Chatlas cache mechanics for canonical Normal Model directories."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Literal
from uuid import uuid4

from filelock import FileLock

from tarav.l0._core.errors import CliError
from tarav.l0._core.persistence import atomic_write_json
from tarav.l1.chatlas.paths import default_chatlas_root

from .normal_model.model import (
    ChatlasNormalModel,
    COLLECTION_FILES,
    JsonObject,
    MAIN_FILENAME,
    NORMAL_MODEL_SCHEMA_VERSION,
)
from .normal_model.pipeline import (
    build_normal_model_from_row,
    normal_model_producer_commit,
)
from tarav.l1.chatlas.index_writer import transcript_sources


CACHE_SCHEMA = "tarav.chatlas.normal-model-cache"
CACHE_SCHEMA_VERSION = 4
CACHE_ROOT = Path("normal-model")
LOCK_ROOT = CACHE_ROOT / "locks"
CACHE_FILENAME = "cache.json"
CacheStanding = Literal["FRESH", "STALE", "MISSING"]


def normal_model_cache_path(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> Path:
    return _root(chatlas_root) / CACHE_ROOT / _identity_hash(row)


# tarav.breadcrumb 0221441d98de
def normal_model_cache_status_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> CacheStanding:
    path = normal_model_cache_path(row, chatlas_root=chatlas_root)
    if not path.exists():
        return "MISSING"
    if not path.is_dir() or not all(
        (path / filename).is_file()
        for filename in (MAIN_FILENAME, *COLLECTION_FILES.values(), CACHE_FILENAME)
    ):
        return "STALE"
    metadata = _read_cache_metadata(path, required=False)
    if metadata is None or metadata.get("cache_key") != _cache_identity(row)["cache_key"]:
        return "STALE"
    try:
        ChatlasNormalModel.open(path)
    except (CliError, ValueError):
        return "STALE"
    return "FRESH"


def open_normal_model_cache_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> ChatlasNormalModel:
    path = normal_model_cache_path(row, chatlas_root=chatlas_root)
    if normal_model_cache_status_from_row(row, chatlas_root=chatlas_root) != "FRESH":
        raise CliError(f"Normal Model cache is not fresh: {path}")
    return ChatlasNormalModel.open(path)


def read_normal_model_cache_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> JsonObject:
    return open_normal_model_cache_from_row(
        row,
        chatlas_root=chatlas_root,
    ).load_normal_model()


def materialize_normal_model_cache_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> ChatlasNormalModel:
    root = _root(chatlas_root)
    path = normal_model_cache_path(row, chatlas_root=root)
    identity = _identity_hash(row)
    lock_path = root / LOCK_ROOT / f"{identity}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(lock_path):
        before = _cache_identity(row)
        model = build_normal_model_from_row(row, include_raw=False)
        after = _cache_identity(row)
        if before != after:
            raise CliError("chat transcript sources changed during normalization")
        _validate_model(model, identity=identity)
        _replace_cache_directory(path, model=model, cache_identity=after)
    return ChatlasNormalModel.open(path)


def provide_normal_model_reader_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
    refresh: bool = False,
) -> ChatlasNormalModel:
    if not refresh and normal_model_cache_status_from_row(
        row, chatlas_root=chatlas_root
    ) == "FRESH":
        return open_normal_model_cache_from_row(row, chatlas_root=chatlas_root)
    return materialize_normal_model_cache_from_row(row, chatlas_root=chatlas_root)


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


def _cache_identity(row: JsonObject) -> JsonObject:
    payload: JsonObject = {
        "session_identity": _identity_hash(row),
        "source_fingerprints": _source_fingerprints(row),
        "normal_model_schema_version": NORMAL_MODEL_SCHEMA_VERSION,
        "producer_commit": normal_model_producer_commit(),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {**payload, "cache_key": f"sha256:{sha256(encoded).hexdigest()}"}


def _source_fingerprints(row: JsonObject) -> list[JsonObject]:
    fingerprints: list[JsonObject] = []
    for path in (source.path for source in transcript_sources(row)):
        try:
            stat = path.stat()
        except OSError as exc:
            raise CliError(f"cannot fingerprint chat transcript source: {path}") from exc
        fingerprints.append(
            {
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
            }
        )
    return fingerprints


def _validate_model(model: JsonObject, *, identity: str) -> None:
    header, _collections = ChatlasNormalModel.validate_projection(model)
    session = header.get("session")
    if not isinstance(session, dict) or session.get("identity_hash") != identity:
        raise CliError("Normal Model session identity does not match its index row")


def _replace_cache_directory(
    path: Path,
    *,
    model: JsonObject,
    cache_identity: JsonObject,
) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    backup = path.with_name(f".{path.name}.old-{uuid4().hex}")
    try:
        ChatlasNormalModel.materialize(temporary, model)
        atomic_write_json(
            temporary / CACHE_FILENAME,
            {
                "schema": CACHE_SCHEMA,
                "schema_version": CACHE_SCHEMA_VERSION,
                **deepcopy(cache_identity),
            },
            ensure_ascii=False,
        )
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


def _read_cache_metadata(path: Path, *, required: bool) -> JsonObject | None:
    metadata_path = path / CACHE_FILENAME
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if required:
            raise CliError(f"invalid Normal Model cache metadata: {metadata_path}") from exc
        return None
    if (
        not isinstance(value, dict)
        or value.get("schema") != CACHE_SCHEMA
        or value.get("schema_version") != CACHE_SCHEMA_VERSION
    ):
        if required:
            raise CliError(f"invalid Normal Model cache metadata: {metadata_path}")
        return None
    return value


def _identity_hash(row: JsonObject) -> str:
    identity = row.get("identity_hash")
    if not isinstance(identity, str) or not identity:
        raise CliError("Normal Model cache requires a session identity hash")
    return identity


def _root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


__all__ = [
    "materialize_normal_model_cache_from_row",
    "normal_model_cache_path",
    "normal_model_cache_status_from_row",
    "open_normal_model_cache_from_row",
    "provide_normal_model_from_row",
    "provide_normal_model_reader_from_row",
    "read_normal_model_cache_from_row",
]
