# $kw: ^event-ref-traceability --from Chatlas.Session.Model.Contract --from Chatlas.Session.Model.Tests --note [CT] stored Event.Ref assertions resolve at stable addresses and amendment becomes a finding ^c20260807-16u
from __future__ import annotations

from agentos.chatlas._payload_helpers import int_or_none, string_or_none
from agentos.chatlas.event_ref import EventRefOutcome, resolve_event_ref


def standard_model_traceability_errors(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    sources = payload.get("sources")
    chat = payload.get("chat")
    if not isinstance(sources, list):
        return ["sources must be a list"]
    if not isinstance(chat, dict):
        return ["chat must be an object"]

    source_ids = standard_model_source_ids(sources, errors=errors)
    events = chat.get("events")
    if not isinstance(events, list):
        errors.append("chat.events must be a list")
        events = []
    tape = [event for event in events if isinstance(event, dict)]

    for index, event in enumerate(events):
        path = f"chat.events[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{path} must be an object")
            continue
        validate_standard_model_source_refs(
            event.get("source_refs"),
            path=f"{path}.source_refs",
            source_ids=source_ids,
            required=True,
            errors=errors,
        )

    for section in ("messages", "model_runs", "tool_invocations", "usage"):
        records = chat.get(section)
        if not isinstance(records, list):
            errors.append(f"chat.{section} must be a list")
            continue
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                errors.append(f"chat.{section}[{index}] must be an object")
                continue
            validate_standard_model_projection_traceability(
                record,
                path=f"chat.{section}[{index}]",
                source_ids=source_ids,
                tape=tape,
                errors=errors,
            )
            if section == "model_runs":
                reasoning_trace = record.get("reasoning_trace")
                if isinstance(reasoning_trace, list):
                    for reasoning_index, reasoning in enumerate(reasoning_trace):
                        if not isinstance(reasoning, dict):
                            errors.append(
                                f"chat.model_runs[{index}].reasoning_trace"
                                f"[{reasoning_index}] must be an object"
                            )
                            continue
                        validate_standard_model_projection_traceability(
                            reasoning,
                            path=(
                                f"chat.model_runs[{index}].reasoning_trace"
                                f"[{reasoning_index}]"
                            ),
                            source_ids=source_ids,
                            tape=tape,
                            errors=errors,
                        )

    return errors


def standard_model_source_ids(
    sources: list[object],
    *,
    errors: list[str],
) -> set[str]:
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"sources[{index}] must be an object")
            continue
        source_id = string_or_none(source.get("source_ref_id"))
        if source_id is None:
            errors.append(f"sources[{index}].source_ref_id must be a non-empty string")
            continue
        if source_id in source_ids:
            errors.append(f"sources[{index}].source_ref_id is duplicated: {source_id}")
        source_ids.add(source_id)
    return source_ids


def validate_standard_model_projection_traceability(
    record: dict[str, object],
    *,
    path: str,
    source_ids: set[str],
    tape: list[dict[str, object]],
    errors: list[str],
) -> None:
    source_refs = record.get("source_refs")
    event_refs = record.get("event_refs")
    has_source_refs = isinstance(source_refs, list) and bool(source_refs)
    has_event_refs = isinstance(event_refs, list) and bool(event_refs)
    if not has_source_refs and not has_event_refs:
        errors.append(f"{path} must have source_refs or event_refs")
        return
    if source_refs is not None:
        validate_standard_model_source_refs(
            source_refs,
            path=f"{path}.source_refs",
            source_ids=source_ids,
            required=False,
            errors=errors,
        )
    if event_refs is not None:
        validate_standard_model_event_refs(
            event_refs,
            path=f"{path}.event_refs",
            tape=tape,
            errors=errors,
        )


def validate_standard_model_event_refs(
    event_refs: object,
    *,
    path: str,
    tape: list[dict[str, object]],
    errors: list[str],
) -> None:
    """Every stored reference is an `Event.Ref`, and its assertion is checked.

    The join is intra-document. An address must exist and its current content
    must satisfy the stored hash assertion; sequence changes are irrelevant.
    """
    if not isinstance(event_refs, list):
        errors.append(f"{path} must be a list")
        return
    for index, ref in enumerate(event_refs):
        ref_path = f"{path}[{index}]"
        if not isinstance(ref, dict):
            errors.append(f"{ref_path} must be an Event.Ref object")
            continue
        try:
            resolution = resolve_event_ref(tape, ref)
        except ValueError as error:
            errors.append(f"{ref_path} is not a well-formed Event.Ref: {error}")
            continue
        if resolution.outcome is EventRefOutcome.MISSING:
            errors.append(f"{ref_path} is missing: {resolution.finding}")
            continue
        if resolution.outcome is not EventRefOutcome.MATCHED:
            errors.append(
                f"{ref_path} is {resolution.outcome.value}: {resolution.finding}"
            )
        event = resolution.event
        if event is None:
            continue
        event_source_refs = event.get("source_refs")
        if not isinstance(event_source_refs, list) or not event_source_refs:
            errors.append(f"{ref_path} references an event without source_refs")


def validate_standard_model_source_refs(
    source_refs: object,
    *,
    path: str,
    source_ids: set[str],
    required: bool,
    errors: list[str],
) -> None:
    if not isinstance(source_refs, list):
        errors.append(f"{path} must be a list")
        return
    if required and not source_refs:
        errors.append(f"{path} must not be empty")
        return
    for index, source_ref in enumerate(source_refs):
        ref_path = f"{path}[{index}]"
        if not isinstance(source_ref, dict):
            errors.append(f"{ref_path} must be an object")
            continue
        source_ref_id = string_or_none(source_ref.get("source_ref_id"))
        if source_ref_id is None:
            errors.append(f"{ref_path}.source_ref_id must be a non-empty string")
        elif source_ref_id not in source_ids:
            errors.append(f"{ref_path}.source_ref_id is unknown: {source_ref_id}")
        locator_keys = [
            key
            for key in (
                "line",
                "record_index",
                "event_index",
                "content_index",
                "request_index",
            )
            if key in source_ref
        ]
        if not locator_keys:
            errors.append(f"{ref_path} must include at least one locator field")
        for key in locator_keys:
            value = source_ref.get(key)
            if int_or_none(value) is None or value < 1:
                errors.append(f"{ref_path}.{key} must be a positive integer")
