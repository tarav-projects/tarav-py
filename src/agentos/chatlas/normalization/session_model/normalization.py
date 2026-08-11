from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizationResult:
    messages: list[dict[str, object]]
    model_runs: list[dict[str, object]]
    tool_invocations: list[dict[str, object]]
    events: list[dict[str, object]]
    usage: list[dict[str, object]]
    normalizer: str
    source_mode: str
    warnings: list[str]
    unsupported_concepts: list[str]
    metadata: dict[str, object]


def unsupported_concepts(
    *,
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
) -> list[str]:
    unsupported: list[str] = []
    if not messages:
        unsupported.append("messages")
    if not model_runs:
        unsupported.append("model_runs")
    if not tool_invocations:
        unsupported.append("tool_invocations")
    if not events:
        unsupported.append("events")
    return unsupported


def normalization_metadata(
    *,
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
    deferred_concepts: list[str],
) -> dict[str, object]:
    return {
        "counts": normalized_counts(
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
        ),
        "raw_counts": {},
        "coverage": normalization_coverage(
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
        ),
        "deferred_concepts": deferred_concepts,
    }


def normalized_counts(
    *,
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "messages": len(messages),
        "model_runs": len(model_runs),
        "tool_invocations": len(tool_invocations),
        "events": len(events),
        "usage": len(usage),
        "reasoning_traces": model_run_reasoning_count(model_runs),
    }


def normalization_coverage(
    *,
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
) -> dict[str, object]:
    reasoning_count = model_run_reasoning_count(model_runs)
    return {
        "messages": {
            "status": coverage_status(len(messages)),
            "normalized_count": len(messages),
        },
        "model_runs": {
            "status": coverage_status(len(model_runs)),
            "normalized_count": len(model_runs),
        },
        "tool_invocations": {
            "status": coverage_status(len(tool_invocations)),
            "normalized_count": len(tool_invocations),
        },
        "events": {
            "status": coverage_status(len(events)),
            "normalized_count": len(events),
        },
        "reasoning": {
            "status": coverage_status(reasoning_count),
            "normalized_count": reasoning_count,
        },
        "usage": {
            "status": coverage_status(len(usage)),
            "normalized_count": len(usage),
        },
    }


def model_run_reasoning_count(model_runs: list[dict[str, object]]) -> int:
    count = 0
    for model_run in model_runs:
        reasoning_trace = model_run.get("reasoning_trace")
        if isinstance(reasoning_trace, list):
            count += len(reasoning_trace)
    return count


def coverage_status(count: int) -> str:
    return "normalized" if count else "missing"


def count_payload(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: count
        for key, count in value.items()
        if isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool)
    }


def sorted_count_dict(counts: dict[str, int]) -> dict[str, int]:
    return {key: counts[key] for key in sorted(counts)}
