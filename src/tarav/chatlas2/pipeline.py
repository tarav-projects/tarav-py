# $kw: ^chatlas2-pipeline --from Normalization.Pipeline::Chatlas.Session.Model --from Raw.Archive --from Chatlas.Session.Index --from Event.Ref --note [CT] assembly reviews every archived Codex transcript, folds same logical places into current event state, finalizes self-verifying annotation refs, and sorts the retained union chronologically --supp ^c20260814-17u ^c20260814-18u ^c20260814-19u ^c20260815-39u ^c20260815-40u ^c20260815-42u
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import subprocess
from typing import Any

from tarav._core.errors import CliError
from tarav.chatlas.index_query import select_one_chatlas_index_row
from tarav.chatlas.index_writer import archive_versions_for

from .codex import CodexRawModelVersioner, CodexRawNormalizer
from .event_ref import event_ref
from .model import JsonObject


@dataclass(frozen=True, slots=True)
class _TranscriptSource:
    path: Path
    current: bool


def build_normal_model(
    *,
    session_id: str | None = None,
    identity_hash: str | None = None,
    chatlas_root: Path | None = None,
) -> JsonObject:
    row = select_one_chatlas_index_row(
        command="chatlas2 normalize",
        identity_hash=identity_hash,
        providers=("codex",),
        session_id=session_id,
        chatlas_root=chatlas_root,
    )
    return build_normal_model_from_row(row)


def build_normal_model_from_row(row: dict[str, Any]) -> JsonObject:
    if row.get("provider") != "codex":
        raise CliError("Chatlas2 first-pass normalization supports only Codex sessions")

    versioner = CodexRawModelVersioner()
    normalizer = CodexRawNormalizer()
    sources: list[JsonObject] = []
    events_by_address: dict[str, JsonObject] = {}
    chat_messages_by_id: dict[str, JsonObject] = {}
    contexts_by_agent_address: dict[str, JsonObject] = {}
    recognized_source_count = 0

    for transcript_source in _transcript_sources(row):
        path = transcript_source.path
        source_id = _source_id(path)
        raw_model_version = versioner.version(path)
        source: JsonObject = {
            "source_id": source_id,
            "path": str(path),
            "role": "transcript",
            "raw_model_version": raw_model_version,
            "status": "recognized" if raw_model_version is not None else "unrecognized",
        }
        sources.append(source)
        if raw_model_version is None:
            continue
        recognized_source_count += 1
        fragment = normalizer.normalize(
            path,
            source_id=source_id,
            raw_model_version=raw_model_version,
        )
        current_addresses = {
            str(event["event_address"])
            for event in fragment.events
        }
        if transcript_source.current:
            for message_id, message in list(chat_messages_by_id.items()):
                addresses = message.get("event_addresses")
                if isinstance(addresses, list) and current_addresses.intersection(
                    str(address) for address in addresses
                ):
                    del chat_messages_by_id[message_id]
            for address in current_addresses:
                contexts_by_agent_address.pop(address, None)
        for event in fragment.events:
            address = str(event["event_address"])
            existing = events_by_address.get(address)
            if existing is None:
                events_by_address[address] = deepcopy(event)
                continue
            observations = _merged_observations(existing, event)
            if transcript_source.current:
                replacement = deepcopy(event)
                replacement["observations"] = observations
                events_by_address[address] = replacement
            else:
                existing["observations"] = observations
        for message in fragment.chat_messages:
            chat_messages_by_id[str(message["message_id"])] = deepcopy(message)
        for context in fragment.agent_loaded_contexts:
            contexts_by_agent_address[str(context["agent_event_address"])] = deepcopy(
                context
            )

    if recognized_source_count == 0:
        raise CliError(
            "Chatlas2 found no recognized Codex transcript artifact for the selected session"
        )

    events = sorted(events_by_address.values(), key=_event_sort_key)
    event_by_address = {str(event["event_address"]): event for event in events}
    event_order = {
        str(event["event_address"]): index for index, event in enumerate(events)
    }
    chat_messages = sorted(
        (
            _finalize_chat_message(message, event_by_address=event_by_address)
            for message in chat_messages_by_id.values()
        ),
        key=lambda message: _annotation_sort_key(message, event_order=event_order),
    )
    contexts = sorted(
        (
            _finalize_loaded_context(context, event_by_address=event_by_address)
            for context in contexts_by_agent_address.values()
        ),
        key=lambda context: _context_sort_key(context, event_order=event_order),
    )
    return {
        "class": "tarav.chatlas2.normal_model",
        "schema_version": 2,
        "metadata": {"commit": _repository_commit()},
        "session": {
            "provider": "codex",
            "session_id": row.get("session_id"),
            "identity_hash": row.get("identity_hash"),
        },
        "sources": sources,
        "events": events,
        "annotations": {
            "chat_messages": chat_messages,
            "agent_loaded_contexts": contexts,
        },
    }


def transcript_paths(row: dict[str, Any]) -> tuple[Path, ...]:
    return tuple(source.path for source in _transcript_sources(row))


def _transcript_sources(row: dict[str, Any]) -> tuple[_TranscriptSource, ...]:
    current_paths = _version_transcript_paths(row)
    all_paths: dict[str, Path] = {}
    for version in archive_versions_for(row):
        for path in _version_transcript_paths(version):
            all_paths[str(path)] = path
    for path in current_paths:
        all_paths[str(path)] = path
    current_keys = {str(path) for path in current_paths}
    return tuple(
        _TranscriptSource(path=path, current=key in current_keys)
        for key, path in sorted(
            all_paths.items(),
            key=lambda item: (item[0] in current_keys, item[0]),
        )
    )


def _version_transcript_paths(version: dict[str, Any]) -> tuple[Path, ...]:
    artifacts = version.get("backing_artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
    candidates = [*artifacts, version.get("primary_backing_artifact")]
    paths: dict[str, Path] = {}
    for artifact in candidates:
        if not isinstance(artifact, dict) or artifact.get("role") != "transcript":
            continue
        path_text = artifact.get("path")
        if not isinstance(path_text, str) or not path_text:
            continue
        path = Path(path_text).expanduser().resolve()
        paths[str(path)] = path
    return tuple(paths[key] for key in sorted(paths))


def _source_id(path: Path) -> str:
    return f"source-{sha256(str(path).encode('utf-8')).hexdigest()[:16]}"


def _event_sort_key(event: JsonObject) -> tuple[datetime, str]:
    timestamp = event.get("started_at")
    if not isinstance(timestamp, str):
        return datetime.max.replace(tzinfo=timezone.utc), str(
            event.get("event_address")
        )
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.max.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc), str(event.get("event_address"))


def _annotation_sort_key(
    annotation: JsonObject,
    *,
    event_order: dict[str, int],
) -> int:
    refs = annotation.get("event_refs")
    if not isinstance(refs, list) or not refs or not isinstance(refs[0], dict):
        return len(event_order)
    return event_order.get(str(refs[0].get("event_address")), len(event_order))


def _context_sort_key(
    context: JsonObject,
    *,
    event_order: dict[str, int],
) -> int:
    ref = context.get("agent_event_ref")
    if not isinstance(ref, dict):
        return len(event_order)
    return event_order.get(str(ref.get("event_address")), len(event_order))


def _merged_observations(first: JsonObject, second: JsonObject) -> list[object]:
    merged: list[object] = []
    for event in (first, second):
        observations = event.get("observations")
        if not isinstance(observations, list):
            continue
        for observation in observations:
            if observation not in merged:
                merged.append(deepcopy(observation))
    return merged


def _finalize_chat_message(
    message: JsonObject,
    *,
    event_by_address: dict[str, JsonObject],
) -> JsonObject:
    result = deepcopy(message)
    addresses = result.pop("event_addresses", None)
    result["event_refs"] = _refs_for_addresses(
        addresses,
        event_by_address=event_by_address,
    )
    return result


def _finalize_loaded_context(
    context: JsonObject,
    *,
    event_by_address: dict[str, JsonObject],
) -> JsonObject:
    result = deepcopy(context)
    agent_address = result.pop("agent_event_address", None)
    if not isinstance(agent_address, str) or agent_address not in event_by_address:
        raise CliError("Chatlas2 loaded context has an unresolved agent event place")
    result["agent_event_ref"] = event_ref(event_by_address[agent_address])
    result["event_refs"] = _refs_for_addresses(
        result.pop("event_addresses", None),
        event_by_address=event_by_address,
    )
    return result


def _refs_for_addresses(
    value: object,
    *,
    event_by_address: dict[str, JsonObject],
) -> list[JsonObject]:
    if not isinstance(value, list):
        raise CliError("Chatlas2 annotation has no event-address membership")
    refs: list[JsonObject] = []
    for address in value:
        if not isinstance(address, str) or address not in event_by_address:
            raise CliError("Chatlas2 annotation event place does not resolve")
        refs.append(event_ref(event_by_address[address]))
    return refs


def _repository_commit() -> str | None:
    repository = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


__all__ = ["build_normal_model", "build_normal_model_from_row", "transcript_paths"]
