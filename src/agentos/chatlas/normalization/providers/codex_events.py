# $kw: ^codex-event-placement --from Normalization.Pipeline::Chatlas.Session.Model --from Session.Event.Tape --note [CT] the assembler assigns sequence as the tape's sole positional field ^c20260728-16u
"""Assembler-owned codex event loop (523 decomposition).

The `Normal.Assembler` (`assemble_codex_events`) owns rollout-record iteration, the
turn/interaction state, and the `SemanticEventBuilder` (sequencing / placement). The
per-record dispatch currently delegates to the existing `_codex_append_*` emitters; the
tool-invocation cross-refs are wired by the batch post-pass
`_codex_attach_tool_invocation_refs` (an in-place step over the whole tape).
"""

from __future__ import annotations

from agentos.chatlas._payload_helpers import (
    copy_present_fields,
    dict_list,
    int_or_none,
    string_or_none,
)
from agentos.chatlas.event_ref import event_ref

from ..session_model._codex import (
    _CodexRawRecord,
    _CodexRawRollout,
    _codex_append_event_msg_event,
    _codex_append_response_item_event,
    _codex_attach_tool_invocation_refs,
    _codex_attach_rollback_origins,
    _codex_call_ids_with_response_output,
    _codex_event_turn_id,
    _codex_record_semantic_type,
    _codex_record_turn_id,
    _codex_response_message_keys,
    _codex_turn_context_payload,
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
    set_event_native,
)


def _codex_event_place_key(event: dict[str, object]) -> tuple[object, ...]:
    """Codex-owned event place: rollout record plus structural fragment."""
    native = event_native(event)
    refs = event.get("source_refs")
    record_index = None
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict):
                record_index = int_or_none(ref.get("record_index"))
                if record_index is not None:
                    break
    return (
        record_index,
        event.get("kind"),
        string_or_none(native.get("message_id")),
        string_or_none(native.get("call_id")),
    )


def codex_compaction_normalizer(
    record: _CodexRawRecord, turn_id: str
) -> list[dict[str, object]]:
    """Normalize a Codex history replacement as a structural event."""
    retained_message_ids = [
        message_id
        for item in dict_list(record.payload.get("replacement_history"))
        if (message_id := string_or_none(item.get("id"))) is not None
    ]
    native = {
        "retained_message_ids": retained_message_ids,
        "replacement_history": record.payload.get("replacement_history"),
    }
    for key in (
        "window_number",
        "first_window_id",
        "previous_window_id",
        "window_id",
        "message",
    ):
        if key in record.payload:
            native[key] = record.payload[key]
    return [
        dict(
            kind="compaction",
            producer=semantic_event_producer("provider"),
            surfaces=semantic_event_surfaces(transcript="hidden"),
            turn_id=turn_id,
            payload={},
            timestamp=record.timestamp,
            source_refs=record.source_refs,
            native=native,
        )
    ]


def codex_session_meta_normalizer(
    record: _CodexRawRecord, turn_id: str
) -> list[dict[str, object]]:
    """`Raw.Normalizer` for codex session_meta records (session.start)."""
    payload: dict[str, object] = {"update_type": "session.start"}
    copy_present_fields(
        payload,
        record.payload,
        (
            ("id", "session_id"),
            ("originator", "originator"),
            ("source", "source"),
            ("cli_version", "cli_version"),
            ("cwd", "cwd"),
            ("model_provider", "model_provider"),
        ),
    )
    return [
        dict(
            kind="session.start",
            producer=semantic_event_producer("provider"),
            surfaces=semantic_event_surfaces(transcript="hidden"),
            turn_id=turn_id,
            payload=payload,
            timestamp=record.timestamp,
            source_refs=record.source_refs,
        )
    ]


def codex_turn_context_normalizer(
    record: _CodexRawRecord, turn_id: str, native_turn_id: str | None
) -> list[dict[str, object]]:
    """`Raw.Normalizer` for codex turn_context records."""
    return [
        dict(
            kind="context",
            producer=semantic_event_producer("provider"),
            surfaces=semantic_event_surfaces(
                transcript="hidden", model_input="visible"
            ),
            turn_id=turn_id,
            payload=_codex_turn_context_payload(record.payload),
            timestamp=record.timestamp,
            source_refs=record.source_refs,
            native={"turn_id": native_turn_id},
        )
    ]


def codex_response_item_normalizer(
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> list[dict[str, object]]:
    """In-place `Raw.Normalizer` for codex response_item records (message/reasoning/tool fan-out)."""
    local = SemanticEventBuilder()
    _codex_append_response_item_event(
        event_builder=local,
        record=record,
        turn_id=turn_id,
        native_turn_id=native_turn_id,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        warnings=warnings,
    )
    message_id = string_or_none(record.payload.get("id"))
    if string_or_none(record.payload.get("type")) == "message":
        for event in local.events:
            set_event_native(event, "message_id", message_id)
    return local.events


def _attach_codex_compaction_refs(events: list[dict[str, object]]) -> None:
    event_by_message_id: dict[str, dict[str, object]] = {}
    for event in events:
        native = event.get("native")
        if not isinstance(native, dict):
            continue
        message_id = string_or_none(native.get("message_id"))
        if message_id is not None:
            event_by_message_id.setdefault(message_id, event)

    for event in events:
        if event.get("kind") != "compaction":
            continue
        native = event.get("native")
        native = native if isinstance(native, dict) else {}
        retained_ids = native.get("retained_message_ids")
        retained_ids = retained_ids if isinstance(retained_ids, list) else []
        refs = [
            event_ref(event_by_message_id[message_id])
            for message_id in retained_ids
            if isinstance(message_id, str) and message_id in event_by_message_id
        ]
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if refs:
            payload["retained_event_refs"] = refs
        event["payload"] = payload
        event["event_hash"] = compute_event_hash(event)


def codex_event_msg_normalizer(
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
    response_message_keys,
    call_ids_with_response_output,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> list[dict[str, object]]:
    """In-place `Raw.Normalizer` for codex event_msg records."""
    local = SemanticEventBuilder()
    _codex_append_event_msg_event(
        event_builder=local,
        record=record,
        turn_id=turn_id,
        native_turn_id=native_turn_id,
        response_message_keys=response_message_keys,
        call_ids_with_response_output=call_ids_with_response_output,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        warnings=warnings,
    )
    return local.events


def _place(event_builder: SemanticEventBuilder, specs: list[dict[str, object]]) -> None:
    for spec in specs:
        event_builder.append(**spec)


def _place_events(
    event_builder: SemanticEventBuilder, events: list[dict[str, object]]
) -> None:
    """Place pre-built events on the tape, assigning their global sequence."""
    for event in events:
        sequence = len(event_builder.events) + 1
        event["sequence"] = sequence
        event_builder.events.append(event)


def assemble_codex_events(
    rollout: _CodexRawRollout,
    *,
    tool_invocation_refs_by_call_id: dict[str, str],
) -> dict[str, object]:
    event_builder = SemanticEventBuilder()
    warnings: list[str] = []
    current_turn_id: str | None = None
    current_native_turn_id: str | None = None
    response_message_keys = _codex_response_message_keys(rollout)
    call_ids_with_response_output = _codex_call_ids_with_response_output(rollout)
    for record in rollout.records:
        semantic_type = _codex_record_semantic_type(record)
        explicit_turn_id = _codex_record_turn_id(record)
        turn_id = _codex_event_turn_id(
            record=record,
            payload_type=semantic_type,
            native_turn_id=explicit_turn_id,
            current_turn_id=current_turn_id,
        )
        if turn_id != "session":
            current_turn_id = turn_id
            if explicit_turn_id is not None:
                current_native_turn_id = explicit_turn_id
        event_native_turn_id = explicit_turn_id or (
            current_native_turn_id if turn_id != "session" else None
        )

        if record.record_type == "session_meta":
            _place(event_builder, codex_session_meta_normalizer(record, turn_id))
            continue

        if record.record_type == "turn_context":
            _place(
                event_builder,
                codex_turn_context_normalizer(record, turn_id, event_native_turn_id),
            )
            continue

        if record.record_type == "compacted":
            _place(event_builder, codex_compaction_normalizer(record, turn_id))
            continue

        if record.record_type == "response_item":
            _place_events(
                event_builder,
                codex_response_item_normalizer(
                    record,
                    turn_id,
                    event_native_turn_id,
                    tool_invocation_refs_by_call_id,
                    warnings,
                ),
            )
            continue

        if record.record_type == "event_msg":
            _place_events(
                event_builder,
                codex_event_msg_normalizer(
                    record,
                    turn_id,
                    event_native_turn_id,
                    response_message_keys,
                    call_ids_with_response_output,
                    tool_invocation_refs_by_call_id,
                    warnings,
                ),
            )

    assign_event_addresses(
        event_builder.events,
        provider="codex",
        scope=rollout.source_ref_id or rollout.path.name,
        place_key=_codex_event_place_key,
    )
    _attach_codex_compaction_refs(event_builder.events)
    _codex_attach_tool_invocation_refs(
        event_builder.events,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        warnings=warnings,
    )
    _codex_attach_rollback_origins(event_builder.events)
    finalize_normal_turn_annotations(event_builder.events)
    enforce_event_envelope(event_builder.events, provider_label="codex")

    return {"events": event_builder.events, "warnings": warnings}
