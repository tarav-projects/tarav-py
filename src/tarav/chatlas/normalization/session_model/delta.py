# $kw: ^chatlas-delta-normalization --from Delta.Normalization::Chatlas --note [CT] delta normalization reads archived raw data and falls back to full derivation on validation failure ^c20260712-9u --supp static cleanup authorized ^c20260730-34u
"""`Delta.Normalization::Chatlas` — incremental claude-code session derivation.

A delta pass resumes from a `Normalization.Delta.Checkpoint::Chatlas` (a small
file beside the derivation caches) plus the existing `Session.Model.Artifact`:
the frozen tape prefix and frozen projection prefixes are reused verbatim, only
the volatile tail and appended raw records are re-normalized, and the results
are spliced into a full `NormalizationResult` byte-identical to a full
derivation. Any validation failure returns None and the caller falls back to
full derivation — delta is an optimization, never a source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tarav.chatlas._payload_helpers import string_or_none
from tarav.chatlas.normalization.session_model._claude import (
    _ClaudeDeltaResume,
    _claude_context_snapshot,
    _claude_closed_estimate_boundary,
    _frozen_pass_warnings,
    _claude_normalization_metadata,
    _claude_normalization_passes,
    _claude_normalization_warnings,
    _claude_record_kind,
    _claude_record_starts_interaction,
    claude_turn_id,
    _claude_unsupported_concepts,
    _load_claude_raw_session_records,
    _claude_raw_record_counts,
    _claude_tail_has_conversation_fork,
    _claude_tail_has_compaction,
    _ClaudeRawSession,
    _reslice_raw_session,
)
from tarav.chatlas.normalization.session_model.artifact import (
    SESSION_MODEL_TAPE_ARTIFACT,
)
from tarav.chatlas.normalization.session_model.normalization import NormalizationResult
from tarav.chatlas.normalization.session_model.provenance import (
    attach_tape_provenance,
    event_chain_hash,
    event_closed_estimate,
    event_stored_source_hash,
    event_source_hash,
    record_payload_hash,
)
from tarav.chatlas.normalization.session_model.source_refs import (
    source_ref_record_indices,
)
from tarav.chatlas.event_ref import event_ref
from tarav.chatlas.trust_tier import (
    TRUST_APPEND,
    TRUST_REBUILD,
    TRUST_TIERS,
    TRUST_VERIFY,
    current_trust_tier,
    set_trust_tier,
)

DELTA_CHECKPOINT_SCHEMA = "chatlas.delta-checkpoint.v3"
DELTA_CHECKPOINTS_DIRNAME = Path("cache") / "delta-checkpoints"



def delta_checkpoint_path(
    chatlas_root: Path,
    *,
    provider: str,
    session_id: str,
) -> Path:
    return chatlas_root / DELTA_CHECKPOINTS_DIRNAME / provider / f"{session_id}.json"


def save_delta_checkpoint(
    chatlas_root: Path,
    *,
    provider: str,
    session_id: str,
    source_path: Path,
    delta_state: dict[str, object],
) -> None:
    path = delta_checkpoint_path(chatlas_root, provider=provider, session_id=session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": DELTA_CHECKPOINT_SCHEMA,
                "provider": provider,
                "session_id": session_id,
                "source_path": str(source_path),
                "state": delta_state,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def load_delta_checkpoint(
    chatlas_root: Path,
    *,
    provider: str,
    session_id: str,
) -> dict[str, Any] | None:
    path = delta_checkpoint_path(chatlas_root, provider=provider, session_id=session_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != DELTA_CHECKPOINT_SCHEMA:
        return None
    state = payload.get("state")
    if not isinstance(state, dict):
        return None
    return payload


def discard_delta_checkpoint(
    chatlas_root: Path,
    *,
    provider: str,
    session_id: str,
) -> None:
    path = delta_checkpoint_path(chatlas_root, provider=provider, session_id=session_id)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _scan_line_end_offset(path: Path, line_count: int) -> int | None:
    """Byte offset just past line `line_count` (1-indexed), scanning without parsing."""
    remaining = line_count
    offset = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            position = 0
            while remaining:
                found = chunk.find(b"\n", position)
                if found < 0:
                    break
                remaining -= 1
                position = found + 1
            offset += position if remaining == 0 else len(chunk)
            if remaining == 0:
                return offset
    return None


def _read_frozen_artifact_pieces(
    artifact_dir: Path,
    *,
    state: dict[str, Any],
) -> dict[str, list[dict[str, object]]] | None:



    tape_path = artifact_dir / SESSION_MODEL_TAPE_ARTIFACT
    if not tape_path.is_file():
        return None

    sequence_base = int(state["sequence_base"])
    frozen_events: list[dict[str, object]] = []
    try:
        with tape_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                frozen_events.append(json.loads(line))
                if len(frozen_events) == sequence_base:
                    break
    except (OSError, json.JSONDecodeError):
        return None
    if len(frozen_events) < sequence_base:
        return None
    if event_chain_hash(frozen_events[-1]) != state.get("chain_seed"):
        return None

    pieces: dict[str, list[dict[str, object]]] = {"events": frozen_events}
    for key, filename, count_key in (
        ("messages", "messages.json", "message_index_base"),
        ("model_runs", "model_runs.json", "model_run_index_base"),
        ("tool_invocations", "tool_invocations.json", "tool_invocation_index_base"),
        ("usage", "usage.json", "usage_index_base"),
    ):
        try:
            rows = json.loads((artifact_dir / filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        count = int(state[count_key])
        if not isinstance(rows, list) or len(rows) < count:
            return None
        pieces[key] = rows[:count]
    return pieces


def _tail_extends_linearly(
    tail_records: list[Any],
    *,
    last_active_uuid: str | None,
) -> bool:
    """A tail record whose parent points deeper into the frozen prefix than its
    last active uuid signals a rewind/fork — frozen events may need lineage
    marks, so the pass must fall back to full derivation."""
    known: set[str] = set()
    if last_active_uuid is not None:
        known.add(last_active_uuid)
    for record in tail_records:
        parent = record.parent_uuid
        if parent is not None and parent not in known:
            return False
        if record.uuid is not None:
            known.add(record.uuid)
    return True


def _sum_raw_counts(
    frozen: dict[str, Any],
    tail: dict[str, Any],
) -> dict[str, object]:
    record_types: dict[str, int] = dict(frozen.get("record_types") or {})
    for kind, count in (tail.get("record_types") or {}).items():
        record_types[kind] = record_types.get(kind, 0) + count
    summed: dict[str, object] = {}
    for key in frozen:
        if key == "record_types":
            summed[key] = dict(sorted(record_types.items()))
        else:
            summed[key] = int(frozen.get(key) or 0) + int(tail.get(key) or 0)
    return summed


def _verify_frozen_prefix(
    source_path: Path,
    *,
    frozen_events: list[dict[str, object]],
    frozen_record_count: int,
    source_ref_id: str | None,
) -> bool:
    prefix = _load_claude_raw_session_records(source_path, source_ref_id=source_ref_id)
    records = prefix.records[:frozen_record_count]
    if len(records) < frozen_record_count:
        return False
    record_hashes = {
        record.record_index: record_payload_hash(record.payload) for record in records
    }
    for event in frozen_events:
        if event_source_hash(
            event, record_hashes=record_hashes
        ) != event_stored_source_hash(event):
            return False
    return True


def _delta_state_after_splice(
    *,
    old_state: dict[str, Any],
    tail_session: _ClaudeRawSession,
    tail_passes: Any,
    merged_pass_warnings: dict[str, list[str]],
    events: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    messages_tail_final_count: int,
    usage_tail_final_count: int,
    new_boundary: int,
) -> dict[str, object] | None:
    if tail_passes.pass_warnings.get("load"):
        return None
    new_frozen_count = new_boundary - 1
    if new_frozen_count <= 0:
        return None
    frozen_events = [event for event in events if event_closed_estimate(event)]
    if not frozen_events or any(
        event_closed_estimate(event) for event in events[len(frozen_events):]
    ):
        return None

    interaction_count = int(old_state["interaction_count"])
    current_turn_id = old_state.get("current_turn_id")
    last_context_snapshot = old_state.get("last_context_snapshot")
    last_active_uuid = old_state.get("last_active_uuid")
    newly_frozen = [
        record
        for record in tail_session.records
        if record.record_index <= new_frozen_count
    ]
    for record in newly_frozen:
        if _claude_record_kind(record) == "last-prompt":
            continue
        if _claude_record_starts_interaction(record):
            interaction_count += 1
            current_turn_id = claude_turn_id(record, ordinal=interaction_count)
        snapshot = _claude_context_snapshot(record)
        if snapshot and snapshot != last_context_snapshot:
            last_context_snapshot = snapshot
        if record.uuid is not None:
            last_active_uuid = record.uuid

    frozen_invocation_count = 0
    for invocation in tool_invocations:
        indices = list(source_ref_record_indices(invocation.get("source_refs")))
        if indices and max(indices) <= new_frozen_count:
            frozen_invocation_count += 1

    frozen_run_count = 0
    span_end_base = 0
    for model_run in model_runs:

        indices = list(source_ref_record_indices(model_run.get("source_refs")))
        if not indices or max(indices) > new_frozen_count:
            continue
        frozen_run_count += 1
        span_end_base = max(span_end_base, max(indices))

    if newly_frozen:
        frozen_line = newly_frozen[-1].line
    else:
        frozen_line = int(old_state["frozen_line"])

    new_message_index_base = int(old_state["message_index_base"]) + messages_tail_final_count
    new_usage_index_base = int(old_state["usage_index_base"]) + usage_tail_final_count



    volatile_session = _reslice_raw_session(
        tail_session,
        [
            record
            for record in tail_session.records
            if record.record_index > new_frozen_count
        ],
    )
    volatile_passes = _claude_normalization_passes(
        volatile_session,
        _ClaudeDeltaResume(
            sequence_base=len(frozen_events),
            interaction_count=interaction_count,
            current_turn_id=string_or_none(current_turn_id),
            last_context_snapshot=last_context_snapshot
            if isinstance(last_context_snapshot, dict)
            else None,
            message_index_base=new_message_index_base,
            model_run_index_base=frozen_run_count,
            tool_invocation_index_base=frozen_invocation_count,
            usage_index_base=new_usage_index_base,
            span_end_base=span_end_base,
        ),
    )
    frozen_pass_warnings = _frozen_pass_warnings(
        merged_pass_warnings, volatile_passes.pass_warnings
    )
    if frozen_pass_warnings is None:
        return None

    frozen_raw_counts = _sum_raw_counts(
        old_state["frozen_raw_counts"],
        _claude_raw_record_counts(
            _reslice_raw_session(tail_session, newly_frozen)
        ),
    )

    return {
        "schema": "chatlas.claude-delta-state.v2",
        "frozen_record_count": new_frozen_count,
        "frozen_line": frozen_line,
        "last_active_uuid": last_active_uuid,
        "interaction_count": interaction_count,
        "current_turn_id": current_turn_id,
        "last_context_snapshot": last_context_snapshot,
        "sequence_base": len(frozen_events),
        "chain_seed": event_chain_hash(frozen_events[-1]),
        "message_index_base": new_message_index_base,
        "usage_index_base": new_usage_index_base,
        "tool_invocation_index_base": frozen_invocation_count,
        "model_run_index_base": frozen_run_count,
        "span_end_base": span_end_base,
        "frozen_pass_warnings": frozen_pass_warnings,
        "frozen_raw_counts": frozen_raw_counts,
    }


def claude_delta_normalization_result(
    row: dict[str, Any],
    *,
    chatlas_root: Path,
    artifact_dir: Path,
    trust: str = TRUST_VERIFY,
) -> NormalizationResult | None:
    """Attempt a delta derivation for a claude-code session. None means the
    caller must run a full derivation."""
    if trust == TRUST_REBUILD:
        return None
    provider = string_or_none(row.get("provider"))
    session_id = string_or_none(row.get("session_id"))
    if provider != "claude-code" or session_id is None:
        return None

    checkpoint = load_delta_checkpoint(
        chatlas_root, provider=provider, session_id=session_id
    )
    if checkpoint is None:
        return None
    state = checkpoint["state"]
    source_path = Path(str(checkpoint["source_path"]))
    if not source_path.is_file():
        return None

    pieces = _read_frozen_artifact_pieces(artifact_dir, state=state)
    if pieces is None:
        return None
    frozen_events = pieces["events"]

    frozen_line = int(state["frozen_line"])
    frozen_record_count = int(state["frozen_record_count"])
    offset = _scan_line_end_offset(source_path, frozen_line)
    if offset is None:
        return None

    source_ref_id = None
    for event in frozen_events:
        for ref in event.get("source_refs") or []:
            if isinstance(ref, dict) and ref.get("source_ref_id"):
                source_ref_id = str(ref["source_ref_id"])
                break
        if source_ref_id:
            break

    if trust == TRUST_VERIFY and not _verify_frozen_prefix(
        source_path,
        frozen_events=frozen_events,
        frozen_record_count=frozen_record_count,
        source_ref_id=source_ref_id,
    ):
        return None

    tail_session = _load_claude_raw_session_records(
        source_path,
        source_ref_id=source_ref_id,
        start_byte=offset,
        start_line=frozen_line + 1,
        record_index_base=frozen_record_count,
    )
    if not tail_session.records:
        return None
    if not _tail_extends_linearly(
        tail_session.records,
        last_active_uuid=string_or_none(state.get("last_active_uuid")),
    ):
        return None



    if _claude_tail_has_conversation_fork(tail_session.records):
        return None


    if _claude_tail_has_compaction(tail_session.records):
        return None

    resume = _ClaudeDeltaResume(
        sequence_base=int(state["sequence_base"]),
        interaction_count=int(state["interaction_count"]),
        current_turn_id=string_or_none(state.get("current_turn_id")),
        last_context_snapshot=state.get("last_context_snapshot")
        if isinstance(state.get("last_context_snapshot"), dict)
        else None,
        message_index_base=int(state["message_index_base"]),
        model_run_index_base=int(state["model_run_index_base"]),
        tool_invocation_index_base=int(state["tool_invocation_index_base"]),
        usage_index_base=int(state["usage_index_base"]),
        span_end_base=int(state["span_end_base"]),
    )
    tail_passes = _claude_normalization_passes(tail_session, resume)
    if frozen_events and tail_passes.events and "lineage" not in tail_passes.events[0]:



        tail_passes.events[0]["lineage"] = {
            "origin_ref": event_ref(frozen_events[-1]),
        }

    new_boundary = _claude_closed_estimate_boundary(
        tail_session,
        tool_invocations=tail_passes.tool_invocations,
        model_runs=tail_passes.model_runs,
    )
    attach_tape_provenance(
        tail_passes.events,
        record_hashes={
            record.record_index: record_payload_hash(record.payload)
            for record in tail_session.records
        },
        closed_estimate_boundary=new_boundary,
        chain_seed=str(state.get("chain_seed") or ""),
    )

    events = frozen_events + tail_passes.events
    messages = pieces["messages"] + tail_passes.messages
    model_runs = pieces["model_runs"] + tail_passes.model_runs
    tool_invocations = pieces["tool_invocations"] + tail_passes.tool_invocations
    usage = pieces["usage"] + tail_passes.usage

    raw_counts = _sum_raw_counts(state["frozen_raw_counts"], tail_passes.raw_counts)


    frozen_pass_warnings = state.get("frozen_pass_warnings")
    if not isinstance(frozen_pass_warnings, dict):
        frozen_pass_warnings = {}
    merged_pass_warnings = {
        key: [
            *[str(item) for item in (frozen_pass_warnings.get(key) or [])],
            *tail_list,
        ]
        for key, tail_list in tail_passes.pass_warnings.items()
    }
    warnings = _claude_normalization_warnings(
        raw_counts=raw_counts,
        pass_warnings=merged_pass_warnings,
        model_runs=model_runs,
        usage=usage,
    )



    from tarav.chatlas.normalization.session_model._claude import (
        _claude_messages_from_events,
        _claude_usage_from_events,
    )

    final_tail_events = [
        event for event in tail_passes.events if event_closed_estimate(event)
    ]
    messages_tail_final_count = len(
        _claude_messages_from_events(final_tail_events)["messages"]
    )
    usage_tail_final_count = len(
        _claude_usage_from_events(final_tail_events)["usage"]
    )

    delta_state = _delta_state_after_splice(
        old_state=state,
        tail_session=tail_session,
        tail_passes=tail_passes,
        merged_pass_warnings=merged_pass_warnings,
        events=events,
        tool_invocations=tool_invocations,
        model_runs=model_runs,
        messages_tail_final_count=messages_tail_final_count,
        usage_tail_final_count=usage_tail_final_count,
        new_boundary=new_boundary,
    )

    return NormalizationResult(
        messages=messages,
        model_runs=model_runs,
        tool_invocations=tool_invocations,
        events=events,
        usage=usage,
        normalizer="claude-code.raw_session.experimental.v2",
        source_mode="claude_code_raw_session",
        warnings=warnings,
        unsupported_concepts=_claude_unsupported_concepts(
            raw_counts=raw_counts,
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
        ),
        metadata={
            **_claude_normalization_metadata(
                raw_counts=raw_counts,
                messages=messages,
                model_runs=model_runs,
                tool_invocations=tool_invocations,
                events=events,
                usage=usage,
                deferred_concepts=[],
            ),


            "derivation": "delta",
            "delta_state": delta_state,
        },
    )


__all__ = [
    "DELTA_CHECKPOINT_SCHEMA",
    "TRUST_APPEND",
    "TRUST_REBUILD",
    "TRUST_TIERS",
    "TRUST_VERIFY",
    "claude_delta_normalization_result",
    "current_trust_tier",
    "set_trust_tier",
    "delta_checkpoint_path",
    "discard_delta_checkpoint",
    "load_delta_checkpoint",
    "save_delta_checkpoint",
]
