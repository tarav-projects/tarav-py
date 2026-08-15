# $kw: --from Chat.Touched.Index --from Normal.Turn --from User.Turn.Purity --from Normal.Turn.Ref
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
import re

from tarav._core.errors import CliError
from tarav.chatlas.index_query import select_materialization_row
from tarav.chatlas.index_store import load_chatlas_session_index_rows
from tarav.chatlas.normal_turn import normal_turn_ref
from tarav.chatlas.normalization.session_model.events import (
    normal_turn_id,
    normal_turn_kind,
)
from tarav.chatlas.normalization.session_model.messages import content_text
from tarav.chatlas.paths import default_chatlas_root
from tarav.chatlas.session_cache import load_chatlas_session_model


DEFAULT_QUOTE_MIN_LENGTH = 40
DEFAULT_QUOTE_THRESHOLD = 0.75
DEFAULT_QUOTE_LOOKBACK = 5
_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class _Token:
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class _VisibleTurn:
    sequence: int
    kind: str
    text: str
    events: tuple[dict[str, Any], ...]
    tokens: tuple[_Token, ...]


@dataclass(frozen=True)
class _Alignment:
    assistant_start: int
    assistant_end: int
    user_start: int
    user_end: int
    score: float
    kind: str


def chatlas_touch_heuristics_quotes(
    *,
    session: str,
    min_length: int = DEFAULT_QUOTE_MIN_LENGTH,
    threshold: float = DEFAULT_QUOTE_THRESHOLD,
    lookback: int = DEFAULT_QUOTE_LOOKBACK,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    _validate_parameters(
        min_length=min_length,
        threshold=threshold,
        lookback=lookback,
    )
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    row, matched_uri = _select_session_row(session, chatlas_root=root)
    materialization_row = select_materialization_row(
        row,
        uri=matched_uri,
    )
    model = load_chatlas_session_model(materialization_row, chatlas_root=root)
    payload = quote_touch_evidence_from_session_model(
        model,
        min_length=min_length,
        threshold=threshold,
        lookback=lookback,
    )
    payload["chatlas_root"] = str(root)
    payload["session"] = {
        "identity_hash": row.get("identity_hash"),
        "session_id": materialization_row.get("session_id"),
        "uri": materialization_row.get("uri"),
    }
    return payload


def quote_touch_evidence_from_session_model(
    session_model: dict[str, Any],
    *,
    min_length: int = DEFAULT_QUOTE_MIN_LENGTH,
    threshold: float = DEFAULT_QUOTE_THRESHOLD,
    lookback: int = DEFAULT_QUOTE_LOOKBACK,
) -> dict[str, object]:
    _validate_parameters(
        min_length=min_length,
        threshold=threshold,
        lookback=lookback,
    )
    identity = _session_identity(session_model)
    findings: list[dict[str, object]] = []
    assistant_turns: list[_VisibleTurn] = []
    for turn in _visible_turns(session_model):
        if turn.kind == "assistant":
            assistant_turns.append(turn)
            continue
        if turn.kind != "user":
            continue
        predecessors = list(reversed(assistant_turns[-lookback:]))
        for distance, assistant_turn in enumerate(predecessors, start=1):
            alignment = _align_turns(
                assistant_turn.tokens,
                turn.tokens,
                min_length=min_length,
                threshold=threshold,
            )
            if alignment is None:
                continue
            findings.append(
                _finding_payload(
                    identity=identity,
                    assistant_turn=assistant_turn,
                    user_turn=turn,
                    alignment=alignment,
                    predecessor_distance=distance,
                )
            )
    return {
        "status": "ok",
        "command": "chatlas touch-heuristics quotes",
        "session": {"identity_hash": identity},
        "parameters": {
            "min_length": min_length,
            "threshold": threshold,
            "lookback": lookback,
        },
        "finding_count": len(findings),
        "findings": findings,
    }


def _validate_parameters(
    *,
    min_length: int,
    threshold: float,
    lookback: int,
) -> None:
    if (
        isinstance(min_length, bool)
        or not isinstance(min_length, int)
        or min_length <= 0
    ):
        raise ValueError("min_length must be a positive integer")
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback <= 0:
        raise ValueError("lookback must be a positive integer")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not 0 <= threshold <= 1
    ):
        raise ValueError("threshold must be between 0 and 1")


def _session_identity(session_model: dict[str, Any]) -> str:
    session = session_model.get("session")
    identity = session.get("identity_hash") if isinstance(session, dict) else None
    if not isinstance(identity, str) or not identity:
        raise CliError("quote touch heuristic requires session.identity_hash")
    return identity


def _select_session_row(
    selector: str,
    *,
    chatlas_root: Path,
) -> tuple[dict[str, Any], str | None]:
    if not selector:
        raise CliError("chatlas touch-heuristics quotes requires a non-empty --session")
    index = load_chatlas_session_index_rows(chatlas_root=chatlas_root)
    matches: dict[str, tuple[dict[str, Any], str | None]] = {}
    for row in index.rows:
        identity = row.get("identity_hash")
        if not isinstance(identity, str) or not identity:
            continue
        row_uri = row.get("uri")
        row_session_id = row.get("session_id")
        matched_uri = (
            row_uri if isinstance(row_uri, str) and row_uri == selector else None
        )
        if (
            matched_uri is not None
            or row_session_id == selector
            or identity.startswith(selector)
        ):
            matches[identity] = (row, matched_uri)
    if not matches:
        raise CliError(
            "no indexed Chatlas session matched the "
            f"chatlas touch-heuristics quotes selector: {selector!r}"
        )
    if len(matches) > 1:
        candidates = ", ".join(sorted(matches)[:5])
        raise CliError(
            "multiple Chatlas sessions matched the "
            f"chatlas touch-heuristics quotes selector: {candidates}"
        )
    return next(iter(matches.values()))


def _visible_turns(session_model: dict[str, Any]) -> list[_VisibleTurn]:
    chat = session_model.get("chat")
    source_events = chat.get("events") if isinstance(chat, dict) else None
    events = [event for event in source_events or [] if isinstance(event, dict)]
    events.sort(key=_event_sequence)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        turn_id = normal_turn_id(event)
        if turn_id is not None:
            grouped.setdefault(turn_id, []).append(event)

    turns: list[_VisibleTurn] = []
    for grouped_events in grouped.values():
        kinds = {normal_turn_kind(event) for event in grouped_events}
        if len(kinds) != 1:
            continue
        kind = next(iter(kinds))
        if kind not in {"user", "assistant"}:
            continue
        texts = [
            text
            for event in grouped_events
            if (text := _visible_message_text(event, kind))
        ]
        if not texts:
            continue
        text = "\n".join(texts)
        tokens = tuple(_normalized_tokens(text))
        if not tokens:
            continue
        turns.append(
            _VisibleTurn(
                sequence=min(_event_sequence(event) for event in grouped_events),
                kind=kind,
                text=text,
                events=tuple(grouped_events),
                tokens=tokens,
            )
        )
    turns.sort(key=lambda turn: turn.sequence)
    return turns


def _event_sequence(event: dict[str, Any]) -> int:
    sequence = event.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        return 2**63 - 1
    return sequence


def _visible_message_text(event: dict[str, Any], kind: str) -> str:
    if event.get("kind") != "message":
        return ""
    surfaces = event.get("surfaces")
    if not isinstance(surfaces, dict) or surfaces.get("transcript") != "visible":
        return ""
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("role") != kind:
        return ""
    return content_text(payload.get("content"))


def _normalized_tokens(text: str) -> list[_Token]:
    return [
        _Token(match.group(0).casefold(), match.start(), match.end())
        for match in _TOKEN_PATTERN.finditer(text)
        if match.group(0)
    ]


def _align_turns(
    assistant: tuple[_Token, ...],
    user: tuple[_Token, ...],
    *,
    min_length: int,
    threshold: float,
) -> _Alignment | None:
    exact = _longest_exact_alignment(assistant, user, min_length=min_length)
    if exact is not None:
        return exact
    return _best_fuzzy_alignment(
        assistant,
        user,
        min_length=min_length,
        threshold=threshold,
    )


def _longest_exact_alignment(
    assistant: tuple[_Token, ...],
    user: tuple[_Token, ...],
    *,
    min_length: int,
) -> _Alignment | None:
    matcher = SequenceMatcher(
        None,
        [token.value for token in assistant],
        [token.value for token in user],
        autojunk=False,
    )
    candidates: list[tuple[int, int, int, int]] = []
    for block in matcher.get_matching_blocks():
        if block.size == 0:
            continue
        length = _normalized_length(assistant, block.a, block.a + block.size)
        if length >= min_length:
            candidates.append((length, block.size, block.a, block.b))
    if not candidates:
        return None
    _, size, assistant_start, user_start = max(
        candidates,
        key=lambda candidate: (
            candidate[0],
            candidate[1],
            -candidate[2],
            -candidate[3],
        ),
    )
    return _Alignment(
        assistant_start=assistant_start,
        assistant_end=assistant_start + size,
        user_start=user_start,
        user_end=user_start + size,
        score=1.0,
        kind="exact",
    )


def _best_fuzzy_alignment(
    assistant: tuple[_Token, ...],
    user: tuple[_Token, ...],
    *,
    min_length: int,
    threshold: float,
) -> _Alignment | None:
    previous: list[tuple[int, int, int, int]] = [(0, 0, 0, 0)] * (len(user) + 1)
    best: tuple[tuple[int, float, int, int, int], _Alignment] | None = None
    for assistant_end, assistant_token in enumerate(assistant, start=1):
        current: list[tuple[int, int, int, int]] = [(0, assistant_end, 0, 0)]
        for user_end, user_token in enumerate(user, start=1):
            candidates = [
                _advance_cell(
                    previous[user_end - 1],
                    assistant_start=assistant_end - 1,
                    user_start=user_end - 1,
                    delta=2 if assistant_token.value == user_token.value else -1,
                    matched=assistant_token.value == user_token.value,
                ),
                _advance_cell(
                    previous[user_end],
                    assistant_start=assistant_end - 1,
                    user_start=user_end,
                    delta=-1,
                    matched=False,
                ),
                _advance_cell(
                    current[user_end - 1],
                    assistant_start=assistant_end,
                    user_start=user_end - 1,
                    delta=-1,
                    matched=False,
                ),
            ]
            cell = max(
                candidates,
                key=lambda item: (
                    item[0],
                    item[3],
                    -max(assistant_end - item[1], user_end - item[2]),
                ),
            )
            if cell[0] <= 0:
                cell = (0, assistant_end, user_end, 0)
            current.append(cell)
            score, assistant_start, user_start, matches = cell
            if score <= 0:
                continue
            assistant_span = assistant_end - assistant_start
            user_span = user_end - user_start
            similarity = matches / max(assistant_span, user_span)
            aligned_length = min(
                _normalized_length(assistant, assistant_start, assistant_end),
                _normalized_length(user, user_start, user_end),
            )
            if aligned_length < min_length or similarity < threshold:
                continue
            alignment = _Alignment(
                assistant_start=assistant_start,
                assistant_end=assistant_end,
                user_start=user_start,
                user_end=user_end,
                score=round(similarity, 6),
                kind="fuzzy",
            )
            rank = (
                aligned_length,
                similarity,
                matches,
                -assistant_start,
                -user_start,
            )
            if best is None or rank > best[0]:
                best = (rank, alignment)
        previous = current
    return best[1] if best is not None else None


def _advance_cell(
    cell: tuple[int, int, int, int],
    *,
    assistant_start: int,
    user_start: int,
    delta: int,
    matched: bool,
) -> tuple[int, int, int, int]:
    score, current_assistant_start, current_user_start, matches = cell
    if score <= 0:
        current_assistant_start = assistant_start
        current_user_start = user_start
    return (
        score + delta,
        current_assistant_start,
        current_user_start,
        matches + int(matched),
    )


def _normalized_length(tokens: tuple[_Token, ...], start: int, end: int) -> int:
    values = tokens[start:end]
    if not values:
        return 0
    return sum(len(token.value) for token in values) + len(values) - 1


def _finding_payload(
    *,
    identity: str,
    assistant_turn: _VisibleTurn,
    user_turn: _VisibleTurn,
    alignment: _Alignment,
    predecessor_distance: int,
) -> dict[str, object]:
    return {
        "class": "Touch.Evidence",
        "heuristic": "quotes",
        "user_turn_ref": normal_turn_ref(identity, list(user_turn.events)),
        "assistant_turn_ref": normal_turn_ref(identity, list(assistant_turn.events)),
        "user_span": _span_payload(
            user_turn.text,
            user_turn.tokens,
            alignment.user_start,
            alignment.user_end,
        ),
        "assistant_span": _span_payload(
            assistant_turn.text,
            assistant_turn.tokens,
            alignment.assistant_start,
            alignment.assistant_end,
        ),
        "normalized_aligned_text": {
            "user": _normalized_text(
                user_turn.tokens,
                alignment.user_start,
                alignment.user_end,
            ),
            "assistant": _normalized_text(
                assistant_turn.tokens,
                alignment.assistant_start,
                alignment.assistant_end,
            ),
        },
        "alignment_score": alignment.score,
        "predecessor_distance": predecessor_distance,
        "match_kind": alignment.kind,
    }


def _span_payload(
    text: str,
    tokens: tuple[_Token, ...],
    start: int,
    end: int,
) -> dict[str, object]:
    source_start = tokens[start].start
    source_end = tokens[end - 1].end
    return {
        "start": source_start,
        "end": source_end,
        "text": text[source_start:source_end],
    }


def _normalized_text(tokens: tuple[_Token, ...], start: int, end: int) -> str:
    return " ".join(token.value for token in tokens[start:end])


def format_quote_touch_evidence_text(payload: dict[str, Any]) -> str:
    findings = payload.get("findings")
    findings = findings if isinstance(findings, list) else []
    if not findings:
        return "no user quotations matched the configured touch heuristic"
    lines: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        user_ref = finding.get("user_turn_ref")
        assistant_ref = finding.get("assistant_turn_ref")
        user_id = user_ref.get("turn_id") if isinstance(user_ref, dict) else "?"
        assistant_id = (
            assistant_ref.get("turn_id") if isinstance(assistant_ref, dict) else "?"
        )
        lines.append(
            f"{user_id} quotes {assistant_id} "
            f"({finding.get('match_kind')}, score={finding.get('alignment_score')}, "
            f"distance={finding.get('predecessor_distance')})"
        )
        for label in ("assistant", "user"):
            span = finding.get(f"{label}_span")
            text = span.get("text") if isinstance(span, dict) else ""
            lines.append(f"  {label}: {text}")
        lines.append("")
    lines.append(f"{len(findings)} quotation finding(s)")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_QUOTE_LOOKBACK",
    "DEFAULT_QUOTE_MIN_LENGTH",
    "DEFAULT_QUOTE_THRESHOLD",
    "chatlas_touch_heuristics_quotes",
    "format_quote_touch_evidence_text",
    "quote_touch_evidence_from_session_model",
]
