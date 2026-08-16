# $kw: ^chatlas2-claude-v1 --from Normalization.Pipeline::Chatlas.Session.Model --from Session.Event.Tape --from Event.Ref --note [CT] Claude structural recognition partitions direct user-message mappings while shared mechanics preserve timed transcript records and loaded request input conservatively --supp ^c20260814-21u ^c20260814-23u ^c20260815-2u ^c20260815-7u ^c20260815-21u ^c20260815-39u ^c20260815-55u ^c20260815-56u ^c20260815-59u ^c20260815-64u ^c20260815-65u
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Callable

from tarav._core.errors import CliError

from .event_ref import compute_event_address, compute_event_hash
from .message_ref import compute_chat_message_address
from .model import JsonObject, NormalFragment


CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION = "claude.transcript.1ecc"
CLAUDE_LEGACY_RAW_MODEL_VERSION = "claude.transcript.b17b"
_PRIMARY_PROMPT_SOURCES = frozenset({"typed", "queued"})
_LEGACY_HARNESS_PREFIXES = (
    "<bash-input>",
    "<bash-stdout>",
    "<command-message>",
    "<command-name>",
    "<local-command-",
    "<skill-context",
    "<system-reminder>",
    "<task-notification>",
    "Base directory for this skill:",
)
_COMMAND_ARGS_PATTERN = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)


@dataclass(frozen=True, slots=True)
class _RawRecord:
    record_index: int
    line: int
    observed_at: str | None
    value: JsonObject


class ClaudeRawModelVersioner:
    def version(self, path: Path) -> str | None:
        try:
            records = _read_records(path)
        except (OSError, ValueError):
            return None
        if not records:
            return None
        session_ids: set[str] = set()
        transcript_count = 0
        has_prompt_source = False
        for record in records:
            value = record.value
            record_type = value.get("type")
            session_id = value.get("sessionId")
            if not isinstance(record_type, str) or not record_type:
                return None
            if session_id is not None and (
                not isinstance(session_id, str) or not session_id
            ):
                return None
            if record_type not in {"user", "assistant"}:
                if isinstance(session_id, str):
                    session_ids.add(session_id)
                continue
            if not isinstance(session_id, str) or not session_id:
                return None
            session_ids.add(session_id)
            if not _is_transcript_record(value):
                return None
            transcript_count += 1
            if record_type == "user" and "promptSource" in value:
                has_prompt_source = True
        if len(session_ids) != 1 or transcript_count == 0:
            return None
        if has_prompt_source:
            return CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION
        return CLAUDE_LEGACY_RAW_MODEL_VERSION


class ClaudePromptSourceRawNormalizer:
    supported_raw_model_versions = frozenset(
        {CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION}
    )

    def normalize(
        self,
        path: Path,
        *,
        source_id: str,
        raw_model_version: str,
    ) -> NormalFragment:
        return _normalize(
            path,
            source_id=source_id,
            raw_model_version=raw_model_version,
            supported_raw_model_versions=self.supported_raw_model_versions,
            is_primary_user_message=_is_prompt_source_primary_user_message,
        )


class ClaudeLegacyRawNormalizer:
    supported_raw_model_versions = frozenset({CLAUDE_LEGACY_RAW_MODEL_VERSION})

    def normalize(
        self,
        path: Path,
        *,
        source_id: str,
        raw_model_version: str,
    ) -> NormalFragment:
        return _normalize(
            path,
            source_id=source_id,
            raw_model_version=raw_model_version,
            supported_raw_model_versions=self.supported_raw_model_versions,
            is_primary_user_message=_is_legacy_primary_user_message,
        )


def _normalize(
    path: Path,
    *,
    source_id: str,
    raw_model_version: str,
    supported_raw_model_versions: frozenset[str],
    is_primary_user_message: Callable[[JsonObject], bool],
) -> NormalFragment:
    if raw_model_version not in supported_raw_model_versions:
        raise CliError(
            "Chatlas2 Claude normalizer does not support raw model version "
            f"{raw_model_version!r}"
        )
    try:
        records = _read_records(path)
    except (OSError, ValueError) as exc:
        raise CliError(
            f"cannot normalize Chatlas2 Claude artifact {path}: {exc}"
        ) from exc

    session_scope = _session_scope(records)
    events: list[JsonObject] = []
    chat_messages: list[JsonObject] = []
    event_address_by_uuid: dict[str, str] = {}
    raw_by_uuid: dict[str, _RawRecord] = {}

    for record in records:
        native_uuid = record.value.get("uuid")
        if isinstance(native_uuid, str) and native_uuid:
            raw_by_uuid[native_uuid] = record
        if record.observed_at is None:
            continue
        place = (
            {"uuid": native_uuid}
            if isinstance(native_uuid, str) and native_uuid
            else {"record_index": record.record_index}
        )
        event_address = compute_event_address(
            provider="claude-code",
            scope=session_scope,
            place=place,
        )
        origin = "user" if is_primary_user_message(record.value) else "agent"
        event: JsonObject = {
            "class": "User.Event" if origin == "user" else "Agent.Event",
            "event_address": event_address,
            "started_at": record.observed_at,
            "origin": origin,
            "record": record.value,
            "observations": [
                {
                    "observed_at": record.observed_at,
                    "source_ref": {
                        "source_id": source_id,
                        "record_index": record.record_index,
                        "line": record.line,
                    },
                }
            ],
        }
        event["event_hash"] = compute_event_hash(event)
        events.append(event)
        if isinstance(native_uuid, str) and native_uuid:
            event_address_by_uuid[native_uuid] = event_address

        message_side = _chat_message_side(
            record.value,
            is_primary_user_message=is_primary_user_message,
        )
        if message_side is not None:
            chat_messages.append(
                {
                    "class": "Chat.Message",
                    "message_address": compute_chat_message_address(
                        provider="claude-code",
                        scope=session_scope,
                        place=place,
                    ),
                    "side": message_side,
                    "text": _chat_message_text(
                        record.value,
                        is_primary_user_message=is_primary_user_message,
                    ),
                    "event_addresses": [event_address],
                }
            )

    loaded_contexts: list[JsonObject] = []
    context_by_request: dict[str, tuple[str, ...]] = {}
    for record in records:
        if record.observed_at is None or record.value.get("type") != "assistant":
            continue
        native_uuid = record.value.get("uuid")
        request_id = record.value.get("requestId")
        if not isinstance(native_uuid, str) or native_uuid not in event_address_by_uuid:
            continue
        if not isinstance(request_id, str) or not request_id:
            continue
        if request_id not in context_by_request:
            context_address = _nearest_user_input_address(
                record,
                raw_by_uuid=raw_by_uuid,
                event_address_by_uuid=event_address_by_uuid,
            )
            context_by_request[request_id] = (
                (context_address,) if context_address is not None else ()
            )
        context = context_by_request[request_id]
        if context:
            loaded_contexts.append(
                {
                    "class": "Agent.Loaded.Context",
                    "agent_event_address": event_address_by_uuid[native_uuid],
                    "event_addresses": list(context),
                }
            )

    return NormalFragment(
        events=tuple(events),
        chat_messages=tuple(chat_messages),
        agent_loaded_contexts=tuple(loaded_contexts),
    )


def _read_records(path: Path) -> list[_RawRecord]:
    records: list[_RawRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"line {line_number} is invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number} is not a JSON object")
            timestamp = value.get("timestamp")
            observed_at = timestamp if isinstance(timestamp, str) and timestamp else None
            records.append(
                _RawRecord(
                    record_index=len(records) + 1,
                    line=line_number,
                    observed_at=observed_at,
                    value=value,
                )
            )
    return records


def _is_transcript_record(value: JsonObject) -> bool:
    return (
        isinstance(value.get("uuid"), str)
        and bool(value["uuid"])
        and isinstance(value.get("timestamp"), str)
        and bool(value["timestamp"])
        and isinstance(value.get("version"), str)
        and bool(value["version"])
        and isinstance(value.get("message"), dict)
    )


def _session_scope(records: list[_RawRecord]) -> str:
    session_ids = {
        value
        for record in records
        if isinstance((value := record.value.get("sessionId")), str) and value
    }
    if len(session_ids) != 1:
        raise CliError(
            "Chatlas2 Claude artifact must contain exactly one native session scope"
        )
    return next(iter(session_ids))


def _is_prompt_source_primary_user_message(value: JsonObject) -> bool:
    message = value.get("message")
    return (
        value.get("type") == "user"
        and value.get("promptSource") in _PRIMARY_PROMPT_SOURCES
        and isinstance(message, dict)
        and message.get("role") == "user"
        and isinstance(message.get("content"), str)
    )


def _is_legacy_primary_user_message(value: JsonObject) -> bool:
    message = value.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if (
        value.get("type") != "user"
        or not isinstance(message, dict)
        or message.get("role") != "user"
        or not isinstance(content, str)
        or not content
        or value.get("sourceToolAssistantUUID") is not None
        or value.get("isCompactSummary") is True
        or content == "/compact"
    ):
        return False
    if not content.startswith(_LEGACY_HARNESS_PREFIXES):
        return True
    return (
        content.startswith(("<command-message>", "<command-name>"))
        and bool(_command_args_text(content))
    )


def _command_args_text(content: str) -> str:
    match = _COMMAND_ARGS_PATTERN.search(content)
    return match.group(1).strip() if match is not None else ""


def _chat_message_side(
    value: JsonObject,
    *,
    is_primary_user_message: Callable[[JsonObject], bool],
) -> str | None:
    if is_primary_user_message(value):
        return "user"
    if value.get("type") != "assistant":
        return None
    return "agent" if _assistant_text(value) else None


def _chat_message_text(
    value: JsonObject,
    *,
    is_primary_user_message: Callable[[JsonObject], bool],
) -> str:
    if is_primary_user_message(value):
        message = value.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            return ""
        command_args = _command_args_text(content)
        return command_args or content
    return _assistant_text(value)


def _assistant_text(value: JsonObject) -> str:
    message = value.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return ""
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


def _nearest_user_input_address(
    record: _RawRecord,
    *,
    raw_by_uuid: dict[str, _RawRecord],
    event_address_by_uuid: dict[str, str],
) -> str | None:
    parent = record.value.get("parentUuid")
    visited: set[str] = set()
    while isinstance(parent, str) and parent and parent not in visited:
        visited.add(parent)
        ancestor = raw_by_uuid.get(parent)
        if ancestor is None:
            return None
        if ancestor.value.get("type") == "user" and isinstance(
            ancestor.value.get("message"), dict
        ):
            return event_address_by_uuid.get(parent)
        parent = ancestor.value.get("parentUuid")
    return None


__all__ = [
    "CLAUDE_LEGACY_RAW_MODEL_VERSION",
    "CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION",
    "ClaudeLegacyRawNormalizer",
    "ClaudePromptSourceRawNormalizer",
    "ClaudeRawModelVersioner",
]
