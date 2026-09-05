"""Typed records and pure calculations for Tarav Assertion Scoring."""

from __future__ import annotations

import hashlib
import json
import random
import shlex
import string
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence
from uuid import UUID, uuid4


JsonObject = dict[str, Any]

POOL_TYPE = "Assertion.Pool"
ASSERTION_TYPE_SELECTOR = "Assertion.Type.Selector"
GROUNDING_TASK_TYPE = "Index.Line.Grounding.Ranking.Task"
RUN_TYPE = "Ranking.Run"
RESULT_TYPE = "Ranking.Result"
SCORE_DEFINITION_TYPE = "Score.Definition"
SCORE_COMPUTATION_TYPE = "Score.Computation"
GROUNDING_ASSERTION_TYPE = "Index.Line.Grounding.Assertion"
GROUNDING_ASSERTION_REFERENCE_TYPE = f"{GROUNDING_ASSERTION_TYPE}.Reference"
DIAGRAM_LINE_EDITION_REFERENCE_TYPE = "Diagram.Line.Edition.Reference"
WIN_RATE_SCORE = "Assertion.Ranking.WinRate.Score.v1"

RECORD_KINDS = {
    POOL_TYPE: "pools",
    GROUNDING_TASK_TYPE: "tasks",
    RUN_TYPE: "runs",
    RESULT_TYPE: "results",
    SCORE_DEFINITION_TYPE: "score-definitions",
    SCORE_COMPUTATION_TYPE: "scores",
}
RECORD_REFERENCE_TARGETS = {
    f"{record_type}.Reference": record_type for record_type in RECORD_KINDS
}


class ScoringError(ValueError):
    """A malformed scoring record or invalid scoring operation."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid4())


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def new_record(record_type: str, **fields: object) -> JsonObject:
    record: JsonObject = {
        "type": record_type,
        "schema_version": 1,
        "id": new_id(),
        "created_at": now_iso(),
    }
    record.update(fields)
    validate_record(record)
    return record


def record_reference(record: Mapping[str, object]) -> JsonObject:
    """Return the typed direct reference for one retained scoring Record."""

    validate_record(record)
    return {
        "type": f"{record['type']}.Reference",
        "id": record["id"],
        "record_sha256": content_hash(record),
    }


def reference_target_type(reference: Mapping[str, object]) -> str | None:
    return RECORD_REFERENCE_TARGETS.get(_required_string(reference, "type"))


def create_pool(
    name: str,
    assertion_type: str = GROUNDING_ASSERTION_TYPE,
) -> JsonObject:
    """Create a named cohort whose only responsibility is Assertion selection."""

    return new_record(
        POOL_TYPE,
        name=_nonempty(name, "name"),
        selector={
            "type": ASSERTION_TYPE_SELECTOR,
            "assertion_type": _nonempty(assertion_type, "assertion_type"),
        },
    )


def pool_matches(
    pool: Mapping[str, object], assertion_ref: Mapping[str, object]
) -> bool:
    validate_record(pool)
    if pool["type"] != POOL_TYPE:
        raise ScoringError("Assertion selection requires an Assertion.Pool")
    selector = _required_object(pool, "selector")
    selector_type = _required_string(selector, "type")
    if selector_type != ASSERTION_TYPE_SELECTOR:
        raise ScoringError(f"unsupported Assertion Pool selector: {selector_type}")
    assertion_type = _required_string(selector, "assertion_type")
    return assertion_ref.get("type") == f"{assertion_type}.Reference"


def candidate_labels(candidate_ids: Sequence[str], *, seed: str) -> dict[str, str]:
    if len(candidate_ids) > len(string.ascii_uppercase):
        raise ScoringError(
            "the first Ranking implementation supports at most 26 candidates"
        )
    shuffled = list(candidate_ids)
    random.Random(seed).shuffle(shuffled)
    return {
        label: candidate for label, candidate in zip(string.ascii_uppercase, shuffled)
    }


def render_task(task: Mapping[str, object], labels: Mapping[str, str]) -> str:
    validate_record(task)
    if task["type"] != GROUNDING_TASK_TYPE:
        raise ScoringError(f"no renderer for Ranking Task type {task['type']}")
    candidates = {
        _required_string(item, "id"): item
        for item in _required_dicts(task, "candidates")
    }
    if set(labels.values()) != set(candidates):
        raise ScoringError("Run labels must cover every Task candidate exactly once")
    sections = [
        "# Ranking Task",
        "",
        "## Background",
        "",
        _required_string(task, "background"),
        "",
        "## Question",
        "",
        _required_string(task, "question"),
    ]
    for label, candidate_id in labels.items():
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise ScoringError(
                f"Run label references unknown candidate: {candidate_id}"
            )
        sections.extend(
            (
                "",
                f"## Candidate {label}",
                "",
                _required_string(candidate, "presentation"),
            )
        )
        local_appendix = candidate.get("appendix", [])
        if local_appendix:
            sections.extend(("", "### Candidate appendix", ""))
            sections.extend(
                f"- {item}" for item in _strings(local_appendix, "appendix")
            )
    appendix = _strings(task.get("appendix", []), "appendix")
    if appendix:
        sections.extend(("", "## Shared appendix", ""))
        sections.extend(f"- {item}" for item in appendix)
    sections.extend(
        (
            "",
            "## Response",
            "",
            "Submit ordered tiers with the exact command below. Earlier tiers are "
            "better; put tied labels in one comma-separated tier. If the evidence "
            "is insufficient, abstain. Give a concise rationale.",
        )
    )
    return "\n".join(sections)


def create_run(
    *,
    task: Mapping[str, object],
    runner: Mapping[str, object],
    repository_root: str,
    seed: str | None = None,
    status: str = "Prepared",
) -> JsonObject:
    validate_record(task)
    run_id = new_id()
    effective_seed = seed or run_id
    candidate_ids = [
        _required_string(item, "id") for item in _required_dicts(task, "candidates")
    ]
    labels = candidate_labels(candidate_ids, seed=effective_seed)
    prompt = render_task(task, labels)
    command_root = shlex.quote(repository_root)
    example_tiers = " ".join(f"--tier {label}" for label in labels)
    prompt += (
        "\n\n"
        f"Ranked: tarav scoring submit {run_id} --root {command_root} "
        f"{example_tiers} --rationale 'brief reason'\n"
        f"Abstain: tarav scoring submit {run_id} --root {command_root} "
        "--abstain --reason 'why the evidence is insufficient'"
    )
    return new_record(
        RUN_TYPE,
        id=run_id,
        task_ref=record_reference(task),
        runner=dict(runner),
        seed=effective_seed,
        labels=labels,
        rendered_prompt=prompt,
        rendered_prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        status=status,
    )


def create_result(
    *,
    run: Mapping[str, object],
    tiers: Sequence[Sequence[str]] = (),
    rationale: str | None = None,
    abstain_reason: str | None = None,
) -> JsonObject:
    validate_record(run)
    if run["type"] != RUN_TYPE:
        raise ScoringError("Ranking Result requires a Ranking.Run")
    if run.get("status") not in {"Prepared", "Preview", "Running"}:
        raise ScoringError(
            f"Ranking Run no longer accepts a Result: {run.get('status')}"
        )
    labels = run.get("labels")
    if not isinstance(labels, dict):
        raise ScoringError("Ranking Run has no label map")
    if abstain_reason is not None:
        if tiers:
            raise ScoringError("an abstention cannot include ranking tiers")
        return new_record(
            RESULT_TYPE,
            run_ref=record_reference(run),
            outcome="abstained",
            tiers=[],
            rationale=rationale,
            abstain_reason=_nonempty(abstain_reason, "abstain_reason"),
        )
    if not tiers:
        raise ScoringError("a ranked Result requires at least one --tier")
    flattened = [label for tier in tiers for label in tier]
    expected = set(labels)
    if set(flattened) != expected or len(flattened) != len(expected):
        raise ScoringError(
            "ranking tiers must contain every presented label exactly once: "
            + ", ".join(sorted(expected))
        )
    return new_record(
        RESULT_TYPE,
        run_ref=record_reference(run),
        outcome="ranked",
        tiers=[list(tier) for tier in tiers],
        rationale=rationale,
        abstain_reason=None,
    )


def builtin_score_definition() -> JsonObject:
    return new_record(
        SCORE_DEFINITION_TYPE,
        name=WIN_RATE_SCORE,
        result_type=RESULT_TYPE,
        method="pairwise win rate; ties contribute one half; abstentions are excluded",
    )


def compute_win_rate_score(
    *,
    definition: Mapping[str, object],
    observations: Sequence[tuple[Mapping[str, object], Mapping[str, object]]],
) -> JsonObject:
    validate_record(definition)
    ranked: list[Mapping[str, object]] = []
    selected: list[Mapping[str, object]] = []
    stats: dict[str, dict[str, float | int]] = {}
    abstentions = 0
    for result, run in observations:
        validate_record(result)
        validate_record(run)
        if result["type"] != RESULT_TYPE:
            continue
        if run["type"] != RUN_TYPE:
            raise ScoringError("Ranking Result observation requires a Ranking.Run")
        if record_reference(run) != result.get("run_ref"):
            raise ScoringError(
                "Ranking Result does not reference the supplied Run edition"
            )
        selected.append(result)
        if result.get("outcome") == "abstained":
            abstentions += 1
            continue
        ranked.append(result)
        presented_tiers = _required_tiers(result)
        labels = _required_object(run, "labels")
        tiers = [
            [_required_string(labels, label) for label in tier]
            for tier in presented_tiers
        ]
        for tier_index, tier in enumerate(tiers):
            for candidate in tier:
                stats.setdefault(candidate, {"wins": 0, "losses": 0, "ties": 0})
                stats[candidate]["ties"] += len(tier) - 1
                stats[candidate]["wins"] += sum(
                    len(later) for later in tiers[tier_index + 1 :]
                )
                stats[candidate]["losses"] += sum(
                    len(earlier) for earlier in tiers[:tier_index]
                )
    standings: list[JsonObject] = []
    for candidate, values in stats.items():
        comparisons = int(values["wins"] + values["losses"] + values["ties"])
        score = (
            (float(values["wins"]) + 0.5 * float(values["ties"])) / comparisons
            if comparisons
            else None
        )
        standings.append(
            {
                "candidate_id": candidate,
                **values,
                "comparisons": comparisons,
                "value": score,
            }
        )
    standings.sort(
        key=lambda item: (
            item["value"] is not None,
            item["value"] if item["value"] is not None else -1,
            item["candidate_id"],
        ),
        reverse=True,
    )
    return new_record(
        SCORE_COMPUTATION_TYPE,
        definition_ref=record_reference(definition),
        result_refs=[record_reference(item) for item in selected],
        result_count=len(ranked),
        abstention_count=abstentions,
        standings=standings,
    )


def _validate_pool(record: Mapping[str, object]) -> None:
    _required_string(record, "name")
    selector = _required_object(record, "selector")
    if _required_string(selector, "type") != ASSERTION_TYPE_SELECTOR:
        raise ScoringError("unsupported Assertion Pool selector")
    _required_string(selector, "assertion_type")


def _validate_task(record: Mapping[str, object]) -> None:
    _validate_reference(record.get("pool_ref"), expected_target=POOL_TYPE)
    _required_string(record, "background")
    _required_string(record, "question")
    _strings(record.get("appendix", []), "appendix")
    candidates = _required_dicts(record, "candidates")
    if len(candidates) < 2:
        raise ScoringError("a Ranking Task requires at least two candidates")
    for candidate in candidates:
        _required_string(candidate, "id")
        _required_string(candidate, "presentation")
        _validate_assertion_reference(candidate.get("assertion_ref"))
        _strings(candidate.get("appendix", []), "candidate.appendix")
    candidate_ids = [_required_string(item, "id") for item in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ScoringError("Ranking Task candidate IDs must be unique")


def _validate_run(record: Mapping[str, object]) -> None:
    _validate_reference(record.get("task_ref"), expected_target=GROUNDING_TASK_TYPE)
    runner = _required_object(record, "runner")
    _required_string(runner, "type")
    labels = record.get("labels")
    if not isinstance(labels, dict) or len(labels) < 2:
        raise ScoringError("labels must map at least two opaque labels")
    for label, candidate in labels.items():
        _nonempty(label, "labels key")
        _nonempty(candidate, "labels value")
    if len(set(labels.values())) != len(labels):
        raise ScoringError("Run labels must reference distinct candidates")
    prompt = _required_string(record, "rendered_prompt")
    expected_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if _required_string(record, "rendered_prompt_sha256") != expected_hash:
        raise ScoringError("rendered_prompt_sha256 does not match rendered_prompt")
    _required_string(record, "status")


def _validate_result(record: Mapping[str, object]) -> None:
    _validate_reference(record.get("run_ref"), expected_target=RUN_TYPE)
    outcome = _required_string(record, "outcome")
    if outcome not in {"ranked", "abstained"}:
        raise ScoringError("Ranking Result outcome must be ranked or abstained")
    tiers = _required_tiers(record)
    if outcome == "ranked" and not tiers:
        raise ScoringError("a ranked Result requires tiers")
    if outcome == "abstained" and tiers:
        raise ScoringError("an abstained Result cannot contain tiers")


def _validate_score_definition(record: Mapping[str, object]) -> None:
    _required_string(record, "name")
    _required_string(record, "result_type")
    _required_string(record, "method")


def _validate_score(record: Mapping[str, object]) -> None:
    _validate_reference(
        record.get("definition_ref"), expected_target=SCORE_DEFINITION_TYPE
    )
    result_refs = record.get("result_refs")
    if not isinstance(result_refs, list):
        raise ScoringError("result_refs must be a list")
    for reference in result_refs:
        _validate_reference(reference, expected_target=RESULT_TYPE)
    standings = record.get("standings")
    if not isinstance(standings, list):
        raise ScoringError("standings must be a list")


def validate_record(record: Mapping[str, object]) -> None:
    record_type = _required_string(record, "type")
    if record_type not in RECORD_KINDS:
        raise ScoringError(f"unsupported scoring Record type: {record_type}")
    if record.get("schema_version") != 1:
        raise ScoringError("scoring Record schema_version must be 1")
    _uuid(_required_string(record, "id"), "id")
    _required_string(record, "created_at")
    validator = {
        POOL_TYPE: _validate_pool,
        GROUNDING_TASK_TYPE: _validate_task,
        RUN_TYPE: _validate_run,
        RESULT_TYPE: _validate_result,
        SCORE_DEFINITION_TYPE: _validate_score_definition,
        SCORE_COMPUTATION_TYPE: _validate_score,
    }[record_type]
    validator(record)


def _validate_assertion_reference(value: object) -> None:
    reference = _required_mapping(value, field="assertion_ref")
    reference_type = _required_string(reference, "type")
    if not reference_type.endswith(".Assertion.Reference"):
        raise ScoringError("assertion_ref must have an Assertion.Reference Type")
    subject_ref = _required_object(reference, "subject_ref")
    if _required_string(subject_ref, "type") != DIAGRAM_LINE_EDITION_REFERENCE_TYPE:
        raise ScoringError("unsupported grounding Assertion subject Reference")
    for field in ("namespace_id", "line_ship", "edition_id"):
        _uuid(_required_string(subject_ref, field), f"subject_ref.{field}")


def _validate_reference(value: object, *, expected_target: str) -> JsonObject:
    reference = _required_mapping(value, field=f"{expected_target}.Reference")
    reference_type = _required_string(reference, "type")
    target = RECORD_REFERENCE_TARGETS.get(reference_type)
    if target != expected_target:
        raise ScoringError(
            f"expected {expected_target}.Reference, found {reference_type}"
        )
    _uuid(_required_string(reference, "id"), "Reference.id")
    digest = _required_string(reference, "record_sha256")
    if len(digest) != 64 or any(
        character not in string.hexdigits for character in digest
    ):
        raise ScoringError("Reference.record_sha256 must be a SHA-256 hex digest")
    return dict(reference)


def _required_tiers(record: Mapping[str, object]) -> list[list[str]]:
    value = record.get("tiers")
    if not isinstance(value, list):
        raise ScoringError("tiers must be a list")
    tiers: list[list[str]] = []
    for tier in value:
        if not isinstance(tier, list) or not tier:
            raise ScoringError("each tier must be a non-empty list")
        tiers.append([_nonempty(item, "tier label") for item in tier])
    return tiers


def _required_dicts(
    record: Mapping[str, object], key: str
) -> list[Mapping[str, object]]:
    value = record.get(key)
    if not isinstance(value, list):
        raise ScoringError(f"{key} must be a list")
    if not all(isinstance(item, dict) for item in value):
        raise ScoringError(f"{key} must contain objects")
    return value


def _required_object(record: Mapping[str, object], key: str) -> JsonObject:
    return dict(_required_mapping(record.get(key), field=key))


def _required_mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ScoringError(f"{field} must be an object")
    return value


def _strings(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ScoringError(f"{field} must be a list of strings")
    return list(value)


def _required_string(record: Mapping[str, object], key: str) -> str:
    return _nonempty(record.get(key), key)


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoringError(f"{field} must be a non-empty string")
    return value


def _uuid(value: str, field: str) -> str:
    try:
        UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ScoringError(f"{field} must be a UUID: {value!r}") from exc
    return value


__all__ = [
    "ASSERTION_TYPE_SELECTOR",
    "DIAGRAM_LINE_EDITION_REFERENCE_TYPE",
    "GROUNDING_ASSERTION_REFERENCE_TYPE",
    "GROUNDING_ASSERTION_TYPE",
    "GROUNDING_TASK_TYPE",
    "POOL_TYPE",
    "RECORD_KINDS",
    "RECORD_REFERENCE_TARGETS",
    "RESULT_TYPE",
    "RUN_TYPE",
    "SCORE_COMPUTATION_TYPE",
    "SCORE_DEFINITION_TYPE",
    "ScoringError",
    "WIN_RATE_SCORE",
    "builtin_score_definition",
    "candidate_labels",
    "compute_win_rate_score",
    "content_hash",
    "create_pool",
    "create_result",
    "create_run",
    "new_record",
    "pool_matches",
    "record_reference",
    "reference_target_type",
    "render_task",
    "validate_record",
]
