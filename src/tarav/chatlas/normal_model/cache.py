from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from filelock import FileLock

from tarav._core.errors import CliError
from tarav._core.persistence import atomic_write_json
from tarav.chatlas.paths import default_chatlas_root

from .model import JsonObject
from .pipeline import (
    NORMAL_MODEL_SCHEMA_VERSION,
    build_normal_model_from_row,
    normal_model_producer_commit,
    transcript_paths,
)


CACHE_CLASS = "tarav.chatlas.normal_model_cache"
CACHE_SCHEMA_VERSION = 1
CACHE_ROOT = Path("normal-model") / "cache"
LOCK_ROOT = Path("normal-model") / "locks"
CacheStanding = Literal["FRESH", "STALE", "MISSING"]


def normal_model_cache_path(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> Path:
    return _root(chatlas_root) / CACHE_ROOT / f"{_identity_hash(row)}.json"


def normal_model_cache_status_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> CacheStanding:
    path = normal_model_cache_path(row, chatlas_root=chatlas_root)
    if not path.is_file():
        return "MISSING"
    cached = _read_cache(path, required=False)
    if cached is None or cached.get("cache_key") != _cache_key(row):
        return "STALE"
    return "FRESH"


def read_normal_model_cache_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> JsonObject:
    path = normal_model_cache_path(row, chatlas_root=chatlas_root)
    cached = _read_cache(path, required=True)
    if cached.get("cache_key") != _cache_key(row):
        raise CliError("Normal Model cache is stale")
    model = cached.get("model")
    if not isinstance(model, dict):
        raise CliError(f"Normal Model cache has no model: {path}")
    return model


def materialize_normal_model_cache_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> JsonObject:
    root = _root(chatlas_root)
    path = normal_model_cache_path(row, chatlas_root=root)
    identity = _identity_hash(row)
    lock_path = root / LOCK_ROOT / f"{identity}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(lock_path):
        before = _cache_key(row)
        model = build_normal_model_from_row(row, include_raw=False)
        after = _cache_key(row)
        if before != after:
            raise CliError("chat transcript sources changed during normalization")
        _validate_model(model, identity=identity)
        atomic_write_json(
            path,
            {
                "class": CACHE_CLASS,
                "schema_version": CACHE_SCHEMA_VERSION,
                "cache_key": after,
                "model": model,
            },
            ensure_ascii=False,
        )
    return model


def provide_normal_model_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
    refresh: bool = False,
) -> JsonObject:
    if not refresh and normal_model_cache_status_from_row(
        row, chatlas_root=chatlas_root
    ) == "FRESH":
        return read_normal_model_cache_from_row(row, chatlas_root=chatlas_root)
    return materialize_normal_model_cache_from_row(row, chatlas_root=chatlas_root)


def _cache_key(row: JsonObject) -> str:
    payload = {
        "session_identity": _identity_hash(row),
        "sources": _source_fingerprints(row),
        "normal_model_schema_version": NORMAL_MODEL_SCHEMA_VERSION,
        "producer_commit": normal_model_producer_commit(),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _source_fingerprints(row: JsonObject) -> list[JsonObject]:
    fingerprints: list[JsonObject] = []
    for path in transcript_paths(row):
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
    if model.get("class") != "tarav.chatlas.normal_model":
        raise CliError("normalization did not produce a Normal Model")
    if model.get("schema_version") != NORMAL_MODEL_SCHEMA_VERSION:
        raise CliError("normalization produced an unsupported Normal Model schema")
    session = model.get("session")
    if not isinstance(session, dict) or session.get("identity_hash") != identity:
        raise CliError("Normal Model session identity does not match its index row")


def _read_cache(path: Path, *, required: bool) -> JsonObject | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if required:
            raise CliError(f"invalid Normal Model cache: {path}") from exc
        return None
    if (
        not isinstance(value, dict)
        or value.get("class") != CACHE_CLASS
        or value.get("schema_version") != CACHE_SCHEMA_VERSION
    ):
        if required:
            raise CliError(f"invalid Normal Model cache: {path}")
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
    "provide_normal_model_from_row",
    "read_normal_model_cache_from_row",
]
