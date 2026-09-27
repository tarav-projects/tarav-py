# $kw: --from Agent.Normal.Model --from Provider.Instance
"""copilot-cli transcript extraction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tarav.l0._core.errors import CliError
from tarav.agent.providers.extractor_common import (
    DialogTurn,
    _string_or_empty,
    _string_or_none,
    format_turns_output,
)


def extract_copilot_cli_chat_session_from_path(
    *,
    path: Path,
    session_id: str | None = None,
    output_format: str = "jsonl",
    raw: bool = False,
) -> str:
    events = load_copilot_cli_events(path)
    resolved_session_id = _resolve_copilot_session_id(
        path,
        events=events,
        session_id=session_id,
    )
    turns = extract_dialog_from_copilot_cli_session(
        events=events,
        session_id=resolved_session_id,
        raw=raw,
    )

    return format_turns_output(turns, output_format)


def extract_dialog_from_copilot_cli_session(
    *,
    events: list[dict[str, Any]],
    session_id: str,
    raw: bool = False,
) -> list[DialogTurn]:
    embedded_session_id = _extract_embedded_session_id(events)
    if embedded_session_id is not None and embedded_session_id != session_id:
        raise CliError(
            f"session id {session_id} does not match Copilot CLI session artifact"
        )

    turns: list[DialogTurn] = []
    for event in events:
        event_type = _string_or_empty(event.get("type"))
        timestamp = _string_or_empty(event.get("timestamp"))
        data = event.get("data")
        if not isinstance(data, dict):
            data = {}

        if raw:
            turns.extend(
                _extract_raw_turns(
                    event_type=event_type,
                    timestamp=timestamp,
                    data=data,
                )
            )
            continue

        clean_turn = _extract_clean_turn(
            event_type=event_type,
            timestamp=timestamp,
            data=data,
        )
        if clean_turn is not None:
            turns.append(clean_turn)

    return turns


def is_copilot_cli_session_path(path: Path) -> bool:
    try:
        events = load_copilot_cli_events(path)
    except CliError:
        return False
    return _extract_embedded_session_id(events) is not None


def infer_copilot_cli_session_id_from_path(path: Path) -> str | None:
    try:
        events = load_copilot_cli_events(path)
    except CliError:
        return _infer_copilot_session_id_from_path_hint(path)

    return _extract_embedded_session_id(events) or _infer_copilot_session_id_from_path_hint(
        path
    )


def load_copilot_cli_events(path: Path) -> list[dict[str, Any]]:
    if path.suffix != ".jsonl":
        raise CliError(f"not a Copilot CLI session artifact: {path}")

    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    events.append(obj)
    except OSError as exc:
        raise CliError(f"unable to read Copilot CLI session artifact {path}: {exc}") from exc

    if not events or _extract_embedded_session_id(events) is None:
        raise CliError(f"not a Copilot CLI session artifact: {path}")

    return events


def _resolve_copilot_session_id(
    path: Path,
    *,
    events: list[dict[str, Any]],
    session_id: str | None,
) -> str:
    embedded_session_id = _extract_embedded_session_id(events)
    inferred_session_id = embedded_session_id or _infer_copilot_session_id_from_path_hint(path)

    if session_id is not None and inferred_session_id is not None and session_id != inferred_session_id:
        raise CliError(
            f"session id {session_id} does not match Copilot CLI artifact provenance: {path}"
        )

    if session_id is not None:
        return session_id
    if inferred_session_id is not None:
        return inferred_session_id

    raise CliError(f"unable to infer Copilot CLI session id from artifact: {path}")


def _extract_embedded_session_id(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        if event.get("type") != "session.start":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        session_id = data.get("sessionId")
        producer = data.get("producer")
        if isinstance(session_id, str) and session_id and producer == "copilot-agent":
            return session_id
    return None


def _infer_copilot_session_id_from_path_hint(path: Path) -> str | None:
    if path.name == "events.jsonl" and path.parent.name:
        return path.parent.name
    if path.suffix == ".jsonl" and path.stem:
        return path.stem
    return None


def _extract_clean_turn(
    *,
    event_type: str,
    timestamp: str,
    data: dict[str, Any],
) -> DialogTurn | None:
    if event_type == "user.message":
        text = _extract_event_text(data.get("content"))
        if text is None:
            return None
        return DialogTurn(role="user", timestamp=timestamp, text=text)

    if event_type == "assistant.message":
        text = _extract_event_text(data.get("content"))
        if text is None:
            return None
        return DialogTurn(role="assistant", timestamp=timestamp, text=text)

    return None


def _extract_raw_turns(
    *,
    event_type: str,
    timestamp: str,
    data: dict[str, Any],
) -> list[DialogTurn]:
    turns: list[DialogTurn] = []

    if event_type == "session.info":
        message = _string_or_none(data.get("message"))
        if message is not None:
            turns.append(DialogTurn(role="info", timestamp=timestamp, text=message))
        return turns

    if event_type == "user.message":
        text = _extract_event_text(data.get("content")) or _extract_event_text(
            data.get("transformedContent")
        )
        if text is not None:
            turns.append(DialogTurn(role="user", timestamp=timestamp, text=text))
        return turns

    if event_type == "assistant.message":
        content = _extract_event_text(data.get("content"))
        if content is not None:
            turns.append(DialogTurn(role="assistant", timestamp=timestamp, text=content))

        reasoning_text = _string_or_none(data.get("reasoningText"))
        if reasoning_text is not None:
            turns.append(DialogTurn(role="assistant", timestamp=timestamp, text=reasoning_text))

        tool_requests = data.get("toolRequests")
        if isinstance(tool_requests, list):
            for tool_request in tool_requests:
                if not isinstance(tool_request, dict):
                    continue
                turns.append(
                    DialogTurn(
                        role="assistant",
                        timestamp=timestamp,
                        text=json.dumps(tool_request, ensure_ascii=False),
                    )
                )
        return turns

    if event_type in {"tool.execution_start", "tool.execution_complete", "skill.invoked"}:
        turns.append(
            DialogTurn(
                role="tool",
                timestamp=timestamp,
                text=json.dumps(
                    {
                        "event": event_type,
                        **data,
                    },
                    ensure_ascii=False,
                ),
            )
        )

    return turns


def _extract_event_text(value: object) -> str | None:
    if isinstance(value, str):
        return value or None

    if not isinstance(value, list):
        return None

    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            if item:
                parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)

    if not parts:
        return None
    return "\n\n".join(parts)
