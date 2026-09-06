from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tarav._core.project import initialize_project_layout
from tarav.cli.cli import main
from tarav.diagram import (
    BLOCK_SHIP_TYPE,
    DESIGN_BLOCK_OBJECT_TYPE,
    DESIGN_LINE_PRINCIPLE_TYPE,
    LINE_SHIP_TYPE,
    CaptureManifest,
    ChatlasEvidence,
    DiagramConfiguration,
    DiagramNamespace,
    ShipDraft,
)
from tarav.scoring import (
    DIAGRAM_LINE_EDITION_REFERENCE_TYPE,
    GROUNDING_ASSERTION_REFERENCE_TYPE,
    GROUNDING_POOL_CLASS,
    GROUNDING_TASK_TYPE,
    POOL_ENROLLMENT_TYPE,
    POOL_TYPE,
    RESULT_TYPE,
    RUN_TYPE,
    LIVE_SCORE_CLASS,
    SCORING_EVENT_TYPE,
    SCORING_TRACE_TYPE,
    ScoringError,
    ScoringRepository,
    compute_win_rate_scores,
    create_grounding_task,
    create_pool,
    create_pool_enrollment,
    create_result,
    create_run,
    create_scoring_event,
    create_scoring_trace,
    record_reference,
    render_run,
    render_task,
)
from tarav.scoring.tasks import (
    IndexLineGroundingAssertionType,
    create_line_grounding_enrollments,
    create_line_grounding_task,
)
from tarav.scoring.runner import execute_run, prepare_agent_run, prepare_unknown_run


def _assertion_ref(candidate_id: str) -> dict[str, object]:
    return {
        "type": GROUNDING_ASSERTION_REFERENCE_TYPE,
        "subject_ref": {
            "type": DIAGRAM_LINE_EDITION_REFERENCE_TYPE,
            "namespace_id": str(uuid4()),
            "line_ship": str(uuid4()),
            "edition_id": candidate_id,
        },
    }


def _candidate(
    enrollment: dict[str, object], candidate_id: str, claim: str
) -> dict[str, object]:
    return {
        "id": candidate_id,
        "enrollment_ref": record_reference(enrollment),
        "presentation": f"Line claim:\n{claim}\n\nDeclared Support.Set:\nEvidence.",
        "appendix": [],
    }


def _code_provenance() -> dict[str, object]:
    return {"version": "test", "git_commit": "0" * 40, "dirty": False}


def _task():
    first, second = str(uuid4()), str(uuid4())
    pool = create_pool("line-grounding")
    enrollments = (
        create_pool_enrollment(pool=pool, assertion_ref=_assertion_ref(first)),
        create_pool_enrollment(pool=pool, assertion_ref=_assertion_ref(second)),
    )
    task = create_grounding_task(
        pool=pool,
        enrollments=enrollments,
        candidates=(
            _candidate(enrollments[0], first, "First claim."),
            _candidate(enrollments[1], second, "Second claim."),
        ),
    )
    return pool, enrollments, task, first, second


def test_repository_retains_typed_records_in_git_and_resolves_prefixes(
    tmp_path: Path,
) -> None:
    repository = ScoringRepository.initialize(tmp_path / "scoring")
    pool = repository.create(create_pool("grounding"))

    assert repository.resolve(pool["id"][:12]) == pool
    assert repository.path_for(pool).relative_to(repository.root) == Path(
        "pools", pool["id"], "pool.json"
    )
    assert {item.name for item in repository.path_for(pool).parent.iterdir()} >= {
        "pool.json",
        "enrollments",
        "tasks",
        "runs",
        "results",
    }
    assert repository.head()
    assert (
        int(
            __import__("subprocess")
            .run(
                ("git", "-C", str(repository.root), "rev-list", "--count", "HEAD"),
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout
        )
        == 2
    )

    rebound = {**pool, "type": RUN_TYPE}
    with pytest.raises(ScoringError):
        repository.save(rebound)


def test_pool_is_an_explicit_population_and_classes_split_ownership() -> None:
    pool = create_pool("line-grounding")
    first, second = str(uuid4()), str(uuid4())
    enrollments = (
        create_pool_enrollment(pool=pool, assertion_ref=_assertion_ref(first)),
        create_pool_enrollment(pool=pool, assertion_ref=_assertion_ref(second)),
    )

    assert pool["pool_class"] == GROUNDING_POOL_CLASS
    assert "selector" not in pool
    assert all(item["type"] == POOL_ENROLLMENT_TYPE for item in enrollments)
    assert GROUNDING_POOL_CLASS in IndexLineGroundingAssertionType.pool_classes

    incompatible = create_pool("other", "Other.Ranking.Pool")
    with pytest.raises(ScoringError, match="unknown Ranking Pool Class"):
        create_grounding_task(
            pool=incompatible,
            enrollments=enrollments,
            candidates=(
                _candidate(enrollments[0], first, "First claim."),
                _candidate(enrollments[1], second, "Second claim."),
            ),
        )


def test_assertions_enroll_in_many_named_pools_and_scores_cross_pools(
    tmp_path: Path,
) -> None:
    repository = ScoringRepository.initialize(tmp_path / "scoring")
    first, second = str(uuid4()), str(uuid4())
    pools = tuple(
        repository.create(create_pool(name))
        for name in ("diagram.line.grounding.global", "tarav.line.grounding")
    )
    results = []
    first_ref = _assertion_ref(first)
    second_ref = _assertion_ref(second)
    for index, pool in enumerate(pools):
        enrollments = tuple(
            repository.create(
                create_pool_enrollment(pool=pool, assertion_ref=assertion_ref)
            )
            for assertion_ref in (first_ref, second_ref)
        )
        task = repository.create(
            create_grounding_task(
                pool=pool,
                enrollments=enrollments,
                candidates=(
                    _candidate(enrollments[0], first, "First claim."),
                    _candidate(enrollments[1], second, "Second claim."),
                ),
            )
        )
        run = repository.create(
            create_run(
                task=task,
                runner={"type": "Unknown.Ranking.Runner"},
                repository_root=str(repository.root),
                code_provenance=_code_provenance(),
                seed=str(index),
            )
        )
        labels = {candidate: label for label, candidate in run["labels"].items()}
        results.append(
            repository.create(
                create_result(
                    run=run,
                    tiers=((labels[first],), (labels[second],)),
                    rationale="First is stronger.",
                )
            )
        )

    assert repository.resolve("diagram.line.grounding.global") == pools[0]
    assert len(repository.enrollments_for_pool(pools[0])) == 2
    assert len(repository.results_for_pools(pools)) == 2
    results_commit = repository.head()
    scores = compute_win_rate_scores(
        observations=repository.ranking_observations(results),
    )
    for score in scores:
        trace = repository.create(create_scoring_trace(score["assertion_ref"]))
        repository.append_event(
            create_scoring_event(
                trace=trace,
                score=score,
                pool_ids=[str(pool["id"]) for pool in pools],
                results_commit=results_commit,
                code_provenance={
                    "version": "test",
                    "git_commit": results_commit,
                    "dirty": False,
                },
            )
        )
    assert len(scores) == 2
    first_trace = repository.trace_reference(first_ref)
    traced_types = {record["type"] for record in first_trace["records"]}
    assert traced_types == {
        POOL_TYPE,
        POOL_ENROLLMENT_TYPE,
        GROUNDING_TASK_TYPE,
        RUN_TYPE,
        RESULT_TYPE,
        SCORING_TRACE_TYPE,
        SCORING_EVENT_TYPE,
    }
    assert (
        sum(item["type"] == POOL_ENROLLMENT_TYPE for item in first_trace["records"])
        == 4
    )


def test_task_rendering_uses_opaque_labels_and_run_reconstructs_exact_prompt() -> None:
    _, _, task, first, second = _task()
    rendered = render_task(task, {"A": second, "B": first})

    assert "## Candidate A" in rendered
    assert "Second claim." in rendered
    assert first not in rendered
    assert second not in rendered

    run = create_run(
        task=task,
        runner={"type": "Unknown.Ranking.Runner"},
        repository_root="/tmp/scoring records",
        code_provenance=_code_provenance(),
        seed="repeatable",
    )
    assert run["type"] == RUN_TYPE
    assert run["task_ref"] == {
        "type": f"{GROUNDING_TASK_TYPE}.Reference",
        "id": task["id"],
        "record_sha256": run["task_ref"]["record_sha256"],
    }
    assert len(run["task_ref"]["record_sha256"]) == 64
    assert "task_id" not in run
    assert "pool_id" not in run
    assert run["rendered_prompt_sha256"]
    assert "rendered_prompt" not in run
    assert "seed" not in run
    prompt = render_run(
        task=task,
        run=run,
    )
    assert "tarav scoring submit" in prompt
    assert "--root '/tmp/scoring records'" in prompt


def test_structured_results_map_labels_and_compute_live_scores() -> None:
    _, enrollments, task, first, second = _task()
    run_one = create_run(
        task=task,
        runner={"type": "Unknown.Ranking.Runner"},
        repository_root="/tmp/scoring",
        code_provenance=_code_provenance(),
        seed="one",
    )
    labels_one = {candidate: label for label, candidate in run_one["labels"].items()}
    result_one = create_result(
        run=run_one,
        tiers=((labels_one[first],), (labels_one[second],)),
        rationale="The first is grounded more completely.",
    )
    run_two = create_run(
        task=task,
        runner={"type": "Unknown.Ranking.Runner"},
        repository_root="/tmp/scoring",
        code_provenance=_code_provenance(),
        seed="two",
    )
    result_two = create_result(
        run=run_two,
        tiers=(tuple(run_two["labels"]),),
        rationale="Equivalent support.",
    )
    assertions = {
        first: enrollments[0]["assertion_ref"],
        second: enrollments[1]["assertion_ref"],
    }
    scores = compute_win_rate_scores(
        observations=(
            (result_one, run_one, assertions),
            (result_two, run_two, assertions),
        ),
    )

    assert result_one["type"] == RESULT_TYPE
    assert result_one["run_ref"]["id"] == run_one["id"]
    assert "run_id" not in result_one
    assert "task_id" not in result_one
    assert "pool_id" not in result_one
    assert result_one["tiers"] == [[labels_one[first]], [labels_one[second]]]
    assert "presented_tiers" not in result_one
    by_assertion = {
        item["assertion_ref"]["subject_ref"]["edition_id"]: item for item in scores
    }
    assert by_assertion[first]["class"] == LIVE_SCORE_CLASS
    assert by_assertion[first]["value"] == pytest.approx(0.75)
    assert by_assertion[second]["value"] == pytest.approx(0.25)
    assert "result_refs" not in by_assertion[first]

    with pytest.raises(ScoringError, match="every presented label"):
        create_result(run=run_one, tiers=((labels_one[first],),))
    with pytest.raises(ScoringError, match="must remain Awaiting.Result"):
        create_result(
            run={**run_one, "status": "Exited.Without.Result"},
            tiers=(tuple(run_one["labels"]),),
        )


def test_cli_submit_score_and_debug_surfaces(tmp_path: Path, capsys) -> None:
    root = tmp_path / "scoring"
    assert main(["scoring", "init", "--root", str(root)]) == 0
    repository = ScoringRepository(root).open()
    pool, enrollments, task, _, _ = _task()
    repository.create(pool)
    for enrollment in enrollments:
        repository.create(enrollment)
    repository.create(task)

    assert main(["scoring", "render", task["id"][:10], "--root", str(root)]) == 0
    assert "# Ranking Task" in capsys.readouterr().out
    run, prompt = prepare_unknown_run(
        repository=repository,
        task=task,
        seed="cli-test",
    )
    run_id = str(run["id"])
    assert "tarav scoring submit" in prompt
    assert main(["scoring", "render", run_id, "--root", str(root)]) == 0
    assert capsys.readouterr().out.rstrip() == prompt
    labels = list(run["labels"])
    assert (
        main(
            [
                "scoring",
                "submit",
                run_id,
                "--root",
                str(root),
                "--tier",
                labels[0],
                "--tier",
                labels[1],
                "--rationale",
                "First is stronger.",
            ]
        )
        == 0
    )
    capsys.readouterr()
    with pytest.raises(ScoringError, match="already has a Result"):
        repository.create(
            create_result(
                run=run,
                tiers=tuple((label,) for label in labels),
                rationale="Duplicate submission.",
            )
        )
    assert main(["scoring", "score", "--pool", pool["id"], "--root", str(root)]) == 0
    assert "scores: 2" in capsys.readouterr().out
    result = repository.records(RESULT_TYPE)[0]
    assert (
        main(
            [
                "scoring",
                "show",
                result["id"],
                "--root",
                str(root),
                "--trace",
                "--json",
            ]
        )
        == 0
    )
    traced = json.loads(capsys.readouterr().out)
    traced_types = {record["type"] for record in traced["trace"]["records"]}
    assert traced_types == {
        RESULT_TYPE,
        RUN_TYPE,
        GROUNDING_TASK_TYPE,
        POOL_ENROLLMENT_TYPE,
        POOL_TYPE,
        SCORING_TRACE_TYPE,
        SCORING_EVENT_TYPE,
    }
    assert len(traced["trace"]["external_references"]) == 2

    traces = repository.records(SCORING_TRACE_TYPE)
    events = repository.records(SCORING_EVENT_TYPE)
    assert len(traces) == 2
    assert len(events) == 2
    assert all(event["results_commit"] for event in events)
    assert all(event["code_provenance"]["version"] for event in events)
    assert repository.path_for(traces[0]).name == "trace.json"
    assert repository.path_for(events[0]).name == "events.jsonl"

    assert (
        main(
            [
                "scoring",
                "score",
                "--pool",
                pool["id"],
                "--root",
                str(root),
                "--no-record",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert len(repository.records(SCORING_EVENT_TYPE)) == 2

    for renderer in (
        "Assertion.Scoring.Trace.History.Renderer",
        "Assertion.Scoring.Trace.Evolution.Renderer",
    ):
        assert (
            main(
                [
                    "scoring",
                    "render",
                    traces[0]["id"],
                    "--renderer",
                    renderer,
                    "--root",
                    str(root),
                ]
            )
            == 0
        )
        assert "events: 1" in capsys.readouterr().out


def test_runtime_exposes_scoring_and_retires_tournament() -> None:
    from tarav.cli.cli import build_parser

    command_action = next(
        action
        for action in build_parser()._actions
        if getattr(action, "dest", None) == "command"
    )
    assert "scoring" in command_action.choices
    assert "tournament" not in command_action.choices


def test_agent_runner_retains_resolved_provenance_and_submitted_result(
    tmp_path: Path, monkeypatch
) -> None:
    from tarav.agent.run_runtime import AgentRunResult

    repository = ScoringRepository.initialize(tmp_path / "scoring")
    pool, enrollments, task, _, _ = _task()
    repository.create(pool)
    for enrollment in enrollments:
        repository.create(enrollment)
    repository.create(task)

    class FakeAgent:
        provider = "fake"
        profile_id = None
        home = tmp_path / "agent-home"
        default_model = "default-judge"
        account = None

        def run(self, command_config, run_config):
            assert command_config.prompt == render_run(
                task=task,
                run=run,
            )
            assert command_config.interaction_mode == "non_interactive"
            assert run_config.process_mode == "capture"
            repository.create(
                create_result(run=run, tiers=tuple((label,) for label in run["labels"]))
            )
            return AgentRunResult(exit_code=0, stdout="submitted", stderr="")

    monkeypatch.setattr("tarav.scoring.runner.resolve_agent", lambda **_: FakeAgent())
    run, _ = prepare_agent_run(
        repository=repository,
        task=task,
        provider="fake",
        profile=None,
        home=tmp_path / "agent-home",
        model="judge-v1",
        account="judge-account",
        cwd=tmp_path,
        seed="runner-test",
    )

    completed, result = execute_run(
        repository=repository,
        run=run,
        timeout_sec=10,
    )

    assert completed["status"] == "Awaiting.Result"
    assert completed["runner"]["provider"] == "fake"
    assert completed["runner"]["model"] == "judge-v1"
    assert repository.resolve(completed["id"]) == completed
    assert repository.result_for_run(completed["id"])["id"] == result["id"]


def test_exact_record_references_resolve_historical_editions(tmp_path: Path) -> None:
    repository = ScoringRepository.initialize(tmp_path / "scoring")
    pool, enrollments, task, _, _ = _task()
    repository.create(pool)
    for enrollment in enrollments:
        repository.create(enrollment)
    repository.create(task)
    run = repository.create(
        create_run(
            task=task,
            runner={"type": "Unknown.Ranking.Runner"},
            repository_root=str(repository.root),
            code_provenance=_code_provenance(),
            seed="historical",
        )
    )

    repository.save({**task, "appendix": ["Later Task edition."]})

    assert repository.resolve(task["id"])["appendix"] == ["Later Task edition."]
    assert repository.resolve_reference(run["task_ref"]) == task


def test_grounding_task_resolves_diagram_line_editions_and_support(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    initialize_project_layout(project_root)
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "diagram")
    model = namespace.create_model(label="Tarav")
    config = DiagramConfiguration.load(tmp_path / "diagram.json", create=True).mount(
        namespace, default=True
    )
    config.diagram().set_project_main_model(project_root, model.ship)
    block_ship = str(uuid4())
    user_ref = {
        "session_identity": "a" * 64,
        "turn_address": "1" * 64,
        "turn_hash": "2" * 64,
    }
    agent_ref = {
        "session_identity": "a" * 64,
        "turn_address": "5" * 64,
        "turn_hash": "6" * 64,
    }
    block = ShipDraft(
        block_ship,
        {
            "type": BLOCK_SHIP_TYPE,
            "model_ship": model.ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "block_type": DESIGN_BLOCK_OBJECT_TYPE,
                    "data": {"label": "Scoring"},
                }
            ],
        },
    )
    lines = []
    line_ids = []
    for text in ("Results are evidence.", "Scores interpret Results."):
        line_ship = str(uuid4())
        line_ids.append(line_ship)
        lines.append(
            ShipDraft(
                line_ship,
                {
                    "type": LINE_SHIP_TYPE,
                    "model_ship": model.ship,
                    "block_ship": block_ship,
                    "editions": [
                        {
                            "id": str(uuid4()),
                            "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
                            "producer": agent_ref,
                            "support": [{"root": user_ref, "neighborhood": []}],
                            "data": {"text": text},
                        }
                    ],
                },
            )
        )
    namespace.apply(CaptureManifest(model.ship, (block, *lines)), commit=False)
    normal_model = {
        "session": {"identity_hash": "a" * 64, "session_id": "session"},
        "events": [],
        "messages": [
            {
                "message_address": "3" * 64,
                "message_hash": "4" * 64,
                "side": "user",
                "text": "Keep ranking evidence separate from scores.",
            }
        ],
        "turns": [
            {
                **user_ref,
                "side": "user",
                "message_refs": [
                    {"message_address": "3" * 64, "message_hash": "4" * 64}
                ],
                "event_refs": [],
            }
        ],
    }
    pool = create_pool("grounding")
    enrollments = create_line_grounding_enrollments(
        pool=pool,
        project_path=project_root,
        line_ships=line_ids,
        diagram_config=config.path,
    )
    task = create_line_grounding_task(
        pool=pool,
        enrollments=enrollments,
        project_path=project_root,
        diagram_config=config.path,
        evidence=ChatlasEvidence(model_loader=lambda _: normal_model),
    )

    assert task["type"] == GROUNDING_TASK_TYPE
    assert "Block: Scoring" in task["candidates"][0]["presentation"]
    assert (
        "Keep ranking evidence separate from scores."
        in task["candidates"][0]["presentation"]
    )
    enrollment_ref = task["candidates"][0]["enrollment_ref"]
    enrollment = next(
        item for item in enrollments if item["id"] == enrollment_ref["id"]
    )
    assertion_ref = enrollment["assertion_ref"]
    assert assertion_ref["type"] == GROUNDING_ASSERTION_REFERENCE_TYPE
    assert assertion_ref["subject_ref"]["line_ship"] == line_ids[0]
    assert set(assertion_ref["subject_ref"]) == {
        "type",
        "namespace_id",
        "line_ship",
        "edition_id",
    }

    scoring_root = tmp_path / "cli-scoring"
    assert main(["scoring", "init", "--root", str(scoring_root)]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "scoring",
                "pool",
                "create",
                "diagram.line.grounding.test",
                "--root",
                str(scoring_root),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "scoring",
                "pool",
                "enroll",
                "diagram.line.grounding.test",
                "--project",
                str(project_root),
                "--diagram-config",
                str(config.path),
                "--line",
                line_ids[0],
                "--line",
                line_ids[1],
                "--root",
                str(scoring_root),
            ]
        )
        == 0
    )
    assert "enrollment:" in capsys.readouterr().out
    monkeypatch.setattr(
        "tarav.scoring.tasks.ChatlasEvidence",
        lambda chatlas_root=None: ChatlasEvidence(model_loader=lambda _: normal_model),
    )
    assert (
        main(
            [
                "scoring",
                "task",
                "--pool",
                "diagram.line.grounding.test",
                "--project",
                str(project_root),
                "--diagram-config",
                str(config.path),
                "--root",
                str(scoring_root),
                "--seed",
                "manual-run",
            ]
        )
        == 0
    )
    task_output = capsys.readouterr().out
    assert "task:" in task_output
    assert "run:" in task_output
    assert "tarav scoring submit" in task_output
    retained_run = ScoringRepository(scoring_root).open().records(RUN_TYPE)[0]
    assert retained_run["runner"] == {"type": "Unknown.Ranking.Runner"}
    assert retained_run["status"] == "Awaiting.Result"
    assert (
        main(
            [
                "scoring",
                "assertion",
                "--project",
                str(project_root),
                "--diagram-config",
                str(config.path),
                "--line",
                line_ids[0],
                "--root",
                str(scoring_root),
                "--json",
            ]
        )
        == 0
    )
    assertion_graph = json.loads(capsys.readouterr().out)
    assert any(
        record["type"] == POOL_ENROLLMENT_TYPE for record in assertion_graph["records"]
    )
