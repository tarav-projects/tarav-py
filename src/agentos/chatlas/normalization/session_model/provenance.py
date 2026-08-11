# $kw: --from Session.Event.Tape
"""Tape line provenance for `Session.Event.Tape`.

Each tape event carries derivation hashes. A provider may additionally publish
``closed.estimate`` as best-effort lifecycle metadata; it is never a promise
that later raw observations cannot amend the event.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agentos.chatlas.normalization.session_model.events import (
    event_extras,
    set_event_extra,
)
from agentos.chatlas.normalization.session_model.source_refs import (
    source_ref_record_indices,
)


_PROVENANCE_FIELDS = ("source_hash", "final", "chain_hash")


def event_closed_estimate(event: dict[str, object]) -> bool:
    closed = event.get("closed")
    return isinstance(closed, dict) and closed.get("estimate") is True


def event_chain_hash(event: dict[str, object]) -> object:
    return event_extras(event).get("chain_hash")


def event_stored_source_hash(event: dict[str, object]) -> object:
    return event_extras(event).get("source_hash")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def record_payload_hash(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def event_source_hash(
    event: dict[str, object],
    *,
    record_hashes: dict[int, str],
) -> str:
    indices = sorted(set(source_ref_record_indices(event.get("source_refs"))))
    joined = ":".join(record_hashes.get(index, "") for index in indices)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def event_max_record_index(event: dict[str, object]) -> int | None:
    indices = list(source_ref_record_indices(event.get("source_refs")))
    return max(indices) if indices else None


def strip_tape_provenance(event: dict[str, object]) -> dict[str, object]:
    stripped = {key: value for key, value in event.items() if key != "extras"}
    remaining = {
        key: value
        for key, value in event_extras(event).items()
        if key not in _PROVENANCE_FIELDS
    }
    if remaining:
        stripped["extras"] = remaining
    return stripped


def _chain_hash_body(event: dict[str, object]) -> dict[str, object]:
    """The event as the chain covers it: everything except the chain hash
    itself, which now lives inside `extras` alongside its siblings."""
    body = {key: value for key, value in event.items() if key != "extras"}
    extras = {
        key: value for key, value in event_extras(event).items() if key != "chain_hash"
    }
    if extras:
        body["extras"] = extras
    return body


def chain_event_hash(previous_chain_hash: str, event: dict[str, object]) -> str:
    body = _canonical_json(_chain_hash_body(event))
    return hashlib.sha256(
        (previous_chain_hash + "\n" + body).encode("utf-8")
    ).hexdigest()


def attach_tape_provenance(
    events: list[dict[str, object]],
    *,
    record_hashes: dict[int, str],
    closed_estimate_boundary: int,
    chain_seed: str = "",
) -> None:
    """Set derivation hashes and an explicitly fallible closure estimate.

    ``closed_estimate_boundary`` is a provider heuristic. The estimate is
    excluded from ``Event.Hash`` and consumers must not treat it as finality.
    """
    previous_chain = chain_seed
    for event in events:
        set_event_extra(
            event, "source_hash", event_source_hash(event, record_hashes=record_hashes)
        )
        max_index = event_max_record_index(event)
        if max_index is not None:
            event["closed"] = {
                "estimate": max_index < closed_estimate_boundary,
            }
        chain = chain_event_hash(previous_chain, event)
        set_event_extra(event, "chain_hash", chain)
        previous_chain = chain


__all__ = [
    "attach_tape_provenance",
    "event_chain_hash",
    "event_closed_estimate",
    "event_stored_source_hash",
    "chain_event_hash",
    "event_max_record_index",
    "event_source_hash",
    "record_payload_hash",
    "strip_tape_provenance",
]
