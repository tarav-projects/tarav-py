# $kw: ^chatlas2-query --from Chatlas.Query.Surface --from Chatlas.Session.Index --note [CT] Session.Query selects bounded lossless-capable chats through existing index mechanics while Chat.Query remains a separate Normal Model read --supp ^c20260816-64u
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re
from typing import Literal
import unicodedata

from tarav.chatlas._payload_helpers import parse_event_timestamp
from tarav.chatlas.index_query import chatlas_index_query

from .message_ref import chat_message_ref
from .model import JsonObject
from .normal_model import provide_normal_model_reader
from .turn_ref import chat_turn_ref


SUPPORTED_QUERY_PROVIDERS = ("codex", "claude-code")
SessionSort = Literal["lexical", "newest", "oldest"]
MessageSort = Literal["oldest", "newest"]


def query_sessions(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    project: str | Path | None = None,
    project_base: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    active_after: str | None = None,
    sort: SessionSort = "newest",
    limit: int | None = 50,
    chatlas_root: Path | None = None,
) -> JsonObject:
    selected_providers = _query_providers(providers)
    payload = chatlas_index_query(
        uri=uri,
        identity_hash=identity_hash,
        project=project,
        project_base=project_base,
        providers=selected_providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        active_after=active_after,
        sort=sort,
        limit=limit,
        chatlas_root=chatlas_root,
    )
    raw_rows = payload.get("rows")
    rows = raw_rows if isinstance(raw_rows, list) else []
    sessions = [
        _session_projection(row)
        for row in rows
        if isinstance(row, dict)
    ]
    return {
        "class": "tarav.chatlas2.session-query",
        "filters": {
            "uri": uri,
            "identity_hash": identity_hash,
            "project": str(project) if project is not None else None,
            "project_base": project_base,
            "providers": list(selected_providers),
            "instances": list(instances) if instances is not None else None,
            "provider_instance_fingerprint": provider_instance_fingerprint,
            "session_id": session_id,
            "display_name": display_name,
            "extractable": extractable_only,
            "active_after": active_after,
        },
        "sort": sort,
        "limit": limit,
        "index_matched_session_count": payload.get("index_matched_row_count", 0),
        "session_count": len(sessions),
        "sessions": sessions,
    }


def query_chat_messages(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    project: str | Path | None = None,
    project_base: str | None = None,
    providers: tuple[str, ...] | None = None,
    session_id: str | None = None,
    active_after: str | None = None,
    side: Literal["user", "agent"] | None = None,
    text_exact: str | None = None,
    text_contains: str | None = None,
    text_regex: str | None = None,
    text_verbatim: str | None = None,
    after: str | None = None,
    before: str | None = None,
    message_address: str | None = None,
    include_turn_ref: bool = False,
    sort: MessageSort = "oldest",
    session_limit: int = 50,
    offset: int = 0,
    limit: int = 50,
    chatlas_root: Path | None = None,
) -> JsonObject:
    predicate = _MessagePredicate.create(
        side=side,
        text_exact=text_exact,
        text_contains=text_contains,
        text_regex=text_regex,
        text_verbatim=text_verbatim,
        after=after,
        before=before,
        message_address=message_address,
    )
    if sort not in {"oldest", "newest"}:
        raise ValueError("Chat.Query sort must be 'oldest' or 'newest'")
    if session_limit < 0 or offset < 0 or limit < 0:
        raise ValueError("Chat.Query limits must be non-negative")
    session_result = query_sessions(
        uri=uri,
        identity_hash=identity_hash,
        project=project,
        project_base=project_base,
        providers=providers,
        session_id=session_id,
        active_after=active_after,
        sort="newest",
        limit=session_limit,
        chatlas_root=chatlas_root,
    )
    sessions = session_result.get("sessions")
    selected_sessions = sessions if isinstance(sessions, list) else []
    matches: list[JsonObject] = []
    failures: list[JsonObject] = []
    queried_session_count = 0
    for session in selected_sessions:
        if not isinstance(session, dict):
            continue
        identity = session.get("identity_hash")
        if not isinstance(identity, str) or not identity:
            failures.append(
                {"session": deepcopy(session), "error": "missing identity_hash"}
            )
            continue
        try:
            reader = provide_normal_model_reader(
                identity_hash=identity,
                chatlas_root=chatlas_root,
            )
            queried_session_count += 1
            addresses = (
                (predicate.message_address,)
                if predicate.message_address is not None
                else None
            )
            records = reader.iter_chat_message_records(
                side=predicate.side,
                text=predicate.text_exact,
                exact=predicate.text_exact is not None,
                message_addresses=addresses,
            )
            for record in records:
                if not predicate.matches(record):
                    continue
                matches.append(
                    _message_result(
                        session,
                        record,
                        reader=reader,
                        include_turn_ref=include_turn_ref,
                    )
                )
        except Exception as exc:
            failures.append(
                {
                    "session": deepcopy(session),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    matches.sort(key=lambda result: _message_sort_key(result, sort=sort))
    selected_matches = matches[offset : offset + limit]
    next_offset = offset + len(selected_matches)
    if next_offset >= len(matches):
        next_offset = None
    return {
        "class": "tarav.chatlas2.chat-query",
        "status": "partial" if failures else "ok",
        "subject": "Chat.Message",
        "filters": predicate.as_dict(),
        "sort": sort,
        "session_limit": session_limit,
        "offset": offset,
        "limit": limit,
        "selected_session_count": len(selected_sessions),
        "queried_session_count": queried_session_count,
        "failure_count": len(failures),
        "failures": failures,
        "query_matched_message_count": len(matches),
        "returned_message_count": len(selected_matches),
        "next_offset": next_offset,
        "messages": selected_matches,
    }


class _MessagePredicate:
    def __init__(
        self,
        *,
        side: Literal["user", "agent"] | None,
        text_exact: str | None,
        text_contains: str | None,
        text_regex: str | None,
        text_verbatim: str | None,
        after: str | None,
        before: str | None,
        message_address: str | None,
    ) -> None:
        self.side = side
        self.text_exact = text_exact
        self.text_contains = text_contains
        self.text_regex = text_regex
        self.text_verbatim = text_verbatim
        self.after = after
        self.before = before
        self.message_address = message_address
        try:
            self._regex = re.compile(text_regex) if text_regex is not None else None
        except re.error as exc:
            raise ValueError("Chat.Query received an invalid regular expression") from exc
        self._after_at = _query_time(after, field="after")
        self._before_at = _query_time(before, field="before")

    @classmethod
    def create(
        cls,
        **kwargs: object,
    ) -> _MessagePredicate:
        text_values = [
            kwargs.get("text_exact"),
            kwargs.get("text_contains"),
            kwargs.get("text_regex"),
            kwargs.get("text_verbatim"),
        ]
        if sum(value is not None for value in text_values) > 1:
            raise ValueError("Chat.Query accepts only one text predicate")
        for value in text_values:
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError("Chat.Query text predicates must be non-empty strings")
        text_verbatim = kwargs.get("text_verbatim")
        if isinstance(text_verbatim, str) and not _verbatim(text_verbatim):
            raise ValueError("Chat.Query verbatim text must contain alphanumeric material")
        side = kwargs.get("side")
        if side not in {None, "user", "agent"}:
            raise ValueError("Chat.Query side must be 'user' or 'agent'")
        return cls(**kwargs)  # type: ignore[arg-type]

    def matches(self, record: JsonObject) -> bool:
        message = record.get("message")
        if not isinstance(message, dict):
            return False
        if self.side is not None and message.get("side") != self.side:
            return False
        if (
            self.message_address is not None
            and message.get("message_address") != self.message_address
        ):
            return False
        text = message.get("text")
        if not isinstance(text, str):
            return False
        if self.text_exact is not None and text != self.text_exact:
            return False
        if (
            self.text_contains is not None
            and self.text_contains.casefold() not in text.casefold()
        ):
            return False
        if self._regex is not None and self._regex.search(text) is None:
            return False
        if self.text_verbatim is not None and _verbatim(self.text_verbatim) not in _verbatim(text):
            return False
        at = record.get("at")
        parsed_at = parse_event_timestamp(at) if isinstance(at, str) else None
        if self._after_at is not None and (parsed_at is None or parsed_at < self._after_at):
            return False
        if self._before_at is not None and (parsed_at is None or parsed_at > self._before_at):
            return False
        return True

    def as_dict(self) -> JsonObject:
        return {
            "side": self.side,
            "text_exact": self.text_exact,
            "text_contains": self.text_contains,
            "text_regex": self.text_regex,
            "text_verbatim": self.text_verbatim,
            "after": self.after,
            "before": self.before,
            "message_address": self.message_address,
        }


def _query_time(value: str | None, *, field: str) -> datetime | None:
    if value is None:
        return None
    parsed = parse_event_timestamp(value)
    if parsed is None:
        raise ValueError(f"Chat.Query {field} must be an ISO 8601 timestamp")
    return parsed


def _verbatim(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _message_result(
    session: JsonObject,
    record: JsonObject,
    *,
    reader: object,
    include_turn_ref: bool,
) -> JsonObject:
    message = record.get("message")
    if not isinstance(message, dict):
        raise ValueError("Chat.Query received an invalid message record")
    ref = chat_message_ref(message)
    at = record.get("at")
    result: JsonObject = {
        "session": deepcopy(session),
        "message_ref": ref,
        "at": at,
        "message": deepcopy(message),
    }
    if include_turn_ref:
        turn = reader.find_chat_turn(message_address=ref["message_address"])
        result["turn_ref"] = chat_turn_ref(turn) if isinstance(turn, dict) else None
    return result


def _message_sort_key(result: JsonObject, *, sort: MessageSort) -> tuple[object, ...]:
    at = result.get("at")
    parsed = parse_event_timestamp(at) if isinstance(at, str) else None
    timestamp = parsed.timestamp() if parsed is not None else 0.0
    session = result.get("session")
    ref = result.get("message_ref")
    identity = session.get("identity_hash") if isinstance(session, dict) else ""
    address = ref.get("message_address") if isinstance(ref, dict) else ""
    return (
        parsed is None,
        -timestamp if sort == "newest" else timestamp,
        str(identity),
        str(address),
    )


def _query_providers(providers: tuple[str, ...] | None) -> tuple[str, ...]:
    selected = SUPPORTED_QUERY_PROVIDERS if providers is None else providers
    unsupported = sorted(set(selected) - set(SUPPORTED_QUERY_PROVIDERS))
    if unsupported:
        raise ValueError(
            "Chatlas2 Session.Query supports only Codex and Claude Code providers"
        )
    return selected


def _session_projection(row: JsonObject) -> JsonObject:
    return {
        key: row.get(key)
        for key in (
            "uri",
            "provider",
            "instance",
            "identity_hash",
            "session_id",
            "last_activity_at",
            "project_path",
        )
    }


__all__ = [
    "MessageSort",
    "SUPPORTED_QUERY_PROVIDERS",
    "SessionSort",
    "query_chat_messages",
    "query_sessions",
]
