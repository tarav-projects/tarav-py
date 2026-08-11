# $kw: ^claude-event-placement --from Normalization.Pipeline::Chatlas.Session.Model --from Session.Event.Tape --note [CT] the assembler assigns sequence as the tape's sole positional field ^c20260728-16u
"""Assembler-owned claude event loop + per-record-type `Raw.Normalizer`s (523).

The `Normal.Assembler` (`assemble_claude_events`) owns record iteration, `turn_id`
state, and the `SemanticEventBuilder` (sequencing / placement). The per-record dispatch
lives here; each branch is being turned into a `Raw.Normalizer` that *returns* position-free
event specs (the `SemanticEventBuilder.append` kwargs — a `Model.Fragment` of one+ events),
which the assembler places.

All five claude event branches are now `Raw.Normalizer`s: pure for session.update / system /
usage; in-place (`Raw + Model -> Fragment`) for progress and message (their tool sub-events
carry raw-keyed `tool_invocation` cross-refs). The message branch stays one cohesive
normalizer — a message record fans out to an *interleaved* sequence (text / reasoning /
tool-call / tool-result via a visible-block flush); it produces those via a local builder
and the assembler re-sequences them at placement (`_place_events`).
"""

from __future__ import annotations

from dataclasses import dataclass

from agentos.chatlas._payload_helpers import int_or_none, string_list, string_or_none
from agentos.chatlas.event_ref import event_ref

from ..session_model._claude import (
    _claude_attach_origin_lineage,
    _ClaudeRawRecord,
    _ClaudeRawSession,
    _claude_append_message_record_events,
    _claude_common_event_native,
    _claude_context_snapshot,
    _claude_message_role,
    _claude_progress_event_payload,
    _claude_record_call_id,
    _claude_record_has_usage_payload,
    _claude_record_kind,
    _claude_record_starts_interaction,
    claude_turn_id,
    _claude_session_update_payload,
    _claude_system_event_payload,
    _claude_usage_event_payload,
)
from ..session_model.events import (
    SemanticEventBuilder,
    assign_event_addresses,
    compute_event_hash,
    enforce_event_envelope,
    event_native,
    finalize_normal_turn_annotations,
    semantic_event_producer,
    semantic_event_surfaces,
)
from ..session_model.source_refs import source_ref_first_record_index


def _claude_event_place_key(event: dict[str, object]) -> tuple[object, ...]:
    """Claude-owned raw coordinate for one normal event place.

    Native UUID wins; record index is the explicit fallback for records without
    one. Fragment discriminators describe provider structure, never content.
    """
    native = event_native(event)
    raw_place = string_or_none(native.get("uuid")) or source_ref_first_record_index(
        event.get("source_refs")
    )
    return (
        raw_place,
        event.get("kind"),
        int_or_none(native.get("content_index")),
        int_or_none(native.get("request_index")),
        string_or_none(native.get("call_id")),
    )


def _claude_compaction_payload(record: _ClaudeRawRecord) -> dict[str, object]:
    metadata = record.payload.get("compactMetadata")
    if not isinstance(metadata, dict):
        return {}
    payload: dict[str, object] = {}
    fields = (
        ("trigger", "trigger", string_or_none),
        ("preTokens", "pre_tokens", int_or_none),
        ("postTokens", "post_tokens", int_or_none),
        ("cumulativeDroppedTokens", "cumulative_dropped_tokens", int_or_none),
        ("durationMs", "duration_ms", int_or_none),
    )
    for source, target, normalize in fields:
        value = normalize(metadata.get(source))
        if value is not None:
            payload[target] = value
    return payload


def claude_compaction_normalizer(
    record: _ClaudeRawRecord, turn_id: str
) -> list[dict[str, object]]:
    """Normalize Claude's compact boundary as a structural event."""
    metadata = record.payload.get("compactMetadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    preserved = metadata.get("preservedMessages")
    preserved = preserved if isinstance(preserved, dict) else {}
    segment = metadata.get("preservedSegment")
    segment = segment if isinstance(segment, dict) else {}
    native = {
        **_claude_common_event_native(record),
        "logical_parent_uuid": string_or_none(record.payload.get("logicalParentUuid")),
        "summary_uuid": string_or_none(preserved.get("anchorUuid"))
        or string_or_none(segment.get("anchorUuid")),
        "retained_uuids": string_list(preserved.get("allUuids")),
        "compact_metadata": metadata,
    }
    return [
        dict(
            kind="compaction",
            producer=semantic_event_producer("provider"),
            surfaces=semantic_event_surfaces(transcript="hidden"),
            turn_id=turn_id,
            payload=_claude_compaction_payload(record),
            timestamp=record.timestamp,
            source_refs=record.source_refs,
            native=native,
        )
    ]


def claude_compaction_summary_normalizer(
    record: _ClaudeRawRecord,
) -> list[dict[str, object]]:
    """Normalize Claude's transport-user recap without granting human authority."""
    content = record.message.get("content")
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else []
    return [
        dict(
            kind="message",
            producer=semantic_event_producer("provider"),
            surfaces=semantic_event_surfaces(
                transcript="visible", model_input="hidden"
            ),
            payload={"role": "system", "content": blocks},
            timestamp=record.timestamp,
            source_refs=record.source_refs,
            native={
                **_claude_common_event_native(record),
                "transport_role": _claude_message_role(record),
                "is_compact_summary": True,
                "is_visible_in_transcript_only": record.payload.get(
                    "isVisibleInTranscriptOnly"
                )
                is True,
                "uuid": record.uuid,
            },
            annotations={"compaction_summary": True},
        )
    ]


def claude_session_update_normalizer(
    record: _ClaudeRawRecord, turn_id: str
) -> list[dict[str, object]]:
    """`Raw.Normalizer` for fallback session-update records."""
    return [
        dict(
            kind="session.update",
            producer=semantic_event_producer("provider"),
            surfaces=semantic_event_surfaces(transcript="hidden"),
            turn_id=turn_id,
            payload=_claude_session_update_payload(record),
            timestamp=record.timestamp,
            source_refs=record.source_refs,
            native=_claude_common_event_native(record),
        )
    ]


def claude_system_normalizer(
    record: _ClaudeRawRecord, turn_id: str
) -> list[dict[str, object]]:
    """`Raw.Normalizer` for system records (turn-duration metric vs session.update)."""
    subtype = string_or_none(record.payload.get("subtype"))
    if subtype == "compact_boundary":
        return claude_compaction_normalizer(record, turn_id)
    kind = "metric" if subtype == "turn_duration" else "session.update"
    return [
        dict(
            kind=kind,
            producer=semantic_event_producer("provider"),
            surfaces=semantic_event_surfaces(transcript="hidden"),
            turn_id=turn_id,
            payload=_claude_system_event_payload(record),
            timestamp=record.timestamp,
            source_refs=record.source_refs,
            native=_claude_common_event_native(record),
        )
    ]


def claude_usage_normalizer(
    record: _ClaudeRawRecord, turn_id: str
) -> list[dict[str, object]]:
    """`Raw.Normalizer` for the usage event accompanying a message record."""
    usage_payload = record.message.get("usage")
    if not isinstance(usage_payload, dict):
        return []
    return [
        dict(
            kind="usage",
            producer=semantic_event_producer("provider"),
            surfaces=semantic_event_surfaces(transcript="hidden"),
            turn_id=turn_id,
            payload=_claude_usage_event_payload(record, usage_payload=usage_payload),
            timestamp=record.timestamp,
            source_refs=record.source_refs,
            native=_claude_common_event_native(record),
        )
    ]


def claude_progress_normalizer(
    record: _ClaudeRawRecord,
    turn_id: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> list[dict[str, object]]:
    """In-place `Raw.Normalizer` for tool-progress records.

    Raw + Model -> Fragment: the event is built from raw, and its `tool_invocation_ref`
    is a raw-keyed cross-reference — `call_id` comes from raw, the target id from the
    model's `tool_invocations` (via the refs map the assembler passes in).
    """
    call_id = _claude_record_call_id(record)
    payload = _claude_progress_event_payload(record)
    if call_id is not None:
        payload["call_id"] = call_id
    spec: dict[str, object] = dict(
        kind="tool.progress",
        producer=semantic_event_producer(
            "system", name=string_or_none(record.data.get("hookName"))
        ),
        surfaces=semantic_event_surfaces(transcript="hidden"),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        native={**_claude_common_event_native(record), "call_id": call_id},
    )
    if call_id is not None:
        ref = tool_invocation_refs_by_call_id.get(call_id)
        if ref is not None:
            spec["tool_invocation_ref"] = ref
        else:
            warnings.append(
                "claude tool-related event "
                f"{record.record_index} has no matching tool invocation for tool_use id {call_id}"
            )
    return [spec]


def claude_message_normalizer(
    record: _ClaudeRawRecord,
    turn_id: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> list[dict[str, object]]:
    """In-place `Raw.Normalizer` for one user/assistant message record.

    A message record fans out to an ordered, *interleaved* run of events (message text,
    reasoning, tool-call, tool-result), the visible-block flush stitching them together —
    one cohesive concern. Tool sub-events carry raw-keyed `tool_invocation` cross-refs, so
    this is in-place. The intricate fan-out logic is reused via a local `SemanticEventBuilder`;
    the assembler re-sequences the produced events at placement.
    """
    local = SemanticEventBuilder()
    _claude_append_message_record_events(
        event_builder=local,
        record=record,
        turn_id=turn_id,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        warnings=warnings,
    )
    return local.events


def _place(event_builder: SemanticEventBuilder, specs: list[dict[str, object]]) -> None:
    for spec in specs:
        placed = dict(spec)
        annotations = placed.pop("annotations", None)
        event = event_builder.append(**placed)
        if isinstance(annotations, dict):
            event["annotations"] = annotations


def _place_events(
    event_builder: SemanticEventBuilder, events: list[dict[str, object]]
) -> None:
    """Place pre-built events on the tape, assigning their global sequence."""
    for event in events:
        sequence = event_builder.sequence_base + len(event_builder.events) + 1
        event["sequence"] = sequence
        event_builder.events.append(event)


def _dispatch_record(
    *,
    event_builder: SemanticEventBuilder,
    record: _ClaudeRawRecord,
    turn_id: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    if record.payload.get("isCompactSummary") is True:
        _place(event_builder, claude_compaction_summary_normalizer(record))
        return
    if record.record_type == "progress":
        _place(
            event_builder,
            claude_progress_normalizer(
                record, turn_id, tool_invocation_refs_by_call_id, warnings
            ),
        )
        return
    if record.record_type == "system":
        _place(event_builder, claude_system_normalizer(record, turn_id))
        return
    role = _claude_message_role(record)
    if role in {"user", "assistant"}:
        _place_events(
            event_builder,
            claude_message_normalizer(
                record, turn_id, tool_invocation_refs_by_call_id, warnings
            ),
        )
        if _claude_record_has_usage_payload(record):
            _place(event_builder, claude_usage_normalizer(record, turn_id))
        return
    _place(event_builder, claude_session_update_normalizer(record, turn_id))


def _source_record_index(event: dict[str, object]) -> int | None:
    refs = event.get("source_refs")
    if not isinstance(refs, list):
        return None
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        record_index = int_or_none(ref.get("record_index"))
        if record_index is not None:
            return record_index
    return None


def _attach_claude_compaction_refs(
    events: list[dict[str, object]], raw_session: _ClaudeRawSession
) -> None:
    record_by_index = {record.record_index: record for record in raw_session.records}
    event_by_uuid: dict[str, dict[str, object]] = {}
    for event in events:
        record = record_by_index.get(_source_record_index(event) or -1)
        if record is not None and record.uuid is not None:
            event_by_uuid.setdefault(record.uuid, event)

    for event in events:
        if event.get("kind") != "compaction":
            continue
        native = event.get("native")
        native = native if isinstance(native, dict) else {}
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        retained_refs = [
            event_ref(event_by_uuid[uuid])
            for uuid in string_list(native.get("retained_uuids"))
            if uuid in event_by_uuid
        ]
        if retained_refs:
            payload["retained_event_refs"] = retained_refs
        summary_uuid = string_or_none(native.get("summary_uuid"))
        if summary_uuid is not None and summary_uuid in event_by_uuid:
            payload["summary_ref"] = event_ref(event_by_uuid[summary_uuid])
        event["payload"] = payload
        event["event_hash"] = compute_event_hash(event)


def assemble_claude_events(
    raw_session: _ClaudeRawSession,
    *,
    tool_invocation_refs_by_call_id: dict[str, str] | None = None,
    resume: "ClaudeEventAssemblyResume | None" = None,
) -> dict[str, object]:
    event_builder = SemanticEventBuilder(
        sequence_base=resume.sequence_base if resume is not None else 0
    )
    warnings: list[str] = []
    current_turn_id = resume.current_turn_id if resume is not None else None
    interaction_count = resume.interaction_count if resume is not None else 0
    last_context_snapshot = resume.last_context_snapshot if resume is not None else None

    for record in raw_session.records:
        if _claude_record_kind(record) == "last-prompt":
            continue
        if _claude_record_starts_interaction(record):
            interaction_count += 1
            current_turn_id = claude_turn_id(record, ordinal=interaction_count)
        turn_id = current_turn_id or "session"
        snapshot = _claude_context_snapshot(record)
        if snapshot and snapshot != last_context_snapshot:
            event_builder.append(
                kind="context",
                producer=semantic_event_producer("provider"),
                surfaces=semantic_event_surfaces(transcript="hidden"),
                turn_id=turn_id,
                payload={"context_type": "session_environment", **snapshot},
                timestamp=record.timestamp,
                source_refs=record.source_refs,
                native=_claude_common_event_native(record),
            )
            last_context_snapshot = snapshot
        _dispatch_record(
            event_builder=event_builder,
            record=record,
            turn_id=turn_id,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id or {},
            warnings=warnings,
        )

    assign_event_addresses(
        event_builder.events,
        provider="claude-code",
        scope=raw_session.source_ref_id or raw_session.path.name,
        place_key=_claude_event_place_key,
    )
    _attach_claude_compaction_refs(event_builder.events, raw_session)
    _claude_attach_origin_lineage(event_builder.events, raw_session)
    finalize_normal_turn_annotations(event_builder.events)
    enforce_event_envelope(event_builder.events, provider_label="claude-code")

    return {"events": event_builder.events, "warnings": warnings}


@dataclass(frozen=True)
class ClaudeEventAssemblyResume:
    """Assembler state at the frozen/volatile boundary for a delta pass.

    Fork lineage is skipped under resume — the delta caller has already
    verified the tail extends the frozen prefix linearly and falls back to
    full derivation otherwise.
    """

    sequence_base: int
    interaction_count: int
    current_turn_id: str | None
    last_context_snapshot: dict[str, object] | None
