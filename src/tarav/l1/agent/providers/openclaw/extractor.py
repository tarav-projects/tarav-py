# $kw: --from Agent.Normal.Model --from Provider.Instance
"""openclaw transcript extraction."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tarav.l0._core.errors import CliError
from tarav.l1.agent.providers.extractor_common import (
    DialogTurn,
    _string_or_empty,
    format_turns_output,
)
from tarav.l1.agent.providers.pi.extractor import has_pi_session_signature

_OPENCLAW_REPLY_PREFIX = "[[reply_to_current]]"
_OPENCLAW_SENDER_METADATA_RE = re.compile(
    r"\ASender \(untrusted metadata\):\n```json\n.*?\n```\n\n",
    re.DOTALL,
)


def extract_openclaw_chat_session_from_path(
    *,
    path: Path,
    session_id: str | None = None,
    output_format: str = "jsonl",
    raw: bool = False,
) -> str:
    records = load_openclaw_session_records(path)
    resolved_session_id = _resolve_openclaw_session_id(
        path,
        records=records,
        session_id=session_id,
    )
    turns = extract_dialog_from_openclaw_session(
        records=records,
        session_id=resolved_session_id,
        raw=raw,
    )

    return format_turns_output(turns, output_format)


def extract_dialog_from_openclaw_session(
    *,
    records: list[dict[str, Any]],
    session_id: str,
    raw: bool = False,
) -> list[DialogTurn]:
    embedded_session_id = _extract_embedded_session_id(records)
    if embedded_session_id is not None and embedded_session_id != session_id:
        raise CliError(f"session id {session_id} does not match OpenClaw session artifact")

    turns: list[DialogTurn] = []
    for record in records:
        record_type = _string_or_empty(record.get("type"))
        timestamp = _string_or_empty(record.get("timestamp"))

        if raw:
            turns.extend(_extract_raw_turns(record_type=record_type, timestamp=timestamp, record=record))
            continue

        if record_type != "message":
            continue

        message = record.get("message")
        if not isinstance(message, dict):
            continue

        role = _string_or_empty(message.get("role"))
        text = _extract_clean_message_text(role=role, content=message.get("content"))
        if text is None:
            continue

        turns.append(DialogTurn(role=role, timestamp=timestamp, text=text))

    return turns


def is_openclaw_session_path(path: Path) -> bool:
    try:
        records = load_openclaw_session_records(path)
    except CliError:
        return False
    return _extract_embedded_session_id(records) is not None


def infer_openclaw_session_id_from_path(path: Path) -> str | None:
    try:
        records = load_openclaw_session_records(path)
    except CliError:
        return path.stem if path.suffix == ".jsonl" else None
    return _extract_embedded_session_id(records) or (path.stem if path.suffix == ".jsonl" else None)


def load_openclaw_session_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix != ".jsonl":
        raise CliError(f"not an OpenClaw session artifact: {path}")

    records: list[dict[str, Any]] = []
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
                    records.append(obj)
    except OSError as exc:
        raise CliError(f"unable to read OpenClaw session artifact {path}: {exc}") from exc

    if (
        not records
        or _extract_embedded_session_id(records) is None
        or has_pi_session_signature(records)
    ):
        raise CliError(f"not an OpenClaw session artifact: {path}")

    return records


def _resolve_openclaw_session_id(
    path: Path,
    *,
    records: list[dict[str, Any]],
    session_id: str | None,
) -> str:
    embedded_session_id = _extract_embedded_session_id(records)
    inferred_session_id = embedded_session_id or (path.stem if path.suffix == ".jsonl" else None)

    if session_id is not None and inferred_session_id is not None and session_id != inferred_session_id:
        raise CliError(
            f"session id {session_id} does not match OpenClaw artifact provenance: {path}"
        )

    if session_id is not None:
        return session_id
    if inferred_session_id is not None:
        return inferred_session_id
    raise CliError(f"unable to infer OpenClaw session id from artifact: {path}")


def _extract_embedded_session_id(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        if record.get("type") != "session":
            continue
        session_id = record.get("id")
        if isinstance(session_id, str) and session_id:
            return session_id
    return None


def _extract_clean_message_text(*, role: str, content: object) -> str | None:
    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type != "text":
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text:
            continue

        if role == "user":
            text = _strip_openclaw_sender_metadata(text)
        elif role == "assistant":
            text = _strip_openclaw_reply_prefix(text)

        if text:
            parts.append(text)

    if not parts:
        return None
    return "\n\n".join(parts)


def _extract_raw_turns(
    *,
    record_type: str,
    timestamp: str,
    record: dict[str, Any],
) -> list[DialogTurn]:
    turns: list[DialogTurn] = []

    if record_type == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            return turns

        role = _string_or_empty(message.get("role")) or "assistant"
        content = message.get("content")
        if not isinstance(content, list):
            return turns

        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                text = item.get("text")
                if isinstance(text, str) and text:
                    turns.append(DialogTurn(role=role, timestamp=timestamp, text=text))
                continue
            if item_type == "thinking":
                thinking = item.get("thinking")
                if isinstance(thinking, str) and thinking:
                    turns.append(DialogTurn(role=role, timestamp=timestamp, text=thinking))
                continue
            turns.append(DialogTurn(role=role, timestamp=timestamp, text=json.dumps(item, ensure_ascii=False)))
        return turns

    turns.append(
        DialogTurn(
            role="system",
            timestamp=timestamp,
            text=json.dumps(record, ensure_ascii=False),
        )
    )
    return turns


def _strip_openclaw_reply_prefix(text: str) -> str:
    if text.startswith(_OPENCLAW_REPLY_PREFIX):
        text = text[len(_OPENCLAW_REPLY_PREFIX) :]
        text = text.lstrip()
    return text


def _strip_openclaw_sender_metadata(text: str) -> str:
    text = _OPENCLAW_SENDER_METADATA_RE.sub("", text)
    return text
