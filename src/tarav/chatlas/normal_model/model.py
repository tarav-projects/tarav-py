"""The Chatlas Normal Model aggregate and its canonical directory representation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from tarav.l0._core.errors import CliError
from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import DirectoryRecord, TypeShip
from tarav.chatlas.identity import CHATLAS_WORKFLOW_SHIP

from .records import AgentLoadedContext, ChatMessage, ChatTurn, event_record


JsonObject = dict[str, Any]
NORMAL_MODEL_SCHEMA_VERSION = 1
MAIN_FILENAME = "main.json"
EVENTS_FILENAME = "events.jsonl"
MESSAGES_FILENAME = "messages.jsonl"
TURNS_FILENAME = "turns.jsonl"
LOADED_CONTEXTS_FILENAME = "loaded-contexts.jsonl"
COLLECTION_FILES = {
    "events": EVENTS_FILENAME,
    "messages": MESSAGES_FILENAME,
    "turns": TURNS_FILENAME,
    "loaded_contexts": LOADED_CONTEXTS_FILENAME,
}
_HEADER_KEYS = ("type", "schema_version", "metadata", "session", "sources", "counts")


class _ClosedRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class NormalModelMetadata(_ClosedRecord):
    commit: str | None


class NormalModelSession(_ClosedRecord):
    provider: Literal["codex", "claude-code"]
    session_id: str = Field(min_length=1)
    identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class NormalModelSource(_ClosedRecord):
    source_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    role: Literal["transcript"]
    raw_model_version: str | None
    status: Literal["recognized", "unrecognized"]


class NormalModelCounts(_ClosedRecord):
    events: int = Field(ge=0)
    messages: int = Field(ge=0)
    turns: int = Field(ge=0)
    loaded_contexts: int = Field(ge=0)


# tarav.breadcrumb fbcaa106132b41dfa0beda40d4dd1bf512c0dbe8ae3a8392a45aaec0037950e7
class ChatlasNormalModel(DirectoryRecord):
    """One provider-neutral chat tape stored as a streamable directory Record."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('64389d49-e0fd-4c26-8343-abf4880b3e33'),
            name='Chatlas.Normal.Model',
            workflow=CHATLAS_WORKFLOW_SHIP,
        )
    class RecordInterface(DirectoryRecord.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Chatlas.Normal.Model"]
        schema_version: Literal[1]
        metadata: NormalModelMetadata
        session: NormalModelSession
        sources: list[NormalModelSource] = Field(min_length=1)
        counts: NormalModelCounts

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> ChatlasNormalModel:
        result = super()._from_record(record_data)
        result._counts = record_data.counts.model_copy(deep=True)
        return result

    @property
    def counts(self) -> NormalModelCounts:
        return self._counts.model_copy(deep=True)

    @classmethod
    def open(cls, directory: str | Path) -> ChatlasNormalModel:
        path = Path(directory).expanduser().absolute()
        try:
            value = json.loads((path / MAIN_FILENAME).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CliError(f"invalid Normal Model entry: {path / MAIN_FILENAME}") from exc
        result = cls.from_record(value)
        result.source = path / MAIN_FILENAME
        return result

    @classmethod
    def materialize(
        cls,
        directory: str | Path,
        model: Mapping[str, object],
    ) -> ChatlasNormalModel:
        """Write only the canonical semantic representation into a new directory."""

        path = Path(directory).expanduser().absolute()
        if "raw" in model:
            raise CliError("raw diagnostic fragments are not part of a materialized Normal Model")
        header, collections = cls.validate_projection(model)
        path.mkdir(parents=True, exist_ok=False)
        atomic_write_json(path / MAIN_FILENAME, header, ensure_ascii=False)
        for name, filename in COLLECTION_FILES.items():
            _write_jsonl(path / filename, collections[name])
        return cls.open(path)

    @classmethod
    def validate_projection(
        cls,
        model: Mapping[str, object],
    ) -> tuple[JsonObject, dict[str, list[JsonObject]]]:
        if not isinstance(model, Mapping):
            raise CliError("Normal Model projection is not an object")
        unexpected = set(model) - {*_HEADER_KEYS, *COLLECTION_FILES, "raw"}
        if unexpected:
            raise CliError(
                "Normal Model projection has unexpected fields: "
                + ", ".join(sorted(unexpected))
            )
        header = {key: deepcopy(model.get(key)) for key in _HEADER_KEYS}
        record = cls.from_record(header)
        collections: dict[str, list[JsonObject]] = {}
        for name in COLLECTION_FILES:
            values = model.get(name)
            if not isinstance(values, list):
                raise CliError(f"Normal Model has no {name} collection")
            collections[name] = [_validated_collection_row(name, value) for value in values]
        counts = record.counts
        for name, values in collections.items():
            if getattr(counts, name) != len(values):
                raise CliError(f"Normal Model {name} count does not match its collection")
        return record.to_record(), collections

    def iter_events(self) -> Iterator[JsonObject]:
        yield from self._iter_collection("events")

    def iter_messages(self) -> Iterator[JsonObject]:
        yield from self._iter_collection("messages")

    def iter_turns(self) -> Iterator[JsonObject]:
        yield from self._iter_collection("turns")

    def iter_loaded_contexts(self) -> Iterator[JsonObject]:
        yield from self._iter_collection("loaded_contexts")

    def model_header(self) -> JsonObject:
        return self.to_record()

    def project(
        self,
        *,
        include_messages: bool = False,
        include_turns: bool = False,
        include_loaded_contexts: bool = False,
    ) -> JsonObject:
        model = self.model_header()
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

    def _iter_collection(self, name: str) -> Iterator[JsonObject]:
        for value in _iter_jsonl(self.directory / COLLECTION_FILES[name]):
            yield _validated_collection_row(name, value)

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "schema_version": NORMAL_MODEL_SCHEMA_VERSION,
            "metadata": {"commit": None},
            "session": {
                "provider": "codex",
                "session_id": "example-session",
                "identity_hash": "0" * 64,
            },
            "sources": [
                {
                    "source_id": "source-example",
                    "path": "/example/transcript.jsonl",
                    "role": "transcript",
                    "raw_model_version": "example.raw-model",
                    "status": "recognized",
                }
            ],
            "counts": {
                "events": 0,
                "messages": 0,
                "turns": 0,
                "loaded_contexts": 0,
            },
        }


def _validated_collection_row(name: str, value: object) -> JsonObject:
    if name == "events":
        return event_record(value).to_record()
    if name == "messages":
        return ChatMessage.from_record(value).to_record()
    if name == "turns":
        return ChatTurn.from_record(value).to_record()
    return AgentLoadedContext.from_record(value).to_record()


def _write_jsonl(path: Path, values: list[JsonObject]) -> None:
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
                        f"Normal Model row is not an object: {path}:{line_number}"
                    )
                yield value
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"invalid Normal Model stream: {path}") from exc


@dataclass(frozen=True, slots=True)
class NormalFragment:
    events: tuple[JsonObject, ...]
    chat_messages: tuple[JsonObject, ...]
    loaded_contexts: tuple[JsonObject, ...]
    raw: object | None = None


__all__ = [
    "ChatlasNormalModel",
    "COLLECTION_FILES",
    "JsonObject",
    "MAIN_FILENAME",
    "NORMAL_MODEL_SCHEMA_VERSION",
    "NormalFragment",
]
