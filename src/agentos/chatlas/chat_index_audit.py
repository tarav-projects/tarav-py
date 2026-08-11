# $kw: --from Chat.Index --from Chat.Index.Delta --from Chat.Index.HEAD --from Index.Line --from Line.Home --from POI.Line --note [IMPL] one read-only pass replaces per-line anchor and home invocations and never repairs what it inspects --supp ^c20260804-60u
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from agentos._core.errors import CliError
from agentos.index.model import (
    canonical_index_line_statement,
    index_line_anchor_triplet_hash,
)
from agentos.index.model.identity import ANCHOR_RE

from agentos.chatlas.anchory import (
    LINE_BOUND_SCHEMAS,
    ChatlasSupportRuntimeCache,
    _load_session_model,
    chatlas_anchory_depot,
    parse_line_attachment,
    parse_support_set_record,
    resolve_support_set_record,
)
from agentos.chatlas.chat_index import (
    chat_index_discovery,
    chat_index_surface_path,
    load_chat_index_capture,
    resolve_delta_tape_positions,
    select_chat_index_session,
    session_locator,
    chat_index_source_model,
    compare_v2_source_tail,
    source_prefix_at_horizon,
)


AUDIT_SCHEMA = "agentos.chat-index.audit.v1"

_DELTA_HEADING_RE = re.compile(
    r"^# Chat\.Index\.Delta/(?P<turn_id>[^\s@]+)(?: @ (?P<at>\S+))?$"
)
_HEAD_HEADING = "# Chat.Index.HEAD"
_HEAD_HORIZON_RE = re.compile(
    r"^Evidence\.Horizon: `(?P<turn_id>[^`]+)`(?: @ (?P<at>\S+))?$"
)
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")

_BLOCKING = "blocking"
_ADVISORY = "advisory"


class _Line:
    """One parsed Index.Line occurrence on a materialized surface."""

    __slots__ = ("relative_path", "line_number", "source", "anchors", "statement_key")

    def __init__(
        self, *, relative_path: str, line_number: int, source: str, anchors: list[str]
    ) -> None:
        self.relative_path = relative_path
        self.line_number = line_number
        self.source = source
        self.anchors = anchors
        self.statement_key = canonical_index_line_statement(source)


def chatlas_chat_index_audit(
    *,
    surface: str | Path | None = None,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    """Audit one Chat.Index surface without changing anything it reads."""
    root, session, identity_hash = select_chat_index_session(
        command="chatlas chat-index audit",
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    if surface is None:
        surface_path = chat_index_surface_path(identity_hash, chatlas_root=root)
        surface_source = "live"
    else:
        surface_path = Path(surface).expanduser().resolve()
        surface_source = "staged"
        if not surface_path.is_dir():
            raise CliError(f"chatlas chat-index audit surface is not a directory: {surface_path}")

    result = audit_chat_index_surface(
        surface_path,
        identity_hash=identity_hash,
        session=session,
        chatlas_root=root,
        at_identity_path=surface is None,
    )
    return {
        "status": "ok",
        "command": "chatlas chat-index audit",
        "schema": AUDIT_SCHEMA,
        "chatlas_root": str(root),
        "session": session_locator(session),
        "surface_path": str(surface_path),
        "surface_source": surface_source,
        **result,
    }


def audit_chat_index_surface(
    surface_path: Path,
    *,
    identity_hash: str,
    session: dict[str, Any] | None = None,
    chatlas_root: Path | None = None,
    runtime_cache: ChatlasSupportRuntimeCache | None = None,
    include_line_inventory: bool = False,
    at_identity_path: bool = True,
) -> dict[str, object]:
    """The single reusable audit engine.

    The same pass serves the public command, staged validation before a swap,
    and post-install verification, so a surface can never be installed under
    weaker rules than the ones the public command reports.
    """
    findings: list[dict[str, object]] = []
    counts = _empty_counts()
    tail: dict[str, object] | None = None

    discovery = chat_index_discovery(identity_hash, chatlas_root=chatlas_root)
    capture, error = load_chat_index_capture(
        surface_path,
        expected_identity_hash=identity_hash,
        at_identity_path=at_identity_path,
    )
    if error is not None:
        _add(findings, "surface-unreadable", _BLOCKING, error)
        return _result(findings, counts, tail)
    assert capture is not None

    if session is None:
        _add(
            findings,
            "source-unavailable",
            _BLOCKING,
            "Chat.Index audit requires the live chat; there is no stored source",
        )
        return _result(findings, counts, tail)
    try:
        _canonical, source = chat_index_source_model(session, chatlas_root=chatlas_root)
    except (CliError, ValueError) as exc:
        _add(findings, "source-unavailable", _BLOCKING, str(exc))
        return _result(findings, counts, tail)
    source_turns = {
        str(entry["turn_ref"]["turn_id"]): entry for entry in source["turn_refs"]
    }

    tail = _audit_source_tail(session, capture, source, chatlas_root, findings)


    deltas = resolve_delta_tape_positions(capture["deltas"], source)
    counts["delta_count"] = len(deltas)

    delta_lines: list[tuple[dict[str, Any], _Line]] = []
    for delta in deltas:
        _audit_delta_horizon(delta, source_turns=source_turns, findings=findings)
        relative_path = str(delta["path"])
        parsed = _read_surface_file(surface_path, relative_path, findings)
        if parsed is None:
            continue
        for line in index_lines_of(relative_path, parsed):
            delta_lines.append((delta, line))

    head = capture["head"]
    head_relative = str(head["path"])
    head_lines: list[_Line] = []
    head_parsed = _read_surface_file(surface_path, head_relative, findings)
    if head_parsed is not None:
        _audit_head_horizon(
            head_parsed, head, source_turns=source_turns, findings=findings
        )
        head_lines = list(index_lines_of(head_relative, head_parsed))

    counts["delta_line_count"] = len(delta_lines)
    counts["head_line_count"] = len(head_lines)
    counts["line_count"] = len(delta_lines) + len(head_lines)

    all_lines = [line for _delta, line in delta_lines] + head_lines
    for line in all_lines:
        _audit_line_anchor_count(line, findings)

    anchors = _resolve_distinct_anchors(
        all_lines,
        chatlas_root=chatlas_root,
        runtime_cache=runtime_cache or ChatlasSupportRuntimeCache(),
        findings=findings,
    )
    counts["distinct_anchor_count"] = len(anchors)
    counts["resolved_anchor_count"] = sum(
        1 for record in anchors.values() if record is not None
    )

    _audit_anchor_attachments(all_lines, anchors, findings)
    _audit_delta_support_horizons(
        delta_lines, anchors, source_turns=source_turns, findings=findings
    )

    occurrences = _delta_occurrences(delta_lines)
    head_only, resolved_homes = _audit_head_coverage(
        head_lines, occurrences, findings, anchors=anchors
    )
    counts["home_count"] = len(resolved_homes)
    counts["head_only_line_count"] = len(head_only)
    _audit_head_only_support(
        head_only, anchors, source_turns=source_turns, findings=findings
    )

    result = _result(findings, counts, tail)
    result["homes"] = resolved_homes
    result["discovery"] = discovery
    if include_line_inventory:
        result["line_inventory"] = {
            "head": _line_occurrences(head_lines),
            "deltas": occurrences,
        }
    return result


def _empty_counts() -> dict[str, int]:
    return {
        "delta_count": 0,
        "delta_line_count": 0,
        "head_line_count": 0,
        "line_count": 0,
        "distinct_anchor_count": 0,
        "resolved_anchor_count": 0,
        "home_count": 0,
        "head_only_line_count": 0,


        "minted_anchor_count": 0,
        "reused_anchor_count": 0,
    }


def _result(
    findings: list[dict[str, object]],
    counts: dict[str, int],
    tail: dict[str, object] | None,
) -> dict[str, object]:
    blocking = sum(1 for finding in findings if finding["severity"] == _BLOCKING)
    counts["finding_count"] = len(findings)
    return {
        "ok": blocking == 0,
        "counts": counts,
        "finding_count": len(findings),
        "blocking_finding_count": blocking,
        "findings": findings,
        "tail": tail,
        "homes": [],
    }


def _add(
    findings: list[dict[str, object]],
    code: str,
    severity: str,
    message: str,
    **context: object,
) -> None:
    findings.append(
        {"code": code, "severity": severity, "message": message, **context}
    )


def _audit_source_tail(
    session: dict[str, Any],
    capture: dict[str, Any],
    source: dict[str, Any],
    chatlas_root: Path | None,
    findings: list[dict[str, object]],
) -> dict[str, object] | None:
    """The prefix HEAD declares against the live authoritative source."""
    try:
        tail = compare_v2_source_tail(
            source_prefix_at_horizon(source, capture["head"]["horizon"]), source
        )
    except (CliError, ValueError) as exc:
        _add(findings, "source-unavailable", _BLOCKING, str(exc))
        return None
    state = tail["state"]
    if state == "append-only":

        _add(
            findings,
            "source-append-only",
            _ADVISORY,
            f"{tail['pending_turn_count']} source turns are pending maintenance",
            pending_turn_count=tail["pending_turn_count"],
        )
    elif state != "current":
        _add(
            findings,
            "source-prefix-incompatible",
            _BLOCKING,
            f"captured source prefix is no longer reproducible: {state}",
            tail_state=state,
        )
    return tail


def _read_surface_file(
    surface_path: Path,
    relative_path: str,
    findings: list[dict[str, object]],
) -> list[str] | None:
    path = surface_path / relative_path
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _add(
            findings,
            "managed-file-unreadable",
            _BLOCKING,
            f"cannot read managed Chat.Index file: {relative_path} ({exc})",
            relative_path=relative_path,
        )
        return None


def _audit_delta_horizon(
    delta: dict[str, Any],
    *,
    source_turns: dict[str, dict[str, Any]],
    findings: list[dict[str, object]],
) -> None:
    """A Delta's horizon is a claim about the chat; the chat settles it.

    The heading and the filename already had to agree for the surface to be
    readable at all, so what is left to check is whether the turn they name is
    really a turn of the inspected prefix, at the timestamp the heading shows.
    """
    relative_path = str(delta["path"])
    horizon = delta["horizon"]
    turn_id = str(horizon["turn_id"])
    entry = source_turns.get(turn_id)
    if entry is None:
        _add(
            findings,
            "delta-horizon-absent-from-source",
            _BLOCKING,
            f"Delta horizon {turn_id} is not a turn of the inspected prefix",
            relative_path=relative_path,
            turn_id=turn_id,
        )
        return
    _audit_horizon_timestamp(
        horizon,
        entry,
        kind="delta",
        relative_path=relative_path,
        findings=findings,
    )


def _audit_head_horizon(
    body: list[str],
    head: dict[str, Any],
    *,
    source_turns: dict[str, dict[str, Any]],
    findings: list[dict[str, object]],
) -> None:
    relative_path = str(head["path"])
    if not body or body[0].rstrip() != _HEAD_HEADING:
        _add(
            findings,
            "head-heading-malformed",
            _BLOCKING,
            f"Chat.Index.HEAD must open with {_HEAD_HEADING!r}",
            relative_path=relative_path,
        )
        return
    horizon = head.get("horizon")
    if horizon is None:
        _add(
            findings,
            "head-horizon-missing",
            _BLOCKING,
            "Chat.Index.HEAD must declare 'Evidence.Horizon: `<turn-id>`[ @ <at>]'",
            relative_path=relative_path,
        )
        return
    turn_id = str(horizon["turn_id"])
    entry = source_turns.get(turn_id)
    if entry is None:
        _add(
            findings,
            "head-horizon-absent-from-source",
            _BLOCKING,
            f"Chat.Index.HEAD evidence horizon {turn_id} is not a turn of the "
            "inspected prefix",
            relative_path=relative_path,
            turn_id=turn_id,
        )
        return
    _audit_horizon_timestamp(
        horizon,
        entry,
        kind="head",
        relative_path=relative_path,
        findings=findings,
    )


def _audit_horizon_timestamp(
    horizon: dict[str, Any],
    entry: dict[str, Any],
    *,
    kind: str,
    relative_path: str,
    findings: list[dict[str, object]],
) -> None:
    declared = horizon.get("at")
    evidenced = entry["turn_ref"].get("at")
    if declared is not None and declared != evidenced:
        _add(
            findings,
            f"{kind}-horizon-timestamp-mismatch",
            _BLOCKING,
            f"horizon {horizon['turn_id']} is timestamped {declared!r} but the "
            f"chat records {evidenced!r}",
            relative_path=relative_path,
        )
    elif declared is None and evidenced:


        _add(
            findings,
            f"{kind}-horizon-timestamp-omitted",
            _ADVISORY,
            f"horizon {horizon['turn_id']} is timestamped {evidenced!r} in the "
            "chat but the surface omits it",
            relative_path=relative_path,
        )


def index_lines_of(relative_path: str, body: list[str]) -> list[_Line]:
    """Index.Line occurrences of one surface file, ignoring fenced content."""
    lines: list[_Line] = []
    in_fence = False
    for line_number, source in enumerate(body, start=1):
        if _FENCE_RE.match(source):
            in_fence = not in_fence
            continue
        if in_fence or not source.lstrip().startswith("- "):
            continue
        lines.append(
            _Line(
                relative_path=relative_path,
                line_number=line_number,
                source=source,
                anchors=_trailing_anchors(source),
            )
        )
    return lines


def _trailing_anchors(source: str) -> list[str]:
    tokens = source.rstrip().split()
    anchors: list[str] = []
    while tokens:
        match = ANCHOR_RE.fullmatch(tokens[-1])
        if match is None:
            break
        anchors.append(match.group("anchor"))
        tokens.pop()
    anchors.reverse()
    return anchors


def _audit_line_anchor_count(line: _Line, findings: list[dict[str, object]]) -> None:
    if not line.anchors:
        _add(
            findings,
            "line-without-anchor",
            _BLOCKING,
            "Index.Line carries no trailing Support.Reference",
            **_locator(line),
        )
    elif len(line.anchors) > 1:
        _add(
            findings,
            "line-with-multiple-anchors",
            _BLOCKING,
            f"Index.Line carries {len(line.anchors)} trailing anchors; exactly one "
            "Support.Reference is allowed",
            anchors=list(line.anchors),
            **_locator(line),
        )


def _resolve_distinct_anchors(
    lines: list[_Line],
    *,
    chatlas_root: Path | None,
    runtime_cache: ChatlasSupportRuntimeCache,
    findings: list[dict[str, object]],
) -> dict[str, dict[str, Any] | None]:
    """Resolve each distinct anchor exactly once for the whole surface."""
    depot = chatlas_anchory_depot(chatlas_root)
    models: dict[str, dict[str, Any]] = {}

    def loader(identity: str) -> dict[str, Any]:
        if identity not in models:
            models[identity] = _load_session_model(identity, chatlas_root=chatlas_root)
        return models[identity]

    records: dict[str, dict[str, Any] | None] = {}
    for anchor in sorted({anchor for line in lines for anchor in line.anchors}):
        resolution = depot.resolve(anchor)
        if resolution is None:
            records[anchor] = None
            _add(
                findings,
                "anchor-unresolved",
                _BLOCKING,
                f"anchor is absent from the Chatlas depot: ^{anchor}",
                anchor=anchor,
            )
            continue
        record = dict(resolution.record)
        if record.get("schema") not in LINE_BOUND_SCHEMAS:
            records[anchor] = None
            _add(
                findings,
                "anchor-not-line-bound",
                _BLOCKING,
                f"anchor ^{anchor} is a generic Support.Set; an Index.Line requires "
                "a line-bound v4, v5, or v6 record",
                anchor=anchor,
            )
            continue
        try:
            resolve_support_set_record(
                record,
                model_loader=loader,
                runtime_cache=runtime_cache,
            )
        except CliError as exc:
            records[anchor] = None
            _add(
                findings,
                "anchor-support-unresolvable",
                _BLOCKING,
                f"anchor ^{anchor} support does not resolve: {exc}",
                anchor=anchor,
            )
            continue
        records[anchor] = record
    return records


def _audit_anchor_attachments(
    lines: list[_Line],
    anchors: dict[str, dict[str, Any] | None],
    findings: list[dict[str, object]],
) -> None:
    attached: dict[str, set[str]] = {}
    for line in lines:
        if len(line.anchors) != 1:
            continue
        anchor = line.anchors[0]
        attached.setdefault(anchor, set()).add(
            index_line_anchor_triplet_hash(line.source, anchor)
        )
        record = anchors.get(anchor)
        if record is None:
            continue
        attachment = parse_line_attachment(record)
        current_hash = index_line_anchor_triplet_hash(line.source, anchor)
        if attachment is None or attachment["triplet_hash"] != current_hash:
            _add(
                findings,
                "anchor-attachment-drift",
                _BLOCKING,
                f"anchor ^{anchor} attachment does not assert the canonical line "
                "triplet carrying it",
                anchor=anchor,
                current_triplet_hash=current_hash,
                stored_triplet_hash=None if attachment is None else attachment["triplet_hash"],
                **_locator(line),
            )
    for anchor, triplet_hashes in sorted(attached.items()):
        if len(triplet_hashes) > 1:
            _add(
                findings,
                "anchor-triplet-collision",
                _BLOCKING,
                f"anchor ^{anchor} is attached to {len(triplet_hashes)} distinct "
                "canonical Index.Line triplets",
                anchor=anchor,
                triplet_hashes=sorted(triplet_hashes),
            )


def _audit_delta_support_horizons(
    delta_lines: list[tuple[dict[str, Any], _Line]],
    anchors: dict[str, dict[str, Any] | None],
    *,
    source_turns: dict[str, dict[str, Any]],
    findings: list[dict[str, object]],
) -> None:
    for delta, line in delta_lines:
        if len(line.anchors) != 1 or delta["tape_position"] is None:


            continue
        record = anchors.get(line.anchors[0])
        if record is None:
            continue
        for member in parse_support_set_record(record):
            entry = _qualifying_user_turn(member, source_turns, line, findings)
            if entry is None:
                continue
            if entry["tape_position"] > delta["tape_position"]:
                _add(
                    findings,
                    "support-beyond-delta-horizon",
                    _BLOCKING,
                    f"support turn {member['turn_id']} sits after the Delta horizon "
                    f"{delta['horizon']['turn_id']}",
                    anchor=line.anchors[0],
                    turn_id=member["turn_id"],
                    **_locator(line),
                )


def _audit_head_only_support(
    head_only: list[_Line],
    anchors: dict[str, dict[str, Any] | None],
    *,
    source_turns: dict[str, dict[str, Any]],
    findings: list[dict[str, object]],
) -> None:
    """A HEAD-first POI.Line owns its grounding; it inherits none."""
    for line in head_only:
        if len(line.anchors) != 1:
            continue
        record = anchors.get(line.anchors[0])
        if record is None:
            continue
        for member in parse_support_set_record(record):
            _qualifying_user_turn(member, source_turns, line, findings)


def _qualifying_user_turn(
    member: dict[str, Any],
    source_turns: dict[str, dict[str, Any]],
    line: _Line,
    findings: list[dict[str, object]],
) -> dict[str, Any] | None:
    entry = source_turns.get(str(member["turn_id"]))
    if (
        entry is None
        or entry.get("role") != "user"
        or entry.get("producer_type") != "human"
    ):
        _add(
            findings,
            "support-not-qualifying-user-turn",
            _BLOCKING,
            f"support turn {member['turn_id']} is not a qualifying human user turn "
            "of this Chat.Index source",
            turn_id=member["turn_id"],
            **_locator(line),
        )
        return None
    return entry


def _delta_occurrences(
    delta_lines: list[tuple[dict[str, Any], _Line]],
) -> dict[str, list[dict[str, object]]]:
    """Typed statement key to its descriptor-ordered Delta occurrences, built once.

    This map is what replaces rescanning every Delta for every HEAD line.
    """
    occurrences: dict[str, list[dict[str, object]]] = {}
    for delta, line in delta_lines:
        occurrences.setdefault(line.statement_key, []).append(
            {
                "relative_path": line.relative_path,
                "line_number": line.line_number,
                "anchors": list(line.anchors),
                "tape_position": delta["tape_position"],
                "horizon": delta["horizon"],
            }
        )
    return occurrences


def _line_occurrences(lines: list[_Line]) -> dict[str, list[dict[str, object]]]:
    occurrences: dict[str, list[dict[str, object]]] = {}
    for line in lines:
        occurrences.setdefault(line.statement_key, []).append(
            {**_locator(line), "anchors": list(line.anchors)}
        )
    return occurrences


def _audit_head_coverage(
    head_lines: list[_Line],
    occurrences: dict[str, list[dict[str, object]]],
    findings: list[dict[str, object]],
    *,
    anchors: dict[str, dict[str, Any] | None],
) -> tuple[list[_Line], list[dict[str, object]]]:
    head_only: list[_Line] = []
    homes: list[dict[str, object]] = []
    for line in head_lines:
        found = occurrences.get(line.statement_key)
        if not found:
            head_only.append(line)
            _add(
                findings,
                "head-line-without-delta-home",
                _ADVISORY,
                "Chat.Index.HEAD line has no exact Chat.Index.Delta occurrence",
                statement_key=line.statement_key,
                **_locator(line),
            )
            continue
        oldest = min(found, key=lambda item: item["tape_position"])
        if found[0] is not oldest:
            _add(
                findings,
                "home-not-oldest-occurrence",
                _ADVISORY,
                "Delta file order disagrees with tape order; Line.Home is the "
                "oldest occurrence by evidence, not by listing",
                statement_key=line.statement_key,
                **_locator(line),
            )
        homes.append(
            {
                "statement_key": line.statement_key,
                "head_line_number": line.line_number,
                "home": oldest,
                "occurrences": found,
                "occurrence_count": len(found),
            }
        )
    return head_only, homes


def _locator(line: _Line) -> dict[str, object]:
    return {"relative_path": line.relative_path, "line_number": line.line_number}


__all__ = [
    "AUDIT_SCHEMA",
    "index_lines_of",
    "audit_chat_index_surface",
    "chatlas_chat_index_audit",
]
