"""Read-only renderers for live scores and retained scoring traces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


CURRENT_SCORE_RENDERER = "Assertion.Score.Current.Renderer"
TRACE_HISTORY_RENDERER = "Assertion.Scoring.Trace.History.Renderer"
TRACE_EVOLUTION_RENDERER = "Assertion.Scoring.Trace.Evolution.Renderer"
RENDERERS = (
    CURRENT_SCORE_RENDERER,
    TRACE_HISTORY_RENDERER,
    TRACE_EVOLUTION_RENDERER,
)


def render_current_scores(scores: Sequence[Mapping[str, object]]) -> str:
    lines = [f"scores: {len(scores)}"]
    for score in scores:
        value = score.get("value")
        rendered = "unscored" if value is None else f"{float(value):.3f}"
        subject = score.get("assertion_ref", {})
        if isinstance(subject, dict):
            subject = subject.get("subject_ref", {})
        edition = subject.get("edition_id", "?") if isinstance(subject, dict) else "?"
        lines.append(
            f"{rendered}\t{edition}\t{score.get('comparisons', 0)} comparisons"
        )
    return "\n".join(lines)


def render_trace_history(
    trace: Mapping[str, object], events: Sequence[Mapping[str, object]]
) -> str:
    lines = [f"trace: {trace['id']}", f"events: {len(events)}"]
    for event in events:
        value = event.get("value")
        rendered = "unscored" if value is None else f"{float(value):.3f}"
        pools = ",".join(str(item)[:8] for item in event.get("pool_ids", []))
        lines.append(
            f"{event.get('computed_at')}\t{rendered}\t"
            f"{event.get('comparisons', 0)} comparisons\t{pools}"
        )
    return "\n".join(lines)


def render_trace_evolution(
    trace: Mapping[str, object], events: Sequence[Mapping[str, object]]
) -> str:
    lines = [f"trace: {trace['id']}", f"events: {len(events)}"]
    previous: float | None = None
    for event in events:
        value = event.get("value")
        if value is None:
            rendered = "unscored"
            delta = "n/a"
        else:
            numeric = float(value)
            rendered = f"{numeric:.3f}"
            delta = "first" if previous is None else f"{numeric - previous:+.3f}"
            previous = numeric
        provenance = event.get("code_provenance", {})
        commit = provenance.get("git_commit") if isinstance(provenance, dict) else None
        lines.append(
            f"{event.get('computed_at')}\t{rendered}\t{delta}\t"
            f"results {str(event.get('results_commit', ''))[:10]}\t"
            f"code {str(commit or 'unknown')[:10]}"
        )
    return "\n".join(lines)


__all__ = [
    "CURRENT_SCORE_RENDERER",
    "RENDERERS",
    "TRACE_EVOLUTION_RENDERER",
    "TRACE_HISTORY_RENDERER",
    "render_current_scores",
    "render_trace_evolution",
    "render_trace_history",
]
