"""claude `tool_invocations` + `model_runs` `Raw.Normalizer`s.

By the raw boundary these are normalizers: they read raw session records to produce the
tool_invocations and model_runs lists. They are surfaced here alongside the event
normalizers so the chatlas session pipeline's raw-normalizer set is explicit and complete.

Their bodies live in the relocated `session_model/_claude.py` (transitional — the
`_normalize_claude_session` assembler calls them through these named entries). `model_runs`
is the in-place form (`Raw + Model -> list`): it also reads the assembled messages,
tool_invocations, and events.
"""

from __future__ import annotations

from typing import Any

from ..session_model._claude import (
    _claude_model_runs_from_raw_session,
    _claude_tool_invocations_from_raw_session,
)


def claude_tool_invocations_normalizer(
    raw_session: Any,
    *,
    index_base: int = 0,
) -> dict[str, object]:
    """Pure `Raw.Normalizer`: raw session records -> tool_invocations."""
    return _claude_tool_invocations_from_raw_session(raw_session, index_base=index_base)


def claude_model_runs_normalizer(
    raw_session: Any,
    *,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    index_base: int = 0,
    span_end_base: int = 0,
) -> dict[str, object]:
    """In-place `Raw.Normalizer`: raw + (messages, tool_invocations, events) -> model_runs."""
    return _claude_model_runs_from_raw_session(
        raw_session,
        messages=messages,
        tool_invocations=tool_invocations,
        events=events,
        index_base=index_base,
        span_end_base=span_end_base,
    )
