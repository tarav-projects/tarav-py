# $kw: ^chatlas2-normal-model-cache --from Normalization.Pipeline::Chatlas.Session.Model --from Raw.Archive --note [CT] completed compact Normal Models are disposable session caches whose collections stream independently after creation --supp ^d20260816-5u ^d20260816-6u ^d20260816-8u ^d20260816-9u ^d20260816-10u ^d20260816-11u ^d20260816-12u ^d20260816-13u ^d20260816-14u ^d20260816-15u
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Iterator, Literal
from uuid import uuid4

from filelock import FileLock

from tarav._core.errors import CliError
from tarav._core.persistence import atomic_write_json
from tarav.chatlas.index_query import select_one_chatlas_index_row
from tarav.chatlas.paths import default_chatlas_root

from .messages import chat_message_at
from .model import JsonObject
from .pipeline import (
    NORMAL_MODEL_SCHEMA_VERSION,
    build_normal_model_from_row,
    normal_model_producer_commit,
    transcript_paths,
)


CACHE_CLASS = "tarav.chatlas2.normal_model_cache"
CACHE_SCHEMA_VERSION = 1
CACHE_ROOT = Path("chatlas2") / "model-cache"
LOCK_ROOT = Path("chatlas2") / "locks" / "model-cache"
METADATA_FILENAME = "metadata.json"
EVENTS_FILENAME = "events.jsonl"
CHAT_MESSAGES_FILENAME = "chat-messages.jsonl"
AGENT_LOADED_CONTEXTS_FILENAME = "agent-loaded-contexts.jsonl"
_CACHE_FILES = (
    METADATA_FILENAME,
    EVENTS_FILENAME,
    CHAT_MESSAGES_FILENAME,
    AGENT_LOADED_CONTEXTS_FILENAME,
)
CacheStanding = Literal["FRESH", "STALE", "MISSING"]


@dataclass(frozen=True, slots=True)
class NormalModelCacheReader:
    path: Path
    metadata: JsonObject

    def iter_events(self) -> Iterator[JsonObject]:
        yield from _iter_jsonl(self.path / EVENTS_FILENAME)

    def iter_chat_message_records(
        self,
        *,
        side: Literal["user", "agent"] | None = None,
        text: str | None = None,
        exact: bool = False,
        limit: int | None = None,
    ) -> Iterator[JsonObject]:
        if side not in {None, "user", "agent"}:
            raise ValueError("Chat.Message side must be 'user' or 'agent'")
        if text is not None and not isinstance(text, str):
            raise ValueError("Chat.Message text query must be a string")
        if limit is not None and limit < 0:
            raise ValueError("Chat.Message limit must be non-negative")
        if limit == 0:
            return
        yielded = 0
        for record in _iter_jsonl(self.path / CHAT_MESSAGES_FILENAME):
            message = record.get("message")
            if not isinstance(message, dict):
                raise CliError("Chatlas2 cache has an invalid Chat.Message record")
            if side is not None and message.get("side") != side:
                continue
            if text is not None:
                candidate = message.get("text")
                if not isinstance(candidate, str):
                    continue
                matched = candidate == text if exact else text in candidate
                if not matched:
                    continue
            yield record
            yielded += 1
            if limit is not None and yielded >= limit:
                return

    def iter_agent_loaded_contexts(self) -> Iterator[JsonObject]:
        yield from _iter_jsonl(self.path / AGENT_LOADED_CONTEXTS_FILENAME)

    def load_normal_model(self) -> JsonObject:
        envelope = self.metadata.get("model")
        if not isinstance(envelope, dict):
            raise CliError("Chatlas2 cache metadata has no Normal Model envelope")
        model = deepcopy(envelope)
        model["events"] = list(self.iter_events())
        model["annotations"] = {
            "chat_messages": [
                deepcopy(record["message"])
                for record in self.iter_chat_message_records()
            ],
            "agent_loaded_contexts": list(self.iter_agent_loaded_contexts()),
        }
        return model


def normal_model_cache_path(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> Path:
    identity = _identity_hash(row)
    return _root(chatlas_root) / CACHE_ROOT / identity


def normal_model_cache_status_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> JsonObject:
    path = normal_model_cache_path(row, chatlas_root=chatlas_root)
    expected = _cache_identity(row)
    if not path.exists():
        standing: CacheStanding = "MISSING"
        observed_key = None
    else:
        metadata = _try_read_metadata(path)
        observed_key = metadata.get("cache_key") if metadata is not None else None
        complete = all((path / name).is_file() for name in _CACHE_FILES)
        standing = (
            "FRESH"
            if complete
            and metadata is not None
            and metadata.get("cache_key") == expected["cache_key"]
            else "STALE"
        )
    return {
        "standing": standing,
        "path": str(path),
        "cache_key": expected["cache_key"],
        "observed_cache_key": observed_key,
        "session": {
            "session_id": row.get("session_id"),
            "identity_hash": row.get("identity_hash"),
        },
    }


def open_normal_model_cache_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> NormalModelCacheReader:
    status = normal_model_cache_status_from_row(row, chatlas_root=chatlas_root)
    if status["standing"] != "FRESH":
        raise CliError(
            f"Chatlas2 Normal Model cache is not fresh: {status['standing']}"
        )
    path = Path(str(status["path"]))
    return NormalModelCacheReader(path=path, metadata=_read_metadata(path))


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
        if "raw" in model:
            raise CliError("Chatlas2 refuses to cache a raw-attached Normal Model")
        after = _cache_identity(row)
        if after != before:
            raise CliError("Chatlas2 transcript sources changed during cache creation")
        _validate_model_for_cache(model, identity=identity)
        _replace_cache_directory(path, model=model, cache_identity=after)
    return open_normal_model_cache_from_row(row, chatlas_root=root)


def open_or_materialize_normal_model_cache_from_row(
    row: JsonObject,
    *,
    chatlas_root: Path | None = None,
) -> NormalModelCacheReader:
    status = normal_model_cache_status_from_row(row, chatlas_root=chatlas_root)
    if status["standing"] == "FRESH":
        return open_normal_model_cache_from_row(row, chatlas_root=chatlas_root)
    return materialize_normal_model_cache_from_row(row, chatlas_root=chatlas_root)


def select_normal_model_cache_row(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    chatlas_root: Path | None = None,
) -> JsonObject:
    return select_one_chatlas_index_row(
        command="chatlas2 cache",
        identity_hash=identity_hash,
        providers=("codex", "claude-code"),
        session_id=session_id,
        chatlas_root=chatlas_root,
    )


def normal_model_cache_status(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    chatlas_root: Path | None = None,
) -> JsonObject:
    row = select_normal_model_cache_row(
        session_id=session_id,
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
    )
    return normal_model_cache_status_from_row(row, chatlas_root=chatlas_root)


def materialize_normal_model_cache(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    chatlas_root: Path | None = None,
) -> NormalModelCacheReader:
    row = select_normal_model_cache_row(
        session_id=session_id,
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
    )
    return materialize_normal_model_cache_from_row(row, chatlas_root=chatlas_root)


def open_or_materialize_normal_model_cache(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    chatlas_root: Path | None = None,
) -> NormalModelCacheReader:
    row = select_normal_model_cache_row(
        session_id=session_id,
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
    )
    return open_or_materialize_normal_model_cache_from_row(
        row,
        chatlas_root=chatlas_root,
    )


def load_or_build_normal_model(
    identity_hash: str,
    *,
    chatlas_root: Path | None = None,
) -> JsonObject:
    return open_or_materialize_normal_model_cache(
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
    ).load_normal_model()


def _cache_identity(row: JsonObject) -> JsonObject:
    payload: JsonObject = {
        "session_identity": _identity_hash(row),
        "source_fingerprints": _source_fingerprints(row),
        "normal_model_schema_version": NORMAL_MODEL_SCHEMA_VERSION,
        "commit": normal_model_producer_commit(),
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
            raise CliError(
                f"Chatlas2 cannot fingerprint transcript source {path}"
            ) from exc
        fingerprints.append(
            {
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
            }
        )
    return fingerprints


def _validate_model_for_cache(model: JsonObject, *, identity: str) -> None:
    if model.get("class") != "tarav.chatlas2.normal_model":
        raise CliError("Chatlas2 cache requires a Normal Model")
    if model.get("schema_version") != NORMAL_MODEL_SCHEMA_VERSION:
        raise CliError("Chatlas2 cache received an unsupported Normal Model schema")
    session = model.get("session")
    if not isinstance(session, dict) or session.get("identity_hash") != identity:
        raise CliError("Chatlas2 cache model/session identity mismatch")
    if not isinstance(model.get("events"), list):
        raise CliError("Chatlas2 cache model has no event collection")
    annotations = model.get("annotations")
    if not isinstance(annotations, dict):
        raise CliError("Chatlas2 cache model has no annotations")
    for key in ("chat_messages", "agent_loaded_contexts"):
        if not isinstance(annotations.get(key), list):
            raise CliError(f"Chatlas2 cache model has no {key} collection")


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
        annotations = model["annotations"]
        metadata: JsonObject = {
            "class": CACHE_CLASS,
            "schema_version": CACHE_SCHEMA_VERSION,
            **deepcopy(cache_identity),
            "model": {
                key: deepcopy(model[key])
                for key in ("class", "schema_version", "metadata", "session", "sources")
            },
            "counts": {
                "events": len(model["events"]),
                "chat_messages": len(annotations["chat_messages"]),
                "agent_loaded_contexts": len(annotations["agent_loaded_contexts"]),
            },
        }
        atomic_write_json(
            temporary / METADATA_FILENAME,
            metadata,
            ensure_ascii=False,
        )
        _write_jsonl(temporary / EVENTS_FILENAME, model["events"])
        _write_jsonl(
            temporary / CHAT_MESSAGES_FILENAME,
            (
                {"message": message, "at": chat_message_at(model, message)}
                for message in annotations["chat_messages"]
            ),
        )
        _write_jsonl(
            temporary / AGENT_LOADED_CONTEXTS_FILENAME,
            annotations["agent_loaded_contexts"],
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


def _write_jsonl(path: Path, values: Iterator[object] | list[object]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(
                json.dumps(
                    value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
            )
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _iter_jsonl(path: Path) -> Iterator[JsonObject]:
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise CliError(f"Chatlas2 cannot read cache collection {path}") from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CliError(
                    f"Chatlas2 cache collection {path} has invalid JSON at line {line_number}"
                ) from exc
            if not isinstance(value, dict):
                raise CliError(
                    f"Chatlas2 cache collection {path} line {line_number} is not an object"
                )
            yield value


def _read_metadata(path: Path) -> JsonObject:
    metadata = _try_read_metadata(path)
    if metadata is None:
        raise CliError(f"Chatlas2 cache metadata is invalid at {path}")
    return metadata


def _try_read_metadata(path: Path) -> JsonObject | None:
    try:
        value = json.loads((path / METADATA_FILENAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, dict)
        or value.get("class") != CACHE_CLASS
        or value.get("schema_version") != CACHE_SCHEMA_VERSION
    ):
        return None
    return value


def _identity_hash(row: JsonObject) -> str:
    identity = row.get("identity_hash")
    if not isinstance(identity, str) or not identity:
        raise CliError("Chatlas2 Normal Model cache requires session identity_hash")
    return identity


def _root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


__all__ = [
    "CACHE_CLASS",
    "CACHE_SCHEMA_VERSION",
    "NormalModelCacheReader",
    "load_or_build_normal_model",
    "materialize_normal_model_cache",
    "materialize_normal_model_cache_from_row",
    "normal_model_cache_path",
    "normal_model_cache_status",
    "normal_model_cache_status_from_row",
    "open_normal_model_cache_from_row",
    "open_or_materialize_normal_model_cache",
    "open_or_materialize_normal_model_cache_from_row",
    "select_normal_model_cache_row",
]
