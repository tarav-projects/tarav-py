# $kw: ^event-query-backends --from Chatlas.Query.Surface --from Chatlas.Session.Model --from Session.Event.Tape --note [CT] candidate backends return stable event addresses; normal-model reload and Event.Ref re-evaluation establish every public match ^c20260807-16u
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Literal, Mapping, Protocol

from tarav.chatlas._payload_helpers import (
    compact_text,
    parse_event_timestamp,
    string_or_none,
)
from tarav.chatlas.event_pattern import (
    EventPattern,
    EventPredicate,
    alphanumeric_material,
    evaluate_event_pattern,
    event_text,
    match_event_sequences,
    visible_turn_events,
)
from tarav.chatlas.event_ref import event_ref
from tarav.chatlas.index_query import chatlas_index_query
from tarav.chatlas.index_store import load_chatlas_session_index_rows
from tarav.chatlas.normal_turn import normal_turn_ref
from tarav.chatlas.normalization.session_model.events import normal_turn_id, normal_turn_kind
from tarav.chatlas.paths import EVENT_QUERY_INDEX_PATH, default_chatlas_root
from tarav.chatlas.views import load_chatlas_session_model


BackendName = Literal["auto", "scan", "sqlite"]
TurnDetail = Literal["summary", "turn"]
_SQLITE_SCHEMA_VERSION = "6"
_AUTO_SCAN_SESSION_LIMIT = 16


@dataclass(frozen=True, order=True)
class CandidateRef:
    session_identity: str
    event_addresses: tuple[str, ...]


@dataclass(frozen=True)
class CandidateBatch:
    candidates: tuple[CandidateRef, ...]
    complete: bool
    fresh: bool


class EventCandidateBackend(Protocol):
    def find_candidates(self, pattern: EventPattern) -> CandidateBatch: ...


class NormalModelScanBackend:
    def __init__(self, session_models: Mapping[str, dict[str, Any]]) -> None:
        self._session_models = session_models

    def find_candidates(self, pattern: EventPattern) -> CandidateBatch:
        candidates: list[CandidateRef] = []
        for identity, model in sorted(self._session_models.items()):
            for match in match_event_sequences(model, pattern):
                candidates.append(
                    CandidateRef(
                        session_identity=identity,
                        event_addresses=tuple(
                            str(event["event_address"]) for event in match
                        ),
                    )
                )
        return CandidateBatch(tuple(candidates), complete=True, fresh=True)


class SQLiteCandidateBackend:
    def __init__(self, database: Path, *, expected_fingerprint: str) -> None:
        self.database = database
        self.expected_fingerprint = expected_fingerprint

    def find_candidates(self, pattern: EventPattern) -> CandidateBatch:
        if not self._is_usable():
            return CandidateBatch((), complete=False, fresh=False)
        sql, params = _candidate_sql(pattern)
        try:
            with sqlite3.connect(self.database) as connection:
                connection.create_function("regexp", 2, _sqlite_regex)
                rows = connection.execute(sql, params).fetchall()
        except sqlite3.Error:
            return CandidateBatch((), complete=False, fresh=False)
        return CandidateBatch(
            tuple(
                CandidateRef(
                    session_identity=str(row[0]),
                    event_addresses=tuple(str(value) for value in row[1:]),
                )
                for row in rows
            ),
            complete=True,
            fresh=True,
        )

    def _is_usable(self) -> bool:
        if not self.database.is_file():
            return False
        try:
            with sqlite3.connect(self.database) as connection:
                metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        except sqlite3.Error:
            return False
        return (
            metadata.get("schema_version") == _SQLITE_SCHEMA_VERSION
            and metadata.get("corpus_fingerprint") == self.expected_fingerprint
            and metadata.get("coverage") == "complete"
        )


def corpus_fingerprint(rows: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        sorted(rows, key=lambda row: str(row.get("identity_hash", ""))),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def rebuild_sqlite_event_index(
    database: Path,
    session_models: Mapping[str, dict[str, Any]],
    *,
    fingerprint: str,
) -> dict[str, object]:
    return _rebuild_sqlite_event_index(
        database,
        sorted(session_models.items()),
        fingerprint=fingerprint,
    )


def _rebuild_sqlite_event_index(
    database: Path,
    session_models: Iterable[tuple[str, dict[str, Any]]],
    *,
    fingerprint: str,
) -> dict[str, object]:
    database.parent.mkdir(parents=True, exist_ok=True)
    temporary = database.with_suffix(f"{database.suffix}.tmp")
    temporary.unlink(missing_ok=True)
    event_count = 0
    session_count = 0
    try:
        with sqlite3.connect(temporary) as connection:
            connection.executescript(
                """
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE turns (
                    session_identity TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    event_address TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_hash TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    role TEXT,
                    turn_kind TEXT,
                    producer_type TEXT,
                    timestamp_epoch REAL,
                    text TEXT NOT NULL,
                    text_casefold TEXT NOT NULL,
                    alphanumeric_material TEXT NOT NULL,
                    PRIMARY KEY (session_identity, event_address)
                );
                CREATE INDEX turns_relation
                    ON turns (session_identity, ordinal);
                CREATE INDEX turns_sequence
                    ON turns (session_identity, sequence);
                CREATE INDEX turns_role
                    ON turns (role);
                CREATE INDEX turns_turn_kind
                    ON turns (turn_kind);
                CREATE INDEX turns_producer_type
                    ON turns (producer_type);
                CREATE INDEX turns_timestamp
                    ON turns (timestamp_epoch);
                """
            )
            for identity, model in session_models:
                session_count += 1
                for ordinal, event in enumerate(visible_turn_events(model)):
                    payload = event.get("payload")
                    role = (
                        payload.get("role")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("role"), str)
                        else None
                    )
                    producer = event.get("producer")
                    producer_type = (
                        producer.get("type")
                        if isinstance(producer, dict)
                        and isinstance(producer.get("type"), str)
                        else None
                    )
                    timestamp = string_or_none(event.get("timestamp"))
                    parsed_timestamp = (
                        parse_event_timestamp(timestamp) if timestamp is not None else None
                    )
                    text = event_text(event)
                    connection.execute(
                        """
                        INSERT INTO turns
                            (session_identity, ordinal, event_address, sequence, event_hash, kind,
                             role, turn_kind, producer_type, timestamp_epoch, text,
                             text_casefold, alphanumeric_material)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            identity,
                            ordinal,
                            str(event["event_address"]),
                            int(event["sequence"]),
                            str(event["event_hash"]),
                            str(event["kind"]),
                            role,
                            normal_turn_kind(event),
                            producer_type,
                            parsed_timestamp.timestamp()
                            if parsed_timestamp is not None
                            else None,
                            text,
                            text.casefold(),
                            alphanumeric_material(text),
                        ),
                    )
                    event_count += 1
            connection.executemany(
                "INSERT INTO metadata (key, value) VALUES (?, ?)",
                (
                    ("schema_version", _SQLITE_SCHEMA_VERSION),
                    ("corpus_fingerprint", fingerprint),
                    ("coverage", "complete"),
                ),
            )
        os.replace(temporary, database)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "status": "ok",
        "database": str(database),
        "session_count": session_count,
        "event_count": event_count,
        "corpus_fingerprint": fingerprint,
    }


def query_event_models(
    session_models: Mapping[str, dict[str, Any]],
    pattern: EventPattern,
    *,
    requested_backend: BackendName,
    sqlite_database: Path,
    corpus_fingerprint: str,
) -> dict[str, object]:
    fallback_reason: str | None = None
    if requested_backend == "scan":
        backend_used = "scan"
        batch = NormalModelScanBackend(session_models).find_candidates(pattern)
    else:
        sqlite_backend = SQLiteCandidateBackend(
            sqlite_database,
            expected_fingerprint=corpus_fingerprint,
        )
        batch = sqlite_backend.find_candidates(pattern)
        if batch.complete and batch.fresh:
            backend_used = "sqlite"
        else:
            backend_used = "scan"
            fallback_reason = "sqlite index is stale or incomplete"
            batch = NormalModelScanBackend(session_models).find_candidates(pattern)

    candidate_sessions = {
        candidate.session_identity for candidate in batch.candidates
    }
    candidate_models = {
        identity: model
        for identity, model in session_models.items()
        if identity in candidate_sessions
    }
    return _authoritative_event_result(
        candidate_models,
        pattern,
        backend_requested=requested_backend,
        backend_used=backend_used,
        fallback_reason=fallback_reason,
    )


def _authoritative_event_result(
    session_models: Mapping[str, dict[str, Any]],
    pattern: EventPattern,
    *,
    backend_requested: BackendName,
    backend_used: Literal["scan", "sqlite"],
    fallback_reason: str | None = None,
) -> dict[str, object]:
    matches: list[dict[str, object]] = []
    for identity, model in sorted(session_models.items()):
        if not match_event_sequences(model, pattern):
            continue
        for event_refs in evaluate_event_pattern(model, pattern):
            events_by_address = {
                str(event["event_address"]): event for event in visible_turn_events(model)
            }
            events = [events_by_address[str(ref["event_address"])] for ref in event_refs]
            matches.append(
                {
                    "session_identity": identity,
                    "event_refs": list(event_refs),
                    "events": events,
                }
            )

    result: dict[str, object] = {
        "status": "ok",
        "backend_requested": backend_requested,
        "backend_used": backend_used,
        "match_count": len(matches),
        "matches": matches,
    }
    if fallback_reason is not None:
        result["fallback_reason"] = fallback_reason
    return result


def chatlas_events_index(
    *,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    index = load_chatlas_session_index_rows(chatlas_root=root)
    payload = _rebuild_sqlite_event_index(
        root / EVENT_QUERY_INDEX_PATH,
        _iter_session_models(index.rows, chatlas_root=root),
        fingerprint=corpus_fingerprint(index.rows),
    )
    payload["command"] = "chatlas events index"
    payload["chatlas_root"] = str(root)
    return payload


def chatlas_events_query(
    pattern_payload: object,
    *,
    backend: BackendName = "auto",
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    pattern = EventPattern.from_dict(pattern_payload)
    index = load_chatlas_session_index_rows(chatlas_root=root)
    effective_limit = selectors.pop("limit", None)
    query_payload = chatlas_index_query(
        **selectors,
        limit=len(index.rows) if effective_limit is None else effective_limit,
        chatlas_root=root,
    )
    selected_rows = [
        row for row in query_payload.get("rows", []) if isinstance(row, dict)
    ]
    models = _load_session_models(selected_rows, chatlas_root=root)
    result = query_event_models(
        models,
        pattern,
        requested_backend=backend,
        sqlite_database=root / EVENT_QUERY_INDEX_PATH,
        corpus_fingerprint=corpus_fingerprint(index.rows),
    )
    result["command"] = "chatlas events query"
    result["chatlas_root"] = str(root)
    result["candidate_session_count"] = len(models)
    return result


def query_turn_models(
    session_models: Mapping[str, dict[str, Any]],
    pattern: EventPattern,
    *,
    requested_backend: BackendName,
    sqlite_database: Path,
    corpus_fingerprint: str,
    sort: Literal["oldest", "newest"] = "oldest",
    limit: int | None = None,
    detail: TurnDetail = "summary",
) -> dict[str, object]:
    event_result = query_event_models(
        session_models,
        pattern,
        requested_backend=requested_backend,
        sqlite_database=sqlite_database,
        corpus_fingerprint=corpus_fingerprint,
    )
    return _project_turn_result(
        event_result,
        session_models,
        sort=sort,
        limit=limit,
        detail=detail,
    )


def _project_turn_result(
    event_result: dict[str, object],
    session_models: Mapping[str, dict[str, Any]],
    *,
    sort: Literal["oldest", "newest"],
    limit: int | None,
    detail: TurnDetail,
) -> dict[str, object]:
    if detail not in {"summary", "turn"}:
        raise ValueError(f"unsupported turn detail: {detail!r}")
    turns_by_identity: dict[
        tuple[str, str], tuple[float, str, str, dict[str, object]]
    ] = {}
    matches = event_result.get("matches")
    for match in matches if isinstance(matches, list) else []:
        if not isinstance(match, dict):
            continue
        identity = string_or_none(match.get("session_identity"))
        events = match.get("events")
        if identity is None or not isinstance(events, list):
            continue
        model = session_models.get(identity)
        if model is None:
            continue
        for matched_event in events:
            if not isinstance(matched_event, dict):
                continue
            turn_id = normal_turn_id(matched_event)
            if turn_id is None:
                continue
            key = (identity, turn_id)
            parsed_at = parse_event_timestamp(
                string_or_none(matched_event.get("timestamp")) or ""
            )
            sort_at = parsed_at.timestamp() if parsed_at is not None else float("inf")
            existing = turns_by_identity.get(key)
            if existing is None:
                in_turn = _events_for_turn(model, turn_id)
                if not in_turn:
                    continue
                turn: dict[str, object] = {
                    "session_identity": identity,
                    "member_ref": f"{identity}:{turn_id}",
                    "turn_ref": normal_turn_ref(identity, in_turn),
                    "matched_events": [],
                }
                if detail == "turn":
                    turn["normal_turn"] = {
                        "turn_id": turn_id,
                        "events": in_turn,
                    }
                existing = (sort_at, identity, turn_id, turn)
                turns_by_identity[key] = existing
            matched_events = existing[3]["matched_events"]
            assert isinstance(matched_events, list)
            matched_ref = event_ref(matched_event)
            if any(
                isinstance(item, dict) and item.get("event_ref") == matched_ref
                for item in matched_events
            ):
                continue
            payload = matched_event.get("payload")
            producer = matched_event.get("producer")
            matched_events.append(
                {
                    "event_ref": matched_ref,
                    "role": (
                        string_or_none(payload.get("role"))
                        if isinstance(payload, dict)
                        else None
                    ),
                    "producer_type": (
                        string_or_none(producer.get("type"))
                        if isinstance(producer, dict)
                        else None
                    ),
                    "turn_kind": normal_turn_kind(matched_event),
                    "text": compact_text(event_text(matched_event)),
                }
            )
    turns = list(turns_by_identity.values())
    turns.sort(key=lambda item: item[:3], reverse=sort == "newest")
    total = len(turns)
    selected = turns if limit is None else turns[:limit]
    result = {
        key: value
        for key, value in event_result.items()
        if key not in {"match_count", "matches"}
    }
    result.update(
        {
            "match_count": total,
            "returned_turn_count": len(selected),
            "sort": sort,
            "detail": detail,
            "turns": [item[3] for item in selected],
        }
    )
    return result


def chatlas_turns_query(
    *,
    role: str | None = None,
    turn_kind: str | None = None,
    producer_type: str | None = None,
    text_exact: str | None = None,
    text_contains: str | None = None,
    text_regex: str | None = None,
    verbatim: str | None = None,
    after: str | None = None,
    before: str | None = None,
    sort: Literal["oldest", "newest"] = "oldest",
    limit: int | None = 50,
    backend: BackendName = "auto",
    detail: TurnDetail = "summary",
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    text_predicates = [text_exact, text_contains, text_regex, verbatim]
    if sum(value is not None for value in text_predicates) > 1:
        raise ValueError(
            "turn query accepts only one of exact, contains, regex, or verbatim text"
        )
    step: dict[str, str] = {"kind": "message"}
    for key, value in (
        ("role", role),
        ("turn_kind", turn_kind),
        ("producer_type", producer_type),
        ("text_exact", text_exact),
        ("text_contains", text_contains),
        ("text_regex", text_regex),
        ("timestamp_after", after),
        ("timestamp_before", before),
    ):
        if value is not None:
            step[key] = value
    if verbatim is not None:
        step["text_alphanumeric_contains"] = _verbatim_query_material(verbatim)

    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    pattern = EventPattern.from_dict({"steps": [step]})
    index = load_chatlas_session_index_rows(chatlas_root=root)
    query_payload = chatlas_index_query(
        **selectors,
        limit=len(index.rows),
        chatlas_root=root,
    )
    selected_rows = [
        row for row in query_payload.get("rows", []) if isinstance(row, dict)
    ]
    event_result, models, candidate_session_count = _query_selected_rows(
        selected_rows,
        pattern,
        requested_backend=backend,
        sqlite_database=root / EVENT_QUERY_INDEX_PATH,
        fingerprint=corpus_fingerprint(index.rows),
        chatlas_root=root,
    )
    result = _project_turn_result(
        event_result,
        models,
        sort=sort,
        limit=limit,
        detail=detail,
    )
    result["command"] = "chatlas turns query"
    result["chatlas_root"] = str(root)
    result["selected_session_count"] = len(selected_rows)
    result["candidate_session_count"] = candidate_session_count
    result["loaded_session_count"] = len(models)
    return result


def _query_selected_rows(
    selected_rows: list[dict[str, Any]],
    pattern: EventPattern,
    *,
    requested_backend: BackendName,
    sqlite_database: Path,
    fingerprint: str,
    chatlas_root: Path,
) -> tuple[dict[str, object], dict[str, dict[str, Any]], int]:
    selected_by_identity = {
        identity: row
        for row in selected_rows
        if (identity := string_or_none(row.get("identity_hash"))) is not None
    }
    fallback_reason: str | None = None
    if requested_backend == "scan" or (
        requested_backend == "auto"
        and len(selected_by_identity) <= _AUTO_SCAN_SESSION_LIMIT
    ):
        models = _load_session_models(selected_rows, chatlas_root=chatlas_root)
        return (
            _authoritative_event_result(
                models,
                pattern,
                backend_requested=requested_backend,
                backend_used="scan",
            ),
            models,
            len(models),
        )
    if requested_backend != "scan":
        batch = SQLiteCandidateBackend(
            sqlite_database,
            expected_fingerprint=fingerprint,
        ).find_candidates(pattern)
        if batch.complete and batch.fresh:
            candidate_identities = {
                candidate.session_identity
                for candidate in batch.candidates
                if candidate.session_identity in selected_by_identity
            }
            candidate_rows = [
                selected_by_identity[identity]
                for identity in sorted(candidate_identities)
            ]
            models = _load_session_models(candidate_rows, chatlas_root=chatlas_root)
            return (
                _authoritative_event_result(
                    models,
                    pattern,
                    backend_requested=requested_backend,
                    backend_used="sqlite",
                ),
                models,
                len(candidate_identities),
            )
        fallback_reason = "sqlite index is stale or incomplete"

    models = _load_session_models(selected_rows, chatlas_root=chatlas_root)
    result = _authoritative_event_result(
        models,
        pattern,
        backend_requested=requested_backend,
        backend_used="scan",
        fallback_reason=fallback_reason,
    )
    return result, models, len(models)


def parse_event_pattern_json(value: str) -> EventPattern:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Event.Pattern JSON: {exc.msg}") from exc
    return EventPattern.from_dict(payload)


def _load_session_models(
    rows: list[dict[str, Any]],
    *,
    chatlas_root: Path,
) -> dict[str, dict[str, Any]]:
    models: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = row.get("identity_hash")
        if not isinstance(identity, str) or not identity:
            continue
        models[identity] = load_chatlas_session_model(row, chatlas_root=chatlas_root)
    return models


def _iter_session_models(
    rows: Iterable[dict[str, Any]],
    *,
    chatlas_root: Path,
) -> Iterable[tuple[str, dict[str, Any]]]:
    for row in rows:
        identity = row.get("identity_hash")
        if not isinstance(identity, str) or not identity:
            continue
        yield identity, load_chatlas_session_model(row, chatlas_root=chatlas_root)


def _events_for_turn(
    session_model: dict[str, Any], turn_id: str
) -> list[dict[str, Any]]:
    chat = session_model.get("chat")
    if not isinstance(chat, dict):
        return []
    return [
        event
        for event in chat.get("events", [])
        if isinstance(event, dict) and normal_turn_id(event) == turn_id
    ]


_TRAILING_ANCHORS = re.compile(r"(?:\s+\^[A-Za-z0-9][^\s]*)+\s*$")
_INDEX_LINE_PREFIX = re.compile(r"^\s*(?:[-*+]\s+)?(?:\[[A-Za-z]{2}\]\s*)?")


def _verbatim_query_material(value: str) -> str:
    without_anchors = _TRAILING_ANCHORS.sub("", value)
    return _INDEX_LINE_PREFIX.sub("", without_anchors)


def _candidate_sql(pattern: EventPattern) -> tuple[str, tuple[object, ...]]:
    aliases = [f"e{index}" for index in range(len(pattern.steps))]
    columns = ", ".join(
        ["e0.session_identity", *(f"{alias}.event_address" for alias in aliases)]
    )
    joins = " ".join(
        (
            f"JOIN turns {alias} ON {alias}.session_identity = e0.session_identity "
            f"AND {alias}.ordinal = e0.ordinal + {index}"
        )
        for index, alias in enumerate(aliases[1:], start=1)
    )
    conditions: list[str] = []
    params: list[object] = []
    for alias, predicate in zip(aliases, pattern.steps, strict=True):
        _append_indexable_predicates(alias, predicate, conditions, params)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return (
        f"SELECT {columns} FROM turns e0 {joins} {where} "
        "ORDER BY e0.session_identity, e0.ordinal",
        tuple(params),
    )


def _append_indexable_predicates(
    alias: str,
    predicate: EventPredicate,
    conditions: list[str],
    params: list[object],
) -> None:
    for field, value in (
        ("role", predicate.role),
        ("kind", predicate.kind),
        ("turn_kind", predicate.turn_kind),
        ("producer_type", predicate.producer_type),
    ):
        if value is not None:
            conditions.append(f"{alias}.{field} = ?")
            params.append(value)
    if predicate.text_exact is not None:
        conditions.append(f"{alias}.text = ?")
        params.append(predicate.text_exact)
    if predicate.text_contains is not None:
        conditions.append(f"instr({alias}.text_casefold, ?) > 0")
        params.append(predicate.text_contains.casefold())
    if predicate.text_regex is not None:
        conditions.append(f"regexp(?, {alias}.text)")
        params.append(predicate.text_regex)
    if predicate.text_alphanumeric_contains is not None:
        conditions.append(f"instr({alias}.alphanumeric_material, ?) > 0")
        params.append(alphanumeric_material(predicate.text_alphanumeric_contains))
    for field, operator, value in (
        ("timestamp_epoch", ">=", predicate.timestamp_after),
        ("timestamp_epoch", "<=", predicate.timestamp_before),
    ):
        if value is not None:
            parsed = parse_event_timestamp(value)
            if parsed is not None:
                conditions.append(f"{alias}.{field} {operator} ?")
                params.append(parsed.timestamp())
    if predicate.event_ref is not None:
        digest = predicate.event_ref["event_hash"]
        conditions.append(f"{alias}.event_address = ?")
        params.append(predicate.event_ref["event_address"])
        conditions.append(f"substr({alias}.event_hash, 1, length(?)) = ?")
        params.extend((digest, digest))


def _sqlite_regex(pattern: object, value: object) -> int:
    if not isinstance(pattern, str) or not isinstance(value, str):
        return 0
    return int(re.search(pattern, value) is not None)


__all__ = [
    "CandidateBatch",
    "CandidateRef",
    "EventCandidateBackend",
    "NormalModelScanBackend",
    "SQLiteCandidateBackend",
    "TurnDetail",
    "chatlas_events_index",
    "chatlas_events_query",
    "chatlas_turns_query",
    "corpus_fingerprint",
    "format_chatlas_turns_query_text",
    "parse_event_pattern_json",
    "query_event_models",
    "query_turn_models",
    "rebuild_sqlite_event_index",
]


def format_chatlas_turns_query_text(payload: dict[str, Any]) -> str:
    turns = payload.get("turns")
    turns = turns if isinstance(turns, list) else []
    if not turns:
        return "no turns matched the query"
    lines: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        lines.append(str(turn.get("member_ref") or ""))
        events = turn.get("matched_events")
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            role = str(event.get("role") or "?")
            text = str(event.get("text") or "")
            lines.append(f"  {role}:")
            lines.extend(f"    {line}" for line in text.splitlines() or [""])
        lines.append("")
    returned = payload.get("returned_turn_count")
    matched = payload.get("match_count")
    lines.append(f"{returned} of {matched} matching turns")
    return "\n".join(lines)
