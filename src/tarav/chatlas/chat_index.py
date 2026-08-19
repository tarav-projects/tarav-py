# $kw: --from Chat.Index --from Chat.Index.Delta --from Chat.Index.HEAD --from Chat.Touched.Index --note [IMPL] incremental maintenance isolates append-only chat evidence without automatic semantic writes --note [IMPL] pending evidence projects at chat, refs, or turn detail so capture reads the transcript without reasoning or tool noise --supp ^c20260804-50u --supp ^c20260804-60u
from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any

from tarav._core.errors import CliError
from tarav.agent._cli_common import format_json_output
from tarav.index_model import canonical_index_line_statement, index_line_statement_parts

from tarav.chatlas.event_query import chatlas_turns_query
from tarav.chatlas.index_query import select_one_chatlas_index_row
from tarav.chatlas.normalization.session_model.messages import (
    transcript_visible_messages,
)
from tarav.chatlas.normalization.session_model.events import normal_turn_kind
from tarav.chatlas.paths import CHAT_INDEX_SURFACES_ROOT, default_chatlas_root


HEAD_FILENAME = "HEAD.md"
DELTA_DIRNAME = "deltas"
_DELTA_HEADING_RE = re.compile(
    r"^# Chat\.Index\.Delta/(?P<turn_id>\S+?)(?: @ (?P<at>\S+))?\s*$"
)
_HEAD_HORIZON_RE = re.compile(
    r"^Evidence\.Horizon: `(?P<turn_id>[^`]+)`(?: @ (?P<at>\S+))?\s*$"
)
CAPTURE_LAYOUT = "delta-head-v2"
SOURCE_SCHEMA = "agentos.chat-index.source.v1"


def chat_index_surface_path(
    identity_hash: str, *, chatlas_root: Path | None = None
) -> Path:
    if not identity_hash:
        raise ValueError("identity_hash must be a non-empty string")
    return _chatlas_root(chatlas_root) / CHAT_INDEX_SURFACES_ROOT / identity_hash


def chat_index_discovery(
    identity_hash: str, *, chatlas_root: Path | None = None
) -> dict[str, object]:
    path = chat_index_surface_path(identity_hash, chatlas_root=chatlas_root)
    capture_path = path / HEAD_FILENAME
    materialized = path.is_dir() and capture_path.is_file()
    state = (
        "materialized" if materialized else "invalid" if path.exists() else "missing"
    )
    return {
        "materialized": materialized,
        "state": state,
        "path": str(path),
    }


def chatlas_chat_index_status(
    *, chatlas_root: Path | None = None, **selectors: object
) -> dict[str, object]:
    return _chat_index_result(
        command="chatlas chat-index status",
        chatlas_root=chatlas_root,
        selectors=selectors,
        verify_source=True,
        include_capture=False,
    )


def chatlas_chat_index_show(
    *, chatlas_root: Path | None = None, **selectors: object
) -> dict[str, object]:
    return _chat_index_result(
        command="chatlas chat-index show",
        chatlas_root=chatlas_root,
        selectors=selectors,
        verify_source=True,
        include_capture=True,
    )


def chatlas_chat_index_path(
    *, chatlas_root: Path | None = None, **selectors: object
) -> dict[str, object]:
    root, session, identity_hash = _select_session(
        command="chatlas chat-index path",
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    discovery = chat_index_discovery(identity_hash, chatlas_root=root)
    return {
        "status": "ok",
        "command": "chatlas chat-index path",
        "chatlas_root": str(root),
        "session": _session_locator(session),
        "chat_index": discovery,
        "path": discovery["path"],
    }


def chatlas_chat_index_files(
    *, chatlas_root: Path | None = None, **selectors: object
) -> dict[str, object]:
    root, session, identity_hash = _select_session(
        command="chatlas chat-index files",
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    surface_path = chat_index_surface_path(identity_hash, chatlas_root=root)
    discovery = chat_index_discovery(identity_hash, chatlas_root=root)
    capture, error = _load_capture(surface_path, expected_identity_hash=identity_hash)
    if error is not None:
        return _invalid_result(
            command="chatlas chat-index files",
            root=root,
            session=session,
            discovery=discovery,
            error=error,
            include_capture=False,
        ) | {"files": []}

    assert capture is not None
    files = [
        {
            "relative_path": relative_path,
            "path": str(surface_path / relative_path),
            "exists": (surface_path / relative_path).is_file(),
        }
        for relative_path in capture["managed_files"]
    ]
    return {
        "status": "ok",
        "command": "chatlas chat-index files",
        "chatlas_root": str(root),
        "session": _session_locator(session),
        "chat_index": {
            **discovery,
            "state": "materialized",
        },
        "files": files,
    }


def chatlas_chat_index_deltas(
    *, chatlas_root: Path | None = None, **selectors: object
) -> dict[str, object]:
    root, session, identity_hash = _select_session(
        command="chatlas chat-index deltas",
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    surface_path = chat_index_surface_path(identity_hash, chatlas_root=root)
    discovery = chat_index_discovery(identity_hash, chatlas_root=root)
    capture, error = _load_capture(surface_path, expected_identity_hash=identity_hash)
    if error is not None:
        return _invalid_result(
            command="chatlas chat-index deltas",
            root=root,
            session=session,
            discovery=discovery,
            error=error,
            include_capture=False,
        ) | {"deltas": []}
    assert capture is not None


    _canonical, source = chat_index_source_model(session, chatlas_root=root)
    deltas = [
        {
            **delta,
            "relative_path": delta["path"],
            "path": str(surface_path / delta["path"]),
            "exists": (surface_path / delta["path"]).is_file(),
        }
        for delta in resolve_delta_tape_positions(capture["deltas"], source)
    ]
    return {
        "status": "ok",
        "command": "chatlas chat-index deltas",
        "chatlas_root": str(root),
        "session": _session_locator(session),
        "chat_index": _materialized_summary(discovery, capture),
        "deltas": deltas,
    }


def chatlas_chat_index_head(
    *, chatlas_root: Path | None = None, **selectors: object
) -> dict[str, object]:
    root, session, identity_hash = _select_session(
        command="chatlas chat-index head",
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    surface_path = chat_index_surface_path(identity_hash, chatlas_root=root)
    discovery = chat_index_discovery(identity_hash, chatlas_root=root)
    capture, error = _load_capture(surface_path, expected_identity_hash=identity_hash)
    if error is not None:
        return _invalid_result(
            command="chatlas chat-index head",
            root=root,
            session=session,
            discovery=discovery,
            error=error,
            include_capture=False,
        ) | {"head": None}
    assert capture is not None
    head = capture["head"]
    relative_path = head["path"]
    return {
        "status": "ok",
        "command": "chatlas chat-index head",
        "chatlas_root": str(root),
        "session": _session_locator(session),
        "chat_index": _materialized_summary(discovery, capture),
        "head": {
            **head,
            "relative_path": relative_path,
            "path": str(surface_path / relative_path),
            "exists": (surface_path / relative_path).is_file(),
        },
    }


def chatlas_chat_index_home(
    *,
    line_content: str,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    if not line_content.strip():
        raise CliError("chatlas chat-index home requires non-empty --line-content")
    root, session, identity_hash = _select_session(
        command="chatlas chat-index home",
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    surface_path = chat_index_surface_path(identity_hash, chatlas_root=root)
    discovery = chat_index_discovery(identity_hash, chatlas_root=root)
    capture, error = _load_capture(surface_path, expected_identity_hash=identity_hash)
    if error is not None:
        return _invalid_result(
            command="chatlas chat-index home",
            root=root,
            session=session,
            discovery=discovery,
            error=error,
            include_capture=False,
        ) | {"home": None, "occurrences": [], "match_count": 0, "finding": None}
    assert capture is not None
    statement_key = index_line_statement_parts(line_content)
    _canonical, source = chat_index_source_model(session, chatlas_root=root)
    occurrences: list[dict[str, object]] = []
    for delta in resolve_delta_tape_positions(capture["deltas"], source):
        relative_path = delta["path"]
        path = surface_path / relative_path
        for line_number, source_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not source_line.lstrip().startswith("-"):
                continue
            if index_line_statement_parts(source_line) != statement_key:
                continue
            occurrences.append(
                {
                    "relative_path": relative_path,
                    "path": str(path),
                    "line_number": line_number,
                    "horizon": delta["horizon"],
                    "tape_position": delta["tape_position"],
                }
            )


    home = occurrences[0] if occurrences else None
    finding = None
    if home is None:
        finding = {
            "kind": "missing-line-home",
            "statement_key": canonical_index_line_statement(line_content),
            "message": "exact Index.Line content is not materialized in any Delta",
        }
    return {
        "status": "ok",
        "command": "chatlas chat-index home",
        "chatlas_root": str(root),
        "session": _session_locator(session),
        "chat_index": _materialized_summary(discovery, capture),
        "statement_key": canonical_index_line_statement(line_content),
        "home": home,
        "occurrences": occurrences,
        "match_count": len(occurrences),
        "finding": finding,
    }


def chatlas_chat_index_tail(
    *,
    detail: str = "refs",
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    if detail not in {"refs", "turn", "chat"}:
        raise CliError(
            "chatlas chat-index tail detail must be 'refs', 'chat', or 'turn'"
        )
    root, session, identity_hash = _select_session(
        command="chatlas chat-index tail",
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    surface_path = chat_index_surface_path(identity_hash, chatlas_root=root)
    discovery = chat_index_discovery(identity_hash, chatlas_root=root)
    if discovery["state"] == "missing":
        return {
            "status": "ok",
            "command": "chatlas chat-index tail",
            "chatlas_root": str(root),
            "session": _session_locator(session),
            "chat_index": {
                **discovery,
                "freshness": {"state": "unknown", "reason": "not materialized"},
            },
            "tail": None,
            "turns": [],
        }

    capture, error = _load_capture(
        surface_path, expected_identity_hash=identity_hash
    )
    if error is not None:
        return _invalid_result(
            command="chatlas chat-index tail",
            root=root,
            session=session,
            discovery=discovery,
            error=error,
            include_capture=False,
        ) | {"tail": None, "turns": []}
    assert capture is not None
    canonical, current_source = chat_index_source_model(session, chatlas_root=root)


    tail = _compare_v2_source_tail(
        source_prefix_at_horizon(current_source, capture["head"]["horizon"]),
        current_source,
    )
    turns: list[dict[str, object]] = []
    if detail in {"turn", "chat"} and tail["state"] in {
        "append-only",
        "expanded",
        "revised",
    }:
        turns = _pending_turn_payloads(canonical, tail, detail=detail)
    return {
        "status": "ok",
        "command": "chatlas chat-index tail",
        "chatlas_root": str(root),
        "session": _session_locator(session),
        "chat_index": _materialized_summary(discovery, capture),
        "tail": tail,
        "turns": turns,
    }


def _pending_turn_payloads(
    canonical: dict[str, Any],
    tail: dict[str, object],
    *,
    detail: str,
) -> list[dict[str, object]]:
    """Pending source turns projected at the requested evidence detail.

    `chat` is the semantic default: transcript-visible messages only, derived in
    memory from the same authoritative turns the tail comparison used. `turn`
    remains the escape hatch that hands back the complete grouping.
    """
    pending_keys = {
        _source_turn_entry_key(entry)
        for entry in tail["turn_refs"]
        if isinstance(entry, dict)
    }
    payloads: list[dict[str, object]] = []
    for turn in canonical["turns"]:
        coordinate = {
            "turn_ref": turn["turn_ref"],
            "tape_position": turn["tape_position"],
            "role": turn["role"],
            "producer_type": turn["producer_type"],
            "turn_kind": turn["turn_kind"],
        }
        if _source_turn_entry_key(coordinate) not in pending_keys:
            continue
        normal_turn = turn["normal_turn"]
        evidence: dict[str, object]
        if detail == "chat":
            events = normal_turn.get("events") if isinstance(normal_turn, dict) else None
            evidence = {"messages": transcript_visible_messages(events)}
        else:
            evidence = {"normal_turn": normal_turn}
        payloads.append({**coordinate, **evidence})
    return payloads


def chat_index_source_hash(
    session: dict[str, Any], *, chatlas_root: Path | None = None
) -> str:
    payload = _source_turn_query(session, chatlas_root=chatlas_root)
    source_bytes = (format_json_output(_canonical_v2_source(payload)) + "\n").encode(
        "utf-8"
    )
    return f"sha256:{hashlib.sha256(source_bytes).hexdigest()}"


def chatlas_chat_index_source(
    *, chatlas_root: Path | None = None, **selectors: object
) -> dict[str, object]:
    root, session, _identity_hash = _select_session(
        command="chatlas chat-index source",
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    queried = _source_turn_query(session, chatlas_root=root)
    canonical = _canonical_v2_source(queried)
    return {
        "status": "ok",
        "command": "chatlas chat-index source",
        "chatlas_root": str(root),
        "session": _session_locator(session),
        "source": _v2_source_descriptor(canonical),
    }


def _source_turn_query(
    session: dict[str, Any], *, chatlas_root: Path | None = None
) -> dict[str, Any]:
    identity_hash = session.get("identity_hash")
    if not isinstance(identity_hash, str) or not identity_hash:
        raise CliError("Chat.Index source hashing requires one session identity_hash")
    payload = chatlas_turns_query(
        identity_hash=identity_hash,
        detail="turn",
        sort="oldest",
        limit=100000,
        chatlas_root=_chatlas_root(chatlas_root),
    )
    if payload.get("selected_session_count") != 1:
        raise CliError(
            "Chat.Index source hashing requires exactly one selected session"
        )
    if payload.get("returned_turn_count") != payload.get("match_count"):
        raise CliError(
            "Chat.Index source hashing did not materialize every matched turn"
        )
    return payload


def _canonical_v2_source(payload: dict[str, Any]) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    findings: list[dict[str, object]] = []
    for turn in payload.get("turns", []):
        normal_turn = turn.get("normal_turn")
        events = normal_turn.get("events") if isinstance(normal_turn, dict) else None
        if not isinstance(events, list) or not events:
            raise CliError("Chat.Index source turn has no ordered events")
        positions = [event.get("sequence") for event in events]
        if not all(isinstance(position, int) for position in positions):
            raise CliError("Chat.Index source event has no integer tape sequence")
        position = min(positions)
        landing = min(events, key=lambda event: event["sequence"])
        payload_value = landing.get("payload")
        producer = landing.get("producer")
        role = payload_value.get("role") if isinstance(payload_value, dict) else None
        producer_type = producer.get("type") if isinstance(producer, dict) else None
        turn_kind = normal_turn_kind(landing)
        for event in events:
            if event.get("kind") == "lineage.rollback":
                findings.append(
                    {
                        "kind": "non-linear-chat",
                        "reason": "lineage.rollback",
                        "sequence": event["sequence"],
                    }
                )
        turns.append(
            {
                "turn_ref": turn.get("turn_ref"),
                "tape_position": position,
                "role": role,
                "producer_type": producer_type,
                "turn_kind": turn_kind,
                "normal_turn": normal_turn,
            }
        )
    turns.sort(key=lambda turn: turn["tape_position"])
    return {
        "schema": SOURCE_SCHEMA,
        "session_identity": (
            turns[0]["turn_ref"].get("session")
            if turns and isinstance(turns[0].get("turn_ref"), dict)
            else None
        ),
        "linear": not findings,
        "findings": findings,
        "turns": turns,
    }


def _v2_source_descriptor(canonical: dict[str, Any]) -> dict[str, Any]:
    source_bytes = (format_json_output(canonical) + "\n").encode("utf-8")
    return {
        "schema": SOURCE_SCHEMA,
        "materialized_source_hash": (
            f"sha256:{hashlib.sha256(source_bytes).hexdigest()}"
        ),
        "turn_count": len(canonical["turns"]),
        "linear": canonical["linear"],
        "turn_refs": [
            {
                "turn_ref": turn["turn_ref"],
                "tape_position": turn["tape_position"],
                "role": turn["role"],
                "producer_type": turn["producer_type"],
                "turn_kind": turn["turn_kind"],
            }
            for turn in canonical["turns"]
        ],
        "findings": canonical["findings"],
    }


def _compare_v2_source_tail(
    captured_source: dict[str, Any],
    current_source: dict[str, Any],
) -> dict[str, object]:
    """What the chat has added since the capture's declared horizon.

    The captured side is reconstructed from the horizon `HEAD.md` declares,
    not from a stored snapshot: the prefix at or before that turn is what the
    capture read. A turn revised inside that prefix without moving the horizon
    is therefore invisible here — see the Accepted.Loss section of Impl.Req
    556. Growth, the ordinary case, is fully detected.
    """
    captured_turns = captured_source.get("turn_refs")
    current_turns = current_source.get("turn_refs")
    if not isinstance(captured_turns, list) or not isinstance(current_turns, list):
        raise ValueError("Chat.Index tail comparison requires ordered source.turn_refs")

    captured_count = len(captured_turns)
    current_count = len(current_turns)
    base: dict[str, object] = {
        "captured_turn_count": captured_count,
        "current_turn_count": current_count,
        "pending_turn_count": 0,
        "pending_before_cursor_count": 0,
        "revised_turn_count": 0,
        "cursor": captured_turns[-1] if captured_turns else None,
        "turn_refs": [],
        "findings": [],
    }
    if current_source.get("linear") is not True:
        findings = current_source.get("findings")
        return {
            **base,
            "state": "blocked",
            "findings": findings if isinstance(findings, list) else [],
        }

    captured_index = 0
    pending: list[object] = []
    pending_before_cursor_count = 0
    revised_turn_count = 0
    for current_turn in current_turns:
        if captured_index < captured_count:
            captured_turn = captured_turns[captured_index]
            if current_turn == captured_turn:
                captured_index += 1
                continue
            if (
                isinstance(current_turn, dict)
                and isinstance(captured_turn, dict)
                and _source_turn_coordinate_key(current_turn)
                == _source_turn_coordinate_key(captured_turn)
            ):
                pending.append(current_turn)
                pending_before_cursor_count += 1
                revised_turn_count += 1
                captured_index += 1
                continue
        pending.append(current_turn)
        if captured_index < captured_count:
            pending_before_cursor_count += 1

    if captured_index != captured_count:
        return {
            **base,
            "state": "diverged",
            "findings": [
                {
                    "kind": "source-prefix-diverged",
                    "reason": "captured-turn-missing-or-changed",
                    "index": captured_index,
                    "captured": captured_turns[captured_index],
                    "current": None,
                }
            ],
        }

    return {
        **base,
        "state": (
            "revised"
            if revised_turn_count
            else "expanded"
            if pending_before_cursor_count
            else "append-only"
            if pending
            else "current"
        ),
        "pending_turn_count": len(pending),
        "pending_before_cursor_count": pending_before_cursor_count,
        "revised_turn_count": revised_turn_count,
        "turn_refs": pending,
    }


def source_prefix_at_horizon(
    source: dict[str, Any], horizon: dict[str, Any] | None
) -> dict[str, Any]:
    """The chat prefix a capture with this declared horizon actually read."""
    turn_refs = source.get("turn_refs")
    if not isinstance(turn_refs, list):
        return {**source, "turn_refs": []}
    if horizon is None:
        return {**source, "turn_refs": []}
    turn_id = horizon.get("turn_id")
    prefix: list[Any] = []
    for entry in turn_refs:
        prefix.append(entry)
        if (
            isinstance(entry, dict)
            and str(entry.get("turn_ref", {}).get("turn_id")) == str(turn_id)
        ):
            break
    return {**source, "turn_refs": prefix, "turn_count": len(prefix)}


def source_tape_positions(source: dict[str, Any]) -> dict[str, int]:
    """Where each turn sits on the live tape, keyed by turn id."""
    turn_refs = source.get("turn_refs")
    if not isinstance(turn_refs, list):
        return {}
    return {
        str(entry["turn_ref"]["turn_id"]): entry["tape_position"]
        for entry in turn_refs
        if isinstance(entry, dict) and isinstance(entry.get("turn_ref"), dict)
    }


def resolve_delta_tape_positions(
    deltas: list[dict[str, Any]], source: dict[str, Any]
) -> list[dict[str, Any]]:
    """Deltas in chat order, each carrying the tape position of its horizon.

    A horizon the live chat no longer holds keeps a `None` position and sorts
    last; the audit is what reports it, not this resolution.
    """
    positions = source_tape_positions(source)
    resolved = [
        {**delta, "tape_position": positions.get(str(delta["horizon"]["turn_id"]))}
        for delta in deltas
    ]
    resolved.sort(
        key=lambda delta: (
            delta["tape_position"] is None,
            delta["tape_position"] or 0,
            delta["path"],
        )
    )
    return resolved


def _source_turn_entry_key(entry: dict[str, Any]) -> tuple[object, ...]:
    turn_ref = entry.get("turn_ref")
    ref = turn_ref if isinstance(turn_ref, dict) else {}
    return (
        ref.get("session"),
        ref.get("turn_id"),
        ref.get("turn_hash"),
        entry.get("tape_position"),
        entry.get("role"),
        entry.get("producer_type"),
        entry.get("turn_kind"),
    )


def _source_turn_coordinate_key(entry: dict[str, Any]) -> tuple[object, ...]:
    turn_ref = entry.get("turn_ref")
    ref = turn_ref if isinstance(turn_ref, dict) else {}
    return (
        ref.get("session"),
        ref.get("turn_id"),
        entry.get("tape_position"),
        entry.get("role"),
        entry.get("producer_type"),
        entry.get("turn_kind"),
    )


def _chat_index_result(
    *,
    command: str,
    chatlas_root: Path | None,
    selectors: dict[str, object],
    verify_source: bool,
    include_capture: bool,
) -> dict[str, object]:
    root, session, identity_hash = _select_session(
        command=command,
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    surface_path = chat_index_surface_path(identity_hash, chatlas_root=root)
    discovery = chat_index_discovery(identity_hash, chatlas_root=root)
    if discovery["state"] == "missing":
        return {
            "status": "ok",
            "command": command,
            "chatlas_root": str(root),
            "session": _session_locator(session),
            "chat_index": {
                **discovery,
                "freshness": {"state": "unknown", "reason": "not materialized"},
            },
            **({"capture": None} if include_capture else {}),
        }

    capture, error = _load_capture(surface_path, expected_identity_hash=identity_hash)
    if error is not None:
        return _invalid_result(
            command=command,
            root=root,
            session=session,
            discovery=discovery,
            error=error,
            include_capture=include_capture,
        )
    assert capture is not None


    freshness = _surface_freshness(session, capture, root)
    state = "materialized"
    warning = None
    if freshness["state"] == "stale":
        warning = freshness["reason"]

    result: dict[str, object] = {
        "status": "ok",
        "command": command,
        "chatlas_root": str(root),
        "session": _session_locator(session),
        "chat_index": {
            **discovery,
            "state": state,
            "warning": warning,
            "layout": CAPTURE_LAYOUT,
            "managed_file_count": len(capture["managed_files"]),
            "delta_count": len(capture["deltas"]),
            "freshness": freshness,
        },
    }
    if include_capture:
        result["capture"] = capture
    return result


def load_chat_index_capture(
    surface_path: Path,
    *,
    expected_identity_hash: str,
    at_identity_path: bool = True,
) -> tuple[dict[str, Any] | None, str | None]:
    """Derive the surface model at any path.

    The same derivation serves the live read commands, a staged directory
    awaiting installation, and the bulk audit, so no consumer can accept a
    surface another one would refuse.
    """
    return _load_capture(
        surface_path,
        expected_identity_hash=expected_identity_hash,
        at_identity_path=at_identity_path,
    )


def select_chat_index_session(
    *, command: str, chatlas_root: Path | None, selectors: dict[str, object]
) -> tuple[Path, dict[str, Any], str]:
    return _select_session(
        command=command, chatlas_root=chatlas_root, selectors=selectors
    )


def session_locator(session: dict[str, Any]) -> dict[str, object]:
    return _session_locator(session)


def chat_index_source_model(
    session: dict[str, Any], *, chatlas_root: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The live canonical source and its descriptor, derived in one query."""
    canonical = _canonical_v2_source(
        _source_turn_query(session, chatlas_root=chatlas_root)
    )
    return canonical, _v2_source_descriptor(canonical)


def compare_v2_source_tail(
    captured_source: dict[str, Any], current_source: dict[str, Any]
) -> dict[str, object]:
    return _compare_v2_source_tail(captured_source, current_source)


def v2_source_tail(
    session: dict[str, Any],
    captured_source: dict[str, Any],
    *,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    """Compare a captured v2 source descriptor against the live source."""
    _canonical, current = chat_index_source_model(session, chatlas_root=chatlas_root)
    return _compare_v2_source_tail(captured_source, current)


def _select_session(
    *, command: str, chatlas_root: Path | None, selectors: dict[str, object]
) -> tuple[Path, dict[str, Any], str]:
    root = _chatlas_root(chatlas_root)
    session = select_one_chatlas_index_row(
        command=command,
        chatlas_root=root,
        **selectors,
    )
    identity_hash = session.get("identity_hash")
    if not isinstance(identity_hash, str) or not identity_hash:
        raise CliError(f"{command} requires one session identity_hash")
    return root, session, identity_hash


def _surface_freshness(
    session: dict[str, Any] | None,
    capture: dict[str, Any],
    chatlas_root: Path | None,
) -> dict[str, object]:
    horizon = capture["head"]["horizon"]
    if session is None:
        return {"state": "unknown", "reason": "live chat unavailable"}
    if horizon is None:
        return {"state": "unknown", "reason": "HEAD declares no evidence horizon"}
    try:
        _canonical, source = chat_index_source_model(session, chatlas_root=chatlas_root)
    except (CliError, ValueError) as exc:
        return {"state": "unknown", "reason": str(exc)}
    tail = _compare_v2_source_tail(
        source_prefix_at_horizon(source, horizon), source
    )
    if tail["state"] == "current":
        return {"state": "current", "reason": None}
    return {
        "state": "stale",
        "reason": f"chat has {tail['pending_turn_count']} turns past the "
        f"declared horizon {horizon['turn_id']}",
        "tail_state": tail["state"],
    }


def _load_capture(
    surface_path: Path,
    *,
    expected_identity_hash: str,
    at_identity_path: bool = True,
) -> tuple[dict[str, Any] | None, str | None]:
    """Derive the surface model from the files themselves.

    There is no descriptor. Identity is the directory name, the Delta set is
    the directory listing, each horizon is its own filename and heading, and
    ordering comes from the chat. Nothing here is asserted by the surface; it
    is all read back from what the surface actually is.

    `at_identity_path` is false for a staged directory, which by construction
    has not yet been named for the session it belongs to.
    """
    head_path = surface_path / HEAD_FILENAME
    if not head_path.is_file():
        return None, f"Chat.Index is not materialized: {head_path}"
    if at_identity_path and surface_path.name != expected_identity_hash:
        return None, (
            "Chat.Index surface path is not its session identity: "
            f"{surface_path.name!r} != {expected_identity_hash!r}"
        )
    deltas: list[dict[str, Any]] = []
    delta_dir = surface_path / DELTA_DIRNAME
    for path in sorted(delta_dir.glob("*.md")) if delta_dir.is_dir() else []:
        horizon, error = _delta_horizon_of(path, expected_identity_hash)
        if error is not None:
            return None, error
        deltas.append(
            {
                "path": f"{DELTA_DIRNAME}/{path.name}",
                "horizon": horizon,
                "tape_position": None,
            }
        )
    head_horizon, error = _head_horizon_of(head_path, expected_identity_hash)
    if error is not None:
        return None, error
    managed = [
        str(path.relative_to(surface_path))
        for path in sorted(surface_path.rglob("*"))
        if path.is_file()
    ]
    return {
        "session": {"identity_hash": expected_identity_hash},
        "deltas": deltas,
        "head": {"path": HEAD_FILENAME, "horizon": head_horizon},
        "managed_files": managed,
    }, None


def _delta_horizon_of(
    path: Path, identity_hash: str
) -> tuple[dict[str, Any] | None, str | None]:
    """A Delta names its own boundary twice; both must agree."""
    try:
        first = path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None, f"Chat.Index Delta is unreadable or empty: {path}"
    match = _DELTA_HEADING_RE.match(first)
    if match is None:
        return None, (
            f"Chat.Index Delta does not declare its horizon heading: {path}"
        )
    if match.group("turn_id") != path.stem:
        return None, (
            f"Chat.Index Delta heading {match.group('turn_id')!r} disagrees with "
            f"its filename: {path.name}"
        )
    return {
        "session": identity_hash,
        "turn_id": match.group("turn_id"),
        "at": match.group("at"),
    }, None


def _head_horizon_of(
    path: Path, identity_hash: str
) -> tuple[dict[str, Any] | None, str | None]:
    for source in path.read_text(encoding="utf-8").splitlines():
        match = _HEAD_HORIZON_RE.match(source)
        if match is not None:
            return {
                "session": identity_hash,
                "turn_id": match.group("turn_id"),
                "at": match.group("at"),
            }, None
    return None, None


def _materialized_summary(
    discovery: dict[str, object], capture: dict[str, Any]
) -> dict[str, object]:
    return {
        **discovery,
        "state": "materialized",
        "layout": CAPTURE_LAYOUT,
        "delta_count": len(capture["deltas"]),
    }


def _invalid_result(
    *,
    command: str,
    root: Path,
    session: dict[str, Any],
    discovery: dict[str, object],
    error: str,
    include_capture: bool,
) -> dict[str, object]:
    return {
        "status": "ok",
        "command": command,
        "chatlas_root": str(root),
        "session": _session_locator(session),
        "chat_index": {
            **discovery,
            "state": "invalid",
            "warning": error,
            "freshness": {"state": "unknown", "reason": "invalid descriptor"},
        },
        **({"capture": None} if include_capture else {}),
    }


def _session_locator(session: dict[str, Any]) -> dict[str, object]:
    return {
        key: session.get(key)
        for key in ("identity_hash", "session_id", "provider", "uri")
    }


def _chatlas_root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


__all__ = [
    "CAPTURE_LAYOUT",
    "chat_index_discovery",
    "chat_index_source_hash",
    "chat_index_source_model",
    "compare_v2_source_tail",
    "chat_index_surface_path",
    "chatlas_chat_index_deltas",
    "chatlas_chat_index_files",
    "chatlas_chat_index_head",
    "chatlas_chat_index_home",
    "chatlas_chat_index_path",
    "chatlas_chat_index_show",
    "chatlas_chat_index_source",
    "chatlas_chat_index_status",
    "chatlas_chat_index_tail",
    "HEAD_FILENAME",
    "load_chat_index_capture",
    "source_prefix_at_horizon",
    "select_chat_index_session",
    "session_locator",
    "v2_source_tail",
]
