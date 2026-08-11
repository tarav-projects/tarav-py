# $kw: --from Normalization.Pipeline::Chatlas.Session.Model
"""Rich `Normal.Assembler` for `Normalization.Pipeline::Chatlas.Session.Model`.

Produces the full `Chatlas.Session.Model` (`session`, `agent_instance`, `sources`,
the `chat` payload / `Session.Event.Tape`, and `normalization`) — the production
producer behind `build_chatlas_session_model_from_index_row`. The per-provider
normalization (`_normalize_provider_raw` -> `_normalize_*_session`) orchestrates the
composable `Raw.Normalizer`s: the per-record event normalizers (`providers/*_events`)
and the tool_invocations / model_runs normalizers (`providers/*_records`); the
event→record projections and ref-attach passes are this assembler's work.
"""

from __future__ import annotations

from typing import Any



from agentos.chatlas._payload_helpers import string_or_none
from agentos.chatlas.normalization.session_model._model import (
    _CHATLAS_SESSION_MODEL_SCHEMA_VERSION,
    _agent_instance_payload,
    _normalize_provider_raw,
    _session_hashes,
    _session_payload,
    _source_payloads,
    _standard_records_payload,
)
from agentos.chatlas.normalization.session_model.normalization import NormalizationResult


def _provider_normalization(row: dict[str, Any]) -> NormalizationResult:
    """Run the per-provider normalization — the orchestration over the composable
    `Raw.Normalizer`s (events, tool_invocations, model_runs) plus projections."""
    return _normalize_provider_raw(row)


def assemble_session_model(
    row: dict[str, Any],
    normalization_result: NormalizationResult | None = None,
) -> dict[str, object]:
    """Assemble the full `Chatlas.Session.Model` from one coarse provider fragment.

    Mirrors ``session_model._build_session_model``; this is the pipeline's
    `Normal.Assembler` for the rich target. ``events`` is the hashed `Session.Event.Tape`;
    ``messages``/``model_runs``/``tool_invocations``/``usage`` are the neutral records
    projected from it.
    """
    provider = string_or_none(row.get("provider"))
    sources = _source_payloads(row)
    result = (
        normalization_result
        if normalization_result is not None
        else _provider_normalization(row)
    )

    normalization: dict[str, object] = {
        "provider": provider,
        "normalizer": result.normalizer,
        "version": 1,
        "source_mode": result.source_mode,
        "warnings": result.warnings,
        "unsupported_concepts": result.unsupported_concepts,
    }



    normalization.update(
        {key: value for key, value in result.metadata.items() if key != "delta_state"}
    )
    normalization.setdefault("derivation", "full")

    events = result.events
    session_payload = _session_payload(row)
    session_payload.update(_session_hashes(row, events=events))

    return {
        "class": "agentos_chatlas.session_model",
        "schema_version": _CHATLAS_SESSION_MODEL_SCHEMA_VERSION,
        "session": session_payload,
        "agent_instance": _agent_instance_payload(row),
        "sources": sources,
        "chat": {
            "messages": _standard_records_payload(result.messages),
            "model_runs": _standard_records_payload(result.model_runs),
            "tool_invocations": _standard_records_payload(result.tool_invocations),
            "events": events,
            "usage": _standard_records_payload(result.usage),
        },
        "normalization": normalization,
    }


def assemble_session_chat(row: dict[str, Any]) -> dict[str, object]:
    """The `chat` payload + `content_hash` — a projection of the full assembled model."""
    model = assemble_session_model(row)
    return {"chat": model["chat"], "content_hash": model["session"]["content_hash"]}
