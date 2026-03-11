from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chat.extractors.common import (
    DialogTurn,
    format_turns_jsonl,
    format_turns_markdown,
    format_unix_ms_timestamp,
)


def extract_opencode_chat_session_from_path(
    *,
    path: Path,
    session_id: str | None = None,
    output_format: str = "jsonl",
    raw: bool = False,
) -> str:
    _validate_opencode_session_path(path)
    resolved_session_id = _resolve_opencode_session_id(path, session_id=session_id)
    db_path = _resolve_opencode_db_path(path)
    turns = extract_dialog_from_opencode_session(
        db_path=db_path,
        session_id=resolved_session_id,
        raw=raw,
    )

    if output_format == "markdown":
        return format_turns_markdown(turns)
    return format_turns_jsonl(turns)


def extract_dialog_from_opencode_session(
    *,
    db_path: Path,
    session_id: str,
    raw: bool = False,
) -> list[DialogTurn]:
    messages = _load_opencode_messages(db_path=db_path, session_id=session_id)
    if not messages:
        raise CliError(f"no OpenCode message data found for session {session_id}")

    turns: list[DialogTurn] = []
    for message in messages:
        role = message["role"]
        if role not in {"user", "assistant"}:
            continue

        if raw:
            turns.extend(_extract_raw_turns(role=role, parts=message["parts"], fallback_time=message["time_created"]))
            continue

        text_parts = [
            _extract_text_part(part["data"])
            for part in message["parts"]
            if _extract_text_part(part["data"]) is not None
        ]
        if not text_parts:
            continue

        turns.append(
            DialogTurn(
                role=role,
                timestamp=format_unix_ms_timestamp(message["time_created"]),
                text="\n\n".join(text_parts),
            )
        )

    return turns


def is_opencode_session_path(path: Path) -> bool:
    if path.name == "opencode.db":
        return _looks_like_opencode_db(path)

    if path.suffix != ".json" or not path.stem.startswith("ses_"):
        return False

    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return False

    return isinstance(obj, list)


def infer_opencode_session_id_from_path(path: Path) -> str | None:
    if path.suffix == ".json" and path.stem.startswith("ses_"):
        return path.stem
    return None


def _validate_opencode_session_path(path: Path) -> None:
    if not is_opencode_session_path(path):
        raise CliError(f"not an OpenCode session artifact: {path}")


def _resolve_opencode_session_id(path: Path, *, session_id: str | None) -> str:
    inferred_session_id = infer_opencode_session_id_from_path(path)
    if session_id is not None and inferred_session_id is not None and session_id != inferred_session_id:
        raise CliError(
            f"session id {session_id} does not match OpenCode artifact provenance: {path}"
        )

    resolved_session_id = session_id or inferred_session_id
    if resolved_session_id is not None:
        return resolved_session_id

    raise CliError(
        f"session id is required when extracting from OpenCode database path: {path}"
    )


def _resolve_opencode_db_path(path: Path) -> Path:
    if path.name == "opencode.db":
        return path

    for parent in path.parents:
        candidate = parent / "opencode.db"
        if candidate.exists():
            return candidate

    raise CliError(f"unable to locate opencode.db for session artifact: {path}")


def _looks_like_opencode_db(path: Path) -> bool:
    try:
        connection = sqlite3.connect(str(path))
    except sqlite3.Error:
        return False

    try:
        cursor = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        table_names = {row[0] for row in cursor.fetchall()}
    except sqlite3.Error:
        return False
    finally:
        connection.close()

    return {"session", "message", "part"}.issubset(table_names)


def _load_opencode_messages(
    *,
    db_path: Path,
    session_id: str,
) -> list[dict[str, Any]]:
    try:
        connection = sqlite3.connect(str(db_path))
    except sqlite3.Error as exc:
        raise CliError(f"unable to read OpenCode database {db_path}: {exc}") from exc

    try:
        cursor = connection.execute(
            """
            SELECT m.id, m.time_created, m.data, p.time_created, p.data
            FROM message m
            LEFT JOIN part p ON p.message_id = m.id
            WHERE m.session_id = ?
            ORDER BY m.time_created, p.time_created, p.id
            """,
            (session_id,),
        )
        rows = cursor.fetchall()
    except sqlite3.Error as exc:
        raise CliError(f"unable to query OpenCode messages for session {session_id}: {exc}") from exc
    finally:
        connection.close()

    messages: list[dict[str, Any]] = []
    current_message_id: str | None = None
    current_message: dict[str, Any] | None = None

    for message_id, message_time_created, message_data_raw, part_time_created, part_data_raw in rows:
        if not isinstance(message_data_raw, str):
            continue

        if current_message_id != message_id:
            message_data = _parse_json_object(message_data_raw)
            if message_data is None:
                current_message = None
                current_message_id = message_id
                continue

            current_message = {
                "id": message_id,
                "role": message_data.get("role", ""),
                "time_created": message_time_created,
                "parts": [],
            }
            messages.append(current_message)
            current_message_id = message_id

        if current_message is None or not isinstance(part_data_raw, str):
            continue

        part_data = _parse_json_object(part_data_raw)
        if part_data is None:
            continue

        current_message["parts"].append(
            {
                "time_created": part_time_created,
                "data": part_data,
            }
        )

    return messages


def _extract_raw_turns(
    *,
    role: str,
    parts: list[dict[str, Any]],
    fallback_time: int | None,
) -> list[DialogTurn]:
    turns: list[DialogTurn] = []
    for part in parts:
        part_data = part["data"]
        text = _stringify_opencode_part(part_data)
        if text is None:
            continue
        turns.append(
            DialogTurn(
                role=role,
                timestamp=format_unix_ms_timestamp(part.get("time_created") or fallback_time),
                text=text,
            )
        )
    return turns


def _extract_text_part(part_data: dict[str, Any]) -> str | None:
    if part_data.get("type") != "text":
        return None
    text = part_data.get("text")
    if not isinstance(text, str) or not text:
        return None
    return text


def _stringify_opencode_part(part_data: dict[str, Any]) -> str | None:
    text = part_data.get("text")
    if isinstance(text, str) and text:
        return text
    return json.dumps(part_data, ensure_ascii=False)


def _parse_json_object(raw_text: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj

