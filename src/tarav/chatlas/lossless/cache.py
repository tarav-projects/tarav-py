# $kw: ^chatlas2-normal-model-cache --from Normalization.Pipeline::Chatlas.Session.Model --from Raw.Archive --note [CT] completed compact Normal Models expose independent event, message, turn, and loaded-context streams with verified candidate reads and on-demand turn hydration --supp ^c20260816-74u ^c20260816-75u ^c20260816-77u ^c20260816-78u ^c20260816-29u ^c20260816-30u ^c20260816-31u ^c20260816-32u ^c20260816-33u ^c20260816-34u ^c20260816-36u ^c20260816-49u ^c20260816-51u ^c20260816-52u ^c20260816-53u ^c20260816-54u ^c20260816-55u ^c20260816-56u ^c20260816-57u
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Iterable, Iterator, Literal
from uuid import uuid4

from filelock import FileLock

from tarav._core.errors import CliError
from tarav._core.persistence import atomic_write_json
from tarav.chatlas.index_query import select_one_chatlas_index_row
from tarav.chatlas.paths import default_chatlas_root

from .messages import chat_message_at
from .jsonl import (
    JsonlCandidateScan,
    address_pattern,
    iter_jsonl_objects,
    read_jsonl_object_lines,
    serialized_json_string,
)
from .model import JsonObject
from .pipeline import (
    NORMAL_MODEL_SCHEMA_VERSION,
    build_normal_model_from_row,
    normal_model_producer_commit,
    transcript_paths,
)


CACHE_CLASS = "tarav.chatlas2.normal_model_cache"
CACHE_SCHEMA_VERSION = 2
CACHE_ROOT = Path("chatlas2") / "model-cache"
LOCK_ROOT = Path("chatlas2") / "locks" / "model-cache"
METADATA_FILENAME = "metadata.json"
EVENTS_FILENAME = "events.jsonl"
CHAT_MESSAGES_FILENAME = "chat-messages.jsonl"
CHAT_TURNS_FILENAME = "chat-turns.jsonl"
AGENT_LOADED_CONTEXTS_FILENAME = "agent-loaded-contexts.jsonl"
_CACHE_FILES = (
    METADATA_FILENAME,
    EVENTS_FILENAME,
    CHAT_MESSAGES_FILENAME,
    CHAT_TURNS_FILENAME,
    AGENT_LOADED_CONTEXTS_FILENAME,
)
CacheStanding = Literal["FRESH", "STALE", "MISSING"]


@dataclass(frozen=True, slots=True)
class NormalModelCacheReader:
    path: Path
    metadata: JsonObject

    def iter_events(
        self,
        *,
        addresses: Iterable[str] | None = None,
    ) -> Iterator[JsonObject]:
        selected = set(addresses) if addresses is not None else None
        scan = (
            JsonlCandidateScan(pattern=address_pattern("event_address", selected))
            if selected
            else None
        )
        for event in iter_jsonl_objects(self.path / EVENTS_FILENAME, scan=scan):
            if selected is not None and event.get("event_address") not in selected:
                continue
            yield event

    def iter_chat_message_records(
        self,
        *,
        side: Literal["user", "agent"] | None = None,
        text: str | None = None,
        exact: bool = False,
        limit: int | None = None,
        message_addresses: Iterable[str] | None = None,
    ) -> Iterator[JsonObject]:
        if side not in {None, "user", "agent"}:
            raise ValueError("Chat.Message side must be 'user' or 'agent'")
        if text is not None and not isinstance(text, str):
            raise ValueError("Chat.Message text query must be a string")
        if limit is not None and limit < 0:
            raise ValueError("Chat.Message limit must be non-negative")
        if limit == 0:
            return
        selected_addresses = (
            set(message_addresses) if message_addresses is not None else None
        )
        literals: list[str] = []
        if side is not None:
            literals.append(f'"side":"{side}"')
        if text is not None:
            encoded = serialized_json_string(text)
            if encoded is not None:
                literals.append(f'"text":{encoded}' if exact else encoded[1:-1])
        pattern = (
            address_pattern("message_address", selected_addresses)
            if selected_addresses
            else None
        )
        scan = JsonlCandidateScan(literals=tuple(literals), pattern=pattern)
        yielded = 0
        for record in iter_jsonl_objects(
            self.path / CHAT_MESSAGES_FILENAME,
            scan=scan if literals or pattern is not None else None,
        ):
            message = record.get("message")
            if not isinstance(message, dict):
                raise CliError("Chatlas2 cache has an invalid Chat.Message record")
            if side is not None and message.get("side") != side:
                continue
            if (
                selected_addresses is not None
                and message.get("message_address") not in selected_addresses
            ):
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

    def iter_chat_turns(
        self,
        *,
        side: Literal["user", "agent"] | None = None,
        turn_address: str | None = None,
        message_address: str | None = None,
        limit: int | None = None,
    ) -> Iterator[JsonObject]:
        if side not in {None, "user", "agent"}:
            raise ValueError("Chat.Turn side must be 'user' or 'agent'")
        if limit is not None and limit < 0:
            raise ValueError("Chat.Turn limit must be non-negative")
        if limit == 0:
            return
        literals = tuple(
            value
            for value in (
                f'"side":"{side}"' if side is not None else None,
                f'"turn_address":"{turn_address}"'
                if turn_address is not None
                else None,
                f'"message_address":"{message_address}"'
                if message_address is not None
                else None,
            )
            if value is not None
        )
        yielded = 0
        for turn in iter_jsonl_objects(
            self.path / CHAT_TURNS_FILENAME,
            scan=JsonlCandidateScan(literals=literals) if literals else None,
        ):
            if side is not None and turn.get("side") != side:
                continue
            if turn_address is not None and turn.get("turn_address") != turn_address:
                continue
            if message_address is not None and not _turn_contains_message(
                turn, message_address
            ):
                continue
            yield turn
            yielded += 1
            if limit is not None and yielded >= limit:
                return

    def find_chat_turn(
        self,
        *,
        turn_address: str | None = None,
        message_address: str | None = None,
    ) -> JsonObject | None:
        if (turn_address is None) == (message_address is None):
            raise ValueError(
                "Chat.Turn lookup requires exactly one turn or message address"
            )
        matches = list(
            self.iter_chat_turns(
                turn_address=turn_address,
                message_address=message_address,
                limit=2,
            )
        )
        if len(matches) > 1:
            raise CliError("Chatlas2 cache contains ambiguous Chat.Turn membership")
        return matches[0] if matches else None

    def hydrate_chat_turn(self, turn: JsonObject) -> JsonObject:
        event_addresses = _ref_addresses(turn.get("event_refs"), "event_address")
        message_addresses = _ref_addresses(
            turn.get("message_refs"), "message_address", allow_empty=True
        )
        events_by_address = {
            str(event["event_address"]): event
            for event in self.iter_events(addresses=event_addresses)
        }
        if set(events_by_address) != set(event_addresses):
            raise CliError("Chatlas2 Chat.Turn event membership does not resolve")
        message_records = list(
            self.iter_chat_message_records(message_addresses=message_addresses)
        )
        if {
            str(record["message"]["message_address"]) for record in message_records
        } != set(message_addresses):
            raise CliError("Chatlas2 Chat.Turn message membership does not resolve")
        raw_values = self._raw_observation_values(
            [events_by_address[address] for address in event_addresses]
        )
        hydrated_events: list[JsonObject] = []
        for event_address in event_addresses:
            event = events_by_address[event_address]
            observations = event.get("observations")
            raw_observations: list[JsonObject] = []
            if isinstance(observations, list):
                for observation in observations:
                    if not isinstance(observation, dict):
                        continue
                    source_ref = observation.get("source_ref")
                    key = _source_line_key(source_ref)
                    if key is None or key not in raw_values:
                        continue
                    raw_observations.append(
                        {
                            "observed_at": observation.get("observed_at"),
                            "source_ref": deepcopy(source_ref),
                            "value": deepcopy(raw_values[key]),
                        }
                    )
            hydrated_events.append(
                {
                    "event": deepcopy(event),
                    "raw_observations": raw_observations,
                }
            )
        message_by_address = {
            str(record["message"]["message_address"]): record
            for record in message_records
        }
        return {
            "class": "Chat.Turn.Hydration",
            "turn": deepcopy(turn),
            "messages": [
                deepcopy(message_by_address[address]) for address in message_addresses
            ],
            "events": hydrated_events,
        }

    def _raw_observation_values(
        self,
        events: list[JsonObject],
    ) -> dict[tuple[str, int], JsonObject]:
        envelope = self.metadata.get("model")
        sources = envelope.get("sources") if isinstance(envelope, dict) else None
        source_paths = {
            str(source["source_id"]): Path(str(source["path"]))
            for source in sources or []
            if isinstance(source, dict)
            and isinstance(source.get("source_id"), str)
            and isinstance(source.get("path"), str)
        }
        lines_by_source: dict[str, set[int]] = {}
        for event in events:
            observations = event.get("observations")
            if not isinstance(observations, list):
                continue
            for observation in observations:
                source_ref = (
                    observation.get("source_ref")
                    if isinstance(observation, dict)
                    else None
                )
                key = _source_line_key(source_ref)
                if key is not None:
                    lines_by_source.setdefault(key[0], set()).add(key[1])
        values: dict[tuple[str, int], JsonObject] = {}
        for source_id, line_numbers in lines_by_source.items():
            path = source_paths.get(source_id)
            if path is None:
                raise CliError(f"Chatlas2 cache source does not resolve: {source_id}")
            for line_number, value in read_jsonl_object_lines(
                path, line_numbers
            ).items():
                values[(source_id, line_number)] = value
        return values

    def iter_agent_loaded_contexts(self) -> Iterator[JsonObject]:
        yield from iter_jsonl_objects(self.path / AGENT_LOADED_CONTEXTS_FILENAME)

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
            "chat_turns": list(self.iter_chat_turns()),
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
            f"lossless Normal Model cache is not fresh: {status['standing']}"
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
        command="chatlas cache",
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
    for key in ("chat_messages", "chat_turns", "agent_loaded_contexts"):
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
                "chat_turns": len(annotations["chat_turns"]),
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
        _write_jsonl(temporary / CHAT_TURNS_FILENAME, annotations["chat_turns"])
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
        raise CliError("lossless Normal Model cache requires session identity_hash")
    return identity


def _root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


def _turn_contains_message(turn: JsonObject, address: str) -> bool:
    refs = turn.get("message_refs")
    return isinstance(refs, list) and any(
        isinstance(ref, dict) and ref.get("message_address") == address for ref in refs
    )


def _ref_addresses(
    value: object,
    field: str,
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise CliError(f"Chatlas2 Chat.Turn has no {field} membership")
    addresses = [ref.get(field) if isinstance(ref, dict) else None for ref in value]
    if not all(isinstance(address, str) and address for address in addresses):
        raise CliError(f"Chatlas2 Chat.Turn has invalid {field} membership")
    return [str(address) for address in addresses]


def _source_line_key(value: object) -> tuple[str, int] | None:
    if not isinstance(value, dict):
        return None
    source_id = value.get("source_id")
    line = value.get("line")
    if not isinstance(source_id, str) or not isinstance(line, int) or line < 1:
        return None
    return source_id, line


__all__ = [
    "CACHE_CLASS",
    "CACHE_SCHEMA_VERSION",
    "NormalModelCacheReader",
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
