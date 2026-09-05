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

POOL_TYPE = "Assertion.Ranking.Pool"
GROUNDING_TASK_TYPE = "Index.Line.Grounding.Ranking.Task"
RUN_TYPE = "Ranking.Run"
RESULT_TYPE = "Ranking.Result"
SCORE_DEFINITION_TYPE = "Score.Definition"
SCORE_COMPUTATION_TYPE = "Score.Computation"
GROUNDING_ASSERTION_TYPE = "Index.Line.Grounding.Assertion"
WIN_RATE_SCORE = "Assertion.Ranking.WinRate.Score.v1"

RECORD_KINDS = {
    POOL_TYPE: "pools",
    GROUNDING_TASK_TYPE: "tasks",
    RUN_TYPE: "runs",
    RESULT_TYPE: "results",
    SCORE_DEFINITION_TYPE: "score-definitions",
    SCORE_COMPUTATION_TYPE: "scores",
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


def create_pool(name: str, assertion_type: str = GROUNDING_ASSERTION_TYPE) -> JsonObject:
    return new_record(
        POOL_TYPE,
        name=_nonempty(name, "name"),
        assertion_type=_nonempty(assertion_type, "assertion_type"),
        task_types=[GROUNDING_TASK_TYPE],
    )


def create_grounding_task(
    *,
    pool: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
    appendix: Sequence[str] = (),
) -> JsonObject:
    validate_record(pool)
    if pool["type"] != POOL_TYPE:
        raise ScoringError("grounding Task requires an Assertion.Ranking.Pool")
    if pool["assertion_type"] != GROUNDING_ASSERTION_TYPE:
        raise ScoringError(
            "grounding Task requires a pool for Index.Line.Grounding.Assertion"
        )
    if GROUNDING_TASK_TYPE not in pool["task_types"]:
        raise ScoringError(
            "the Ranking Pool does not accept Index.Line.Grounding.Ranking.Task"
        )
    candidate_records = [dict(item) for item in candidates]
    if len(candidate_records) < 2:
        raise ScoringError("a Ranking Task requires at least two candidates")
    ids = [_required_string(item, "id") for item in candidate_records]
    if len(set(ids)) != len(ids):
        raise ScoringError("Ranking Task candidate IDs must be unique")
    return new_record(
        GROUNDING_TASK_TYPE,
        pool_id=pool["id"],
        assertion_type=pool["assertion_type"],
        background=(
            "Each candidate is an Index.Line together with the Block context in which "
            "it must be interpreted and its declared Support.Set."
        ),
        question=(
            "Rank the candidates by how completely their declared Support.Set supports "
            "the Line's full semantic claim in its Block context."
        ),
        appendix=list(appendix),
        candidates=candidate_records,
        response_contract={
            "outcomes": ["ranked", "abstained"],
            "ranking": "ordered tiers; comma-separated labels within one tier are tied",
        },
    )


def candidate_labels(candidate_ids: Sequence[str], *, seed: str) -> dict[str, str]:
    if len(candidate_ids) > len(string.ascii_uppercase):
        raise ScoringError("the first Ranking implementation supports at most 26 candidates")
    shuffled = list(candidate_ids)
    random.Random(seed).shuffle(shuffled)
    return {label: candidate for label, candidate in zip(string.ascii_uppercase, shuffled)}


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
            raise ScoringError(f"Run label references unknown candidate: {candidate_id}")
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
            sections.extend(f"- {item}" for item in _strings(local_appendix, "appendix"))
    appendix = _strings(task.get("appendix", []), "appendix")
    if appendix:
        sections.extend(("", "## Shared appendix", ""))
        sections.extend(f"- {item}" for item in appendix)
    sections.extend(
        (
            "",
            "## Response",
            "",
            "Submit ordered tiers with the exact command below. Earlier tiers are better; "
            "put tied labels in one comma-separated tier. If the evidence is insufficient, "
            "abstain. Give a concise rationale.",
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
        task_id=task["id"],
        pool_id=task["pool_id"],
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
            run_id=run["id"],
            task_id=run["task_id"],
            pool_id=run["pool_id"],
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
    candidate_tiers = [[labels[label] for label in tier] for tier in tiers]
    return new_record(
        RESULT_TYPE,
        run_id=run["id"],
        task_id=run["task_id"],
        pool_id=run["pool_id"],
        outcome="ranked",
        presented_tiers=[list(tier) for tier in tiers],
        tiers=candidate_tiers,
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
    pool: Mapping[str, object],
    definition: Mapping[str, object],
    results: Sequence[Mapping[str, object]],
) -> JsonObject:
    validate_record(pool)
    validate_record(definition)
    accepted: list[Mapping[str, object]] = []
    stats: dict[str, dict[str, float | int]] = {}
    abstentions = 0
    for result in results:
        validate_record(result)
        if result["type"] != RESULT_TYPE or result.get("pool_id") != pool["id"]:
            continue
        if result.get("outcome") == "abstained":
            abstentions += 1
            continue
        accepted.append(result)
        tiers = _required_tiers(result)
        for tier_index, tier in enumerate(tiers):
            for candidate in tier:
                stats.setdefault(candidate, {"wins": 0, "losses": 0, "ties": 0})
                stats[candidate]["ties"] += len(tier) - 1
                stats[candidate]["wins"] += sum(len(later) for later in tiers[tier_index + 1 :])
                stats[candidate]["losses"] += sum(len(earlier) for earlier in tiers[:tier_index])
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
        name=definition["name"],
        definition_id=definition["id"],
        pool_id=pool["id"],
        result_ids=[item["id"] for item in accepted],
        result_count=len(accepted),
        abstention_count=abstentions,
        standings=standings,
    )


def _validate_pool(record: Mapping[str, object]) -> None:
    _required_string(record, "name")
    _required_string(record, "assertion_type")
    _strings(record.get("task_types"), "task_types")


def _validate_task(record: Mapping[str, object]) -> None:
    _uuid(_required_string(record, "pool_id"), "pool_id")
    _required_string(record, "assertion_type")
    _required_string(record, "background")
    _required_string(record, "question")
    _strings(record.get("appendix", []), "appendix")
    candidates = _required_dicts(record, "candidates")
    if len(candidates) < 2:
        raise ScoringError("a Ranking Task requires at least two candidates")
    for candidate in candidates:
        _required_string(candidate, "id")
        _required_string(candidate, "presentation")
        assertion = candidate.get("assertion")
        if not isinstance(assertion, dict):
            raise ScoringError("candidate.assertion must be an object")
        _required_string(assertion, "type")
        _strings(candidate.get("appendix", []), "candidate.appendix")
    candidate_ids = [_required_string(item, "id") for item in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ScoringError("Ranking Task candidate IDs must be unique")


def _validate_run(record: Mapping[str, object]) -> None:
    for key in ("task_id", "pool_id"):
        _uuid(_required_string(record, key), key)
    runner = record.get("runner")
    if not isinstance(runner, dict):
        raise ScoringError("runner must be an object")
    _required_string(runner, "type")
    labels = record.get("labels")
    if not isinstance(labels, dict) or len(labels) < 2:
        raise ScoringError("labels must map at least two opaque labels")
    for label, candidate in labels.items():
        _nonempty(label, "labels key")
        _nonempty(candidate, "labels value")
    if len(set(labels.values())) != len(labels):
        raise ScoringError("Run labels must reference distinct candidates")
    _required_string(record, "rendered_prompt")
    _required_string(record, "rendered_prompt_sha256")
    _required_string(record, "status")


def _validate_result(record: Mapping[str, object]) -> None:
    for key in ("run_id", "task_id", "pool_id"):
        _uuid(_required_string(record, key), key)
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
    _required_string(record, "name")
    for key in ("definition_id", "pool_id"):
        _uuid(_required_string(record, key), key)
    _strings(record.get("result_ids", []), "result_ids")
    standings = record.get("standings")
    if not isinstance(standings, list):
        raise ScoringError("standings must be a list")


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


def _required_dicts(record: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = record.get(key)
    if not isinstance(value, list):
        raise ScoringError(f"{key} must be a list")
    if not all(isinstance(item, dict) for item in value):
        raise ScoringError(f"{key} must contain objects")
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
    "GROUNDING_ASSERTION_TYPE",
    "GROUNDING_TASK_TYPE",
    "POOL_TYPE",
    "RECORD_KINDS",
    "RESULT_TYPE",
    "RUN_TYPE",
    "SCORE_COMPUTATION_TYPE",
    "SCORE_DEFINITION_TYPE",
    "ScoringError",
    "WIN_RATE_SCORE",
    "builtin_score_definition",
    "compute_win_rate_score",
    "content_hash",
    "create_grounding_task",
    "create_pool",
    "create_result",
    "create_run",
    "new_record",
    "render_task",
    "validate_record",
]
