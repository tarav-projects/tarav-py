# $kw: ^chatlas2-pipeline --from Normalization.Pipeline::Chatlas.Session.Model --from Raw.Archive --from Chatlas.Session.Index --note [CT] assembly reviews every archived Codex transcript, collapses only same-position exact observations, and sorts the retained union chronologically --supp ^c20260814-17u ^c20260814-18u ^c20260814-19u
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import subprocess
from typing import Any

from tarav._core.errors import CliError
from tarav.chatlas.index_query import select_one_chatlas_index_row
from tarav.chatlas.index_writer import archive_versions_for

from .codex import CodexRawModelVersioner, CodexRawNormalizer
from .model import JsonObject


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
    events_by_id: dict[str, JsonObject] = {}
    chat_messages_by_id: dict[str, JsonObject] = {}
    contexts_by_agent_event: dict[str, JsonObject] = {}
    recognized_source_count = 0

    for path in _transcript_paths(row):
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
        for event in fragment.events:
            event_id = str(event["event_id"])
            existing = events_by_id.get(event_id)
            if existing is None:
                events_by_id[event_id] = deepcopy(event)
                continue
            existing_observations = existing["observations"]
            if isinstance(existing_observations, list):
                existing_observations.extend(deepcopy(event["observations"]))
        for message in fragment.chat_messages:
            chat_messages_by_id[str(message["message_id"])] = deepcopy(message)
        for context in fragment.agent_loaded_contexts:
            contexts_by_agent_event[str(context["agent_event_id"])] = deepcopy(context)

    if recognized_source_count == 0:
        raise CliError(
            "Chatlas2 found no recognized Codex transcript artifact for the selected session"
        )

    events = sorted(events_by_id.values(), key=_event_sort_key)
    event_order = {str(event["event_id"]): index for index, event in enumerate(events)}
    chat_messages = sorted(
        chat_messages_by_id.values(),
        key=lambda message: _annotation_sort_key(message, event_order=event_order),
    )
    contexts = sorted(
        contexts_by_agent_event.values(),
        key=lambda context: event_order.get(
            str(context["agent_event_id"]), len(events)
        ),
    )
    return {
        "class": "tarav.chatlas2.normal_model",
        "schema_version": 1,
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


def _transcript_paths(row: dict[str, Any]) -> tuple[Path, ...]:
    paths: dict[str, Path] = {}
    versions = [row, *archive_versions_for(row)]
    for version in versions:
        artifacts = version.get("backing_artifacts")
        if not isinstance(artifacts, list):
            artifacts = []
        primary = version.get("primary_backing_artifact")
        candidates = [*artifacts, primary]
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
        return datetime.max.replace(tzinfo=timezone.utc), str(event.get("event_id"))
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.max.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc), str(event.get("event_id"))


def _annotation_sort_key(
    annotation: JsonObject,
    *,
    event_order: dict[str, int],
) -> int:
    event_ids = annotation.get("event_ids")
    if not isinstance(event_ids, list) or not event_ids:
        return len(event_order)
    return event_order.get(str(event_ids[0]), len(event_order))


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


__all__ = ["build_normal_model", "build_normal_model_from_row"]
