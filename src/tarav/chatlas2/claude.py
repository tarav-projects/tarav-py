# $kw: ^chatlas2-claude-v1 --from Normalization.Pipeline::Chatlas.Session.Model --from Session.Event.Tape --from Event.Ref --note [CT] Claude structural recognition recovers direct human prompt variants and mixed legacy-shaped records while preserving ambiguous timed records as unresolved and loaded request input conservatively --supp ^c20260814-21u ^c20260814-23u ^c20260815-2u ^c20260815-7u ^c20260815-21u ^c20260815-39u ^c20260815-55u ^c20260815-56u ^c20260815-59u ^c20260815-64u ^c20260815-65u ^d20260816-0u ^d20260816-1u ^c20260816-20u
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
_AGENT_RECORD_TYPES = frozenset({"assistant", "progress", "system"})
_AGENT_ORIGIN_KINDS = frozenset(
    {"agent", "assistant", "auto-continuation", "system", "task-notification", "tool"}
)
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
        include_raw: bool = False,
    ) -> NormalFragment:
        return _normalize(
            path,
            source_id=source_id,
            raw_model_version=raw_model_version,
            supported_raw_model_versions=self.supported_raw_model_versions,
            is_primary_user_message=_is_prompt_source_primary_user_message,
            include_raw=include_raw,
        )


class ClaudeLegacyRawNormalizer:
    supported_raw_model_versions = frozenset({CLAUDE_LEGACY_RAW_MODEL_VERSION})

    def normalize(
        self,
        path: Path,
        *,
        source_id: str,
        raw_model_version: str,
        include_raw: bool = False,
    ) -> NormalFragment:
        return _normalize(
            path,
            source_id=source_id,
            raw_model_version=raw_model_version,
            supported_raw_model_versions=self.supported_raw_model_versions,
            is_primary_user_message=_is_legacy_primary_user_message,
            include_raw=include_raw,
        )


def _normalize(
    path: Path,
    *,
    source_id: str,
    raw_model_version: str,
    supported_raw_model_versions: frozenset[str],
    is_primary_user_message: Callable[[JsonObject], bool],
    include_raw: bool,
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
        message_side = _chat_message_side(
            record.value,
            is_primary_user_message=is_primary_user_message,
        )
        message_text = (
            _chat_message_text(
                record.value,
                is_primary_user_message=is_primary_user_message,
            )
            if message_side is not None
            else None
        )
        started_at = _event_started_at(record)
        event_address = compute_event_address(
            provider="claude-code",
            scope=session_scope,
            place=place,
        )
        origin = _event_origin(
            record.value,
            is_primary_user_message=is_primary_user_message,
        )
        event: JsonObject = {
            "class": {
                "user": "User.Event",
                "agent": "Agent.Event",
                "unresolved": "Unresolved.Event",
            }[origin],
            "event_address": event_address,
            "started_at": started_at,
            "origin": origin,
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
        if message_text is not None:
            event["content"] = {"text": message_text}
        event["event_hash"] = compute_event_hash(event)
        events.append(event)
        if isinstance(native_uuid, str) and native_uuid:
            event_address_by_uuid[native_uuid] = event_address

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
                    "text": message_text,
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
        raw={"records": [record.value for record in records]}
        if include_raw
        else None,
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
    if "promptSource" not in value:
        return value.get("isMeta") is not True and _is_legacy_primary_user_message(
            value
        )
    prompt_source = value.get("promptSource")
    if prompt_source not in _PRIMARY_PROMPT_SOURCES and not (
        prompt_source == "suggestion_accepted" and _has_human_origin(value)
    ):
        return False
    return _user_message_text(value) is not None


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


def _human_queued_command(value: JsonObject) -> JsonObject | None:
    attachment = value.get("attachment")
    if value.get("type") != "attachment" or not isinstance(attachment, dict):
        return None
    origin = attachment.get("origin")
    prompt = attachment.get("prompt")
    if (
        attachment.get("type") != "queued_command"
        or not isinstance(origin, dict)
        or origin.get("kind") != "human"
        or not isinstance(prompt, str)
        or not prompt
    ):
        return None
    return attachment


def _is_human_queued_command(value: JsonObject) -> bool:
    return _human_queued_command(value) is not None


def _has_human_origin(value: JsonObject) -> bool:
    origin = value.get("origin")
    if isinstance(origin, dict) and origin.get("kind") == "human":
        return True
    attachment = value.get("attachment")
    attachment_origin = (
        attachment.get("origin") if isinstance(attachment, dict) else None
    )
    return (
        isinstance(attachment_origin, dict)
        and attachment_origin.get("kind") == "human"
    )


def _origin_kind(value: JsonObject) -> str | None:
    origin = value.get("origin")
    if isinstance(origin, dict) and isinstance(origin.get("kind"), str):
        return origin["kind"]
    attachment = value.get("attachment")
    attachment_origin = (
        attachment.get("origin") if isinstance(attachment, dict) else None
    )
    if isinstance(attachment_origin, dict) and isinstance(
        attachment_origin.get("kind"), str
    ):
        return attachment_origin["kind"]
    return None


def _event_origin(
    value: JsonObject,
    *,
    is_primary_user_message: Callable[[JsonObject], bool],
) -> str:
    if (
        is_primary_user_message(value)
        or _is_human_queued_command(value)
        or _has_human_origin(value)
    ):
        return "user"
    if _is_agent_origin(value):
        return "agent"
    return "unresolved"


def _is_agent_origin(value: JsonObject) -> bool:
    record_type = value.get("type")
    if record_type in _AGENT_RECORD_TYPES:
        return True
    if _origin_kind(value) in _AGENT_ORIGIN_KINDS:
        return True
    if record_type != "user":
        return False
    if value.get("sourceToolAssistantUUID") is not None:
        return True
    if value.get("isCompactSummary") is True or value.get("isMeta") is True:
        return True
    if value.get("promptSource") in {"sdk", "system"}:
        return True
    message = value.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content == "/compact" or content.startswith(_LEGACY_HARNESS_PREFIXES)
    if not isinstance(content, list):
        return False
    return any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    )


def _event_started_at(record: _RawRecord) -> str:
    queued = _human_queued_command(record.value)
    if queued is not None:
        queued_at = queued.get("timestamp")
        if isinstance(queued_at, str) and queued_at:
            return queued_at
    if record.observed_at is None:
        raise CliError("Chatlas2 Claude timed event has no observed timestamp")
    return record.observed_at


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
    if _is_human_queued_command(value):
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
        text = _user_message_text(value) or ""
        command_args = _command_args_text(text)
        return command_args or text
    queued = _human_queued_command(value)
    if queued is not None:
        prompt = queued.get("prompt")
        return prompt if isinstance(prompt, str) else ""
    return _assistant_text(value)


def _user_message_text(value: JsonObject) -> str | None:
    if value.get("type") != "user":
        return None
    message = value.get("message")
    if not isinstance(message, dict) or message.get("role") != "user":
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    texts = [
        block.get("text")
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    return "".join(texts) if texts else None


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
        if (
            ancestor.value.get("type") == "user"
            and isinstance(ancestor.value.get("message"), dict)
        ) or _is_human_queued_command(ancestor.value):
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
