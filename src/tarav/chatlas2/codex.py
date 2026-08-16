# $kw: ^chatlas2-codex-v1 --from Normalization.Pipeline::Chatlas.Session.Model --from Session.Event.Tape --from Event.Ref --note [CT] Codex structural recognition dispatches only its declared opaque raw-model identity, addresses raw places independently from content and version labels, and resolves origin and loaded context conservatively --supp ^c20260814-21u ^c20260814-23u ^c20260815-2u ^c20260815-21u ^c20260815-37u ^c20260815-38u ^c20260815-39u ^c20260815-64u ^c20260815-65u
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from tarav._core.errors import CliError

from .event_ref import compute_event_address, compute_event_hash
from .message_ref import compute_chat_message_address
from .model import JsonObject, NormalFragment


CODEX_RAW_MODEL_VERSION = "codex.rollout.5f98"

_AGENT_TOP_LEVEL_TYPES = {
    "compacted",
    "inter_agent_communication_metadata",
    "session_meta",
    "turn_context",
    "world_state",
}
_HARNESS_USER_PREFIXES = (
    "# AGENTS.md",
    "<INSTRUCTIONS>",
    "<collaboration_mode>",
    "<environment_context>",
    "<goal_context>",
    "<permissions",
    "<skill-context",
    "<skill>",
    "<system-reminder>",
    "<turn_aborted>",
)
_INPUT_RESPONSE_TYPES = {
    "custom_tool_call_output",
    "function_call_output",
}
_GENERATED_RESPONSE_TYPES = {
    "custom_tool_call",
    "function_call",
    "reasoning",
}


@dataclass(frozen=True, slots=True)
class _RawRecord:
    record_index: int
    line: int
    observed_at: str
    value: JsonObject


class CodexRawModelVersioner:
    def version(self, path: Path) -> str | None:
        try:
            records = _read_records(path)
        except (OSError, ValueError):
            return None
        if not records:
            return None
        has_session_meta = False
        for record in records:
            value = record.value
            record_type = value.get("type")
            payload = value.get("payload")
            if not isinstance(record_type, str) or not record_type:
                return None
            if not isinstance(payload, dict):
                return None
            if record_type == "session_meta" and isinstance(payload.get("id"), str):
                has_session_meta = True
        return CODEX_RAW_MODEL_VERSION if has_session_meta else None


class CodexRawNormalizer:
    supported_raw_model_versions = frozenset({CODEX_RAW_MODEL_VERSION})

    def normalize(
        self,
        path: Path,
        *,
        source_id: str,
        raw_model_version: str,
    ) -> NormalFragment:
        if raw_model_version not in self.supported_raw_model_versions:
            raise CliError(
                "Chatlas2 Codex normalizer does not support raw model version "
                f"{raw_model_version!r}"
            )
        try:
            records = _read_records(path)
        except (OSError, ValueError) as exc:
            raise CliError(
                f"cannot normalize Chatlas2 Codex artifact {path}: {exc}"
            ) from exc

        session_scope = _session_scope(records)
        response_message_keys = _response_message_keys(records)
        events: list[JsonObject] = []
        chat_messages: list[JsonObject] = []
        loaded_contexts: list[JsonObject] = []
        pending_context: list[str] = []
        active_context: tuple[str, ...] = ()
        previous_generated = False

        for record in records:
            event_address = compute_event_address(
                provider="codex",
                scope=session_scope,
                place={"record_index": record.record_index},
            )
            event = {
                "class": _event_class(record.value),
                "event_address": event_address,
                "started_at": record.observed_at,
                "origin": _event_origin(record.value),
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

            message_side = _chat_message_side(
                record.value,
                response_message_keys=response_message_keys,
            )
            if message_side is not None:
                chat_messages.append(
                    {
                        "class": "Chat.Message",
                        "message_address": compute_chat_message_address(
                            provider="codex",
                            scope=session_scope,
                            place={"record_index": record.record_index},
                        ),
                        "side": message_side,
                        "event_addresses": [event_address],
                    }
                )

            if _is_context_input(record.value):
                pending_context.append(event_address)
                active_context = ()
                previous_generated = False
                continue

            if _is_generated(record.value):
                if pending_context:
                    active_context = tuple(pending_context)
                    pending_context.clear()
                elif not previous_generated:
                    active_context = ()
                if active_context:
                    loaded_contexts.append(
                        {
                            "class": "Agent.Loaded.Context",
                            "agent_event_address": event_address,
                            "event_addresses": list(active_context),
                        }
                    )
                previous_generated = True
                continue

            active_context = ()
            previous_generated = False

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
            observed_at = value.get("timestamp")
            if not isinstance(observed_at, str) or not observed_at:
                raise ValueError(f"line {line_number} has no timestamp")
            records.append(
                _RawRecord(
                    record_index=len(records) + 1,
                    line=line_number,
                    observed_at=observed_at,
                    value=value,
                )
            )
    return records


def _session_scope(records: list[_RawRecord]) -> str:
    session_ids = {
        payload["id"]
        for record in records
        if record.value.get("type") == "session_meta"
        and isinstance((payload := record.value.get("payload")), dict)
        and isinstance(payload.get("id"), str)
        and payload["id"]
    }
    if len(session_ids) != 1:
        raise CliError(
            "Chatlas2 Codex artifact must contain exactly one native session scope"
        )
    return next(iter(session_ids))


def _event_origin(record: JsonObject) -> str:
    record_type = record.get("type")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return "unresolved"
    if record_type in _AGENT_TOP_LEVEL_TYPES:
        return "agent"
    if record_type == "event_msg":
        payload_type = payload.get("type")
        if payload_type == "user_message":
            text = payload.get("message")
            if isinstance(text, str) and not _is_harness_text(text):
                return "user"
        return "agent" if isinstance(payload_type, str) else "unresolved"
    if record_type != "response_item":
        return "unresolved"
    payload_type = payload.get("type")
    if not isinstance(payload_type, str):
        return "unresolved"
    if payload_type != "message":
        return "agent"
    role = payload.get("role")
    if role == "user":
        return "agent" if _is_harness_message(payload) else "user"
    if role in {"assistant", "developer", "system", "tool"}:
        return "agent"
    return "unresolved"


def _event_class(record: JsonObject) -> str:
    return {
        "user": "User.Event",
        "agent": "Agent.Event",
        "unresolved": "Unresolved.Event",
    }[_event_origin(record)]


def _response_message_keys(records: list[_RawRecord]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for record in records:
        payload = record.value.get("payload")
        if record.value.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        if payload.get("type") != "message":
            continue
        role = payload.get("role")
        text = _message_text(payload)
        if isinstance(role, str) and text is not None:
            keys.add((role, text))
    return keys


def _chat_message_side(
    record: JsonObject,
    *,
    response_message_keys: set[tuple[str, str]],
) -> str | None:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    record_type = record.get("type")
    if record_type == "response_item" and payload.get("type") == "message":
        role = payload.get("role")
        if role == "user" and not _is_harness_message(payload):
            return "user"
        if role == "assistant":
            return "agent"
        return None
    if record_type != "event_msg":
        return None
    payload_type = payload.get("type")
    text = payload.get("message")
    if not isinstance(text, str):
        return None
    if payload_type == "user_message":
        if _is_harness_text(text) or ("user", text) in response_message_keys:
            return None
        return "user"
    if payload_type == "agent_message":
        if ("assistant", text) in response_message_keys:
            return None
        return "agent"
    return None


def _is_context_input(record: JsonObject) -> bool:
    if record.get("type") != "response_item":
        return False
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return False
    payload_type = payload.get("type")
    if payload_type in _INPUT_RESPONSE_TYPES:
        return True
    return payload_type == "message" and payload.get("role") in {
        "developer",
        "system",
        "user",
    }


def _is_generated(record: JsonObject) -> bool:
    if record.get("type") != "response_item":
        return False
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return False
    payload_type = payload.get("type")
    if payload_type in _GENERATED_RESPONSE_TYPES:
        return True
    return payload_type == "message" and payload.get("role") == "assistant"


def _is_harness_message(payload: dict[str, Any]) -> bool:
    text = _message_text(payload)
    return text is not None and _is_harness_text(text)


def _is_harness_text(text: str) -> bool:
    normalized = text.lstrip()
    return normalized.startswith(_HARNESS_USER_PREFIXES)


def _message_text(payload: dict[str, Any]) -> str | None:
    content = payload.get("content")
    if not isinstance(content, list):
        return None
    texts = [
        item.get("text")
        for item in content
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ]
    return "".join(texts) if texts else None


__all__ = [
    "CODEX_RAW_MODEL_VERSION",
    "CodexRawModelVersioner",
    "CodexRawNormalizer",
]
