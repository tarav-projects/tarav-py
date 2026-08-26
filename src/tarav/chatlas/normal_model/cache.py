from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Literal
from uuid import uuid4

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
CACHE_SCHEMA_VERSION = 2
CACHE_ROOT = Path("normal-model")
LOCK_ROOT = CACHE_ROOT / "locks"
METADATA_FILENAME = "metadata.json"
EVENTS_FILENAME = "events.jsonl"
MESSAGES_FILENAME = "messages.jsonl"
TURNS_FILENAME = "turns.jsonl"
LOADED_CONTEXTS_FILENAME = "loaded-contexts.jsonl"
_COLLECTION_FILES = {
    "events": EVENTS_FILENAME,
    "messages": MESSAGES_FILENAME,
    "turns": TURNS_FILENAME,
    "loaded_contexts": LOADED_CONTEXTS_FILENAME,
}
_MODEL_HEADER_KEYS = ("class", "schema_version", "metadata", "session", "sources")
CacheStanding = Literal["FRESH", "STALE", "MISSING"]


@dataclass(frozen=True, slots=True)
class NormalModelCacheReader:
    path: Path
    metadata: JsonObject

    def iter_events(self) -> Iterator[JsonObject]:
        yield from self._iter_collection("events")

    def iter_messages(self) -> Iterator[JsonObject]:
        yield from self._iter_collection("messages")

    def iter_turns(self) -> Iterator[JsonObject]:
        yield from self._iter_collection("turns")

    def iter_loaded_contexts(self) -> Iterator[JsonObject]:
        yield from self._iter_collection("loaded_contexts")

    def project(
        self,
        *,
        include_messages: bool = False,
        include_turns: bool = False,
        include_loaded_contexts: bool = False,
    ) -> JsonObject:
        model = self._model_header()
        model["events"] = list(self.iter_events())
        if include_messages:
            model["messages"] = list(self.iter_messages())
        if include_turns:
            model["turns"] = list(self.iter_turns())
        if include_loaded_contexts:
            model["loaded_contexts"] = list(self.iter_loaded_contexts())
        return model

    def load_normal_model(self) -> JsonObject:
        return self.project(
            include_messages=True,
            include_turns=True,
            include_loaded_contexts=True,
        )

    def _model_header(self) -> JsonObject:
        model = self.metadata.get("model")
        if not isinstance(model, dict):
            raise CliError(f"Normal Model cache has no model header: {self.path}")
        return deepcopy(model)

    def _iter_collection(self, name: str) -> Iterator[JsonObject]:
        filename = _COLLECTION_FILES[name]
        yield from _iter_jsonl(self.path / filename)


def normal_model_cache_path(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> Path:
    return _root(chatlas_root) / CACHE_ROOT / _identity_hash(row)


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
        for filename in (METADATA_FILENAME, *_COLLECTION_FILES.values())
    ):
        return "STALE"
    metadata = _read_metadata(path, required=False)
    if metadata is None or metadata.get("cache_key") != _cache_identity(row)["cache_key"]:
        return "STALE"
    return "FRESH"


def open_normal_model_cache_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> NormalModelCacheReader:
    path = normal_model_cache_path(row, chatlas_root=chatlas_root)
    if normal_model_cache_status_from_row(row, chatlas_root=chatlas_root) != "FRESH":
        raise CliError(f"Normal Model cache is not fresh: {path}")
    return NormalModelCacheReader(path=path, metadata=_read_metadata(path, required=True))


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
) -> NormalModelCacheReader:
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
    return NormalModelCacheReader(path=path, metadata=_read_metadata(path, required=True))


def provide_normal_model_reader_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
    refresh: bool = False,
) -> NormalModelCacheReader:
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
    for name in _COLLECTION_FILES:
        if not isinstance(model.get(name), list):
            raise CliError(f"Normal Model has no {name} collection")


def _replace_cache_directory(
    path: Path,
    *,
    model: JsonObject,
    cache_identity: JsonObject,
) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    backup = path.with_name(f".{path.name}.old-{uuid4().hex}")
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        metadata: JsonObject = {
            "class": CACHE_CLASS,
            "schema_version": CACHE_SCHEMA_VERSION,
            **deepcopy(cache_identity),
            "model": {key: deepcopy(model[key]) for key in _MODEL_HEADER_KEYS},
            "counts": {
                name: len(model[name]) for name in _COLLECTION_FILES
            },
        }
        atomic_write_json(
            temporary / METADATA_FILENAME,
            metadata,
            ensure_ascii=False,
        )
        for name, filename in _COLLECTION_FILES.items():
            _write_jsonl(temporary / filename, model[name])
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


def _write_jsonl(path: Path, values: object) -> None:
    if not isinstance(values, list):
        raise CliError(f"Normal Model collection is not a list: {path.name}")
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _iter_jsonl(path: Path) -> Iterator[JsonObject]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise CliError(
                        f"Normal Model cache row is not an object: {path}:{line_number}"
                    )
                yield value
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"invalid Normal Model cache stream: {path}") from exc


def _read_metadata(path: Path, *, required: bool) -> JsonObject | None:
    metadata_path = path / METADATA_FILENAME
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if required:
            raise CliError(f"invalid Normal Model cache metadata: {metadata_path}") from exc
        return None
    if (
        not isinstance(value, dict)
        or value.get("class") != CACHE_CLASS
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
    "NormalModelCacheReader",
    "materialize_normal_model_cache_from_row",
    "normal_model_cache_path",
    "normal_model_cache_status_from_row",
    "open_normal_model_cache_from_row",
    "provide_normal_model_from_row",
    "provide_normal_model_reader_from_row",
    "read_normal_model_cache_from_row",
]
