# $kw: --from Session.Event.Tape --from Provider.Instance
"""codex `tool_invocations` + `model_runs` `Raw.Normalizer`s.

Raw-touching (they read raw rollout records) -> `Raw.Normalizer`s, surfaced here so the
chatlas session pipeline's raw-normalizer set is explicit. Bodies live in the relocated
`session_model/_codex.py` (transitional); `model_runs` is in-place (`Raw + Model -> list`).
"""

from __future__ import annotations

from typing import Any

from ..session_model._codex import (
    _codex_model_runs_from_raw_rollout,
    _codex_tool_invocations_from_raw_rollout,
)


def codex_tool_invocations_normalizer(rollout: Any) -> dict[str, object]:
    """Pure `Raw.Normalizer`: raw rollout records -> tool_invocations."""
    return _codex_tool_invocations_from_raw_rollout(rollout)


def codex_model_runs_normalizer(
    rollout: Any,
    *,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
) -> dict[str, object]:
    """In-place `Raw.Normalizer`: raw + (messages, tool_invocations, events) -> model_runs."""
    return _codex_model_runs_from_raw_rollout(
        rollout,
        messages=messages,
        tool_invocations=tool_invocations,
        events=events,
    )
