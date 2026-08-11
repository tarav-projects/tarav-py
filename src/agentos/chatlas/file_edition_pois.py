# $kw: ^file-edition-event-refs --from Chatlas.Session.Model --from Session.Event.Tape --note [CT] file-edition evidence persists Event.Ref objects because POIs outlive the materialization that produced them ^c20260728-16u
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Sequence

from agentos.chatlas.event_ref import event_ref
from agentos.chatlas.index_query import (
    select_materialization_row,
    select_one_chatlas_index_row,
)
from agentos.chatlas.views import load_chatlas_session_model


@dataclass(frozen=True)
class FileEditionPoi:
    poi_id: str
    file: str
    region: str | None
    event_refs: tuple[dict[str, Any], ...]


DetectorFunction = Callable[[dict[str, Any]], list[FileEditionPoi]]


@dataclass(frozen=True)
class FileEditionDetector:
    name: str
    detect: DetectorFunction


_PATCH_FILE_RE = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (?P<path>.+?)\s*$",
    re.MULTILINE,
)
_PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (?P<path>.+?)\s*$", re.MULTILINE)
_FILE_WRITE_PATH_KEYS = {
    "write": "file_path",
    "edit": "file_path",
    "notebookedit": "notebook_path",
}


def _chat_events(session_model: dict[str, Any]) -> list[dict[str, Any]]:
    chat = session_model.get("chat")
    if not isinstance(chat, dict):
        return []
    events = chat.get("events")
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def _event_refs_by_invocation(
    events: Iterable[dict[str, Any]],
) -> dict[str, tuple[dict[str, Any], ...]]:
    refs: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        invocation_ref = event.get("tool_invocation_ref")
        if not isinstance(invocation_ref, str) or not isinstance(
            event.get("event_address"), str
        ):
            continue
        refs.setdefault(invocation_ref, []).append(event_ref(event))
    return {key: tuple(value) for key, value in refs.items()}


def _event_arguments(event: dict[str, Any]) -> object:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    tool_input = payload.get("input")
    if not isinstance(tool_input, dict):
        return None
    return tool_input.get("arguments")


def _tool_name(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    tool_name = payload.get("tool_name")
    return tool_name if isinstance(tool_name, str) else None


def _refs_for_call(
    event: dict[str, Any],
    refs_by_invocation: dict[str, tuple[dict[str, Any], ...]],
) -> tuple[dict[str, Any], ...]:
    invocation_ref = event.get("tool_invocation_ref")
    if isinstance(invocation_ref, str):
        refs = refs_by_invocation.get(invocation_ref)
        if refs:
            return refs
    return (event_ref(event),) if isinstance(event.get("event_address"), str) else ()


def _candidate(
    *,
    file: str,
    event_refs: tuple[dict[str, Any], ...],
    region: str | None = None,
) -> FileEditionPoi:
    return FileEditionPoi(
        poi_id="",
        file=file,
        region=region,
        event_refs=event_refs,
    )


def _detect_apply_patch(session_model: dict[str, Any]) -> list[FileEditionPoi]:
    events = _chat_events(session_model)
    refs_by_invocation = _event_refs_by_invocation(events)
    pois: list[FileEditionPoi] = []
    for event in events:
        tool_name = _tool_name(event)
        if event.get("kind") != "tool.call" or tool_name is None:
            continue
        if tool_name.rsplit(".", 1)[-1].casefold() != "apply_patch":
            continue
        arguments = _event_arguments(event)
        if not isinstance(arguments, str):
            continue
        paths = [
            *(match.group("path") for match in _PATCH_FILE_RE.finditer(arguments)),
            *(match.group("path") for match in _PATCH_MOVE_RE.finditer(arguments)),
        ]
        event_refs = _refs_for_call(event, refs_by_invocation)
        for path in paths:
            pois.append(_candidate(file=path, event_refs=event_refs))
    return pois


def _find_string_key(value: object, key: str) -> str | None:
    if isinstance(value, dict):
        candidate = value.get(key)
        if isinstance(candidate, str):
            return candidate
        for nested in value.values():
            found = _find_string_key(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_string_key(nested, key)
            if found is not None:
                return found
    return None


def _detect_file_write(session_model: dict[str, Any]) -> list[FileEditionPoi]:
    events = _chat_events(session_model)
    refs_by_invocation = _event_refs_by_invocation(events)
    pois: list[FileEditionPoi] = []
    for event in events:
        tool_name = _tool_name(event)
        if event.get("kind") != "tool.call" or tool_name is None:
            continue
        path_key = _FILE_WRITE_PATH_KEYS.get(tool_name.casefold())
        if path_key is None:
            continue
        path = _find_string_key(_event_arguments(event), path_key)
        if path is None:
            continue
        pois.append(
            _candidate(
                file=path,
                event_refs=_refs_for_call(event, refs_by_invocation),
            )
        )
    return pois


DEFAULT_FILE_EDITION_DETECTORS = (
    FileEditionDetector(name="tool.apply_patch", detect=_detect_apply_patch),
    FileEditionDetector(name="tool.file-write", detect=_detect_file_write),
)


def _normalized_path(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).as_posix()


def _matches_file(observed: str, requested: str) -> bool:
    observed_path = _normalized_path(observed)
    requested_path = _normalized_path(requested)
    if observed_path == requested_path:
        return True
    return (
        requested_path.startswith("/")
        and "/" in observed_path
        and requested_path.endswith(f"/{observed_path.lstrip('/')}")
    )


def _stable_poi(poi: FileEditionPoi, *, session_id: object) -> FileEditionPoi:
    identity = json.dumps(
        {
            "session": session_id,
            "file": poi.file,
            "region": poi.region,
            "event_refs": list(poi.event_refs),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return FileEditionPoi(
        poi_id=hashlib.sha256(identity.encode()).hexdigest()[:10],
        file=poi.file,
        region=poi.region,
        event_refs=poi.event_refs,
    )


def _poi_payload(poi: FileEditionPoi) -> dict[str, object]:
    return {
        "poi_id": poi.poi_id,
        "file": poi.file,
        "region": poi.region,
        "event_refs": list(poi.event_refs),
    }


def _event_refs_key(event_refs: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    return tuple(
        json.dumps(ref, sort_keys=True, separators=(",", ":")) for ref in event_refs
    )


def file_edition_pois_from_session_model(
    session_model: dict[str, Any],
    *,
    file: str | None = None,
    limit: int | None = None,
    detectors: Sequence[FileEditionDetector] = DEFAULT_FILE_EDITION_DETECTORS,
) -> dict[str, object]:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    session = session_model.get("session")
    session_id = session.get("session_id") if isinstance(session, dict) else None
    candidates = [
        _stable_poi(poi, session_id=session_id)
        for detector in detectors
        for poi in detector.detect(session_model)
        if file is None or _matches_file(poi.file, file)
    ]
    unique = {
        (poi.file, poi.region, _event_refs_key(poi.event_refs)): poi
        for poi in candidates
    }
    pois = sorted(
        unique.values(),
        key=lambda poi: (poi.file, poi.region or "", _event_refs_key(poi.event_refs)),
    )
    if limit is not None:
        pois = pois[:limit]
    return {
        "session": session_id,
        "file": file,
        "detectors": [detector.name for detector in detectors],
        "pois": [_poi_payload(poi) for poi in pois],
    }


def chatlas_file_edition_pois(
    *,
    session: str,
    file: str | None = None,
    limit: int | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    index_row = select_one_chatlas_index_row(
        command="chatlas file-edition-pois",
        session_id=session,
        chatlas_root=chatlas_root,
    )
    materialization_row = select_materialization_row(index_row)
    session_model = load_chatlas_session_model(
        materialization_row,
        chatlas_root=chatlas_root,
    )
    return file_edition_pois_from_session_model(
        session_model,
        file=file,
        limit=limit,
    )


__all__ = [
    "DEFAULT_FILE_EDITION_DETECTORS",
    "FileEditionDetector",
    "FileEditionPoi",
    "chatlas_file_edition_pois",
    "file_edition_pois_from_session_model",
]
