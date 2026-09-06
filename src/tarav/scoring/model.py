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

POOL_ENROLLMENT_TYPE = "Assertion.Pool.Enrollment"
GROUNDING_TASK_TYPE = "Index.Line.Grounding.Ranking.Task"
GROUNDING_POOL_TYPE = "Index.Line.Grounding.Ranking.Pool"
GROUNDING_TASK_RENDERER = "Index.Line.Grounding.Ranking.Task.Renderer.v1"
RUN_TYPE = "Ranking.Run"
RESULT_TYPE = "Ranking.Result"
SCORING_TRACE_TYPE = "Assertion.Scoring.Trace"
SCORING_EVENT_TYPE = "Assertion.Scoring.Event"
LIVE_SCORE_CLASS = "Assertion.Score.Live"
GROUNDING_ASSERTION_TYPE = "Index.Line.Grounding.Assertion"
GROUNDING_ASSERTION_REFERENCE_TYPE = f"{GROUNDING_ASSERTION_TYPE}.Reference"
DIAGRAM_LINE_EDITION_REFERENCE_TYPE = "Diagram.Line.Edition.Reference"
WIN_RATE_SCORE = "Assertion.Ranking.WinRate.Score.v1"

RECORD_KINDS = {
    GROUNDING_POOL_TYPE: "pools",
    POOL_ENROLLMENT_TYPE: "enrollments",
    GROUNDING_TASK_TYPE: "tasks",
    RUN_TYPE: "runs",
    RESULT_TYPE: "results",
    SCORING_TRACE_TYPE: "assertion-traces",
    SCORING_EVENT_TYPE: "events",
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


def create_pool_enrollment(
    *, pool: Mapping[str, object], assertion_ref: Mapping[str, object]
) -> JsonObject:
    """Retain one explicit Assertion-instance enrollment in a Pool."""

    validate_record(pool)
    if not is_pool_record_type(str(pool["type"])):
        raise ScoringError("Assertion enrollment requires an Assertion.Pool")
    _validate_assertion_reference(assertion_ref)
    return new_record(
        POOL_ENROLLMENT_TYPE,
        pool_ref=record_reference(pool),
        assertion_ref=dict(assertion_ref),
        status="Enrolled",
    )


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


def render_run(
    *,
    task: Mapping[str, object],
    run: Mapping[str, object],
) -> str:
    """Reconstruct and verify the exact prompt for a frozen Ranking Run."""

    validate_record(task)
    validate_record(run)
    if run["type"] != RUN_TYPE:
        raise ScoringError("render_run requires a Ranking.Run")
    if run.get("task_ref") != record_reference(task):
        raise ScoringError("Ranking Run does not reference the supplied Task edition")
    renderer = _required_object(run, "renderer")
    if _required_string(renderer, "type") != GROUNDING_TASK_RENDERER:
        raise ScoringError(f"unsupported Ranking Run renderer: {renderer.get('type')}")
    labels = _required_object(run, "labels")
    prompt = render_task(task, labels)
    submission = _required_object(run, "submission")
    command_root = shlex.quote(_required_string(submission, "repository_root"))
    example_tiers = " ".join(f"--tier {label}" for label in labels)
    prompt += (
        "\n\n"
        f"Ranked: tarav scoring submit {run['id']} --root {command_root} "
        f"{example_tiers} --rationale 'brief reason'\n"
        f"Abstain: tarav scoring submit {run['id']} --root {command_root} "
        "--abstain --reason 'why the evidence is insufficient'"
    )
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if digest != run.get("rendered_prompt_sha256"):
        raise ScoringError("rendered Ranking prompt does not match its frozen hash")
    return prompt


def create_run(
    *,
    task: Mapping[str, object],
    runner: Mapping[str, object],
    repository_root: str,
    code_provenance: Mapping[str, object],
    seed: str | None = None,
) -> JsonObject:
    """Freeze one unresolved evaluation without duplicating its rendered prompt."""

    validate_record(task)
    run_id = new_id()
    effective_seed = seed or run_id
    candidate_ids = [
        _required_string(item, "id") for item in _required_dicts(task, "candidates")
    ]
    labels = candidate_labels(candidate_ids, seed=effective_seed)
    renderer = {
        "type": GROUNDING_TASK_RENDERER,
        "code_provenance": dict(code_provenance),
    }
    provisional = new_record(
        RUN_TYPE,
        id=run_id,
        task_ref=record_reference(task),
        runner=dict(runner),
        labels=labels,
        renderer=renderer,
        submission={"repository_root": repository_root},
        rendered_prompt_sha256="0" * 64,
        status="Awaiting.Result",
    )
    prompt = _render_unchecked_run_prompt(
        task=task,
        run=provisional,
    )
    return new_record(
        RUN_TYPE,
        id=run_id,
        created_at=provisional["created_at"],
        task_ref=record_reference(task),
        runner=dict(runner),
        labels=labels,
        renderer=renderer,
        submission={"repository_root": repository_root},
        rendered_prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        status="Awaiting.Result",
    )


def _render_unchecked_run_prompt(
    *,
    task: Mapping[str, object],
    run: Mapping[str, object],
) -> str:
    labels = _required_object(run, "labels")
    prompt = render_task(task, labels)
    submission = _required_object(run, "submission")
    command_root = shlex.quote(_required_string(submission, "repository_root"))
    example_tiers = " ".join(f"--tier {label}" for label in labels)
    return prompt + (
        "\n\n"
        f"Ranked: tarav scoring submit {run['id']} --root {command_root} "
        f"{example_tiers} --rationale 'brief reason'\n"
        f"Abstain: tarav scoring submit {run['id']} --root {command_root} "
        "--abstain --reason 'why the evidence is insufficient'"
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
    if run.get("status") != "Awaiting.Result":
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


def compute_win_rate_scores(
    *,
    observations: Sequence[
        tuple[
            Mapping[str, object],
            Mapping[str, object],
            Mapping[str, Mapping[str, object]],
        ]
    ],
) -> tuple[JsonObject, ...]:
    """Compute current scores without retaining derived scoring Records."""

    stats: dict[str, dict[str, float | int]] = {}
    assertion_refs: dict[str, Mapping[str, object]] = {}
    ranked_results: dict[str, int] = {}
    abstentions: dict[str, int] = {}
    for result, run, assertions_by_candidate in observations:
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
        candidate_ids = set(assertions_by_candidate)
        if set(_required_object(run, "labels").values()) != candidate_ids:
            raise ScoringError(
                "Ranking observation Assertions must cover every Run candidate"
            )
        for candidate_id, assertion_ref in assertions_by_candidate.items():
            _validate_assertion_reference(assertion_ref)
            previous = assertion_refs.setdefault(candidate_id, assertion_ref)
            if previous != assertion_ref:
                raise ScoringError(
                    f"candidate id is rebound to another Assertion: {candidate_id}"
                )
        if result.get("outcome") == "abstained":
            for candidate_id in candidate_ids:
                abstentions[candidate_id] = abstentions.get(candidate_id, 0) + 1
            continue
        for candidate_id in candidate_ids:
            ranked_results[candidate_id] = ranked_results.get(candidate_id, 0) + 1
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
    scores: list[JsonObject] = []
    for candidate in sorted(assertion_refs):
        values = stats.get(candidate, {"wins": 0, "losses": 0, "ties": 0})
        comparisons = int(values["wins"] + values["losses"] + values["ties"])
        score = (
            (float(values["wins"]) + 0.5 * float(values["ties"])) / comparisons
            if comparisons
            else None
        )
        scores.append(
            {
                "class": LIVE_SCORE_CLASS,
                "assertion_ref": dict(assertion_refs[candidate]),
                "method": WIN_RATE_SCORE,
                "result_count": ranked_results.get(candidate, 0),
                "abstention_count": abstentions.get(candidate, 0),
                "wins": values["wins"],
                "losses": values["losses"],
                "ties": values["ties"],
                "comparisons": comparisons,
                "value": score,
            }
        )
    return tuple(scores)


def create_scoring_trace(assertion_ref: Mapping[str, object]) -> JsonObject:
    """Create the stable retained scoring-history object for one Assertion."""

    _validate_assertion_reference(assertion_ref)
    return new_record(SCORING_TRACE_TYPE, assertion_ref=dict(assertion_ref))


def create_scoring_event(
    *,
    trace: Mapping[str, object],
    score: Mapping[str, object],
    pool_ids: Sequence[str],
    results_commit: str,
    code_provenance: Mapping[str, object],
) -> JsonObject:
    """Create one compact retained observation of an explicit score computation."""

    validate_record(trace)
    if trace["type"] != SCORING_TRACE_TYPE:
        raise ScoringError("Assertion scoring Event requires a scoring Trace")
    _validate_live_score(score)
    if score.get("assertion_ref") != trace.get("assertion_ref"):
        raise ScoringError("Score and Trace must identify the same Assertion")
    computed_at = now_iso()
    return new_record(
        SCORING_EVENT_TYPE,
        created_at=computed_at,
        computed_at=computed_at,
        trace_ref=record_reference(trace),
        method=_required_string(score, "method"),
        pool_ids=list(pool_ids),
        results_commit=_nonempty(results_commit, "results_commit"),
        code_provenance=dict(code_provenance),
        result_count=score["result_count"],
        abstention_count=score["abstention_count"],
        wins=score["wins"],
        losses=score["losses"],
        ties=score["ties"],
        comparisons=score["comparisons"],
        value=score["value"],
    )


def _validate_pool(record: Mapping[str, object]) -> None:
    _required_string(record, "name")
    if "pool_class" in record:
        raise ScoringError("Pool Record must not retain a pool_class discriminator")


def _validate_pool_reference(value: object) -> None:
    reference = _required_mapping(value, field="Assertion.Pool.Reference")
    reference_type = _required_string(reference, "type")
    target = RECORD_REFERENCE_TARGETS.get(reference_type)
    if target is None or not is_pool_record_type(target):
        raise ScoringError(
            f"expected a concrete Pool Reference, found {reference_type}"
        )
    _validate_reference(reference, expected_target=target)


def _validate_pool_enrollment(record: Mapping[str, object]) -> None:
    _validate_pool_reference(record.get("pool_ref"))
    _validate_assertion_reference(record.get("assertion_ref"))
    if _required_string(record, "status") != "Enrolled":
        raise ScoringError("unsupported Assertion Pool enrollment status")


def _validate_task(record: Mapping[str, object]) -> None:
    _validate_pool_reference(record.get("pool_ref"))
    _required_string(record, "background")
    _required_string(record, "question")
    _strings(record.get("appendix", []), "appendix")
    candidates = _required_dicts(record, "candidates")
    if len(candidates) < 2:
        raise ScoringError("a Ranking Task requires at least two candidates")
    for candidate in candidates:
        _required_string(candidate, "id")
        _required_string(candidate, "presentation")
        _validate_reference(
            candidate.get("enrollment_ref"), expected_target=POOL_ENROLLMENT_TYPE
        )
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
    renderer = _required_object(record, "renderer")
    _required_string(renderer, "type")
    _validate_code_provenance(_required_object(renderer, "code_provenance"))
    submission = _required_object(record, "submission")
    _required_string(submission, "repository_root")
    digest = _required_string(record, "rendered_prompt_sha256")
    if len(digest) != 64 or any(
        character not in string.hexdigits for character in digest
    ):
        raise ScoringError("rendered_prompt_sha256 must be a SHA-256 hex digest")
    if _required_string(record, "status") != "Awaiting.Result":
        raise ScoringError("Ranking Run status must remain Awaiting.Result")
    if "rendered_prompt" in record:
        raise ScoringError("Ranking Run must not duplicate its rendered prompt")


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


def _validate_scoring_trace(record: Mapping[str, object]) -> None:
    _validate_assertion_reference(record.get("assertion_ref"))


def _validate_scoring_event(record: Mapping[str, object]) -> None:
    _validate_reference(record.get("trace_ref"), expected_target=SCORING_TRACE_TYPE)
    _required_string(record, "computed_at")
    _required_string(record, "method")
    pool_ids = record.get("pool_ids")
    if not isinstance(pool_ids, list) or not pool_ids:
        raise ScoringError("pool_ids must be a non-empty list")
    for pool_id in pool_ids:
        _uuid(_nonempty(pool_id, "pool_ids[]"), "pool_ids[]")
    _git_hash(_required_string(record, "results_commit"), "results_commit")
    provenance = _required_object(record, "code_provenance")
    _validate_code_provenance(provenance)
    _validate_score_statistics(record)


def _validate_code_provenance(provenance: Mapping[str, object]) -> None:
    _required_string(provenance, "version")
    git_commit = provenance.get("git_commit")
    if git_commit is not None:
        _git_hash(
            _nonempty(git_commit, "code_provenance.git_commit"),
            "code_provenance.git_commit",
        )
    if not isinstance(provenance.get("dirty"), bool):
        raise ScoringError("code_provenance.dirty must be Boolean")


def _validate_live_score(score: Mapping[str, object]) -> None:
    if score.get("class") != LIVE_SCORE_CLASS:
        raise ScoringError(f"Score class must be {LIVE_SCORE_CLASS}")
    _validate_assertion_reference(score.get("assertion_ref"))
    _required_string(score, "method")
    _validate_score_statistics(score)


def _validate_score_statistics(record: Mapping[str, object]) -> None:
    for field in (
        "result_count",
        "abstention_count",
        "wins",
        "losses",
        "ties",
        "comparisons",
    ):
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ScoringError(f"{field} must be a nonnegative integer")
    value = record.get("value")
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise ScoringError("Score value must be numeric or null")


def validate_record(record: Mapping[str, object]) -> None:
    record_type = _required_string(record, "type")
    if record_type not in RECORD_KINDS:
        raise ScoringError(f"unsupported scoring Record type: {record_type}")
    if record.get("schema_version") != 1:
        raise ScoringError("scoring Record schema_version must be 1")
    _uuid(_required_string(record, "id"), "id")
    _required_string(record, "created_at")
    validators = {
        POOL_ENROLLMENT_TYPE: _validate_pool_enrollment,
        GROUNDING_TASK_TYPE: _validate_task,
        RUN_TYPE: _validate_run,
        RESULT_TYPE: _validate_result,
        SCORING_TRACE_TYPE: _validate_scoring_trace,
        SCORING_EVENT_TYPE: _validate_scoring_event,
    }
    validator = (
        _validate_pool if is_pool_record_type(record_type) else validators[record_type]
    )
    validator(record)


def is_pool_record_type(record_type: str) -> bool:
    return RECORD_KINDS.get(record_type) == "pools"


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


def _git_hash(value: str, field: str) -> str:
    if len(value) not in {40, 64} or any(
        character not in string.hexdigits for character in value
    ):
        raise ScoringError(f"{field} must be a Git commit hash")
    return value


__all__ = [
    "LIVE_SCORE_CLASS",
    "DIAGRAM_LINE_EDITION_REFERENCE_TYPE",
    "GROUNDING_ASSERTION_REFERENCE_TYPE",
    "GROUNDING_ASSERTION_TYPE",
    "GROUNDING_TASK_TYPE",
    "GROUNDING_POOL_TYPE",
    "GROUNDING_TASK_RENDERER",
    "POOL_ENROLLMENT_TYPE",
    "RECORD_KINDS",
    "RECORD_REFERENCE_TARGETS",
    "RESULT_TYPE",
    "RUN_TYPE",
    "SCORING_EVENT_TYPE",
    "SCORING_TRACE_TYPE",
    "ScoringError",
    "WIN_RATE_SCORE",
    "candidate_labels",
    "compute_win_rate_scores",
    "content_hash",
    "create_pool_enrollment",
    "create_result",
    "create_run",
    "create_scoring_event",
    "create_scoring_trace",
    "is_pool_record_type",
    "new_record",
    "record_reference",
    "reference_target_type",
    "render_run",
    "render_task",
    "validate_record",
]
